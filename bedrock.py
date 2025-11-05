import boto3
from botocore.config import Config
import json
from typing import List, Dict, Any, Optional, Tuple

def generate_message(bedrock_runtime: Any, model_id: str, messages: List[Dict[str, str]], max_tokens: int) -> Dict[str, Any]:
    """
    Generates a message using the specified bedrock runtime, model ID, messages, and maximum tokens.

    Args:
        bedrock_runtime (object): The bedrock runtime object.
        model_id (str): The ID of the model to invoke.
        messages (list): A list of messages to include in the generation.
        max_tokens (int): The maximum number of tokens to generate.

    Returns:
        dict: The generated message as a dictionary.

    """
    body=json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": messages
        }  
    )    
    response = bedrock_runtime.invoke_model(body=body, modelId=model_id)
    return json.loads(response.get('body').read())

def simple_prompt(bedrock_runtime: Any, prompt: str, model_id: str = 'anthropic.claude-3-sonnet-20240229-v1:0', 
                  max_tokens: int = 1000, top_p: Optional[float]=None, temperature: Optional[float]=None, 
                  top_k: Optional[int]=None, stop_sequences: Optional[List[str]]=None) -> Tuple[str,int,int]:
    """
    Generates a simple prompt using the specified bedrock runtime, prompt, model ID, and maximum tokens.

    Args:
        bedrock_runtime (object): The bedrock runtime object.
        prompt (str): The prompt to use for generation.
        model_id (str, optional): The ID of the model to invoke. Defaults to 'anthropic.claude-3-sonnet-20240229-v1:0'.
        max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 1000.

    Returns:
        str: The generated response to the prompt.
        int: The reported number input tokens.
        int: The reported number of output tokens.
    """
    # Setup the appropriate body
    body={}
    if 'anthropic' in model_id:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt }]
        }
        if top_p is not None:
            body['top_p'] = top_p
        if temperature is not None:
            body['temperature'] = temperature
        if top_k is not None:
            body['top_k'] = top_k
        if stop_sequences is not None:
            body['stop_sequences'] = stop_sequences
    elif 'mistral' in model_id:
        body =  {
                    'prompt': "<s> [INST] " + prompt + ' [/INST]',
                    'max_tokens': max_tokens,
                }
        if top_p is not None:
            raise ValueError('top_p not supported for mistral models')
        if temperature is not None:
            body['temperature'] = temperature
        if top_k is not None:
            body['top_k'] = top_k
        if stop_sequences is not None:
            body['stop'] = stop_sequences
    elif 'meta.llama' in model_id:
        body =  {
                    'prompt': f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n{prompt} <|eot_id|><|start_header_id|>assistant<|end_header_id|>\n",
                    'max_gen_len': max_tokens,
                }
        if temperature is not None:
            body['temperature'] = temperature
        if top_p is not None:
            body['top_p'] = top_p
        if top_k is not None:
            raise ValueError('top_k not supported for Llama models')
        if stop_sequences is not None:
            raise ValueError('stop_sequences not supported for Llama models')
    else:
        raise ValueError(f'Only anthropic, llama, and mistral supported')
    
    # Actually InvokeModel here
    response = bedrock_runtime.invoke_model(body=json.dumps(body), modelId=model_id)
    response_body = json.loads(response.get('body').read())
    
    # Output dependent on output response
    if 'anthropic' in model_id:
        return response_body['content'][0]['text'], response_body['usage']['input_tokens'], response_body['usage']['output_tokens']
    elif 'mistral' in model_id:
        # Mistral models don't give token count, approximate to 1.5 * #word
        text = response_body['outputs'][0]['text'] 
        return text, int(1.2 * len(prompt.split(' '))), int(1.5 * len(text.split(' ')))
    elif 'meta.llama' in model_id:
        return response_body['generation'], response_body['prompt_token_count'], response_body['generation_token_count']


def few_shot(bedrock_runtime: Any, prompt: List[str], examples: List[Tuple[str,str]], model_id: str = 'anthropic.claude-3-sonnet-20240229-v1:0', 
                  max_tokens: int = 1000, top_p: Optional[float]=None, temperature: Optional[float]=None, 
                  top_k: Optional[int]=None, stop_sequences: Optional[List[str]]=None) -> Tuple[str,int,int]:
    """
    Generates a simple prompt using the specified bedrock runtime, prompt, model ID, and maximum tokens.

    Args:
        bedrock_runtime (object): The bedrock runtime object.
        prompt (str): The prompt to use for generation.
        examples(List[Tuple[str,str]]): List of examples, each element is a pair of (prompt,response)
        model_id (str, optional): The ID of the model to invoke. Defaults to 'anthropic.claude-3-sonnet-20240229-v1:0'.
        max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 1000.

    Returns:
        str: The generated response to the prompt.
        int: The reported number input tokens.
        int: The reported number of output tokens.
    """
    # Setup the appropriate body
    body={}
    if 'anthropic' in model_id:
        messages = []
        for example,response in examples:
            messages.append({"role": "user", "content": example })
            messages.append({"role": "assistant", "content": response })
        messages.append({"role": "user", "content": prompt })
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": messages
        }
        if top_p is not None:
            body['top_p'] = top_p
        if temperature is not None:
            body['temperature'] = temperature
        if top_k is not None:
            body['top_k'] = top_k
        if stop_sequences is not None:
            body['stop_sequences'] = stop_sequences
    else:
        raise ValueError(f'Only anthropic currently supported')
    
    # Actually InvokeModel here
    response = bedrock_runtime.invoke_model(body=json.dumps(body), modelId=model_id)
    response_body = json.loads(response.get('body').read())
    
    # Output dependent on output response
    if 'anthropic' in model_id:
        return response_body['content'][0]['text'], response_body['usage']['input_tokens'], response_body['usage']['output_tokens']


def get_embeddings_short(client, texts, input_type='clustering',truncate="NONE",model_id="cohere.embed-english-v3"):
    '''
    Base function for accessing Bedrock embeddings
    Use get_embeddings if list of texts is longer than model maximum
    '''
    if 'cohere' in model_id:
        json_params = {
                'texts': texts,
                'truncate': truncate, 
                "input_type": input_type
            }
    else: 
        raise Exception(f'Invalid embedding model {model_id}')
    json_body = json.dumps(json_params)
    params = {'body': json_body, 'modelId': model_id,}

    # Invoke the model and print the response
    result = client.invoke_model(**params)
    response = json.loads(result['body'].read().decode())
    return response['embeddings']

def get_embeddings(client,texts, chunksize=50, **kwargs) -> List[List[float]]:
    '''
    Main function for getting Bedrock embeddings
    Chunks up list of texts into manageable size and flattens sublists
    '''
    return [embedding
            for start in range(0,len(texts),chunksize)
                for embedding in get_embeddings_short(client,texts[start:(start+chunksize)], **kwargs)]


def get_client(region: str="us-east-1", read_timeout=1500) -> Any:
    """
    Returns a client object for the bedrock runtime service.

    Args:
        region (str, optional): The AWS region to use. Defaults to "us-east-1".
        read_timeout(int,optional): Timeout interval, AWS default is 5 minutes (300), 
                                    which often fails on longer >2000 word requests, so default is 1500

    Returns:
        object: The bedrock runtime client object.

    """
    config = Config(read_timeout=read_timeout)
    client = boto3.client('bedrock-runtime', region, config=config)
    return client

import boto3
import json
class BedrockClient:
    def __init__(self, region_name="us-east-1"):
        self.client = boto3.client("bedrock-runtime", region_name=region_name)

    def simple_prompt(self, prompt, model_id, max_tokens=1000):
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "top_p": 1
        })

        response = self.client.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json"
        )

        response_body = json.loads(response['body'].read())
        return (
            response_body['content'][0]['text'],
            response_body.get('usage', {}).get('input_tokens', 0),
            response_body.get('usage', {}).get('output_tokens', 0)
        )

    def converse(self, messages, system_prompt, model_id, max_tokens=4096, temperature=0.7, top_p=0.9):
        """
        Use the Converse API with separate system prompt and messages.
        This is the proper way to send context + question to Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System-level instructions and context
            model_id: Model ID to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling

        Returns:
            tuple: (response_text, input_tokens, output_tokens)
        """
        response = self.client.converse(
            modelId=model_id,
            messages=messages,
            system=[{"text": system_prompt}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": temperature,
                "topP": top_p
            }
        )

        # Extract text from response
        output_message = response['output']['message']
        response_text = output_message['content'][0]['text']

        # Extract token usage
        usage = response.get('usage', {})
        input_tokens = usage.get('inputTokens', 0)
        output_tokens = usage.get('outputTokens', 0)

        return response_text, input_tokens, output_tokens



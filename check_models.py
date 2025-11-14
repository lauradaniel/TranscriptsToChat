#!/usr/bin/env python3
"""
Script to check available Claude models in AWS Bedrock
"""
import sys
import os

# Add current directory to path to import bedrock module
sys.path.insert(0, os.path.dirname(__file__))

try:
    import boto3

    bedrock = boto3.client('bedrock', region_name='us-east-1')
    response = bedrock.list_foundation_models()

    claude_models = [m for m in response['modelSummaries'] if 'claude' in m['modelId'].lower()]

    print('\n' + '='*80)
    print('AVAILABLE CLAUDE MODELS IN AWS BEDROCK (us-east-1)')
    print('='*80)

    # Sort by model ID
    for model in sorted(claude_models, key=lambda x: x['modelId']):
        model_id = model['modelId']
        model_name = model.get('modelName', 'N/A')

        # Get input/output modalities
        input_mods = ', '.join(model.get('inputModalities', []))
        output_mods = ', '.join(model.get('outputModalities', []))

        print(f'\n📌 {model_id}')
        print(f'   Name: {model_name}')
        print(f'   Input: {input_mods} → Output: {output_mods}')

        # Check if it's the current model being used
        if model_id == "us.anthropic.claude-3-5-sonnet-20241022-v2:0":
            print(f'   ⭐ CURRENTLY IN USE')

    print('\n' + '='*80)
    print('\nNOTE: Context window sizes for Claude models:')
    print('  • Claude 3.5 Sonnet (all versions): 200K tokens')
    print('  • Claude 3 Opus: 200K tokens')
    print('  • Claude 3 Haiku: 200K tokens')
    print('\nTo process more transcripts, you would need:')
    print('  1. A model with larger context (500K+ tokens) - check if available above')
    print('  2. OR use a different processing strategy (batching, summarization, etc.)')
    print('='*80 + '\n')

except ImportError as e:
    print(f'\n❌ Error: boto3 not installed')
    print(f'Install it with: pip3 install boto3 --user')
    sys.exit(1)
except Exception as e:
    print(f'\n❌ Error: {e}')
    print(f'\nMake sure:')
    print(f'  1. AWS credentials are configured (~/.aws/credentials)')
    print(f'  2. You have bedrock:ListFoundationModels permission')
    print(f'  3. You have access to Bedrock in us-east-1 region')
    sys.exit(1)

"""
Flask Backend API for Transcript Analysis Project
Integrates with the existing HTML/JS frontend
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
import sys
import platform
from pathlib import Path
from datetime import datetime
from database import TranscriptDatabase
from csv_processor import CSVProcessor
from main_integration import create_project_from_csv
from bedrock import BedrockClient

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Configuration
UPLOAD_FOLDER = 'uploads'
DB_PATH = '/tmp/transcript_projects.db'  # Use local path, not NFS
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database
db = TranscriptDatabase(DB_PATH)


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': os.path.exists(DB_PATH)
    })


@app.route('/api/debug/csv', methods=['POST'])
def debug_csv():
    """
    Debug endpoint to check CSV structure without creating project
    Helps identify column issues
    """
    try:
        if 'csv_file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No CSV file provided'
            }), 400
        
        csv_file = request.files['csv_file']
        
        # Save temporarily
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_path = os.path.join(UPLOAD_FOLDER, f"debug_{timestamp}_{csv_file.filename}")
        csv_file.save(temp_path)
        
        # Validate CSV
        processor = CSVProcessor()
        is_valid, errors = processor.validate_csv_structure(temp_path)
        
        # Read first few lines
        import csv as csv_lib
        with open(temp_path, 'r', encoding='utf-8') as f:
            sample = f.read(1024)
            f.seek(0)
            sniffer = csv_lib.Sniffer()
            try:
                delimiter = sniffer.sniff(sample).delimiter
                delimiter_name = 'TAB' if delimiter == '\t' else 'COMMA'
            except:
                delimiter = ','
                delimiter_name = 'COMMA (default)'
            
            # Check if we need to switch to tab
            first_line = f.readline()
            f.seek(0)
            if delimiter == ',' and ',' not in first_line and '\t' in first_line:
                delimiter = '\t'
                delimiter_name = 'TAB (detected tabs in header)'
            
            reader = csv_lib.DictReader(f, delimiter=delimiter)
            headers = list(reader.fieldnames)
            
            # Read first 2 rows as sample
            first_rows = []
            for i, row in enumerate(reader):
                if i >= 2:
                    break
                first_rows.append(dict(row))
        
        # Clean up
        os.remove(temp_path)
        
        return jsonify({
            'success': True,
            'validation': {
                'is_valid': is_valid,
                'errors': errors
            },
            'file_info': {
                'filename': csv_file.filename,
                'size': csv_file.content_length,
                'delimiter': delimiter_name
            },
            'columns': {
                'found': headers,
                'required': processor.REQUIRED_COLUMNS,
                'optional': processor.OPTIONAL_COLUMNS,
                'missing': [col for col in processor.REQUIRED_COLUMNS if col not in headers]
            },
            'sample_data': first_rows
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects', methods=['GET'])
def list_projects():
    """Get all projects"""
    # **CHANGE IS HERE** - Use the context manager for database operations
    try:
        # Note: Using DB_PATH directly and instantiating within the function scope
        with TranscriptDatabase(DB_PATH) as local_db:
            projects = local_db.get_all_projects()
        
        return jsonify({
            'success': True,
            'projects': projects
        })
    except Exception as e:
        print(f"Error listing projects: {str(e)}") # Print error to console for debugging
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects', methods=['POST'])
def create_project():
    """
    Create new project from CSV upload
    
    Expected form data:
    - projectName: string
    - projectDescription: string (optional)
    - csv_file: file
    """
    try:
        # Get form data
        project_name = request.form.get('projectName')
        project_description = request.form.get('projectDescription', '')
        
        # Validate inputs
        if not project_name:
            return jsonify({
                'success': False,
                'error': 'Project name is required'
            }), 400
        
        # Get uploaded file
        if 'csv_file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'CSV file is required'
            }), 400
        
        csv_file = request.files['csv_file']
        
        if csv_file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not csv_file.filename.endswith('.csv'):
            return jsonify({
                'success': False,
                'error': 'File must be a CSV'
            }), 400
        
        # Save uploaded CSV
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"{timestamp}_{csv_file.filename}"
        csv_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        csv_file.save(csv_path)
        
        # Process CSV and create project
        result = create_project_from_csv(
            project_name=project_name,
            description=project_description,
            csv_path=csv_path,
            db_path=DB_PATH,
            verify_transcripts=False  # Set to True if you want to verify files exist
        )
        
        # Clean up uploaded file (optional - keep it for reference)
        # os.remove(csv_path)
        
        if result['success']:
            return jsonify({
                'success': True,
                'project_id': result['project_id'],
                'stats': result['stats'],
                'warnings': result['warnings']
            }), 201
        else:
            return jsonify({
                'success': False,
                'errors': result['errors'],
                'stats': result['stats']
            }), 400
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    """
    Delete a project and all its data
    """
    try:
        with TranscriptDatabase(DB_PATH) as db:
            # Check if project exists
            project = db.get_project(project_id)
            if not project:
                return jsonify({
                    'success': False,
                    'error': 'Project not found'
                }), 404
            
            # Delete the project (this will also drop the conversations table)
            cursor = db.conn.cursor()
            
            # Drop conversations table
            table_name = f"conversations_{project_id}"
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            
            # Delete project record
            cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            db.conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'Project {project_id} deleted successfully'
            })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>', methods=['GET'])
def get_project(project_id):
    """Get project details"""
    try:
        project = db.get_project(project_id)
        
        if not project:
            return jsonify({
                'success': False,
                'error': 'Project not found'
            }), 404
        
        return jsonify({
            'success': True,
            'project': project
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/columns', methods=['GET'])
def get_report_columns(project_id):
    """Get available columns for report building"""
    try:
        # Verify project exists
        project = db.get_project(project_id)
        if not project:
            return jsonify({
                'success': False,
                'error': 'Project not found'
            }), 404
        
        columns = db.get_report_columns(project_id)
        
        # Return columns with metadata
        column_metadata = {
            'Intent': {'type': 'categorical', 'filterable': True, 'groupable': True},
            'Topic': {'type': 'categorical', 'filterable': True, 'groupable': True},
            'Category': {'type': 'categorical', 'filterable': True, 'groupable': True},
            'AgentTask': {'type': 'categorical', 'filterable': True, 'groupable': True},
            'SentimentScore': {'type': 'numeric', 'filterable': True, 'groupable': False},
            'DurationSeconds': {'type': 'numeric', 'filterable': True, 'groupable': False},
            'IsAutomatable': {'type': 'categorical', 'filterable': True, 'groupable': True}
        }
        
        return jsonify({
            'success': True,
            'columns': columns,
            'metadata': column_metadata
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/conversations', methods=['GET'])
def get_conversations(project_id):
    """
    Get conversations with optional filters
    
    Query parameters:
    - intent: filter by intent
    - topic: filter by topic
    - agent_task: filter by agent task
    - is_automatable: filter by automatable flag
    - limit: max number of results
    """
    try:
        # Build filters from query params
        filters = {}
        if request.args.get('intent'):
            filters['intent'] = request.args.get('intent')
        if request.args.get('topic'):
            filters['topic'] = request.args.get('topic')
        if request.args.get('agent_task'):
            filters['agent_task'] = request.args.get('agent_task')
        if request.args.get('is_automatable'):
            filters['is_automatable'] = request.args.get('is_automatable')
        
        limit = request.args.get('limit', type=int)
        
        conversations = db.get_conversations(
            project_id, 
            filters=filters if filters else None,
            limit=limit
        )
        
        return jsonify({
            'success': True,
            'count': len(conversations),
            'conversations': conversations
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/report', methods=['POST'])
def generate_report(project_id):
    """
    Generate aggregated report
    
    Request body:
    {
        "group_by": "intent",  // Column to group by
        "filters": {           // Optional filters
            "topic": "Billing"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'group_by' not in data:
            return jsonify({
                'success': False,
                'error': 'group_by parameter is required'
            }), 400
        
        group_by = data['group_by'].lower()
        filters = data.get('filters', {})
        
        # Validate group_by column
        valid_columns = ['intent', 'topic', 'category', 'agent_task', 'is_automatable']
        if group_by not in valid_columns:
            return jsonify({
                'success': False,
                'error': f'Invalid group_by column. Must be one of: {", ".join(valid_columns)}'
            }), 400
        
        # Get aggregated data
        report_data = db.get_aggregated_data(
            project_id,
            group_by,
            filters if filters else None
        )
        
        return jsonify({
            'success': True,
            'group_by': group_by,
            'filters': filters,
            'data': report_data
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/chat/context', methods=['POST'])
def get_chat_context(project_id):
    """
    Get transcript file paths for chat context
    Used when user clicks chat button on a report row
    
    Request body:
    {
        "filters": {
            "intent": "Billing Question",
            "sentiment_score": 4.5
        }
    }
    
    Returns:
    {
        "success": true,
        "transcript_files": [
            ["call_001", "/path/to/transcript.json"],
            ["call_002", "/path/to/transcript2.json"]
        ],
        "count": 2
    }
    """
    try:
        data = request.get_json()
        filters = data.get('filters', {})
        
        if not filters:
            return jsonify({
                'success': False,
                'error': 'Filters are required to identify relevant conversations'
            }), 400
        
        # Get transcript file paths
        transcript_files = db.get_interaction_ids_by_filter(
            project_id,
            filters
        )
        
        return jsonify({
            'success': True,
            'transcript_files': transcript_files,
            'count': len(transcript_files)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/summary', methods=['GET'])
def get_project_summary(project_id):
    """
    Get summarized/aggregated view of conversations grouped by intent and topic
    Returns data formatted for the Chat Summary Table
    """
    try:
        # Check if project exists
        with TranscriptDatabase(DB_PATH) as local_db:
            project = local_db.get_project(project_id)
            if not project:
                return jsonify({
                    'success': False,
                    'error': 'Project not found'
                }), 404
            
            # Check if conversations table exists
            table_name = f"conversations_{project_id}"
            cursor = local_db.conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (table_name,))
            
            if not cursor.fetchone():
                return jsonify({
                    'success': True,
                    'summary': [],
                    'count': 0,
                    'message': f'No data found for project {project_id}'
                })
            
            # Query to group conversations by intent, topic, category, and agent_task
            # Return columns: Category, Topic, Intent, Agent_Task, Volume
            query = f"""
                SELECT 
                    COALESCE(category, 'Not Specified') as Category,
                    COALESCE(topic, 'Not Specified') as Topic,
                    COALESCE(intent, 'Unknown') as Intent,
                    COALESCE(agent_task, 'Not Specified') as Agent_Task,
                    COUNT(DISTINCT interaction_id) as Volume
                FROM {table_name}
                GROUP BY intent, topic, category, agent_task
                ORDER BY Volume DESC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Format results
            summary_data = []
            for row in rows:
                summary_data.append({
                    'Category': row[0],
                    'Topic': row[1],
                    'Intent': row[2],
                    'Agent_Task': row[3],
                    'Volume': row[4]
                })
        
        return jsonify({
            'success': True,
            'summary': summary_data,
            'count': len(summary_data)
        })
    
    except Exception as e:
        print(f"❌ ERROR in get_project_summary for project {project_id}:")
        print(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'Check Flask terminal for full error traceback'
        }), 500


@app.route('/api/projects/<int:project_id>/stats', methods=['GET'])
def get_project_stats(project_id):
    """
    Get project statistics for dashboard
    """
    try:
        project = db.get_project(project_id)
        if not project:
            return jsonify({
                'success': False,
                'error': 'Project not found'
            }), 404
        
        # Get various statistics
        intent_stats = db.get_aggregated_data(project_id, 'intent')
        topic_stats = db.get_aggregated_data(project_id, 'topic')
        
        # Calculate overall stats
        all_conversations = db.get_conversations(project_id)
        total_duration = sum(c['duration_seconds'] or 0 for c in all_conversations)
        avg_sentiment = sum(c['sentiment_score'] or 0 for c in all_conversations) / len(all_conversations) if all_conversations else 0
        
        return jsonify({
            'success': True,
            'stats': {
                'total_conversations': project['total_records'],
                'total_duration_seconds': total_duration,
                'avg_duration_seconds': total_duration / project['total_records'] if project['total_records'] > 0 else 0,
                'avg_sentiment': avg_sentiment,
                'unique_intents': len(intent_stats),
                'unique_topics': len(topic_stats),
                'intent_breakdown': intent_stats[:10],  # Top 10
                'topic_breakdown': topic_stats[:10]      # Top 10
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


# === HELPER FUNCTIONS FOR AI CHAT ===

# Path conversion configuration - UPDATE THESE based on your setup
PATH_MAPPINGS = {
    # Format: 'UNC_prefix': 'local_mount_path'
    # Example: '\\\\VAOD177APP05\\Media': '/mnt/media'
    # Add your mappings here:
}

def convert_unc_to_local_path(unc_path):
    """
    Convert Windows UNC path to local mounted path.

    Examples:
    - Windows: \\VAOD177APP05\Media\file.json -> \\VAOD177APP05\Media\file.json (no change)
    - Linux with mount: \\VAOD177APP05\Media\file.json -> /mnt/media/file.json

    Returns: (converted_path, conversion_notes)
    """
    if not unc_path:
        return unc_path, "Empty path"

    original_path = unc_path
    notes = []

    # Remove quotes if present
    if unc_path.startswith('"') and unc_path.endswith('"'):
        unc_path = unc_path[1:-1]
        notes.append("Removed surrounding quotes")

    # Check if running on Windows
    is_windows = platform.system() == 'Windows'

    if is_windows:
        # On Windows, UNC paths should work directly
        # Just normalize the path
        unc_path = unc_path.replace('/', '\\')
        notes.append(f"Running on Windows - using UNC path directly")
        return unc_path, "; ".join(notes) if notes else "Windows UNC path"

    # On Linux/Mac, need to convert UNC to mounted path
    notes.append(f"Running on {platform.system()}")

    # Check if path mappings are configured
    if not PATH_MAPPINGS:
        notes.append("⚠️ No PATH_MAPPINGS configured - UNC paths won't work on Linux")
        return unc_path, "; ".join(notes)

    # Try to convert using configured mappings
    for unc_prefix, local_mount in PATH_MAPPINGS.items():
        # Normalize the UNC prefix
        unc_prefix_normalized = unc_prefix.replace('/', '\\').upper()
        unc_path_normalized = unc_path.replace('/', '\\').upper()

        if unc_path_normalized.startswith(unc_prefix_normalized):
            # Replace UNC prefix with local mount
            relative_path = unc_path[len(unc_prefix):]
            relative_path = relative_path.replace('\\', '/')
            if relative_path.startswith('/'):
                relative_path = relative_path[1:]

            converted_path = os.path.join(local_mount, relative_path)
            notes.append(f"Converted UNC to local mount: {unc_prefix} -> {local_mount}")
            return converted_path, "; ".join(notes)

    notes.append(f"⚠️ No matching PATH_MAPPING found for {unc_path[:50]}...")
    return unc_path, "; ".join(notes)


def load_transcript_file(file_path):
    """
    Load a transcript JSON file from the network path.
    Handles both Windows UNC paths and local paths.
    Returns the parsed JSON data or None if file cannot be loaded.
    """
    try:
        # Convert path if needed
        converted_path, conversion_notes = convert_unc_to_local_path(file_path)

        # Try to access the file
        if not os.path.exists(converted_path):
            print(f"Warning: Transcript file not found: {converted_path}")
            print(f"  Original path: {file_path}")
            print(f"  Conversion notes: {conversion_notes}")
            return None

        with open(converted_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading transcript {file_path}: {str(e)}")
        return None


def clean_transcript(transcript_data):
    """
    Clean transcript data by extracting only conversation turns.

    Expected JSON structure:
    {
        "topics": [  // The conversation array
            {
                "text": "Hello, how can I help you?",
                "speaker": 0,  // 0 = Agent, 1 = Caller
                "startOffset": 1657,
                "endOffset": 6468,
                // May have extra fields we need to remove:
                "category": "...",  // Remove - duplicate of CSV metadata
                "topic": "...",     // Remove - duplicate
                "subTopic": "...",  // Remove - duplicate
                "callDriver": true, // Remove - ML metadata
                "snippet": "...",   // Remove - ML metadata
                "score": 1.0,       // Remove - ML metadata
                "altTopics": [...]  // Remove - alternative classifications
            }
        ],
        "namedEntities": [...],  // Remove - PII data
        "transcriptFile": "...", // Remove - file metadata
        "version": "1.2",        // Remove - version info
        "primaryTopic": {...}    // Remove - duplicate of CSV
    }

    Returns: List of cleaned turns with ONLY text, speaker, start_time, end_time
    """
    if not transcript_data:
        return None

    cleaned_turns = []

    # Handle dict structure with "topics" key (EnlightenXO format)
    if isinstance(transcript_data, dict):
        # First check for "topics" key specifically
        if 'topics' in transcript_data and isinstance(transcript_data['topics'], list):
            for turn in transcript_data['topics']:
                if isinstance(turn, dict) and 'text' in turn:
                    # Extract ONLY the 4 essential fields, discard everything else
                    cleaned_turn = {
                        'text': turn.get('text', '').strip(),
                        'speaker': 'Agent' if turn.get('speaker') == 0 else 'Caller',
                        'start_time': turn.get('startOffset', 0),
                        'end_time': turn.get('endOffset', 0)
                    }
                    # Only add non-empty text
                    if cleaned_turn['text']:
                        cleaned_turns.append(cleaned_turn)
            return cleaned_turns

        # Fallback: search for any key with a list of turns
        for key, value in transcript_data.items():
            if isinstance(value, list) and len(value) > 0:
                if isinstance(value[0], dict) and 'text' in value[0]:
                    # Found a conversation array
                    for turn in value:
                        cleaned_turn = {
                            'text': turn.get('text', '').strip(),
                            'speaker': 'Agent' if turn.get('speaker') == 0 else 'Caller',
                            'start_time': turn.get('startOffset', 0),
                            'end_time': turn.get('endOffset', 0)
                        }
                        if cleaned_turn['text']:
                            cleaned_turns.append(cleaned_turn)
                    return cleaned_turns

        # If no conversation array found
        return []

    # Handle array of conversation turns directly (less common)
    elif isinstance(transcript_data, list):
        for turn in transcript_data:
            if isinstance(turn, dict) and 'text' in turn:
                cleaned_turn = {
                    'text': turn.get('text', '').strip(),
                    'speaker': 'Agent' if turn.get('speaker') == 0 else 'Caller',
                    'start_time': turn.get('startOffset', 0),
                    'end_time': turn.get('endOffset', 0)
                }
                if cleaned_turn['text']:
                    cleaned_turns.append(cleaned_turn)
        return cleaned_turns

    return cleaned_turns if cleaned_turns else []


def format_conversation(turns):
    """
    Format a list of conversation turns into readable text.

    Args:
        turns: List of dicts with 'speaker', 'text', 'start_time', 'end_time'

    Returns:
        Formatted conversation string
    """
    if not turns:
        return "[Empty conversation]"

    formatted = []
    for turn in turns:
        speaker = turn.get('speaker', 'Unknown')
        text = turn.get('text', '')
        start_time = turn.get('start_time', 0)

        # Format: [MM:SS] Speaker: Text
        minutes = int(start_time // 60)
        seconds = int(start_time % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"

        formatted.append(f"[{time_str}] {speaker}: {text}")

    return "\n".join(formatted)


def prepare_chat_context(transcripts, intent, topic, category, agent_task):
    """
    Prepare context string for AI from multiple transcripts.
    Handles large groups intelligently by sampling.
    """
    if not transcripts:
        return "No transcript data available.", 0

    total_count = len(transcripts)

    # Smart sampling strategy based on group size
    if total_count <= 10:
        # Small group: include all
        sample_transcripts = transcripts
        sampling_note = ""
    elif total_count <= 50:
        # Medium group: include first 20
        sample_transcripts = transcripts[:20]
        sampling_note = f"\n(Showing first 20 of {total_count} total transcripts)"
    elif total_count <= 200:
        # Large group: sample every Nth transcript to get ~30 samples
        step = total_count // 30
        sample_transcripts = transcripts[::step][:30]
        sampling_note = f"\n(Showing representative sample of 30 from {total_count} total transcripts)"
    else:
        # Very large group: stratified sample of 50
        # Take samples from beginning, middle, and end
        step = total_count // 50
        sample_transcripts = transcripts[::step][:50]
        sampling_note = f"\n(Showing stratified sample of 50 from {total_count} total transcripts)"

    context_parts = [
        f"You are analyzing customer service transcripts with these characteristics:",
        f"- Category: {category}",
        f"- Topic: {topic}",
        f"- Intent: {intent}",
        f"- Agent Task: {agent_task}",
        f"- Total transcripts: {total_count}",
        sampling_note,
        "\n" + "="*60 + "\n"
    ]

    # Add formatted transcripts
    for idx, transcript in enumerate(sample_transcripts, 1):
        context_parts.append(f"\n--- TRANSCRIPT {idx} ---")

        if isinstance(transcript, list):
            # Already cleaned turns
            context_parts.append(format_conversation(transcript))
        elif isinstance(transcript, dict) and 'data' in transcript:
            # Wrapped in data field
            context_parts.append(format_conversation(transcript['data']))
        else:
            # Fallback
            context_parts.append(json.dumps(transcript, indent=2))

        context_parts.append("")  # Empty line between transcripts

    return "\n".join(context_parts), total_count


@app.route('/api/projects/<int:project_id>/chat/verify', methods=['POST'])
def verify_transcript_files(project_id):
    """
    Verify if transcript files are accessible from the server.
    Useful for debugging file path issues.

    Request body:
    {
        "filters": {
            "intent": "Billing Question",
            "topic": "Payment Issue"
        },
        "sample_size": 5  // Optional, defaults to 5
    }

    Returns:
    {
        "success": true,
        "total_files": 10,
        "accessible": 7,
        "inaccessible": 3,
        "sample_results": [
            {
                "interaction_id": "call_001",
                "file_path": "/path/to/file.json",
                "accessible": true,
                "file_size": 12345,
                "turn_count": 25
            },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        filters = data.get('filters', {})
        sample_size = data.get('sample_size', 5)

        # Get transcript file paths
        with TranscriptDatabase(DB_PATH) as local_db:
            transcript_refs = local_db.get_interaction_ids_by_filter(project_id, filters)

        if not transcript_refs:
            return jsonify({
                'success': False,
                'error': 'No transcripts found matching the specified filters'
            }), 404

        # Check accessibility
        total_files = len(transcript_refs)
        accessible_count = 0
        inaccessible_count = 0
        sample_results = []

        # Check a sample
        for interaction_id, file_path in transcript_refs[:sample_size]:
            # Convert path
            converted_path, conversion_notes = convert_unc_to_local_path(file_path)

            result = {
                'interaction_id': interaction_id,
                'file_path': file_path,
                'converted_path': converted_path if converted_path != file_path else None,
                'conversion_notes': conversion_notes,
                'accessible': False,
                'file_size': None,
                'turn_count': None,
                'error': None
            }

            try:
                if os.path.exists(converted_path):
                    result['accessible'] = True
                    result['file_size'] = os.path.getsize(converted_path)

                    # Try to load and parse
                    transcript_data = load_transcript_file(file_path)
                    if transcript_data:
                        cleaned = clean_transcript(transcript_data)
                        if cleaned:
                            result['turn_count'] = len(cleaned)
                        else:
                            result['error'] = 'File loaded but no conversation turns found'
                    else:
                        result['error'] = 'File exists but could not be parsed as JSON'
                else:
                    result['error'] = f'File not found at path: {converted_path}'
                    result['suggestion'] = 'Check if network share is mounted or configure PATH_MAPPINGS in flask_backend.py'
            except Exception as e:
                result['error'] = str(e)

            if result['accessible']:
                accessible_count += 1
            else:
                inaccessible_count += 1

            sample_results.append(result)

        # System diagnostics
        system_info = {
            'platform': platform.system(),
            'platform_details': platform.platform(),
            'python_version': sys.version.split()[0],
            'path_mappings_configured': len(PATH_MAPPINGS) > 0,
            'path_mappings': PATH_MAPPINGS if PATH_MAPPINGS else None
        }

        return jsonify({
            'success': True,
            'total_files': total_files,
            'sample_checked': len(sample_results),
            'accessible': accessible_count,
            'inaccessible': inaccessible_count,
            'sample_results': sample_results,
            'system_info': system_info,
            'note': f'Checked first {len(sample_results)} files. Increase sample_size to check more.',
            'help': 'If files are not accessible on Linux, configure PATH_MAPPINGS in flask_backend.py to map UNC paths to local mounts.'
        })

    except Exception as e:
        print(f"Verify error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/chat/query', methods=['POST'])
def chat_query(project_id):
    """
    AI Chat endpoint - answers questions about a specific group of transcripts

    Request body:
    {
        "filters": {
            "intent": "Billing Question",
            "topic": "Payment Issue",
            "category": "Finance",
            "agent_task": "Process Refund"
        },
        "question": "What are the common issues in these calls?"
    }

    Returns:
    {
        "success": true,
        "answer": "Based on the transcripts...",
        "transcript_count": 5,
        "tokens_used": {"input": 1500, "output": 300}
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': 'Request body is required'
            }), 400

        filters = data.get('filters', {})
        question = data.get('question', '')

        if not question:
            return jsonify({
                'success': False,
                'error': 'Question is required'
            }), 400

        # Get transcript file paths from database
        with TranscriptDatabase(DB_PATH) as local_db:
            transcript_refs = local_db.get_interaction_ids_by_filter(project_id, filters)

        if not transcript_refs:
            return jsonify({
                'success': False,
                'error': 'No transcripts found matching the specified filters'
            }), 404

        # Load and clean transcripts
        transcripts = []
        failed_loads = 0

        for interaction_id, file_path in transcript_refs:
            transcript_data = load_transcript_file(file_path)
            if transcript_data:
                cleaned = clean_transcript(transcript_data)
                if cleaned:
                    transcripts.append({
                        'interaction_id': interaction_id,
                        'data': cleaned
                    })
            else:
                failed_loads += 1

        if not transcripts:
            return jsonify({
                'success': False,
                'error': f'Could not load any transcript files. {failed_loads} files failed to load. Check file paths and permissions.'
            }), 500

        # Prepare context for AI
        context, total_analyzed = prepare_chat_context(
            [t['data'] for t in transcripts],
            filters.get('intent', 'N/A'),
            filters.get('topic', 'N/A'),
            filters.get('category', 'N/A'),
            filters.get('agent_task', 'N/A')
        )

        # Create prompt for AI
        full_prompt = f"""You are an AI assistant analyzing customer service call transcripts.

Each transcript shows a conversation between an Agent and a Caller, with timestamps.
Format: [MM:SS] Speaker: Text

{context}

User Question: {question}

Instructions:
- Provide a detailed, accurate answer based on the transcripts above
- Reference specific conversations when relevant
- If asking about patterns or trends, analyze across all transcripts shown
- If the transcripts don't contain enough information, say so clearly
- Format your response with clear paragraphs and bullet points where appropriate"""

        # Call AWS Bedrock
        try:
            bedrock = BedrockClient(region_name="us-east-1")
            model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

            # Limit prompt size to avoid token limits
            max_prompt_chars = 100000  # ~25k tokens
            if len(full_prompt) > max_prompt_chars:
                full_prompt = full_prompt[:max_prompt_chars] + "\n\n[Context truncated due to length...]"

            answer, input_tokens, output_tokens = bedrock.simple_prompt(
                prompt=full_prompt,
                model_id=model_id,
                max_tokens=2000
            )

            return jsonify({
                'success': True,
                'answer': answer,
                'transcript_count': len(transcripts),
                'failed_loads': failed_loads,
                'tokens_used': {
                    'input': input_tokens,
                    'output': output_tokens
                }
            })

        except Exception as bedrock_error:
            print(f"Bedrock error: {str(bedrock_error)}")
            return jsonify({
                'success': False,
                'error': f'AI service error: {str(bedrock_error)}',
                'transcript_count': len(transcripts)
            }), 500

    except Exception as e:
        print(f"Chat query error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    print("="*60)
    print("TRANSCRIPT ANALYSIS - FLASK BACKEND")
    print("="*60)
    print(f"Database: {DB_PATH}")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print(f"Server running on: http://localhost:5000")
    print("="*60)
    print("\nAvailable endpoints:")
    print("  GET  /api/health")
    print("  GET  /api/projects")
    print("  POST /api/projects")
    print("  GET  /api/projects/<id>")
    print("  GET  /api/projects/<id>/columns")
    print("  GET  /api/projects/<id>/conversations")
    print("  GET  /api/projects/<id>/summary")
    print("  POST /api/projects/<id>/report")
    print("  POST /api/projects/<id>/chat/context")
    print("  POST /api/projects/<id>/chat/verify   (NEW - verify file access)")
    print("  POST /api/projects/<id>/chat/query    (AI Chat)")
    print("  GET  /api/projects/<id>/stats")
    print("="*60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
"""
Flask Backend API for Transcript Analysis Project
Integrates with the existing HTML/JS frontend
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os
import json
import sys
import platform
import csv
import hashlib
import random
import pandas as pd
from pathlib import Path
from datetime import datetime
from database import TranscriptDatabase
from csv_processor import CSVProcessor
from main_integration import create_project_from_csv
from bedrock import BedrockClient

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)  # Enable CORS for frontend communication

# Configuration
UPLOAD_FOLDER = 'uploads'
DB_PATH = 'data/transcript_projects.db'  # Changed from /tmp to persistent location
MAX_CHAT_TRANSCRIPTS = 200  # Maximum transcripts to process for AI chat to stay within token limits
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('data', exist_ok=True)  # Ensure data directory exists for database

# Initialize database
db = TranscriptDatabase(DB_PATH)


# Serve frontend files
@app.route('/')
def serve_index():
    """Serve the main index.html file"""
    return send_from_directory('.', 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files (CSS, JS, images, etc.)"""
    return send_from_directory('.', path)


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

    Query parameters (optional):
        categories: Comma-separated list of categories to filter
        topics: Comma-separated list of topics to filter
        intents: Comma-separated list of intents to filter
        agent_tasks: Comma-separated list of agent tasks to filter
        is_automatable: '1' or 'true' to filter only automatable conversations
    """
    try:
        # Get filter parameters from query string
        filter_categories = request.args.get('categories', '').split(',') if request.args.get('categories') else []
        filter_topics = request.args.get('topics', '').split(',') if request.args.get('topics') else []
        filter_intents = request.args.get('intents', '').split(',') if request.args.get('intents') else []
        filter_agent_tasks = request.args.get('agent_tasks', '').split(',') if request.args.get('agent_tasks') else []
        filter_is_automatable = request.args.get('is_automatable', '').lower() in ['1', 'true']

        # Get sentiment range filters
        sentiment_min = request.args.get('sentiment_min')
        sentiment_max = request.args.get('sentiment_max')
        if sentiment_min:
            sentiment_min = float(sentiment_min)
        if sentiment_max:
            sentiment_max = float(sentiment_max)

        # Get duration range filters
        duration_min = request.args.get('duration_min')
        duration_max = request.args.get('duration_max')
        if duration_min:
            duration_min = float(duration_min)
        if duration_max:
            duration_max = float(duration_max)

        # Get group_by parameter (comma-separated column names)
        group_by_param = request.args.get('group_by', '')
        group_by_columns = [c.strip() for c in group_by_param.split(',') if c.strip()] if group_by_param else ['category', 'topic', 'intent', 'agent_task']

        # Clean up empty strings from split
        filter_categories = [c.strip() for c in filter_categories if c.strip()]
        filter_topics = [t.strip() for t in filter_topics if t.strip()]
        filter_intents = [i.strip() for i in filter_intents if i.strip()]
        filter_agent_tasks = [a.strip() for a in filter_agent_tasks if a.strip()]

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

            # Build WHERE clause for filters
            where_conditions = []
            params = []

            # Category filter
            if filter_categories:
                category_conditions = []
                for cat in filter_categories:
                    if cat == 'Not Specified' or cat == 'Unknown':
                        category_conditions.append("category IS NULL")
                    else:
                        category_conditions.append("category = ?")
                        params.append(cat)
                if category_conditions:
                    where_conditions.append(f"({' OR '.join(category_conditions)})")

            # Topic filter
            if filter_topics:
                topic_conditions = []
                for topic in filter_topics:
                    if topic == 'Not Specified' or topic == 'Unknown':
                        topic_conditions.append("topic IS NULL")
                    else:
                        topic_conditions.append("topic = ?")
                        params.append(topic)
                if topic_conditions:
                    where_conditions.append(f"({' OR '.join(topic_conditions)})")

            # Intent filter
            if filter_intents:
                intent_conditions = []
                for intent in filter_intents:
                    if intent == 'Not Specified' or intent == 'Unknown':
                        intent_conditions.append("intent IS NULL")
                    else:
                        intent_conditions.append("intent = ?")
                        params.append(intent)
                if intent_conditions:
                    where_conditions.append(f"({' OR '.join(intent_conditions)})")

            # Agent Task filter
            if filter_agent_tasks:
                agent_task_conditions = []
                for task in filter_agent_tasks:
                    if task == 'Not Specified' or task == 'Unknown':
                        agent_task_conditions.append("agent_task IS NULL")
                    else:
                        agent_task_conditions.append("agent_task = ?")
                        params.append(task)
                if agent_task_conditions:
                    where_conditions.append(f"({' OR '.join(agent_task_conditions)})")

            # IsAutomatable filter
            if filter_is_automatable:
                where_conditions.append("is_automatable = '1'")

            # Sentiment score filter
            if sentiment_min is not None:
                where_conditions.append("sentiment_score >= ?")
                params.append(sentiment_min)
            if sentiment_max is not None:
                where_conditions.append("sentiment_score <= ?")
                params.append(sentiment_max)

            # Duration filter
            if duration_min is not None:
                where_conditions.append("duration_seconds >= ?")
                params.append(duration_min)
            if duration_max is not None:
                where_conditions.append("duration_seconds <= ?")
                params.append(duration_max)

            # Build dynamic SELECT and GROUP BY based on group_by_columns
            # Map lowercase column names to display names
            column_map = {
                'category': ('category', 'Category'),
                'topic': ('topic', 'Topic'),
                'intent': ('intent', 'Intent'),
                'agent_task': ('agent_task', 'Agent_Task')
            }

            select_columns = []
            for col in group_by_columns:
                if col in column_map:
                    db_col, display_name = column_map[col]
                    coalesce_value = "'Unknown'" if col == 'intent' else "'Not Specified'"
                    select_columns.append(f"COALESCE({db_col}, {coalesce_value}) as {display_name}")

            select_columns.append("COUNT(DISTINCT interaction_id) as Volume")

            query = f"""
                SELECT
                    {', '.join(select_columns)}
                FROM {table_name}
            """

            if where_conditions:
                query += " WHERE " + " AND ".join(where_conditions)

            # GROUP BY only the columns specified
            query += f"""
                GROUP BY {', '.join(group_by_columns)}
                ORDER BY Volume DESC
            """

            print(f"\n🔍 Executing summary query with filters:")
            print(f"   Categories: {filter_categories}")
            print(f"   Topics: {filter_topics}")
            print(f"   Intents: {filter_intents}")
            print(f"   Agent Tasks: {filter_agent_tasks}")
            print(f"   Is Automatable: {filter_is_automatable}")
            print(f"   Query: {query}")
            print(f"   Params: {params}")

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Format results dynamically based on columns returned
            column_names = [description[0] for description in cursor.description]
            summary_data = []
            for row in rows:
                row_dict = {}
                for i, value in enumerate(row):
                    row_dict[column_names[i]] = value
                # Fill in missing columns with 'Not Specified' for frontend compatibility
                if 'Category' not in row_dict:
                    row_dict['Category'] = 'Not Specified'
                if 'Topic' not in row_dict:
                    row_dict['Topic'] = 'Not Specified'
                if 'Intent' not in row_dict:
                    row_dict['Intent'] = 'Unknown'
                if 'Agent_Task' not in row_dict:
                    row_dict['Agent_Task'] = 'Not Specified'
                summary_data.append(row_dict)

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
     '\\\\vaod177enlext02\\Media': '/mnt/Media'
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


def format_conversation(turns, max_turns=None):
    """
    Format a list of conversation turns into readable text.

    Args:
        turns: List of dicts with 'speaker', 'text', 'start_time', 'end_time'
        max_turns: Optional limit on number of turns to include (for very long conversations)

    Returns:
        Formatted conversation string
    """
    if not turns:
        return "[Empty conversation]"

    # Truncate if needed to stay within token limits
    turns_to_format = turns[:max_turns] if max_turns else turns
    was_truncated = max_turns and len(turns) > max_turns

    formatted = []
    for turn in turns_to_format:
        speaker = turn.get('speaker', 'Unknown')
        text = turn.get('text', '')
        start_time = turn.get('start_time', 0)

        # Format: [MM:SS] Speaker: Text
        minutes = int(start_time // 60)
        seconds = int(start_time % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"

        formatted.append(f"[{time_str}] {speaker}: {text}")

    if was_truncated:
        formatted.append(f"\n[... {len(turns) - max_turns} more conversation turns omitted for brevity ...]")

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
    # OPTIMIZED: Conservative limits to prevent truncation with very long transcripts (100+ turns avg)
    if total_count <= 10:
        # Small group: include all
        sample_transcripts = transcripts
        sampling_note = ""
    elif total_count <= 50:
        # Medium group: include first 15
        sample_transcripts = transcripts[:15]
        sampling_note = f"\n(Showing first 15 of {total_count} total transcripts)"
    elif total_count <= 200:
        # Large group: sample every Nth transcript to get ~15 samples
        step = total_count // 15
        sample_transcripts = transcripts[::step][:15]
        sampling_note = f"\n(Showing representative sample of 15 from {total_count} total transcripts)"
    else:
        # Very large group: stratified sample of 18
        # Take samples from beginning, middle, and end
        step = total_count // 18
        sample_transcripts = transcripts[::step][:18]
        sampling_note = f"\n(Showing stratified sample of 18 from {total_count} total transcripts)"

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

    # Add formatted transcripts with per-transcript length limit
    # Limit each transcript to 70 turns to ensure all sampled transcripts fit within token limits
    # Target: 15 transcripts × 70 turns × ~80 chars/turn ≈ 84k chars (stays under 100k without truncation)
    MAX_TURNS_PER_TRANSCRIPT = 70

    for idx, transcript in enumerate(sample_transcripts, 1):
        context_parts.append(f"\n--- TRANSCRIPT {idx} ---")

        if isinstance(transcript, list):
            # Already cleaned turns
            context_parts.append(format_conversation(transcript, max_turns=MAX_TURNS_PER_TRANSCRIPT))
        elif isinstance(transcript, dict) and 'data' in transcript:
            # Wrapped in data field
            context_parts.append(format_conversation(transcript['data'], max_turns=MAX_TURNS_PER_TRANSCRIPT))
        else:
            # Fallback
            context_parts.append(json.dumps(transcript, indent=2))

        context_parts.append("")  # Empty line between transcripts

    return "\n".join(context_parts), len(sample_transcripts)


def create_transcript_csv(project_id, filters, transcript_refs, force_recreate=False):
    """
    Create a CSV file from JSON transcripts for efficient AI processing.

    NEW OPTIMIZED FORMAT - One row per transcript:
    - Filename: Name of transcript (e.g., "Transcript330476")
    - Conversation: Complete conversation with all turns concatenated
                    Format: "Agent: text Customer: text Agent: text..."

    This format is MUCH more efficient:
    - 60-75% fewer tokens used
    - 3-4x more transcripts can fit in token budget
    - Better LLM comprehension (natural dialogue vs fragmented CSV)
    - Faster processing

    SMART SAMPLING - Only processes up to MAX_CHAT_TRANSCRIPTS to save time:
    - If <=200 transcripts: Process all
    - If >200 transcripts: Randomly sample 200 (no need to process thousands!)

    CSV CACHING STRATEGY:
    - force_recreate=True: Deletes old CSV and creates fresh one (used when opening chat)
    - force_recreate=False: Reuses existing CSV if available (used for subsequent questions)

    Args:
        project_id: Project ID
        filters: Dict with intent, topic, category, agent_task
        transcript_refs: List of (interaction_id, file_path) tuples
        force_recreate: If True, always create fresh CSV. If False, reuse existing CSV.

    Returns:
        dict: {
            'csv_path': str path to CSV file,
            'total_count': int total transcripts available,
            'sampled_count': int transcripts actually processed,
            'was_sampled': bool whether sampling was applied
        }
    """
    # Get project name from database
    with TranscriptDatabase(DB_PATH) as local_db:
        project = local_db.get_project(project_id)
        project_name = project['name'] if project else f"Project{project_id}"

    # Create data folder structure: /data/ProjectName_YYYY-MM-DD/
    today = datetime.now().strftime('%Y-%m-%d')
    data_folder = Path(f"data/{project_name}_{today}")
    data_folder.mkdir(parents=True, exist_ok=True)

    # Create unique filename based on filters hash
    filter_str = f"{filters.get('intent', '')}_{filters.get('topic', '')}_{filters.get('category', '')}_{filters.get('agent_task', '')}"
    filter_hash = hashlib.md5(filter_str.encode()).hexdigest()[:8]
    csv_path = data_folder / f"transcripts_{filter_hash}.csv"

    # Handle force_recreate: delete existing CSV to create fresh one
    if force_recreate and csv_path.exists():
        print(f"\n🔄 Force recreate enabled - Deleting old CSV: {csv_path}")
        csv_path.unlink()
        print(f"  Creating fresh CSV with new random sample...")

    # Check if CSV already exists (for consistent counts across chat session)
    if csv_path.exists() and not force_recreate:
        print(f"\n♻️  Reusing existing CSV: {csv_path}")
        # Load existing CSV to get accurate counts
        existing_df = pd.read_csv(csv_path)
        sampled_count = len(existing_df)
        total_count = len(transcript_refs)
        was_sampled = total_count > MAX_CHAT_TRANSCRIPTS

        print(f"  ✅ CSV loaded from cache!")
        print(f"  Transcripts in CSV: {sampled_count}")
        print(f"  Total available: {total_count}")
        print(f"  💡 Using cached CSV ensures consistent transcript counts across questions")

        return {
            'csv_path': str(csv_path),
            'total_count': total_count,
            'sampled_count': sampled_count,
            'was_sampled': was_sampled
        }

    # CSV doesn't exist or force_recreate is True - create it
    print(f"\n📝 Creating fresh CSV file (OPTIMIZED FORMAT): {csv_path}")

    # APPLY SMART SAMPLING BEFORE PROCESSING (performance optimization!)
    total_count = len(transcript_refs)
    was_sampled = False

    if total_count > MAX_CHAT_TRANSCRIPTS:
        # Randomly sample to MAX_CHAT_TRANSCRIPTS
        transcript_refs = random.sample(transcript_refs, MAX_CHAT_TRANSCRIPTS)
        was_sampled = True
        print(f"🎯 SMART SAMPLING APPLIED:")
        print(f"  Total available: {total_count} transcripts")
        print(f"  Randomly sampled: {MAX_CHAT_TRANSCRIPTS} transcripts")
        print(f"  Time saved: {total_count - MAX_CHAT_TRANSCRIPTS} transcripts skipped!")
    else:
        print(f"  Processing all {total_count} transcript files...")

    # Prepare CSV data - ONE ROW PER TRANSCRIPT
    csv_rows = []
    processed_count = 0
    failed_count = 0

    for interaction_id, file_path in transcript_refs:
        # Load JSON transcript
        transcript_data = load_transcript_file(file_path)
        if not transcript_data:
            failed_count += 1
            continue

        # Clean transcript to get conversation turns
        cleaned = clean_transcript(transcript_data)
        if not cleaned:
            failed_count += 1
            continue

        # Extract filename from interaction_id or file_path
        # Example: Transcript330476.CSV.json → Transcript330476
        filename = str(interaction_id)
        if 'Transcript' in str(file_path):
            # Extract from path
            import re
            match = re.search(r'Transcript\d+', str(file_path))
            if match:
                filename = match.group(0)

        # Concatenate all conversation turns into a single string
        conversation_parts = []
        for turn in cleaned:
            party = 'Agent' if turn.get('speaker') == 'Agent' else 'Customer'
            text = turn.get('text', '').strip()
            if text:  # Only include non-empty turns
                conversation_parts.append(f"{party}: {text}")

        # Join all turns with a space separator
        full_conversation = " ".join(conversation_parts)

        # Add single row for entire transcript
        csv_rows.append({
            'Filename': filename,
            'Conversation': full_conversation
        })

        processed_count += 1
        if processed_count % 10 == 0:
            print(f"  Processed {processed_count}/{len(transcript_refs)} transcripts...")

    # Write CSV file
    if csv_rows:
        df = pd.DataFrame(csv_rows)
        df.to_csv(csv_path, index=False, encoding='utf-8')

        print(f"  ✅ CSV created successfully!")
        print(f"  Total rows: {len(csv_rows)} (one per transcript)")
        print(f"  Processed: {processed_count} transcripts")
        print(f"  Failed: {failed_count} transcripts")
        if was_sampled:
            print(f"  🎯 Smart sampling saved processing {total_count - len(csv_rows)} transcripts!")
        print(f"  💡 New format is 60-75% more token-efficient!")
    else:
        print(f"  ❌ No data to write to CSV")
        return None

    return {
        'csv_path': str(csv_path),
        'total_count': total_count,
        'sampled_count': len(csv_rows),
        'was_sampled': was_sampled
    }


def prepare_chat_context_from_csv(csv_path, filters):
    """
    Prepare AI context from CSV file.

    NEW OPTIMIZED VERSION - Works with one-row-per-transcript format.
    Can fit 3-4x more transcripts in the same token budget!

    NOTE: Sampling is now done during CSV creation, not here.
    This function just formats the CSV data into context for the AI.

    Args:
        csv_path: Path to the transcript CSV file (already sampled)
        filters: Dict with intent, topic, category, agent_task

    Returns:
        tuple: (context_string, transcript_count, total_transcripts)
    """
    # Load CSV - new format has just Filename and Conversation columns
    df = pd.read_csv(csv_path)

    if df.empty:
        return "No transcript data available.", 0, 0

    # CSV is already sampled during creation, so just use all rows
    total_transcripts = len(df)
    sampled_df = df
    num_sampled = len(sampled_df)

    print(f"\n📊 CSV Data Loaded (OPTIMIZED FORMAT):")
    print(f"  Using all {total_transcripts} transcripts from pre-sampled CSV")

    sampling_note = ""

    # Build context - ULTRA-SIMPLIFIED format
    context_parts = [
        f"=== CUSTOMER SERVICE CALL TRANSCRIPTS ===\n",
        f"Intent Category: {filters.get('intent', 'N/A')}",
        f"Topic: {filters.get('topic', 'N/A')}",
        f"Category: {filters.get('category', 'N/A')}",
        f"Agent Task: {filters.get('agent_task', 'N/A')}",
        f"Number of Calls: {num_sampled}",
        sampling_note,
        "\nEach call shows the conversation between Customer and Agent.\n"
    ]

    # Add each transcript conversation - SIMPLE AND EFFICIENT!
    for idx, row in enumerate(sampled_df.itertuples(), 1):
        filename = row.Filename
        conversation = row.Conversation

        # Truncate very long conversations if needed (rare case)
        MAX_CHARS_PER_TRANSCRIPT = 4000  # ~1000 tokens
        if len(conversation) > MAX_CHARS_PER_TRANSCRIPT:
            conversation = conversation[:MAX_CHARS_PER_TRANSCRIPT] + "... [conversation truncated]"

        context_parts.append(f"\n--- Call {idx}: {filename} ---")
        context_parts.append(conversation)
        context_parts.append("")  # Empty line between calls

    context_str = "\n".join(context_parts)

    print(f"  Context size: {len(context_str):,} characters (~{len(context_str)//4:,} tokens)")
    print(f"  💡 Chat limit: maximum {MAX_CHAT_TRANSCRIPTS} transcripts to ensure token limits")

    return context_str, num_sampled, total_transcripts


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


@app.route('/api/projects/<int:project_id>/chat/prepare', methods=['POST'])
def prepare_chat(project_id):
    """
    Pre-generate CSV file when user opens chat (before asking questions).
    This provides a better UX - user sees loading once, then chat is instant.

    Request body:
    {
        "filters": {
            "intent": "Billing Question",
            "topic": "Payment Issue",
            "category": "Finance",
            "agent_task": "Process Refund"
        }
    }

    Returns:
    {
        "success": true,
        "csv_created": true,
        "transcript_count": 71,
        "message": "Chat context prepared successfully"
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

        # Get transcript file paths from database
        with TranscriptDatabase(DB_PATH) as local_db:
            transcript_refs = local_db.get_interaction_ids_by_filter(project_id, filters)

        print(f"\n{'='*60}")
        print(f"📝 PREPARING CHAT CONTEXT - Project {project_id}")
        print(f"{'='*60}")
        print(f"Filters received: {filters}")
        for key, value in filters.items():
            print(f"  - {key}: {value} (type: {type(value).__name__})")
        print(f"Total transcript files found in DB: {len(transcript_refs)}")
        if len(transcript_refs) > 0:
            print(f"  Sample IDs: {[ref[0] for ref in transcript_refs[:5]]}")

        if not transcript_refs:
            return jsonify({
                'success': False,
                'error': 'No transcripts found matching the specified filters'
            }), 404

        # Create CSV file (this is the time-consuming part)
        # force_recreate=True ensures fresh CSV with new random sample each time chat is opened
        csv_result = create_transcript_csv(project_id, filters, transcript_refs, force_recreate=True)

        if not csv_result or not os.path.exists(csv_result['csv_path']):
            return jsonify({
                'success': False,
                'error': 'Failed to create transcript CSV file'
            }), 500

        print(f"✅ Chat context prepared successfully!")
        print(f"{'='*60}\n")

        return jsonify({
            'success': True,
            'csv_created': True,
            'transcript_count': csv_result['sampled_count'],
            'total_count': csv_result['total_count'],
            'was_sampled': csv_result['was_sampled'],
            'message': 'Chat context prepared successfully'
        })

    except Exception as e:
        print(f"Prepare chat error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/filter-values', methods=['GET'])
def get_filter_values(project_id):
    """
    Get unique values for all filter fields in a project.
    Used to populate multi-select dropdowns in the filter panel.

    Returns:
    {
        "success": true,
        "filter_values": {
            "categories": ["BILLING", "TECHNICAL", ...],
            "topics": ["Payment", "Account", ...],
            "intents": ["Making Payment", "Billing Question", ...],
            "agent_tasks": ["Copay Was Discussed", "Process Refund", ...]
        }
    }
    """
    try:
        with TranscriptDatabase(DB_PATH) as local_db:
            table_name = f"conversations_{project_id}"
            cursor = local_db.conn.cursor()

            # Get unique values for each filter field
            query = f"""
                SELECT DISTINCT
                    COALESCE(category, 'Not Specified') as category,
                    COALESCE(topic, 'Not Specified') as topic,
                    COALESCE(intent, 'Unknown') as intent,
                    COALESCE(agent_task, 'Not Specified') as agent_task
                FROM {table_name}
                ORDER BY category, topic, intent, agent_task
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            # Collect unique values for each field
            categories = set()
            topics = set()
            intents = set()
            agent_tasks = set()

            for row in rows:
                categories.add(row[0])
                topics.add(row[1])
                intents.add(row[2])
                agent_tasks.add(row[3])

            return jsonify({
                'success': True,
                'filter_values': {
                    'categories': sorted(list(categories)),
                    'topics': sorted(list(topics)),
                    'intents': sorted(list(intents)),
                    'agent_tasks': sorted(list(agent_tasks))
                }
            })

    except Exception as e:
        print(f"Get filter values error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/projects/<int:project_id>/sentiment-range', methods=['GET'])
def get_sentiment_range(project_id):
    """
    Get min and max sentiment scores for a project.
    Used to initialize the sentiment slider range.

    Returns:
    {
        "success": true,
        "min_sentiment": 1.25,
        "max_sentiment": 4.85
    }
    """
    try:
        with TranscriptDatabase(DB_PATH) as local_db:
            table_name = f"conversations_{project_id}"
            cursor = local_db.conn.cursor()

            # Get min and max sentiment scores
            query = f"""
                SELECT
                    MIN(sentiment_score) as min_sentiment,
                    MAX(sentiment_score) as max_sentiment
                FROM {table_name}
                WHERE sentiment_score IS NOT NULL
            """

            cursor.execute(query)
            row = cursor.fetchone()

            if row and row[0] is not None and row[1] is not None:
                return jsonify({
                    'success': True,
                    'min_sentiment': round(float(row[0]), 2),
                    'max_sentiment': round(float(row[1]), 2)
                })
            else:
                # No sentiment data, return default range
                return jsonify({
                    'success': True,
                    'min_sentiment': 1.0,
                    'max_sentiment': 5.0
                })

    except Exception as e:
        print(f"Get sentiment range error: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return default range on error
        return jsonify({
            'success': True,
            'min_sentiment': 1.0,
            'max_sentiment': 5.0
        })


@app.route('/api/projects/<int:project_id>/duration-range', methods=['GET'])
def get_duration_range(project_id):
    """
    Get min and max duration (in seconds) for a project.
    Used to initialize the duration slider range.

    Returns:
    {
        "success": true,
        "min_duration": 45,
        "max_duration": 1800
    }
    """
    try:
        with TranscriptDatabase(DB_PATH) as local_db:
            table_name = f"conversations_{project_id}"
            cursor = local_db.conn.cursor()

            # Get min and max duration in seconds
            query = f"""
                SELECT
                    MIN(duration_seconds) as min_duration,
                    MAX(duration_seconds) as max_duration
                FROM {table_name}
                WHERE duration_seconds IS NOT NULL
            """

            cursor.execute(query)
            row = cursor.fetchone()

            if row and row[0] is not None and row[1] is not None:
                return jsonify({
                    'success': True,
                    'min_duration': int(row[0]),
                    'max_duration': int(row[1])
                })
            else:
                # No duration data, return default range
                return jsonify({
                    'success': True,
                    'min_duration': 0,
                    'max_duration': 1000
                })

    except Exception as e:
        print(f"Get duration range error: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return default range on error
        return jsonify({
            'success': True,
            'min_duration': 0,
            'max_duration': 1000
        })


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

        print(f"\n{'='*60}")
        print(f"🔍 CHAT QUERY DEBUG - Project {project_id} (CSV-based approach)")
        print(f"{'='*60}")
        print(f"Question: {question[:100]}...")
        print(f"Filters: {filters}")
        print(f"Total transcript files found in DB: {len(transcript_refs)}")

        if not transcript_refs:
            return jsonify({
                'success': False,
                'error': 'No transcripts found matching the specified filters'
            }), 404

        # Step 1: Create or load CSV file
        # force_recreate=False (default) reuses existing CSV for consistent counts during chat session
        csv_result = create_transcript_csv(project_id, filters, transcript_refs, force_recreate=False)

        if not csv_result or not os.path.exists(csv_result['csv_path']):
            return jsonify({
                'success': False,
                'error': 'Failed to create transcript CSV file'
            }), 500

        # Step 2: Prepare context from CSV
        context, sampled_count, total_count = prepare_chat_context_from_csv(csv_result['csv_path'], filters)

        print(f"\n📝 Context Preparation Complete:")
        print(f"  Transcripts sampled for AI: {sampled_count} (from {total_count} total)")

        # Create system prompt with context - matches working implementation exactly
        system_prompt = f"""You are an expert analyst reviewing customer service call transcripts.

{context}

Your role:
- Answer questions about these specific transcripts
- Provide specific examples and quotes when relevant
- Identify patterns and insights
- Be concise but thorough
- If asked to summarize, provide actionable insights

The user is asking about the transcripts above. Answer their questions accurately based on the data provided."""

        # User message contains ONLY the question (not buried in context!)
        user_message = question

        print(f"  Context size: {len(system_prompt):,} characters")
        print(f"  Question: {question[:100]}...")

        # Call AWS Bedrock using Converse API (proper way with separate system/user messages)
        try:
            bedrock = BedrockClient(region_name="us-east-1")
            # UPGRADED: Using Claude 3.5 Sonnet v2
            model_id = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

            # Build messages array (just the user question)
            messages = [
                {
                    'role': 'user',
                    'content': [{'text': user_message}]
                }
            ]

            print(f"\n🚀 Sending to Bedrock Converse API (model: {model_id})...")
            print(f"  Max output tokens: 4096")

            # Use Converse API with separate system prompt and user message
            answer, input_tokens, output_tokens = bedrock.converse(
                messages=messages,
                system_prompt=system_prompt,
                model_id=model_id,
                max_tokens=4096,
                temperature=0.7,
                top_p=0.9
            )

            print(f"\n✅ Bedrock Response Received:")
            print(f"  Input tokens: {input_tokens:,}")
            print(f"  Output tokens: {output_tokens:,}")
            print(f"  Answer length: {len(answer)} characters")
            print(f"  Answer preview: {answer[:150]}...")
            print(f"{'='*60}\n")

            return jsonify({
                'success': True,
                'answer': answer,
                'transcript_count': total_count,
                'sampled_count': sampled_count,
                'tokens_used': {
                    'input': input_tokens,
                    'output': output_tokens
                }
            })

        except Exception as bedrock_error:
            error_msg = str(bedrock_error)
            print(f"\n❌ BEDROCK ERROR:")
            print(f"  Error type: {type(bedrock_error).__name__}")
            print(f"  Error message: {error_msg}")

            # Check for common errors
            if "ServiceUnavailableException" in error_msg:
                print(f"  ⚠️ Bedrock service unavailable - likely rate limiting or service issues")
                print(f"  💡 Try again in a few seconds")
            elif "ThrottlingException" in error_msg:
                print(f"  ⚠️ Rate limit exceeded")
                print(f"  💡 Wait 60 seconds before retry")
            elif "ValidationException" in error_msg or "token" in error_msg.lower():
                print(f"  ⚠️ Possible token limit exceeded")
                if 'system_prompt' in locals():
                    print(f"  💡 Context was {len(system_prompt):,} chars (~{len(system_prompt)//4:,} tokens)")

            import traceback
            traceback.print_exc()
            print(f"{'='*60}\n")

            return jsonify({
                'success': False,
                'error': f'AI service error: {str(bedrock_error)}',
                'transcript_count': total_count if 'total_count' in locals() else 0
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
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    print("="*70)
    print("🚀 TRANSCRIPT ANALYSIS - FULL STACK APPLICATION")
    print("="*70)
    print(f"Database: {DB_PATH}")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print(f"Max transcripts for AI chat: {MAX_CHAT_TRANSCRIPTS}")
    print("="*70)
    print("\n📍 ACCESS THE APPLICATION:")
    print(f"  Local:          http://localhost:5000")
    print(f"  Network:        http://{local_ip}:5000")
    print(f"  External:       http://<your-public-ip>:5000")
    print("\n💡 Share the Network URL with other users on your local network!")
    print("="*70)
    print("\n📡 Available API endpoints:")
    print("  GET  /api/health")
    print("  GET  /api/projects")
    print("  POST /api/projects")
    print("  GET  /api/projects/<id>")
    print("  GET  /api/projects/<id>/summary")
    print("  POST /api/projects/<id>/chat/prepare")
    print("  POST /api/projects/<id>/chat/query")
    print("="*70)
    print("\n⚠️  IMPORTANT: Make sure port 5000 is open in your firewall!")
    print("="*70)

    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
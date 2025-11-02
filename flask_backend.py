"""
Flask Backend API for Transcript Analysis Project
Integrates with the existing HTML/JS frontend
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
from pathlib import Path
from datetime import datetime
from database import TranscriptDatabase
from csv_processor import CSVProcessor
from main_integration import create_project_from_csv

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
    print("  GET  /api/projects/<id>/stats")
    print("="*60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
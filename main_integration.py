import os
from database import TranscriptDatabase
from csv_processor import CSVProcessor

# Use local path for database (not NFS)
DEFAULT_DB_PATH = "/tmp/transcript_projects.db"


def create_project_from_csv(project_name, description, csv_path, db_path=None, verify_transcripts=True, transcript_base_path=None):
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    
    result = {'success': False, 'project_id': None, 'errors': [], 'warnings': [], 'stats': {}}
    
    try:
        print("Processing CSV:", csv_path)
        processor = CSVProcessor()
        conversations, stats = processor.process_csv(csv_path, verify_transcripts=verify_transcripts, base_path=transcript_base_path)
        
        summary = processor.get_summary()
        result['errors'] = summary['errors']
        result['warnings'] = summary['warnings']
        result['stats'] = stats
        
        if not summary['success']:
            print("CSV processing failed:")
            for error in summary['errors']:
                print("  -", error)
            return result
        
        if not conversations:
            result['errors'].append("No valid conversations found in CSV")
            print("No valid conversations to import")
            return result
        
        print("CSV validated successfully")
        print("  - Total rows:", stats['total_rows'])
        print("  - Valid rows:", stats['valid_rows'])
        print("  - Invalid rows:", stats['invalid_rows'])
        
        if stats['missing_transcripts'] > 0:
            print("Warning:", stats['missing_transcripts'], "transcript files not found")
        
        print("\nCreating project in database:", db_path)
        
        with TranscriptDatabase(db_path) as db:
            csv_filename = os.path.basename(csv_path)
            project_id = db.create_project(name=project_name, description=description, csv_filename=csv_filename)
            
            print("Project created with ID:", project_id)
            
            print("\nInserting", len(conversations), "conversations...")
            inserted_count = db.insert_conversations(project_id, conversations)
            
            print("Inserted", inserted_count, "conversations")
            
            project = db.get_project(project_id)
            print("\nProject Summary:")
            print("  - Name:", project['name'])
            print("  - Total Records:", project['total_records'])
            print("  - Created:", project['created_at'])
            
            sample_conversations = db.get_conversations(project_id, limit=3)
            print("\nSample conversations:")
            for i, conv in enumerate(sample_conversations, 1):
                print("  ", i, ". Intent:", conv['intent'], ", Sentiment:", conv['sentiment_score'], ", Duration:", conv['duration_seconds'], "s")
            
            report_columns = db.get_report_columns(project_id)
            print("\nAvailable columns for reports:")
            print("  ", ', '.join(report_columns))
        
        result['success'] = True
        result['project_id'] = project_id
        
        return result
    
    except Exception as e:
        result['errors'].append("Unexpected error: " + str(e))
        print("Error:", str(e))
        import traceback
        traceback.print_exc()
        return result


def query_project_example(project_id, db_path=None):
    if db_path is None:
        db_path = DEFAULT_DB_PATH
        
    print("\n" + "="*60)
    print("QUERYING PROJECT", project_id)
    print("="*60)
    
    with TranscriptDatabase(db_path) as db:
        print("\nConversations by Intent:")
        intent_data = db.get_aggregated_data(project_id, 'intent')
        for row in intent_data:
            print("  ", row['intent'], ":", row['count'], "calls, Avg Sentiment:", round(row['avg_sentiment'], 2))
        
        print("\nHigh sentiment conversations (score > 4.0):")
        all_convs = db.get_conversations(project_id, limit=100)
        high_sentiment = [c for c in all_convs if c['sentiment_score'] and c['sentiment_score'] > 4.0]
        print("   Found", len(high_sentiment), "conversations with sentiment > 4.0")
        
        print("\nGetting conversations for chat (Intent='Billing Question'):")
        transcript_files = db.get_interaction_ids_by_filter(project_id, {'intent': 'Billing Question'})
        print("   Found", len(transcript_files), "transcripts")
        if transcript_files:
            print("   First transcript:", transcript_files[0][1])


def list_all_projects(db_path=None):
    if db_path is None:
        db_path = DEFAULT_DB_PATH
        
    print("\n" + "="*60)
    print("ALL PROJECTS")
    print("="*60)
    
    with TranscriptDatabase(db_path) as db:
        projects = db.get_all_projects()
        
        if not projects:
            print("No projects found")
        else:
            for project in projects:
                print("\nProject ID:", project['id'])
                print("   Name:", project['name'])
                print("   Description:", project['description'])
                print("   Records:", project['total_records'])
                print("   Created:", project['created_at'])


if __name__ == "__main__":
    print("="*60)
    print("TRANSCRIPT PROJECT - CSV TO DATABASE INTEGRATION")
    print("="*60)
    print("Database location:", DEFAULT_DB_PATH)
    print("(Using /tmp because /mnt/Media is NFS with locking issues)")
    print("="*60)
    
    sample_csv_content = """InteractionId,JsonSummaryFilePath,DurationSeconds,SentimentScore,IsAutomatable,Intent,Topic,AgentTask
call_12345,/mnt/Media/transcripts/1/call_12345.json,320,4.5,Yes,Billing Question,Payment Issue,Process Refund
call_12346,/mnt/Media/transcripts/1/call_12346.json,180,3.2,No,Technical Support,Login Problem,Reset Password
call_12347,/mnt/Media/transcripts/2/call_12347.json,540,4.8,Yes,Account Question,Profile Update,Update Address
call_12348,/mnt/Media/transcripts/2/call_12348.json,420,2.9,No,Billing Question,Disputed Charge,Investigate Charge
call_12349,/mnt/Media/transcripts/3/call_12349.json,290,4.1,Yes,Technical Support,Software Bug,Escalate to L2"""
    
    sample_csv_path = "sample_transcripts.csv"
    with open(sample_csv_path, 'w') as f:
        f.write(sample_csv_content)
    
    print("\nCreated sample CSV:", sample_csv_path, "\n")
    
    result = create_project_from_csv(
        project_name="Sample Call Center Analysis",
        description="Demo project showing CSV import and database storage",
        csv_path=sample_csv_path,
        verify_transcripts=False
    )
    
    if result['success']:
        print("\nPROJECT CREATED SUCCESSFULLY!")
        print("   Project ID:", result['project_id'])
        
        query_project_example(result['project_id'])
        
        list_all_projects()
        
    else:
        print("\nPROJECT CREATION FAILED")
        for error in result['errors']:
            print("   -", error)
    
    if os.path.exists(sample_csv_path):
        os.remove(sample_csv_path)
    
    print("\n" + "="*60)
    print("DEMO COMPLETED")
    print("="*60)
    print("\nDatabase file created at:", DEFAULT_DB_PATH)
    print("You can now use this structure in your Flask backend!")
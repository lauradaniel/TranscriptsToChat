"""
Database schema and operations for Transcript Analysis Project
SQLite-based solution for storing project metadata and conversation data
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class TranscriptDatabase:
    """Handles all database operations for transcript projects"""
    
    def __init__(self, db_path: str = "transcript_projects.db"):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self.initialize_database()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures connection is closed"""
        self.close()
        return False
    
    def initialize_database(self):
        """Create database and initialize schema if not exists"""
        # Close existing connection if any
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
        
        # Connect with timeout to handle locks
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name
        self.create_projects_table()
    
    def create_projects_table(self):
        """Create the main projects table"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                csv_filename TEXT NOT NULL,
                csv_upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_records INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()
    
    def create_project(self, name: str, description: str, csv_filename: str) -> int:
        """
        Create a new project
        
        Args:
            name: Project name
            description: Project description
            csv_filename: Name of uploaded CSV file
            
        Returns:
            project_id: ID of created project
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO projects (name, description, csv_filename)
            VALUES (?, ?, ?)
        """, (name, description, csv_filename))
        self.conn.commit()
        
        project_id = cursor.lastrowid
        
        # Create conversations table for this project
        self.create_conversations_table(project_id)
        
        return project_id
    
    def create_conversations_table(self, project_id: int):
        """
        Create a conversations table for a specific project
        
        Args:
            project_id: ID of the project
        """
        table_name = f"conversations_{project_id}"
        cursor = self.conn.cursor()
        
        # Main table with all CSV columns
        # Note: interaction_id can have duplicates (one call can have multiple tasks)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interaction_id TEXT NOT NULL,
                json_summary_filepath TEXT NOT NULL,
                duration_seconds INTEGER,
                sentiment_score REAL,
                is_automatable TEXT,
                intent TEXT,
                topic TEXT,
                category TEXT,
                agent_task TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for fast filtering and searching
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_intent 
            ON {table_name}(intent)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_sentiment 
            ON {table_name}(sentiment_score)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_topic 
            ON {table_name}(topic)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_category 
            ON {table_name}(category)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_is_automatable 
            ON {table_name}(is_automatable)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_duration 
            ON {table_name}(duration_seconds)
        """)
        
        self.conn.commit()
    
    def insert_conversations(self, project_id: int, conversations: List[Dict]) -> int:
        """
        Bulk insert conversations (tasks) into project table
        Note: interaction_id can repeat - each row is a task, not a call
        
        Args:
            project_id: ID of the project
            conversations: List of conversation/task dictionaries
            
        Returns:
            Number of records inserted
        """
        table_name = f"conversations_{project_id}"
        cursor = self.conn.cursor()
        
        insert_query = f"""
            INSERT INTO {table_name} 
            (interaction_id, json_summary_filepath, duration_seconds, 
             sentiment_score, is_automatable, intent, topic, category, agent_task)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        records = [
            (
                conv['InteractionId'],
                conv['JsonSummaryFilePath'],
                conv.get('DurationSeconds'),
                conv.get('SentimentScore'),
                conv.get('IsAutomatable'),
                conv.get('Intent'),
                conv.get('Topic'),
                conv.get('Category'),
                conv.get('AgentTask')
            )
            for conv in conversations
        ]
        
        cursor.executemany(insert_query, records)
        self.conn.commit()
        
        # Update total_records in projects table
        cursor.execute("""
            UPDATE projects 
            SET total_records = ? 
            WHERE id = ?
        """, (len(records), project_id))
        self.conn.commit()
        
        return len(records)
    
    def get_project(self, project_id: int) -> Optional[Dict]:
        """
        Get project by ID
        
        Args:
            project_id: ID of the project
            
        Returns:
            Project dictionary or None
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_all_projects(self) -> List[Dict]:
        """Get all projects"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_conversations(
        self, 
        project_id: int, 
        filters: Optional[Dict] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get conversations for a project with optional filters
        
        Args:
            project_id: ID of the project
            filters: Dictionary of column:value filters
            limit: Maximum number of records to return
            
        Returns:
            List of conversation dictionaries
        """
        table_name = f"conversations_{project_id}"
        cursor = self.conn.cursor()
        
        query = f"SELECT * FROM {table_name}"
        params = []
        
        if filters:
            conditions = []
            for column, value in filters.items():
                if value is not None:
                    conditions.append(f"{column} = ?")
                    params.append(value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY id DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_report_columns(self, project_id: int) -> List[str]:
        """
        Get available columns for report building
        Excludes technical columns (InteractionId, JsonSummaryFilePath)
        
        Args:
            project_id: ID of the project
            
        Returns:
            List of column names available for reports
        """
        # These are the columns users can see in reports
        report_columns = [
            'Intent',
            'Topic',
            'Category',
            'AgentTask',
            'SentimentScore',
            'DurationSeconds',
            'IsAutomatable'
        ]
        return report_columns
    
    def get_aggregated_data(
        self, 
        project_id: int, 
        group_by: str,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Get aggregated data grouped by a specific column
        
        Args:
            project_id: ID of the project
            group_by: Column to group by (e.g., 'intent', 'topic')
            filters: Optional filters to apply
            
        Returns:
            List of aggregated results
        """
        table_name = f"conversations_{project_id}"
        cursor = self.conn.cursor()
        
        query = f"""
            SELECT 
                {group_by},
                COUNT(*) as count,
                AVG(sentiment_score) as avg_sentiment,
                AVG(duration_seconds) as avg_duration,
                MIN(sentiment_score) as min_sentiment,
                MAX(sentiment_score) as max_sentiment
            FROM {table_name}
        """
        
        params = []
        if filters:
            conditions = []
            for column, value in filters.items():
                if value is not None:
                    conditions.append(f"{column} = ?")
                    params.append(value)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        query += f" GROUP BY {group_by} ORDER BY count DESC"
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_interaction_ids_by_filter(
        self,
        project_id: int,
        filters: Dict
    ) -> List[Tuple[str, str]]:
        """
        Get InteractionIds and JsonSummaryFilePaths for conversations matching filters
        Used for chat context loading

        Args:
            project_id: ID of the project
            filters: Dictionary of filters

        Returns:
            List of tuples (interaction_id, json_summary_filepath) - one per unique interaction_id
        """
        table_name = f"conversations_{project_id}"
        cursor = self.conn.cursor()

        # Use GROUP BY to get one row per interaction_id (matching COUNT(DISTINCT interaction_id))
        # Take MIN(json_summary_filepath) to pick one filepath when there are duplicates
        query = f"""
            SELECT interaction_id, MIN(json_summary_filepath) as json_summary_filepath
            FROM {table_name}
        """

        params = []
        if filters:
            conditions = []
            for column, value in filters.items():
                if value is not None and value != '':
                    # Handle sentiment range filters
                    if column == 'sentiment_min':
                        conditions.append("sentiment_score >= ?")
                        params.append(float(value))
                    elif column == 'sentiment_max':
                        conditions.append("sentiment_score <= ?")
                        params.append(float(value))
                    # Handle multi-select filters (plural forms with comma-separated values)
                    # e.g., 'categories': 'value1,value2,value3' or 'intents': 'val1,val2'
                    elif column in ['categories', 'topics', 'intents', 'agent_tasks']:
                        # Multi-select filter - split by comma and create OR conditions
                        values = [v.strip() for v in value.split(',') if v.strip()]
                        if values:
                            # Map plural to singular column name
                            column_map = {
                                'categories': 'category',
                                'topics': 'topic',
                                'intents': 'intent',
                                'agent_tasks': 'agent_task'
                            }
                            actual_column = column_map.get(column, column)

                            or_conditions = []
                            for val in values:
                                if val == 'Not Specified' or val == 'Unknown':
                                    or_conditions.append(f"{actual_column} IS NULL")
                                else:
                                    or_conditions.append(f"{actual_column} = ?")
                                    params.append(val)
                            if or_conditions:
                                conditions.append(f"({' OR '.join(or_conditions)})")
                    else:
                        # Single value filter
                        if value == 'Not Specified' or value == 'Unknown':
                            conditions.append(f"{column} IS NULL")
                        else:
                            conditions.append(f"{column} = ?")
                            params.append(value)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        # Group by interaction_id to get exactly one row per unique interaction_id
        query += " GROUP BY interaction_id"

        # Debug logging
        print(f"\n🔍 Database Query Debug:")
        print(f"  Filters: {filters}")
        print(f"  Generated SQL: {query}")
        print(f"  Parameters: {params}")

        cursor.execute(query, params)
        results = cursor.fetchall()
        print(f"  Results count: {len(results)}")
        return results
    
    def close(self):
        """Close database connection"""
        if self.conn:
            try:
                self.conn.commit()  # Commit any pending transactions
                self.conn.close()
                self.conn = None
            except Exception as e:
                print(f"Warning: Error closing database connection: {e}")
                self.conn = None


if __name__ == "__main__":
    # Test the database schema
    with TranscriptDatabase("test_transcript_projects.db") as db:
        # Create a test project
        project_id = db.create_project(
            name="Test Project",
            description="Testing database schema",
            csv_filename="test_data.csv"
        )
        
        print(f"Created project with ID: {project_id}")
        
        # Test insert
        test_conversations = [
            {
                'InteractionId': 'call_001',
                'JsonSummaryFilePath': '/path/to/transcript_001.json',
                'DurationSeconds': 300,
                'SentimentScore': 4.5,
                'IsAutomatable': 'Yes',
                'Intent': 'Billing Question',
                'Topic': 'Payment',
                'AgentTask': 'Process Payment'
            }
        ]
        
        inserted = db.insert_conversations(project_id, test_conversations)
        print(f"Inserted {inserted} conversations")
        
        # Test retrieval
        project = db.get_project(project_id)
        print(f"Project: {project}")
    
    # Connection automatically closed by context manager
    print("\nDatabase schema created successfully!")
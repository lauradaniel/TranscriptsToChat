"""
CSV Processing Module for Transcript Analysis Project
Validates, parses, and imports CSV files into SQLite database
"""

import csv
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import json


class CSVProcessor:
    """Handles CSV file validation and processing"""
    
    REQUIRED_COLUMNS = [
        'InteractionId',
        'JsonSummaryFilePath',
        'DurationSeconds',
        'SentimentScore',
        'IsAutomatable',
        'Intent',
        'Topic',
        'AgentTask'
    ]
    
    # Optional columns
    OPTIONAL_COLUMNS = [
        'Category'
    ]
    
    # Note: User had typo "ntent" but we'll handle both cases
    COLUMN_ALIASES = {
        'ntent': 'Intent'  # Handle typo in CSV
    }
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.stats = {
            'total_rows': 0,
            'valid_rows': 0,
            'invalid_rows': 0,
            'missing_transcripts': 0
        }
        self.detected_delimiter = None
        self.found_columns = []
    
    def validate_csv_structure(self, csv_path: str) -> Tuple[bool, List[str]]:
        """
        Validate CSV file structure and required columns
        Auto-detects delimiter (comma or tab)
        
        Args:
            csv_path: Path to CSV file
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if not os.path.exists(csv_path):
            errors.append(f"CSV file not found: {csv_path}")
            return False, errors
        
        if not csv_path.lower().endswith('.csv'):
            errors.append("File must have .csv extension")
            return False, errors
        
        try:
            # Use utf-8-sig encoding to automatically handle UTF-8 BOM
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                # Read first line to detect delimiter
                first_line = f.readline()
                f.seek(0)

                # Explicit delimiter detection
                if '\t' in first_line and ',' not in first_line:
                    # Tab-separated
                    delimiter = '\t'
                    self.detected_delimiter = 'TAB'
                elif ',' in first_line:
                    # Comma-separated (most common)
                    delimiter = ','
                    self.detected_delimiter = 'COMMA'
                else:
                    # Fallback: try csv.Sniffer
                    f.seek(0)
                    sample = f.read(1024)
                    f.seek(0)
                    sniffer = csv.Sniffer()
                    try:
                        delimiter = sniffer.sniff(sample).delimiter
                        self.detected_delimiter = 'TAB' if delimiter == '\t' else 'COMMA'
                    except:
                        # Default to comma
                        delimiter = ','
                        self.detected_delimiter = 'COMMA'

                # Read headers with detected delimiter
                reader = csv.DictReader(f, delimiter=delimiter)
                headers = reader.fieldnames

                if not headers:
                    errors.append("CSV file is empty or has no headers")
                    return False, errors
                
                # Normalize headers (strip whitespace)
                headers = [h.strip() for h in headers]
                self.found_columns = headers
                
                print(f"DEBUG: Detected delimiter: {self.detected_delimiter}")
                print(f"DEBUG: Found columns: {headers}")
                
                # Check for required columns
                missing_columns = []
                for required_col in self.REQUIRED_COLUMNS:
                    # Check if column exists or has an alias
                    found = False
                    for header in headers:
                        if header == required_col or self.COLUMN_ALIASES.get(header) == required_col:
                            found = True
                            break
                    
                    if not found:
                        missing_columns.append(required_col)
                
                if missing_columns:
                    errors.append(f"Missing required columns: {', '.join(missing_columns)}")
                    errors.append(f"Found columns: {', '.join(headers)}")
                    errors.append(f"Expected columns: {', '.join(self.REQUIRED_COLUMNS)}")
                    return False, errors
                
        except Exception as e:
            errors.append(f"Error reading CSV file: {str(e)}")
            return False, errors
        
        return True, []
    
    def normalize_column_name(self, column: str) -> str:
        """
        Normalize column names to handle variations
        
        Args:
            column: Original column name
            
        Returns:
            Normalized column name
        """
        column = column.strip()
        return self.COLUMN_ALIASES.get(column, column)
    
    def validate_row_data(self, row: Dict, row_num: int) -> Tuple[bool, Optional[str]]:
        """
        Validate individual row data
        
        Args:
            row: Row dictionary
            row_num: Row number for error reporting
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check InteractionId
        if not row.get('InteractionId') or not row['InteractionId'].strip():
            return False, f"Row {row_num}: Missing InteractionId"
        
        # Check JsonSummaryFilePath
        if not row.get('JsonSummaryFilePath') or not row['JsonSummaryFilePath'].strip():
            return False, f"Row {row_num}: Missing JsonSummaryFilePath"
        
        # Validate numeric fields if present
        if row.get('DurationSeconds'):
            try:
                duration = float(row['DurationSeconds'])
                if duration < 0:
                    return False, f"Row {row_num}: DurationSeconds cannot be negative"
            except ValueError:
                return False, f"Row {row_num}: DurationSeconds must be a number"
        
        if row.get('SentimentScore'):
            try:
                sentiment = float(row['SentimentScore'])
                # Sentiment scores typically range from 1-5 or 0-1
                if sentiment < 0:
                    self.warnings.append(f"Row {row_num}: Unusual SentimentScore value: {sentiment}")
            except ValueError:
                return False, f"Row {row_num}: SentimentScore must be a number"
        
        return True, None
    
    def check_transcript_files_exist(
        self, 
        conversations: List[Dict],
        base_path: Optional[str] = None
    ) -> Tuple[List[Dict], List[str]]:
        """
        Check if transcript JSON files exist at specified paths
        
        Args:
            conversations: List of conversation dictionaries
            base_path: Optional base path to prepend to relative paths
            
        Returns:
            Tuple of (conversations_with_existing_files, missing_file_paths)
        """
        valid_conversations = []
        missing_files = []
        
        for conv in conversations:
            filepath = conv['JsonSummaryFilePath']
            
            # Handle both absolute and relative paths
            if base_path and not os.path.isabs(filepath):
                full_path = os.path.join(base_path, filepath)
            else:
                full_path = filepath
            
            if os.path.exists(full_path):
                # Update with full path for consistency
                conv['JsonSummaryFilePath'] = full_path
                valid_conversations.append(conv)
            else:
                missing_files.append(filepath)
                self.stats['missing_transcripts'] += 1
        
        return valid_conversations, missing_files
    
    def process_csv(
        self, 
        csv_path: str, 
        verify_transcripts: bool = True,
        base_path: Optional[str] = None
    ) -> Tuple[List[Dict], Dict]:
        """
        Process CSV file and return cleaned data
        
        Args:
            csv_path: Path to CSV file
            verify_transcripts: Whether to verify transcript files exist
            base_path: Base path for transcript files (if relative paths in CSV)
            
        Returns:
            Tuple of (list_of_conversations, statistics_dict)
        """
        self.errors = []
        self.warnings = []
        self.stats = {
            'total_rows': 0,
            'valid_rows': 0,
            'invalid_rows': 0,
            'missing_transcripts': 0
        }
        
        # Validate CSV structure
        is_valid, errors = self.validate_csv_structure(csv_path)
        if not is_valid:
            self.errors.extend(errors)
            return [], self.stats
        
        conversations = []
        
        try:
            # Use utf-8-sig encoding to automatically handle UTF-8 BOM
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                # Read first line to detect delimiter
                first_line = f.readline()
                f.seek(0)

                # Explicit delimiter detection
                if '\t' in first_line and ',' not in first_line:
                    # Tab-separated
                    delimiter = '\t'
                    print(f"   Detected delimiter: TAB")
                elif ',' in first_line:
                    # Comma-separated (most common)
                    delimiter = ','
                    print(f"   Detected delimiter: COMMA")
                else:
                    # Fallback: try csv.Sniffer
                    f.seek(0)
                    sample = f.read(1024)
                    f.seek(0)
                    sniffer = csv.Sniffer()
                    try:
                        delimiter = sniffer.sniff(sample).delimiter
                        print(f"   Detected delimiter: {'TAB' if delimiter == chr(9) else 'COMMA'} (via Sniffer)")
                    except:
                        # Default to comma
                        delimiter = ','
                        print(f"   Using default delimiter: COMMA")

                reader = csv.DictReader(f, delimiter=delimiter)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                    self.stats['total_rows'] += 1
                    
                    # Normalize column names
                    normalized_row = {}
                    for key, value in row.items():
                        normalized_key = self.normalize_column_name(key)
                        normalized_row[normalized_key] = value.strip() if value else None
                    
                    # Validate row
                    is_valid, error = self.validate_row_data(normalized_row, row_num)
                    
                    if not is_valid:
                        self.errors.append(error)
                        self.stats['invalid_rows'] += 1
                        continue
                    
                    # Convert numeric fields
                    conversation = {
                        'InteractionId': normalized_row['InteractionId'],
                        'JsonSummaryFilePath': normalized_row['JsonSummaryFilePath'],
                        'DurationSeconds': int(float(normalized_row['DurationSeconds'])) if normalized_row.get('DurationSeconds') else None,
                        'SentimentScore': float(normalized_row['SentimentScore']) if normalized_row.get('SentimentScore') else None,
                        'IsAutomatable': normalized_row.get('IsAutomatable'),
                        'Intent': normalized_row.get('Intent'),
                        'Topic': normalized_row.get('Topic'),
                        'AgentTask': normalized_row.get('AgentTask'),
                        'Category': normalized_row.get('Category')  # Optional field
                    }
                    
                    conversations.append(conversation)
                    self.stats['valid_rows'] += 1
        
        except Exception as e:
            self.errors.append(f"Error processing CSV: {str(e)}")
            return [], self.stats
        
        # Verify transcript files exist
        if verify_transcripts:
            conversations, missing_files = self.check_transcript_files_exist(
                conversations, 
                base_path
            )
            
            if missing_files:
                if len(missing_files) <= 10:
                    self.warnings.append(f"Missing transcript files: {', '.join(missing_files)}")
                else:
                    self.warnings.append(f"Missing {len(missing_files)} transcript files")
        
        return conversations, self.stats
    
    def get_summary(self) -> Dict:
        """
        Get processing summary
        
        Returns:
            Dictionary with errors, warnings, and statistics
        """
        return {
            'errors': self.errors,
            'warnings': self.warnings,
            'stats': self.stats,
            'success': len(self.errors) == 0
        }


def validate_transcript_json(json_path: str) -> Tuple[bool, Optional[Dict]]:
    """
    Validate and extract basic info from transcript JSON file
    
    Args:
        json_path: Path to transcript JSON file
        
    Returns:
        Tuple of (is_valid, transcript_data or None)
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if it has expected structure
        # Adjust this based on your actual JSON structure
        if not isinstance(data, dict):
            return False, None
        
        return True, data
    
    except json.JSONDecodeError:
        return False, None
    except Exception:
        return False, None


if __name__ == "__main__":
    # Test CSV processing
    processor = CSVProcessor()
    
    # Create a sample CSV for testing
    sample_csv = """InteractionId,JsonSummaryFilePath,DurationSeconds,SentimentScore,IsAutomatable,Intent,Topic,AgentTask
call_001,/path/to/1/transcript_001.json,300,4.5,Yes,Billing Question,Payment,Process Payment
call_002,/path/to/2/transcript_002.json,450,3.8,No,Technical Support,Software Issue,Troubleshoot
call_003,/path/to/3/transcript_003.json,200,4.9,Yes,Account Question,Login Issue,Reset Password"""
    
    # Write sample CSV
    with open('test_sample.csv', 'w') as f:
        f.write(sample_csv)
    
    # Process the CSV
    conversations, stats = processor.process_csv('test_sample.csv', verify_transcripts=False)
    
    print("CSV Processing Results:")
    print(f"Total rows: {stats['total_rows']}")
    print(f"Valid rows: {stats['valid_rows']}")
    print(f"Invalid rows: {stats['invalid_rows']}")
    print(f"\nProcessed {len(conversations)} conversations")
    
    # Show summary
    summary = processor.get_summary()
    print(f"\nErrors: {len(summary['errors'])}")
    print(f"Warnings: {len(summary['warnings'])}")
    
    if conversations:
        print(f"\nFirst conversation:")
        print(json.dumps(conversations[0], indent=2))
    
    # Cleanup
    os.remove('test_sample.csv')
    print("\nCSV processing test completed!")
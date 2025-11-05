#!/usr/bin/env python3
"""
Integrated API Server with Steps 0, 1, 2
NEW WORKFLOW: Upload CSV → Upload Mapping → Generate Intents → Select Intent → Run Analysis
"""

import http.server
import socketserver
import json
import os
import csv
import subprocess
import threading
import urllib.parse
from pathlib import Path
import io
import sys
import time
import re
import pandas as pd

from datetime import datetime

def create_project_folder(base_dir: str, company_name: str) -> str:
    safe_name = ''.join(company_name.split())  # remove spaces
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    company_dir = Path(base_dir) / safe_name
    project_dir = company_dir / f"Project_{timestamp}"
    project_dir.mkdir(parents=True, exist_ok=True)
    return str(project_dir)

# Import step modules
try:
    from annotations import save_convs, get_conversations
    from transcripts import load_whisper_as_nx, load_and_clean_nxtranscript, sample_calls
    from intents import IntentGenerator, IntentBuilder, categories2dataframe
    import bedrock
    from default_prompts import STEP1_GENERATE_INTENTS_PROMPT, STEP2_ASSIGN_CATEGORIES_PROMPT
except ImportError as e:
    print(f"⚠️  Warning: Could not import required modules: {e}")
    print("Make sure all supporting files are in the same directory")

csv.field_size_limit(sys.maxsize)

PORT = 5000
UPLOAD_FOLDER = './uploads'
WORKING_FOLDER = './data'
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)
Path(WORKING_FOLDER).mkdir(exist_ok=True)
Path('./logs').mkdir(exist_ok=True)

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP Request Handler with CORS support"""
    
    def end_headers(self):
        """Add CORS headers to all responses"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
        # --- Helper: send Server-Sent Events (used by handle_generate_intents etc.) ---
        
    def send_sse(self, data):
        """
        Safely send Server-Sent Event data to the client.
        Handles disconnects gracefully (browser closed or reloaded).
        """
        try:
            msg = f"data: {json.dumps(data)}\n\n"
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError, OSError):
            # Client disconnected — stop sending and mark connection closed
            print("⚠️ SSE connection closed by client. Stopping stream.")
            self.close_connection = True
            raise ConnectionAbortedError("Client disconnected during SSE stream")
        
    def do_OPTIONS(self):
        """Handle preflight CORS requests"""
        self.send_response(200)
        self.end_headers()
    
    def do_POST(self):
        """Handle POST requests"""
        print(f"📥 POST request to: {self.path}")
        
        if self.path == '/api/upload-asr':
            self.handle_upload_asr()
        elif self.path == '/api/upload-mapping':
            self.handle_upload_mapping()
        elif self.path == '/api/generate-intents':
            self.handle_generate_intents()
        elif self.path == '/api/filter-and-run':
            self.handle_filter_and_run()
        elif self.path == '/api/load-chat-context':
            self.handle_load_chat_context()
        elif self.path == '/api/chat-with-calls':
            self.handle_chat_with_calls()
        else:
            print(f"❌ Unknown endpoint: {self.path}")
            self.send_error(404, f"Endpoint not found: {self.path}")
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/api/health':
            self.handle_health()
        elif self.path.startswith('/api/download/'):
            self.handle_download()
        else:
            self.send_error(404, "Endpoint not found")
    
    def handle_health(self):
        """Health check endpoint"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {'status': 'healthy', 'message': 'API server is running'}
        self.wfile.write(json.dumps(response).encode())
    
    def parse_multipart(self):
        """Parse multipart form data and return file content and filename"""
        content_type = self.headers['Content-Type']
        if not content_type.startswith('multipart/form-data'):
            return None, None
        
        boundary = content_type.split('boundary=')[1].encode()
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        
        parts = body.split(b'--' + boundary)
        
        for part in parts:
            if b'Content-Disposition' in part:
                if b'filename=' in part:
                    lines = part.split(b'\r\n')
                    filename = None
                    for line in lines:
                        if b'filename=' in line:
                            filename = line.split(b'filename=')[1].strip(b'"\r\n ')
                            filename = filename.decode('utf-8')
                            break
                    
                    if filename:
                        content_start = part.find(b'\r\n\r\n') + 4
                        file_data = part[content_start:].rstrip(b'\r\n')
                        return file_data, filename
        
        return None, None
    
    def handle_upload_asr(self):
        """Upload the ASR CSV file"""
        try:
            file_data, filename = self.parse_multipart()
            
            if not file_data or not filename:
                self.send_error(400, "No file uploaded")
                return
            
            timestamp = int(time.time())
            file_path = os.path.join(UPLOAD_FOLDER, f'input_asr_{timestamp}.csv')
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            print(f"📁 Uploaded ASR file: {file_path}")
            
            # Pre-clean the file at text level (remove .mp4.mp4 rows before pandas reads it)
            # --- Phase 1: pre-clean robustly (handles multi-line rows too) ---
            cleaned_path = file_path.replace('.csv', '_cleaned.csv')
            rows_removed = 0

            try:
                # Read entire file safely even if there are quoted newlines
                df_tmp = pd.read_csv(file_path, sep='\t', engine='python', quoting=3, on_bad_lines='skip')
                before = len(df_tmp)
                # Drop any row containing ".mp4.mp4" anywhere
                mask_bad = df_tmp.apply(lambda r: any('.mp4.mp4' in str(x) for x in r.values), axis=1)
                rows_removed = int(mask_bad.sum())
                df_tmp = df_tmp[~mask_bad]
                df_tmp.to_csv(cleaned_path, sep='\t', index=False)
                file_path = cleaned_path
                if rows_removed > 0:
                    print(f"   🧹 Pre-clean removed {rows_removed} rows containing .mp4.mp4 (any column, multi-line safe)")
                else:
                    print("   ✅ No .mp4.mp4 rows found in any column")
            except Exception as e:
                print(f"   ⚠️ Pre-clean step failed fallback to line-by-line mode: {e}")
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile, \
                    open(cleaned_path, 'w', encoding='utf-8') as outfile:
                    for line in infile:
                        if '.mp4.mp4' not in line:
                            outfile.write(line)
                        else:
                            rows_removed += 1
                file_path = cleaned_path
                print(f"   🧹 Fallback removed {rows_removed} raw lines containing .mp4.mp4")
            
            row_count = 0
            error_msg = None
            
            try:
                print("   Reading CSV with tab delimiter...")
                df = pd.read_csv(file_path, sep='\t', nrows=10)
                print(f"   Original columns: {list(df.columns)}")
                
                # Normalize column names to standard format
                column_mapping = {
                    'Path': 'Filename',
                    'path': 'Filename',
                    'party': 'Party',
                    'Party': 'Party',
                    'text': 'Text',
                    'Text': 'Text',
                    'start': 'StartOffset (sec)',
                    'StartOffset (sec)': 'StartOffset (sec)',
                    'end': 'EndOffset (sec)',
                    'EndOffset (sec)': 'EndOffset (sec)'
                }
                
                df_renamed = df.rename(columns=column_mapping)
                print(f"   Normalized columns: {list(df_renamed.columns)}")
                
                # Check for required columns
                required = ['Filename', 'Party', 'Text', 'StartOffset (sec)', 'EndOffset (sec)']
                missing = [col for col in required if col not in df_renamed.columns]
                
                if missing:
                    error_msg = f"Missing columns: {missing}"
                    print(f"   ⚠️  {error_msg}")
                    row_count = len(df)
                else:
                    # Read full file and normalize  
                    df_full = pd.read_csv(file_path, sep='\t', low_memory=False)
                    
                    # Filter out rows with .mp4.mp4 extensions at source
                    rows_before = len(df_full)
                    # 🧹 Remove any row containing ".mp4.mp4" in ANY column
                    mask_any = df_full.apply(
                        lambda row: any('.mp4.mp4' in str(x) for x in row.values), axis=1
                    )
                    df_full = df_full[~mask_any]

                    rows_removed = rows_before - len(df_full)
                    if rows_removed > 0:
                        print(f"   🧹 Removed {rows_removed} rows with .mp4.mp4 in any column")
                    else:
                        print(f"   ✅ No .mp4.mp4 rows found in any column")
                    
                    if rows_removed > 0:
                        print(f"   🧹 Removed {rows_removed} rows with .mp4.mp4 extensions")
                    
                    # Keep only expected columns (first 6: Path, Line, Party, Start, End, Text)
                    if len(df_full.columns) > 6:
                        print(f"   ⚠️  Found {len(df_full.columns)} columns, keeping first 6")
                        df_full = df_full.iloc[:, :6]
                    
                    df_full = df_full.rename(columns=column_mapping)
                    
                    # Save normalized version
                    normalized_path = file_path.replace('.csv', '_normalized.csv')
                    df_full.to_csv(normalized_path, sep='\t', index=False)
                    
                    row_count = len(df_full)
                    print(f"   ✅ Normalized {row_count} rows")
                    print(f"   Saved: {normalized_path}")
                    
                    # Use normalized file for further processing
                    file_path = normalized_path
            
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                print(f"   ❌ {error_msg}")
                import traceback
                traceback.print_exc()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'success': True,
                'file_path': file_path,
                'filename': filename,
                'row_count': row_count,
                'error_msg': error_msg,
                'message': f'Uploaded {filename}' + (f' with {row_count} rows' if row_count > 0 else '')
            }
            
            print(f"   Response: row_count={row_count}")
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Upload failed: {str(e)}")
    
    def handle_upload_mapping(self):
        """Upload the L123 Intent Mapping Excel file"""
        print("🔵 handle_upload_mapping called")
        try:
            file_data, filename = self.parse_multipart()
            
            if not file_data or not filename:
                self.send_error(400, "No file uploaded")
                return
            
            timestamp = int(time.time())
            file_path = os.path.join(UPLOAD_FOLDER, f'mapping_{timestamp}.xlsx')
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            print(f"📄 Uploaded mapping file: {file_path}")
            
            try:
                categories_txt_path = self.convert_mapping_to_categories(file_path)
                print(f"✅ Conversion successful: {categories_txt_path}")
            except Exception as conv_error:
                print(f"❌ Conversion failed: {conv_error}")
                import traceback
                traceback.print_exc()
                self.send_error(500, f"Failed to convert mapping: {str(conv_error)}")
                return
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'success': True,
                'file_path': file_path,
                'categories_txt': categories_txt_path,
                'filename': filename,
                'message': f'Uploaded and converted {filename}'
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Upload failed: {str(e)}")
    
    def convert_mapping_to_categories(self, excel_path):
        """Convert L123 Excel mapping to YAML-style categories text file"""
        print(f"🔄 Converting {excel_path}...")
        
        df = pd.read_excel(excel_path)
        print(f"   Read {len(df)} rows, {len(df.columns)} columns")
        print(f"   Columns: {list(df.columns)}")
        
        l1_col = None
        l2_col = None
        l3_col = None
        
        for col in df.columns:
            col_lower = str(col).lower()
            if 'level1' in col_lower or 'l1' in col_lower or 'category_mapped' in col_lower:
                l1_col = col
            if 'level2' in col_lower or 'l2' in col_lower or 'topic_mapped' in col_lower:
                l2_col = col
            if 'level3' in col_lower or 'l3' in col_lower or 'intent' in col_lower:
                l3_col = col
        
        if not l1_col:
            raise ValueError(f"Cannot find L1 column. Available: {list(df.columns)}")
        if not l2_col:
            raise ValueError(f"Cannot find L2 column. Available: {list(df.columns)}")
        if not l3_col:
            raise ValueError(f"Cannot find L3 column. Available: {list(df.columns)}")
        
        print(f"   ✅ Found L1: '{l1_col}'")
        print(f"   ✅ Found L2: '{l2_col}'")
        print(f"   ✅ Found L3: '{l3_col}'")
        
        df_unique = df[[l1_col, l2_col, l3_col]].drop_duplicates().sort_values([l1_col, l2_col, l3_col])
        print(f"   Unique combinations: {len(df_unique)}")
        
        lines = []
        current_l1 = None
        current_l2 = None
        
        for _, row in df_unique.iterrows():
            l1 = str(row[l1_col]).strip()
            l2 = str(row[l2_col]).strip()
            l3 = str(row[l3_col]).strip()
            
            if l1 == 'nan' or l2 == 'nan' or l3 == 'nan':
                continue
            if not l1 or not l2 or not l3:
                continue
            
            if l1 != current_l1:
                lines.append(f'- {l1}')
                current_l1 = l1
                current_l2 = None
            
            if l2 != current_l2:
                lines.append(f'    - {l2}')
                current_l2 = l2
            
            lines.append(f'        - {l3}')
        
        if len(lines) == 0:
            raise ValueError("No valid L1/L2/L3 combinations found")
        
        output_path = excel_path.replace('.xlsx', '_categories.txt')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        print(f"   ✅ Converted {len(lines)} lines to: {output_path}")
        
        preview = '\n'.join(lines[:10])
        print(f"\n   Preview:\n{preview}\n   ...")
        
        return output_path
    
    def handle_generate_intents(self):
        """Run Steps 0, 1, 2 to generate intent mapping"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            
            input_csv = data['input_csv']
            categories_txt = data['categories_txt']
            company_name = data['company_name']
            company_description = data['company_description']
            prompt_template = data.get('prompt_template', STEP1_GENERATE_INTENTS_PROMPT)
            csv_format = data.get('format', 'whisper')
            max_calls = data.get('max_calls', 10000)
            
            self.send_sse({'type': 'progress', 'message': '🚀 Starting Intent Generation Pipeline'})
            self.send_sse({'type': 'progress', 'message': '=' * 80})
            
            # 📂 Standardized project directory
            project_dir = create_project_folder(WORKING_FOLDER, company_name)
            self.send_sse({'type': 'progress', 'message': f"📁 Project directory: {project_dir}"})

            # 🗂 Standardized filenames (Step outputs)
            step0_json = f"{project_dir}/cleaned_asr.json"
            step0_csv  = f"{project_dir}/cleaned_asr.csv"
            step1_json = f"{project_dir}/intent_generation.json"
            step1_csv  = f"{project_dir}/intent_generation.csv"
            step2_csv  = f"{project_dir}/intent_mapping.csv"
            
            # STEP 0
            self.send_sse({'type': 'progress', 'message': '\n📋 STEP 0: Preparing Transcripts'})
            try:
                if csv_format == 'whisper':
                    df = load_whisper_as_nx(input_csv)
                else:
                    df = load_and_clean_nxtranscript(input_csv)
                
                self.send_sse({'type': 'progress', 'message': f'  Loaded {len(df)} rows'})
                self.send_sse({'type': 'progress', 'message': f'  Columns: {list(df.columns)}'})
                
                # Filter out rows with double .mp4.mp4 extensions (invalid transcripts)
                rows_before = len(df)
                
                # Check which column contains the file paths
                path_column = 'Filename' if 'Filename' in df.columns else 'Path'
                self.send_sse({'type': 'progress', 'message': f'  Checking column: {path_column}'})
                
                # Debug: show sample of paths before filtering
                if path_column in df.columns and len(df) > 0:
                    sample_paths = df[path_column].head(3).tolist()
                    self.send_sse({'type': 'progress', 'message': f'  Sample paths: {sample_paths}'})
                
                # Filter out any files containing .mp4.mp4 (more aggressive)
                if path_column in df.columns:
                    mask = df[path_column].astype(str).str.contains(r'\.mp4\.mp4', regex=True, na=False)
                    bad_rows = mask.sum()
                    self.send_sse({'type': 'progress', 'message': f'  Found {bad_rows} rows with .mp4.mp4 pattern'})
                    
                    # Show sample of what will be removed
                    if bad_rows > 0:
                        bad_samples = df[mask][path_column].head(2).tolist()
                        self.send_sse({'type': 'progress', 'message': f'  Examples to remove: {bad_samples}'})
                    
                    df = df[~mask]
                    rows_removed = rows_before - len(df)
                    # Extra safety: remove any rows containing ".mp4.mp4" in any column
                    mask_any = df.apply(lambda row: any('.mp4.mp4' in str(x) for x in row.values), axis=1)
                    extra_removed = mask_any.sum()
                    if extra_removed > 0:
                        df = df[~mask_any]
                        self.send_sse({'type': 'progress', 'message': f'  🧹 Extra removed {extra_removed} rows with .mp4.mp4 across any column'})

                    if rows_removed > 0:
                        self.send_sse({'type': 'progress', 'message': f'  🧹 Filtered out {rows_removed} rows with double .mp4.mp4 extensions'})
                
                # Debug: Show sample before filename extraction
                sample_before = df['Filename'].head(3).tolist()
                self.send_sse({'type': 'progress', 'message': f'  Filenames before cleaning: {sample_before}'})
                
                # Extract just the filename (UUID) from full paths - BULLETPROOF METHOD
                # Handles: /path/to/uuid.mp4, /path/to/uuid.0.mp4, uuid.mp4, uuid
                def clean_filename(path):
                    if pd.isna(path):
                        return path
                    # Get the basename (last part after / or \)
                    basename = str(path).split('/')[-1].split('\\')[-1]
                    # Remove any extension (.mp4, .0.mp4, etc)
                    # Split by . and take first part (the UUID)
                    name_without_ext = basename.split('.')[0]
                    return name_without_ext
                
                df['Filename'] = df['Filename'].apply(clean_filename)
                
                # Debug: Show sample after filename extraction
                sample_after = df['Filename'].head(3).tolist()
                self.send_sse({'type': 'progress', 'message': f'  Filenames after cleaning: {sample_after}'})
                
                # Verify cleaning worked
                still_has_paths = df['Filename'].astype(str).str.contains(r'[/\\]', na=False).sum()
                if still_has_paths > 0:
                    self.send_sse({'type': 'progress', 'message': f'  ⚠️ Warning: {still_has_paths} rows still have paths in filename'})
                
                sampled_df = sample_calls(df, max_calls=max_calls)
                
                # CRITICAL: Clean filenames again after sample_calls (in case it modified them)
                def clean_filename(path):
                    if pd.isna(path):
                        return path
                    basename = str(path).split('/')[-1].split('\\')[-1]
                    name_without_ext = basename.split('.')[0]
                    return name_without_ext
                
                if 'Filename' in sampled_df.columns:
                    sampled_df['Filename'] = sampled_df['Filename'].apply(clean_filename)
                    self.send_sse({'type': 'progress', 'message': f'  Re-cleaned filenames after sampling'})
                
                sampled_df.to_csv(step0_csv, index=False, sep='\t')
                
                # COMPREHENSIVE POST-SAVE CHECK: Clean everything one more time
                df_check = pd.read_csv(step0_csv, sep='\t')
                rows_before_check = len(df_check)
                
                # Remove .mp4.mp4 rows
                for col in df_check.columns:
                    if 'filename' in col.lower() or 'path' in col.lower():
                        df_check = df_check[~df_check[col].astype(str).str.contains(r'\.mp4\.mp4', regex=True, na=False)]
                        break
                
                # Clean ALL filenames one final time
                def clean_filename_final(path):
                    if pd.isna(path):
                        return path
                    basename = str(path).split('/')[-1].split('\\')[-1]
                    name_without_ext = basename.split('.')[0]
                    return name_without_ext
                
                if 'Filename' in df_check.columns:
                    df_check['Filename'] = df_check['Filename'].apply(clean_filename_final)
                    # Count how many still have .mp4
                    still_dirty = df_check['Filename'].astype(str).str.contains(r'\.mp4', na=False).sum()
                    if still_dirty > 0:
                        self.send_sse({'type': 'progress', 'message': f'  ⚠️ POST-SAVE: {still_dirty} filenames still contained .mp4 - now cleaned'})
                
                # Save the fully cleaned version
                if len(df_check) < rows_before_check or 'still_dirty' in locals():
                    df_check.to_csv(step0_csv, index=False, sep='\t')
                    self.send_sse({'type': 'progress', 'message': f'  ✅ Post-save cleaning complete'})


                
                # FINAL BRUTAL FORCE CLEAN: Clean the CSV before save_convs processes it
                try:
                    self.send_sse({'type': 'progress', 'message': f'  🔧 Final filename cleaning pass...'})
                    df_final = pd.read_csv(step0_csv, sep='\t')
                    
                    def brutal_clean_filename(path):
                        """Extract ONLY the UUID, no matter what format the path is in"""
                        if pd.isna(path):
                            return path
                        path_str = str(path)
                        # Remove everything before the last / or \
                        basename = path_str.split('/')[-1].split('\\')[-1]
                        # Remove ALL extensions (.mp4, .0.mp4, .mp4.mp4, etc)
                        # Just take everything before the first dot
                        uuid_only = basename.split('.')[0]
                        return uuid_only
                    
                    if 'Filename' in df_final.columns:
                        before_clean = df_final['Filename'].astype(str).str.contains(r'[/\\.mp4]', na=False).sum()
                        df_final['Filename'] = df_final['Filename'].apply(brutal_clean_filename)
                        after_clean = df_final['Filename'].astype(str).str.contains(r'[/\\.mp4]', na=False).sum()
                        
                        self.send_sse({'type': 'progress', 'message': f'  🧹 Final clean: {before_clean} dirty → {after_clean} dirty ({before_clean - after_clean} fixed)'})
                        
                        # Save the brutally cleaned version
                        df_final.to_csv(step0_csv, index=False, sep='\t')
                        self.send_sse({'type': 'progress', 'message': f'  💾 Saved final cleaned CSV'})
                except Exception as clean_error:
                    self.send_sse({'type': 'progress', 'message': f'  ⚠️ Final cleaning error: {str(clean_error)}'})
                
                conversations = get_conversations(sampled_df)
                save_convs(output_fn=step0_json, prompt=input_csv, convs=conversations, save_path=True)
                
                # VERIFY: Check if save_convs modified the CSV file
                try:
                    df_verify = pd.read_csv(step0_csv, sep='\t')
                    if 'Filename' in df_verify.columns:
                        dirty_count = df_verify['Filename'].astype(str).str.contains(r'[/\\.mp4]', na=False).sum()
                        if dirty_count > 0:
                            self.send_sse({'type': 'progress', 'message': f'  ⚠️ WARNING: After save_convs, found {dirty_count} dirty filenames! Re-cleaning...'})
                            # Clean again
                            def brutal_clean(path):
                                if pd.isna(path):
                                    return path
                                basename = str(path).split('/')[-1].split('\\')[-1]
                                return basename.split('.')[0]
                            df_verify['Filename'] = df_verify['Filename'].apply(brutal_clean)
                            df_verify.to_csv(step0_csv, index=False, sep='\t')
                            self.send_sse({'type': 'progress', 'message': f'  ✅ Re-cleaned CSV after save_convs'})
                except Exception as verify_error:
                    self.send_sse({'type': 'progress', 'message': f'  ⚠️ Verification error: {str(verify_error)}'})
                
                self.send_sse({'type': 'progress', 'message': f'  ✅ Step 0 Complete: {len(conversations)} conversations'})
                
            except Exception as e:
                self.send_sse({'type': 'error', 'message': f'Step 0 failed: {str(e)}'})
                return

            self.track_coverage("Step 0", max_calls, len(conversations), "conversations extracted")

            # STEP 1
            self.send_sse({'type': 'progress', 'message': '\n🤖 STEP 1: Generating Intents'})
            try:
                client = bedrock.get_client(region="us-east-1")
                categories_str = open(categories_txt).read()
                
                custom_prompt = prompt_template.format(
                    company_name=company_name,
                    company_description=company_description,
                    conv="{conv}",
                    categories="{categories}",
                    min_words="{min_words}",
                    max_words="{max_words}",
                    additional_instructions="{additional_instructions}"
                )
                
                generator = IntentGenerator(
                    bedrock_client=client,
                    prompt=custom_prompt,
                    categories=categories_str,
                    num_lines=10,
                    model_id='anthropic.claude-3-5-sonnet-20240620-v1:0',
                    min_words=5,
                    max_words=10,
                    max_workers=10,
                    max_tokens=256
                )
                
                generator.collect_reasons(input_json=step0_json, output_json=step1_json, max_interactions=max_calls)
                generator.create_intent_csv(step1_json, step1_csv, additional_columns=[])
                self.send_sse({'type': 'progress', 'message': f'  ✅ Step 1 Complete'})

            except Exception as e:
                self.send_sse({'type': 'error', 'message': f'Step 1 failed: {str(e)}'})
                return

            df_step1 = pd.read_csv(step1_csv, sep='\t')
            intents_with_data = df_step1.dropna(subset=['Intent'])
            self.track_coverage("Step 1", len(conversations), len(intents_with_data), "intents generated")

            # STEP 2
            self.send_sse({'type': 'progress', 'message': '\n🏷️  STEP 2: Mapping to Categories'})
            try:
                assign_prompt = STEP2_ASSIGN_CATEGORIES_PROMPT
                cat_df = categories2dataframe(categories_txt)
                reasons_df = pd.read_csv(step1_csv, sep='\t').dropna(subset=['Intent']).copy()
                
                if len(reasons_df) == 0:
                    self.send_sse({'type': 'error', 'message': 'Step 1 produced no intents!'})
                    return
                
                reasons_df['Ind'] = range(len(reasons_df))
                self.send_sse({'type': 'progress', 'message': f'  Categorizing {len(reasons_df)} intents...'})
                
                builder = IntentBuilder(client, cluster_prompt="", assign_prompt=assign_prompt)
                chunk_size = 100
                all_results = []
                
                for start in range(0, len(reasons_df), chunk_size):
                    end = min(start + chunk_size, len(reasons_df))
                    chunk_intents = list(reasons_df.iloc[start:end]['Intent'])
                    
                    try:
                        result = builder.assign_reasons(categories_txt, chunk_intents, 
                                                    'anthropic.claude-3-5-sonnet-20240620-v1:0', start)
                        
                        from io import StringIO
                        data_io = StringIO(result)
                        assign_cols = ['Ind', 'Intent_Input', 'Intent_Category', 'L3_Score', 'L2_Score', 'L1_Score']
                        df = pd.read_csv(data_io, names=assign_cols, on_bad_lines='skip')

                        df = df[~df['Ind'].astype(str).str.lower().str.contains('ind', na=False)]
                        score_cols = ['Ind', 'L3_Score', 'L2_Score', 'L1_Score']
                        for col in score_cols:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                        df = df.dropna(subset=score_cols)
                        for col in score_cols:
                            df[col] = df[col].astype(int)
                        
                        if len(df) > 0:
                            all_results.append(df)
                        else:
                            print(f"⚠️ Chunk {start}-{end} produced no valid rows")
                    except Exception as chunk_error:
                        print(f"❌ Chunk {start}-{end} failed: {chunk_error}")
                        self.send_sse({'type': 'progress', 'message': f'  ⚠️ Chunk {start}-{end} failed'})
                    
                    progress_pct = int((end / len(reasons_df)) * 100)
                    self.send_sse({'type': 'progress', 'message': f'  Progress: {progress_pct}%'})
                
                if len(all_results) == 0:
                    self.send_sse({'type': 'error', 'message': 'Step 2: No valid categorizations produced. Check logs.'})
                    return
                
                combined_df = pd.concat(all_results, ignore_index=True)
                print(f"✅ Combined {len(combined_df)} total rows from {len(all_results)} chunks")

                combined_df.drop(['Intent_Input'], axis=1, inplace=True, errors='ignore')
                merged_df = pd.merge(reasons_df, combined_df, on='Ind')
                merged_df['Intent_Category'] = merged_df['Intent_Category'].str.replace(r',.*', '', regex=True)
                merged_df.to_csv(step2_csv, sep='\t', index=False)
                
                if 'L3_Score' in merged_df.columns:
                    score_distribution = merged_df['L3_Score'].value_counts().sort_index()
                    self.send_sse({'type': 'progress', 'message': f'  Score distribution: {dict(score_distribution)}'})
                
                self.send_sse({'type': 'progress', 'message': f'  ✅ Step 2 Complete: {len(merged_df)} intents categorized'})

            except Exception as e:
                print(f"❌ Step 2 failed: {e}")
                import traceback
                traceback.print_exc()
                self.send_sse({'type': 'error', 'message': f'Step 2 failed: {str(e)}'})
                return

            # Diagnostics
            try:
                self.diagnose_coverage_issues(step0_json, step1_csv, step2_csv)
                self.analyze_low_score_intents(step2_csv)
            except Exception as diag_error:
                self.send_sse({'type': 'progress', 'message': f'  ⚠️ Diagnostic failed: {str(diag_error)}'})

            # Extract intents
            try:
                intents, total_calls, calls_with_intents, unique_intents = self.extract_intents(step2_csv)
                coverage_pct = (calls_with_intents / total_calls * 100) if total_calls > 0 else 0
                
                self.send_sse({'type': 'progress', 'message': f'✅ COMPLETE!'})
                self.send_sse({'type': 'progress', 'message': f'   Unique intent types: {unique_intents}'})
                self.send_sse({'type': 'progress', 'message': f'   Coverage: {calls_with_intents}/{total_calls} calls ({coverage_pct:.1f}%)'})

                # ✅ FINAL SSE — only once
                try:
                    self.send_sse({
                        'type': 'complete',
                        'results': {
                            'intents': intents,
                            'intent_mapping_file': step2_csv,
                            'total_intents': unique_intents,
                            'total_processed': total_calls,
                            'intents_assigned': calls_with_intents,
                            'project_dir': project_dir
                        }
                    })
                    print("✅ Pipeline completed successfully — final SSE sent.")
                except (BrokenPipeError, ConnectionResetError, ValueError, OSError) as e:
                    print(f"⚠️ SSE connection closed before completion: {e}")
                    self.close_connection = True
                    return

            except Exception as e:
                print(f"⚠️ Pipeline error after completion: {e}")
                import traceback
                traceback.print_exc()

        except Exception as e:
            import traceback
            print(f"❌ Unhandled pipeline failure: {e}")
            traceback.print_exc()
            try:
                self.send_sse({'type': 'error', 'message': f'Pipeline failed: {str(e)}'})
            except Exception:
                pass

    
    def extract_intents(self, intent_file_path):
        """Extract unique intents with volume from the mapping file"""
        df_full = pd.read_csv(intent_file_path, sep='\t')
        
        self.send_sse({'type': 'progress', 'message': f'\n📊 Analyzing Intent Coverage'})
        self.send_sse({'type': 'progress', 'message': f'  Total rows in mapping file: {len(df_full)}'})
        
        # Report score distribution BEFORE filtering
        if 'L3_Score' in df_full.columns:
            score_dist = df_full['L3_Score'].value_counts().sort_index()
            self.send_sse({'type': 'progress', 'message': f'  Score Distribution:'})
            for score in sorted(score_dist.keys(), reverse=True):
                count = score_dist[score]
                pct = count / len(df_full) * 100
                self.send_sse({'type': 'progress', 'message': f'    Score {score}: {count} ({pct:.1f}%)'})
            
            # ✅ CHANGE: Use more lenient filtering (4 and 5 instead of only 5)
            df = df_full[df_full['L3_Score'] >= 3].copy()
            
            coverage = len(df) / len(df_full) * 100 if len(df_full) > 0 else 0
            self.send_sse({'type': 'progress', 'message': f'  ✅ Using L3_Score ≥ 4: {len(df)}/{len(df_full)} intents ({coverage:.1f}% coverage)'})
            
            # Report what we'd get with different thresholds
            for threshold in [5, 4, 3]:
                count = len(df_full[df_full['L3_Score'] >= threshold])
                pct = count / len(df_full) * 100
                self.send_sse({'type': 'progress', 'message': f'    If using ≥{threshold}: {count} intents ({pct:.1f}%)'})
        else:
            df = df_full.copy()
            self.send_sse({'type': 'progress', 'message': f'  ⚠️  No L3_Score column found, using all intents'})
        
        if len(df) == 0:
            self.send_sse({'type': 'progress', 'message': '  ❌ No intents passed filtering!'})
            self.send_sse({'type': 'progress', 'message': '  💡 Recommendation: Lower the score threshold or improve category matching'})
            return []
        
        # Check for Intent_Category column
        if 'Intent_Category' not in df.columns:
            self.send_sse({'type': 'progress', 'message': f'  ❌ Missing Intent_Category column. Available: {list(df.columns)}'})
            return []
        
        # Count intents and calculate statistics
        intent_counts = df['Intent_Category'].value_counts()
        total = len(df)
        total_transcripts = len(df_full)  # Use original count for percentage
        intents = []
        
        for intent, volume in intent_counts.items():
            parts = intent.split(' - ')
            intents.append({
                'intent': intent,
                'volume': int(volume),
                'percentage': round((volume / total_transcripts * 100), 1),  # % of ALL transcripts
                'level1': parts[0].strip() if len(parts) > 0 else 'General',
                'level2': parts[1].strip() if len(parts) > 1 else 'Support',
                'level3': parts[2].strip() if len(parts) > 2 else 'Inquiry'
            })
        
        sorted_intents = sorted(intents, key=lambda x: x['volume'], reverse=True)
        
        # Report top intents
        self.send_sse({'type': 'progress', 'message': f'\n🏆 Top 5 Intents:'})
        for i, intent in enumerate(sorted_intents[:5], 1):
            self.send_sse({'type': 'progress', 'message': 
                f"  {i}. {intent['intent']}: {intent['volume']} calls ({intent['percentage']}%)"})
        # Add these calculations before the return statement:
        total_calls = len(df_full)
        calls_with_intents = len(df)
        unique_intent_types = len(intent_counts)

            # ✅ RETURN ALL THE STATS
        # Return: (intents_list, total_calls, calls_with_intents, unique_intent_types)
        return sorted_intents, total_calls, calls_with_intents, unique_intent_types
    
    def diagnose_coverage_issues(self, step0_json, step1_csv, step2_csv):
        """Diagnose where coverage is being lost in the pipeline"""
        self.send_sse({'type': 'progress', 'message': '\n🔍 COVERAGE DIAGNOSTIC REPORT'})
        self.send_sse({'type': 'progress', 'message': '=' * 60})
        
        # Step 0: Conversations
        with open(step0_json, 'r') as f:
            step0_data = json.load(f)
        total_conversations = len(step0_data['conversations'])
        self.send_sse({'type': 'progress', 'message': f'Step 0 - Input Conversations: {total_conversations}'})
        
        # Step 1: Intent Generation
        df_step1 = pd.read_csv(step1_csv, sep='\t')
        intents_generated = len(df_step1.dropna(subset=['Intent']))
        intents_missing = len(df_step1) - intents_generated
        step1_coverage = (intents_generated / total_conversations * 100) if total_conversations > 0 else 0
        
        self.send_sse({'type': 'progress', 'message': f'Step 1 - Intents Generated: {intents_generated}/{total_conversations} ({step1_coverage:.1f}%)'})
        if intents_missing > 0:
            self.send_sse({'type': 'progress', 'message': f'  ⚠️  {intents_missing} conversations got no intent (prompt may be failing)'})
        
        # Step 2: Category Mapping
        df_step2 = pd.read_csv(step2_csv, sep='\t')
        total_mapped = len(df_step2)
        
        self.send_sse({'type': 'progress', 'message': f'Step 2 - Categorized: {total_mapped}/{intents_generated}'})
        
        if 'L3_Score' in df_step2.columns:
            score_dist = df_step2['L3_Score'].value_counts().sort_index()
            self.send_sse({'type': 'progress', 'message': f'  Score Distribution:'})
            
            for score in sorted(score_dist.keys(), reverse=True):
                count = score_dist[score]
                pct_of_total = (count / total_conversations * 100) if total_conversations > 0 else 0
                pct_of_mapped = count / total_mapped * 100
                self.send_sse({'type': 'progress', 'message': 
                    f'    Score {score}: {count} ({pct_of_mapped:.1f}% of mapped, {pct_of_total:.1f}% of total)'})
            
            # Show coverage at different thresholds
            self.send_sse({'type': 'progress', 'message': f'\n  Coverage by Score Threshold:'})
            for threshold in [5, 4, 3, 2]:
                count = len(df_step2[df_step2['L3_Score'] >= threshold])
                pct = count / total_conversations * 100
                self.send_sse({'type': 'progress', 'message': 
                    f'    Using ≥{threshold}: {count}/{total_conversations} ({pct:.1f}% coverage)'})
        
        # Recommendations
        self.send_sse({'type': 'progress', 'message': f'\n💡 RECOMMENDATIONS:'})
        
        if step1_coverage < 90:
            self.send_sse({'type': 'progress', 'message': 
                f'  1. Improve Step 1 prompt - only {step1_coverage:.1f}% getting intents'})
        
        if 'L3_Score' in df_step2.columns:
            high_quality = len(df_step2[df_step2['L3_Score'] >= 4])
            if high_quality / total_conversations < 0.5:
                self.send_sse({'type': 'progress', 'message': 
                    f'  2. Review category taxonomy - only {high_quality/total_conversations*100:.1f}% getting good matches'})
                self.send_sse({'type': 'progress', 'message': 
                    f'     Categories may not match actual customer intents'})
        
        self.send_sse({'type': 'progress', 'message': '=' * 60})
        
    def track_coverage(self, step_name, total, successful, details=""):
        """Track and report coverage at each pipeline step"""
        coverage_pct = (successful / total * 100) if total > 0 else 0
        message = f'  📊 {step_name} Coverage: {successful}/{total} ({coverage_pct:.1f}%)'
        if details:
            message += f' - {details}'
        self.send_sse({'type': 'progress', 'message': message})
        return coverage_pct

    def handle_filter_and_run(self):
        """
        PHASE 1 TEST MODE:
        - Create intent folder under the existing project folder (L3-only, spaces removed)
        - Build asr_filtered.csv with full ASR columns, saved as TAB-separated
        - Do NOT run the pipeline yet; just return 'complete' so we can inspect the filesystem
        """
        try:
            # ---- Read request JSON ----
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            # Expected fields from FE (already implemented on your side)
            project_dir     = data.get('project_dir') or data.get('work_dir')
            intent_fullname = data.get('intent_name') or data.get('intent')  # "L1 - L2 - L3"

            if not project_dir or not intent_fullname:
                self.send_error(400, "Missing project_dir or intent_name")
                return

            project_dir = Path(project_dir)

            # ---- L3-only folder name (remove spaces + keep alnum only) ----
            parts = [p.strip() for p in intent_fullname.split(' - ') if p.strip()]
            l3_name = parts[-1] if parts else intent_fullname
            safe_intent = ''.join(ch for ch in l3_name if ch.isalnum())

            # ---- Paths ----
            intent_dir = project_dir / safe_intent
            intent_dir.mkdir(parents=True, exist_ok=True)

            cleaned_asr_csv    = project_dir / "cleaned_asr.csv"
            intent_mapping_csv = project_dir / "intent_mapping.csv"
            asr_filtered_path  = intent_dir / "asr_filtered.csv"

            # ---- Basic checks ----
            if not cleaned_asr_csv.exists():
                self.send_error(400, f"Missing file: {cleaned_asr_csv}")
                return
            if not intent_mapping_csv.exists():
                self.send_error(400, f"Missing file: {intent_mapping_csv}")
                return

            # ---- Read mapping + ASR; normalize column names ----
            df_map = pd.read_csv(intent_mapping_csv, sep='\t')
            if 'L3_Score' in df_map.columns:
                df_map = df_map[df_map['L3_Score'] >= 4]

            if 'Intent_Category' not in df_map.columns:
                self.send_error(400, "intent_mapping.csv missing 'Intent_Category'")
                return

            # exact match on full L1-L2-L3 string
            df_map_sel = df_map[df_map['Intent_Category'] == intent_fullname].copy()
            if 'Filename' not in df_map_sel.columns or df_map_sel.empty:
                self.send_error(400, "No filenames found for selected intent")
                return

            # ASR: read with TAB and normalize headers to your canonical names
            df_asr = pd.read_csv(cleaned_asr_csv, sep='\t')
            
            # Filter out rows with .mp4.mp4 extensions (safety check)
            rows_before = len(df_asr)
            for col in df_asr.columns:
                if 'filename' in col.lower() or 'path' in col.lower():
                    df_asr = df_asr[~df_asr[col].astype(str).str.contains(r'\.mp4\.mp4', regex=True, na=False)]
                    break
            rows_removed = rows_before - len(df_asr)
            if rows_removed > 0:
                print(f"  🧹 Filtered out {rows_removed} rows with .mp4.mp4 from cleaned_asr.csv")


            col_map = {
                'path': 'Filename', 'Path': 'Filename',
                'party': 'Party', 'Party': 'Party',
                'text': 'Text', 'Text': 'Text',
                'start': 'StartOffset (sec)', 'StartOffset': 'StartOffset (sec)',
                'StartTime': 'StartOffset (sec)', 'StartTimeSec': 'StartOffset (sec)',
                'end': 'EndOffset (sec)', 'EndOffset': 'EndOffset (sec)',
                'EndTime': 'EndOffset (sec)', 'EndTimeSec': 'EndOffset (sec)',
            }
            df_asr = df_asr.rename(columns=lambda c: str(c).strip())
            df_asr = df_asr.rename(columns=col_map)

            required = ['Filename', 'Party', 'Text', 'StartOffset (sec)', 'EndOffset (sec)']
            missing = [c for c in required if c not in df_asr.columns]
            if missing:
                self.send_error(400, f"cleaned_asr.csv missing required columns after normalization: {missing}; Have: {list(df_asr.columns)}")
                return

            # ---- Filter ASR by filenames for this intent (keep ALL ASR columns) ----
            keep_cols = [c for c in df_asr.columns if c != 'Unnamed: 0']
            df_filtered = df_asr[df_asr['Filename'].isin(df_map_sel['Filename'])][keep_cols]

            # ---- SAVE FILTERED FILE AS TAB-SEPARATED (critical) ----
            df_filtered.to_csv(asr_filtered_path, index=False, sep='\t')

            # ---- Log + SSE + STOP (no pipeline yet) ----
            # ----  Run the actual universal_pipeline.py process ----
            analysis_prompt = data.get('analysis_prompt', '')
            batch_size = data.get('batch_size', 10)
            workers = data.get('workers', 2)
            client = data.get('client', 'UnknownClient')
            intent_fullname = data.get('intent_name', 'UnknownIntent')

            cmd = [
                sys.executable, 'universal_pipeline.py',
                '--client', client,
                '--intent', intent_fullname,
                '--input', str(asr_filtered_path),
                '--output-dir', str(intent_dir),
                '--batch-size', str(batch_size),
                '--workers', str(workers),
                '--prompt', analysis_prompt,
                '--skip-company-folder'
            ]

            print("🚀 Launching pipeline:", " ".join(cmd))
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                self.send_sse({'type': 'progress', 'message': line})

            process.wait()

            # ---- Verify outputs ----
            results_csv  = intent_dir / "analysis_results.csv"
            summary_json = intent_dir / "analysis_summary.json"

            if results_csv.exists() and summary_json.exists():
                self.send_sse({'type': 'complete', 'results': {
                    'project_dir': str(project_dir),
                    'intent_dir': str(intent_dir),
                    'filtered_file': str(asr_filtered_path),
                    'analysis_results': str(results_csv),
                    'analysis_summary': str(summary_json)
                }})
            else:
                self.send_sse({'type': 'error', 'message': 'Expected analysis outputs not found'})

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.send_error(500, f"filter-and-run (phase1) failed: {e}")

    
    def get_filenames_for_intent(self, intent_file, target_intent):
        """Get list of filenames for a specific intent"""
        df = pd.read_csv(intent_file, sep='\t')
        
        if 'Intent_Category' in df.columns and 'Filename' in df.columns:
            filtered = df[df['Intent_Category'] == target_intent]
            if 'L3_Score' in df.columns:
                filtered = filtered[filtered['L3_Score'] == 4]
            return set(filtered['Filename'].tolist())
        
        return set()
    
    def filter_asr_by_filenames(self, asr_file, filenames, intent):
        """Filter ASR file to only include specified filenames"""
        intent_safe = re.sub(r'\W+', '', intent)
        output_dir = f"{WORKING_FOLDER}/filtered_{intent_safe}"
        Path(output_dir).mkdir(exist_ok=True)
        
        filtered_path = f"{output_dir}/asr_filtered.csv"
        
        df = pd.read_csv(asr_file, sep='\t')
        
        if 'Filename' in df.columns:
            df['Filename_clean'] = df['Filename'].str.replace(r'.*[\\/]([^\\/\.]+)\..*', r'\1', regex=True)
            filenames_clean = {re.sub(r'.*[\\/]([^\\/\.]+)\..*', r'\1', fn) for fn in filenames}
            
            filtered_df = df[df['Filename_clean'].isin(filenames_clean)]
            filtered_df = filtered_df.drop('Filename_clean', axis=1)
            filtered_df.to_csv(filtered_path, sep='\t', index=False)
        
        return filtered_path
    
    def send_sse(self, data):
        """Send Server-Sent Event"""
        message = f"data: {json.dumps(data)}\n\n"
        self.wfile.write(message.encode())
        self.wfile.flush()
    
    def handle_download(self):
        """Handle file download"""
        try:
            parsed = urllib.parse.urlparse(self.path)
            file_type = parsed.path.split('/')[-1]
            query = urllib.parse.parse_qs(parsed.query)
            
            output_dir = query.get('path', [''])[0]
            if not output_dir:
                self.send_error(400, "No path provided")
                return
            
            file_mapping = {
                'results': 'analysis_results.csv',
                'normalized': 'analysis_normalized.csv',
                'summary': 'analysis_summary.json'
            }
            
            if file_type not in file_mapping:
                self.send_error(400, "Invalid file type")
                return
            
            file_path = os.path.join(output_dir, file_mapping[file_type])
            
            if not os.path.exists(file_path):
                self.send_error(404, "File not found")
                return
            
            self.send_response(200)
            content_type = 'application/json' if file_type == 'summary' else 'text/csv'
            self.send_header('Content-type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{file_mapping[file_type]}"')
            self.end_headers()
            
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
            
        except Exception as e:
            self.send_error(500, f"Download failed: {str(e)}")
    
    def handle_load_chat_context(self):
        """Load and format ASR data for chat context - filters on-the-fly"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            
            project_dir = Path(data.get('project_dir', ''))
            intent_fullname = data.get('intent_fullname', '')
            call_limit = min(int(data.get('call_limit', 100)), 100)  # Max 100
            
            print(f"📂 Loading chat context for intent: {intent_fullname}")
            print(f"📊 Project directory: {project_dir}")
            print(f"📊 Call limit: {call_limit}")
            
            if not project_dir.exists():
                self.send_error(400, f"Project directory not found: {project_dir}")
                return
            
            # Find the cleaned ASR file and intent mapping
            cleaned_asr = project_dir / "cleaned_asr.csv"
            intent_mapping = project_dir / "intent_mapping.csv"
            
            if not cleaned_asr.exists():
                self.send_error(404, f"Cleaned ASR file not found in {project_dir}")
                return
            
            if not intent_mapping.exists():
                self.send_error(404, f"Intent mapping file not found in {project_dir}")
                return
            
            # Read intent mapping to get filenames for this intent
            df_map = pd.read_csv(intent_mapping, sep='\t')
            df_map_filtered = df_map[df_map['Intent_Category'] == intent_fullname]
            
            if df_map_filtered.empty:
                self.send_error(404, f"No calls found for intent: {intent_fullname}")
                return
            
            filenames_for_intent = set(df_map_filtered['Filename'].tolist())
            print(f"📊 Found {len(filenames_for_intent)} files for this intent")
            
            # Read cleaned ASR with tab separator
            df_asr = pd.read_csv(cleaned_asr, sep='\t')
            
            # Filter out rows with .mp4.mp4 extensions (safety check)
            rows_before = len(df_asr)
            for col in df_asr.columns:
                if 'filename' in col.lower() or 'path' in col.lower():
                    df_asr = df_asr[~df_asr[col].astype(str).str.contains(r'\.mp4\.mp4', regex=True, na=False)]
                    break
            rows_removed = rows_before - len(df_asr)
            if rows_removed > 0:
                print(f"  🧹 Filtered out {rows_removed} rows with .mp4.mp4 from cleaned_asr.csv")

            
            # Normalize column names
            col_map = {
                'path': 'Filename', 'Path': 'Filename',
                'party': 'Party', 'Party': 'Party',
                'text': 'Text', 'Text': 'Text',
                'start': 'StartOffset (sec)', 'StartOffset': 'StartOffset (sec)',
                'StartTime': 'StartOffset (sec)', 'StartTimeSec': 'StartOffset (sec)',
                'end': 'EndOffset (sec)', 'EndOffset': 'EndOffset (sec)',
                'EndTime': 'EndOffset (sec)', 'EndTimeSec': 'EndOffset (sec)',
            }
            df_asr = df_asr.rename(columns=lambda c: str(c).strip())
            df_asr = df_asr.rename(columns=col_map)
            
            # Filter ASR data to only include files for this intent
            df_filtered = df_asr[df_asr['Filename'].isin(filenames_for_intent)]
            
            print(f"📊 Filtered to {len(df_filtered)} rows")
            
            # Group by filename to get conversations
            conversations = []
            unique_filenames = df_filtered['Filename'].unique()[:call_limit]
            
            for filename in unique_filenames:
                call_df = df_filtered[df_filtered['Filename'] == filename].sort_values('StartOffset (sec)')
                
                conversation = {
                    'filename': filename,
                    'turns': []
                }
                
                for _, row in call_df.iterrows():
                    conversation['turns'].append({
                        'party': row['Party'],
                        'text': row['Text'],
                        'start': row['StartOffset (sec)'],
                        'end': row['EndOffset (sec)']
                    })
                
                conversations.append(conversation)
            
            # Format for Claude
            formatted_context = self.format_conversations_for_claude(conversations, intent_fullname)
            
            # Estimate tokens (rough: 1 token ≈ 4 characters)
            total_tokens = len(formatted_context) // 4
            
            print(f"✅ Loaded {len(conversations)} conversations ({total_tokens:,} tokens)")
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                'success': True,
                'calls_loaded': len(conversations),
                'total_tokens': total_tokens,
                'context': formatted_context,
                'intent_dir': str(project_dir)
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.send_error(500, f"Failed to load chat context: {e}")
    
    def format_conversations_for_claude(self, conversations, intent_name):
        """Format conversations into a readable format for Claude"""
        formatted = f"=== CUSTOMER SERVICE CALL TRANSCRIPTS ===\n\n"
        formatted += f"Intent Category: {intent_name}\n"
        formatted += f"Number of Calls: {len(conversations)}\n\n"
        formatted += "Each call shows the conversation between Customer and Agent.\n\n"
        
        for i, conv in enumerate(conversations, 1):
            formatted += f"--- Call {i}: {conv['filename']} ---\n"
            
            for turn in conv['turns']:
                party = turn['party']
                text = turn['text']
                formatted += f"{party}: {text}\n"
            
            formatted += "\n"
        
        return formatted
    
    def handle_chat_with_calls(self):
        """Handle chat messages with Bedrock streaming"""
        try:
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())
            
            message = data.get('message', '')
            chat_history = data.get('chat_history', [])
            context = data.get('context', '')
            
            if not message:
                self.send_error(400, "No message provided")
                return
            
            print(f"💬 Chat message received: {message[:50]}...")
            
            # Build messages for Claude
            messages = []
            
            # Add chat history (exclude current message as it's added below)
            for msg in chat_history[:-1]:  # Exclude the last one (current)
                messages.append({
                    'role': msg['role'],
                    'content': [{'text': msg['content']}]
                })
            
            # Add current message
            messages.append({
                'role': 'user',
                'content': [{'text': message}]
            })
            
            # System prompt
            system_prompt = f"""You are an expert analyst reviewing customer service call transcripts.

{context}

Your role:
- Answer questions about these specific transcripts
- Provide specific examples and quotes when relevant
- Identify patterns and insights
- Be concise but thorough
- If asked to summarize, provide actionable insights

The user is asking about the transcripts above. Answer their questions accurately based on the data provided."""

            print(f"🤖 Calling Bedrock with {len(messages)} messages...")
            
            # Start SSE stream
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            
            # Call Bedrock with streaming using boto3
            try:
                import boto3
                
                # Get bedrock runtime client
                bedrock_runtime = boto3.client(
                    service_name='bedrock-runtime',
                    region_name='us-east-1'
                )
                
                # Call converse stream API
                response = bedrock_runtime.converse_stream(
                    modelId="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                    messages=messages,
                    system=[{"text": system_prompt}],
                    inferenceConfig={
                        "maxTokens": 4096,
                        "temperature": 0.7,
                        "topP": 0.9
                    }
                )
                
                # Stream the response
                full_response = ""
                for event in response['stream']:
                    if 'contentBlockDelta' in event:
                        delta = event['contentBlockDelta']['delta']
                        if 'text' in delta:
                            text = delta['text']
                            full_response += text
                            self.send_sse({'type': 'content', 'content': text})
                
                # Send completion
                self.send_sse({'type': 'complete', 'full_response': full_response})
                print(f"✅ Chat response complete ({len(full_response)} chars)")
                
            except Exception as e:
                print(f"❌ Bedrock error: {e}")
                import traceback
                print(traceback.format_exc())
                self.send_sse({'type': 'error', 'message': str(e)})
            
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            try:
                self.send_sse({'type': 'error', 'message': str(e)})
            except:
                pass

def main():
    """Start the server"""
    print("=" * 80)
    print("🚀 INTEGRATED TRANSCRIPT ANALYSIS API SERVER")
    print("   NEW WORKFLOW: Generate Intents → Select → Analyze")
    print("=" * 80)
    print(f"📂 Upload folder: {UPLOAD_FOLDER}")
    print(f"📂 Working folder: {WORKING_FOLDER}")
    print(f"🌐 Server running on http://localhost:{PORT}")
    print("=" * 80)
    print("\nNew Workflow:")
    print("  1. Upload ASR CSV file")
    print("  2. Upload L123 Intent Mapping Excel")
    print("  3. Enter company info")
    print("  4. Edit AI prompt (optional)")
    print("  5. Generate intents (Steps 0→1→2)")
    print("  6. Select intent from table")
    print("  7. Run detailed analysis")
    print("\nPress Ctrl+C to stop\n")
    
    with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Server stopped")
            sys.exit(0)


if __name__ == '__main__':
    main()
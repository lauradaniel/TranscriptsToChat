# How It Works

This document explains the technical workflow and how different components of the application interact.

## 🔄 Complete Workflow

### 1. Application Startup

```
User runs: ./start.sh
  ↓
Script checks directory and dependencies
  ↓
Sets PYTHONPATH to current directory
  ↓
Launches: python3 flask_backend.py
  ↓
Flask starts on http://0.0.0.0:5000
  ↓
Browser loads: http://localhost:5000
  ↓
Flask serves index.html + MainScript.js + CSS
  ↓
MainScript.js runs: init()
  ↓
Calls: GET /api/projects
  ↓
Displays projects in UI
```

---

## 📊 Feature Workflows

### Feature 1: Create a Project

**User Action**: Click "Create Project" button

**Frontend Flow** (MainScript.js):
```javascript
1. openCreateProject()
   - Shows side panel
   - Initializes file upload dropzone

2. User fills form and uploads CSV

3. createProject() triggered on "Save" click
   - Validates form data (name required, CSV required)
   - Creates FormData object
   - Sends POST request to /api/projects

4. Displays success/error notification
```

**Backend Flow** (flask_backend.py):
```python
1. @app.route('/api/projects', methods=['POST'])
   - Receives form data with CSV file

2. Validates inputs:
   - Project name exists?
   - CSV file uploaded?
   - File is .csv?

3. Saves CSV to uploads/ folder:
   uploads/20241117_143022_filename.csv

4. Calls: create_project_from_csv()
   ↓
5. main_integration.py processes:
   - Validates CSV structure (csv_processor.py)
   - Creates project in database
   - Parses each CSV row
   - Inserts conversations into database

6. Returns response:
   {
     "success": true,
     "project_id": 1,
     "stats": {"total": 100, "processed": 95, "failed": 5},
     "warnings": ["5 transcripts have missing files"]
   }

7. Frontend reloads project list
```

**Database Changes** (database.py):
```sql
-- Creates project record
INSERT INTO projects (name, description, total_records, created_at)
VALUES ('My Project', 'Description', 100, '2024-11-17 14:30:22');

-- Creates dedicated conversations table
CREATE TABLE conversations_1 (
    interaction_id TEXT PRIMARY KEY,
    category TEXT,
    topic TEXT,
    intent TEXT,
    ...
);

-- Inserts conversation records
INSERT INTO conversations_1 VALUES (...);
INSERT INTO conversations_1 VALUES (...);
-- (repeats for each CSV row)
```

---

### Feature 2: View Summary Table

**User Action**: Select a project from dropdown

**Frontend Flow**:
```javascript
1. selectProject(projectId)
   - Sets selectedProject = projectId
   - Calls loadProjectSummary(projectId)

2. loadProjectSummary(projectId)
   - Builds filter parameters from currentFilters
   - Calls: GET /api/projects/{id}/summary?filters=...

3. renderSummaryTable(data)
   - Generates HTML table rows
   - Adds sort icons to headers
   - Adds chat buttons to each row
   - Injects into #resultsPanel
```

**Backend Flow**:
```python
1. @app.route('/api/projects/<int:project_id>/summary')
   - Receives filters from query params
   - Examples: ?categories=BILLING&topics=Payment

2. Parses filters:
   - categories → ['BILLING', 'TECHNICAL']
   - topics → ['Payment', 'Account']
   - intents → ['Make Payment']
   - sentiment_min/max → numeric ranges
   - duration_min/max → numeric ranges

3. Builds SQL query:
   SELECT
     COALESCE(category, 'Not Specified') as Category,
     COALESCE(topic, 'Not Specified') as Topic,
     COALESCE(intent, 'Unknown') as Intent,
     COALESCE(agent_task, 'Not Specified') as Agent_Task,
     COUNT(DISTINCT interaction_id) as Volume
   FROM conversations_{project_id}
   WHERE
     category IN ('BILLING', 'TECHNICAL')
     AND sentiment_score >= 3.0
   GROUP BY category, topic, intent, agent_task
   ORDER BY Volume DESC

4. Returns:
   {
     "success": true,
     "summary": [
       {"Category": "BILLING", "Topic": "Payment", "Intent": "Make Payment", "Agent_Task": "Process Payment", "Volume": 42},
       ...
     ],
     "count": 15
   }
```

---

### Feature 3: Apply Filters

**User Action**: Click filter button, select options, click "Apply"

**Frontend Flow**:
```javascript
1. openFilterPanel()
   - Shows filter side panel
   - Calls loadFilterValues(projectId)

2. loadFilterValues(projectId)
   - Calls: GET /api/projects/{id}/filter-values
   - Populates dropdowns with unique values

3. User selects filters (multi-select)

4. applyFilters()
   - Collects selected values from UI
   - Updates currentFilters object:
     {
       categories: ['BILLING'],
       topics: ['Payment', 'Refund'],
       intents: ['Make Payment'],
       agent_tasks: [],
       is_automatable: false,
       sentiment_min: 3.0,
       sentiment_max: 5.0,
       duration_min: 0,
       duration_max: 600
     }
   - Calls loadProjectSummary() with new filters
   - Closes filter panel
```

**Backend Flow**:
```python
1. GET /api/projects/{id}/filter-values
   - Queries distinct values:
     SELECT DISTINCT category, topic, intent, agent_task
     FROM conversations_{project_id}

   - Returns:
     {
       "categories": ["BILLING", "TECHNICAL", ...],
       "topics": ["Payment", "Login", ...],
       "intents": ["Make Payment", "Report Issue", ...],
       "agent_tasks": ["Process Payment", "Reset Password", ...]
     }

2. When filters applied, summary endpoint receives them
   - See "View Summary Table" workflow above
```

---

### Feature 4: AI Chat (Most Complex)

**User Action**: Click chat icon on a summary table row

**Frontend Flow**:
```javascript
1. openAIChatForRow(rowData)
   - Extracts filters from row data:
     {
       category: "BILLING",
       topic: "Payment",
       intent: "Make Payment",
       agent_task: "Process Payment"
     }
   - Shows AI chat modal
   - Sets subtitle: "Preparing context..."
   - Calls: POST /api/projects/{id}/chat/prepare

2. Receives response:
   {
     "success": true,
     "transcript_count": 71,
     "total_count": 150,
     "was_sampled": true,
     "message": "Chat context prepared successfully"
   }

3. Updates subtitle: "Chat about 71 transcripts (from 150 total)"

4. User types question and clicks send

5. sendChatMessage()
   - Validates question not empty
   - Displays user message in chat
   - Shows "AI is thinking..." message
   - Calls: POST /api/projects/{id}/chat/query

6. Receives AI response:
   {
     "success": true,
     "answer": "Based on the 71 transcripts...",
     "transcript_count": 150,
     "sampled_count": 71,
     "tokens_used": {"input": 45000, "output": 1200}
   }

7. Displays AI answer in chat
   - Removes "thinking" message
   - Shows answer with markdown formatting
   - User can ask follow-up questions
```

**Backend Flow - Part 1: Prepare Chat**:
```python
1. POST /api/projects/{id}/chat/prepare
   - Receives filters:
     {
       "filters": {
         "category": "BILLING",
         "topic": "Payment",
         "intent": "Make Payment",
         "agent_task": "Process Payment"
       }
     }

2. Query database for matching transcripts:
   - Calls: db.get_interaction_ids_by_filter(project_id, filters)
   - Returns list of (interaction_id, file_path) tuples
   - Example: [
       ("CALL001", "\\\\server\\share\\transcript001.json"),
       ("CALL002", "\\\\server\\share\\transcript002.json"),
       ...
     ]
   - Total: 150 matching transcripts found

3. Create CSV for AI (create_transcript_csv):
   a) Determine if sampling needed:
      - If ≤ 200 transcripts: Use all
      - If > 200 transcripts: Randomly sample 200

   b) Shuffle transcript references for randomness

   c) Process each transcript file:
      - Convert UNC path to local path (if on Linux)
      - Load JSON file: load_transcript_file(path)
      - Clean transcript: clean_transcript(data)
      - Extract conversation turns
      - Concatenate into single string:
        "Agent: Hello Customer: Hi Agent: ..."
      - Add to CSV row

   d) Handle missing files:
      - If file not found, skip and continue
      - Keep sampling until 200 valid transcripts or exhausted

   e) Write CSV:
      data/ProjectName_2024-11-17/transcripts_abc123.csv

      Format:
      Filename,Conversation
      CALL001,"Agent: Hello Customer: Hi Agent: ..."
      CALL002,"Agent: Good morning Customer: ..."
      ...

4. Return success:
   {
     "success": true,
     "transcript_count": 71,  # Actually found 71 valid files
     "total_count": 150,
     "was_sampled": true
   }
```

**Backend Flow - Part 2: Answer Question**:
```python
1. POST /api/projects/{id}/chat/query
   - Receives:
     {
       "filters": {...},
       "question": "What are the main issues?"
     }

2. Check if CSV exists (from prepare step):
   - Look for: data/ProjectName_2024-11-17/transcripts_abc123.csv
   - If not found, create it (with force_recreate=False)
   - If found, reuse it (consistent counts during session)

3. Load CSV and build context:
   - Read CSV file with pandas
   - Build context string:

     === CUSTOMER SERVICE CALL TRANSCRIPTS ===

     Intent Category: Make Payment
     Topic: Payment
     Category: BILLING
     Agent Task: Process Payment
     Number of Calls: 71

     --- Call 1: CALL001 ---
     Agent: Hello Customer: Hi Agent: How can I help? ...

     --- Call 2: CALL002 ---
     Agent: Good morning Customer: I need to make a payment ...

     ... (repeat for all 71 transcripts)

4. Prepare AI request:
   - System prompt: Context + Instructions
   - User message: Just the question
   - Model: Claude 3.5 Sonnet v2
   - Max tokens: 4096

5. Call AWS Bedrock (bedrock.py):
   bedrock.converse(
     messages=[{"role": "user", "content": question}],
     system_prompt=context,
     model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
     max_tokens=4096,
     temperature=0.7,
     top_p=0.9
   )

6. Receive AI response:
   - Answer text: "Based on the 71 transcripts..."
   - Input tokens: 45,000
   - Output tokens: 1,200

7. Return to frontend:
   {
     "success": true,
     "answer": "Based on the 71 transcripts...",
     "transcript_count": 150,
     "sampled_count": 71,
     "tokens_used": {"input": 45000, "output": 1200}
   }
```

---

## 🔍 Deep Dive: Key Components

### CSV Processing Pipeline

```
Raw CSV Upload
  ↓
1. Save to disk
   File: uploads/20241117_143022_file.csv
  ↓
2. Detect delimiter (csv_processor.py)
   - Try to auto-detect: comma vs tab
   - Read first 1024 bytes
   - Use Python's csv.Sniffer
  ↓
3. Validate structure
   - Check required columns present
   - Check data types
   - Return errors if invalid
  ↓
4. Parse rows
   - Read each row into dict
   - Extract fields
   - Handle missing optional fields
  ↓
5. Insert into database
   - Create conversations_{project_id} table
   - Insert each row
   - Track success/failure counts
```

### Transcript File Loading

```
File path from database
  ↓
1. Path conversion (for Linux servers)
   Windows UNC: \\SERVER\Share\file.json
   Linux mount: /mnt/share/file.json

   Uses PATH_MAPPINGS config
  ↓
2. Check file exists
   os.path.exists(converted_path)
  ↓
3. Load JSON
   json.load(file)
  ↓
4. Clean transcript (remove metadata)
   Input JSON:
   {
     "topics": [
       {
         "text": "Hello",
         "speaker": 0,
         "startOffset": 1000,
         "endOffset": 2000,
         "category": "BILLING",  ← Remove
         "score": 0.95,          ← Remove
         "namedEntities": [...]  ← Remove
       }
     ],
     "version": "1.2"            ← Remove
   }

   Output (cleaned):
   [
     {
       "text": "Hello",
       "speaker": "Agent",
       "start_time": 1000,
       "end_time": 2000
     }
   ]
  ↓
5. Return clean conversation turns
```

### AI Context Optimization

**Problem**: Claude has a 200K token limit, but we want to analyze many transcripts.

**Solution**: Smart sampling + efficient format

```
Challenge: 500 transcripts × 100 turns each = Too many tokens

Strategy:
1. Limit to 200 transcripts max
2. Use optimized format (one row per transcript)
3. Truncate very long individual transcripts

Old Format (inefficient):
Filename,Turn,Speaker,Text
CALL001,1,Agent,Hello
CALL001,2,Customer,Hi
CALL001,3,Agent,How can I help?
→ 100 rows per transcript = lots of overhead

New Format (efficient):
Filename,Conversation
CALL001,"Agent: Hello Customer: Hi Agent: How can I help?"
→ 1 row per transcript = 60-75% fewer tokens!

Result:
- 200 transcripts with ~70 turns each
- ~45,000 input tokens
- ~4,000 output tokens
- Stays well under 200K limit
```

---

## 🎯 Smart Sampling Algorithm

**Goal**: Get exactly 200 valid transcripts despite missing files

```python
# Pseudocode
transcript_refs = db.get_filtered_transcripts()  # Returns 500 refs
target = 200
valid_transcripts = []
failed_count = 0

random.shuffle(transcript_refs)  # Randomize order

for ref in transcript_refs:
    if len(valid_transcripts) >= target:
        break  # We have enough

    transcript = load_transcript_file(ref.path)

    if transcript is None:
        failed_count += 1
        continue  # Skip missing file, try next

    valid_transcripts.append(transcript)

# Result: 200 valid transcripts even if 100 files were missing
```

**Why this works**:
- Continues sampling beyond 200 if files are missing
- Guarantees 200 valid transcripts (or exhausts all files trying)
- Random shuffle ensures variety
- Handles unreliable network file systems

---

## 🔒 Caching Strategy

### Problem
Every time user asks a question, should we:
- A) Re-load all 200 transcript files? (slow, inconsistent counts)
- B) Cache the transcripts? (fast, consistent counts)

### Solution: Two-phase caching

**Phase 1: Chat Open** (force_recreate=True)
```python
# When user clicks chat icon:
create_transcript_csv(force_recreate=True)
# Deletes old CSV, creates fresh one with new random sample
# Ensures variety between different chat sessions
```

**Phase 2: During Chat** (force_recreate=False)
```python
# For each question in the same chat session:
create_transcript_csv(force_recreate=False)
# Reuses existing CSV, doesn't re-sample
# Ensures consistent counts: "Based on 71 transcripts..."
```

**CSV Naming**:
```
data/ProjectName_2024-11-17/transcripts_abc123.csv
                             └─> Hash of filters (unique per filter combo)
```

Benefits:
- Fast: No file I/O for follow-up questions
- Consistent: Same transcripts for entire chat session
- Isolated: Different filter combinations get different CSVs
- Fresh: New chat session gets new sample

---

## 🚦 Error Handling

### Database Locked Error

**Cause**: Multiple Python processes accessing SQLite on network filesystem

**Solution** (in start.sh):
```bash
# Set PYTHONPATH to ensure Flask uses local modules
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
```

**Backup Solution** (in database.py):
```python
# Use context manager to ensure connections close
with TranscriptDatabase(DB_PATH) as db:
    data = db.get_projects()
# Connection automatically closed here
```

---

### Missing Transcript Files

**Cause**: Network path not accessible or file deleted

**Handling**:
```python
# In create_transcript_csv():
try:
    transcript = load_transcript_file(path)
    if not transcript:
        failed_count += 1
        continue  # Skip and try next file
except Exception as e:
    print(f"Warning: {path} not accessible")
    continue

# Keep sampling until we have 200 valid transcripts
```

**User Experience**:
- Warning logged to console
- Chat still works with available transcripts
- Subtitle shows actual count: "Chat about 71 transcripts"

---

### AI Token Limit Exceeded

**Prevention**:
```python
MAX_CHAT_TRANSCRIPTS = 200  # Hard limit

# Per-transcript truncation
MAX_CHARS_PER_TRANSCRIPT = 4000  # ~1000 tokens

# Context size monitoring
print(f"Context size: {len(context):,} chars (~{len(context)//4:,} tokens)")
```

**Recovery**:
```python
try:
    answer = bedrock.converse(...)
except ValidationException as e:
    if "token" in str(e).lower():
        return {
            "error": "Context too large. Try filtering to fewer transcripts."
        }
```

---

## 📈 Performance Optimizations

### 1. Database Indexing
```sql
-- Primary key automatically indexed
CREATE TABLE conversations_1 (
    interaction_id TEXT PRIMARY KEY,  -- Indexed
    ...
)

-- Filtered columns should be indexed (future enhancement):
CREATE INDEX idx_category ON conversations_1(category);
CREATE INDEX idx_topic ON conversations_1(topic);
CREATE INDEX idx_intent ON conversations_1(intent);
```

### 2. Frontend Caching
```javascript
// Cache headers disabled for development
response.headers['Cache-Control'] = 'no-store, no-cache'

// For production, enable caching:
response.headers['Cache-Control'] = 'public, max-age=3600'
```

### 3. CSV Generation
```python
# Only generate CSV once per chat session
if csv_exists and not force_recreate:
    return existing_csv  # Skip file I/O
```

### 4. Database Connection Pooling
```python
# Future enhancement: Use connection pool
from sqlalchemy import create_engine, pool

engine = create_engine(
    f'sqlite:///{DB_PATH}',
    poolclass=pool.QueuePool,
    pool_size=5
)
```

---

## 🔄 State Management

### Frontend State
```javascript
// Global state in MainScript.js
let projects = [];              // All projects from API
let selectedProject = null;     // Currently selected project ID
let currentFilters = {          // Active filters
    categories: [],
    topics: [],
    intents: [],
    agentTasks: [],
    isAutomatable: false,
    sentimentRange: [1, 5],
    durationRange: [0, 1000]
};
let currentSummaryData = [];    // Currently displayed table data
let currentChatContext = null;  // Active chat session data
```

### Backend State
```python
# Stateless - each request is independent
# State stored in:
# 1. SQLite database (persistent)
# 2. CSV files in data/ folder (cache)
# 3. Session data in browser (frontend)
```

---

## 🎨 UI Update Flow

```
User action (click, type)
  ↓
Event handler in MainScript.js
  ↓
Update state variables
  ↓
Call API endpoint (if needed)
  ↓
Receive response
  ↓
Update DOM (innerHTML, classList)
  ↓
Show notification (if needed)
  ↓
Browser renders changes
```

Example: Applying filters
```javascript
1. User clicks "Apply" in filter panel
   ↓
2. applyFilters() called
   ↓
3. currentFilters updated:
   currentFilters.categories = ['BILLING']
   ↓
4. closeFilterPanel() - UI update
   ↓
5. loadProjectSummary(selectedProject) - API call
   ↓
6. fetch('/api/projects/1/summary?categories=BILLING')
   ↓
7. Receive response: {summary: [...]}
   ↓
8. renderSummaryTable(response.summary)
   ↓
9. Generate HTML, inject into #resultsPanel
   ↓
10. showNotification('Filters applied')
```

---

## 🔍 Debugging Tips

### Backend Debugging
```python
# Flask prints detailed logs:
print(f"🔍 Filters received: {filters}")
print(f"📊 Query: {query}")
print(f"✅ Results: {len(rows)} rows")

# Check browser Network tab for API responses
```

### Frontend Debugging
```javascript
// Use browser console:
console.log('Current filters:', currentFilters);
console.log('Selected project:', selectedProject);
console.log('Summary data:', currentSummaryData);

// Add breakpoints in DevTools Sources tab
```

### Database Debugging
```bash
# Open database directly:
sqlite3 data/transcript_projects.db

# Run queries:
SELECT * FROM projects;
SELECT * FROM conversations_1 LIMIT 10;

# Check table structure:
.schema conversations_1
```

---

## 🎯 Next Steps

- See **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** for development setup
- See **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** for file details
- See **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** for production deployment

# Project Structure

This document explains the organization of files and folders in the TranscriptsToChat application.

## 📂 Directory Overview

```
TranscriptsToChat/
├── Backend (Python)
│   ├── flask_backend.py         # Main Flask application (API + static file server)
│   ├── database.py              # SQLite database operations
│   ├── csv_processor.py         # CSV validation and processing
│   ├── main_integration.py      # Integrates CSV → Database
│   ├── bedrock.py               # AWS Bedrock (Claude AI) client
│   └── simple_api_server.py     # Legacy API server (not used)
│
├── Frontend (HTML/CSS/JS)
│   ├── index.html               # Main HTML structure
│   ├── MainScript.js            # All JavaScript logic
│   ├── styleUI.css              # Main styles
│   └── table-scroll-styles.css  # Table-specific styles
│
├── Scripts & Config
│   ├── start.sh                 # Startup script (recommended way to run)
│   ├── fix_network_db.sh        # Database repair utility
│   ├── requirements.txt         # Python dependencies
│   └── .gitignore               # Git ignore rules
│
├── Data (Generated at runtime)
│   ├── data/                    # Database and CSV cache folder
│   │   ├── transcript_projects.db
│   │   └── ProjectName_YYYY-MM-DD/
│   │       └── transcripts_*.csv
│   └── uploads/                 # Uploaded CSV files
│
└── Documentation
    ├── README.md                # Quick start guide
    ├── DEPLOYMENT_GUIDE.md      # Deployment options
    ├── PROJECT_STRUCTURE.md     # This file
    ├── HOW_IT_WORKS.md          # Technical workflow
    └── DEVELOPER_GUIDE.md       # Development guide
```

---

## 🔧 Backend Files (Python)

### `flask_backend.py` (Main Application)
**Lines**: ~1900
**Purpose**: Core Flask application that serves both API endpoints and frontend files

**Key Features**:
- Static file serving (HTML, CSS, JS)
- No-cache headers for development (lines 37-46)
- REST API endpoints for projects, filters, and AI chat
- Database integration
- Transcript file loading and CSV generation

**Important Endpoints**:
```python
GET  /                              # Serve index.html
GET  /<path>                        # Serve static files (CSS, JS)
GET  /api/health                    # Health check
GET  /api/projects                  # List all projects
POST /api/projects                  # Create new project
GET  /api/projects/<id>/summary     # Get filtered summary data
POST /api/projects/<id>/chat/prepare # Prepare AI chat context
POST /api/projects/<id>/chat/query  # Ask AI a question
```

**Configuration Variables** (lines 26-29):
- `UPLOAD_FOLDER = 'uploads'` - Where uploaded CSVs are stored
- `DB_PATH = 'data/transcript_projects.db'` - Database location
- `MAX_CHAT_TRANSCRIPTS = 200` - Max transcripts for AI chat
- `PATH_MAPPINGS = {...}` - UNC path to Linux mount mappings (line 787)

---

### `database.py` (Database Layer)
**Lines**: ~550
**Purpose**: SQLite database operations with context manager support

**Key Classes**:
- `TranscriptDatabase` - Main database class with context manager

**Key Methods**:
```python
get_all_projects()                              # List projects
get_project(project_id)                         # Get single project
create_project(name, description, total_records) # Create project
get_conversations(project_id, filters)          # Query conversations
get_interaction_ids_by_filter(project_id, filters) # Get transcript paths
get_aggregated_data(project_id, group_by)      # Aggregated stats
```

**Database Schema**:
```sql
-- Projects table
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT,
    description TEXT,
    total_records INTEGER,
    created_at TIMESTAMP
)

-- Per-project conversations table (dynamic)
CREATE TABLE conversations_<project_id> (
    interaction_id TEXT PRIMARY KEY,
    category TEXT,
    topic TEXT,
    intent TEXT,
    agent_task TEXT,
    sentiment_score REAL,
    duration_seconds INTEGER,
    is_automatable TEXT,
    conversation_file_path TEXT
)
```

---

### `csv_processor.py` (CSV Validation)
**Lines**: ~450
**Purpose**: Validate and process uploaded CSV files

**Key Class**:
- `CSVProcessor` - Validates CSV structure and required columns

**Key Methods**:
```python
validate_csv_structure(csv_path)   # Check if CSV is valid
process_csv(csv_path)              # Parse CSV into records
```

**Required CSV Columns**:
- `InteractionId`
- `ConversationFilePath`

**Optional CSV Columns**:
- `Category`, `Topic`, `Intent`, `AgentTask`
- `SentimentScore`, `DurationSeconds`, `IsAutomatable`

---

### `main_integration.py` (CSV → Database)
**Lines**: ~220
**Purpose**: Orchestrates CSV upload → Database insertion

**Key Function**:
```python
create_project_from_csv(project_name, description, csv_path, db_path)
# Returns: {'success': bool, 'project_id': int, 'stats': {...}, 'warnings': [...]}
```

**Workflow**:
1. Validate CSV structure
2. Create project in database
3. Parse CSV rows
4. Insert conversations into database
5. Return stats and warnings

---

### `bedrock.py` (AWS AI Integration)
**Lines**: ~320
**Purpose**: AWS Bedrock client for Claude AI

**Key Class**:
- `BedrockClient` - Wrapper for AWS Bedrock API

**Key Method**:
```python
converse(messages, system_prompt, model_id, max_tokens, temperature)
# Returns: (answer_text, input_tokens, output_tokens)
```

**Model Used**:
- `us.anthropic.claude-3-5-sonnet-20241022-v2:0` (Claude 3.5 Sonnet v2)
- Region: `us-east-1`
- Max output tokens: 4096

---

## 🎨 Frontend Files (HTML/CSS/JS)

### `index.html` (Main HTML)
**Lines**: ~490
**Purpose**: HTML structure for the entire application

**Main Sections**:
1. **Navigation bar** (lines 14-43) - Home, Chat, Admin icons
2. **Header** (lines 47-80) - Title, project selector, buttons
3. **Results panel** (lines 82-89) - Main content area
4. **Create Project panel** (lines 93-175) - Side panel for project creation
5. **Filter panel** (lines 178-446) - Side panel for filters
6. **AI Chat modal** (lines 449-487) - Chat interface overlay

**External Dependencies**:
- `font_google.css` - Google Fonts
- `chart.js` - Chart library (currently unused)
- `styleUI.css` - Main styles
- `table-scroll-styles.css` - Table scroll behavior
- `MainScript.js` - All JavaScript logic

---

### `MainScript.js` (All JavaScript Logic)
**Lines**: ~2200
**Purpose**: Complete frontend application logic

**Key Sections**:

#### 1. State Management (lines 1-50)
```javascript
let projects = [];
let selectedProject = null;
let currentFilters = {...};
let currentSummaryData = [];
```

#### 2. Initialization (lines 51-100)
```javascript
init()                    // Initialize app on page load
loadProjects()            // Fetch projects from API
```

#### 3. View Management (lines 101-200)
```javascript
showView(viewName)        // Switch between Home/Chat/Admin views
updateUIForView()         // Update UI elements per view
```

#### 4. Project Management (lines 201-600)
```javascript
openCreateProject()       // Show create project panel
createProject()           // Handle project creation
deleteProject(id)         // Delete project
```

#### 5. Summary Table (lines 601-1000)
```javascript
loadProjectSummary(projectId)     // Load summary data
renderSummaryTable(data)          // Render table with data
applySorting(column)              // Sort table columns
```

#### 6. Filtering System (lines 1001-1400)
```javascript
loadFilterValues(projectId)       // Load filter options
applyFilters()                    // Apply selected filters
clearAllFilters()                 // Reset all filters
updateColumnVisibility()          // Show/hide table columns
```

#### 7. AI Chat (lines 1401-2000)
```javascript
openAIChatForRow(rowData)         // Open chat modal
sendChatMessage()                 // Send question to AI
displayChatMessage(text, isUser)  // Display message in UI
```

#### 8. Utility Functions (lines 2001-2200)
```javascript
showNotification(message, type)   // Show toast notifications
formatDuration(seconds)           // Format duration display
escapeHtml(text)                  // Prevent XSS
```

**API Calls**:
```javascript
fetch('/api/projects')                          // GET projects
fetch('/api/projects', {method: 'POST'})        // POST create project
fetch(`/api/projects/${id}/summary`)            // GET summary
fetch(`/api/projects/${id}/chat/prepare`)       // POST prepare chat
fetch(`/api/projects/${id}/chat/query`)         // POST chat query
```

---

### `styleUI.css` (Main Styles)
**Lines**: ~1600
**Purpose**: All CSS styles for the application

**Key Style Sections**:
1. **CSS Variables** (lines 1-50) - Color scheme, spacing
2. **Layout** (lines 51-200) - Navigation, header, panels
3. **Tables** (lines 201-500) - Summary table styles
4. **Forms** (lines 501-800) - Input fields, dropdowns
5. **Modals** (lines 801-1000) - AI chat modal styles
6. **Buttons** (lines 1001-1200) - Button variants
7. **Notifications** (lines 1201-1300) - Toast messages
8. **Responsive** (lines 1301-1600) - Mobile breakpoints

---

### `table-scroll-styles.css` (Table Scrolling)
**Lines**: ~120
**Purpose**: Specific styles for scrollable table with fixed headers

**Features**:
- Fixed table header while scrolling
- Smooth scrollbar styling
- Column width consistency

---

## 🚀 Scripts & Configuration

### `start.sh` (Startup Script)
**Lines**: ~45
**Purpose**: Recommended way to start the application

**What it does**:
1. Verifies we're in the correct directory
2. Checks if `flask_backend.py` exists
3. Sets correct `PYTHONPATH` (prevents database lock issues)
4. Installs dependencies if needed
5. Starts Flask backend

**Usage**:
```bash
./start.sh
```

---

### `fix_network_db.sh` (Database Repair)
**Lines**: ~20
**Purpose**: Fix database corruption on network filesystems

**When to use**:
- "Database is locked" errors on network drives
- Database corruption after unclean shutdown

**Usage**:
```bash
./fix_network_db.sh
```

---

### `requirements.txt` (Dependencies)
**Lines**: 4
**Dependencies**:
```
flask>=2.3.0           # Web framework
flask-cors>=4.0.0      # CORS support
pandas>=2.0.0          # CSV processing
boto3>=1.28.0          # AWS SDK (for Bedrock)
```

---

## 📁 Generated Folders (Runtime)

### `data/` (Database & Cache)
Created automatically when the app runs.

**Contents**:
```
data/
├── transcript_projects.db              # Main SQLite database
└── ProjectName_YYYY-MM-DD/             # Per-project folder
    └── transcripts_abc123.csv          # Cached CSV for AI chat
```

**Purpose**:
- `transcript_projects.db` - Stores all project metadata and conversation records
- CSV files - Pre-processed transcripts for AI chat (cached for performance)

**Backup**:
```bash
cp -r data/ data_backup/
```

---

### `uploads/` (Uploaded CSV Files)
Created when user uploads CSV files.

**Contents**:
```
uploads/
└── 20241117_143022_my_transcripts.csv  # Timestamped uploads
```

**Purpose**:
- Keep original uploaded CSVs for reference
- Enable re-processing if needed

---

## 🔄 Data Flow

```
1. User uploads CSV
   ↓
2. Saved to uploads/
   ↓
3. csv_processor.py validates
   ↓
4. main_integration.py processes
   ↓
5. database.py stores in SQLite
   ↓
6. User views summary in browser
   ↓
7. User opens AI chat
   ↓
8. flask_backend.py creates CSV from DB
   ↓
9. CSV saved to data/ProjectName/
   ↓
10. bedrock.py sends to Claude AI
    ↓
11. AI response displayed to user
```

---

## 🔑 Key Design Patterns

### 1. Context Manager for Database
```python
with TranscriptDatabase(DB_PATH) as db:
    projects = db.get_all_projects()
# Database connection automatically closed
```

### 2. REST API Design
```
GET    /api/resource       # List all
POST   /api/resource       # Create new
GET    /api/resource/:id   # Get one
DELETE /api/resource/:id   # Delete one
```

### 3. CSV Caching for AI Chat
- Generate CSV once when chat opens (force_recreate=True)
- Reuse CSV for subsequent questions (force_recreate=False)
- Ensures consistent transcript counts during chat session

### 4. Smart Sampling
- Limit to 200 transcripts max for AI chat
- Random sampling with missing file handling
- Continue sampling until target reached or all files exhausted

---

## 📝 File Relationships

```
start.sh
  └─> flask_backend.py
        ├─> database.py              (SQLite operations)
        ├─> csv_processor.py         (CSV validation)
        ├─> main_integration.py      (CSV → Database)
        ├─> bedrock.py               (AWS AI)
        └─> Serves: index.html
                     ├─> MainScript.js
                     ├─> styleUI.css
                     └─> table-scroll-styles.css
```

---

## 💡 Development Tips

1. **Backend changes**: Restart Flask (`Ctrl+C` then `./start.sh`)
2. **Frontend changes**: Just refresh browser (`F5`) - caching is disabled!
3. **Database changes**: Use `fix_network_db.sh` if corruption occurs
4. **CSV format changes**: Update `csv_processor.py` REQUIRED_COLUMNS
5. **UI changes**: Edit `styleUI.css` or `index.html` - no build step needed!

---

## 🎯 Next Steps

- See **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)** for technical workflow details
- See **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** for development setup
- See **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** for deployment options

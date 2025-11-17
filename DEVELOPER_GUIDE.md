# Developer Guide

This guide will help you set up your development environment and contribute to the TranscriptsToChat project.

## 🚀 Development Setup

### Prerequisites

Before you start, make sure you have:

- **Python 3.8+** installed
- **Git** installed
- **AWS credentials** configured (for AI chat testing)
- **Text editor** (VS Code, Sublime, vim, etc.)
- **Web browser** with DevTools (Chrome, Firefox, Edge)

### Installation Steps

1. **Clone the repository**:
   ```bash
   git clone https://github.com/lauradaniel/TranscriptsToChat.git
   cd TranscriptsToChat
   ```

2. **Create a virtual environment** (optional but recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Configure AWS credentials** (for AI chat):
   ```bash
   aws configure
   # Enter your AWS Access Key ID, Secret Key, and region (us-east-1)
   ```

5. **Test the installation**:
   ```bash
   ./start.sh
   ```

   Open browser to http://localhost:5000 - you should see the app!

### Project Setup Complete ✅

---

## 📁 Development Workflow

### Daily Workflow

1. **Pull latest changes**:
   ```bash
   git pull origin main
   ```

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Start the development server**:
   ```bash
   ./start.sh
   ```
   - Flask runs with **auto-reload** enabled (restarts on Python changes)
   - Browser caching is **disabled** (always loads latest JS/CSS)

4. **Make your changes**:
   - Edit Python files in your IDE
   - Edit HTML/CSS/JS in your IDE
   - See changes immediately in the browser!

5. **Test your changes**:
   - Manually test in the browser
   - Check browser console for errors (F12)
   - Check Flask terminal for backend errors

6. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add feature: description of changes"
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request** on GitHub

---

## 🛠️ Common Development Tasks

### Task 1: Add a New API Endpoint

**Example**: Add an endpoint to export project data as JSON

1. **Add route in flask_backend.py**:
   ```python
   @app.route('/api/projects/<int:project_id>/export', methods=['GET'])
   def export_project(project_id):
       """Export project data as JSON"""
       try:
           # Get project data
           project = db.get_project(project_id)
           conversations = db.get_conversations(project_id)

           return jsonify({
               'success': True,
               'project': project,
               'conversations': conversations
           })
       except Exception as e:
           return jsonify({
               'success': False,
               'error': str(e)
           }), 500
   ```

2. **Test the endpoint**:
   ```bash
   curl http://localhost:5000/api/projects/1/export
   ```

3. **Call from frontend** (MainScript.js):
   ```javascript
   async function exportProject(projectId) {
       const response = await fetch(`/api/projects/${projectId}/export`);
       const data = await response.json();

       // Download as file
       const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
       const url = URL.createObjectURL(blob);
       const a = document.createElement('a');
       a.href = url;
       a.download = `project_${projectId}_export.json`;
       a.click();
   }
   ```

---

### Task 2: Add a New Database Column

**Example**: Add "AgentName" column to conversations

1. **Update database schema** (database.py):
   ```python
   def create_conversations_table(self, project_id):
       table_name = f"conversations_{project_id}"
       self.conn.execute(f"""
           CREATE TABLE IF NOT EXISTS {table_name} (
               interaction_id TEXT PRIMARY KEY,
               category TEXT,
               topic TEXT,
               intent TEXT,
               agent_task TEXT,
               agent_name TEXT,  -- NEW COLUMN
               sentiment_score REAL,
               duration_seconds INTEGER,
               is_automatable TEXT,
               conversation_file_path TEXT
           )
       """)
   ```

2. **Update CSV processor** (csv_processor.py):
   ```python
   OPTIONAL_COLUMNS = [
       'Category', 'Topic', 'Intent', 'AgentTask',
       'AgentName',  # NEW
       'SentimentScore', 'DurationSeconds', 'IsAutomatable'
   ]
   ```

3. **Update main integration** (main_integration.py):
   ```python
   # Parse CSV row
   conversation = {
       'interaction_id': row.get('InteractionId'),
       'category': row.get('Category'),
       'agent_name': row.get('AgentName'),  # NEW
       ...
   }
   ```

4. **Update frontend table** (MainScript.js):
   ```javascript
   function renderSummaryTable(data) {
       let html = `
           <thead>
               <tr>
                   <th>Category</th>
                   <th>Topic</th>
                   <th>Agent Name</th>  <!-- NEW -->
                   <th>Volume</th>
               </tr>
           </thead>
       `;
       // ... rest of table
   }
   ```

5. **Migration for existing projects**:
   ```python
   # Add migration script: migrate_add_agent_name.py
   import sqlite3

   conn = sqlite3.connect('data/transcript_projects.db')
   cursor = conn.cursor()

   # Get all project IDs
   projects = cursor.execute("SELECT id FROM projects").fetchall()

   for (project_id,) in projects:
       table = f"conversations_{project_id}"
       try:
           cursor.execute(f"ALTER TABLE {table} ADD COLUMN agent_name TEXT")
           print(f"✅ Added agent_name to {table}")
       except Exception as e:
           print(f"⚠️  {table}: {e}")

   conn.commit()
   conn.close()
   ```

---

### Task 3: Add a New UI Component

**Example**: Add a "Download CSV" button

1. **Add HTML** (index.html):
   ```html
   <button class="ngnx-button ngnx-button--medium ngnx-button--secondary"
           onclick="downloadCurrentData()">
       <span class="ngnx-button__content">
           <span class="ngnx-button__label">Download CSV</span>
       </span>
   </button>
   ```

2. **Add JavaScript** (MainScript.js):
   ```javascript
   function downloadCurrentData() {
       if (!currentSummaryData || currentSummaryData.length === 0) {
           showNotification('No data to download', 'warning');
           return;
       }

       // Convert to CSV
       const headers = Object.keys(currentSummaryData[0]);
       const csvContent = [
           headers.join(','),
           ...currentSummaryData.map(row =>
               headers.map(h => JSON.stringify(row[h])).join(',')
           )
       ].join('\n');

       // Download
       const blob = new Blob([csvContent], { type: 'text/csv' });
       const url = URL.createObjectURL(blob);
       const a = document.createElement('a');
       a.href = url;
       a.download = `summary_${new Date().toISOString()}.csv`;
       a.click();
       URL.revokeObjectURL(url);

       showNotification('CSV downloaded successfully', 'success');
   }
   ```

3. **Add CSS** (styleUI.css) if needed:
   ```css
   .download-button {
       margin-left: 10px;
   }
   ```

---

### Task 4: Modify AI Chat Behavior

**Example**: Change the AI's tone to be more formal

1. **Update system prompt** (flask_backend.py, line ~1796):
   ```python
   system_prompt = f"""You are a senior business analyst reviewing customer service transcripts.

   {context}

   Your role:
   - Provide formal, executive-level analysis
   - Use business terminology and metrics
   - Focus on actionable insights and ROI
   - Structure responses with clear sections and bullet points
   - Be concise but thorough

   The user is asking about the transcripts above. Provide a professional analysis based on the data."""
   ```

2. **Adjust AI parameters** (flask_backend.py, line ~1837):
   ```python
   answer, input_tokens, output_tokens = bedrock.converse(
       messages=messages,
       system_prompt=system_prompt,
       model_id=model_id,
       max_tokens=4096,
       temperature=0.3,  # Lower = more focused/formal
       top_p=0.9
   )
   ```

3. **Test different prompts**:
   - Ask the same question with different system prompts
   - Compare responses
   - Choose the best tone for your use case

---

## 🧪 Testing

### Manual Testing Checklist

Before committing changes, test these core flows:

**Project Management**:
- [ ] Create a new project with CSV upload
- [ ] View project list
- [ ] Delete a project

**Summary Table**:
- [ ] View summary for a project
- [ ] Sort by different columns
- [ ] Apply filters (categories, topics, intents)
- [ ] Clear filters

**AI Chat**:
- [ ] Open chat for a summary row
- [ ] Ask a question
- [ ] Ask follow-up questions
- [ ] Close and reopen chat

**Edge Cases**:
- [ ] Upload CSV with missing optional columns
- [ ] Apply filter with no matching results
- [ ] Very large projects (1000+ conversations)
- [ ] Very long transcripts (200+ turns)

### Browser Testing

Test in multiple browsers:
- Chrome/Edge (Chromium)
- Firefox
- Safari (if on Mac)

### API Testing with cURL

```bash
# Health check
curl http://localhost:5000/api/health

# List projects
curl http://localhost:5000/api/projects

# Get project summary
curl "http://localhost:5000/api/projects/1/summary?categories=BILLING"

# Prepare chat
curl -X POST http://localhost:5000/api/projects/1/chat/prepare \
  -H "Content-Type: application/json" \
  -d '{"filters": {"intent": "Make Payment"}}'

# Chat query
curl -X POST http://localhost:5000/api/projects/1/chat/query \
  -H "Content-Type: application/json" \
  -d '{"filters": {"intent": "Make Payment"}, "question": "What are the main issues?"}'
```

---

## 🐛 Debugging

### Backend Debugging

**Add debug prints**:
```python
print(f"🔍 DEBUG: Received filters: {filters}")
print(f"📊 DEBUG: Query returned {len(rows)} rows")
print(f"✅ DEBUG: Response: {response}")
```

**Use Flask debug mode** (for detailed error pages):
```python
# In flask_backend.py, change:
app.run(debug=True, host='0.0.0.0', port=5000)
```

**Python debugger**:
```python
import pdb

@app.route('/api/test')
def test():
    data = get_some_data()
    pdb.set_trace()  # Breakpoint here
    return jsonify(data)
```

### Frontend Debugging

**Browser Console** (F12):
```javascript
console.log('Current state:', {
    selectedProject,
    currentFilters,
    currentSummaryData
});

console.table(currentSummaryData);  // Nice table view
```

**Network Tab**:
- View all API requests
- Check request/response data
- Look for errors (red status codes)

**Breakpoints**:
- Open Sources tab in DevTools
- Find MainScript.js
- Click line number to add breakpoint
- Trigger the code
- Inspect variables in scope

### Database Debugging

**View database directly**:
```bash
sqlite3 data/transcript_projects.db

-- List tables
.tables

-- View projects
SELECT * FROM projects;

-- View conversations
SELECT * FROM conversations_1 LIMIT 10;

-- Count by category
SELECT category, COUNT(*) FROM conversations_1 GROUP BY category;

-- Exit
.quit
```

**Export database for inspection**:
```bash
sqlite3 data/transcript_projects.db .dump > dump.sql
```

---

## 📝 Coding Standards

### Python Code Style

Follow **PEP 8** guidelines:

```python
# Good
def get_project_summary(project_id, filters=None):
    """
    Get summarized project data.

    Args:
        project_id (int): Project ID
        filters (dict): Optional filters

    Returns:
        dict: Summary data
    """
    if filters is None:
        filters = {}

    # Implementation
    return result

# Bad
def getProjectSummary(projectId,filters=None):
    if filters == None:
        filters = {}
    return result
```

**Key points**:
- Use `snake_case` for functions and variables
- Use 4 spaces for indentation (not tabs)
- Add docstrings to all functions
- Keep lines under 100 characters
- Add type hints where helpful

### JavaScript Code Style

```javascript
// Good
function loadProjectSummary(projectId) {
    if (!projectId) {
        showNotification('Project ID required', 'error');
        return;
    }

    const url = `/api/projects/${projectId}/summary`;
    fetch(url)
        .then(response => response.json())
        .then(data => renderSummaryTable(data))
        .catch(error => console.error('Error:', error));
}

// Bad
function loadProjectSummary(projectId){
    if(!projectId){
        showNotification('Project ID required','error')
        return
    }
    const url='/api/projects/'+projectId+'/summary'
    fetch(url).then(response=>response.json()).then(data=>renderSummaryTable(data)).catch(error=>console.error('Error:',error))
}
```

**Key points**:
- Use `camelCase` for functions and variables
- Use 2 or 4 spaces consistently
- Add comments for complex logic
- Use template literals for strings
- Handle errors properly

### CSS Code Style

```css
/* Good */
.summary-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 20px;
}

.summary-table th {
    background-color: var(--ngnx-color-application-glue-5);
    padding: 12px;
    text-align: left;
}

/* Bad */
.summary-table{width:100%;border-collapse:collapse;margin-top:20px}
.summary-table th{background-color:var(--ngnx-color-application-glue-5);padding:12px;text-align:left}
```

### Git Commit Messages

Follow **Conventional Commits**:

```bash
# Good
git commit -m "feat: Add export to CSV functionality"
git commit -m "fix: Resolve database lock issue on network drives"
git commit -m "docs: Update installation instructions"
git commit -m "refactor: Simplify filter logic"

# Bad
git commit -m "updates"
git commit -m "fixed stuff"
git commit -m "WIP"
```

**Format**: `<type>: <description>`

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

---

## 🔧 Common Issues & Solutions

### Issue: "Database is locked"

**Cause**: Multiple processes accessing SQLite simultaneously

**Solution**:
```bash
# Always use start.sh script
./start.sh

# Or manually set PYTHONPATH
export PYTHONPATH="$(pwd):$PYTHONPATH"
python3 flask_backend.py
```

---

### Issue: JavaScript not updating

**Cause**: Browser caching old files

**Solution**:
1. Hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
2. Restart Flask server (ensures no-cache headers are sent)
3. Clear browser cache completely

**Prevention**: Already implemented (flask_backend.py lines 37-46)

---

### Issue: "ModuleNotFoundError: No module named 'flask'"

**Cause**: Dependencies not installed

**Solution**:
```bash
pip3 install -r requirements.txt

# Or activate virtual environment first:
source venv/bin/activate
pip3 install -r requirements.txt
```

---

### Issue: AI Chat returns "ThrottlingException"

**Cause**: AWS Bedrock rate limit exceeded

**Solution**:
- Wait 60 seconds before retrying
- Reduce number of questions asked quickly
- Check AWS console for rate limits

---

### Issue: "No transcripts found matching filters"

**Cause**: Filters are too restrictive or data missing

**Solution**:
1. Check database has data:
   ```bash
   sqlite3 data/transcript_projects.db
   SELECT COUNT(*) FROM conversations_1;
   ```

2. Clear filters and try again

3. Check CSV upload was successful

---

## 📚 Useful Resources

### Flask Documentation
- **Flask Quickstart**: https://flask.palletsprojects.com/quickstart/
- **Flask API**: https://flask.palletsprojects.com/api/

### AWS Bedrock
- **Bedrock Converse API**: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
- **Claude Models**: https://docs.anthropic.com/claude/docs

### JavaScript
- **MDN Web Docs**: https://developer.mozilla.org/en-US/
- **Fetch API**: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API

### SQLite
- **SQLite Tutorial**: https://www.sqlitetutorial.net/
- **SQLite CLI**: https://sqlite.org/cli.html

---

## 🎯 Project Roadmap

### Current Features ✅
- Project creation from CSV
- Summary table with filtering
- AI chat with Claude 3.5 Sonnet
- Multi-select filters
- Sentiment and duration sliders

### Planned Features 🔮
- [ ] User authentication
- [ ] Role-based access control
- [ ] Export to Excel
- [ ] Scheduled reports
- [ ] Advanced visualizations (charts)
- [ ] Batch AI analysis
- [ ] Search within transcripts
- [ ] Transcript editing
- [ ] Custom AI prompts
- [ ] API rate limiting

### Performance Improvements 🚀
- [ ] Database connection pooling
- [ ] Redis caching layer
- [ ] Async file loading
- [ ] Lazy loading for large tables
- [ ] Database indexing optimization

---

## 🤝 Contributing

### How to Contribute

1. **Fork the repository** on GitHub

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/amazing-feature
   ```

3. **Make your changes** and **commit**:
   ```bash
   git commit -m "feat: Add amazing feature"
   ```

4. **Push to your fork**:
   ```bash
   git push origin feature/amazing-feature
   ```

5. **Open a Pull Request** on GitHub

### Pull Request Guidelines

- Describe what your changes do
- Reference any related issues
- Include screenshots for UI changes
- Ensure code follows style guidelines
- Test manually before submitting

### Code Review Process

- All PRs require review before merging
- Address review comments promptly
- Keep PRs focused and small
- Squash commits before merging

---

## 📞 Getting Help

### Documentation
1. Check **[README.md](README.md)** for quick start
2. Check **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)** for technical details
3. Check **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** for file layout

### Community
- Open an issue on GitHub
- Ask in team chat
- Email: [your-email@example.com]

### Debugging Tips
- Check browser console (F12)
- Check Flask terminal output
- Add debug prints liberally
- Use git bisect to find breaking commits

---

## 🎉 You're Ready!

You now have everything you need to contribute to TranscriptsToChat. Happy coding! 🚀

For questions or issues, don't hesitate to reach out to the team.

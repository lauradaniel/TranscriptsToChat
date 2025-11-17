# XO Transcripts to AI Chat

A web application that analyzes customer service call transcripts using AI. Upload CSV files with transcript metadata, explore patterns, and chat with AI about specific groups of conversations.

## 🎯 What Does This App Do?

1. **Upload Transcripts**: Import CSV files containing customer service call metadata
2. **Explore Data**: View summaries by Category, Topic, Intent, and Agent Task
3. **Filter & Group**: Apply filters to find specific conversation patterns
4. **AI Chat**: Ask questions about groups of transcripts using AWS Bedrock (Claude AI)

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- AWS credentials configured (for AI chat feature)
- Network access to transcript JSON files (if using file paths in CSV)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/lauradaniel/TranscriptsToChat.git
   cd TranscriptsToChat
   ```

2. **Install dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Start the application**:
   ```bash
   ./start.sh
   ```

4. **Open in browser**:
   - Local: http://localhost:5000
   - Network: http://your-ip:5000 (shown in terminal)

That's it! 🎉

## 📊 How to Use

### Step 1: Create a Project
1. Click **"Create Project"** button
2. Enter project name and description
3. Upload a CSV file with transcript data
4. Click **"Save"**

### Step 2: Explore Data
- View the summary table showing conversation counts grouped by filters
- Click on table headers to sort
- Use the **Filter** button to narrow down results

### Step 3: Chat with AI
1. Select a row from the summary table
2. Click the **Chat** icon
3. Ask questions like:
   - "What are the main issues customers are facing?"
   - "Summarize common complaints"
   - "What actions do agents take most often?"

## 📁 CSV Format

Your CSV must have these columns:

| Column | Required | Description |
|--------|----------|-------------|
| `InteractionId` | Yes | Unique ID for each call |
| `ConversationFilePath` | Yes | Path to JSON transcript file |
| `Category` | No | Main category (e.g., "BILLING") |
| `Topic` | No | Specific topic (e.g., "Payment Issue") |
| `Intent` | No | Customer's intent (e.g., "Make Payment") |
| `AgentTask` | No | What agent did (e.g., "Processed Refund") |
| `SentimentScore` | No | Sentiment score (1-5) |
| `DurationSeconds` | No | Call duration in seconds |
| `IsAutomatable` | No | "1" if automatable, "0" if not |

**Example CSV**:
```csv
InteractionId,ConversationFilePath,Category,Topic,Intent,AgentTask,SentimentScore,DurationSeconds,IsAutomatable
CALL001,/path/to/transcript.json,BILLING,Payment,Make Payment,Process Payment,4.2,180,1
CALL002,/path/to/transcript2.json,TECHNICAL,Login Issue,Reset Password,Reset Credentials,3.8,240,1
```

## 🛠️ Configuration

### Network File Paths (Linux Deployments)

If your transcripts are on a Windows network share and you're running on Linux, configure path mappings in `flask_backend.py`:

```python
PATH_MAPPINGS = {
    '\\\\SERVER\\Share': '/mnt/share'  # Map UNC path to local mount
}
```

### AI Chat Settings

Maximum transcripts for AI chat (to stay within token limits):
```python
MAX_CHAT_TRANSCRIPTS = 200  # In flask_backend.py line 29
```

## 📚 Additional Documentation

- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Deployment options (local, server, cloud)
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - File organization and architecture
- **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)** - Technical details and workflow
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** - Development setup and contribution guide

## 🔧 Troubleshooting

### "Database is locked" error
Use the startup script: `./start.sh` (ensures correct Python path)

### Can't access from other computers
1. Check firewall: `sudo ufw allow 5000`
2. Make sure Flask is bound to 0.0.0.0 (already configured)

### JavaScript not updating after changes
1. Stop the server (Ctrl+C)
2. Restart: `./start.sh`
3. Hard refresh browser: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)

### AI Chat not working
1. Verify AWS credentials are configured: `aws sts get-caller-identity`
2. Check you have Bedrock access in us-east-1 region
3. Ensure transcript files are accessible from the server

## 🔐 Security Notes

- **For development**: Caching is disabled so JavaScript updates immediately
- **For production**: Consider adding authentication and HTTPS
- **Data privacy**: Transcripts may contain sensitive customer information

## 📝 License

[Your License Here]

## 🙋 Support

For issues or questions:
1. Check the documentation in `/docs`
2. Review troubleshooting section above
3. Open an issue on GitHub

---

Built with Flask, AWS Bedrock (Claude AI), and SQLite

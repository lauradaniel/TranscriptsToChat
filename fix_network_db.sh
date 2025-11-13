#!/bin/bash
# Quick fix for database lock issue on network filesystem

echo "Applying database path fix for network filesystem..."

# Backup original file
cp flask_backend.py flask_backend.py.backup

# Update DB_PATH to use /tmp instead of data/ folder
sed -i "s|DB_PATH = 'data/transcript_projects.db'|DB_PATH = '/tmp/transcript_projects.db'|g" flask_backend.py

echo "✅ Fixed! Database will now use /tmp/transcript_projects.db (local filesystem)"
echo "Original file backed up to flask_backend.py.backup"
echo ""
echo "Now run: ./start.sh"

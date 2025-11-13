#!/bin/bash
# Transcript Analysis Application Startup Script

# Set the working directory
cd "$(dirname "$0")"

# Ensure we use local Python modules (not from other locations)
export PYTHONPATH="$(pwd):$PYTHONPATH"

# Display startup message
echo "========================================"
echo "Starting Transcript Analysis Application"
echo "Working directory: $(pwd)"
echo "========================================"

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo ""
    echo "⚠️  Flask is not installed!"
    echo "Installing required dependencies..."
    echo ""
    pip3 install -r requirements.txt --user
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        echo "Please run manually: pip3 install -r requirements.txt --user"
        exit 1
    fi
    echo ""
    echo "✅ Dependencies installed successfully"
    echo ""
fi

# Run the Flask backend
python3 flask_backend.py

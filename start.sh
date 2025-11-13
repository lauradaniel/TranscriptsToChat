#!/bin/bash
# Transcript Analysis Application Startup Script

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if we're running from the correct location
if [ ! -f "$SCRIPT_DIR/flask_backend.py" ]; then
    echo "❌ ERROR: Cannot find flask_backend.py"
    echo "This script must be in the same directory as flask_backend.py"
    exit 1
fi

# Change to the correct directory
cd "$SCRIPT_DIR"

# Ensure we use local Python modules (not from other locations)
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

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

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

# Run the Flask backend
python3 flask_backend.py

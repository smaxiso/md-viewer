#!/bin/bash
# Convenience wrapper to start the documentation viewer
# Note: This is optional - you can run view-docs.py directly

cd "$(dirname "$0")"

echo "📚 Starting Insights Provider Documentation Viewer..."
echo "💡 Tip: You can also run 'python3 view-docs.py' directly"
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3 to use the documentation viewer"
    exit 1
fi

# Check if required packages are installed
if ! python3 -c "import markdown" 2>/dev/null; then
    echo "📦 Installing required packages..."
    pip3 install -q -r requirements-docs.txt
fi

# Make the Python script executable
chmod +x view_docs.py

# Start the server
python3 view_docs.py

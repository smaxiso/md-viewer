#!/bin/bash
# install.sh - Setup 'view' command globally

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_PATH="$(pwd)/view_docs.py"
COMMAND_PATH="$INSTALL_DIR/view"

# Ensure install directory exists
mkdir -p "$INSTALL_DIR"

# Make script executable
chmod +x "$SCRIPT_PATH"

# Create symlink
ln -sf "$SCRIPT_PATH" "$COMMAND_PATH"

echo "✅ Installation complete!"
echo "🚀 You can now run 'view' from any terminal."
echo "   Usage:"
echo "     view                  # Serve current directory"
echo "     view folder_name      # Serve specific folder"
echo "     view file_name.md     # Serve specific markdown file"

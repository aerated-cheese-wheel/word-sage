#!/bin/bash
# Auto-launch Wiki Browser in venv

# Path to venv
VENV_DIR="$HOME/wikibrowser-venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install ttkbootstrap pillow requests beautifulsoup4 tkinterweb tkhtmlsview
else
    source "$VENV_DIR/bin/activate"
fi

# Run the app
python word-sage-viewer

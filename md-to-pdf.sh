#!/bin/bash
# Markdown to PDF Converter with Hypernova Branding
# Usage: ./md-to-pdf.sh input.md [--mode light|dark] [--output output.pdf]

# Set library paths for WeasyPrint
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"

# Activate virtual environment
source .venv/bin/activate

# Run the Python converter with all arguments
python3 markdown-to-pdf.py "$@"

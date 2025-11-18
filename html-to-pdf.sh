#!/bin/bash
# HTML to PDF Converter using WeasyPrint
# Usage: ./html-to-pdf.sh input.html [output.pdf]

# Set library paths for WeasyPrint
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"

# Activate virtual environment
source .venv/bin/activate

# Get input file
INPUT_HTML="$1"

# Determine output file
if [ -z "$2" ]; then
    # If no output specified, use input name with .pdf extension
    OUTPUT_PDF="${INPUT_HTML%.html}.pdf"
else
    OUTPUT_PDF="$2"
fi

# Check if input file exists
if [ ! -f "$INPUT_HTML" ]; then
    echo "Error: Input file '$INPUT_HTML' not found"
    exit 1
fi

echo "Converting $INPUT_HTML to PDF..."

# Run WeasyPrint conversion
python3 -c "from weasyprint import HTML; HTML('$INPUT_HTML').write_pdf('$OUTPUT_PDF'); print('PDF created: $OUTPUT_PDF')"

if [ $? -eq 0 ]; then
    # Show file size
    SIZE=$(du -h "$OUTPUT_PDF" | cut -f1)
    echo "  Size: $SIZE"
    echo ""
    echo "To view: open \"$OUTPUT_PDF\""
else
    echo "✗ PDF conversion failed"
    exit 1
fi

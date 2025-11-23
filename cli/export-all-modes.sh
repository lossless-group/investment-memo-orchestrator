#!/bin/bash
# Export all investment memos in both light and dark modes

echo "═══════════════════════════════════════════════════════════════"
echo "  Exporting All Memos - Light & Dark Modes"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Activate virtual environment
source .venv/bin/activate

# Export light mode
echo "📄 Exporting LIGHT MODE..."
python export-branded.py output/ --all --mode light -o exports/light
echo ""

# Export dark mode
echo "🌙 Exporting DARK MODE..."
python export-branded.py output/ --all --mode dark -o exports/dark
echo ""

echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ Complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📁 Light Mode: exports/light/"
echo "🌙 Dark Mode:  exports/dark/"
echo ""

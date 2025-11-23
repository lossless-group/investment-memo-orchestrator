#!/usr/bin/env python3
"""
Markdown to PDF Converter with Hypernova Branding
Converts markdown files directly to PDF with proper styling and branding.
"""

import argparse
import sys
from pathlib import Path

def convert_markdown_to_pdf(md_path: Path, output_path: Path = None, mode: str = "light"):
    """Convert markdown to PDF with Hypernova branding."""

    # Import here to give better error messages
    try:
        import pypandoc
    except ImportError:
        print("Error: pypandoc is not installed.")
        print("Please install it with: uv pip install pypandoc")
        sys.exit(1)

    try:
        from weasyprint import HTML
    except ImportError:
        print("Error: WeasyPrint is not installed.")
        print("Please install it with: uv pip install weasyprint")
        print("\nNote: WeasyPrint requires system dependencies:")
        print("  macOS:   brew install cairo pango gdk-pixbuf libffi")
        sys.exit(1)

    # Read markdown file
    if not md_path.exists():
        print(f"Error: Input file not found: {md_path}")
        sys.exit(1)

    md_content = md_path.read_text(encoding='utf-8')

    # Convert markdown to HTML
    html_content = pypandoc.convert_text(
        md_content,
        'html',
        format='md',
        extra_args=['--mathjax']
    )

    # Read template CSS
    template_css_path = Path(__file__).parent.parent / "templates" / "hypernova-style.css"
    if not template_css_path.exists():
        print(f"Error: Template CSS not found: {template_css_path}")
        sys.exit(1)

    css_content = template_css_path.read_text(encoding='utf-8')

    # Determine dark mode classes
    html_class = ' class="dark-mode-page"' if mode == "dark" else ''
    body_class = ' class="dark-mode"' if mode == "dark" else ''

    # Add page background style for dark mode (ensures margins are colored)
    page_style = ""
    if mode == "dark":
        page_style = """
        html {
            background: #1a3a52 !important;
        }
        body {
            background: #1a3a52 !important;
        }
        """

    # Additional CSS for PDF rendering with colored backgrounds
    pdf_css = """
    @page {
        size: letter;
        margin: 0;
        background: #1a3a52;
    }

    html, body {
        margin: 0;
        padding: 0;
        background: transparent;
    }

    .page-wrapper {
        padding: 0.3in 0.4in 0.1in 0.4in;
        min-height: 11in;
        box-sizing: border-box;
    }
    """ if mode == "dark" else """
    @page {
        size: letter;
        margin: 0;
        background: white;
    }

    html, body {
        margin: 0;
        padding: 0;
        background: transparent;
    }

    .page-wrapper {
        padding: 0.3in 0.4in 0.1in 0.4in;
        min-height: 11in;
        box-sizing: border-box;
    }
    """

    # Create complete HTML document
    full_html = f"""<!DOCTYPE html>
<html lang="en"{html_class}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Investment Memo | Hypernova Capital</title>
    <style>
{css_content}
{page_style}
{pdf_css}
    </style>
</head>
<body{body_class}>
<div class="page-wrapper">
    <div class="memo-header">
        <div class="memo-logo">
            Hypern<span class="memo-logo-accent">o</span>va
        </div>
        <div class="memo-tagline">
            Network-Driven | High-impact | Transformative venture fund
        </div>
    </div>

    <div class="memo-content">
{html_content}
    </div>

    <div class="memo-footer">
        <div class="memo-footer-logo">
            Hypernova Capital
        </div>
        <div class="memo-footer-tagline">
            Intelligent Capital for Transformative Ventures
        </div>
    </div>
</div>
</body>
</html>"""

    # Determine output path
    if output_path is None:
        output_path = md_path.with_suffix('.pdf')
    else:
        output_path = Path(output_path)
        # If output is a directory, use input filename with .pdf extension
        if output_path.is_dir():
            output_path = output_path / md_path.with_suffix('.pdf').name

    # Convert HTML to PDF
    print(f"Converting {md_path.name} to PDF...")
    print(f"  Mode: {mode}")
    print(f"  Output: {output_path}")

    try:
        HTML(string=full_html).write_pdf(str(output_path))

        # Get file size
        size_bytes = output_path.stat().st_size
        size_kb = size_bytes / 1024

        print(f"\n✓ PDF created successfully!")
        print(f"  Size: {size_kb:.0f}K")
        print(f"\nTo view: open \"{output_path}\"")

        return output_path

    except Exception as e:
        print(f"\n✗ Error converting to PDF: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure system dependencies are installed:")
        print("     macOS: brew install cairo pango gdk-pixbuf")
        print("  2. Set library path: export DYLD_LIBRARY_PATH=\"/opt/homebrew/lib:$DYLD_LIBRARY_PATH\"")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Convert markdown to PDF with Hypernova Capital branding',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s memo.md
  %(prog)s memo.md --mode dark
  %(prog)s memo.md --mode dark --output ~/Desktop/memo.pdf
  %(prog)s memo.md -o exports/
        """
    )

    parser.add_argument('input', type=Path, help='Input markdown file')
    parser.add_argument('--mode', choices=['light', 'dark'], default='light',
                        help='Color mode (default: light)')
    parser.add_argument('--output', '-o', type=Path,
                        help='Output PDF file or directory (default: same as input with .pdf extension)')

    args = parser.parse_args()

    convert_markdown_to_pdf(args.input, args.output, args.mode)


if __name__ == '__main__':
    main()

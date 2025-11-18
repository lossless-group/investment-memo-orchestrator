#!/usr/bin/env python3
"""
Hypernova Capital - Branded Memo Exporter

Exports investment memos with Hypernova Capital branding to:
- Styled HTML (with embedded CSS and fonts)
- PDF (via wkhtmltopdf or weasyprint)
- DOCX (with custom styling)
"""

import argparse
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import pypandoc
except ImportError:
    print("Error: pypandoc is not installed.")
    print("Please install it with: uv pip install pypandoc")
    sys.exit(1)


def ensure_pandoc_installed():
    """Check if pandoc is installed."""
    try:
        version = pypandoc.get_pandoc_version()
        print(f"Using pandoc version {version}")
    except OSError:
        print("Pandoc not found. Downloading...")
        try:
            pypandoc.download_pandoc()
            version = pypandoc.get_pandoc_version()
            print(f"Pandoc {version} downloaded successfully!")
        except Exception as e:
            print(f"Error downloading pandoc: {e}")
            sys.exit(1)


def extract_title_from_markdown(md_path: Path) -> tuple[str, str]:
    """Extract title and company name from markdown file."""
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for first H1
    title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else md_path.stem

    # Try to extract company name
    company_match = re.search(r'Investment Memo[:\s]+(.+?)(?:\n|$)', content, re.IGNORECASE)
    if not company_match:
        company_match = re.search(r'# (.+?)(?:\s+[-–—]\s+|\n)', content)

    company = company_match.group(1) if company_match else title

    return title, company


def create_html_template(title: str, company: str, css_path: Path, dark_mode: bool = False) -> str:
    """Create HTML template with Hypernova branding.

    Args:
        title: Document title
        company: Company name
        css_path: Path to CSS file
        dark_mode: If True, apply dark mode styling
    """
    today = datetime.now().strftime("%B %d, %Y")

    # Read CSS
    with open(css_path, 'r') as f:
        css_content = f.read()

    # Add dark-mode class to body if requested
    body_class = ' class="dark-mode"' if dark_mode else ''

    template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | Hypernova Capital</title>
    <style>
{css_content}
    </style>
</head>
<body{body_class}>
    <div class="memo-header">
        <div class="memo-logo">
            Hypern<span class="memo-logo-accent">o</span>va
        </div>
        <div class="memo-tagline">
            Network-Driven | High-impact | Transformative venture fund
        </div>
    </div>

    <div class="memo-title">{company}</div>
    <div class="memo-subtitle">Investment Memo</div>

    <div class="memo-meta">
        <div class="memo-meta-item">
            <span class="memo-meta-label">Date</span>
            <span class="memo-meta-value">{today}</span>
        </div>
        <div class="memo-meta-item">
            <span class="memo-meta-label">Prepared By</span>
            <span class="memo-meta-value">Hypernova Capital</span>
        </div>
        <div class="memo-meta-item">
            <span class="memo-meta-label">Status</span>
            <span class="memo-meta-value">Confidential</span>
        </div>
    </div>

    $body$

    <div class="memo-footer">
        <div class="memo-footer-logo">Hypernova Capital</div>
        <div>Network-Driven | High-impact | Transformative venture fund</div>
        <div style="margin-top: 0.5rem; font-size: 0.8rem;">
            This document is confidential and proprietary to Hypernova Capital.
        </div>
    </div>
</body>
</html>"""

    return template


def convert_to_branded_html(
    input_path: Path,
    output_path: Path,
    css_path: Path,
    dark_mode: bool = False
) -> Path:
    """Convert markdown to branded HTML.

    Args:
        input_path: Path to input markdown file
        output_path: Path for output HTML file
        css_path: Path to CSS file
        dark_mode: If True, use dark mode styling
    """

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Extract metadata
    title, company = extract_title_from_markdown(input_path)

    # Create HTML template
    template = create_html_template(title, company, css_path, dark_mode)

    # Save template to temp file
    template_path = output_path.parent / f".temp_template_{output_path.stem}.html"
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(template)

    try:
        # Convert using pypandoc with custom template
        pypandoc.convert_file(
            str(input_path),
            'html',
            outputfile=str(output_path),
            extra_args=[
                '--standalone',
                '--embed-resources',
                f'--template={template_path}',
                '--toc',
                '--toc-depth=3'
            ]
        )

        return output_path
    finally:
        # Clean up temp template
        if template_path.exists():
            template_path.unlink()


def convert_html_to_pdf(html_path: Path, pdf_path: Path) -> Optional[Path]:
    """Convert HTML to PDF using WeasyPrint (modern alternative to wkhtmltopdf)."""

    try:
        from weasyprint import HTML
        print("Converting to PDF using WeasyPrint...")
        HTML(str(html_path)).write_pdf(str(pdf_path))
        return pdf_path
    except ImportError:
        print("\n⚠️  WeasyPrint not installed. Installing now...")
        print("Note: WeasyPrint requires system dependencies:")
        print("  macOS:   brew install cairo pango gdk-pixbuf libffi")
        print("  Ubuntu:  sudo apt install libpango-1.0-0 libpangocairo-1.0-0")
        print("\nInstalling WeasyPrint via pip...")
        try:
            import subprocess
            subprocess.run(['pip', 'install', 'weasyprint'], check=True)
            print("✓ WeasyPrint installed successfully!")

            # Try again after installation
            from weasyprint import HTML
            HTML(str(html_path)).write_pdf(str(pdf_path))
            return pdf_path
        except Exception as install_error:
            print(f"\n✗ Failed to install WeasyPrint: {install_error}")
            print("\nPlease install manually:")
            print("  1. Install system dependencies (see above)")
            print("  2. Run: pip install weasyprint")
            return None
    except Exception as e:
        print(f"Error converting to PDF: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Export Hypernova Capital branded investment memos',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s memo.md                          # Export to light mode HTML (default)
  %(prog)s memo.md --mode dark              # Export to dark mode HTML
  %(prog)s memo.md --mode dark --pdf        # Export dark mode HTML and PDF
  %(prog)s output/ --all --mode light       # Export all memos (light mode)
  %(prog)s output/ --all --mode dark        # Export all memos (dark mode)
  %(prog)s memo.md -o exports/dark/         # Custom output directory
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        help='Input markdown file or directory'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=Path('exports/branded'),
        help='Output directory (default: exports/branded)'
    )

    parser.add_argument(
        '--pdf',
        action='store_true',
        help='Also generate PDF output'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Convert all markdown files in directory'
    )

    parser.add_argument(
        '--mode',
        choices=['light', 'dark'],
        default='light',
        help='Color mode: light (default) or dark'
    )

    args = parser.parse_args()

    # Determine dark mode flag
    dark_mode = args.mode == 'dark'

    # Check pandoc
    ensure_pandoc_installed()

    # Get CSS path
    css_path = Path(__file__).parent / 'templates' / 'hypernova-style.css'
    if not css_path.exists():
        print(f"Error: CSS file not found: {css_path}")
        sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Determine input files
    if args.input.is_file():
        files = [args.input]
    elif args.input.is_dir():
        if args.all:
            files = list(args.input.glob('**/*.md'))
        else:
            # Find highest version files
            files = list(args.input.glob('**/4-final-draft.md'))
            if not files:
                files = list(args.input.glob('**/*-memo.md'))
    else:
        print(f"Error: Input not found: {args.input}")
        sys.exit(1)

    if not files:
        print("No markdown files found")
        sys.exit(0)

    print(f"\nFound {len(files)} file(s) to convert\n")

    success_count = 0
    pdf_count = 0

    for md_file in files:
        try:
            # Determine output filename
            if md_file.name == '4-final-draft.md':
                # Use parent directory name
                output_name = md_file.parent.name
            else:
                output_name = md_file.stem

            html_path = args.output / f"{output_name}.html"

            # Convert to branded HTML
            convert_to_branded_html(md_file, html_path, css_path, dark_mode)
            size = html_path.stat().st_size / 1024
            mode_label = "dark" if dark_mode else "light"
            print(f"✓ HTML ({mode_label}): {html_path.name} ({size:.1f} KB)")
            success_count += 1

            # Convert to PDF if requested
            if args.pdf:
                pdf_path = args.output / f"{output_name}.pdf"
                result = convert_html_to_pdf(html_path, pdf_path)
                if result:
                    size = pdf_path.stat().st_size / 1024
                    print(f"✓ PDF:  {pdf_path.name} ({size:.1f} KB)")
                    pdf_count += 1

        except Exception as e:
            print(f"✗ Error converting {md_file.name}: {e}")

    print(f"\n✓ Completed: {success_count} HTML files", end="")
    if args.pdf:
        print(f", {pdf_count} PDF files")
    else:
        print()

    print(f"\nOutput directory: {args.output.absolute()}")


if __name__ == '__main__':
    main()

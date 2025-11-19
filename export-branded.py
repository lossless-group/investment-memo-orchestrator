#!/usr/bin/env python3
"""
Branded Memo Exporter - Multi-Brand Support

Exports investment memos with customizable branding to:
- Styled HTML (with embedded CSS and fonts)
- PDF (via wkhtmltopdf or weasyprint)
- DOCX (with custom styling)

Supports multiple brand configurations:
- brand-config.yaml (default)
- brand-<name>-config.yaml (e.g., brand-accel-config.yaml)
"""

import argparse
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add src to path for branding module
sys.path.insert(0, str(Path(__file__).parent))

try:
    import pypandoc
except ImportError:
    print("Error: pypandoc is not installed.")
    print("Please install it with: uv pip install pypandoc")
    sys.exit(1)

try:
    from src.branding import BrandConfig, validate_brand_config
except ImportError:
    print("Error: Could not import branding module.")
    print("Make sure src/branding.py exists.")
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


def generate_css_from_brand(brand: BrandConfig, base_css_path: Path, dark_mode: bool = False) -> str:
    """Generate CSS with brand colors and fonts injected.

    Args:
        brand: Brand configuration
        base_css_path: Path to base CSS template
        dark_mode: If True, use dark mode colors for @page background

    Returns:
        CSS content with brand variables injected
    """
    # Read base CSS
    with open(base_css_path, 'r') as f:
        css_content = f.read()

    # Replace color placeholders with brand-specific colors
    css_content = css_content.replace('--brand-primary: #1a3a52;',
                                     f'--brand-primary: {brand.colors.primary};')
    css_content = css_content.replace('--brand-secondary: #1dd3d3;',
                                     f'--brand-secondary: {brand.colors.secondary};')
    css_content = css_content.replace('--brand-background: #ffffff;',
                                     f'--brand-background: {brand.colors.background};')
    css_content = css_content.replace('--brand-background-alt: #f0f0eb;',
                                     f'--brand-background-alt: {brand.colors.background_alt};')
    css_content = css_content.replace('--brand-text-dark: #1a2332;',
                                     f'--brand-text-dark: {brand.colors.text_dark};')
    css_content = css_content.replace('--brand-text-light: #6b7280;',
                                     f'--brand-text-light: {brand.colors.text_light};')

    # Replace @page background-color based on mode
    page_bg = brand.colors.primary if dark_mode else brand.colors.background
    css_content = css_content.replace('background-color: #ffffff; /* Light mode background - will be overridden in dark mode */',
                                     f'background-color: {page_bg};')
    css_content = css_content.replace('background-color: var(--brand-background); /* Light mode */',
                                     f'background-color: {page_bg};')
    css_content = css_content.replace('background-color: var(--brand-background);',
                                     f'background-color: {page_bg};')

    # Replace body font family
    css_content = css_content.replace("font-family: 'Arboria'",
                                     f"font-family: '{brand.fonts.family}'")
    css_content = css_content.replace('font-family: Arboria',
                                     f"font-family: '{brand.fonts.family}'")

    # Add header font family if specified
    if brand.fonts.header_family:
        # Add CSS rule for headers to use different font
        header_font_rule = f"""
/* Header Font Override */
h1, h2, h3, h4, h5, h6,
.memo-title,
.memo-subtitle,
.memo-logo,
.memo-header {{
    font-family: '{brand.fonts.header_family}', {brand.fonts.header_fallback or brand.fonts.fallback} !important;
}}
"""
        css_content += header_font_rule

    return css_content


def embed_svg_logo(svg_path: Path) -> str:
    """Read and embed SVG logo content.

    Args:
        svg_path: Path to SVG file

    Returns:
        SVG content as string
    """
    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Warning: Could not read logo SVG {svg_path}: {e}")
        return ""


def create_html_template(
    title: str,
    company: str,
    brand: BrandConfig,
    css_path: Path,
    dark_mode: bool = False
) -> str:
    """Create HTML template with brand configuration.

    Args:
        title: Document title
        company: Company name
        brand: Brand configuration
        css_path: Path to base CSS file
        dark_mode: If True, apply dark mode styling
    """
    today = datetime.now().strftime("%B %d, %Y")

    # Generate CSS with brand colors and dark mode setting
    css_content = generate_css_from_brand(brand, css_path, dark_mode)

    # Add dark-mode class to body if requested
    body_class = ' class="dark-mode"' if dark_mode else ''

    # Handle logo - use SVG if available, otherwise text-based
    logo_html = brand.company.name
    if brand.logo:
        # Use appropriate logo based on theme
        logo_path_str = brand.logo.dark_mode if dark_mode else brand.logo.light_mode
        if logo_path_str:
            logo_path = Path(logo_path_str)
            if logo_path.exists():
                # Embed SVG directly
                svg_content = embed_svg_logo(logo_path)
                if svg_content:
                    logo_html = f'<div style="width: {brand.logo.width}; height: {brand.logo.height}; margin: 0 auto;">{svg_content}</div>'
            else:
                print(f"Warning: Logo file not found: {logo_path}")
    else:
        # Fallback to text with optional accent (e.g., Hypernova)
        if 'hypernova' in brand.company.name.lower():
            logo_html = 'Hypern<span class="memo-logo-accent">o</span>va'

    template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | {brand.company.name}</title>
    <style>
{css_content}
    </style>
</head>
<body{body_class}>
    <div class="page-content">
        <div class="memo-header">
            <div class="memo-logo">
                {logo_html}
            </div>
            <div class="memo-tagline">
                {brand.company.tagline}
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
                <span class="memo-meta-value">{brand.company.name}</span>
            </div>
            <div class="memo-meta-item">
                <span class="memo-meta-label">Status</span>
                <span class="memo-meta-value">Confidential</span>
            </div>
        </div>

        $body$

        <div class="memo-footer">
            <div class="memo-footer-logo">{brand.company.name}</div>
            <div>{brand.company.tagline}</div>
            <div style="margin-top: 0.5rem; font-size: 0.8rem;">
                {brand.company.confidential_footer.format(company_name=brand.company.name)}
            </div>
        </div>
    </div>
</body>
</html>"""

    return template


def convert_to_branded_html(
    input_path: Path,
    output_path: Path,
    brand: BrandConfig,
    css_path: Path,
    dark_mode: bool = False
) -> Path:
    """Convert markdown to branded HTML.

    Args:
        input_path: Path to input markdown file
        output_path: Path for output HTML file
        brand: Brand configuration
        css_path: Path to CSS file
        dark_mode: If True, use dark mode styling
    """

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Extract metadata
    title, company = extract_title_from_markdown(input_path)

    # Create HTML template
    template = create_html_template(title, company, brand, css_path, dark_mode)

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

        # Post-process: Restore uncited footnotes that Pandoc excluded
        try:
            from pathlib import Path
            import subprocess
            restore_script = Path(__file__).parent / 'restore-uncited-footnotes.py'
            if restore_script.exists():
                result = subprocess.run(
                    [sys.executable, str(restore_script), str(output_path), str(input_path)],
                    capture_output=True, text=True
                )
                if result.stdout:
                    print(f"  {result.stdout.strip()}")
        except Exception as e:
            print(f"  Warning: Could not restore uncited footnotes: {e}")

        # Post-process: Fix duplicate citations (Obsidian-style)
        try:
            fix_script = Path(__file__).parent / 'fix-citations.py'
            if fix_script.exists():
                result = subprocess.run(
                    [sys.executable, str(fix_script), str(output_path)],
                    capture_output=True, text=True
                )
                if result.stdout:
                    print(f"  {result.stdout.strip()}")
        except Exception as e:
            print(f"  Warning: Could not fix citations: {e}")

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
        description='Export branded investment memos with customizable branding',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s memo.md                          # Export to dark mode HTML (default brand)
  %(prog)s memo.md --brand accel            # Use brand-accel-config.yaml
  %(prog)s memo.md --mode light             # Export to light mode HTML
  %(prog)s memo.md --pdf                    # Export dark mode HTML and PDF
  %(prog)s output/ --all                    # Export all memos (dark mode)
  %(prog)s memo.md -o exports/accel/        # Custom output directory
  %(prog)s memo.md --brand hypernova        # Specific brand with dark mode

Multiple Brands:
  Create brand config files for different clients:
  - brand-hypernova-config.yaml
  - brand-accel-config.yaml
  - brand-a16z-config.yaml

  Then export with: %(prog)s memo.md --brand accel
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
        '--brand',
        type=str,
        default=None,
        help='Brand name (loads brand-{name}-config.yaml). If not specified, uses brand-config.yaml or defaults.'
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
        default='dark',
        help='Color mode: dark (default) or light'
    )

    args = parser.parse_args()

    # Load brand configuration
    print(f"\n{'='*60}")
    print("BRANDED MEMO EXPORTER")
    print(f"{'='*60}\n")

    try:
        brand = BrandConfig.load(brand_name=args.brand)
        print(f"✓ Brand: {brand.company.name}")

        # Validate configuration
        warnings = validate_brand_config(brand)
        if warnings:
            print("\n⚠️  Configuration warnings:")
            for warning in warnings:
                print(f"   - {warning}")
            print()
    except Exception as e:
        print(f"✗ Error loading brand config: {e}")
        sys.exit(1)

    # Determine dark mode flag
    dark_mode = args.mode == 'dark'

    # Check pandoc
    ensure_pandoc_installed()

    # Get CSS path (base template for all brands)
    css_path = Path(__file__).parent / 'templates' / 'base-style.css'
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
            convert_to_branded_html(md_file, html_path, brand, css_path, dark_mode)
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

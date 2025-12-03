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

Usage:
    # Firm-scoped (recommended):
    python cli/export_branded.py --firm hypernova --deal Aalo
    python cli/export_branded.py --firm hypernova --deal Aalo --version v0.0.5 --mode dark

    # Legacy (direct path):
    python cli/export_branded.py output/Fernstone-v0.0.1/4-final-draft.md
    python cli/export_branded.py output/Fernstone-v0.0.1/4-final-draft.md --brand hypernova --mode light
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project root to path for branding module
sys.path.insert(0, str(Path(__file__).parent.parent))

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

try:
    from src.paths import resolve_deal_context, get_latest_output_dir_for_deal, DealContext
except ImportError:
    print("Error: Could not import paths module.")
    print("Make sure src/paths.py exists.")
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
    """Extract title and company name from markdown file.

    Priority order for company name:
    1. Directory name pattern: {Company}-v{version}/4-final-draft.md
    2. Explicit "Investment Memo: Company" at start of file (first 500 chars)
    3. First H1 header (# Title)
    4. Filename stem as fallback
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Priority 1: Extract from parent directory name (most reliable for our output structure)
    # Pattern: output/Company-Name-v0.0.1/4-final-draft.md -> "Company Name"
    parent_dir = md_path.parent.name
    dir_match = re.match(r'^(.+?)-v\d+\.\d+\.\d+$', parent_dir)
    if dir_match:
        company = dir_match.group(1).replace('-', ' ')
        title = f"{company} - Investment Memo"
        return title, company

    # Priority 2: Look for "Investment Memo" pattern at START of file only (first 500 chars)
    # This avoids matching text in the middle of the document
    first_500 = content[:500]
    company_match = re.search(r'^Investment Memo[:\s]+(.+?)(?:\n|$)', first_500, re.MULTILINE | re.IGNORECASE)
    if company_match:
        company = company_match.group(1).strip()
        return f"{company} - Investment Memo", company

    # Priority 3: First H1 header in first 1000 chars (avoid section headers later in doc)
    first_1000 = content[:1000]
    title_match = re.search(r'^# (.+)$', first_1000, re.MULTILINE)
    if title_match:
        title = title_match.group(1)
        # Clean up company name from title
        company = re.sub(r'\s*[-–—]\s*Investment Memo.*$', '', title, flags=re.IGNORECASE)
        return title, company

    # Priority 4: Fallback to filename
    title = md_path.stem
    company = title.replace('-', ' ').replace('_', ' ')

    return title, company


def generate_font_face_rules(brand: BrandConfig) -> str:
    """Generate @font-face rules for brand fonts.

    Args:
        brand: Brand configuration

    Returns:
        CSS @font-face declarations
    """
    font_faces = []

    # Generate body font @font-face (if custom fonts dir specified)
    if brand.fonts.custom_fonts_dir:
        font_dir = Path(brand.fonts.custom_fonts_dir)
        if font_dir.exists():
            # Look for font files
            for font_file in font_dir.glob('*'):
                if font_file.suffix.lower() in ['.woff2', '.woff', '.ttf', '.otf']:
                    # Determine font weight and style from filename
                    name_lower = font_file.stem.lower()

                    # Determine weight
                    if 'black' in name_lower or 'extrabold' in name_lower:
                        weight = 900
                    elif 'bold' in name_lower:
                        weight = 700
                    elif 'semibold' in name_lower or 'medium' in name_lower:
                        weight = 500
                    elif 'light' in name_lower or 'extralight' in name_lower:
                        weight = 300
                    else:
                        weight = 400

                    # Determine style
                    style = 'italic' if 'italic' in name_lower else 'normal'

                    # Generate @font-face rule
                    format_map = {
                        '.woff2': 'woff2',
                        '.woff': 'woff',
                        '.ttf': 'truetype',
                        '.otf': 'opentype'
                    }
                    font_format = format_map.get(font_file.suffix.lower(), 'truetype')

                    font_faces.append(f"""@font-face {{
    font-family: '{brand.fonts.family}';
    src: url('{font_file}') format('{font_format}');
    font-weight: {weight};
    font-style: {style};
    font-display: swap;
}}""")

    # Generate header font @font-face (if different from body font)
    if brand.fonts.header_family and brand.fonts.header_family != brand.fonts.family:
        if brand.fonts.header_fonts_dir:
            font_dir = Path(brand.fonts.header_fonts_dir)
            if font_dir.exists():
                for font_file in font_dir.glob('*'):
                    if font_file.suffix.lower() in ['.woff2', '.woff', '.ttf', '.otf']:
                        name_lower = font_file.stem.lower()

                        # Determine weight
                        if 'black' in name_lower or 'extrabold' in name_lower:
                            weight = 900
                        elif 'bold' in name_lower:
                            weight = 700
                        elif 'semibold' in name_lower or 'medium' in name_lower:
                            weight = 500
                        elif 'light' in name_lower or 'extralight' in name_lower:
                            weight = 300
                        else:
                            weight = 400

                        style = 'italic' if 'italic' in name_lower else 'normal'

                        format_map = {
                            '.woff2': 'woff2',
                            '.woff': 'woff',
                            '.ttf': 'truetype',
                            '.otf': 'opentype'
                        }
                        font_format = format_map.get(font_file.suffix.lower(), 'truetype')

                        font_faces.append(f"""@font-face {{
    font-family: '{brand.fonts.header_family}';
    src: url('{font_file}') format('{font_format}');
    font-weight: {weight};
    font-style: {style};
    font-display: swap;
}}""")

    return '\n\n'.join(font_faces)


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

    # Replace hardcoded Arboria @font-face declarations with brand fonts
    # Remove all Arboria @font-face blocks using regex
    css_content = re.sub(
        r'@font-face\s*\{[^}]*font-family:\s*[\'"]?Arboria[\'"]?[^}]*\}',
        '',
        css_content,
        flags=re.DOTALL
    )

    # Add brand-specific font-face rules at the beginning
    brand_font_faces = generate_font_face_rules(brand)
    if brand_font_faces:
        css_content = brand_font_faces + '\n\n' + css_content

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

    # Add font weight rules if specified
    font_weight = getattr(brand.fonts, 'weight', 400)
    header_weight = getattr(brand.fonts, 'header_weight', 700)

    font_weight_rule = f"""
/* Font Weight Override from Brand Config */
body {{
    font-weight: {font_weight};
}}
p, li, td, blockquote {{
    font-weight: {font_weight};
}}
h1, h2, h3, h4, h5, h6 {{
    font-weight: {header_weight};
}}
"""
    css_content += font_weight_rule

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
    dark_mode: bool = False,
    memo_date: str = None
) -> str:
    """Create HTML template with brand configuration.

    Args:
        title: Document title
        company: Company name
        brand: Brand configuration
        css_path: Path to base CSS file
        dark_mode: If True, apply dark mode styling
        memo_date: Optional custom date string (e.g., "January 10, 2025").
                   If None, uses today's date.
    """
    # Use custom memo_date if provided, otherwise use today's date
    if memo_date:
        # Try to parse and reformat the date if it's in a different format
        try:
            # Try common date formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%B %d, %Y', '%b %d, %Y']:
                try:
                    parsed = datetime.strptime(memo_date, fmt)
                    today = parsed.strftime("%B %d, %Y")
                    break
                except ValueError:
                    continue
            else:
                # If no format matched, use the date string as-is
                today = memo_date
        except Exception:
            today = memo_date
    else:
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
            # Check if it's a URL or local path
            if logo_path_str.startswith(('http://', 'https://')):
                # Remote URL - use img tag with preserved aspect ratio
                logo_html = f'<img src="{logo_path_str}" alt="{brand.logo.alt or brand.company.name}" style="max-width: {brand.logo.width}; height: auto; margin: 0 auto; display: block;" />'
            else:
                # Local path - check file type
                logo_path = Path(logo_path_str)
                if logo_path.exists():
                    # Check file extension
                    if logo_path.suffix.lower() == '.svg':
                        # Embed SVG directly with preserved aspect ratio
                        svg_content = embed_svg_logo(logo_path)
                        if svg_content:
                            logo_html = f'<div style="max-width: {brand.logo.width}; height: auto; margin: 0 auto;">{svg_content}</div>'
                    else:
                        # Use img tag for PNG, WEBP, JPG, etc. with preserved aspect ratio
                        logo_html = f'<img src="{logo_path_str}" alt="{brand.logo.alt or brand.company.name}" style="max-width: {brand.logo.width}; height: auto; margin: 0 auto; display: block;" />'
                else:
                    print(f"Warning: Logo file not found: {logo_path}")
    else:
        # Fallback to text with optional accent (e.g., Hypernova)
        if 'hypernova' in brand.company.name.lower():
            logo_html = 'Hypern<span class="memo-logo-accent">o</span>va'

    # Generate Google Fonts links if specified
    google_fonts_html = ""
    if brand.fonts.google_fonts_url:
        google_fonts_html += f'    <link rel="preconnect" href="https://fonts.googleapis.com">\n'
        google_fonts_html += f'    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        google_fonts_html += f'    <link href="{brand.fonts.google_fonts_url}" rel="stylesheet">\n'
    if brand.fonts.header_google_fonts_url and brand.fonts.header_google_fonts_url != brand.fonts.google_fonts_url:
        if not google_fonts_html:  # Add preconnect if not already added
            google_fonts_html += f'    <link rel="preconnect" href="https://fonts.googleapis.com">\n'
            google_fonts_html += f'    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        google_fonts_html += f'    <link href="{brand.fonts.header_google_fonts_url}" rel="stylesheet">\n'

    template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | {brand.company.name}</title>
{google_fonts_html}    <style>
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

    # Swap company trademark URLs based on mode (light <-> dark)
    with open(input_path, 'r', encoding='utf-8') as f:
        markdown_content = f.read()

    # Load company data to get trademark URLs and memo_date
    # Extract company name from path (e.g., "Terrantic-v0.0.1" -> "Terrantic")
    company_data = {}
    memo_date = None
    company_match = re.search(r'([A-Za-z0-9-]+)-v\d+\.\d+\.\d+', str(input_path))
    if company_match:
        company_name = company_match.group(1)

        # Try firm-scoped path first, then legacy
        data_file = None

        # Check if input is in io/{firm}/deals/{deal}/outputs/
        # Path like: io/hypernova/deals/Aalo/outputs/Aalo-Atomics-v0.0.5/4-final-draft.md
        io_match = re.search(r'io/([^/]+)/deals/([^/]+)/outputs/', str(input_path))
        if io_match:
            firm_name = io_match.group(1)
            deal_name = io_match.group(2)
            # Try io/{firm}/deals/{deal}/inputs/deal.json
            firm_data_file = Path(__file__).parent.parent / 'io' / firm_name / 'deals' / deal_name / 'inputs' / 'deal.json'
            if firm_data_file.exists():
                data_file = firm_data_file
            else:
                # Try io/{firm}/deals/{deal}/{deal}.json
                firm_data_file = Path(__file__).parent.parent / 'io' / firm_name / 'deals' / deal_name / f'{deal_name}.json'
                if firm_data_file.exists():
                    data_file = firm_data_file

        # Fall back to legacy data/ directory
        if not data_file:
            legacy_data_file = Path(__file__).parent.parent / 'data' / f'{company_name}.json'
            if legacy_data_file.exists():
                data_file = legacy_data_file

        if data_file:
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    company_data = json.load(f)

                # Get memo_date from company data (if specified)
                memo_date = company_data.get('memo_date')
                if memo_date:
                    print(f"  Using custom memo date: {memo_date}")

                # Get trademark URLs from company data
                trademark_light = company_data.get('trademark_light')
                trademark_dark = company_data.get('trademark_dark')

                if trademark_light and trademark_dark:
                    if dark_mode:
                        # Swap light mode URL to dark mode URL
                        markdown_content = markdown_content.replace(trademark_light, trademark_dark)
                    else:
                        # Swap dark mode URL to light mode URL
                        markdown_content = markdown_content.replace(trademark_dark, trademark_light)
            except Exception as e:
                # If loading company data fails, continue without URL swapping
                pass

    # Also handle local file path trademarks (legacy)
    if dark_mode:
        # Swap light mode trademark paths to dark mode
        markdown_content = markdown_content.replace(
            'trademark__Avalanche--Light-Mode',
            'trademark__Avalanche--Dark-Mode'
        )
        markdown_content = markdown_content.replace(
            'trademark__TheoryForge--Light-Mode',
            'trademark__TheoryForge--Dark-Mode'
        )
    else:
        # Swap dark mode trademark paths to light mode
        markdown_content = markdown_content.replace(
            'trademark__Avalanche--Dark-Mode',
            'trademark__Avalanche--Light-Mode'
        )
        markdown_content = markdown_content.replace(
            'trademark__TheoryForge--Dark-Mode',
            'trademark__TheoryForge--Light-Mode'
        )

    # Extract metadata BEFORE stripping H1 (we need the title for the HTML header)
    # Write temp file first for extract_title_from_markdown
    temp_input_path = input_path.parent / f".temp_input_{input_path.stem}.md"
    with open(temp_input_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    title, company = extract_title_from_markdown(temp_input_path)

    # Now strip redundant H1 title from markdown (HTML template already provides header)
    # Pattern: "# Investment Memo: CompanyName" or "# CompanyName" at start of file
    markdown_content = re.sub(
        r'^#\s+(?:Investment Memo[:\s]*)?[^\n]+\n+',
        '',
        markdown_content,
        count=1  # Only remove the first H1
    )

    # Save modified markdown (with H1 stripped) to temp file
    with open(temp_input_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    # Create HTML template (with optional custom memo_date from company data)
    template = create_html_template(title, company, brand, css_path, dark_mode, memo_date)

    # Save template to temp file
    template_path = output_path.parent / f".temp_template_{output_path.stem}.html"
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(template)

    def _normalize_table_col_widths(html: str) -> str:
        """Normalize <colgroup> widths so each column shares the width equally.

        This avoids odd, uneven scorecard tables unless a future template
        explicitly overrides them. For each <colgroup>, we count the <col>
        elements and assign width = 100 / n % to each.
        """
        import re

        def repl(match: re.Match) -> str:
            colgroup = match.group(0)
            cols = re.findall(r"<col\b[^>]*>", colgroup)
            n = len(cols)
            if n == 0:
                return colgroup
            width = 100.0 / n
            new_cols = []
            for col in cols:
                # Remove any existing style="width: ..." fragments
                col_clean = re.sub(r"style=\"[^\"]*\"", "", col)
                # Ensure a single style attribute with width percentage
                if col_clean.endswith("/>"):
                    col_clean = col_clean[:-2].rstrip()
                    col_clean += f" style=\"width: {width:.6f}%\" />"
                elif col_clean.endswith(">"):
                    col_clean = col_clean[:-1].rstrip()
                    col_clean += f" style=\"width: {width:.6f}%\">"
                new_cols.append(col_clean)

            inner = "".join(new_cols)
            return f"<colgroup>{inner}</colgroup>"

        return re.sub(r"<colgroup>.*?</colgroup>", repl, html, flags=re.DOTALL | re.IGNORECASE)

    try:
        # Convert using pypandoc with custom template
        pypandoc.convert_file(
            str(temp_input_path),
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

        # Post-process: normalize table column widths so columns are even by default
        try:
            html_text = output_path.read_text(encoding='utf-8')
            normalized_html = _normalize_table_col_widths(html_text)
            output_path.write_text(normalized_html, encoding='utf-8')
        except Exception as e:
            print(f"  Warning: Could not normalize table column widths: {e}")

        # Post-process: Restore uncited footnotes that Pandoc excluded
        try:
            import subprocess
            restore_script = Path(__file__).parent / 'utils' / 'restore_uncited_footnotes.py'
            if restore_script.exists():
                result = subprocess.run(
                    [sys.executable, str(restore_script), str(output_path), str(temp_input_path)],
                    capture_output=True, text=True
                )
                if result.stdout:
                    print(f"  {result.stdout.strip()}")
        except Exception as e:
            print(f"  Warning: Could not restore uncited footnotes: {e}")

        # Post-process: Fix duplicate citations (Obsidian-style)
        try:
            fix_script = Path(__file__).parent / 'utils' / 'fix_citations.py'
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
        # Clean up temp files
        if template_path.exists():
            template_path.unlink()
        if temp_input_path.exists():
            temp_input_path.unlink()


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
  # Firm-scoped (recommended):
  %(prog)s --firm hypernova --deal Aalo     # Export latest version
  %(prog)s --firm hypernova --deal Aalo --version v0.0.5  # Specific version

  # Legacy (direct path):
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
        nargs='?',
        help='Input markdown file or directory. Optional if --firm and --deal are provided.'
    )

    parser.add_argument(
        '--firm',
        type=str,
        help='Firm name for firm-scoped IO (e.g., "hypernova"). Uses io/{firm}/deals/{deal}/'
    )

    parser.add_argument(
        '--deal',
        type=str,
        help='Deal name when using --firm. Required if --firm is provided.'
    )

    parser.add_argument(
        '--version',
        type=str,
        help='Specific version (e.g., "v0.0.1"). If not specified, uses latest.'
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

    # Check for MEMO_DEFAULT_FIRM environment variable if --firm not provided
    if not args.firm:
        args.firm = os.environ.get("MEMO_DEFAULT_FIRM")

    # Validate arguments
    # --deal is only required when --firm is provided AND no input file is given
    if args.firm and not args.deal and not args.input:
        print("Error: --deal is required when --firm is provided without an input path")
        sys.exit(1)

    if not args.input and not (args.firm and args.deal):
        print("Error: Either provide an input path or use --firm and --deal")
        sys.exit(1)

    # Resolve input file from firm/deal if provided (only if no direct input)
    deal_context = None
    if args.firm and args.deal:
        deal_context = resolve_deal_context(args.deal, firm=args.firm)

        if not deal_context.outputs_dir or not deal_context.outputs_dir.exists():
            print(f"Error: Outputs directory not found for {args.firm}/{args.deal}")
            print(f"  Expected: {deal_context.outputs_dir}")
            sys.exit(1)

        if args.version:
            artifact_dir = deal_context.get_version_output_dir(args.version)
        else:
            try:
                artifact_dir = get_latest_output_dir_for_deal(deal_context)
            except FileNotFoundError as e:
                print(f"Error: {e}")
                sys.exit(1)

        if not artifact_dir.exists():
            print(f"Error: Artifact directory not found: {artifact_dir}")
            sys.exit(1)

        # Set input to the final draft in the artifact directory
        args.input = artifact_dir / "4-final-draft.md"
        if not args.input.exists():
            # Try alternative memo filename
            memo_files = list(artifact_dir.glob("*-memo.md"))
            if memo_files:
                args.input = memo_files[0]
            else:
                print(f"Error: No memo file found in {artifact_dir}")
                print("  Expected: 4-final-draft.md or *-memo.md")
                sys.exit(1)

        print(f"Resolved: {args.input}")

        # Set default output to firm-scoped exports directory if not specified
        if args.output == Path('exports/branded'):
            args.output = deal_context.exports_dir / args.mode
            args.output.mkdir(parents=True, exist_ok=True)

    # Auto-detect firm-scoped paths from input file when --firm not explicitly provided
    # Pattern: io/{firm}/deals/{deal}/outputs/... or io/{firm}/deals/{deal}/...
    elif args.input and args.output == Path('exports/branded'):
        input_str = str(args.input.absolute())
        io_match = re.search(r'/io/([^/]+)/deals/([^/]+)/', input_str)
        if io_match:
            detected_firm = io_match.group(1)
            detected_deal = io_match.group(2)

            # Set firm if not already set (for brand config lookup)
            if not args.firm:
                args.firm = detected_firm

            # Create firm-scoped exports directory
            exports_dir = Path('io') / detected_firm / 'deals' / detected_deal / 'exports' / args.mode
            exports_dir.mkdir(parents=True, exist_ok=True)
            args.output = exports_dir
            print(f"Auto-detected firm-scoped path: {detected_firm}/{detected_deal}")
            print(f"  Exporting to: {args.output}")

    # Load brand configuration
    print(f"\n{'='*60}")
    print("BRANDED MEMO EXPORTER")
    print(f"{'='*60}\n")

    try:
        # Pass firm to BrandConfig.load for firm-scoped config lookup
        brand = BrandConfig.load(brand_name=args.brand, firm=args.firm)
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
    css_path = Path(__file__).parent.parent / 'templates' / 'base-style.css'
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

            # Auto-version if file exists (add .1, .2, etc.)
            if html_path.exists():
                base_name = output_name
                version = 1
                # Check for existing versions like Name-v0.0.2.1.html, Name-v0.0.2.2.html
                while html_path.exists():
                    html_path = args.output / f"{base_name}.{version}.html"
                    version += 1
                output_name = f"{base_name}.{version - 1}"
                print(f"  → File exists, using versioned name: {html_path.name}")

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

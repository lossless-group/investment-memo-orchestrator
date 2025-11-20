# Brand Configuration Guide

This directory contains brand configuration files for customizing investment memo exports with your brand identity.

## Quick Start

1. **Create a brand config file**: Copy `brand-example-config.yaml` to `brand-<your-brand>-config.yaml`
2. **Customize colors, fonts, and logos**: Edit the YAML file with your brand details
3. **Export with your brand**: `python export-branded.py memo.md --brand <your-brand> --pdf`

## Brand Config Structure

```yaml
company:
  name: "Your Company Name"
  tagline: "Your company tagline or motto"
  confidential_footer: "This document is confidential and proprietary to {company_name}."

colors:
  primary: "#1a3a52"          # Main brand color (headers, accents)
  secondary: "#1dd3d3"        # Secondary color (links, highlights)
  text_dark: "#1a2332"        # Primary text color
  text_light: "#6b7280"       # Secondary/muted text
  background: "#ffffff"       # Page background
  background_alt: "#f0f0eb"   # Alternate backgrounds (callouts, code blocks)

fonts:
  family: "Your Brand Font"
  fallback: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  custom_fonts_dir: "templates/fonts/YourFont"  # Optional: path to custom fonts

logo:
  # SVG logos for different themes (optional)
  light_mode: "templates/trademarks/your-brand--light.svg"
  dark_mode: "templates/trademarks/your-brand--dark.svg"
  width: "180px"              # Logo width in header
  height: "60px"              # Logo height in header
  alt: "Your Company Name"

layout:
  max_width: "800px"          # Maximum content width
  page_margins: "40mm 25mm"   # Top/bottom left/right margins for PDF

branding:
  show_header: true           # Show branded header
  show_footer: true           # Show confidential footer
  header_style: "minimal"     # Header style: minimal, full

metadata:
  author: "Your Company Investment Team"
  confidentiality: "Confidential and Proprietary"
```

## Logo Configuration

The system supports theme-specific logos (SVG format recommended):

### Option 1: Theme-Specific Logos (Recommended)

Use different logos for light and dark mode exports:

```yaml
logo:
  light_mode: "templates/trademarks/brand-name--light.svg"
  dark_mode: "templates/trademarks/brand-name--dark.svg"
  width: "180px"
  height: "60px"
  alt: "Brand Name"
```

**Directory structure:**
```
templates/
  trademarks/
    trademark__BrandName--Light-Mode.svg
    trademark__BrandName--Dark-Mode.svg
```

**Benefits:**
- Light mode logo: Optimized for white/light backgrounds
- Dark mode logo: Optimized for dark backgrounds with white/light text
- SVG format: Scales perfectly at any size, small file size

### Option 2: Text-Based Logo (Fallback)

If no logo files are specified, the system will use a text-based logo with your company name:

```yaml
company:
  name: "Your Company"

# No logo section needed - will use text-based logo
```

### Option 3: Single Logo

Use the same logo for both themes:

```yaml
logo:
  light_mode: "templates/trademarks/brand-logo.svg"
  dark_mode: "templates/trademarks/brand-logo.svg"
  width: "180px"
  height: "60px"
```

## Custom Fonts

Place custom font files (`.woff2` format) in `templates/fonts/YourFont/`:

```
templates/
  fonts/
    YourFont/
      YourFont-Regular.woff2
      YourFont-Medium.woff2
      YourFont-Bold.woff2
      YourFont-Italic.woff2
```

Then reference in config:

```yaml
fonts:
  family: "Your Font Name"
  custom_fonts_dir: "templates/fonts/YourFont"
```

## Export Examples

### Export with specific brand (dark mode)
```bash
python export-branded.py memo.md --brand mac --pdf
```

### Export with specific brand (light mode)
```bash
python export-branded.py memo.md --brand mac --mode light --pdf
```

### Export all memos in a directory
```bash
python export-branded.py output/ --brand mac --all --pdf
```

## Color Guidelines

### Primary Color
- Used for: Main headers (H1, H2), brand accents, header background
- Choose: Your main brand color
- Example: `#1a3a52` (Navy blue)

### Secondary Color
- Used for: Links, highlights, accents, underlines
- Choose: A complementary accent color
- Example: `#1dd3d3` (Cyan)

### Text Colors
- `text_dark`: Main body text, headings
- `text_light`: Muted text, metadata, secondary info

### Backgrounds
- `background`: Main page background
- `background_alt`: Code blocks, callouts, alternate sections

## Available Brands

Current brand configurations:

- **Default** (`brand-config.yaml`): Hypernova Capital
- **MaC** (`brand-mac-config.yaml`): MaC Venture Capital
- **Collide** (`brand-collide-config.yaml`): Collide Capital

## Creating a New Brand

1. Copy example config:
   ```bash
   cp templates/brand-configs/brand-mac-config.yaml templates/brand-configs/brand-yourname-config.yaml
   ```

2. Edit the file with your brand details

3. Add logos (optional):
   ```bash
   # Add your SVG logos
   templates/trademarks/trademark__YourName--Light-Mode.svg
   templates/trademarks/trademark__YourName--Dark-Mode.svg
   ```

4. Add custom fonts (optional):
   ```bash
   mkdir templates/fonts/YourFont
   # Add .woff2 font files
   ```

5. Test the export:
   ```bash
   python export-branded.py output/CompanyName-v0.0.1/4-final-draft.md --brand yourname --pdf
   ```

## Troubleshooting

### Logo not showing
- Verify logo file path is correct relative to project root
- Check file exists: `ls templates/trademarks/your-logo.svg`
- Ensure SVG file is valid XML
- Check export console output for warnings

### Fonts not loading
- Verify `custom_fonts_dir` path exists
- Ensure `.woff2` font files are in the directory
- Check font family name matches font file names
- WOFF2 is the recommended format for web fonts

### Colors not applying
- Verify hex color format: `#RRGGBB` or `#RGB`
- Check YAML syntax (proper indentation, quotes)
- Run validation: `python -c "from src.branding import BrandConfig; BrandConfig.load(brand_name='yourname')"`

## Theme Modes

### Dark Mode (Default)
- Dark background (`primary` color)
- Light text on dark background
- Best for: Modern, tech-focused aesthetic
- Uses `logo.dark_mode` SVG

### Light Mode
- Light background (`background` color)
- Dark text on light background
- Best for: Traditional, professional aesthetic
- Uses `logo.light_mode` SVG

Export with `--mode light` or `--mode dark` flag.

## Company Trademarks (In Memo Content)

In addition to the VC firm logo in the header, you can also insert the target company's logo/trademark within the memo content itself.

### Configuration

Add trademark paths to the company's data file (`data/{CompanyName}.json`):

```json
{
  "type": "fund",
  "mode": "justify",
  "description": "Company description...",
  "url": "https://company.com",
  "trademark_light": "https://company.com/logo-light.svg",
  "trademark_dark": "https://company.com/logo-dark.svg",
  "notes": "Research focus..."
}
```

### How It Works

1. The **trademark enrichment agent** automatically inserts the company logo after the header metadata section
2. For **fund memos**: Inserted after the "Date:" line
3. For **direct investment memos**: Inserted after the company metadata
4. The logo renders as a figure with caption

### Example Output

```markdown
**Date**: November 19, 2025

![Theory Forge Ventures Logo](https://theoryforge.vc/logo.svg)

---

## 1. Executive Summary
...
```

### Trademark Sources

- **URLs**: Use direct URLs to company logos (e.g., from company website)
- **Local files**: Use relative paths from project root (e.g., `templates/trademarks/company-logo.svg`)

### Theme Support

- Light mode exports use `trademark_light`
- Dark mode exports use `trademark_dark`
- If only one is provided, it's used for both themes

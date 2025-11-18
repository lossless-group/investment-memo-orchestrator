# Custom Branding Guide

Complete guide to customizing memo exports with your firm's branding.

## Overview

The investment memo orchestrator supports **multiple brand configurations** in a single installation. This means you can:
- Create branded exports for your own firm
- Manage multiple VC firm clients from one installation
- Switch between brands with a simple command-line flag

## Quick Start

### 1. Create Your Brand Configuration

Copy the example configuration:
```bash
cp templates/brand-configs/brand-config.example.yaml templates/brand-configs/brand-yourfirm-config.yaml
```

### 2. Customize the Configuration

Edit `templates/brand-configs/brand-yourfirm-config.yaml` with your firm's details:

```yaml
company:
  name: "Your VC Firm Name"
  tagline: "Your firm's tagline"
  confidential_footer: "This document is confidential..."

colors:
  primary: "#2c3e50"          # Your brand's primary color
  secondary: "#3498db"        # Accent color
  text_dark: "#333333"        # Main text
  text_light: "#777777"       # Secondary text
  background: "#ffffff"       # Page background
  background_alt: "#f8f8f8"   # Alternate background

fonts:
  family: "Inter"             # Font name
  fallback: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  custom_fonts_dir: null      # Path to custom fonts, or null for system fonts
```

### 3. Export with Your Brand

```bash
python export-branded.py memo.md --brand yourfirm
```

That's it! Your memo will be exported with your firm's branding.

## Configuration Options

### Company Information

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Firm name (appears in header, footer, metadata) | "Accel" |
| `tagline` | Mission or tagline (appears below logo) | "Early stage venture capital" |
| `confidential_footer` | Legal disclaimer. Use `{company_name}` placeholder | "Confidential - {company_name}" |

### Colors

All colors must be in hex format (`#RRGGBB`):

| Field | Purpose | Used For |
|-------|---------|----------|
| `primary` | Main brand color | Headers, logo background (light mode), page background (dark mode) |
| `secondary` | Accent color | Links, highlights, borders, logo accents |
| `text_dark` | Primary text | Main body text, headings |
| `text_light` | Secondary text | Metadata, captions, subtle text |
| `background` | Page background | Page background in light mode |
| `background_alt` | Alternate background | Code blocks, callouts, tables |

**Tip:** Use a color picker tool (like [ColorZilla](https://www.colorzilla.com/)) to extract hex codes from your brand guidelines.

### Fonts

| Field | Description | Example |
|-------|-------------|---------|
| `family` | Primary font name | "Inter", "Georgia", "Arboria" |
| `fallback` | Fallback font stack | "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" |
| `custom_fonts_dir` | Path to WOFF2 files, or `null` for system fonts | "templates/fonts" or `null` |

## Using Custom Fonts

### Option 1: System Fonts (Easiest)

Use web-safe fonts that work everywhere:

```yaml
fonts:
  family: "Georgia"
  fallback: "Times New Roman, serif"
  custom_fonts_dir: null
```

Recommended system fonts:
- **Georgia** - Classic serif
- **Inter** - Modern sans-serif (available on most systems)
- **Arial** or **Helvetica** - Universal sans-serif
- **Times New Roman** - Traditional serif

### Option 2: Custom Font Files

If you have custom brand fonts:

1. **Convert fonts to WOFF2 format**
   - WOFF2 is the most efficient web font format
   - Use tools like [CloudConvert](https://cloudconvert.com/) to convert from TTF/OTF

2. **Organize font files**
   ```
   templates/fonts/YourFont/
   ├── YourFont_Book.woff2
   ├── YourFont_Medium.woff2
   ├── YourFont_Bold.woff2
   └── YourFont_Italic.woff2
   ```

3. **Update configuration**
   ```yaml
   fonts:
     family: "YourFont"
     fallback: "-apple-system, sans-serif"
     custom_fonts_dir: "templates/fonts/YourFont"
   ```

## Multiple Brands Management

### Naming Convention

Store brand configurations in `templates/brand-configs/` as `brand-<name>-config.yaml`:

```
templates/brand-configs/
├── brand-hypernova-config.yaml
├── brand-accel-config.yaml
├── brand-sequoia-config.yaml
└── brand-a16z-config.yaml
```

### Using Different Brands

```bash
# Export with Hypernova branding
python export-branded.py memo.md --brand hypernova -o exports/hypernova/

# Export with Accel branding
python export-branded.py memo.md --brand accel -o exports/accel/

# Export with Sequoia branding
python export-branded.py memo.md --brand sequoia -o exports/sequoia/
```

### Default Brand

Create `brand-config.yaml` (no name suffix) for your default brand:

```bash
# Will use brand-config.yaml by default
python export-branded.py memo.md

# Explicitly specify brand
python export-branded.py memo.md --brand hypernova
```

## Color Schemes

### Light Mode vs. Dark Mode

All brand configurations work in both light and dark modes:

```bash
# Light mode (default)
python export-branded.py memo.md --brand accel

# Dark mode
python export-branded.py memo.md --brand accel --mode dark
```

The same color palette adapts automatically - primary/secondary colors swap roles between light and dark modes.

### Choosing Colors

**For professional VC memos:**
- Primary: Dark, professional color (navy, dark blue, charcoal)
- Secondary: Bright accent for highlights (cyan, orange, teal)
- Text: High contrast for readability (#333 or darker)
- Background: White or very light gray (#fff, #f8f8f8)

**Examples:**

| Firm Style | Primary | Secondary | Use Case |
|------------|---------|-----------|----------|
| Traditional | `#1a3a52` (Navy) | `#1dd3d3` (Cyan) | Conservative, trustworthy |
| Modern | `#2c3e50` (Slate) | `#3498db` (Blue) | Clean, professional |
| Bold | `#0066CC` (Blue) | `#FF6B35` (Orange) | Energetic, innovative |
| Minimal | `#1a1a1a` (Black) | `#666666` (Gray) | Elegant, understated |

## Examples

### Example 1: Minimal Configuration (System Fonts)

```yaml
company:
  name: "Venture Partners"
  tagline: "Investing in great founders"
  confidential_footer: "Confidential - {company_name}"

colors:
  primary: "#2c3e50"
  secondary: "#3498db"
  text_dark: "#333333"
  text_light: "#777777"
  background: "#ffffff"
  background_alt: "#f8f8f8"

fonts:
  family: "Georgia"
  fallback: "Times New Roman, serif"
  custom_fonts_dir: null
```

Usage:
```bash
cp templates/brand-configs/brand-config.example.yaml templates/brand-configs/brand-venturepartners-config.yaml
# Edit the file with your details
python export-branded.py memo.md --brand venturepartners
```

### Example 2: Full Configuration (Custom Fonts)

```yaml
company:
  name: "Hypernova Capital"
  tagline: "Network-Driven | High-impact | Transformative venture fund"
  confidential_footer: "This document is confidential and proprietary to {company_name}."

colors:
  primary: "#1a3a52"          # Navy
  secondary: "#1dd3d3"        # Cyan
  text_dark: "#1a2332"
  text_light: "#6b7280"
  background: "#ffffff"
  background_alt: "#f0f0eb"

fonts:
  family: "Arboria"
  fallback: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  custom_fonts_dir: "templates/fonts"
```

## Testing Your Branding

### 1. Validate Configuration

Test that your config loads correctly:

```bash
python -c "from src.branding import BrandConfig; config = BrandConfig.load(brand_name='yourfirm'); print(f'✓ Brand: {config.company.name}')"
```

### 2. Generate Test Export

```bash
python export-branded.py output/test-memo.md --brand yourfirm -o exports/test/
```

### 3. Preview in Browser

Open the generated HTML file to see your branding:

```bash
open exports/test/test-memo.html
```

### 4. Test Both Modes

```bash
# Light mode
python export-branded.py memo.md --brand yourfirm --mode light

# Dark mode
python export-branded.py memo.md --brand yourfirm --mode dark
```

### 5. Iterate on Colors

Adjust colors in your config file and regenerate until you're satisfied with the appearance.

## Troubleshooting

### "Brand config not found" Error

**Problem:** `FileNotFoundError: Brand config not found: templates/brand-configs/brand-xyz-config.yaml`

**Solution:**
- Check the file is in `templates/brand-configs/` directory
- Check the filename matches exactly: `brand-<name>-config.yaml`
- Use the correct name with `--brand <name>` (without "brand-" prefix or ".yaml" extension)

Example:
```bash
# File: templates/brand-configs/brand-accel-config.yaml
# Command: --brand accel  ✓
# NOT: --brand brand-accel-config.yaml  ✗
```

### Colors Not Applying

**Problem:** Colors in the exported HTML don't match your configuration

**Solutions:**
- Ensure hex codes start with `#`
- Use 6-digit format: `#1a3a52` (not `#1a3` or `1a3a52`)
- Validate hex format: all characters must be 0-9 or a-f

### Custom Fonts Not Loading

**Problem:** Exports fall back to system fonts instead of your custom fonts

**Solutions:**

1. **Check font files exist:**
   ```bash
   ls templates/fonts/YourFont/
   ```
   Should show `.woff2` files

2. **Check file naming:**
   Files should match pattern: `{FontName}_Book.woff2`, `{FontName}_Bold.woff2`, etc.

3. **Verify path in config:**
   ```yaml
   custom_fonts_dir: "templates/fonts/YourFont"  # Must match actual directory
   ```

4. **Convert fonts to WOFF2:**
   Only WOFF2 format is supported. Convert from TTF/OTF using online tools.

### Logo Not Showing Correctly

**Problem:** Logo text doesn't display or format correctly

**Note:** The logo accent feature (colored letter) only works for "Hypernova" by default.

For other brands, the logo will display the full company name without special formatting.

To customize logo HTML, edit `export-branded.py:140-141`.

### Configuration Validation Warnings

The exporter shows warnings for common issues:

```
⚠️  Configuration warnings:
   - Invalid color 'primary': not-a-color (should be hex format like #1a3a52)
   - Custom fonts directory not found: bad/path
   - No .woff2 font files found in: templates/fonts
```

These are **warnings**, not errors. The export will still work, but may not look as intended.

## Advanced Customization

### Custom Footer Text

Use `{company_name}` placeholder for dynamic text:

```yaml
confidential_footer: "© 2025 {company_name}. All rights reserved. This memo is confidential."
```

### Multiple Taglines

Use the pipe character `|` to separate tagline sections:

```yaml
tagline: "Early Stage | Deep Tech | Global Reach"
```

### Color Palette Tools

Generate professional color palettes:
- [Coolors](https://coolors.co/) - Color palette generator
- [Adobe Color](https://color.adobe.com/) - Color wheel and harmonies
- [Paletton](https://paletton.com/) - Color scheme designer

### Accessibility Considerations

Ensure good contrast ratios for readability:
- Text on background: minimum 4.5:1 contrast ratio
- Large text (18pt+): minimum 3:1 contrast ratio
- Test with [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)

## Command Reference

### Basic Export
```bash
python export-branded.py <input> --brand <name>
```

### Export Options
```bash
python export-branded.py memo.md \
  --brand accel \              # Brand configuration to use
  --mode dark \                # Color mode: light (default) or dark
  --pdf \                      # Also generate PDF
  -o exports/accel/            # Output directory
```

### Batch Export
```bash
# Export all memos with Accel branding
python export-branded.py output/ --all --brand accel -o exports/accel/
```

### Export with Both Modes
```bash
# Light mode
python export-branded.py memo.md --brand accel --mode light -o exports/accel/light/

# Dark mode
python export-branded.py memo.md --brand accel --mode dark -o exports/accel/dark/
```

## Best Practices

1. **Version control your configs:** Store brand configurations in git (configs are in `templates/brand-configs/`)
2. **Test both modes:** Always test light and dark mode exports
3. **Use consistent naming:** Follow `brand-<name>-config.yaml` pattern in `templates/brand-configs/` directory
4. **Document custom colors:** Add comments in YAML explaining color choices
5. **Keep fallback fonts:** Always specify fallback fonts for reliability
6. **Validate before sharing:** Review exports before sending to clients

## Support

For issues or questions:
- Check [Troubleshooting](#troubleshooting) section above
- Review [Examples](#examples) for working configurations
- Validate your YAML syntax with a YAML linter
- File an issue on GitHub with your configuration (redact sensitive info)

## Related Documentation

- [Export Guide](../exports/EXPORT-GUIDE.md) - General export features
- [Dark Mode Guide](../exports/DARK-MODE-GUIDE.md) - Light vs dark mode details
- [Citation Guide](../exports/CITATION-IMPROVEMENTS.md) - Citation formatting

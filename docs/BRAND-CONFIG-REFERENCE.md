# Brand Configuration Reference

Quick reference for understanding how colors and fonts work in brand configurations.

## How Colors Work: Light Mode vs Dark Mode

### Single Color Palette

You only define **one set of colors** that automatically adapts between modes:

```yaml
colors:
  primary: "#1a1a1a"          # Black
  secondary: "#8B5CF6"        # Purple
  text_dark: "#111111"        # Near black
  text_light: "#6b7280"       # Gray
  background: "#ffffff"       # White
  background_alt: "#f9fafb"   # Light gray
```

### Automatic Mode Adaptation

**Light Mode:**
- `primary` → Headers, logo, primary elements
- `secondary` → Accents, links, borders (stays same in both modes)
- `text_dark` → Main body text
- `text_light` → Subtle text, metadata
- `background` → Page background
- `background_alt` → Callouts, code blocks

**Dark Mode:**
- `primary` → **Page background** (role reversal!)
- `secondary` → Accents, links (same as light mode)
- `text_dark` → Becomes light/inverted
- `text_light` → Becomes brighter
- `background` → **Text color** (role reversal!)
- `background_alt` → Darker shade for contrast

### The CSS handles the swapping

The `--mode dark` flag adds a `.dark-mode` class to the HTML body, and the CSS rules automatically:
- Swap primary ↔ background
- Invert text colors
- Adjust contrast for readability

### Tips for Choosing Colors

1. **Primary**: Choose a dark color (navy, charcoal, black) that works as:
   - Headers in light mode
   - Background in dark mode

2. **Secondary**: Choose a vibrant accent that works on both light and dark backgrounds:
   - Good: Cyan (`#1dd3d3`), Purple (`#8B5CF6`), Orange (`#FF6B35`)
   - Avoid: Light pastels (poor contrast on white)

3. **Test both modes:**
   ```bash
   # Light mode
   python export-branded.py memo.md --brand yourfirm --mode light

   # Dark mode
   python export-branded.py memo.md --brand yourfirm --mode dark
   ```

## Custom Fonts with Relative Paths

### Basic Setup (Single Font)

```yaml
fonts:
  family: "Inter"
  fallback: "-apple-system, sans-serif"
  custom_fonts_dir: null  # Use system font
```

### Custom Font Files

**Step 1: Organize your font files**

Place WOFF2 files in `templates/fonts/`:

```
templates/fonts/
├── GeneralSans/
│   └── Fonts/
│       └── WEB/
│           └── fonts/
│               ├── GeneralSans-Regular.woff2
│               ├── GeneralSans-Bold.woff2
│               └── GeneralSans-Medium.woff2
└── Ranade/
    └── Fonts/
        └── WEB/
            └── fonts/
                ├── Ranade-Regular.woff2
                └── Ranade-Bold.woff2
```

**Step 2: Use relative paths from project root**

```yaml
fonts:
  family: "GeneralSans"
  fallback: "-apple-system, sans-serif"
  custom_fonts_dir: "templates/fonts/GeneralSans/Fonts/WEB/fonts"
```

### Separate Header and Body Fonts

Use different fonts for headers vs body text:

```yaml
fonts:
  # Body text (paragraphs, lists, general content)
  family: "GeneralSans"
  fallback: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  custom_fonts_dir: "templates/fonts/GeneralSans/Fonts/WEB/fonts"

  # Headers (h1-h6, titles, logo)
  header_family: "Ranade"
  header_fallback: "Georgia, serif"
  header_fonts_dir: "templates/fonts/Ranade/Fonts/WEB/fonts"
```

**What uses header fonts:**
- All headings: `h1`, `h2`, `h3`, `h4`, `h5`, `h6`
- Memo title (company name)
- Memo subtitle ("Investment Memo")
- Logo text
- Section headers

**What uses body fonts:**
- Paragraphs
- Lists (bullet and numbered)
- Tables
- Blockquotes
- Code blocks
- All other text content

### Font File Requirements

**Format:** Only WOFF2 supported (most efficient web font format)

**Convert other formats:**
- Use [CloudConvert](https://cloudconvert.com/) to convert TTF/OTF → WOFF2
- Or use [Font Squirrel](https://www.fontsquirrel.com/tools/webfont-generator)

**Naming:** Files can have any name, but should include:
- Regular/Book weight
- Bold weight (for headers)
- Medium weight (optional)
- Italic variants (optional)

### Path Resolution

All paths are **relative to the project root** (where you run the export command):

```yaml
# ✓ Correct (relative from project root)
custom_fonts_dir: "templates/fonts/MyFont"

# ✗ Wrong (absolute paths not recommended)
custom_fonts_dir: "/Users/you/project/templates/fonts/MyFont"

# ✗ Wrong (missing subdirectories)
custom_fonts_dir: "templates/fonts"  # If fonts are in templates/fonts/MyFont/Fonts/WEB/fonts
```

**Finding the right path:**

```bash
# From project root, find your font files
find templates/fonts -name "*.woff2"

# Example output:
# templates/fonts/GeneralSans/Fonts/WEB/fonts/GeneralSans-Medium.woff2
# templates/fonts/Ranade/Fonts/WEB/fonts/Ranade-Bold.woff2

# Use the directory path (without the filename):
custom_fonts_dir: "templates/fonts/GeneralSans/Fonts/WEB/fonts"
```

## Validation

### Test Your Config

```bash
# Validate configuration loads correctly
python -c "from src.branding import BrandConfig; config = BrandConfig.load(brand_name='yourfirm'); print(f'✓ Brand: {config.company.name}')"

# Check for warnings
python export-branded.py memo.md --brand yourfirm
```

### Common Warnings

**"Body font directory not found"**
- Check path is relative from project root
- Verify directory exists: `ls templates/fonts/YourFont`

**"No .woff2 font files found"**
- Ensure files are WOFF2 format (not TTF/OTF)
- Check files are in the exact directory specified
- Use `find` command to locate files

**No warnings = Success!**
- Font files found and will be embedded in HTML
- Export will use your custom fonts

## Complete Example: Collide Capital

```yaml
company:
  name: "Collide Capital"
  tagline: "Guiding founders on their institutional capital journey"
  confidential_footer: "This document is confidential and proprietary to {company_name}."

colors:
  # Light mode: Uses these directly
  # Dark mode: Primary/background swap, text inverts
  primary: "#1a1a1a"          # Black → headers in light, bg in dark
  secondary: "#8B5CF6"        # Purple → accents in both modes
  text_dark: "#111111"        # Near black text
  text_light: "#6b7280"       # Gray text
  background: "#ffffff"       # White bg in light, text in dark
  background_alt: "#f9fafb"   # Light gray

fonts:
  # Body text
  family: "GeneralSans"
  fallback: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  custom_fonts_dir: "templates/fonts/GeneralSans/Fonts/WEB/fonts"

  # Headers
  header_family: "Ranade"
  header_fallback: "Georgia, serif"
  header_fonts_dir: "templates/fonts/Ranade/Fonts/WEB/fonts"
```

**Usage:**

```bash
# Light mode with custom fonts
python export-branded.py memo.md --brand collide

# Dark mode with custom fonts
python export-branded.py memo.md --brand collide --mode dark

# Verify no font warnings
python export-branded.py memo.md --brand collide 2>&1 | grep -i warning
# (Should only see pandoc warnings about external resources, not font warnings)
```

## Troubleshooting

### Fonts Not Loading

**Problem:** Fonts fall back to system defaults

**Solutions:**
1. Check path is correct: `ls <custom_fonts_dir>`
2. Verify WOFF2 files exist: `find <custom_fonts_dir> -name "*.woff2"`
3. Use absolute path temporarily to test: `ls -la /full/path/to/fonts`
4. Check permissions: Files must be readable

### Colors Look Wrong in Dark Mode

**Problem:** Text is hard to read in dark mode

**Solutions:**
1. Ensure `primary` is dark (for light mode headers)
2. Ensure `background` is light (for light mode bg)
3. Choose vibrant `secondary` that works on both backgrounds
4. Test both modes before finalizing

### Different Fonts Not Showing

**Problem:** Headers use same font as body

**Solutions:**
1. Verify `header_family` is set (not `null`)
2. Check `header_fonts_dir` path exists
3. Clear browser cache and reload HTML
4. Inspect HTML with browser dev tools to see if CSS rule is applied

## Quick Reference Table

| Field | Purpose | Example | Notes |
|-------|---------|---------|-------|
| `primary` | Main brand color | `#1a3a52` | Dark color recommended |
| `secondary` | Accent color | `#1dd3d3` | Works on light & dark |
| `text_dark` | Primary text | `#111111` | Near black |
| `text_light` | Secondary text | `#6b7280` | Gray |
| `background` | Page background | `#ffffff` | White/light |
| `background_alt` | Alt background | `#f0f0eb` | Light gray |
| `family` | Body font | `"Inter"` | Font name |
| `custom_fonts_dir` | Body font path | `"templates/fonts/Inter"` | Relative path |
| `header_family` | Header font | `"Ranade"` | Optional |
| `header_fonts_dir` | Header font path | `"templates/fonts/Ranade/Fonts/WEB/fonts"` | Optional |

## See Also

- [Custom Branding Guide](CUSTOM-BRANDING.md) - Complete branding documentation
- [Export Guide](../exports/EXPORT-GUIDE.md) - Export command reference
- [Dark Mode Guide](../exports/DARK-MODE-GUIDE.md) - Light vs dark mode details

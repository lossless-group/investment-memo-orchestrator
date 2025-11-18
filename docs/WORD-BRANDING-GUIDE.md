# Word Document Branding Guide

**Goal**: Create a branded Word reference document (`templates/hypernova-reference.docx`) that applies Hypernova Capital styling to all Word exports.

**Time Required**: ~30 minutes

---

## Step 1: Create a New Word Document

1. Open Microsoft Word
2. Create a new blank document
3. **Save immediately as**: `hypernova-reference.docx`
   - Location: `templates/` folder in your project
   - Format: Word Document (.docx)

---

## Step 2: Set Up Custom Styles

### Apply Hypernova Colors

**Color Palette** (from `hypernova-style.css`):
- **Navy**: RGB(26, 58, 82) or Hex #1a3a52
- **Cyan**: RGB(29, 211, 211) or Hex #1dd3d3
- **Dark Gray**: RGB(26, 35, 50) or Hex #1a2332
- **Light Gray**: RGB(107, 114, 128) or Hex #6b7280

### Configure Heading Styles

**Heading 1**:
1. Type "Heading 1 Sample" and select it
2. In the ribbon: **Home** → **Styles** → Right-click "Heading 1" → **Modify**
3. Set:
   - **Font**: Arboria (if available) or Calibri
   - **Size**: 20pt
   - **Color**: Navy (#1a3a52)
   - **Bold**: Yes
   - Click **Format** → **Paragraph**:
     - Space Before: 24pt
     - Space After: 12pt
     - Border (bottom): 3pt solid, Cyan (#1dd3d3)

**Heading 2**:
1. Type "Heading 2 Sample" and select it
2. Right-click "Heading 2" in Styles → **Modify**
3. Set:
   - **Font**: Arboria or Calibri
   - **Size**: 16pt
   - **Color**: Navy (#1a3a52)
   - **Bold**: Yes
   - Space Before: 18pt, After: 10pt

**Heading 3**:
1. Right-click "Heading 3" → **Modify**
2. Set:
   - **Font**: Arboria or Calibri
   - **Size**: 14pt
   - **Color**: Navy (#1a3a52)
   - **Semi-bold**: Yes
   - Space Before: 12pt, After: 8pt

**Heading 4**:
1. Right-click "Heading 4" → **Modify**
2. Set:
   - **Font**: Arboria or Calibri
   - **Size**: 12pt
   - **Color**: Dark Gray (#1a2332)
   - **Bold**: Yes

---

## Step 3: Configure Body Text Styles

**Normal (Body Text)**:
1. Right-click "Normal" style → **Modify**
2. Set:
   - **Font**: Arboria or Calibri
   - **Size**: 11pt
   - **Color**: Dark Gray (#1a2332)
   - **Line Spacing**: 1.5 lines
   - **Alignment**: Justified
   - Space After: 6pt

**Hyperlink**:
1. Right-click "Hyperlink" style → **Modify**
2. Set:
   - **Color**: Cyan (#1dd3d3)
   - **Underline**: None (or subtle)

---

## Step 4: Create Custom Table Style

1. Insert a sample table: **Insert** → **Table** (3 columns × 3 rows)
2. Select the table
3. **Table Design** → **Table Styles** → **New Table Style**
4. Name: "Hypernova Table"
5. Configure:
   - **Header Row**:
     - Background: Navy (#1a3a52)
     - Text: White
     - Bold: Yes
   - **Body Rows**:
     - Border: 1pt Light Gray
     - Alternate rows: Light gray background (#f0f0eb)
   - **Borders**:
     - Outer: 2pt Cyan (#1dd3d3)
     - Inner: 1pt Light Gray

6. Click **OK**
7. Delete the sample table

---

## Step 5: Add Header and Footer

### Header Setup

1. **Insert** → **Header** → **Blank**
2. In the header area:
   - **Left side**: Type "Hypernova Capital"
     - Font: Arboria Bold or Calibri Bold, 10pt
     - Color: Navy (#1a3a52)
   - **Right side**: Insert **Field** → **Title** (will auto-populate from document title)
     - Font: Arboria or Calibri, 10pt
     - Color: Light Gray (#6b7280)
3. Add a **bottom border**:
   - Select header text → **Home** → **Borders** → **Bottom Border**
   - Color: Cyan (#1dd3d3), 1pt

### Footer Setup

1. **Insert** → **Footer** → **Blank**
2. Create three sections (use Tab key):
   - **Left**: "Confidential"
   - **Center**: **Insert** → **Page Number** → **Current Position** → **Plain Number**
   - **Right**: "Network-Driven | High-impact | Transformative"
3. Format:
   - Font: Arboria or Calibri, 9pt
   - Color: Light Gray (#6b7280)
   - Italics for "Confidential"
4. Add **top border**:
   - Select footer → **Borders** → **Top Border**
   - Color: Cyan (#1dd3d3), 1pt

5. Click **Close Header and Footer**

---

## Step 6: Configure Page Layout

1. **Layout** → **Size** → **Letter** (8.5" × 11")
2. **Layout** → **Margins** → **Custom Margins**:
   - Top: 0.75"
   - Bottom: 0.75"
   - Left: 1"
   - Right: 1"
   - Header: 0.5"
   - Footer: 0.5"

---

## Step 7: Create Custom List Styles

### Bulleted List

1. Create a bullet point and select it
2. **Home** → **Bullets** → **Define New Bullet**
3. Choose:
   - **Symbol**: • (bullet)
   - **Color**: Cyan (#1dd3d3)
   - **Size**: Same as text
4. Right-click "List Bullet" style → **Modify**:
   - Indent: 0.25"
   - Space After: 6pt

### Numbered List

1. Create a numbered list
2. Right-click "List Number" style → **Modify**
3. Set:
   - **Number color**: Navy (#1a3a52)
   - **Number format**: 1., 2., 3.
   - **Bold**: Yes

---

## Step 8: Add Sample Content (Optional)

To verify styles, add sample content representing common elements:

```markdown
# Sample Heading 1

This is normal body text with proper spacing and justification.

## Sample Heading 2

- Bullet point one with cyan bullet
- Bullet point two
- Bullet point three

### Sample Heading 3

1. Numbered item one
2. Numbered item two
3. Numbered item three

This is a [hyperlink](https://example.com) in cyan.

| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| Data 4   | Data 5   | Data 6   |
```

After verifying styles look good, **delete all content** (leave the document blank).

---

## Step 9: Save the Reference Document

1. **File** → **Save As**
2. Location: `templates/hypernova-reference.docx`
3. Format: **Word Document (.docx)**
4. Click **Save**

**Important**: The reference document should be **empty** or contain only a paragraph mark. Pandoc uses it only for styles, not content.

---

## Step 10: Test with Your Memo

Now test the reference document with the KearnyJackson memo:

```bash
# Navigate to project directory
cd /Users/mpstaton/code/lossless-monorepo/ai-labs/investment-memo-orchestrator

# Convert with reference document
python md2docx.py output/KearnyJackson_Memo.md \
  --reference-doc templates/hypernova-reference.docx \
  -o exports/KearnyJackson_Branded.docx

# Open the result
open exports/KearnyJackson_Branded.docx
```

---

## Expected Results

✅ **Headings**: Navy color with cyan underline (H1)
✅ **Body text**: Dark gray, justified, proper spacing
✅ **Links**: Cyan color
✅ **Tables**: Navy headers, cyan borders
✅ **Header**: "Hypernova Capital" | Document title
✅ **Footer**: "Confidential" | Page # | Tagline
✅ **Lists**: Cyan bullets, navy numbers

---

## Troubleshooting

**Problem**: Fonts don't match exactly
- **Solution**: If Arboria isn't installed, use Calibri as fallback. Word will apply what's available.

**Problem**: Colors look different
- **Solution**: Ensure you're using RGB values, not approximate colors. Word's color picker may need manual RGB entry.

**Problem**: Header/footer don't show
- **Solution**: Check **Header & Footer Tools** → **Options** → "Different First Page" is unchecked

**Problem**: Tables don't style correctly
- **Solution**: Ensure table style is set as default: Right-click "Hypernova Table" → **Set as Default**

**Problem**: Borders/spacing look wrong
- **Solution**: Check **Layout** → **Paragraph** spacing settings for each style

---

## Quick Reference: Hypernova Brand Colors (for Word)

| Element | Color Name | RGB | Hex |
|---------|------------|-----|-----|
| Headings | Navy | 26, 58, 82 | #1a3a52 |
| Accents | Cyan | 29, 211, 211 | #1dd3d3 |
| Body Text | Dark Gray | 26, 35, 50 | #1a2332 |
| Metadata | Light Gray | 107, 114, 128 | #6b7280 |
| White | White | 255, 255, 255 | #ffffff |
| Cream | Cream | 240, 240, 235 | #f0f0eb |

---

## Next Steps

Once you have a working reference document:

1. **Update md2docx.py** to use it by default
2. **Create brand-config.yaml** support (future) to generate reference docs automatically
3. **Document in README** how to use `--reference-doc` flag

---

## Advanced: Creating Multiple Reference Documents

If you want variations (e.g., for different funds or themes):

```bash
# Create variants
templates/hypernova-reference.docx       # Default
templates/hypernova-dark-reference.docx  # Dark theme (if needed)
templates/custom-brand-reference.docx    # Custom branding
```

Use with:
```bash
python md2docx.py memo.md --reference-doc templates/custom-brand-reference.docx
```

---

**Need Help?**
- Word Style Guide: https://support.microsoft.com/en-us/office/customize-or-create-new-styles
- Pandoc Reference Doc: https://pandoc.org/MANUAL.html#option--reference-doc

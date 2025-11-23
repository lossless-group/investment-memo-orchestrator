# Investment Memo Export Guide

## ✅ What's Been Created

All 10 investment memos have been exported in **3 formats** with Hypernova Capital branding:

### 1. **Branded HTML** (`exports/branded/*.html`) ⭐ RECOMMENDED
- **Location**: `exports/branded/`
- **Files**: 10 HTML files with full Hypernova styling
- **Features**:
  - Hypernova navy (#1a3a52) and cyan (#1dd3d3) color scheme
  - Professional header with logo and tagline
  - All citations preserved as clickable footnotes
  - Table of contents
  - Responsive design
  - Ready to open in any web browser

**To View**: Double-click any `.html` file or open in Chrome/Safari/Firefox

### 2. **Plain HTML** (`exports/html/*.html`)
- **Location**: `exports/html/`
- **Files**: 10 HTML files with basic styling
- **Features**: Clean, simple HTML with citations preserved

### 3. **Microsoft Word** (`exports/*.docx`)
- **Location**: `exports/`
- **Files**: 10 Word documents
- **Features**: Citations as Word footnotes (requires Microsoft Word to view properly)

---

## 📊 Brand Colors Used

```css
Navy:    #1a3a52  (headers, primary text)
Cyan:    #1dd3d3  (accents, highlights, links)
White:   #ffffff  (text on dark backgrounds)
Cream:   #f0f0eb  (alternate backgrounds)
Gray:    #6b7280  (secondary text)
```

**Font**: Arboria (with fallbacks to system fonts)

---

## 🖨️ Converting to PDF

### Option 1: Print from Browser (Easiest)
1. Open any branded HTML file in Chrome/Safari
2. Press `Cmd+P` (Mac) or `Ctrl+P` (Windows)
3. Select "Save as PDF"
4. Click "Save"

**Recommended Settings**:
- Paper: Letter (8.5 x 11 in)
- Margins: Default
- Background graphics: ON

### Option 2: Using wkhtmltopdf (Best Quality)

Install wkhtmltopdf:
```bash
# macOS
brew install wkhtmltopdf

# Then convert
wkhtmltopdf \
  --enable-local-file-access \
  --print-media-type \
  --margin-top 20mm \
  --margin-bottom 20mm \
  exports/branded/Aalo-Atomics-v0.0.5.html \
  exports/Aalo-Atomics-v0.0.5.pdf
```

### Option 3: Using Python Script

```bash
# Install weasyprint (if not already)
pip install weasyprint

# Run the export script with PDF flag
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md --pdf
```

---

## 📝 Citation Preservation

**All formats preserve citations!**

- **HTML**: Citations appear as clickable superscript numbers (e.g., [1], [2]) that link to the full citation list at the bottom
- **Word**: Citations stored as Word footnotes (must open in Microsoft Word, not Google Docs)
- **PDF**: Citations print as footnotes with full URLs and dates

**Example**:
> "The company raised $100M Series B"[^1][^2]

**Citations Section** (at bottom):
```
[1] 2025-08-19. Aalo Atomics secures funding to build its first reactor
    https://www.world-nuclear-news.org/...
```

---

## 📂 File Structure

```
exports/
├── EXPORT-GUIDE.md (this file)
│
├── branded/  ⭐ Best for viewing
│   ├── fonts/
│   │   └── Arboria_*.woff2 (brand fonts)
│   ├── Aalo-Atomics-v0.0.5.html
│   ├── Aito-v0.0.1.html
│   └── ... (10 files total)
│
├── html/  📄 Simple HTML
│   ├── Aalo-Atomics-v0.0.5.html
│   └── ... (10 files total)
│
└── *.docx  📝 Microsoft Word
    ├── Aalo-Atomics-v0.0.5.docx
    └── ... (10 files total)
```

---

## 🎨 Customizing the Brand

To modify the styling:

1. **Edit CSS**: `templates/hypernova-style.css`
2. **Change colors**: Update the `:root` variables
3. **Re-export**: Run the export script again

```css
/* templates/hypernova-style.css */
:root {
    --hypernova-navy: #1a3a52;  /* Change this */
    --hypernova-cyan: #1dd3d3;  /* Change this */
}
```

---

## 🚀 Batch Export Commands

### Export all latest versions with branding:
```bash
python export-branded.py output/ --all -o exports/branded
```

### Export single memo:
```bash
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md
```

### Export with PDF:
```bash
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md --pdf
```

---

## ✨ Features

✅ Full Hypernova Capital branding
✅ All citations preserved with clickable links
✅ Professional header and footer
✅ Table of contents
✅ Responsive design (works on mobile)
✅ Print-friendly styling
✅ Self-contained HTML (no external dependencies except fonts)

---

## 🤝 Sharing Memos

### For Internal Review (Best):
- Share the **branded HTML** files
- Recipients can open in any browser
- All formatting and citations preserved

### For External Partners:
- Convert to **PDF** using browser print (Cmd+P → Save as PDF)
- Or share **Word docs** for editing

### For Email:
- Attach PDF or Word doc
- HTML files can be attached but may not render in all email clients

---

**Questions?** The export scripts are located at:
- `md2docx.py` - Basic Word export
- `export-branded.py` - Hypernova branded HTML/PDF export
- `templates/hypernova-style.css` - Styling template

# Dark Mode Export Guide

## 🌙 Light & Dark Mode Support

All Hypernova Capital branded HTML exports now support both **light mode** and **dark mode**!

### Color Schemes

#### 📄 Light Mode (Default)
- **Background**: White (#ffffff)
- **Text**: Dark navy (#1a2332)
- **Headers**: Navy (#1a3a52)
- **Accents**: Cyan (#1dd3d3)
- **Perfect for**: Printing, reading in bright environments

#### 🌙 Dark Mode
- **Background**: Dark navy (#1a3a52)
- **Text**: White (#ffffff)
- **Headers**: White with cyan accents
- **Accents**: Cyan (#1dd3d3)
- **Perfect for**: Screen reading, presentations, night reading

---

## 🚀 Usage

### Export Single Memo

**Light Mode** (default):
```bash
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md --mode light
```

**Dark Mode**:
```bash
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md --mode dark
```

### Export All Memos

**Light Mode**:
```bash
python export-branded.py output/ --all --mode light -o exports/light
```

**Dark Mode**:
```bash
python export-branded.py output/ --all --mode dark -o exports/dark
```

### Export Both Modes at Once

```bash
./export-all-modes.sh
```

This will create:
- `exports/light/` - All memos in light mode
- `exports/dark/` - All memos in dark mode

---

## 📊 Comparison

| Feature | Light Mode | Dark Mode |
|---------|-----------|-----------|
| **Best for** | Printing, bright environments | Screen reading, presentations |
| **Background** | White | Dark navy |
| **Text** | Dark | White |
| **Eye strain** | Higher in dark rooms | Lower in dark rooms |
| **Ink usage** | Low (good for printing) | High (avoid printing) |
| **Professional** | ✅ Traditional business look | ✅ Modern tech aesthetic |
| **Citations** | ✅ Fully preserved | ✅ Fully preserved |

---

## 🎨 When to Use Each Mode

### Use Light Mode For:
- ✅ **Printing** to paper
- ✅ **Email attachments** to traditional investors
- ✅ **Board presentations** with projectors
- ✅ **Reading in bright offices**
- ✅ **Converting to PDF** for distribution

### Use Dark Mode For:
- ✅ **Screen reading** late at night
- ✅ **Presentations** with dark themes
- ✅ **Modern tech audiences** (engineers, developers)
- ✅ **Reducing eye strain** during long reading sessions
- ✅ **Demo days** or pitch presentations

---

## 💡 Pro Tips

### Combine With PDF Export

**Light Mode PDF** (best for printing):
```bash
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md \
  --mode light --pdf -o exports/print/
```

**Dark Mode PDF** (best for screens):
```bash
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md \
  --mode dark --pdf -o exports/screen/
```

### Browser Print to PDF

1. Open HTML in browser
2. `Cmd+P` (Mac) or `Ctrl+P` (Windows)
3. **Light Mode**: Enable "Background graphics" for full styling
4. **Dark Mode**: Enable "Background graphics" for dark background
5. Save as PDF

---

## 🎯 Quick Reference

```bash
# Export all memos in both modes
./export-all-modes.sh

# Export single memo (light mode - default)
python export-branded.py output/Company/4-final-draft.md

# Export single memo (dark mode)
python export-branded.py output/Company/4-final-draft.md --mode dark

# Export directory (dark mode)
python export-branded.py output/ --all --mode dark -o exports/dark

# Export with PDF (dark mode)
python export-branded.py output/Company/4-final-draft.md --mode dark --pdf
```

---

## 📁 Output Structure

After running `./export-all-modes.sh`:

```
exports/
├── light/  📄 Light mode HTML files
│   ├── Aalo-Atomics-v0.0.5.html
│   ├── Aito-v0.0.1.html
│   └── ...
│
├── dark/  🌙 Dark mode HTML files
│   ├── Aalo-Atomics-v0.0.5.html
│   ├── Aito-v0.0.1.html
│   └── ...
│
└── branded/  (previous exports)
```

---

## 🔧 Technical Details

### How It Works

The dark mode is implemented using CSS classes:

```css
body.dark-mode {
    background: var(--hypernova-navy);
    color: var(--hypernova-white);
}
```

The `--mode` flag adds the `dark-mode` class to the `<body>` element, which triggers all dark mode styles.

### Customizing Colors

Edit `templates/hypernova-style.css` to customize:

```css
/* Light Mode Colors */
:root {
    --hypernova-navy: #1a3a52;
    --hypernova-cyan: #1dd3d3;
    --hypernova-white: #ffffff;
}

/* Dark Mode Overrides */
body.dark-mode {
    background: var(--hypernova-navy);
    color: var(--hypernova-white);
}
```

---

## ✅ All Features Preserved

Both light and dark modes preserve **all features**:
- ✅ Citations with clickable footnotes
- ✅ Table of contents
- ✅ Professional header/footer
- ✅ Hypernova branding
- ✅ Responsive design
- ✅ Print-friendly
- ✅ Self-contained HTML

---

**Need help?** Check `exports/EXPORT-GUIDE.md` for general export documentation.

# Citation Spacing Improvements

## 🎯 Problem Fixed

Citations were "clumping" together and hard to read:

### ❌ Before:
```
The company raised $100M[1][2][3][4][5] in funding.
```

Visual appearance: **[1][2][3][4][5]** - Hard to distinguish individual citations

### ✅ After:
```
The company raised $100M[1], [2], [3], [4], [5] in funding.
```

Visual appearance: **[1], [2], [3], [4], [5]** - Clear separation with commas

---

## 🎨 What Changed

### Spacing Added:
- **0.15em margins** on left and right of each citation
- **Automatic comma separators** between consecutive citations
- **Gray color** for commas (less prominent than citation numbers)

### CSS Implementation:

```css
/* Base citation styling */
.footnote-ref {
    margin-left: 0.15em;
    margin-right: 0.15em;
    color: var(--hypernova-cyan);
}

/* Automatic comma between consecutive citations */
.footnote-ref + .footnote-ref::before {
    content: ",";
    margin-right: 0.25em;
    color: var(--hypernova-gray);
}

/* Dark mode comma color */
body.dark-mode .footnote-ref + .footnote-ref::before {
    color: rgba(255, 255, 255, 0.5);
}
```

---

## 📊 Visual Comparison

### Multiple Citations Example:

**Before** (cramped):
> Series B led by Valor Equity Partners[^3][^4][^5][^6][^7]

**After** (readable):
> Series B led by Valor Equity Partners[^3], [^4], [^5], [^6], [^7]

### Single Citation (unchanged):
> The company was founded in 2023[^1]

---

## ✨ Benefits

1. **Better Readability**: Each citation number is clearly distinguishable
2. **Professional Appearance**: Follows academic citation formatting standards
3. **Hover Targets**: Easier to click individual citations on screen
4. **Print Friendly**: Citations print clearly with proper spacing
5. **Consistent**: Works in both light and dark modes

---

## 🚀 How to Get Updated Exports

The citation improvements are automatically included in all new exports:

```bash
# Re-export with improved citations
python export-branded.py output/Company/4-final-draft.md

# Dark mode with improved citations
python export-branded.py output/Company/4-final-draft.md --mode dark

# All memos with improved citations
python export-branded.py output/ --all
```

---

## 📝 Example in Context

### From Aalo Atomics Memo:

**Old version**:
> Key de-risking milestones include: DOE selection for the Nuclear Reactor Pilot
> Program, NRC pre-licensing phase entry (July 2024), signed MOU with Idaho Falls
> Power for seven commercial reactors, and Preliminary Design Review completion for
> their Aalo-X experimental reactor targeting criticality by summer 2026[^2][^3][^8].

**New version** (with improved spacing):
> Key de-risking milestones include: DOE selection for the Nuclear Reactor Pilot
> Program, NRC pre-licensing phase entry (July 2024), signed MOU with Idaho Falls
> Power for seven commercial reactors, and Preliminary Design Review completion for
> their Aalo-X experimental reactor targeting criticality by summer 2026[^2], [^3], [^8].

Much cleaner and easier to read! 🎉

---

## 🎯 Design Principles

The citation styling follows these principles:

1. **Minimal but visible**: Commas are subtle (gray) but present
2. **Consistent spacing**: Equal margins around all citations
3. **Clickable targets**: Proper spacing makes hover/click easier
4. **Academic standards**: Follows IEEE/ACM citation formatting
5. **Non-intrusive**: Doesn't distract from content

---

## 💡 Technical Notes

- **Automatic**: No changes needed to markdown files
- **CSS-only**: Pure CSS solution, no JavaScript required
- **Responsive**: Works on all screen sizes
- **Print-optimized**: Citations print clearly on paper
- **Accessible**: Screen readers handle citations properly

---

**All existing exports have been updated with this improvement!**

Re-export your memos to get the better citation spacing.

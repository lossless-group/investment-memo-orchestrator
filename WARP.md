# Investment Memo Orchestrator - Warp Terminal Quick Reference

Quick command reference for generating professional investment memos with AI.

---

## ⚠️ CRITICAL: Use `uv` NOT `pip`

**This project uses `uv` for dependency management. NEVER use `pip` directly.**

```bash
# ❌ WRONG - DO NOT USE
pip install -r requirements.txt

# ✅ CORRECT - ALWAYS USE
uv pip install -r requirements.txt
```

**If you don't have `uv` installed:**
```bash
# macOS/Linux (Homebrew)
brew install uv

# Or install script
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 🚀 Initial Setup

**IMPORTANT: Follow these steps exactly in order.**

```bash
# 1. Install uv (if not already installed)
brew install uv

# 2. Create virtual environment with uv
uv venv --python python3.11

# 3. Activate environment
source .venv/bin/activate

# 4. Install dependencies with uv (NOT pip!)
uv pip install -r requirements.txt

# 5. Configure API keys
cp .env.example .env
# Edit .env with your keys (required: ANTHROPIC_API_KEY, optional: PERPLEXITY_API_KEY, TAVILY_API_KEY)
```

**Verify Installation:**
```bash
source .venv/bin/activate
python -m src.main --help
```

---

## 📝 Generate Memos

### Basic Command
```bash
# Activate venv first (always!)
source .venv/bin/activate

# Generate memo (defaults: direct investment, prospective analysis)
python -m src.main "Company Name"
```

### Direct Investment Examples
```bash
# Prospective analysis (evaluating potential investment)
python -m src.main "Aalo Atomics" --type direct --mode consider

# Retrospective justification (existing investment)
python -m src.main "TheoryForge" --type direct --mode justify
```

### Fund Commitment Examples
```bash
# LP commitment analysis (prospective)
python -m src.main "Class5 Global" --type fund --mode consider

# LP commitment justification (retrospective)
python -m src.main "Avalanche Fund IV" --type fund --mode justify
```

---

## 🎨 Export to Branded HTML/PDF

```bash
# Export with default brand
python export-branded.py output/Company-v0.0.X/4-final-draft.md

# Export with specific brand (dark mode)
python export-branded.py output/Company-v0.0.X/4-final-draft.md --brand hypernova --mode dark

# Export with specific brand (light mode)
python export-branded.py output/Company-v0.0.X/4-final-draft.md --brand avalanche --mode light

# Convert HTML to PDF
./html-to-pdf.sh exports/branded/Company-v0.0.X.html
```

---

## 🔧 Improve Individual Sections

```bash
# Improve specific section (uses Perplexity Sonar Pro for real-time research)
python improve-section.py "Avalanche" "Team"

# Improve with specific version
python improve-section.py "Avalanche" "Market Context" --version v0.0.1

# Available sections:
# - "Executive Summary"
# - "Business Overview"
# - "Market Context"
# - "Team"
# - "Technology & Product"
# - "Traction & Milestones"
# - "Funding & Terms"
# - "Risks & Mitigations"
# - "Investment Thesis"
# - "Recommendation"
```

---

## 📁 Company Data Files (Optional)

Create `data/{CompanyName}.json` for pre-configured context:

```json
{
  "type": "direct",
  "mode": "consider",
  "description": "Brief company description",
  "url": "https://company.com",
  "stage": "Series A",
  "deck": "data/CompanyName-deck.pdf",
  "trademark_light": "https://company.com/logo-light.svg",
  "trademark_dark": "https://company.com/logo-dark.svg",
  "notes": "Research focus areas"
}
```

**Then run:**
```bash
python -m src.main "CompanyName"
# Automatically uses settings from data/CompanyName.json
```

---

## 🔑 Command Arguments Reference

### Main Command: `python -m src.main`

| Argument | Options | Default | Description |
|----------|---------|---------|-------------|
| `company_name` | Any string | - | **Required**: Company or fund name |
| `--type` | `direct`, `fund` | `direct` | Investment type |
| `--mode` | `consider`, `justify` | `consider` | Memo mode |

### Export Command: `python export-branded.py`

| Argument | Options | Default | Description |
|----------|---------|---------|-------------|
| `memo_path` | File path | - | **Required**: Path to markdown memo |
| `--brand` | Brand name | `hypernova` | Brand config to use |
| `--mode` | `light`, `dark` | `light` | Color theme |

---

## 📂 Output Structure

Each memo generates a versioned directory:

```
output/
└── Company-Name-v0.0.X/
    ├── 0-deck-analysis.json        # Pitch deck extraction
    ├── 0-deck-analysis.md
    ├── 1-research/                 # Section research with citations
    │   ├── 01-executive-summary-research.md
    │   ├── 02-business-overview-research.md
    │   └── ... (10 sections)
    ├── 2-sections/                 # Polished section drafts
    │   ├── 01-executive-summary.md
    │   ├── 02-business-overview.md
    │   └── ... (10 sections)
    ├── 3-validation.json           # Quality scores
    ├── 3-validation.md
    ├── 4-final-draft.md           # Complete memo with citations
    └── state.json                  # Full workflow state
```

---

## 🛠️ Troubleshooting

### Dependencies Keep Disappearing
```bash
# Always use uv (NOT pip)
source .venv/bin/activate
uv pip install -r requirements.txt
```

### API Key Issues
```bash
# Check your .env file has:
ANTHROPIC_API_KEY=sk-ant-...           # Required
PERPLEXITY_API_KEY=pplx-...           # Optional (recommended for citations)
TAVILY_API_KEY=tvly-...               # Optional (for web search)
```

### Permission Errors on Scripts
```bash
# Make scripts executable
chmod +x html-to-pdf.sh
chmod +x md-to-pdf.sh
chmod +x export-all-modes.sh
```

### "Module not found" Errors
```bash
# Reinstall in editable mode
source .venv/bin/activate
uv pip install -e .
```

---

## 🎯 Common Workflows

### Complete Memo Generation
```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Generate memo
python -m src.main "Aalo Atomics" --type direct --mode consider

# 3. Export to HTML/PDF
python export-branded.py output/Aalo-Atomics-v0.0.1/4-final-draft.md --brand hypernova --mode dark
./html-to-pdf.sh exports/branded/Aalo-Atomics-v0.0.1.html

# 4. Open PDF
open exports/branded/Aalo-Atomics-v0.0.1.pdf
```

### Improve Weak Section
```bash
source .venv/bin/activate

# Improve section (adds citations automatically)
python improve-section.py "Aalo Atomics" "Team"

# Re-export with improvements
python export-branded.py output/Aalo-Atomics-v0.0.1/4-final-draft.md --brand hypernova --mode dark
```

### Batch Export All Memos
```bash
source .venv/bin/activate

# Export all memos in both light and dark modes
./export-all-modes.sh
```

---

## 📖 Key Features

- **Perplexity Section Research**: Real-time web research with 5-10 citations per section
- **Outline System**: YAML-based content structure with guiding questions
- **Section-by-Section Processing**: Avoids API timeouts, processes 10 sections individually
- **Citation Preservation**: Citations added during research, preserved through polishing
- **Multi-Brand Export**: Support for multiple VC firm branding configurations
- **Quality Validation**: 0-10 scoring with actionable feedback

---

## 🔗 Additional Resources

- **Full Documentation**: `README.md`
- **User Guide**: `CASUAL_USER_GUIDE.md`
- **Branding Setup**: `docs/CUSTOM-BRANDING.md`
- **Recent Changes**: `changelog/2025-11-21_02.md`

---

## 💡 Pro Tips

1. **Always activate venv first**: `source .venv/bin/activate`
2. **Use company data files**: Pre-configure settings in `data/{Company}.json`
3. **Check output quality**: Review `3-validation.md` for scores and feedback
4. **Improve weak sections**: Use `improve-section.py` instead of regenerating entire memo
5. **Set PERPLEXITY_API_KEY**: Dramatically improves citation quality (5-10 sources per section)
6. **Use dark mode for presentations**: `--mode dark` looks professional on projectors

---

## 🐛 Report Issues

Found a bug? Have feedback?
- GitHub Issues: [https://github.com/anthropics/claude-code/issues](https://github.com/anthropics/claude-code/issues)
- Email: [support contact]

---

**Version**: 1.0 (2025-11-21)
**Powered by**: Claude Sonnet 4.5, LangGraph, Perplexity Sonar Pro

# Investment Memo Orchestrator

Multi-agent orchestration system for generating high-quality investment memos using LangGraph and specialized AI agents.

**Status**: Production-Ready with Section-by-Section Processing ✅

Sponsored by [Hypernova Capital](https://www.hypernova.capital)

### Similar Services
Many people may not want to manage using an Open Source library and deal with the command line.  These are services we have found that can provide similar Investment Memo Generation.

#### Dedicated Private Markets AI Platforms
- [Deck](https://www.hellodeck.ai/)
- [Deliverables](https://deliverables.ai/)
- [Blueflame AI](https://www.blueflame.ai/)
- [Pascal AI](https://www.pascalailabs.com/)

#### General AI Automation Platforms with Blueprints or Templates
- [Lyzr | Investment Memo Blueprint](https://www.lyzr.ai/blueprints/venture-capital/investment-memo-generator-agent/)
- [v7 Labs | Investment Memo Automations](https://www.v7labs.com/automations/ai-investment-memo-generation)
- [Stack AI | Investment Memo Generator Template](https://www.stack-ai.com/blog/how-to-build-an-investment-memo-generator)
- [Bash | Investment Memo Template](https://www.getbash.com/templates/investment-memo)

## Recent Updates

### 2025-11-26: Dataroom Analyzer Agent System

**New multi-agent dataroom analyzer** for processing investment datarooms containing diverse document types (pitch decks, financials, battlecards, etc.). The system scans, classifies, and extracts structured data from dataroom documents.

**Phase 1 - Document Scanning & Classification** ✅
- Three-stage classification: directory-based → filename pattern → LLM fallback
- Supports 12+ document types (pitch_deck, cap_table, competitive_analysis, etc.)
- Confidence scoring with classification reasoning

**Phase 2 - Specialized Extractors** (4/5 Complete)
- [x] Competitive Extractor - Synthesizes battlecards into unified competitive landscape
- [x] Cap Table Extractor - Ownership structure, shareholders, option pools
- [x] Financial Extractor - P&L, projections, key metrics from CSV/Excel
- [x] Traction Extractor - Customer counts, ARR/MRR, retention, pipeline, partnerships
- [ ] Team Extractor - Team bios and backgrounds

**Output Structure:**
```
output/Company-v0.0.1/
├── 0-dataroom-inventory.json/md    # Document inventory
├── 1-competitive-analysis.json/md  # Competitive landscape
├── 2-cap-table.json/md             # Ownership structure
├── 3-financial-analysis.json/md    # Financial projections
├── 4-traction-analysis.json/md     # Customers & traction metrics
└── (future) 5-team-analysis.json/md
```

See `changelog/2025-11-26_01.md` through `changelog/2025-11-26_04.md` for complete details.

### 2025-11-22: Premium Data Sources Integration

**Perplexity @ Syntax Integration**: Research queries now automatically target premium data sources using Perplexity's `@source` syntax. All 20 outline sections (direct + fund) have section-specific source preferences that ensure high-quality research from authoritative sources like @crunchbase, @pitchbook, @statista, and @cbinsights. This prevents low-quality filler content from generic benchmark sites. See `changelog/2025-11-22_02.md` for complete details.

**Key Benefits:**
- ✅ 80-90% authoritative sources (up from 50-70%)
- ✅ Section-specific source targeting (Market Context uses @statista, Team uses @linkedin, etc.)
- ✅ Automatic source aggregation (8 premium sources from 5 key sections)
- ✅ Zero additional cost (uses existing Perplexity API)

### 2025-11-20: Section-by-Section Processing

**Major architecture refactor**: The system now processes sections individually throughout the entire pipeline, eliminating API timeout issues and ensuring consistent citation formatting. All enrichment agents work on section files rather than assembled content. See `changelog/2025-11-20_01.md` for complete details.

### Outstanding Issues

  - Ongoing need for reactivating venv and reinstalling dependencies, despite having done so already.

## Overview

This system uses a supervisor pattern with specialized AI agents to generate investment memos that match Hypernova Capital's analytical standards. Instead of a single AI prompt, it coordinates multiple expert agents that research, write, enrich, cite, validate, and iterate on memos using **section-by-section processing** to avoid timeouts and maintain quality.

## Key Features

### Core Commands
```bash
python3.11 -m src.main "Class5 Global" --type fund --mode justify
```

### Multi-Agent Architecture (Section-by-Section Processing)
- **Deck Analyst Agent**: Extracts key information from pitch deck PDFs (team, metrics, market sizing) and creates initial section drafts
- **Research Agent**: Actively searches the web (Tavily/Perplexity) for company information, funding data, team backgrounds, and market context
- **Writer Agent**: Writes 10 sections individually, saving each to `2-sections/` directory (~5k chars per section instead of 50k+ char full memo)
- **Trademark Enrichment**: Creates header file with company logo/trademark (if provided)
- **Socials Enrichment**: Adds LinkedIn profile links to team members in Team section file
- **Link Enrichment**: Processes each section file to add organization/entity hyperlinks
- **Citation-Enrichment Agent**: Loads each section file, enriches with Perplexity Sonar Pro citations, renumbers globally, consolidates into ONE citation block
- **Citation Validator Agent**: Validates citation accuracy, checking dates, duplicates, broken links
- **Validator Agent**: Rigorously evaluates quality (0-10 scale) with specific, actionable feedback
- **Supervisor**: Orchestrates workflow, manages state, routes to revision or finalization

**Key Architecture Change**: All enrichment agents now process individual section files rather than the full assembled memo, eliminating API timeout issues and ensuring consistent citation formatting.

### Web Search Integration with Premium Source Targeting
- **Premium data sources**: Research queries enhanced with Perplexity `@source` syntax (@crunchbase, @pitchbook, @statista, @cbinsights)
- **Section-specific sources**: Each memo section targets appropriate authoritative sources (e.g., Market Context uses @statista, Team uses @linkedin)
- **Automatic aggregation**: 8 premium sources aggregated from 5 key sections for comprehensive coverage
- **Quality control**: Prevents low-quality filler from benchmark sites and SEO spam
- **Multi-query strategy**: Company overview, funding, team, news with targeted source selection
- **Real-time research**: Tavily API or Perplexity Sonar Pro API
- **Fallback mode**: Claude-only mode (no API keys required for testing)

### Artifact Trail System
- **Complete transparency**: Every workflow step saves artifacts to output directory
- **Research artifacts**: `1-research.json` (structured data) and `1-research.md` (human-readable summary)
- **Section drafts**: Individual section files in `2-sections/` (all 10 sections as separate .md files)
- **Validation reports**: `3-validation.json` (scores/feedback) and `3-validation.md` (human-readable report)
- **Final output**: `4-final-draft.md` with inline citations and citation list
- **State snapshot**: `state.json` for full workflow debugging
- **Benefits**: Inspect intermediate outputs, identify improvement areas, preserve citations through pipeline

### Citation System (Perplexity Sonar Pro with Premium Sources)
- **Inline citations**: Industry-standard [^1], [^2] format throughout memo with space separation
- **Placement**: After punctuation with space: `text. [^1]` or multiple: `text. [^1] [^2]`
- **Source enrichment**: Perplexity Sonar Pro adds citations to each section independently
- **Global renumbering**: Citations renumbered sequentially across all sections ([^1][^2][^3]...)
- **Consolidated format**: ONE citation block at the end (not duplicated per section)
- **Premium sources**: Automatically targets authoritative sources via @ syntax:
  - **@crunchbase**: Funding data, investors, team backgrounds, firmographics
  - **@pitchbook**: Valuations, market analysis, deal data, fund performance
  - **@statista**: Market statistics, TAM/SAM sizing, industry forecasts
  - **@cbinsights**: Market trends, competitive intelligence, startup tracking
  - **@bloomberg**, **@reuters**, **@forbes**: Financial journalism and news
  - **@sec**: Regulatory filings, IPO data, fund disclosures
  - **@linkedin**: Professional backgrounds and team profiles
- **Quality control**: Prevents citations from low-quality blogs, benchmark sites, SEO spam
- **Citation format**: `[^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: N/A`
- **Markdown links**: URLs wrapped in clickable markdown links for easy reference

### Multi-Brand Export System
- **Customizable branding**: Configure company name, tagline, colors, and fonts via YAML files
- **Multiple brands**: Support for multiple VC firm clients in a single installation
- **Brand configurations**: Create `templates/brand-configs/brand-<name>-config.yaml` files (e.g., `brand-accel-config.yaml`, `brand-sequoia-config.yaml`)
- **Quick setup**: Copy `templates/brand-configs/brand-config.example.yaml` and customize with your firm's colors and fonts
- **Export formats**: HTML (light/dark modes) and PDF with full branding
- **Easy switching**: `python export-branded.py memo.md --brand accel` applies Accel branding
- **System fonts**: Works with or without custom font files
- **Documentation**: Complete guide in [docs/CUSTOM-BRANDING.md](docs/CUSTOM-BRANDING.md)

#### Creating Your Own Brand

Any VC firm can create their own branded exports in 3 simple steps:

1. **Copy the example config:**
   ```bash
   cp templates/brand-configs/brand-config.example.yaml templates/brand-configs/brand-yourfirm-config.yaml
   ```

2. **Edit with your firm's details:**
   ```yaml
   company:
     name: "Your VC Firm Name"
     tagline: "Your firm's tagline"

   colors:
     primary: "#1a3a52"        # Your brand's primary color (hex code)
     secondary: "#1dd3d3"      # Accent color
     # ... (see example file for all options)

   fonts:
     family: "Inter"           # Use system fonts like Inter, Georgia, Arial
     custom_fonts_dir: null    # Or path to custom WOFF2 font files
   ```

3. **Export with your brand:**
   ```bash
   python export-branded.py memo.md --brand yourfirm
   ```

That's it! Your memos will now export with your firm's branding. See [docs/CUSTOM-BRANDING.md](docs/CUSTOM-BRANDING.md) for detailed customization options including custom fonts, color modes, and troubleshooting.

### Version Control System
- Semantic versioning for memo iterations (v0.0.x → v0.x.0 → vx.0.0)
- Automatic patch increments for each generation
- Complete version history with timestamps and scores
- JSON-tracked state for each version

### Quality Standards
- Follows Hypernova template (10 sections)
- Style guide enforcement (analytical tone, specific metrics, balanced perspective)
- Source citation requirements
- Validation score threshold (8/10) for auto-finalization
- Detailed improvement suggestions when score < 8

### Dual-Template System
Hypernova is a Fund-of-Funds, deploying 40% of capital as LP commitments to solo GPs and emerging managers, and 60% as direct investments into technology startups. The system supports both investment types:

**Direct Investment Template** (`memo-template-direct.md`):
- 10 sections optimized for startup analysis
- Sections: Executive Summary, Business Overview, Market Context, Team, Technology & Product, Traction & Milestones, Funding & Terms, Risks & Mitigations, Investment Thesis, Recommendation

**Fund Commitment Template** (`memo-template-fund.md`):
- 10 sections optimized for LP diligence
- Sections: Executive Summary, GP Background & Track Record, Fund Strategy & Thesis, Portfolio Construction, Value Add & Differentiation, Track Record Analysis, Fee Structure & Economics, LP Base & References, Risks & Mitigations, Recommendation

**Memo Modes**:
- **Justify mode**: Retrospective analysis for existing investments - recommendation is always "COMMIT" with rationale explaining the investment decision
- **Consider mode**: Prospective analysis for potential investments - recommendation is "PASS/CONSIDER/COMMIT" based on objective analysis

## Tech Stack

- **Orchestration**: LangGraph (Python) for multi-agent coordination
- **LLM**: Anthropic Claude Sonnet 4.5 for analysis and writing
- **Web Search**: Tavily API (recommended) or [Perplexity Sonar Pro](https://www.perplexity.ai/hub/blog/introducing-the-sonar-pro-api) API for research
- **Web Scraping**: httpx + BeautifulSoup for website parsing
- **CLI**: Rich for beautiful terminal output with progress indicators
- **State Management**: TypedDict schemas with LangGraph state graphs

## Quick Start

### Installation

#### System Dependencies (Recommended)

While Python dependencies install automatically, certain export features require system-level tools. Install these for the best experience:

**Pandoc** (for Word/HTML exports):
```bash
# macOS
brew install pandoc

# Ubuntu/Debian
sudo apt install pandoc

# Windows
choco install pandoc
```
*Note: If not installed, `pypandoc` will attempt to auto-download, but brew installation is faster and more reliable.*

**WeasyPrint Dependencies** (for PDF exports):
```bash
# macOS
brew install cairo pango gdk-pixbuf libffi

# Ubuntu/Debian
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev
```

#### Python Dependencies

```bash
# Install dependencies with uv (requires Python 3.11+)
uv pip install -e . --python /path/to/python3.11

# Or with pip
pip install -e .
```

### Configuration

```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your API keys
# Required:
ANTHROPIC_API_KEY=your-claude-key

# Optional (for web search - highly recommended):
TAVILY_API_KEY=your-tavily-key
# or
PERPLEXITY_API_KEY=your-perplexity-key
```

Get a free Tavily API key at [tavily.com](https://tavily.com) (1,000 searches/month free tier).

### Usage

The system supports two investment types and two memo modes:

**Investment Types:**
- `direct`: Direct startup investment (default)
- `fund`: LP commitment to a venture fund

**Memo Modes:**
- `consider`: Prospective analysis for potential investment (default)
- `justify`: Retrospective justification for existing investment

```bash
# Basic usage (defaults to: direct + consider)
python -m src.main "Company Name"

# Direct investment examples
python -m src.main "Aalo Atomics" --type direct --mode justify
python -m src.main "Thinking Machines" --type direct --mode consider

# Fund commitment examples
python -m src.main "Pear VC" --type fund --mode justify
python -m src.main "Accel Growth Fund V" --type fund --mode consider

# Interactive mode
python -m src.main
```

**CLI Arguments:**
- `--type [direct|fund]`: Investment type (default: `direct`)
- `--mode [justify|consider]`: Memo mode (default: `consider`)

### Company Data Files (Optional)

You can create a JSON file in `data/{CompanyName}.json` to provide additional context and configuration:

```json
{
  "type": "direct",
  "mode": "consider",
  "description": "Brief company description for research context",
  "url": "https://company.com",
  "stage": "Series B",
  "deck": "data/CompanyName-deck.pdf",
  "trademark_light": "https://company.com/logo-light.svg",
  "trademark_dark": "https://company.com/logo-dark.svg",
  "notes": "Research focus: team backgrounds, competitive positioning, unit economics"
}
```

**Field Reference:**

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"direct"` or `"fund"` | Investment type (overrides CLI `--type`) |
| `mode` | `"consider"` or `"justify"` | Memo mode (overrides CLI `--mode`) |
| `description` | string | Brief description to guide research |
| `url` | string | Company website URL |
| `stage` | string | Investment stage (Seed, Series A, etc.) |
| `deck` | string | Path to pitch deck PDF (relative to project root) |
| `trademark_light` | string | URL or path to light mode company logo |
| `trademark_dark` | string | URL or path to dark mode company logo |
| `notes` | string | Specific research focus areas or instructions |

**Trademark Insertion:**
- If trademark paths are provided, the company logo will be automatically inserted in the memo content after the header metadata
- Light mode exports use `trademark_light`, dark mode exports use `trademark_dark`
- Trademarks can be URLs (e.g., from company website) or local file paths (e.g., `templates/trademarks/company-logo.svg`)

**Example:** See `data/sample-company.json` and `data/TheoryForge.json` for complete examples.

### Output

Each generation creates a versioned artifact directory:
```
output/{Company-Name}-v0.0.x/
├── 1-research.json          # Structured research data
├── 1-research.md            # Human-readable research summary
├── 2-sections/              # Individual section drafts
│   ├── 01-executive-summary.md
│   ├── 02-business-overview.md
│   └── ... (all 10 sections)
├── 3-validation.json        # Validation scores and feedback
├── 3-validation.md          # Human-readable validation report
├── 4-final-draft.md         # Complete memo with citations
└── state.json               # Full workflow state for debugging
```

Plus `versions.json` tracking version history across all iterations.

## Improving Existing Memos

After generating a memo, you can improve individual sections without regenerating the entire memo. This is useful when:
- One section is weak or missing details
- You want to add more citations to a specific section
- You need to strengthen analysis in a particular area
- Research data has been updated since generation

### Section Improvement with Perplexity Sonar Pro

The `improve-section.py` script uses **Perplexity Sonar Pro** for real-time research and automatic citation addition.

**Features:**
- Real-time web research for up-to-date information
- Automatic citation addition (Obsidian-style `[^1], [^2]`)
- Quality source selection (TechCrunch, Crunchbase, industry reports)
- Automatic final draft reassembly after improvement
- One-step process (no separate citation enrichment needed)

**Usage:**
```bash
# Activate venv first
source .venv/bin/activate

# Improve a specific section
python improve-section.py "Avalanche" "Team"

# Specify version
python improve-section.py "Avalanche" "Market Context" --version v0.0.1

# Use direct path to artifact directory
python improve-section.py output/Avalanche-v0.0.1 "Technology & Product"
```

**Available Section Names:**

*Direct Investment Sections:*
- Executive Summary
- Business Overview
- Market Context
- Team
- Technology & Product
- Traction & Milestones
- Funding & Terms
- Risks & Mitigations
- Investment Thesis
- Recommendation

*Fund Commitment Sections:*
- Executive Summary
- GP Background & Track Record
- Fund Strategy & Thesis
- Portfolio Construction
- Value Add & Differentiation
- Track Record Analysis
- Fee Structure & Economics
- LP Base & References
- Risks & Mitigations
- Recommendation

**Output:**
```
✓ Loading artifacts from: output/Avalanche-v0.0.1/
✓ Loaded research data
✓ Loaded 10 existing sections

Improving section: Team
  Using Perplexity Sonar Pro for real-time research...

✓ Section improved with 11 new citations added
✓ Saved to: output/Avalanche-v0.0.1/2-sections/04-team.md

Reassembling final draft...
✓ Final draft reassembled: output/Avalanche-v0.0.1/4-final-draft.md

Citations added: 11

Next steps:
  1. Review improved section in: output/Avalanche-v0.0.1/2-sections/
  2. View complete memo: output/Avalanche-v0.0.1/4-final-draft.md
  3. Export to HTML: python export-branded.py output/Avalanche-v0.0.1/4-final-draft.md --brand hypernova
```

**Requirements:**
- `PERPLEXITY_API_KEY` must be set in `.env` file
- Existing artifact directory from a previous memo generation

**Benefits:**
- **Faster**: ~60 seconds vs. 10+ minutes for full regeneration
- **Cheaper**: ~$1.00 per section vs. ~$10.00 for full memo
- **Targeted**: Improve only what needs improvement
- **Preserves**: Other sections remain unchanged

## File Format Conversion & Export

The system supports multiple export formats with professional Hypernova branding and citation preservation.

### Overview of Export Tools

1. **`md2docx.py`** - Basic Word (.docx) conversion
2. **`export-branded.py`** - Branded HTML exports with light/dark modes
3. **`export-all-modes.sh`** - Batch export of all memos in both color modes

All exports preserve:
- ✅ Inline citations `[^1], [^2], [^3]` with proper spacing
- ✅ Complete footnote sections with URLs and publication dates
- ✅ Markdown formatting (headers, lists, tables, blockquotes)
- ✅ Proper typography and professional styling

---

### 1. Word (.docx) Export

Convert markdown memos to Microsoft Word format for traditional sharing:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Convert a single memo
python md2docx.py output/Aalo-Atomics-v0.0.5/4-final-draft.md

# Convert with custom output location
python md2docx.py output/Aalo-Atomics-v0.0.5/4-final-draft.md -o exports/

# Convert all memos in a directory
python md2docx.py output/Aalo-Atomics-v0.0.5/2-sections/ -o exports/

# Add table of contents
python md2docx.py output/memo.md --toc
```

**Features:**
- Automatically downloads pandoc if needed
- Maintains all formatting from markdown source
- Preserves footnotes (visible in Microsoft Word, not Google Docs/Preview)

**Note:** Citations only render properly in Microsoft Word. For better citation visibility, use HTML exports.

---

### 2. Branded HTML Export (Light Mode)

Export with full Hypernova Capital branding in light mode (default):

```bash
source .venv/bin/activate

# Export single memo (light mode - default)
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md

# Export with custom output directory
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md -o exports/light/

# Export all memos in a directory
python export-branded.py output/ --all -o exports/light/
```

**Features:**
- **Hypernova branding**: Logo, colors (#1a3a52 navy, #1dd3d3 cyan), Arboria font
- **Improved citation spacing**: `[1], [2], [3]` instead of `[1][2][3]`
- **Clickable footnotes**: Citations link to source list at bottom
- **Professional header/footer**: Company branding and metadata
- **Self-contained HTML**: Includes all CSS and fonts (no external dependencies)
- **Print-optimized**: Ready for PDF conversion via browser print

---

### 3. Branded HTML Export (Dark Mode)

Export with dark theme optimized for screen reading:

```bash
source .venv/bin/activate

# Export single memo in dark mode
python export-branded.py output/Aalo-Atomics-v0.0.5/4-final-draft.md --mode dark

# Export all memos in dark mode
python export-branded.py output/ --all --mode dark -o exports/dark/
```

**Dark Mode Colors:**
- Background: Dark navy (#1a3a52)
- Text: White (#ffffff)
- Accents: Cyan (#1dd3d3)
- Perfect for: Screen reading, presentations, reducing eye strain

---

### 4. Batch Export (Both Light & Dark Modes)

Export all memos in both color modes at once:

```bash
source .venv/bin/activate

# Export everything
./export-all-modes.sh
```

**Output structure:**
```
exports/
├── light/  # 📄 Light mode HTML (white background)
│   ├── Aalo-Atomics-v0.0.5.html
│   ├── DayOne-v0.0.3.html
│   └── ... (all memos)
└── dark/   # 🌙 Dark mode HTML (navy background)
    ├── Aalo-Atomics-v0.0.5.html
    ├── DayOne-v0.0.3.html
    └── ... (all memos)
```

This creates **267+ HTML files** per mode with the latest citation improvements.

---

### 5. PDF Export (via HTML)

Convert branded HTML to PDF using your browser or command-line tools:

**Option A: Browser Print to PDF**
```bash
# 1. Generate HTML export
python export-branded.py output/Company/4-final-draft.md --mode light

# 2. Open in browser
open exports/branded/Company.html

# 3. Print to PDF (Cmd+P on Mac, Ctrl+P on Windows)
# - Enable "Background graphics" for full styling
# - Save as PDF
```

**Option B: Command-line with wkhtmltopdf** (if installed)
```bash
# Export with PDF generation
python export-branded.py output/Company/4-final-draft.md --mode light --pdf
```

---

### Citation Improvements (All Export Formats)

All exports include **improved citation spacing** for better readability:

**Before:**
```
The company raised $100M[1][2][3][4][5] in funding.
```
Visual: **[1][2][3][4][5]** (cramped, hard to read)

**After:**
```
The company raised $100M[^1], [^2], [^3], [^4], [^5] in funding.
```
Visual: **[1], [2], [3], [4], [5]** (clear, professional)

**Technical Implementation:**
- **0.15em margins** around each citation
- **Automatic comma separators** between consecutive citations
- **Gray commas** for subtlety (adapts to dark mode)
- **Academic formatting** following IEEE/ACM standards

---

### Export Format Comparison

| Format | Best For | Citations Visible | Branding | Editable |
|--------|----------|-------------------|----------|----------|
| **Word (.docx)** | Offline editing, track changes | ⚠️ MS Word only | ❌ Plain | ✅ Yes |
| **HTML (Light)** | Printing, email attachments, bright environments | ✅ Always | ✅ Full | ⚠️ Via code |
| **HTML (Dark)** | Screen reading, presentations, night reading | ✅ Always | ✅ Full | ⚠️ Via code |
| **PDF (from HTML)** | Distribution, archival, compliance | ✅ Always | ✅ Full | ❌ No |

---

### Quick Reference Commands

```bash
# Activate environment
source .venv/bin/activate

# Word export (single memo)
python md2docx.py output/Company/4-final-draft.md

# HTML light mode (single memo)
python export-branded.py output/Company/4-final-draft.md

# HTML dark mode (single memo)
python export-branded.py output/Company/4-final-draft.md --mode dark

# Batch export all memos (both modes)
./export-all-modes.sh

# HTML with PDF generation
python export-branded.py output/Company/4-final-draft.md --pdf
```

---

### Documentation

For more details, see:
- `exports/EXPORT-GUIDE.md` - Comprehensive export documentation
- `exports/DARK-MODE-GUIDE.md` - Light vs. dark mode usage guide
- `exports/CITATION-IMPROVEMENTS.md` - Citation spacing implementation details

## Architecture

### Workflow

```
┌──────────────┐
│  Supervisor  │ ← Coordinates workflow
└──────┬───────┘
       │
   ┌───┴────────────┐
   │ Deck Analyst   │ ← Extract info from pitch deck PDF (if available)
   └───┬────────────┘   Saves: 0-deck-analysis.json, 0-deck-analysis.md, initial drafts
       │
   ┌───┴────┐
   │Research│ ← Web search (Tavily: 4 queries) + synthesis
   └───┬────┘   Saves: 1-research.json, 1-research.md
       │
   ┌───┴────┐
   │ Writer │ ← Draft memo (10 sections), enrich deck drafts with research
   └───┬────┘   Saves: 2-sections/*.md (10 files)
       │
   ┌───┴─────────────┐
   │Citation Enrich  │ ← Add inline citations (Perplexity Sonar Pro)
   └───┬─────────────┘   Preserves narrative, adds [^1], [^2], etc.
       │
   ┌───┴──────────────────┐
   │Citation Validator    │ ← Validate date accuracy, detect duplicates
   └───┬──────────────────┘   Check URLs, ensure proper formatting
       │
   ┌───┴────────┐
   │ Validator  │ ← Score 0-10, identify issues
   └───┬────────┘   Saves: 3-validation.json, 3-validation.md
       │
   ┌───┴───────────────┐
   │   Score >= 8?     │
   └───┬───────────┬───┘
       │           │
   ┌───┴────┐  ┌──┴──────────┐
   │Finalize│  │Human Review │
   └────────┘  └─────────────┘
   Both save: 4-final-draft.md, state.json
```

### State Management

```python
MemoState = {
    "company_name": str,
    "investment_type": Literal["direct", "fund"],  # Type of investment
    "memo_mode": Literal["justify", "consider"],   # Memo purpose
    "research": ResearchData,      # Web search results + synthesis
    "draft_sections": Dict,         # Drafted memo sections
    "validation_results": Dict,     # Scores and feedback
    "overall_score": float,         # 0-10 quality score
    "revision_count": int,          # Iteration tracking
    "final_memo": str,              # Finalized content
    "messages": List[str]           # Agent outputs
}
```

## Project Structure

```
investment-memo-orchestrator/
├── src/
│   ├── agents/
│   │   ├── deck_analyst.py           # Pitch deck analysis (PDF extraction)
│   │   ├── researcher.py             # Basic research (no web search)
│   │   ├── research_enhanced.py      # Web search + synthesis
│   │   ├── writer.py                 # Memo drafting
│   │   ├── citation_enrichment.py    # Citation addition (Perplexity)
│   │   ├── citation_validator.py     # Citation accuracy validation
│   │   ├── validator.py              # Quality validation
│   │   └── dataroom/                 # Dataroom Analyzer Agent System
│   │       ├── __init__.py           # Package exports
│   │       ├── analyzer.py           # Main orchestrator
│   │       ├── dataroom_state.py     # TypedDict schemas
│   │       ├── document_scanner.py   # Directory scanning
│   │       ├── document_classifier.py # 3-stage classification
│   │       └── extractors/           # Specialized extractors
│   │           ├── __init__.py
│   │           └── competitive_extractor.py  # Battlecard synthesis
│   ├── state.py                      # TypedDict schemas
│   ├── workflow.py                   # LangGraph orchestration
│   ├── artifacts.py                  # Artifact trail system
│   ├── versioning.py                 # Version tracking system
│   └── main.py                       # CLI entry point
├── templates/
│   ├── memo-template.md              # 10-section structure
│   └── style-guide.md                # Writing standards
├── docs/
│   └── WEB_SEARCH_SETUP.md           # Search provider guide
├── changelog/
│   ├── 2025-11-16_01.md              # Week 1 POC completion
│   └── 2025-11-16_02.md              # Artifact trail system
├── context-vigilance/
│   └── Multi-Agent-Orchestration...  # Exploration document
├── output/                           # Generated memos with artifacts
│   └── {Company}-v0.0.x/             # Versioned artifact directories
├── data/                             # Sample company data
└── tests/                            # Unit tests (TODO)
```

## Versioning & Releases

This project uses **git-based semantic versioning** with `setuptools-scm`:

- **Version is automatically derived from git tags** (no manual file updates needed)
- Tags follow semantic versioning: `v0.1.0`, `v0.2.0`, `v1.0.0`, etc.
- Between releases, version includes commit count: `0.1.1.dev3` (3 commits after v0.1.0)

### Creating a New Release

```bash
# 1. Ensure all changes are committed
git status

# 2. Create and push a new tag (follows semantic versioning)
git tag v0.2.0 -m "Release v0.2.0: Brief description of changes"
git push origin v0.2.0

# 3. Version automatically updates to 0.2.0
python -c "from src import __version__; print(__version__)"
# Output: 0.2.0

# 4. Create GitHub release from tag (optional)
gh release create v0.2.0 --generate-notes
```

### Semantic Versioning Guide

- **Patch** (`v0.1.1`): Bug fixes, minor improvements
- **Minor** (`v0.2.0`): New features, backward-compatible changes
- **Major** (`v1.0.0`): Breaking changes, major milestones

### Checking Current Version

```bash
# From Python
python -c "from src import __version__; print(__version__)"

# From command line
git describe --tags
```

## Testing

### POC Test Results (Aalo Atomics)

**Without Web Search** (v0.0.0 equivalent):
- Score: 3.5/10
- Issues: 90% placeholders, no actual company data
- Output: Framework memo showing what should be evaluated

**With Web Search** (v0.0.1-v0.0.4):
- Score: 7.5-8.5/10
- Real Data Found:
  - Founders: Matt Loszak (CEO), Yasir Arafat (CTO, ex-INL)
  - Funding: $136M total (Seed $6.3M, Series A $27M, Series B $100M)
  - Investors: Valor Equity Partners, NRG Energy, Hitachi Ventures
  - Location: Austin, Texas
  - Technology: 50 MWe modular reactors for AI data centers
- Issues: Source citations were missing

**With Citation-Enrichment Agent** (v0.0.5):
- Score: 8.5/10
- **Citations Added**: 8 inline citations with full source attribution
- **Citation Format**: `[^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD`
- **Sources Used**: TechCrunch, Business Insider, PowerMag, World Nuclear News, company blog
- **Artifact Trail**: 16 files saved (research, sections, validation, final draft, state)
- Issues: Some data gaps, market sizing lacks specifics (expected for pre-commercial company)

### Completed Improvements ✅
- [x] Create a "trail" of the collected information as structured output or markdown files
- [x] Assure that citations are retained in the final output with proper attribution
- [x] Terminal progress indicators and status messages to track workflow
- [x] Find a way to include direct markdown links to team's LinkedIn profiles
- [x] Find a way to "add" links to important organizations, such as government bodies, co-investors or previous investors, etc
- [x] Find a way to include any public charts, graphs, diagrams, or visualizations from the company's website or other sources
- [x] Allow arguments for customizing the memo template based on a "Direct Investment" or an "LP Commitment" that leads to changes in the template being generated.
- [x] Allow arguments for specifying whether the investment has already been decided (even wired already) or is currently being considered.

### Improvements that need more testing
- [x] Ability for users to run a command to improve or enhance a certain section rather than running the whole memo generation orchestration.
- [x] Ability for users to run a command that adds or corrects crucial information that influences the entire content of the memo.  
  Example: the Avalanche memo output says Avalanche is raising a $50M fund, but they were raising a $10M fund. In many different places it discusses the fund size.  Therefore, this correction influences the entire content of the memo.

### Remaining Enhancements
- [ ] Elegant use of Trademarks of both authoring investment firm and target company.
 - This has been developed but it's still buggy.
- [ ] Specialized research strategies per investment type (e.g., GP track record analysis for funds) 
- [ ] Specialized section outline per `fund` or `direct` investment type.
- [ ] Agent that can screenshot the `deck` if provided and include relevant screenshots in relevant sections in the memo.


## Current Capabilities ✅

- [x] Multi-agent orchestration (Research → Write → Cite → Validate)
- [x] Web search integration (Tavily for research, Perplexity Sonar Pro for citations)
- [x] Citation-Enrichment Agent with inline [^1], [^2] format
- [x] Artifact trail system (research, sections, validation, final draft)
- [x] Complete workflow transparency with 16+ files per generation
- [x] Hypernova template following (10 sections)
- [x] Style guide enforcement
- [x] Rigorous validation with specific feedback
- [x] Semantic versioning (v0.0.x)
- [x] Version history tracking
- [x] Rich CLI with progress indicators
- [x] State export (JSON)

## Roadmap

### Week 2: MCP Server Integration
- [ ] Build Portfolio Data MCP server
- [ ] Crunchbase/PitchBook API integration via MCP
- [ ] Template serving via MCP (version-controlled)
- [ ] Validation criteria as MCP resources

### Week 3: Revision Loop
- [ ] Implement Revision Agent
- [ ] Iterative improvement until score >= 8
- [ ] Specialized section writers (Market, Technical, Risk)
- [ ] Parallel section generation

### Week 4: Production Features
- [ ] Web UI (Streamlit/Gradio)
- [ ] Human-in-the-loop checkpoints
- [ ] PDF export with branding
- [ ] Version comparison view
- [ ] Manual version promotion (v0.0.x → v0.1.0)

### Future Enhancements
- [ ] LangGraph checkpointing (resume from failures)
- [ ] Multi-model orchestration (GPT-4 for data, Claude for writing)
- [ ] Fine-tuned validation models
- [ ] Integration with pitch decks and financial models
- [ ] Batch processing for portfolio analysis
- [ ] A/B testing different agent configurations

## Configuration Options

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Web Search (recommended: both for best results)
TAVILY_API_KEY=tvly-...         # For research phase (fast, reliable)
PERPLEXITY_API_KEY=pplx-...     # For citation enrichment + premium source targeting (sonar-pro model)

# Optional
OPENAI_API_KEY=sk-...           # For future multi-model support

# Settings
USE_WEB_SEARCH=true             # Enable/disable web search
RESEARCH_PROVIDER=tavily        # tavily, perplexity, or claude (for research)
MAX_SEARCH_RESULTS=10           # Results per query
DEFAULT_MODEL=claude-sonnet-4-5-20250929
```

**Note**: For full citation support with premium sources, both `TAVILY_API_KEY` (research) and `PERPLEXITY_API_KEY` (citations + source targeting) are recommended.

- **With PERPLEXITY_API_KEY**: Research queries automatically enhanced with `@crunchbase`, `@pitchbook`, `@statista`, and other premium sources
- **Without PERPLEXITY_API_KEY**: Generic web search (no source targeting), Citation-Enrichment Agent skipped

See `docs/WEB_SEARCH_SETUP.md` for detailed provider comparison and `changelog/2025-11-22_02.md` for premium sources implementation details.

## Contributing

This is an internal Hypernova Capital research project. For questions or suggestions, contact the development team.

## License

Proprietary - Hypernova Capital

---

## Project Sponsored By

**[Hypernova Capital](https://www.hypernova.capital)**

Investing in frontier technology companies at the intersection of climate, energy, and AI.

---

*Last updated: 2025-11-26*
*Version: Automatically derived from git tags (currently v0.1.0)*
*Status: Git-based versioning with setuptools-scm*

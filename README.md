# Investment Memo Orchestrator

Multi-agent orchestration system for generating high-quality investment memos using LangGraph and specialized AI agents.

**Status**: Production-Ready with Section-by-Section Processing ✅

Supported by [Hypernova Capital](https://www.hypernova.capital), [Avalanche VC](https://avalanche.vc), and [Emerge Capital](https://emergecapital.vc)

---

## Table of Contents

- [Similar Services](#similar-services)
- [Recent Updates](#recent-updates)
  - [Firm-Scoped IO System (v0.3.0)](#2025-12-03-firm-scoped-io-system-v030)
  - [Dataroom Analyzer Agent System](#2025-11-26-dataroom-analyzer-agent-system)
  - [Premium Data Sources Integration](#2025-11-22-premium-data-sources-integration)
  - [Section-by-Section Processing](#2025-11-20-section-by-section-processing)
- [Overview](#overview)
- [Key Features](#key-features)
  - [Core Command](#core-command)
  - [Multi-Agent Pipeline](#multi-agent-pipeline)
  - [Web Search Integration](#web-search-integration-with-premium-source-targeting)
  - [Artifact Trail System](#artifact-trail-system)
  - [Citation System](#citation-system-perplexity-sonar-pro-with-premium-sources)
  - [Multi-Brand Export System](#multi-brand-export-system)
  - [Version Control System](#version-control-system)
  - [Quality Standards](#quality-standards)
  - [Dual-Template System](#dual-template-system)
  - [Scorecard Template System](#scorecard-template-system)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Usage](#usage)
  - [Company Data Files](#company-data-files-optional)
  - [Output](#output)
- [Improving Existing Memos](#improving-existing-memos)
  - [Section Improvement with Perplexity](#section-improvement-with-perplexity-sonar-pro)
  - [Reassembling Final Draft](#reassembling-final-draft)
- [Export](#export)
- [Architecture](#architecture)
  - [Workflow](#workflow)
  - [State Management](#state-management)
- [Project Structure](#project-structure)
- [CLI Tools Reference](#cli-tools-reference)
- [Pipeline Agents Reference](#pipeline-agents-reference)
- [Standalone Agents Reference](#standalone-agents-reference)
- [Versioning & Releases](#versioning--releases)
- [Status](#status)
- [Current Capabilities](#current-capabilities-)
- [Up Next](#up-next)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

### Similar Services
Many people may not want to manage using an Open Source library and deal with the command line.  These are services we have found that can provide similar Investment Memo Generation.

#### Dedicated Private Markets AI Platforms
- [Deck](https://www.hellodeck.ai/)
- [Deliverables](https://deliverables.ai/)
- [Blueflame AI](https://www.blueflame.ai/)
- [Pascal AI](https://www.pascalailabs.com/)
- [Promenade AI](https://www.promenade-ai.com/)
- [Rogo AI](https://rogo.ai/)
- [Wokelo](https://www.wokelo.ai/)

#### General AI Automation Platforms with Blueprints or Templates
- [Lyzr | Investment Memo Blueprint](https://www.lyzr.ai/blueprints/venture-capital/investment-memo-generator-agent/)
- [v7 Labs | Investment Memo Automations](https://www.v7labs.com/automations/ai-investment-memo-generation)
- [Stack AI | Investment Memo Generator Template](https://www.stack-ai.com/blog/how-to-build-an-investment-memo-generator)
- [Bash | Investment Memo Template](https://www.getbash.com/templates/investment-memo)

## Recent Updates

### 2025-12-03: Firm-Scoped IO System (v0.3.0)

**Multi-tenant architecture** enabling private firm-specific configurations, deal data, and branded exports. Each firm can maintain isolated data while sharing the core codebase.

**New Directory Structure:**
```
io/
└── {firm}/                           # e.g., "hypernova", "emerge"
    ├── configs/
    │   └── brand-{firm}-config.yaml  # Firm-specific brand styling
    ├── templates/
    │   ├── outlines/                 # Firm-specific content outlines
    │   └── scorecards/               # Firm-specific evaluation scorecards
    └── deals/
        └── {deal}/                   # e.g., "Blinka", "CoachCube"
            ├── {deal}.json           # Deal configuration
            ├── inputs/               # Pitch decks, datarooms
            ├── outputs/              # Versioned memo artifacts
            └── exports/              # Branded HTML/PDF exports
                ├── dark/
                └── light/
```

**Key Features:**
- **Privacy**: Firm data stays in `io/` (gitignored or private git submodule)
- **Multi-Tenant**: Multiple firms use same codebase with isolated configs
- **Backward Compatible**: Legacy `output/`, `data/`, `templates/` paths still work
- **Auto-Detection**: System auto-detects firm from `io/{firm}/deals/{deal}/` paths
- **Resume**: New `resume_from_interruption.py` CLI to continue interrupted generation

**Usage:**
```bash
# Generate memo with firm context
python -m src.main "Blinka" --firm hypernova

# Export with firm-scoped paths
python cli/export_branded.py --firm hypernova --deal Blinka --mode dark --pdf

# Resume interrupted generation
python cli/resume_from_interruption.py --firm emerge --deal CoachCube
```

See `io/README.md` for complete firm-scoped IO documentation.

---

### 2025-11-26: Dataroom Analyzer Agent System

**New multi-agent dataroom analyzer** for processing investment datarooms containing diverse document types (pitch decks, financials, battlecards, etc.). The system scans, classifies, and extracts structured data from dataroom documents.

**Phase 1 - Document Scanning & Classification** ✅
- Three-stage classification: directory-based → filename pattern → LLM fallback
- Supports 12+ document types (pitch_deck, cap_table, competitive_analysis, etc.)
- Confidence scoring with classification reasoning

**Phase 2 - Specialized Extractors** (5/5 Complete) ✅
- [x] Competitive Extractor - Synthesizes battlecards into unified competitive landscape
- [x] Cap Table Extractor - Ownership structure, shareholders, option pools
- [x] Financial Extractor - P&L, projections, key metrics from CSV/Excel
- [x] Traction Extractor - Customer counts, ARR/MRR, retention, pipeline, partnerships
- [x] Team Extractor - Founders, leadership, headcount, advisors, board

**Phase 3 - Data Synthesis** ✅
- [x] Conflict detection - ARR mismatches, headcount discrepancies, ownership totals
- [x] Data gap identification - Critical (burn rate, runway) and medium priority gaps
- [x] Cross-reference engine - Unified metrics with confidence scores
- [x] Synthesis report - Human-readable conflict/gap analysis

**Output Structure:**
```
output/Company-v0.0.1/
├── 0-dataroom-inventory.json/md    # Document inventory
├── 1-competitive-analysis.json/md  # Competitive landscape
├── 2-cap-table.json/md             # Ownership structure
├── 3-financial-analysis.json/md    # Financial projections
├── 4-traction-analysis.json/md     # Customers & traction metrics
├── 5-team-analysis.json/md         # Team & leadership profiles
└── 6-synthesis-report.json/md      # Cross-reference, conflicts, gaps
```

See `changelog/2025-11-26_01.md` through `changelog/2025-11-26_07.md` for complete details.

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

### Core Command
```bash
# Legacy mode (outputs to output/)
python -m src.main "Company Name" --type direct --mode consider

# Firm-scoped mode (outputs to io/{firm}/deals/{deal}/outputs/)
python -m src.main "Company Name" --firm hypernova --type direct --mode consider
```

### Multi-Agent Pipeline
The system coordinates 11+ specialized agents: research, writing, enrichment (trademarks, socials, links, citations), validation, and fact-checking. All agents process sections individually to avoid API timeouts.

See [Pipeline Agents Reference](#pipeline-agents-reference) and [CLI Tools Reference](#cli-tools-reference) for complete listings.

### Web Search Integration with Premium Source Targeting
- **Premium data sources**: Research queries enhanced with Perplexity `@source` syntax (@crunchbase, @pitchbook, @statista, @cbinsights)
- **Section-specific sources**: Each memo section targets appropriate authoritative sources (e.g., Market Context uses @statista, Team uses @linkedin)
- **Automatic aggregation**: 8 premium sources aggregated from 5 key sections for comprehensive coverage
- **Quality control**: Prevents low-quality filler from benchmark sites and SEO spam
- **Multi-query strategy**: Company overview, funding, team, news with targeted source selection
- **Multiple providers**: Tavily API (preferred), Perplexity Sonar Pro API, or DuckDuckGo (free fallback)
- **Automatic fallback**: If Tavily unavailable, falls back to Perplexity → DuckDuckGo
- **Free option**: Set `RESEARCH_PROVIDER=duckduckgo` for free web search (no API key required)

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
- **Firm-scoped configs**: Brand configs in `io/{firm}/configs/` for private firm branding
- **Shared configs**: Brand configs in `templates/brand-configs/` for cross-firm use
- **Multiple brands**: Support for multiple VC firm clients in a single installation
- **Quick setup**: Copy `templates/brand-configs/brand-config.example.yaml` and customize with your firm's colors and fonts
- **Export formats**: HTML (light/dark modes) and PDF with full branding
- **Easy switching**: `python cli/export_branded.py --firm hypernova --deal Blinka --brand collide` applies Collide branding to a Hypernova deal
- **System fonts**: Works with or without custom font files (supports local `.woff2`, `.ttf` files)
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

### Scorecard Template System

Scorecards codify your firm's proprietary evaluation criteria into structured YAML templates. This ensures AI-generated analysis reflects your actual investment thinking rather than generic LLM output.

**Why Scorecards Matter:**
- Generic AI output lacks firm-specific perspective
- Experienced investors have mental models they apply consistently
- Scorecards make implicit evaluation criteria explicit and repeatable
- Teams can align on what matters before AI generates content

**Create Your Own Scorecard:**

```yaml
# templates/scorecards/your-firm/your-scorecard.yaml
metadata:
  scorecard_id: "your-firm-evaluation-v1"
  name: "Your Evaluation Framework"
  applicable_types: ["direct", "fund"]  # or just one

scoring:
  scale:
    min: 1
    max: 5  # or 10, or any range

dimension_groups:
  - group_id: "team_quality"
    name: "Team Assessment"
    dimensions: [founder_market_fit, technical_depth, execution_speed]

dimensions:
  founder_market_fit:
    name: "Founder-Market Fit"
    short_description: "How well founders understand the problem space"
    evaluation_guidance:
      questions:
        - "Have founders experienced this problem firsthand?"
        - "Do they have unfair insight into the market?"
      red_flags:
        - "No domain experience"
        - "Thesis based on market reports, not lived experience"
    scoring_rubric:
      5: "Deep personal experience with problem; unique insight"
      3: "Relevant adjacent experience"
      1: "No connection to problem space"
```

**Using Scorecards:**

```bash
# Generate scorecard for a memo
python cli/generate_scorecard.py "CompanyName"

# Output: scorecard.md in artifact directory with scored dimensions
```

**Scorecard Structure:**
- **Dimensions**: Individual criteria you evaluate (any number)
- **Groups**: Logical groupings of related dimensions (any number)
- **Scoring rubrics**: What each score level means for your firm
- **Evaluation guidance**: Questions to ask, evidence to seek, red flags to watch

See `templates/scorecards/lp-commits_emerging-managers/hypernova-scorecard.yaml` for a complete example with 12 dimensions across 3 groups.

## Tech Stack

- **Orchestration**: LangGraph (Python) for multi-agent coordination
- **LLM**: Anthropic Claude Sonnet 4.5 for analysis and writing
- **Web Search**: Tavily API (preferred), [Perplexity Sonar Pro](https://www.perplexity.ai/hub/blog/introducing-the-sonar-pro-api), or DuckDuckGo (free fallback)
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
TAVILY_API_KEY=your-tavily-key        # Preferred - has domain filtering
PERPLEXITY_API_KEY=your-perplexity-key # Also used for citation enrichment

# Research provider selection (default: tavily)
RESEARCH_PROVIDER=tavily     # Options: tavily, perplexity, duckduckgo
```

**Research Provider Options:**

| Provider | API Key Required | Best For |
|----------|-----------------|----------|
| `tavily` | Yes (`TAVILY_API_KEY`) | General research, domain filtering |
| `perplexity` | Yes (`PERPLEXITY_API_KEY`) | Deep research with citations |
| `duckduckgo` | No (free!) | Free fallback, no API key needed |

**Automatic Fallback:** If your configured provider's API key is missing, the system automatically tries: Tavily → Perplexity → DuckDuckGo.

Get API keys:
- Tavily: [tavily.com](https://tavily.com) (1,000 searches/month free tier)
- Perplexity: [perplexity.ai](https://www.perplexity.ai/settings/api) (pay-as-you-go)

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
  "notes": "Research focus: team backgrounds, competitive positioning, unit economics",
  "disambiguation": [
    "https://wrong-company.com/",
    "https://similar-name-different-entity.com/"
  ]
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
| `disambiguation` | array | URLs of **wrong** companies with similar names to exclude from research |

**Trademark Insertion:**
- If trademark paths are provided, the company logo will be automatically inserted in the memo content after the header metadata
- Light mode exports use `trademark_light`, dark mode exports use `trademark_dark`
- Trademarks can be URLs (e.g., from company website) or local file paths (e.g., `templates/trademarks/company-logo.svg`)

**Entity Disambiguation:**
- Companies with common names often have multiple entities in search results (e.g., "Mercury" could be the banking startup or an insurance company)
- The `disambiguation` array lists URLs of **wrong entities** that should be excluded from research
- Research agents will discard data from these domains, preventing entity confusion
- Example: A company called "Reson8" at `reson8.xyz` might be confused with `reson8.group`, `reson8media.com`, or `reson8sms.com` - add those to the disambiguation array to exclude them

**Example:** See `data/sample-company.json` and `data/TheoryForge.json` for complete examples.

### Output

Each generation creates a versioned artifact directory:

**Legacy mode** (`output/`):
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

**Firm-scoped mode** (`io/{firm}/`):
```
io/{firm}/deals/{deal}/
├── {deal}.json              # Deal configuration
├── inputs/                  # Source materials (decks, datarooms)
├── outputs/                 # Generated memo artifacts
│   └── {Deal}-v0.0.x/       # Same structure as legacy
├── exports/                 # Branded HTML/PDF exports
│   ├── dark/
│   └── light/
└── assets/                  # Deal-specific assets (logos)
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

**Section Names:** Use the section names as they appear in `2-sections/` for the memo you're improving (e.g., "Team", "Market Context"). Section names are defined by your outline/template configuration.

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

### Reassembling Final Draft

If the final draft gets corrupted or you need to manually reassemble after editing section files:

```bash
# Reassemble with citation renumbering and TOC generation
python -m cli.assemble_draft "Sava"
python -m cli.assemble_draft "Sava" --version v0.0.2
```

This ensures:
- Citations renumbered globally (no collisions)
- All citation references consolidated at document end
- Table of Contents is present and accurate

All section improvement tools automatically call this after their changes.

## Export

The system supports multiple export formats with branding and citation preservation.

| Tool | Format | Command |
|------|--------|---------|
| `md2docx.py` | Word (.docx) | `python md2docx.py output/Company-v0.0.1/4-final-draft.md` |
| `export-branded.py` | HTML (light) | `python export-branded.py output/Company-v0.0.1/4-final-draft.md` |
| `export-branded.py` | HTML (dark) | `python export-branded.py output/Company-v0.0.1/4-final-draft.md --mode dark` |
| `export-branded.py` | PDF | `python export-branded.py output/Company-v0.0.1/4-final-draft.md --pdf` |
| `export-all-modes.sh` | Batch (all memos) | `./export-all-modes.sh` |

All exports preserve inline citations, footnotes, and markdown formatting.

For detailed export options, custom branding, and troubleshooting, see:
- `exports/EXPORT-GUIDE.md` - Comprehensive export documentation
- `docs/CUSTOM-BRANDING.md` - Multi-brand configuration guide

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
│   │   ├── toc_generator.py          # Table of Contents generation
│   │   ├── fact_checker.py           # Fact verification agent
│   │   ├── validator.py              # Quality validation
│   │   ├── scorecard_agent.py        # 12-dimension emerging manager scorecard
│   │   ├── portfolio_listing_agent.py # Portfolio company extraction
│   │   └── dataroom/                 # Dataroom Analyzer Agent System
│   │       ├── __init__.py           # Package exports
│   │       ├── analyzer.py           # Main orchestrator
│   │       ├── dataroom_state.py     # TypedDict schemas
│   │       ├── document_scanner.py   # Directory scanning
│   │       ├── document_classifier.py # 3-stage classification
│   │       └── extractors/           # Specialized extractors
│   ├── state.py                      # TypedDict schemas
│   ├── workflow.py                   # LangGraph orchestration
│   ├── artifacts.py                  # Artifact trail system
│   ├── versioning.py                 # Version tracking system
│   ├── paths.py                      # Firm-scoped path resolution
│   ├── branding.py                   # Brand config loading
│   ├── scorecard_loader.py           # Scorecard loading
│   └── main.py                       # CLI entry point
├── cli/
│   ├── export_branded.py             # HTML/PDF export with branding
│   ├── resume_from_interruption.py   # Resume interrupted generation
│   ├── improve_section.py            # Section improvement
│   ├── score_memo.py                 # Scorecard generation
│   ├── recompile_memo.py             # Memo recompilation
│   ├── refocus_section.py            # Section refocusing
│   └── html-to-pdf.sh                # HTML to PDF conversion
├── io/                               # Firm-scoped IO (gitignored)
│   ├── README.md                     # Firm-scoped IO documentation
│   └── {firm}/                       # e.g., hypernova, emerge
│       ├── configs/                  # Brand configs
│       ├── templates/                # Outlines, scorecards
│       └── deals/                    # Deal data and outputs
├── templates/
│   ├── outlines/                     # YAML content outlines
│   ├── scorecards/                   # Evaluation scorecards
│   ├── brand-configs/                # Shared brand configurations
│   ├── memo-template-direct.md       # Direct investment template
│   ├── memo-template-fund.md         # Fund commitment template
│   └── style-guide.md                # Writing standards
├── docs/
│   ├── CUSTOM-BRANDING.md            # Brand configuration guide
│   ├── COMMANDS_CHEAT_SHEET.md       # CLI reference
│   └── WEB_SEARCH_SETUP.md           # Search provider guide
├── changelog/
│   └── releases/                     # Release notes
├── output/                           # Legacy output directory
├── data/                             # Legacy company data
└── tests/                            # Unit tests
```

## CLI Tools Reference

Standalone tools for post-generation improvements and exports. All tools support `--firm` and `--deal` flags for firm-scoped IO.

| Tool | Purpose | Usage |
|------|---------|-------|
| `cli/resume_from_interruption.py` | Resume interrupted generation | `python cli/resume_from_interruption.py --firm hypernova --deal Blinka` |
| `cli/sanitize_commentary.py` | Extract LLM process commentary to internal notes | `python cli/sanitize_commentary.py --firm hypernova --deal Blinka` |
| `cli/improve_section.py` | Improve a section with Perplexity research | `python cli/improve_section.py --firm hypernova --deal Blinka "Team"` |
| `cli/improve_team_section.py` | Deep team research (LinkedIn + web) | `python cli/improve_team_section.py --firm hypernova --deal Blinka` |
| `cli/assemble_draft.py` | Rebuild final draft from sections | `python cli/assemble_draft.py --firm hypernova --deal Blinka` |
| `cli/rewrite_key_info.py` | Apply YAML corrections across sections | `python cli/rewrite_key_info.py "Company" corrections.yaml` |
| `cli/generate_scorecard.py` | Generate scorecard from template | `python cli/generate_scorecard.py "Company"` |
| `cli/score_memo.py` | Score memo with scorecard | `python cli/score_memo.py --firm hypernova --deal Blinka` |
| `cli/evaluate_memo.py` | Re-run validation on existing memo | `python cli/evaluate_memo.py "Company"` |
| `cli/refocus_section.py` | Refocus section with new guidance | `python cli/refocus_section.py --firm hypernova --deal Blinka "Section"` |
| `cli/recompile_memo.py` | Recompile memo from sections | `python cli/recompile_memo.py --firm hypernova --deal Blinka` |
| `cli/export_branded.py` | Export to branded HTML/PDF | `python cli/export_branded.py --firm hypernova --deal Blinka --pdf` |
| `cli/html-to-pdf.sh` | Convert HTML to PDF | `bash cli/html-to-pdf.sh path/to/memo.html` |
| `cli/md2docx.py` | Export to Word (.docx) | `python md2docx.py memo.md` |

## Pipeline Agents Reference

Agents that run as part of the main memo generation workflow (`python -m src.main`).

| Agent | File | Purpose |
|-------|------|---------|
| Deck Analyst | `deck_analyst.py` | Extract info from pitch deck PDFs |
| Research | `research_enhanced.py` | Web search via Tavily/Perplexity |
| Writer | `writer.py` | Draft sections from outline/template |
| Trademark Enrichment | `trademark_enrichment.py` | Insert company logo into header |
| Socials Enrichment | `socials_enrichment.py` | Add LinkedIn links to team members |
| Link Enrichment | `link_enrichment.py` | Add hyperlinks to organizations/entities |
| Citation Enrichment | `citation_enrichment.py` | Add inline citations via Perplexity |
| TOC Generator | `toc_generator.py` | Generate Table of Contents |
| Citation Validator | `citation_validator.py` | Validate citation accuracy and dates |
| Fact Checker | `fact_checker.py` | Verify claims against research sources |
| Validator | `validator.py` | Score memo quality (0-10 scale) |

## Standalone Agents Reference

Agents with their own CLI entry points for specialized tasks.

| Agent | File | Purpose |
|-------|------|---------|
| Internal Comments Sanitizer | `internal_comments_sanitizer.py` | Extract LLM process commentary to internal notes |
| Scorecard Agent | `scorecard_agent.py` | Generate scorecards from YAML templates |
| Portfolio Listing | `portfolio_listing_agent.py` | Extract portfolio companies from fund memos |
| Key Info Rewrite | `key_info_rewrite.py` | Propagate fact corrections across sections |
| Dataroom Analyzer | `dataroom/analyzer.py` | Scan and extract data from dataroom documents |

For detailed documentation, see:
- `docs/COMMANDS_CHEAT_SHEET.md` - **Complete CLI reference with all options and examples**
- `docs/CASUAL_USER_GUIDE.md` - Comprehensive usage guide
- `docs/SETUP.md` - Installation and configuration
- `docs/TROUBLESHOOTING.md` - Common issues and solutions

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

## Status

### Completed ✅
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
- [x] Elegant use of Trademarks of both authoring investment firm and target company (v0.3.0)
  - VC firm logo in HTML header via brand config
  - Company trademark in memo body via deal config
  - Dark/light mode support for both
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

## Up Next

### Internal Comments Containerization ✅

LLMs have a tendency to include meta-commentary in generated content ("Let me search for...", "Note: Unable to find...", "If you have the actual content, please share..."). Despite aggressive prompt engineering, this process commentary leaks into final output and is inappropriate for external-facing documents.

**Implemented:** The `cli/sanitize_commentary.py` CLI and `src/agents/internal_comments_sanitizer.py` agent:
1. Detects leaked commentary using 15+ regex patterns
2. Extracts internal notes to a separate `2-sections-internal/` folder
3. Consolidates process notes into `4-internal-notes.md`
4. Automatically reassembles clean final draft

**Usage:**
```bash
# Sanitize a memo
python cli/sanitize_commentary.py --firm hypernova --deal Blinka

# Preview what would be extracted without modifying
python cli/sanitize_commentary.py --firm hypernova --deal Blinka --preview
```

See `context-vigilance/Containerizing-Internal-Comments-and-Recommendations-for-Consideration.md` for complete specification.

### Table Generator Agent

A specialized agent to identify and generate tables from data that would be better presented in tabular form:
- Temporal series (funding rounds, milestones, metrics over time)
- Entity comparisons (competitors, investors, team members)
- Structured data from decks and datarooms

See `context-vigilance/Table-Generator-Agent-Spec.md` for complete specification.

## Roadmap

- [x] Resume from interruption (v0.3.0 - `cli/resume_from_interruption.py`)
- [x] Multi-tenant firm isolation (v0.3.0 - firm-scoped IO)
- [x] Internal comments containerization (v0.3.4 - `cli/sanitize_commentary.py`)
- [ ] Table generator agent
- [ ] LangGraph native checkpointing
- [ ] Web UI (Streamlit/Gradio)
- [ ] Human-in-the-loop checkpoints
- [ ] Batch processing for portfolio analysis

## Contributing

This is an internal Hypernova Capital research project. For questions or suggestions, contact the development team.

## License

Proprietary - Hypernova Capital

---

## Project Sponsored By

**[Hypernova Capital](https://www.hypernova.capital)**

Investing in frontier technology companies at the intersection of climate, energy, and AI.

---

*Last updated: 2025-12-05*
*Version: v0.3.4 (Internal Comments Sanitizer)*
*Status: Production-ready with multi-tenant support*

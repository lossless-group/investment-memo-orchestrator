# Investment Memo Orchestrator

Multi-agent orchestration system for generating high-quality investment memos using LangGraph and specialized AI agents.

**Status**: Week 1 POC Complete + Artifact Trail & Citation System ✅

Sponsored by [Hypernova Capital](https://www.hypernova.capital)

## Overview

This system uses a supervisor pattern with specialized AI agents to generate investment memos that match Hypernova Capital's analytical standards. Instead of a single AI prompt, it coordinates multiple expert agents that research, write, validate, and iterate on memos.

## Key Features

### Core Commands
```bash
python3.11 -m src.main "Class5 Global" --type fund --mode justify
```

### Multi-Agent Architecture
- **Research Agent**: Actively searches the web (Tavily/Perplexity) for company information, funding data, team backgrounds, and market context
- **Writer Agent**: Drafts professional memos following Hypernova's 10-section template and style guide
- **Citation-Enrichment Agent**: Adds inline citations [^1], [^2] to drafted content using Perplexity Sonar Pro, preserving narrative while adding scholarly rigor with industry sources (TechCrunch, Medium, Crunchbase, etc.)
- **Validator Agent**: Rigorously evaluates quality (0-10 scale) with specific, actionable feedback
- **Supervisor**: Orchestrates workflow, manages state, routes to revision or finalization

### Web Search Integration
- Real-time company research via Tavily API or Perplexity API
- Multi-query strategy: company overview, funding, team, news
- Automatic source aggregation and synthesis
- Fallback to Claude-only mode (no API keys required for testing)

### Artifact Trail System
- **Complete transparency**: Every workflow step saves artifacts to output directory
- **Research artifacts**: `1-research.json` (structured data) and `1-research.md` (human-readable summary)
- **Section drafts**: Individual section files in `2-sections/` (all 10 sections as separate .md files)
- **Validation reports**: `3-validation.json` (scores/feedback) and `3-validation.md` (human-readable report)
- **Final output**: `4-final-draft.md` with inline citations and citation list
- **State snapshot**: `state.json` for full workflow debugging
- **Benefits**: Inspect intermediate outputs, identify improvement areas, preserve citations through pipeline

### Citation System
- **Inline citations**: Industry-standard [^1], [^2] format throughout memo
- **Source preservation**: Citations from research phase maintained through final output
- **Quality sources**: Prioritizes TechCrunch, Sifted, Crunchbase, Medium, company blogs, press releases over academic papers
- **Citation list**: Formatted with publication dates, URLs, and titles matching Obsidian workflow
- **Format**: `[^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD`

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

### Exporting to Word Format

Convert your generated markdown memos to Microsoft Word (.docx) format for easy sharing:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Convert a single memo
python md2docx.py output/Aalo-Atomics-v0.0.5-memo.md

# Convert with custom output location
python md2docx.py output/Aalo-Atomics-v0.0.5-memo.md -o exports/

# Convert all memos in a directory
python md2docx.py output/Aalo-Atomics-v0.0.5/2-sections/ -o exports/

# Add table of contents
python md2docx.py output/memo.md --toc
```

The tool automatically downloads pandoc if needed. All converted files maintain proper formatting, headers, lists, and links from the markdown source.

## Architecture

### Workflow

```
┌──────────────┐
│  Supervisor  │ ← Coordinates workflow
└──────┬───────┘
       │
   ┌───┴────┐
   │Research│ ← Web search (Tavily: 4 queries) + synthesis
   └───┬────┘   Saves: 1-research.json, 1-research.md
       │
   ┌───┴────┐
   │ Writer │ ← Draft memo (10 sections)
   └───┬────┘   Saves: 2-sections/*.md (10 files)
       │
   ┌───┴─────────────┐
   │Citation Enrich  │ ← Add inline citations (Perplexity Sonar Pro)
   └───┬─────────────┘   Preserves narrative, adds [^1], [^2], etc.
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
│   │   ├── researcher.py             # Basic research (no web search)
│   │   ├── research_enhanced.py      # Web search + synthesis
│   │   ├── writer.py                 # Memo drafting
│   │   ├── citation_enrichment.py    # Citation addition (Perplexity)
│   │   └── validator.py              # Quality validation
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

### Remaining Enhancements
- [x] Find a way to include direct markdown links to team's LinkedIn profiles
- [x] Find a way to "add" links to important organizations, such as government bodies, co-investors or previous investors, etc
- [x] Find a way to include any public charts, graphs, diagrams, or visualizations from the company's website or other sources
- [x] Allow arguments for customizing the memo template based on a "Direct Investment" or an "LP Commitment" that leads to changes in the template being generated.
- [x] Allow arguments for specifying whether the investment has already been decided (even wired already) or is currently being considered.
- [ ] Specialized research strategies per investment type (e.g., GP track record analysis for funds) 


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
PERPLEXITY_API_KEY=pplx-...     # For citation enrichment (sonar-pro model)

# Optional
OPENAI_API_KEY=sk-...           # For future multi-model support

# Settings
USE_WEB_SEARCH=true             # Enable/disable web search
RESEARCH_PROVIDER=tavily        # tavily, perplexity, or claude (for research)
MAX_SEARCH_RESULTS=10           # Results per query
DEFAULT_MODEL=claude-sonnet-4-5-20250929
```

**Note**: For full citation support, both `TAVILY_API_KEY` (research) and `PERPLEXITY_API_KEY` (citations) are recommended. Without Perplexity, the Citation-Enrichment Agent will be skipped.

See `docs/WEB_SEARCH_SETUP.md` for detailed provider comparison.

## Contributing

This is an internal Hypernova Capital research project. For questions or suggestions, contact the development team.

## License

Proprietary - Hypernova Capital

---

## Project Sponsored By

**[Hypernova Capital](https://www.hypernova.capital)**

Investing in frontier technology companies at the intersection of climate, energy, and AI.

---

*Last updated: 2024-11-16*
*Version: 0.1.0-alpha*
*Status: Week 1 POC Complete*

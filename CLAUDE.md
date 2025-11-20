# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Investment Memo Orchestrator: A multi-agent system using LangGraph to generate professional investment memos for Hypernova Capital. The system coordinates specialized AI agents that research, write, enrich, cite, and validate investment memos for both direct startup investments and LP fund commitments.

## Recent Changes (2025-11-20)

**Major architecture refactor**: The system now processes sections individually throughout the entire pipeline. This eliminates API timeout issues and ensures consistent citation formatting.

### What Changed
- **Section-by-section processing**: All enrichment agents now process individual section files instead of the full assembled memo
- **Citation consolidation**: Citations from all sections are renumbered globally and consolidated into ONE block at the end
- **Citation format standardized**: `[^1]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: N/A`
- **Dynamic version resolution**: New `get_latest_output_dir()` helper ensures all agents find the same output directory
- **No more timeouts**: Each section ~5k chars instead of full memo ~50k+ chars

See `changelog/2025-11-20_01.md` for complete details.

## Ongoing Troubleshooting

1. **Issue**: Dependencies keep disappearing after running `uv pip install -e .`  We need to find a way to have .venv activate effectively when initially running commands, and to ensure the program continues to be active with dependencies.


## Essential Commands

### Development Setup

**CRITICAL: This project uses `uv` for dependency management. NEVER use `pip` directly.**

```bash
# Create virtual environment with uv (Python 3.11+)
uv venv --python python3.11

# Activate the venv
source .venv/bin/activate

# Install ALL dependencies with uv (NOT pip)
uv pip install -e .

# Copy environment template and configure
cp .env.example .env
# Edit .env with your API keys
```

**Why dependencies keep disappearing**: Multiple broken venvs (`.venv`, `venv`) or using `pip` instead of `uv`. Always use the commands above.

### Running the System

**ALWAYS activate venv before running ANY commands:**
```bash
source .venv/bin/activate
```

Then run memo generation:
```bash
# Basic usage (default: direct investment, prospective analysis)
python -m src.main "Company Name"

# Direct investment with retrospective justification
python -m src.main "Company Name" --type direct --mode justify

# Fund commitment with prospective analysis
python -m src.main "Fund Name" --type fund --mode consider

# Interactive mode
python -m src.main
```

**Without activating**, use `.venv/bin/python` directly:
```bash
.venv/bin/python -m src.main "Company Name"
```

### Improving Individual Sections
When the full pipeline completes but some sections are missing or weak, use `improve-section.py` to target specific sections.

**IMPORTANT: Always use `.venv/bin/python` or activate venv first!**

```bash
# Activate venv first (recommended)
source .venv/bin/activate

# Then run commands:
python improve-section.py "Bear-AI" "Team"
python improve-section.py "Bear-AI" "Market Context"
python improve-section.py "Bear-AI" "Technology & Product" --version v0.0.1

# OR use venv Python directly without activating:
.venv/bin/python improve-section.py "Bear-AI" "Team"
.venv/bin/python improve-section.py output/Bear-AI-v0.0.1 "Team"
```

**Available section names:**
- Direct investment: "Executive Summary", "Business Overview", "Market Context", "Team", "Technology & Product", "Traction & Milestones", "Funding & Terms", "Risks & Mitigations", "Investment Thesis", "Recommendation"
- Fund commitment: "Executive Summary", "GP Background & Track Record", "Fund Strategy & Thesis", "Portfolio Construction", "Value Add & Differentiation", "Track Record Analysis", "Fee Structure & Economics", "LP Base & References", "Risks & Mitigations", "Recommendation"

**How it works:**
1. Loads existing artifacts (research, other sections, state)
2. If section exists: improves it by adding sources, removing speculation, strengthening analysis
3. If section missing: creates it from scratch using available research data
4. Saves improved section back to `2-sections/` directory
5. Preserves all other sections and artifacts

### Exports
```bash
# Activate venv first
source .venv/bin/activate

# Export to Word
python md2docx.py output/Company-v0.0.5/4-final-draft.md

# Export to branded HTML (light mode)
python export-branded.py output/Company-v0.0.5/4-final-draft.md

# Export to branded HTML (dark mode)
python export-branded.py output/Company-v0.0.5/4-final-draft.md --mode dark

# Export with custom brand
python export-branded.py memo.md --brand yourfirm

# Batch export all memos in both modes
./export-all-modes.sh
```

### Git-Based Versioning
```bash
# Check current version (derived from git tags)
python -c "from src import __version__; print(__version__)"

# Create a new release
git tag v0.2.0 -m "Release v0.2.0: Brief description"
git push origin v0.2.0
```

## Architecture & Workflow

### Multi-Agent Pipeline (Section-by-Section Processing)
The system uses a LangGraph state machine with specialized agents executing in sequence. **CRITICAL**: ALL enrichment agents now process section files individually to avoid API timeouts and ensure consistent formatting.

1. **Deck Analyst** (`src/agents/deck_analyst.py`) - Extracts info from pitch deck PDFs, creates initial section drafts
2. **Research** (`src/agents/research_enhanced.py`) - Web search via Tavily/Perplexity, synthesizes findings
3. **Writer** (`src/agents/writer.py`) - **SECTION-BY-SECTION**: Writes memo ONE SECTION AT A TIME (10 separate API calls)
   - Writes section 1 → saves to `2-sections/01-executive-summary.md`
   - Writes section 2 → saves to `2-sections/02-business-overview.md`
   - Continues until all 10 sections saved as individual files
   - Returns EMPTY `draft_sections` dict (sections live in files, not state)
   - Each section: ~500 words, ~5k chars (small API payload)
4. **Trademark Enrichment** (`src/agents/trademark_enrichment.py`) - Creates header file with company logo/trademark
   - Creates `header.md` file with company logo and date
   - Supports both light and dark mode logos (URLs or local paths)
   - Skips if no trademark paths provided in company data file
   - Uses `get_latest_output_dir()` to find correct output directory
5. **Socials Enrichment** (`src/agents/socials_enrichment.py`) - Adds LinkedIn links to team members
   - Loads `04-team.md` section file
   - Enriches with LinkedIn profile links
   - Saves enriched section back to file
6. **Link Enrichment** (`src/agents/link_enrichment.py`) - Adds organization/entity hyperlinks
   - Processes EACH section file independently
   - Adds markdown links to investors, competitors, partners, etc.
   - Saves enriched sections back to files
7. **Visualization Enrichment** (`src/agents/visualization_enrichment.py`) - **TEMPORARILY DISABLED**
   - Being refactored for section-by-section processing
   - Currently returns skip message
8. **Citation Enrichment** (`src/agents/citation_enrichment.py`) - **SECTION-BY-SECTION + CONSOLIDATION**
   - Loads each section file from `2-sections/`
   - Enriches with Perplexity Sonar Pro citations
   - Saves enriched section back
   - Renumbers citations globally ([^1][^2][^3]... sequentially across all sections)
   - Consolidates ALL citations into ONE block at the end
   - Assembles final `4-final-draft.md` with globally renumbered citations
9. **Citation Validator** (`src/agents/citation_validator.py`) - Validates citation accuracy, checks dates, detects duplicates
10. **Validator** (`src/agents/validator.py`) - Scores quality 0-10, provides specific feedback
11. **Supervisor** (`src/workflow.py`) - Routes to finalization (score ≥8) or human review (score <8)

### Why Section-by-Section Processing?
LLMs don't have the context window to reliably handle full memos (50k+ chars) in one API call. By processing ONE SECTION AT A TIME:
- Each API call: ~5k chars instead of ~50k chars
- Reduces connection timeouts (10 small calls vs 1 giant call)
- Enables progressive saving (work isn't lost if one section fails)
- Better error isolation (can retry individual sections)

### State Management
The `MemoState` TypedDict (src/state.py) flows through all agents:
- **Input**: company_name, investment_type ("direct"|"fund"), memo_mode ("consider"|"justify")
- **Company context**: description, url, stage, research_notes (loaded from data/{company}.json)
- **Deck analysis**: deck_path, deck_analysis (DeckAnalysisData)
- **Research phase**: research (ResearchData with sources/citations)
- **Writing phase**: draft_sections (dict of SectionDraft)
- **Validation phase**: validation_results, citation_validation, overall_score
- **Output**: final_memo, messages (append-only list)

### Artifact Trail System
Every workflow run saves to `output/{Company-Name}-v0.0.x/`:
- `0-deck-analysis.json` + `.md` - Pitch deck extraction (if deck provided)
- `1-research.json` + `.md` - Web search results and synthesis
- `2-sections/*.md` - Individual section drafts (all 10 sections)
- `3-validation.json` + `.md` - Validation scores and feedback
- `4-final-draft.md` - Complete memo with inline citations
- `state.json` - Full workflow state for debugging

Functions in `src/artifacts.py` handle all artifact saving.

### Dual-Template System
The system supports two investment types via template selection:

**Direct Investment** (`templates/memo-template-direct.md`):
- 10 sections for startup analysis
- Sections: Executive Summary, Business Overview, Market Context, Team, Technology & Product, Traction & Milestones, Funding & Terms, Risks & Mitigations, Investment Thesis, Recommendation

**Fund Commitment** (`templates/memo-template-fund.md`):
- 10 sections for LP diligence
- Sections: Executive Summary, GP Background & Track Record, Fund Strategy & Thesis, Portfolio Construction, Value Add & Differentiation, Track Record Analysis, Fee Structure & Economics, LP Base & References, Risks & Mitigations, Recommendation

Templates are selected in `writer.py` based on `state["investment_type"]`.

### Memo Modes
- **consider**: Prospective analysis for potential investments (recommendation: PASS/CONSIDER/COMMIT)
- **justify**: Retrospective justification for existing investments (recommendation: always COMMIT with rationale)

Mode affects the recommendation section and overall framing.

## Key Implementation Patterns

### Agent Structure
Each agent follows this pattern:
```python
def agent_name(state: MemoState) -> dict:
    """Agent function docstring."""
    # 1. Extract needed data from state
    company_name = state["company_name"]

    # 2. Call LLM or perform operations
    result = anthropic_client.invoke(...)

    # 3. Save artifacts (if applicable)
    save_artifacts(output_dir, result)

    # 4. Return state updates (dict merge)
    return {
        "field_name": updated_value,
        "messages": ["Status message"]
    }
```

### Workflow Graph Construction
`src/workflow.py` defines the graph in `build_workflow()`:
- Nodes are agent functions
- Edges define sequence
- Conditional edges handle branching (e.g., score-based routing)
- Entry point: `deck_analyst` (always runs, skips if no deck)
- End points: `finalize` or `human_review`

### Version Management
`src/versioning.py` handles semantic versioning:
- Auto-increments patch version per generation (v0.0.1 → v0.0.2)
- Tracks history in `output/versions.json`
- Minor/major bumps require manual tagging
- Git tags control package version (setuptools-scm)

### Brand Configuration System
Multi-brand export support via YAML configs in `templates/brand-configs/`:
- Create `brand-{name}-config.yaml` for each VC firm
- Configure colors, fonts, VC firm logos (header)
- `src/branding.py` loads configs and generates branded CSS
- `export-branded.py` applies branding to HTML exports

**Dual Trademark System:**
1. **VC Firm Logo** (Header): Configured in brand YAML, appears at top of every memo
   - Set via `logo.light_mode` and `logo.dark_mode` in brand config
   - Displayed in memo header with firm tagline
2. **Company Trademark** (Content): Configured in company data JSON, inserted into memo body
   - Set via `trademark_light` and `trademark_dark` in `data/{Company}.json`
   - Automatically inserted after header metadata by Trademark Enrichment Agent

See `templates/brand-configs/README.md` for complete documentation.

## Critical Code Locations

### Entry Points
- `src/main.py` - CLI entry, argument parsing, version display
- `src/workflow.py:generate_memo()` - Main orchestration function

### State & Schema
- `src/state.py` - All TypedDict schemas (MemoState, ResearchData, DeckAnalysisData, etc.)
- `src/state.py:create_initial_state()` - State initialization

### Core Agents
- `src/agents/research_enhanced.py` - Web search integration (Tavily/Perplexity)
- `src/agents/writer.py` - Template selection, section-by-section drafting
- `src/agents/trademark_enrichment.py` - Company logo/trademark insertion
- `src/agents/socials_enrichment.py` - LinkedIn profile link insertion
- `src/agents/link_enrichment.py` - Organization/investor hyperlink enrichment
- `src/agents/citation_enrichment.py` - Inline citation addition (Perplexity Sonar Pro)
- `src/agents/citation_validator.py` - Citation accuracy validation
- `src/agents/validator.py` - Quality scoring (0-10 scale)

### Utilities
- `src/artifacts.py` - All artifact saving functions
- `src/versioning.py` - Version management (VersionManager class)
- `src/branding.py` - Brand config loading and CSS generation

### Templates
- `templates/memo-template-direct.md` - Direct investment template
- `templates/memo-template-fund.md` - Fund commitment template
- `templates/style-guide.md` - Writing standards and tone

## Environment Variables

Required:
- `ANTHROPIC_API_KEY` - Claude API key

Recommended:
- `TAVILY_API_KEY` - For research phase (fast, reliable)
- `PERPLEXITY_API_KEY` - For citation enrichment (Sonar Pro model)

Optional:
- `USE_WEB_SEARCH=true` - Enable/disable web search
- `RESEARCH_PROVIDER=tavily` - Research provider choice (tavily/perplexity/claude)
- `MAX_SEARCH_RESULTS=10` - Results per query
- `DEFAULT_MODEL=claude-sonnet-4-5-20250929` - LLM model

## Company Data Files

Store company context in `data/{CompanyName}.json`:
```json
{
  "type": "direct",
  "mode": "justify",
  "description": "Brief company description for research context",
  "url": "https://company.com",
  "stage": "Series A",
  "deck": "data/CompanyName-deck.pdf",
  "trademark_light": "https://company.com/logo-light.svg",
  "trademark_dark": "https://company.com/logo-dark.svg",
  "notes": "Research focus: team backgrounds, competitive positioning, unit economics"
}
```

**Field Descriptions:**
- `type`: `"direct"` for startup investments, `"fund"` for LP commitments (overrides CLI `--type`)
- `mode`: `"consider"` for prospective analysis, `"justify"` for retrospective (overrides CLI `--mode`)
- `description`: Brief company description to guide research
- `url`: Company website URL
- `stage`: Investment stage (Seed, Series A, etc.)
- `deck`: Path to pitch deck PDF (relative to project root)
- `trademark_light`: URL or path to light mode company logo/trademark
- `trademark_dark`: URL or path to dark mode company logo/trademark
- `notes`: Specific research focus areas or instructions for agents

**Trademark Support:**
If trademark paths are provided, the **Trademark Enrichment Agent** automatically inserts the company logo into the memo content after the header metadata section. Light mode exports use `trademark_light`, dark mode exports use `trademark_dark`. Trademarks can be:
- **URLs**: Direct links to company logos (e.g., from company website)
- **Local paths**: Relative paths from project root (e.g., `templates/trademarks/company-logo.svg`)

File presence triggers automatic loading in `main.py`. CLI arguments override JSON values.

**Examples**: See `data/sample-company.json`, `data/TheoryForge.json`, `data/Powerline.json` for complete examples.

## Output Structure

Each generation creates:
```
output/
├── {Company-Name}-v0.0.x/
│   ├── 0-deck-analysis.json + .md
│   ├── 1-research.json + .md
│   ├── 2-sections/
│   │   ├── 01-executive-summary.md
│   │   └── ... (10 sections)
│   ├── 3-validation.json + .md
│   ├── 4-final-draft.md
│   └── state.json
└── versions.json  # Version history
```

## Citation System

The system uses Obsidian-style citations:
- **Inline format**: `[^1], [^2], [^3]` (with comma separators)
- **Citation list format**: `[^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD`
- **Spacing**: CSS applies 0.15em margins for readability
- **Validation**: Citation validator checks date accuracy, duplicate URLs, broken links

Citations flow through:
1. Research phase captures sources (ResearchData.sources)
2. Writer preserves sources in drafts
3. Citation enrichment adds inline refs via Perplexity Sonar Pro
4. Citation validator checks accuracy
5. Final draft includes complete citation list

## Common Development Scenarios

### Adding a New Agent
1. Create agent file in `src/agents/new_agent.py`
2. Define function: `def new_agent(state: MemoState) -> dict`
3. Import in `src/workflow.py`
4. Add node: `workflow.add_node("new_agent", new_agent)`
5. Add edge to sequence: `workflow.add_edge("previous_agent", "new_agent")`
6. Update `MemoState` in `src/state.py` if new state fields needed

### Modifying Template Structure
1. Edit `templates/memo-template-direct.md` or `templates/memo-template-fund.md`
2. Update section list in `src/agents/writer.py:SECTION_ORDER` if adding/removing sections
3. Update validation criteria in `src/agents/validator.py` if section evaluation changes

### Adding a New Brand
1. Copy `templates/brand-configs/brand-config.example.yaml`
2. Rename to `brand-{yourfirm}-config.yaml`
3. Customize colors, fonts, logo paths
4. Export with: `python export-branded.py memo.md --brand yourfirm`

### Debugging Workflow Issues
1. Check `output/{Company}-v0.0.x/state.json` for full state snapshot
2. Review individual artifacts (`1-research.md`, `2-sections/*.md`, `3-validation.md`)
3. Check terminal messages (each agent appends to `state["messages"]`)
4. Enable verbose logging in agent functions if needed

## Known Constraints

- **MUST USE `uv` for dependency management** - Never use `pip` directly, it breaks the venv
- Requires Python 3.11+ (type hints use newer syntax)
- Claude Sonnet 4.5 is the primary LLM (other models untested)
- PDF deck analysis requires readable text PDFs (scanned images won't work)
- Citation enrichment requires PERPLEXITY_API_KEY (skips if missing)
- Word export citations only render in Microsoft Word (not Google Docs/Preview)
- Git-based versioning requires git repository with tags

## Dependency Management (IMPORTANT)

**If you need to install or reinstall dependencies:**

1. **ONLY use `uv`** - This project uses `uv` for all package management
2. **Never use `pip`** - Using `pip` will break the virtual environment
3. **Single venv location** - Always use `.venv` (not `venv` or other names)

**If dependencies are missing:**
```bash
# Remove any broken venvs
rm -rf .venv venv

# Create fresh venv with uv
uv venv --python python3.11

# Install with uv (NOT pip)
uv pip install -e .
```

**Common mistake**: Running `pip install` or `python -m venv` instead of `uv` commands.

## Testing Notes

- POC testing on Aalo Atomics: score progression from 3.5/10 (no web search) → 8.5/10 (full pipeline)
- Validation threshold: 8/10 for auto-finalization
- Version auto-increments on each run (prevents overwrites)
- Artifact trail enables targeted improvements without full regeneration

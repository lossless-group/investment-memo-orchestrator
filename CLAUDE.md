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
- **NEW: Section improvement tool** (`improve-section.py`): Use Perplexity Sonar Pro to improve individual sections with automatic citations and final draft reassembly (commit: 6fbafe5)

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

When the full pipeline completes but some sections are missing or weak, use `improve-section.py` to target specific sections without regenerating the entire memo.

**Key Features**:
- Uses **Perplexity Sonar Pro** for real-time research and up-to-date information
- Automatically adds **citations** during improvement (Obsidian-style `[^1], [^2]`)
- **One-step process**: Research + improvement + citations in single API call
- Automatically **reassembles final draft** after improvement
- Preserves all other sections and artifacts unchanged

**IMPORTANT: Always use `.venv/bin/python` or activate venv first!**

**Requirements**:
- `PERPLEXITY_API_KEY` must be set in `.env` file
- Existing artifact directory with sections

```bash
# Activate venv first (recommended)
source .venv/bin/activate

# Basic usage: improve specific section
python improve-section.py "Avalanche" "Team"

# Specify version (default: latest)
python improve-section.py "Avalanche" "Team" --version v0.0.1

# Direct path to artifact directory
python improve-section.py output/Avalanche-v0.0.1 "Market Context"

# OR use venv Python directly without activating:
.venv/bin/python improve-section.py "Avalanche" "Team"
```

**Available section names:**
- Direct investment: "Executive Summary", "Business Overview", "Market Context", "Team", "Technology & Product", "Traction & Milestones", "Funding & Terms", "Risks & Mitigations", "Investment Thesis", "Recommendation"
- Fund commitment: "Executive Summary", "GP Background & Track Record", "Fund Strategy & Thesis", "Portfolio Construction", "Value Add & Differentiation", "Track Record Analysis", "Fee Structure & Economics", "LP Base & References", "Risks & Mitigations", "Recommendation"

**How it works:**
1. Loads existing artifacts (research, other sections, state)
2. Calls **Perplexity Sonar Pro** with comprehensive improvement prompt
3. If section exists: improves it by adding specific metrics, quality sources, removing vague language
4. If section missing: creates it from scratch using available research data
5. **Automatically adds inline citations** (`[^1]`, `[^2]`) during writing (not as separate step)
6. Saves improved section to `2-sections/{section-file}.md`
7. **Automatically reassembles `4-final-draft.md`** from all sections (includes header.md if present)
8. Shows citation count and improvement preview

**Example output:**
```
✓ Loaded state.json
✓ Loaded research data
✓ Loaded 10 existing sections

Improving section: Team
  Calling Perplexity Sonar Pro for real-time research and citations...

✓ Saved improved section to: output/Avalanche-v0.0.1/2-sections/04-team.md
✓ Final draft reassembled: output/Avalanche-v0.0.1/4-final-draft.md

Citations added: 11

Next steps:
  1. Review improved section in: output/Avalanche-v0.0.1/2-sections/
  2. View complete memo: output/Avalanche-v0.0.1/4-final-draft.md
  3. Export to HTML: python export-branded.py output/Avalanche-v0.0.1/4-final-draft.md --brand hypernova
```

**When to use:**
- One section is weak or lacks specific details
- Section is missing citations or has speculative language
- Need to add more metrics and concrete evidence
- Research data has been updated since generation
- Want to strengthen analysis in a specific area

**Performance:**
- Time: ~60 seconds per section (Sonar Pro call + reassembly)
- Cost: ~$0.75 per section (vs. ~$10 for full regeneration)
- Quality: Real-time web research + automatic citation enrichment

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

### Outline-Based Architecture (Preferred) with Template Fallback

**IMPORTANT**: This system uses **YAML outlines** for content structure, with markdown templates as fallback.

#### Content Structure Hierarchy

**Preferred: YAML Outlines** (`templates/outlines/`)
- Structured YAML files defining sections, questions, vocabulary, and preferred sources
- Self-contained and machine-readable
- Support inheritance and customization
- Enable section-specific research source targeting

**Fallback: Markdown Templates** (`templates/`)
- Legacy markdown templates used if no outline specified
- Basic section structure only
- Less flexible than YAML outlines

#### Two Investment Types

**Direct Investment**:
- **Outline**: `templates/outlines/direct-investment.yaml` (preferred)
- **Template**: `templates/memo-template-direct.md` (fallback)
- **10 sections**: Executive Summary, Business Overview, Market Context, Team, Technology & Product, Traction & Milestones, Funding & Terms, Risks & Mitigations, Investment Thesis, Recommendation

**Fund Commitment**:
- **Outline**: `templates/outlines/fund-commitment.yaml` (preferred)
- **Template**: `templates/memo-template-fund.md` (fallback)
- **10 sections**: Executive Summary, GP Background & Track Record, Fund Strategy & Thesis, Portfolio Construction, Value Add & Differentiation, Track Record Analysis, Fee Structure & Economics, LP Base & References, Risks & Mitigations, Recommendation

#### YAML Outline Structure

Each outline contains:
- **Metadata**: Outline type, version, compatibility
- **Vocabulary**: Global and section-specific terminology guidance
- **Sections**: For each section:
  - Number, name, filename
  - Target word counts (min/max/ideal)
  - Guiding questions (what to address)
  - Section-specific vocabulary
  - **Preferred sources** (Perplexity @ syntax and domains)
  - Mode-specific guidance (consider vs justify)
  - Validation criteria

**Example section structure:**
```yaml
sections:
  - number: 3
    name: "Market Context"
    filename: "03-market-context.md"
    guiding_questions:
      - "What is the TAM and how is it growing?"
      - "Who are key competitors?"
    preferred_sources:
      perplexity_at_syntax: ["@statista", "@cbinsights", "@pitchbook"]
      domains:
        include: ["statista.com", "cbinsights.com", "pitchbook.com"]
        exclude: ["*.top10.com", "*.saas-metrics.com"]
```

See `context-vigilance/Format-Memo-According-to-Template-Input.md` for complete architecture documentation.

#### Selection Logic

The writer agent selects content structure based on:
1. Check for custom outline in company data: `data/{Company}.json` → `"outline": "custom-name"`
2. Load custom outline from `templates/outlines/custom/{custom-name}.yaml` (if specified)
3. Otherwise load default outline: `templates/outlines/{investment_type}.yaml`
4. If outline not found, fallback to markdown template: `templates/memo-template-{type}.md`

#### Memo Modes
- **consider**: Prospective analysis for potential investments (recommendation: PASS/CONSIDER/COMMIT)
- **justify**: Retrospective justification for existing investments (recommendation: always COMMIT with rationale)

Mode affects the recommendation section and overall framing. Outlines include mode-specific guidance for each section.

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

### Brand Configuration System (Separate but Related)

**Important Distinction:**
- **Outlines** (`templates/outlines/`) = **Content structure** (sections, questions, vocabulary, sources)
- **Brand Configs** (`templates/brand-configs/`) = **Visual styling** (colors, fonts, logos, CSS)

These are separate systems that work together:
- **One outline** can be exported with **multiple brand configs** (e.g., Hypernova outline → export as Hypernova brand or Collide brand)
- **Multiple firms** can each have their own outline AND brand config
- Outlines control WHAT to write, Brand configs control HOW it looks when exported

**Multi-Brand Export Support:**
- Create `brand-{name}-config.yaml` for each VC firm in `templates/brand-configs/`
- Configure colors, fonts, VC firm logos (header), typography, spacing
- `src/branding.py` loads configs and generates branded CSS
- `export-branded.py` applies branding to HTML exports

**Example Multi-Firm Setup:**
```
templates/
├── outlines/
│   ├── direct-investment.yaml          # Default outline
│   ├── fund-commitment.yaml            # Default outline
│   └── custom/
│       ├── hypernova-direct.yaml       # Hypernova's content preferences
│       └── collide-direct.yaml         # Collide's content preferences
│
└── brand-configs/
    ├── brand-hypernova-config.yaml     # Hypernova's visual branding
    ├── brand-collide-config.yaml       # Collide's visual branding
    └── brand-example-config.yaml       # Template for new firms
```

A firm can customize BOTH content (outline) AND styling (brand config) independently.

**Dual Trademark System:**

The system supports logos/trademarks in two distinct locations within exported HTML memos:

1. **VC Firm Logo** (Header): Branding for the firm creating the memo
   - **Configuration**: Set in brand YAML config file (`templates/brand-configs/brand-{name}-config.yaml`)
   - **Fields**: `logo.light_mode` and `logo.dark_mode`
   - **Location**: Appears at the top of every exported HTML memo in the header section
   - **Display**: Shown with firm name, tagline, and metadata (date, prepared by, status)
   - **Supports both**:
     - **Remote URLs**: `https://example.com/logo.svg` (referenced via `<img>` tag)
     - **Local paths**: `templates/logos/firm-logo.svg` (embedded directly as SVG)
   - **Example**:
     ```yaml
     logo:
       light_mode: "https://ik.imagekit.io/example/logo-light.svg"
       dark_mode: "https://ik.imagekit.io/example/logo-dark.svg"
       width: "180px"
       height: "60px"
       alt: "Firm Name"
     ```

2. **Company/Fund Trademark** (Content): Logo of the company or fund being analyzed
   - **Configuration**: Set in company data JSON file (`data/{CompanyName}.json`)
   - **Fields**: `trademark_light` and `trademark_dark`
   - **Location**: Inserted into memo body content after header metadata, before main content
   - **Processing**: Automatically inserted by Trademark Enrichment Agent during workflow
   - **Supports both**:
     - **Remote URLs**: `https://company.com/trademark.svg`
     - **Local paths**: `templates/trademarks/company-logo.svg`
   - **Example**:
     ```json
     {
       "trademark_light": "https://company.com/logo-light.svg",
       "trademark_dark": "https://company.com/logo-dark.svg"
     }
     ```

**HTML Export Logo Handling:**

The `export-branded.py` script automatically detects logo type and handles appropriately:
- **URLs** (starting with `http://` or `https://`): Referenced via `<img src="URL">` tag
- **Local paths**: SVG files are embedded directly into HTML for offline viewing
- **Theme switching**: Light mode exports use `*_light` logos, dark mode uses `*_dark` logos
- **Validation**: Only local paths are checked for existence; URLs are assumed valid

**Implementation Details:**
- `export-branded.py:178-196`: Logo detection and embedding logic
- `src/branding.py:291-310`: Brand config validation (skips URL validation)
- `src/agents/trademark_enrichment.py`: Company trademark insertion into markdown

See `templates/brand-configs/README.md` for complete brand configuration documentation.

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

### Content Structure & Configuration
- **Outlines** (Preferred):
  - `templates/outlines/direct-investment.yaml` - Direct investment outline (preferred)
  - `templates/outlines/fund-commitment.yaml` - Fund commitment outline (preferred)
  - `templates/outlines/custom/` - Firm-specific outline customizations
  - `templates/outlines/sections-schema.json` - Validation schema for outlines
  - `templates/outlines/README.md` - Outline system documentation
- **Templates** (Fallback):
  - `templates/memo-template-direct.md` - Direct investment template (fallback)
  - `templates/memo-template-fund.md` - Fund commitment template (fallback)
  - `templates/style-guide.md` - Writing standards and tone
- **Brand Configs** (Visual Styling):
  - `templates/brand-configs/brand-{firm}-config.yaml` - Per-firm visual branding
  - `templates/brand-configs/README.md` - Brand configuration documentation

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
  "outline": "hypernova-direct",
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
- `outline`: Optional custom outline name (e.g., `"hypernova-direct"` loads `templates/outlines/custom/hypernova-direct.yaml`). If omitted, uses default outline based on type.
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

### Modifying Content Structure

**Preferred: Edit YAML Outlines**
1. Edit `templates/outlines/direct-investment.yaml` or `templates/outlines/fund-commitment.yaml`
2. Modify sections: add/remove/reorder, update guiding questions, vocabulary, preferred sources
3. Validate against schema: `templates/outlines/sections-schema.json`
4. Update validation criteria in outline's `validation_criteria` field
5. No code changes needed - agents read from outlines

**Fallback: Edit Markdown Templates** (if outline loading not yet implemented)
1. Edit `templates/memo-template-direct.md` or `templates/memo-template-fund.md`
2. Update section list in `src/agents/writer.py:SECTION_ORDER` if adding/removing sections
3. Update validation criteria in `src/agents/validator.py` if section evaluation changes

### Adding Firm-Specific Customization

**Custom Outline** (content preferences):
1. Create `templates/outlines/custom/{firm}-{type}.yaml`
2. Set `extends: "../direct-investment.yaml"` to inherit from default
3. Override specific sections or add firm vocabulary
4. Reference in company data: `"outline": "firm-direct"`

**Custom Brand Config** (visual styling):
1. Copy `templates/brand-configs/brand-config.example.yaml`
2. Rename to `brand-{firm}-config.yaml`
3. Customize colors, fonts, logos
4. Export with: `python export-branded.py memo.md --brand firm`

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

## Related Documentation

### Architecture & Design
- `context-vigilance/Format-Memo-According-to-Template-Input.md` - **Outline-based architecture** (YAML content structure system)
- `context-vigilance/Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` - Multi-agent workflow design
- `context-vigilance/Improving-Memo-Output.md` - Section improvement and quality enhancement

### Configuration
- `templates/outlines/README.md` - **Outline system documentation** (sections, questions, vocabulary, sources)
- `templates/brand-configs/README.md` - **Brand configuration guide** (visual styling, logos, colors)

### Development
- `context-vigilance/issue-resolution/Perplexity-Premium-API-Calls-Reference.md` - Premium data sources and @ syntax usage
- `changelog/` - Version history and feature updates

### Key Distinctions
- **Outlines** (`templates/outlines/`) = Content structure (what to write, which sources to use)
- **Brand Configs** (`templates/brand-configs/`) = Visual styling (how it looks when exported)
- **Templates** (`templates/*.md`) = Fallback for legacy markdown-based structure

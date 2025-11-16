# Investment Memo Orchestrator

Multi-agent orchestration system for generating high-quality investment memos using LangGraph and specialized AI agents.

**Status**: Week 1 POC Complete ✅

Sponsored by [Hypernova Capital](https://www.hypernova.capital)

## Overview

This system uses a supervisor pattern with specialized AI agents to generate investment memos that match Hypernova Capital's analytical standards. Instead of a single AI prompt, it coordinates multiple expert agents that research, write, validate, and iterate on memos.

## Key Features

### Multi-Agent Architecture
- **Research Agent**: Actively searches the web (Tavily/Perplexity) for company information, funding data, team backgrounds, and market context
- **Writer Agent**: Drafts professional memos following Hypernova's 10-section template and style guide
- **Validator Agent**: Rigorously evaluates quality (0-10 scale) with specific, actionable feedback
- **Supervisor**: Orchestrates workflow, manages state, routes to revision or finalization

### Web Search Integration
- Real-time company research via Tavily API or Perplexity API
- Multi-query strategy: company overview, funding, team, news
- Automatic source aggregation and synthesis
- Fallback to Claude-only mode (no API keys required for testing)

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

## Tech Stack

- **Orchestration**: LangGraph (Python) for multi-agent coordination
- **LLM**: Anthropic Claude Sonnet 4.5 for analysis and writing
- **Web Search**: Tavily API (recommended) or Perplexity API for research
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

```bash
# Generate a memo
python -m src.main "Company Name"

# Examples
python -m src.main "Aalo Atomics"
python -m src.main "OpenAI"

# Interactive mode
python -m src.main
```

### Output

Memos are saved to `output/` directory:
- `{company}-v0.0.1-draft.md` - The memo draft
- `{company}-v0.0.1-state.json` - Full workflow state
- `versions.json` - Version history across all iterations

## Architecture

### Workflow

```
┌──────────────┐
│  Supervisor  │ ← Coordinates workflow
└──────┬───────┘
       │
   ┌───┴────┐
   │Research│ ← Web search (4 queries) + synthesis
   └───┬────┘
       │
   ┌───┴────┐
   │ Writer │ ← Draft memo (10 sections)
   └───┬────┘
       │
   ┌───┴────────┐
   │ Validator  │ ← Score 0-10, identify issues
   └───┬────────┘
       │
   ┌───┴───────────────┐
   │   Score >= 8?     │
   └───┬───────────┬───┘
       │           │
   ┌───┴────┐  ┌──┴──────────┐
   │Finalize│  │Human Review │
   └────────┘  └─────────────┘
```

### State Management

```python
MemoState = {
    "company_name": str,
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
│   │   ├── researcher.py          # Basic research (no web search)
│   │   ├── research_enhanced.py   # Web search + synthesis
│   │   ├── writer.py              # Memo drafting
│   │   └── validator.py           # Quality validation
│   ├── state.py                   # TypedDict schemas
│   ├── workflow.py                # LangGraph orchestration
│   ├── versioning.py              # Version tracking system
│   └── main.py                    # CLI entry point
├── templates/
│   ├── memo-template.md           # 10-section structure
│   └── style-guide.md             # Writing standards
├── docs/
│   └── WEB_SEARCH_SETUP.md        # Search provider guide
├── changelog/
│   └── 2025-11-16_01.md           # Development log
├── output/                        # Generated memos
├── data/                          # Sample company data
└── tests/                         # Unit tests (TODO)
```

## Testing

### POC Test Results (Aalo Atomics)

**Without Web Search** (v0.0.0 equivalent):
- Score: 3.5/10
- Issues: 90% placeholders, no actual company data
- Output: Framework memo showing what should be evaluated

**With Web Search** (v0.0.1):
- Score: 7.5/10
- Real Data Found:
  - Founders: Matt Loszak (CEO), Yasir Arafat (CTO, ex-INL)
  - Funding: $136M total (Seed $6.3M, Series A $27M, Series B $100M)
  - Investors: Valor Equity Partners, NRG Energy, Hitachi Ventures
  - Location: Austin, Texas
  - Technology: 50 MWe modular reactors for AI data centers
- Issues: Source citations need improvement, some promotional language

## Current Capabilities ✅

- [x] Multi-agent orchestration (Research → Write → Validate)
- [x] Web search integration (Tavily/Perplexity)
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

# Web Search (choose one)
TAVILY_API_KEY=tvly-...         # Recommended for POC
PERPLEXITY_API_KEY=pplx-...     # Better quality, higher cost

# Optional
OPENAI_API_KEY=sk-...           # For future multi-model support

# Settings
USE_WEB_SEARCH=true             # Enable/disable web search
RESEARCH_PROVIDER=tavily        # tavily, perplexity, or claude
MAX_SEARCH_RESULTS=10           # Results per query
DEFAULT_MODEL=claude-sonnet-4-5-20250929
```

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

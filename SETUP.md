# Investment Memo Orchestrator - Setup Guide

## Prerequisites

- Python 3.11 or higher
- Anthropic API key (Claude)

## Installation

1. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -e .
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env and add your keys:
   # - ANTHROPIC_API_KEY (required for all operations)
   # - TAVILY_API_KEY (recommended for research)
   # - PERPLEXITY_API_KEY (required for citation enrichment)
   # See docs/WEB_SEARCH_SETUP.md for details
   ```

## Usage

### Generate a memo from the command line:

```bash
# Run from the project root
python -m src.main "Company Name"
```

### Interactive mode:
```bash
python -m src.main
# You'll be prompted for the company name
```

### Example:
```bash
python -m src.main "Aalo Atomics"
```

## Output

Each generation creates a versioned artifact directory:
```
output/{Company-Name}-v0.0.x/
├── 1-research.json          # Structured research data
├── 1-research.md            # Human-readable research summary
├── 2-sections/              # Individual section drafts (10 files)
│   ├── 01-executive-summary.md
│   ├── 02-business-overview.md
│   └── ... (all 10 sections)
├── 3-validation.json        # Validation scores and feedback
├── 3-validation.md          # Human-readable validation report
├── 4-final-draft.md         # Complete memo with inline citations
└── state.json               # Full workflow state for debugging
```

Plus `versions.json` tracking version history across all iterations.

## Project Structure

```
investment-memo-orchestrator/
├── src/
│   ├── agents/           # Agent implementations
│   │   ├── researcher.py # Research Agent
│   │   ├── writer.py     # Writer Agent
│   │   └── validator.py  # Validator Agent
│   ├── state.py          # State schema
│   ├── workflow.py       # LangGraph orchestration
│   └── main.py           # CLI entry point
├── templates/
│   ├── memo-template.md  # Memo structure
│   └── style-guide.md    # Writing standards
├── data/
│   └── sample-company.json # Sample test data
├── output/               # Generated memos (created at runtime)
└── tests/                # Unit tests (TODO)
```

## Development

### Running tests:
```bash
pytest tests/
```

### Code formatting:
```bash
black src/
ruff check src/
```

## Workflow Stages

The memo generation follows this sequence:

1. **Research Agent**: Gathers company and market data via Tavily web search
   - Saves: `1-research.json`, `1-research.md`
2. **Writer Agent**: Drafts memo following template (10 sections)
   - Saves: `2-sections/*.md` (10 individual section files)
3. **Citation-Enrichment Agent**: Adds inline citations using Perplexity Sonar Pro
   - Preserves narrative, adds [^1], [^2] citations with source list
4. **Validator Agent**: Checks quality and provides feedback
   - Saves: `3-validation.json`, `3-validation.md`
5. **Decision**:
   - Score >= 8: Auto-finalize
   - Score < 8: Human review required
   - Both save: `4-final-draft.md`, `state.json`

## Next Steps

This is a POC (Week 1 implementation). Future enhancements:

- **Week 2**: Add MCP servers for real data sources
- **Week 3**: Add specialized section writers and revision loop
- **Week 4**: Build web UI and production deployment

## Troubleshooting

### "ANTHROPIC_API_KEY not set"
Make sure you've created a `.env` file with your API key:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### Import errors
Make sure you installed the package:
```bash
pip install -e .
```

### Module not found
Make sure you're in the virtual environment:
```bash
source venv/bin/activate
```

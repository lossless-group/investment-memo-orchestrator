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
   # Edit .env and add your ANTHROPIC_API_KEY
   # Optional: Add TAVILY_API_KEY or PERPLEXITY_API_KEY for web search
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

Generated memos are saved to the `output/` directory:
- `{company-name}-memo.md` - The final memo
- `{company-name}-state.json` - Full workflow state (for debugging)

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

1. **Research Agent**: Gathers company and market data
2. **Writer Agent**: Drafts memo following template
3. **Validator Agent**: Checks quality and provides feedback
4. **Decision**:
   - Score >= 8: Auto-finalize
   - Score < 8: Human review required

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

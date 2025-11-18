# Project-Specific Instructions for Claude Code

## CRITICAL: Package Management

**ALWAYS USE `uv` FOR THIS PROJECT - NEVER USE `pip` DIRECTLY**

### Installing Dependencies

```bash
# ✓ CORRECT: Install project dependencies
uv pip install -e .

# ✓ CORRECT: Install specific package
uv pip install package-name

# ✗ WRONG: Never use pip directly
pip install -e .  # DON'T DO THIS
```

### Why uv?

- This project uses `uv` for fast, reliable Python package management
- Dependencies are defined in `pyproject.toml`
- The virtual environment is at `.venv/`
- Running `uv pip install -e .` installs the project in editable mode with all dependencies

### After Adding Dependencies to pyproject.toml

**ALWAYS run:**
```bash
uv pip install -e .
```

This ensures new dependencies in `pyproject.toml` are actually installed in the virtual environment.

## Python Commands

- Virtual environment: `.venv/` (managed by uv)
- Python version: 3.11+ (managed by pyenv)
- Both `python` and `python3` point to Python 3.11.9 via pyenv

### Running Scripts

```bash
# Main memo generation
python -m src.main "Company Name"

# Export scripts
python export-branded.py memo.md --brand collide
```

## Common Issues

### "No module named X" Error

**Solution:** Run `uv pip install -e .` to sync dependencies

### Dependencies Not Persisting

When you add a new dependency to `pyproject.toml`, you MUST run:
```bash
uv pip install -e .
```

Otherwise the dependency exists in the config but not in the virtual environment.

## Project Structure

- `src/` - Main application code
- `data/` - Input JSON files for companies
- `output/` - Generated memos
- `exports/` - Exported HTML/PDF files
- `templates/` - Branding templates and fonts
- `docs/` - Documentation

## Key Files

- `pyproject.toml` - Dependencies and project config
- `.env` - API keys (not in git)
- `brand-*-config.yaml` - Brand configurations for exports

## Branding

- Use `--brand <name>` to specify brand config
- Brand configs: `brand-<name>-config.yaml`
- Example: `brand-collide-config.yaml` for Collide Capital

## Remember

1. **Always use `uv`** for package management
2. **Run `uv pip install -e .`** after modifying `pyproject.toml`
3. Use `.venv/bin/python` or just `python` (pyenv manages it)
4. Brand configs support custom fonts with relative paths

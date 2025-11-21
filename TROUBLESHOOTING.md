# Troubleshooting Installation Issues

## Error: "No matching distribution found for langchain==1.0.7"

This means you have an outdated requirements.txt file. We upgraded to langchain 1.0.8.

**Fix:**
```bash
# 1. Make sure you've pulled the latest changes
git pull origin main

# 2. Check requirements.txt has the latest versions
grep "langchain==" requirements.txt
# Should show: langchain==1.0.8 (not 1.0.7)
```

---

## Error: "You are using pip version 21.2.4"

You're using `pip` directly, but this project uses `uv`. **NEVER use `pip` directly.**

**Fix:**
```bash
# 1. Install uv (if not already installed)
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with Homebrew:
brew install uv

# 2. Remove old venv
rm -rf .venv

# 3. Create fresh venv with uv
uv venv --python python3.11

# 4. Activate venv
source .venv/bin/activate

# 5. Install dependencies with uv (NOT pip!)
uv pip install -r requirements.txt
```

---

## Complete Fresh Setup (Recommended)

If you're having persistent issues, start completely fresh:

```bash
# 1. Pull latest changes
git pull origin main

# 2. Remove ALL old venvs
rm -rf .venv venv

# 3. Install uv if needed
brew install uv
# Or: curl -LsSf https://astral.sh/uv/install.sh | sh

# 4. Create fresh venv
uv venv --python python3.11

# 5. Activate venv
source .venv/bin/activate

# 6. Install dependencies with uv
uv pip install -r requirements.txt

# 7. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 8. Test installation
python -m src.main --help
```

---

## Key Rules

1. **ALWAYS use `uv` (NEVER use `pip` directly)**
   - ❌ `pip install -r requirements.txt`
   - ✅ `uv pip install -r requirements.txt`

2. **ALWAYS activate venv first**
   - ❌ `python -m src.main "Company"`
   - ✅ `source .venv/bin/activate && python -m src.main "Company"`

3. **ALWAYS use `.venv` (not `venv` or other names)**
   - Multiple venvs cause conflicts

4. **ALWAYS pull before installing**
   - `git pull` to get latest requirements.txt

---

## Verify Installation

After setup, verify everything works:

```bash
source .venv/bin/activate

# Check Python version
python --version
# Should show: Python 3.11.x

# Check dependencies installed
python -c "import anthropic, langchain, langgraph; print('✅ All imports successful')"

# Check command works
python -m src.main --help
```

---

## Current Dependency Versions (as of 2025-11-21)

- anthropic==0.74.1
- langchain==1.0.8
- langchain-core==1.0.7
- langgraph==1.0.3
- langgraph-prebuilt==1.0.5

If you see different versions in requirements.txt, run `git pull`.

---

## Still Having Issues?

1. Check you're in the right directory:
   ```bash
   pwd
   # Should end with: /investment-memo-orchestrator
   ```

2. Check requirements.txt exists and is up to date:
   ```bash
   ls -la requirements.txt
   head -20 requirements.txt
   ```

3. Check uv is installed:
   ```bash
   which uv
   uv --version
   # Should show uv 0.9.x or later
   ```

4. Check Python version:
   ```bash
   python3.11 --version
   # Need Python 3.11 or later
   ```

5. If all else fails, delete everything and start over:
   ```bash
   rm -rf .venv
   git pull origin main
   uv venv --python python3.11
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

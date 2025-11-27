---
title: Git Submodules for Private Data and Exports
lede: Configure git submodules to enable private GitHub repositories for sensitive company data inputs and branded memo exports, while keeping the main orchestrator repo public/shareable.
date_authored_initial_draft: 2025-11-27
date_authored_current_draft: 2025-11-27
date_authored_final_draft:
date_first_published:
date_last_updated: 2025-11-27
at_semantic_version: 0.1.0
status: Planning
augmented_with: Claude Code (Opus 4.5)
category: Infrastructure
tags: [Git, Submodules, Security, Configuration, Private-Data]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A diagram showing a main git repository with two submodule arrows pointing to separate private repositories, one labeled "data" containing company files, another labeled "exports" containing branded PDFs.
date_created: 2025-11-27
date_modified: 2025-11-27
---

# Git Submodules for Private Data and Exports

**Status**: Planning
**Date**: 2025-11-27
**Author**: AI Labs Team
**Related**: Multi-Agent-Orchestration-for-Investment-Memo-Generation.md

---

## Executive Summary

This document specifies how to use **git submodules** to separate sensitive/proprietary content from the main Investment Memo Orchestrator codebase. This enables:

1. **Private data inputs** (`data/`) in a separate private repo
2. **Private branded exports** (`exports/`) in a separate private repo
3. **Public/shareable orchestrator** code without exposing client information
4. **Firm-specific deployments** with different data/export repos per firm

---

## Problem Statement

### Current State

The orchestrator currently has hardcoded paths:
- **`data/`** — Company JSON files with sensitive deal information
- **`output/`** — Generated artifacts (intermediate, not for sharing)
- **`exports/`** — Branded HTML/PDF memos (final deliverables)

All three directories are in the same repository, creating issues:

**Issue #1: Cannot Share Orchestrator Code**
- Company data files contain confidential deal information
- Branded exports are proprietary deliverables
- Cannot open-source or share the tool without exposing client data

**Issue #2: No Multi-Firm Support**
- Different VC firms need different data and export destinations
- Currently everything is mixed in one repo
- No clean way to maintain firm-specific content separately

**Issue #3: Access Control Limitations**
- Cannot give collaborators access to code without data access
- Cannot share exports with LPs without exposing other companies
- No granular permissions model

### Desired State

```
investment-memo-orchestrator/     (PUBLIC or shared repo)
├── src/                          (code - shareable)
├── templates/                    (outlines, scorecards - shareable)
├── data/        → [SUBMODULE]   (private repo: hypernova-memo-data)
├── exports/     → [SUBMODULE]   (private repo: hypernova-memo-exports)
└── output/                       (local only, gitignored)
```

---

## Solution: Git Submodules

### What Are Git Submodules?

Git submodules allow embedding one git repository inside another as a subdirectory. The parent repo tracks a specific commit of the submodule, not its contents.

**Key characteristics**:
- Submodule contents are NOT stored in parent repo
- Parent repo stores only a reference (commit SHA)
- Submodules can have different access permissions
- Each submodule is cloned separately

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  investment-memo-orchestrator (PUBLIC/SHARED)                   │
│  github.com/lossless-group/investment-memo-orchestrator         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  src/                    ← Code (in main repo)                  │
│  templates/              ← Templates (in main repo)             │
│  context-vigilance/      ← Specs (in main repo)                 │
│                                                                 │
│  data/                   ← SUBMODULE (private repo)             │
│    └── .git → github.com/hypernova-capital/memo-data (PRIVATE)  │
│                                                                 │
│  exports/                ← SUBMODULE (private repo)             │
│    └── .git → github.com/hypernova-capital/memo-exports (PRIV)  │
│                                                                 │
│  output/                 ← LOCAL ONLY (gitignored)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Benefits

1. **Code Sharing**: Main repo can be public/shared without exposing data
2. **Access Control**: Different permissions per repo (data vs exports vs code)
3. **Multi-Firm**: Each firm can have their own data/exports repos
4. **LP Sharing**: Export repo can be shared with specific LPs
5. **Audit Trail**: Separate commit history for data changes vs code changes

---

## Implementation Plan

### Phase 1: Create Private Repositories

#### 1.1 Create Data Repository

**Repository**: `github.com/hypernova-capital/memo-data` (PRIVATE)

**Contents**:
```
memo-data/
├── README.md
├── .gitignore
│
├── companies/              # Company input files
│   ├── Avalanche.json
│   ├── Class5-Global.json
│   ├── Fernstone.json
│   └── ...
│
├── decks/                  # Pitch deck PDFs (optional)
│   ├── Avalanche-deck.pdf
│   └── ...
│
└── datarooms/              # Dataroom contents (optional)
    └── Hydden/
        └── ...
```

**Migration**:
```bash
# Create new private repo on GitHub first, then:
cd /tmp
mkdir memo-data && cd memo-data
git init

# Copy existing data
cp -r /path/to/investment-memo-orchestrator/data/* .

# Reorganize (optional - can keep flat structure)
mkdir -p companies decks
mv *.json companies/
mv *.pdf decks/ 2>/dev/null || true

# Initial commit
git add .
git commit -m "Initial data migration from orchestrator"
git remote add origin git@github.com:hypernova-capital/memo-data.git
git push -u origin main
```

#### 1.2 Create Exports Repository

**Repository**: `github.com/hypernova-capital/memo-exports` (PRIVATE)

**Contents**:
```
memo-exports/
├── README.md
├── .gitignore
│
├── branded/                # Final branded exports
│   ├── hypernova/
│   │   ├── light/
│   │   │   ├── Avalanche.html
│   │   │   └── Avalanche.pdf
│   │   └── dark/
│   │       ├── Avalanche.html
│   │       └── Avalanche.pdf
│   └── collide/
│       └── ...
│
└── docx/                   # Word exports
    ├── Avalanche.docx
    └── ...
```

**Migration**:
```bash
# Create new private repo on GitHub first, then:
cd /tmp
mkdir memo-exports && cd memo-exports
git init

# Copy existing exports
cp -r /path/to/investment-memo-orchestrator/exports/* .

# Initial commit
git add .
git commit -m "Initial exports migration from orchestrator"
git remote add origin git@github.com:hypernova-capital/memo-exports.git
git push -u origin main
```

---

### Phase 2: Configure Submodules in Orchestrator

#### 2.1 Remove Existing Directories

```bash
cd /path/to/investment-memo-orchestrator

# Backup first!
cp -r data data_backup
cp -r exports exports_backup

# Remove from git tracking (but keep files locally for now)
git rm -r --cached data/
git rm -r --cached exports/

# Update .gitignore
echo "# Submodules are tracked separately" >> .gitignore
echo "data/" >> .gitignore
echo "exports/" >> .gitignore
echo "output/" >> .gitignore

git add .gitignore
git commit -m "chore: Prepare for submodule migration - remove data/exports from tracking"
```

#### 2.2 Add Submodules

```bash
# Add data submodule
git submodule add git@github.com:hypernova-capital/memo-data.git data

# Add exports submodule
git submodule add git@github.com:hypernova-capital/memo-exports.git exports

# Commit submodule configuration
git add .gitmodules data exports
git commit -m "feat: Add git submodules for private data and exports"
```

#### 2.3 Resulting `.gitmodules` File

```ini
[submodule "data"]
    path = data
    url = git@github.com:hypernova-capital/memo-data.git

[submodule "exports"]
    path = exports
    url = git@github.com:hypernova-capital/memo-exports.git
```

---

### Phase 3: Update Application Code

#### 3.1 Create Configuration Module

**File**: `src/config.py`

```python
"""
Configuration for data and export paths.

Supports:
1. Default paths (data/, exports/) for submodule setup
2. Environment variable overrides for custom deployments
3. Absolute path support for non-submodule setups
"""

import os
from pathlib import Path

# Base directory (where the app is installed)
BASE_DIR = Path(__file__).parent.parent

# Data directory - where company JSON files live
# Override with DATA_DIR environment variable
DATA_DIR = Path(os.environ.get("MEMO_DATA_DIR", BASE_DIR / "data"))

# Output directory - intermediate artifacts (local, not shared)
# Override with OUTPUT_DIR environment variable
OUTPUT_DIR = Path(os.environ.get("MEMO_OUTPUT_DIR", BASE_DIR / "output"))

# Exports directory - final branded deliverables
# Override with EXPORTS_DIR environment variable
EXPORTS_DIR = Path(os.environ.get("MEMO_EXPORTS_DIR", BASE_DIR / "exports"))


def get_data_dir() -> Path:
    """Get the data directory path, creating if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_output_dir() -> Path:
    """Get the output directory path, creating if needed."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def get_exports_dir() -> Path:
    """Get the exports directory path, creating if needed."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORTS_DIR


def get_company_data_path(company_name: str) -> Path:
    """Get path to company data file."""
    # Check in companies/ subdirectory first (new structure)
    companies_dir = DATA_DIR / "companies"
    if companies_dir.exists():
        return companies_dir / f"{company_name}.json"
    # Fall back to flat structure (legacy)
    return DATA_DIR / f"{company_name}.json"


def validate_paths():
    """Validate that required directories exist and are accessible."""
    issues = []

    if not DATA_DIR.exists():
        issues.append(f"Data directory not found: {DATA_DIR}")
        issues.append("  - Run: git submodule update --init")
        issues.append("  - Or set MEMO_DATA_DIR environment variable")

    if not EXPORTS_DIR.exists():
        issues.append(f"Exports directory not found: {EXPORTS_DIR}")
        issues.append("  - Run: git submodule update --init")
        issues.append("  - Or set MEMO_EXPORTS_DIR environment variable")

    if issues:
        print("Configuration issues detected:")
        for issue in issues:
            print(f"  {issue}")
        return False

    return True
```

#### 3.2 Update Existing Code References

**Files to update** (replace hardcoded `Path("data")` and `Path("output")`):

| File | Current | Updated |
|------|---------|---------|
| `src/main.py:127` | `Path(f"data/{company_name}.json")` | `get_company_data_path(company_name)` |
| `src/main.py:270` | `Path("output")` | `get_output_dir()` |
| `src/artifacts.py:40` | `Path("output")` | `get_output_dir()` |
| `src/artifacts.py:66` | `Path("output")` | `get_output_dir()` |
| `src/artifacts.py:104` | `Path("output")` | `get_output_dir()` |
| `src/workflow.py:121` | `Path("output")` | `get_output_dir()` |
| `src/workflow.py:126` | `Path("output")` | `get_output_dir()` |
| `src/utils.py:21` | `Path("output")` | `get_output_dir()` |
| `src/agents/writer.py:545` | `Path("output")` | `get_output_dir()` |
| `src/agents/writer.py:548` | `Path("output")` | `get_output_dir()` |
| `src/agents/validator.py:206` | `Path("output")` | `get_output_dir()` |
| `src/agents/research_enhanced.py:543` | `Path("output")` | `get_output_dir()` |
| `src/agents/dataroom/analyzer.py:421` | `Path("output")` | `get_output_dir()` |
| `src/agents/perplexity_section_researcher.py:205` | `Path("output")` | `get_output_dir()` |

**Example update for `src/main.py`**:

```python
# Before
from pathlib import Path
data_file = Path(f"data/{company_name}.json")

# After
from src.config import get_company_data_path
data_file = get_company_data_path(company_name)
```

**Example update for `src/artifacts.py`**:

```python
# Before
from pathlib import Path
output_dir = Path("output") / f"{safe_name}-{version}"

# After
from src.config import get_output_dir
output_dir = get_output_dir() / f"{safe_name}-{version}"
```

#### 3.3 Update Export Scripts

**File**: `export-branded.py`

```python
# Add at top
from src.config import get_exports_dir, get_output_dir

# Update default output path
def main():
    parser = argparse.ArgumentParser(...)
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=None,  # Will use get_exports_dir() if not specified
        help='Output directory (default: exports/branded/)'
    )

    args = parser.parse_args()

    # Default to exports directory from config
    output_dir = args.output or (get_exports_dir() / "branded")
```

---

### Phase 4: Update Documentation

#### 4.1 Update README.md

Add section on submodule setup:

```markdown
## Installation

### Clone with Submodules

```bash
# Clone with submodules in one command
git clone --recurse-submodules git@github.com:lossless-group/investment-memo-orchestrator.git

# Or if already cloned:
git submodule update --init --recursive
```

### Private Data Access

This repo uses git submodules for private data:
- `data/` → Private company data repository
- `exports/` → Private branded exports repository

**If you don't have access to the private repos**, you can:
1. Create your own data directory with company JSON files
2. Set environment variables to point to your directories:

```bash
export MEMO_DATA_DIR=/path/to/your/data
export MEMO_EXPORTS_DIR=/path/to/your/exports
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMO_DATA_DIR` | `./data` | Company data files location |
| `MEMO_OUTPUT_DIR` | `./output` | Intermediate artifacts |
| `MEMO_EXPORTS_DIR` | `./exports` | Final branded exports |
```

#### 4.2 Update CLAUDE.md

Add to the "Essential Commands" section:

```markdown
### Submodule Management

```bash
# Initialize submodules after clone
git submodule update --init --recursive

# Update submodules to latest
git submodule update --remote

# Check submodule status
git submodule status

# If submodules are not configured, set custom paths:
export MEMO_DATA_DIR=/path/to/data
export MEMO_OUTPUT_DIR=/path/to/output
export MEMO_EXPORTS_DIR=/path/to/exports
```
```

---

### Phase 5: Workflow Updates

#### 5.1 Committing Data Changes

When adding/modifying company data:

```bash
# Navigate to data submodule
cd data

# Make changes
vim companies/NewCompany.json

# Commit in submodule
git add .
git commit -m "Add NewCompany data file"
git push

# Back to main repo - update submodule reference
cd ..
git add data
git commit -m "Update data submodule reference"
git push
```

#### 5.2 Committing Export Changes

When generating new exports:

```bash
# Generate exports (they go to exports/ submodule)
python export-branded.py output/Company-v0.0.1/4-final-draft.md

# Navigate to exports submodule
cd exports

# Commit new exports
git add .
git commit -m "Add Company branded exports"
git push

# Back to main repo - update submodule reference
cd ..
git add exports
git commit -m "Update exports submodule reference"
git push
```

#### 5.3 Automated Submodule Commits (Optional)

Add helper script `scripts/commit-exports.sh`:

```bash
#!/bin/bash
# Commit and push exports submodule

cd exports
git add .
git commit -m "Export: $(date +%Y-%m-%d) batch update"
git push
cd ..
git add exports
git commit -m "chore: Update exports submodule"
git push
```

---

## Multi-Firm Configuration

### Scenario: Different Data Repos per Firm

For supporting multiple VC firms with different data:

**Firm A (Hypernova)**:
```bash
export MEMO_DATA_DIR=/path/to/hypernova-data
export MEMO_EXPORTS_DIR=/path/to/hypernova-exports
```

**Firm B (Collide)**:
```bash
export MEMO_DATA_DIR=/path/to/collide-data
export MEMO_EXPORTS_DIR=/path/to/collide-exports
```

### Scenario: Shared Code, Private Data

```
orchestrator/              (PUBLIC - lossless-group/investment-memo-orchestrator)
├── src/
├── templates/
├── data -> (not tracked, each firm provides their own)
└── exports -> (not tracked, each firm provides their own)

hypernova-deployment/      (PRIVATE - hypernova-capital/memo-deployment)
├── data/                  (actual company data)
├── exports/               (actual exports)
└── .env                   (sets MEMO_DATA_DIR, MEMO_EXPORTS_DIR)
```

---

## Testing the Migration

### Test 1: Fresh Clone

```bash
# Clone without submodules
git clone git@github.com:lossless-group/investment-memo-orchestrator.git test-clone
cd test-clone

# Verify data/ and exports/ are empty directories
ls -la data/
ls -la exports/

# Initialize submodules
git submodule update --init

# Verify data files are now present
ls -la data/
```

### Test 2: Environment Variable Override

```bash
# Create test data directory
mkdir -p /tmp/test-data
echo '{"type": "direct", "description": "Test"}' > /tmp/test-data/TestCompany.json

# Run with override
export MEMO_DATA_DIR=/tmp/test-data
python -m src.main "TestCompany" --type direct
```

### Test 3: Path Validation

```bash
# Test path validation
python -c "from src.config import validate_paths; validate_paths()"
```

---

## Rollback Plan

If submodule migration causes issues:

```bash
# Remove submodules
git submodule deinit -f data
git submodule deinit -f exports
git rm -f data exports
rm -rf .git/modules/data .git/modules/exports

# Restore from backup
cp -r data_backup data
cp -r exports_backup exports

# Re-add to git
git add data exports
git commit -m "Revert submodule migration"
```

---

## Security Considerations

### Access Control Matrix

| Repo | Access | Who |
|------|--------|-----|
| `investment-memo-orchestrator` | Public/Team | All developers |
| `memo-data` | Private | Investment team only |
| `memo-exports` | Private | Investment team + LPs (selective) |

### Sensitive Data Checklist

Ensure these stay in private repos:
- [ ] Company JSON files (deal terms, valuations)
- [ ] Pitch deck PDFs
- [ ] Dataroom contents
- [ ] Branded memo exports
- [ ] Internal notes and corrections

### Do NOT Commit to Main Repo

- Company names in code comments
- Example data with real companies
- Screenshots of exports
- Log files with company data

---

## Implementation Checklist

### Preparation
- [ ] Create GitHub private repo: `memo-data`
- [ ] Create GitHub private repo: `memo-exports`
- [ ] Backup existing `data/` directory
- [ ] Backup existing `exports/` directory

### Migration
- [ ] Migrate data files to new repo
- [ ] Migrate export files to new repo
- [ ] Remove `data/` and `exports/` from orchestrator tracking
- [ ] Add `.gitmodules` with submodule configuration
- [ ] Update `.gitignore`

### Code Updates
- [ ] Create `src/config.py` with path configuration
- [ ] Update `src/main.py` to use config
- [ ] Update `src/artifacts.py` to use config
- [ ] Update `src/workflow.py` to use config
- [ ] Update `src/utils.py` to use config
- [ ] Update all agent files to use config
- [ ] Update `export-branded.py` to use config
- [ ] Add path validation to startup

### Documentation
- [ ] Update README.md with submodule instructions
- [ ] Update CLAUDE.md with submodule commands
- [ ] Add environment variable documentation

### Testing
- [ ] Test fresh clone with submodule init
- [ ] Test environment variable overrides
- [ ] Test memo generation end-to-end
- [ ] Test export generation
- [ ] Test without submodule access (graceful failure)

---

## Related Documentation

- `Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` - Main architecture
- `CLAUDE.md` - Developer guide (to be updated)
- Git submodules documentation: https://git-scm.com/book/en/v2/Git-Tools-Submodules

---

## Changelog

**2025-11-27**:
- Document created with full implementation plan
- Defined two-repo structure (data + exports)
- Specified code changes needed for path configuration
- Added multi-firm support considerations

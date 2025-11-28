# Firm and Deal-Based File Organization System

## Needs Thinking

- [ ] Custom Configs are loaded from `io/{firm}/config/*'
  - [ ] Outlines
  - [ ] Scorecards
  - [ ] Brand Configs
- [ ] Examples and a Generator script are provided for each firm
- [ ] Viable refactor of current IO system for painless migration with few bugs.

## Overview

Refactor the current flat `output/` and `data/` directory structure into a hierarchical `io/` directory organized by firm and deal. This enables:

1. **Improved navigability** as memo generation scales across multiple firms and deals
2. **Git submodule support** for firms to maintain private repositories for their IO data
3. **Clear separation** between the open-source orchestrator code and proprietary firm data

## Current Structure (Problems)

```
investment-memo-orchestrator/
├── data/                           # Mixed: all firms' input data
│   ├── Aito.json
│   ├── Avalanche.json
│   ├── TheoryForge.json
│   └── Hydden-deck.pdf
├── output/                         # Mixed: all firms' generated memos
│   ├── Aito-v0.0.1/
│   ├── Avalanche-v0.0.3/
│   └── TheoryForge-v0.0.2/
└── exports/                        # Mixed: all firms' exported files
    ├── light/
    └── dark/
```

**Problems:**
- All firms' data mixed together
- No clear ownership boundaries
- Can't easily gitignore or submodule firm-specific data
- Difficult to navigate at scale (50+ deals across 3+ firms)
- No separation between inputs (decks, datarooms) and outputs (memos, scorecards)

## Proposed Structure

```
investment-memo-orchestrator/
├── io/                                    # NEW: All firm IO in one place
│   ├── .gitignore                         # Ignore all firm dirs by default
│   ├── README.md                          # Instructions for setting up firm dirs
│   │
│   ├── Hypernova-Capital/                 # Firm directory (example 1)
│   │   ├── firm-config.yaml               # Firm-level settings, brand reference
│   │   ├── Deals/
│   │   │   ├── Ontra/                     # Deal directory
│   │   │   │   ├── inputs/                # Source materials
│   │   │   │   │   ├── deal.json          # Deal metadata (replaces data/*.json)
│   │   │   │   │   ├── deck.pdf           # Pitch deck
│   │   │   │   │   └── dataroom/          # Dataroom documents
│   │   │   │   ├── outputs/               # Generated artifacts (versioned)
│   │   │   │   │   ├── v0.0.1/
│   │   │   │   │   │   ├── 0-deck-analysis.json
│   │   │   │   │   │   ├── 1-research.json
│   │   │   │   │   │   ├── 2-sections/
│   │   │   │   │   │   ├── 3-validation.json
│   │   │   │   │   │   ├── 4-final-draft.md
│   │   │   │   │   │   ├── scorecard.md
│   │   │   │   │   │   └── state.json
│   │   │   │   │   └── v0.0.2/
│   │   │   │   └── exports/               # Exported formats
│   │   │   │       ├── light/
│   │   │   │       │   └── Ontra-v0.0.2.html
│   │   │   │       └── dark/
│   │   │   │           └── Ontra-v0.0.2.html
│   │   │   │
│   │   │   ├── Aito/
│   │   │   │   ├── inputs/
│   │   │   │   ├── outputs/
│   │   │   │   └── exports/
│   │   │   │
│   │   │   └── TheoryForge/
│   │   │       ├── inputs/
│   │   │       ├── outputs/
│   │   │       └── exports/
│   │   │
│   │   └── versions.json                  # Firm-level version tracking
│   │
│   └── Avalanche-VC/                      # Firm directory (example 2)
│       ├── firm-config.yaml
│       ├── Deals/
│       │   ├── Hydden/
│       │   │   ├── inputs/
│       │   │   ├── outputs/
│       │   │   └── exports/
│       │   └── SomeOtherDeal/
│       │       ├── inputs/
│       │       ├── outputs/
│       │       └── exports/
│       └── versions.json
│
├── templates/                             # UNCHANGED: Shared templates
│   ├── outlines/
│   ├── scorecards/
│   └── brand-configs/
│
└── src/                                   # UNCHANGED: Core code
```

## Git Submodule Strategy

Each firm directory can be a separate private git repository, linked as a submodule:

```bash
# Initial setup (orchestrator maintainer)
cd investment-memo-orchestrator
mkdir -p io
echo "*" > io/.gitignore
echo "!.gitignore" >> io/.gitignore
echo "!README.md" >> io/.gitignore

# Firm setup (each firm does this)
cd io
git submodule add git@github.com:hypernova-capital/memo-io.git Hypernova-Capital
git submodule add git@github.com:avalanche-vc/memo-io.git Avalanche-VC
```

**Benefits:**
- Orchestrator repo stays public and open-source
- Each firm's IO data lives in their own private repo
- Firms can manage access control independently
- Updates to orchestrator don't affect firm data
- Firm data can have its own commit history, branches, etc.

## File Reference Changes

### deal.json (replaces data/*.json)

Location: `io/{Firm}/Deals/{DealName}/inputs/deal.json`

```json
{
  "name": "Ontra",
  "type": "direct",
  "mode": "consider",
  "outline": "direct-investment",
  "description": "AI-powered contract automation for private markets",
  "url": "https://ontra.ai",
  "stage": "Series C",
  "deck": "deck.pdf",
  "dataroom": "dataroom/",
  "trademark_light": "https://ontra.ai/logo-light.svg",
  "trademark_dark": "https://ontra.ai/logo-dark.svg",
  "notes": "Focus on competitive positioning vs Ironclad, unit economics"
}
```

**Changes:**
- `deck` path is now relative to `inputs/` directory
- `dataroom` path is now relative to `inputs/` directory
- No need for full paths; system resolves based on deal location

### firm-config.yaml

Location: `io/{Firm}/firm-config.yaml`

```yaml
firm:
  name: "Hypernova Capital"
  brand: "hypernova"  # References templates/brand-configs/brand-hypernova-config.yaml

defaults:
  outline: "direct-investment"
  mode: "consider"

scorecard:
  template: "hypernova-emerging-manager"  # For fund deals

export:
  default_mode: "dark"
  auto_export: true
```

## CLI Changes

### Current Commands

```bash
# Current: company name, searches data/ and output/
python -m src.main "Ontra"
python cli/generate_scorecard.py "Ontra"
python export-branded.py output/Ontra-v0.0.1/4-final-draft.md
```

### Proposed Commands

```bash
# New: firm and deal specification
python -m src.main --firm "Hypernova-Capital" --deal "Ontra"

# Or use path directly
python -m src.main io/Hypernova-Capital/Deals/Ontra

# Short form with default firm (set in .env or config)
export MEMO_DEFAULT_FIRM="Hypernova-Capital"
python -m src.main "Ontra"

# Scorecard generation
python cli/generate_scorecard.py --firm "Hypernova-Capital" --deal "Ontra"

# Export
python cli/export_branded.py --firm "Hypernova-Capital" --deal "Ontra" --version v0.0.2
```

### Path Resolution Logic

```python
def resolve_deal_path(firm: str, deal: str) -> Path:
    """Resolve deal directory from firm and deal names."""
    io_root = Path("io")
    deal_path = io_root / firm / "Deals" / deal

    if not deal_path.exists():
        raise FileNotFoundError(f"Deal not found: {deal_path}")

    return deal_path

def get_deal_inputs(deal_path: Path) -> Path:
    return deal_path / "inputs"

def get_deal_outputs(deal_path: Path) -> Path:
    return deal_path / "outputs"

def get_deal_exports(deal_path: Path) -> Path:
    return deal_path / "exports"

def get_latest_version(deal_path: Path) -> str:
    outputs = deal_path / "outputs"
    versions = sorted([d.name for d in outputs.iterdir() if d.is_dir()])
    return versions[-1] if versions else "v0.0.1"
```

## Migration Plan

### Phase 1: Create New Structure (Non-Breaking)

1. Create `io/` directory with README and .gitignore
2. Create example firm directories
3. Add new path resolution utilities in `src/paths.py`
4. Update CLI to support `--firm` and `--deal` flags
5. Keep backward compatibility with `data/` and `output/`

### Phase 2: Dual-Mode Operation

1. CLI checks for deal in `io/{firm}/Deals/{deal}` first
2. Falls back to legacy `data/{deal}.json` and `output/{deal}-v*/`
3. Add migration helper: `python cli/migrate_deal.py "Ontra" --to-firm "Hypernova-Capital"`

### Phase 3: Documentation & Examples

1. Update README with new directory structure
2. Add `io/README.md` with setup instructions
3. Document git submodule workflow
4. Create example firm with sample deal

### Phase 4: Deprecate Legacy Paths

1. Add deprecation warnings for `data/` and `output/` usage
2. Update all documentation
3. Eventually remove legacy path support

## Files to Modify

### New Files

| File | Purpose |
|------|---------|
| `io/.gitignore` | Ignore firm directories by default |
| `io/README.md` | Instructions for firm setup |
| `src/paths.py` | Path resolution utilities |
| `cli/migrate_deal.py` | Migration helper script |

### Modified Files

| File | Changes |
|------|---------|
| `src/main.py` | Add `--firm` and `--deal` flags |
| `src/workflow.py` | Use new path resolution |
| `src/artifacts.py` | Save to deal-specific outputs/ |
| `src/versioning.py` | Firm-scoped version tracking |
| `cli/generate_scorecard.py` | Add firm/deal resolution |
| `cli/export_branded.py` | Add firm/deal resolution, export to deal exports/ |
| `cli/improve-section.py` | Add firm/deal resolution |
| `cli/refocus_section.py` | Add firm/deal resolution |
| `cli/recompile_memo.py` | Add firm/deal resolution |

## Environment Variables

```bash
# .env additions
MEMO_DEFAULT_FIRM="Hypernova-Capital"    # Default firm when not specified
MEMO_IO_ROOT="io"                         # Override IO root (default: io/)
```

## Backward Compatibility

During migration, the system should:

1. Check `io/{firm}/Deals/{deal}` first (new structure)
2. Fall back to `data/{deal}.json` + `output/{deal}-v*/` (legacy)
3. Log deprecation warning when using legacy paths
4. Allow `--legacy` flag to force old behavior

## Questions to Resolve

1. **Version tracking**: Per-deal `versions.json` or per-firm `versions.json`?
   - Recommendation: Per-firm, with deal name as key

2. **Brand configs**: Stay in `templates/brand-configs/` or move to `io/{firm}/`?
   - Recommendation: Stay in templates (shared resource), firm-config.yaml references by name

3. **Scorecards**: Stay in `templates/scorecards/` or allow firm-specific?
   - Recommendation: Both - templates/ for shared, io/{firm}/scorecards/ for firm-specific

4. **Default firm**: Set via `.env`, CLI flag, or interactive prompt?
   - Recommendation: All three, with precedence: CLI > .env > prompt

## Success Criteria

- [ ] Firms can maintain private repos for their IO data
- [ ] Clear separation between orchestrator code and firm data
- [ ] Easy navigation at scale (100+ deals across 5+ firms)
- [ ] Backward compatible during migration period
- [ ] Submodule workflow documented and tested
- [ ] All CLI commands support `--firm` and `--deal` flags

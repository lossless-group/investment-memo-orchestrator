# Firm and Deal-Based File Organization System

## Implementation Progress

**Last Updated**: 2025-12-02

### Completed

- [x] **Git submodule created**: `io/hypernova` linked to private repository (commit: 9216a84)
- [x] **Versioning system refactored**: `src/versioning.py` supports firm-scoped and legacy modes
- [x] **Migration CLI created**: `cli/migrate_versions.py` for migrating version history
- [x] **17 deals migrated to `io/hypernova/deals/`**:
  - Aalo, Aito, Andela, Avalanche, BlueLayer, Bruin, Class5-Global
  - DontQuitVentures, Harmonic, KearnyJackson, Ontra, Star-Catcher
  - TheoryForge, Thinking-Machines, Trela, WatershedVC, Yassir
- [x] **Firm versions.json populated**: `io/hypernova/versions.json` with 15 deals tracked
- [x] **Legacy data files moved**: 14 `data/*.json` files moved to submodule

#### Phase 1: Path Resolution ✅ COMPLETED
- [x] **`src/paths.py` created** - Centralized path resolution with `DealContext` dataclass
  - `resolve_deal_context()` - Resolves firm and deal paths with priority system
  - `get_latest_output_dir_for_deal()` - Gets latest versioned output directory
  - Priority: explicit firm → MEMO_DEFAULT_FIRM env → auto-detect from io/ → legacy fallback
- [x] **`src/utils.py` updated** - `get_latest_output_dir()` now supports `firm` parameter
- [x] **`src/main.py` updated** - Added `--firm` and `--deal` CLI flags
- [x] **`src/workflow.py` updated** - `generate_memo()` accepts and passes `firm` parameter
- [x] **`src/artifacts.py` updated** - `create_artifact_directory()` supports firm-scoped outputs
- [x] **`src/state.py` updated** - Added `firm: Optional[str]` to `MemoState`
- [x] **All 10 agents updated** to extract `firm` from state and pass to `get_latest_output_dir()`:
  - citation_enrichment.py, fact_checker.py, link_enrichment.py
  - perplexity_section_researcher.py, portfolio_listing_agent.py
  - scorecard_agent.py, scorecard_evaluator.py, socials_enrichment.py
  - toc_generator.py, trademark_enrichment.py

#### Phase 3: Dual-Mode & Environment ✅ COMPLETED
- [x] **Dual-mode operation implemented**: Checks io/{firm}/deals/{deal}/ first, falls back to legacy
- [x] **MEMO_DEFAULT_FIRM environment variable**: Supported in path resolution
- [x] **Auto-detection**: Can find firm from io/ directory when deal exists

#### Phase 2: CLI Updates ✅ COMPLETED
- [x] `cli/improve_section.py` - Added `--firm` and `--deal` flags, auto-detection, firm-scoped path resolution
- [x] `cli/export_branded.py` - Added `--firm`, `--deal`, and `--version` flags, exports to firm-scoped `exports/` directory
- [x] `cli/score_memo.py` - Added `--firm` and `--deal` flags with auto-detection fallback
- [x] `cli/refocus_section.py` - Added `--firm` and `--deal` flags with full path resolution
- [x] `cli/recompile_memo.py` - Added `--firm` and `--deal` flags with auto-detection

### Remaining Work

#### Phase 4: Documentation
- [ ] Update `README.md` with new structure
- [ ] Create `io/README.md` with setup instructions
- [ ] Update `CLAUDE.md` with new paths

#### Phase 5: Firm-Specific Templates ✅ COMPLETED
- [x] **Firm templates structure**: `io/{firm}/templates/` for firm-specific content structure
  - `io/{firm}/templates/outlines/` - Firm-specific outlines (e.g., `direct-early-stage-12Ps.yaml`)
  - `io/{firm}/templates/scorecards/` - Firm-specific scorecards
- [x] **Firm configs structure**: `io/{firm}/configs/` for runtime settings
  - `io/{firm}/configs/brand-{firm}-config.yaml` - Brand styling

### Remaining Work

#### Phase 6: Template Loading
- [ ] Update `src/outline_loader.py` to check `io/{firm}/templates/outlines/` first
- [ ] Update `src/scorecard_loader.py` to check `io/{firm}/templates/scorecards/` first
- [ ] Fallback to shared `templates/` if not found in firm directory

#### Phase 4: Documentation
- [ ] Update `README.md` with new structure
- [ ] Create `io/README.md` with setup instructions
- [ ] Update `CLAUDE.md` with new paths

### Needs Thinking

- [ ] Examples and a Generator script are provided for each firm
- [ ] Converge 4-final-draft.md and the higher level draft

---

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
├── io/                                    # All firm IO in one place
│   ├── .gitignore                         # Ignore all firm dirs by default
│   ├── README.md                          # Instructions for setting up firm dirs
│   │
│   ├── hypernova/                         # Firm directory (example - git submodule)
│   │   ├── templates/                     # Firm-specific content structure
│   │   │   ├── outlines/                  # Firm-specific outlines
│   │   │   │   ├── direct-early-stage-12Ps.yaml
│   │   │   │   └── lpcommit-emerging-manager.yaml
│   │   │   └── scorecards/                # Firm-specific scorecards
│   │   │       ├── direct-early-stage-12Ps/
│   │   │       └── lp-commits_emerging-managers/
│   │   │
│   │   ├── configs/                       # Firm runtime settings
│   │   │   └── brand-hypernova-config.yaml
│   │   │
│   │   ├── deals/                         # All deals for this firm
│   │   │   ├── Ontra/                     # Deal directory
│   │   │   │   ├── inputs/                # Source materials (optional)
│   │   │   │   │   ├── deal.json          # Deal metadata
│   │   │   │   │   ├── deck.pdf           # Pitch deck
│   │   │   │   │   └── dataroom/          # Dataroom documents
│   │   │   │   ├── outputs/               # Generated artifacts (versioned)
│   │   │   │   │   ├── Ontra-v0.0.1/
│   │   │   │   │   │   ├── 0-deck-analysis.json
│   │   │   │   │   │   ├── 1-research.json
│   │   │   │   │   │   ├── 2-sections/
│   │   │   │   │   │   ├── 3-validation.json
│   │   │   │   │   │   ├── 4-final-draft.md
│   │   │   │   │   │   └── state.json
│   │   │   │   │   └── Ontra-v0.0.2/
│   │   │   │   ├── exports/               # Exported formats
│   │   │   │   │   ├── light/
│   │   │   │   │   └── dark/
│   │   │   │   └── Ontra.json             # Deal config (alternative location)
│   │   │   │
│   │   │   ├── Aito/
│   │   │   └── TheoryForge/
│   │   │
│   │   └── versions.json                  # Firm-level version tracking
│   │
│   └── avalanche/                         # Another firm (example)
│       ├── templates/
│       ├── configs/
│       ├── deals/
│       └── versions.json
│
├── templates/                             # Shared/default templates (fallback)
│   ├── outlines/
│   ├── scorecards/
│   └── brand-configs/
│
└── src/                                   # Core code
```

**Key Design Decisions:**
- **`templates/`** in firm directory = content structure (outlines, scorecards) - what to write
- **`configs/`** in firm directory = runtime settings (brand styling) - how it looks
- Firm-specific templates override shared `templates/` when present
- Deal config can be at `deals/{Deal}/{Deal}.json` or `deals/{Deal}/inputs/deal.json`

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

## Design Decisions (Resolved)

1. **Version tracking**: Per-deal `versions.json` or per-firm `versions.json`?
   - **Decision**: Per-firm, with deal name as key
   - **Implemented**: `io/hypernova/versions.json` contains all 15 deals

2. **Brand configs**: Stay in `templates/brand-configs/` or move to `io/{firm}/`?
   - **Decision**: Move to `io/{firm}/configs/` for firm-specific branding
   - **Implemented**: `io/hypernova/configs/brand-hypernova-config.yaml`
   - **Rationale**: Keeps all firm customization in one submodule

3. **Outlines and Scorecards**: Stay in `templates/` or allow firm-specific?
   - **Decision**: Both - shared `templates/` as fallback, `io/{firm}/templates/` takes precedence
   - **Implemented**: `io/hypernova/templates/outlines/` and `io/hypernova/templates/scorecards/`
   - **Rationale**: `templates/` is intuitive naming for content structure files

4. **templates/ vs configs/ split**:
   - **`io/{firm}/templates/`** = Content structure (outlines, scorecards) - *what* to write
   - **`io/{firm}/configs/`** = Runtime settings (brand styling) - *how* it looks
   - **Rationale**: Clear semantic separation; templates is universally understood

5. **Default firm**: Set via `.env`, CLI flag, or interactive prompt?
   - **Decision**: All three, with precedence: CLI > .env > prompt
   - **Implemented**: `MEMO_DEFAULT_FIRM` env var supported in `src/paths.py`

6. **Directory naming**: `Deals/` vs `deals/`?
   - **Decision**: Lowercase `deals/` for consistency
   - **Implemented**: `io/hypernova/deals/`

## Success Criteria

- [x] Firms can maintain private repos for their IO data (submodule working)
- [x] Clear separation between orchestrator code and firm data (io/ structure)
- [ ] Easy navigation at scale (100+ deals across 5+ firms)
- [ ] Backward compatible during migration period
- [ ] Submodule workflow documented and tested
- [ ] All CLI commands support `--firm` and `--deal` flags

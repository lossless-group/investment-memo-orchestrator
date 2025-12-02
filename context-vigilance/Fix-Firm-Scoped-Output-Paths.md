# Fix Firm-Scoped Output Paths

## Problem

When running `python -m src.main --firm hypernova --deal Blinka`, artifacts are being saved to `output/Blinka-v0.0.1/` instead of `io/hypernova/deals/Blinka/outputs/Blinka-v0.0.1/`.

The `firm` parameter is passed through `generate_memo()` and stored in state, but several artifact-saving functions don't read it from state or pass it down the call chain.

## Root Cause Analysis

The workflow passes `firm` into `initial_state`, but artifact-saving functions don't consistently use it:

### Functions that need `firm` parameter added:

1. **`src/artifacts.py:save_deck_analysis_artifacts()`** (line 69)
   - Currently: `VersionManager(Path("output"))` - hardcoded
   - Fix: Accept `firm` param, use firm-scoped VersionManager

2. **`src/agents/deck_analyst.py:deck_analyst_agent()`** (line 139)
   - Currently: Calls `save_deck_analysis_artifacts()` without `firm`
   - Fix: Extract `firm` from `state` and pass it

3. **`src/agents/research_enhanced.py`** - Check if it saves artifacts directly

4. **`src/agents/writer.py`** - Check if it creates artifact directories

5. **`src/workflow.py:human_review()`** (line 123)
   - Currently: `VersionManager(Path("output"))` - hardcoded
   - Fix: Extract `firm` from `state`, use firm-scoped paths

6. **All agents that call `get_latest_output_dir()`** - Verify they pass `firm`

## Files to Modify

### Priority 1: Core Artifact Functions

| File | Function | Change |
|------|----------|--------|
| `src/artifacts.py` | `save_deck_analysis_artifacts()` | Add `firm` param, use firm-scoped VersionManager |
| `src/artifacts.py` | `save_research_artifacts()` | Check if needs `firm` param |
| `src/versioning.py` | `VersionManager.__init__()` | Verify firm-scoped mode works correctly |

### Priority 2: Agent Callers

| File | Function | Change |
|------|----------|--------|
| `src/agents/deck_analyst.py` | `deck_analyst_agent()` | Pass `state.get("firm")` to `save_deck_analysis_artifacts()` |
| `src/agents/research_enhanced.py` | Research agent | Pass `firm` when saving artifacts |
| `src/agents/writer.py` | Writer agent | Pass `firm` when creating directories |

### Priority 3: Workflow Functions

| File | Function | Change |
|------|----------|--------|
| `src/workflow.py` | `human_review()` | Use `state.get("firm")` for VersionManager |

## Implementation Steps

1. **Update `save_deck_analysis_artifacts()`** to accept `firm` parameter
   - Use `resolve_deal_context()` if firm provided
   - Use firm-scoped VersionManager

2. **Update `deck_analyst_agent()`** to pass `firm` from state

3. **Audit all agent files** for direct artifact saves:
   ```bash
   grep -r "VersionManager\|save_.*artifacts\|create_artifact" src/agents/
   ```

4. **Update `human_review()`** in workflow.py

5. **Test with Blinka** to verify artifacts go to `io/hypernova/deals/Blinka/outputs/`

## Verification

After fixes, running:
```bash
python -m src.main --firm hypernova --deal Blinka
```

Should create artifacts at:
```
io/hypernova/deals/Blinka/outputs/Blinka-v0.0.1/
├── 0-deck-analysis.json
├── 0-deck-analysis.md
├── 1-research.json
├── 1-research.md
├── 2-sections/
├── 3-validation.json
├── 4-final-draft.md
└── state.json
```

NOT at:
```
output/Blinka-v0.0.1/  # Wrong!
```

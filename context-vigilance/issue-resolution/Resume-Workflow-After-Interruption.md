# Resume Workflow After Interruption

## Problem Statement

Investment memo generation can be interrupted by:
- API timeouts or rate limits
- Network connectivity issues
- Process crashes or kills
- User-initiated stops (Ctrl+C)
- System shutdowns

Currently, the system must restart from scratch, wasting:
- **Time**: Re-running completed agents (deck analysis, research, drafting can each take 2-5 minutes)
- **API costs**: Re-calling expensive LLM and research APIs
- **Progress**: Discarding partial results from successful agents

## Solution: Checkpoint-Based Resume System

### Core Concept

The workflow is a **linear pipeline of agents**, each producing **artifacts** that serve as **checkpoints**:

```
deck_analyst → research → section_research → draft → enrich_trademark →
enrich_socials → enrich_links → enrich_visualizations → cite →
validate_citations → fact_check → validate → finalize
```

**Key Insight**: If an artifact exists and is valid, we can skip that agent and resume from the next step.

### Checkpoint Artifacts

Each agent produces specific artifacts in `output/{Company}-v0.0.x/`:

| Agent | Checkpoint Artifact | Indicates Completion |
|-------|-------------------|---------------------|
| `deck_analyst` | `0-deck-analysis.json` | Deck analyzed successfully |
| `research` | `1-research.json` | Web research complete |
| `section_research` | `1-section-research.json` | Section-specific research complete |
| `draft` | `2-sections/*.md` (10 files) | All sections written |
| `enrich_trademark` | `header.md` | Company trademark inserted |
| `enrich_socials` | `2-sections/04-team.md` (with LinkedIn links) | LinkedIn enrichment complete |
| `enrich_links` | `2-sections/*.md` (with hyperlinks) | Entity linking complete |
| `enrich_visualizations` | `2-sections/*.md` (with viz markers) | Visualization enrichment complete |
| `cite` | `4-final-draft.md` (with citations) | Citations added, memo assembled |
| `validate_citations` | `3-validation.json` (with citation_validation) | Citation accuracy checked |
| `fact_check` | `3-validation.json` (with fact_check_results) | Facts verified |
| `validate` | `3-validation.json` (with overall_score) | Quality validation complete |
| `finalize` | `state.json` + `4-final-draft.md` | Workflow complete |

### Detection Logic

To determine which agent to resume from, check artifacts in order:

```python
def detect_resume_point(output_dir: Path) -> str:
    """
    Detect which agent to resume from based on existing artifacts.

    Returns:
        Agent name to resume from, or "start" if no checkpoints found
    """
    # Check in reverse order (later checkpoints first)

    # Check if fully complete
    state_json = output_dir / "state.json"
    if state_json.exists():
        # Load and check if finalized
        with open(state_json) as f:
            state = json.load(f)
        if state.get("final_memo"):
            return "complete"  # Already done

    # Check validation
    validation_json = output_dir / "3-validation.json"
    if validation_json.exists():
        with open(validation_json) as f:
            validation = json.load(f)
        if validation.get("overall_score"):
            return "finalize"  # Resume at finalization
        if validation.get("fact_check_results"):
            return "validate"  # Resume at validation
        if validation.get("citation_validation"):
            return "fact_check"  # Resume at fact-checking

    # Check citations
    final_draft = output_dir / "4-final-draft.md"
    if final_draft.exists():
        # Check if it has citations (not just placeholder)
        content = final_draft.read_text()
        if "[^1]" in content or "## Citations" in content:
            return "validate_citations"  # Resume at citation validation

    # Check enrichment stages (need to check if each is truly complete)
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        sections = list(sections_dir.glob("*.md"))
        if len(sections) >= 10:  # All sections exist
            # Check if visualization enrichment complete
            # (This is tricky - need to check section content for viz markers)
            team_section = sections_dir / "04-team.md"
            if team_section.exists():
                content = team_section.read_text()
                # Check for LinkedIn links (socials enrichment marker)
                if "linkedin.com/in/" in content:
                    return "enrich_links"  # Resume at link enrichment
                # Check for trademark
                header = output_dir / "header.md"
                if header.exists():
                    return "enrich_socials"  # Resume at socials enrichment
            return "enrich_trademark"  # Resume at trademark enrichment
        return "draft"  # Resume at drafting (sections incomplete)

    # Check section research
    section_research_json = output_dir / "1-section-research.json"
    if section_research_json.exists():
        return "draft"  # Resume at drafting

    # Check research
    research_json = output_dir / "1-research.json"
    if research_json.exists():
        return "section_research"  # Resume at section research

    # Check deck analysis
    deck_analysis_json = output_dir / "0-deck-analysis.json"
    if deck_analysis_json.exists():
        return "research"  # Resume at research

    # No checkpoints - start from beginning
    return "start"
```

### State Reconstruction

To resume, we must reconstruct the `MemoState` from artifacts:

```python
def reconstruct_state_from_artifacts(company_name: str, output_dir: Path) -> MemoState:
    """
    Rebuild MemoState from saved artifacts.

    Args:
        company_name: Name of the company
        output_dir: Path to artifact directory

    Returns:
        Reconstructed MemoState ready for resumption
    """
    from src.state import create_initial_state

    # Start with fresh state (loads company data JSON)
    state = create_initial_state(company_name)

    # Load deck analysis if exists
    deck_json = output_dir / "0-deck-analysis.json"
    if deck_json.exists():
        with open(deck_json) as f:
            state["deck_analysis"] = json.load(f)

    # Load research if exists
    research_json = output_dir / "1-research.json"
    if research_json.exists():
        with open(research_json) as f:
            state["research"] = json.load(f)

    # Load section research if exists
    section_research_json = output_dir / "1-section-research.json"
    if section_research_json.exists():
        with open(section_research_json) as f:
            state["section_research"] = json.load(f)

    # Load draft sections if exist
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        draft_sections = {}
        for section_file in sections_dir.glob("*.md"):
            section_name = section_file.stem
            content = section_file.read_text()
            draft_sections[section_name] = {
                "section_name": section_name.replace("-", " ").title(),
                "content": content,
                "word_count": len(content.split()),
                "citations": []  # Citations extracted during cite stage
            }
        state["draft_sections"] = draft_sections

    # Load validation if exists
    validation_json = output_dir / "3-validation.json"
    if validation_json.exists():
        with open(validation_json) as f:
            validation = json.load(f)
        state["validation_results"] = validation.get("validation_results", {})
        state["citation_validation"] = validation.get("citation_validation", {})
        state["fact_check_results"] = validation.get("fact_check_results", {})
        state["overall_score"] = validation.get("overall_score", 0.0)

    # Load final draft if exists
    final_draft = output_dir / "4-final-draft.md"
    if final_draft.exists():
        state["final_memo"] = final_draft.read_text()

    return state
```

### Resume Implementation

#### Option 1: New CLI Flag (Recommended)

Add `--resume` flag to `src/main.py`:

```bash
# Resume from latest checkpoint
python -m src.main "Fernstone" --resume

# Resume from specific version
python -m src.main "Fernstone" --resume --version v0.0.3
```

**Implementation**:
```python
# In src/main.py

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("company_name", ...)
    parser.add_argument("--resume", action="store_true",
                       help="Resume from latest checkpoint if available")
    parser.add_argument("--version", type=str,
                       help="Specific version to resume (e.g., v0.0.3)")
    args = parser.parse_args()

    if args.resume:
        result = generate_memo_resume(
            company_name=args.company_name,
            version=args.version,
            investment_type=args.type,
            memo_mode=args.mode
        )
    else:
        result = generate_memo(...)  # Normal flow
```

#### Option 2: Standalone Script (Alternative)

Create `tools/resume-memo.py`:

```bash
# Resume latest
python tools/resume-memo.py "Fernstone"

# Resume specific version
python tools/resume-memo.py "Fernstone" --version v0.0.3
```

**Implementation**:
```python
# tools/resume-memo.py

from pathlib import Path
from src.workflow import build_workflow
from src.state import MemoState

def resume_memo_generation(company_name: str, version: str = None):
    """Resume memo generation from latest checkpoint."""

    # Find output directory
    if version:
        output_dir = Path("output") / f"{sanitize_filename(company_name)}-{version}"
    else:
        # Find latest version
        output_dir = get_latest_output_dir(company_name)

    if not output_dir.exists():
        print(f"No artifacts found for {company_name}")
        return

    # Detect resume point
    resume_from = detect_resume_point(output_dir)

    if resume_from == "complete":
        print(f"✓ Memo already complete: {output_dir / '4-final-draft.md'}")
        return

    if resume_from == "start":
        print(f"⚠️  No checkpoints found, starting from scratch...")
        # Fall back to normal generation
        from src.main import generate_memo
        return generate_memo(company_name, ...)

    print(f"✓ Resuming from checkpoint: {resume_from}")

    # Reconstruct state
    state = reconstruct_state_from_artifacts(company_name, output_dir)

    # Build workflow
    workflow = build_workflow()
    compiled = workflow.compile()

    # Execute from resume point (need to modify workflow to support this)
    # This requires LangGraph subgraph execution or manual agent calling
    result = execute_from_checkpoint(compiled, state, resume_from)

    print(f"✓ Memo complete: {output_dir / '4-final-draft.md'}")
```

### Workflow Modifications Required

To support resumption, the workflow must:

1. **Accept starting node parameter**: LangGraph doesn't natively support "start from node X", so we need to either:
   - **Option A**: Manually call agents in sequence (skip those already complete)
   - **Option B**: Use conditional routing at entry point to skip completed nodes
   - **Option C**: Create partial workflows that start from specific checkpoints

**Recommended: Option A (Manual Agent Calling)**

```python
def execute_from_checkpoint(state: MemoState, resume_from: str) -> MemoState:
    """
    Execute agents in sequence starting from resume_from checkpoint.

    Args:
        state: Reconstructed state
        resume_from: Agent name to resume from

    Returns:
        Final state after completion
    """
    from src.agents import (
        research_agent_enhanced,
        perplexity_section_researcher_agent,
        writer_agent,
        trademark_enrichment_agent,
        socials_enrichment_agent,
        link_enrichment_agent,
        visualization_enrichment_agent,
        citation_enrichment_agent,
        citation_validator_agent,
        fact_checker_agent,
        validator_agent,
    )
    from src.workflow import finalize_memo

    # Define agent sequence
    agent_sequence = [
        ("research", research_agent_enhanced),
        ("section_research", perplexity_section_researcher_agent),
        ("draft", writer_agent),
        ("enrich_trademark", trademark_enrichment_agent),
        ("enrich_socials", socials_enrichment_agent),
        ("enrich_links", link_enrichment_agent),
        ("enrich_visualizations", visualization_enrichment_agent),
        ("cite", citation_enrichment_agent),
        ("validate_citations", citation_validator_agent),
        ("fact_check", fact_checker_agent),
        ("validate", validator_agent),
        ("finalize", finalize_memo),
    ]

    # Find starting index
    start_index = next(
        (i for i, (name, _) in enumerate(agent_sequence) if name == resume_from),
        0
    )

    # Execute agents from resume point
    for agent_name, agent_fn in agent_sequence[start_index:]:
        print(f"Running agent: {agent_name}")
        result = agent_fn(state)
        state.update(result)

        # Check if validation failed (needs human review)
        if agent_name == "validate" and state.get("overall_score", 0) < 8.0:
            from src.workflow import human_review
            result = human_review(state)
            state.update(result)
            break

    return state
```

## Implementation Plan

### Phase 1: Detection & Reconstruction (Minimal Viable Resume)
- ✅ Implement `detect_resume_point()` function
- ✅ Implement `reconstruct_state_from_artifacts()` function
- ✅ Add `--resume` flag to CLI
- ✅ Implement `execute_from_checkpoint()` for manual agent execution

### Phase 2: Validation & Testing
- Test resumption from each checkpoint
- Add safety checks:
  - Verify artifact integrity (JSON validation, file sizes)
  - Check for corruption or incomplete files
  - Validate state consistency
- Add logging to track resume operations

### Phase 3: Enhanced Features
- Auto-detect interruption and offer resume on next run
- Add `--force-restart` flag to override resume
- Create visual progress indicator showing completed/pending agents
- Support resume after manual artifact edits (e.g., improved research.json)

### Phase 4: Robustness
- Add checkpoint versioning (handle schema changes between versions)
- Implement partial rollback (e.g., "redo citation enrichment")
- Add agent-level retry logic (retry failed agent before full restart)

## Usage Examples

### Basic Resume
```bash
# Interruption occurs during citation enrichment
^C

# Resume from checkpoint
python -m src.main "Fernstone" --resume
# Output: "✓ Resuming from checkpoint: cite"
# Output: "Running agent: cite"
# Output: "Running agent: validate_citations"
# ...
```

### Resume Specific Version
```bash
# Resume older version
python -m src.main "Fernstone" --resume --version v0.0.2
```

### Force Fresh Start
```bash
# Ignore checkpoints, start over
python -m src.main "Fernstone"  # Normal invocation always starts fresh
```

## Edge Cases & Considerations

### 1. Artifact Corruption
**Problem**: JSON file exists but is incomplete/corrupted (interrupted mid-write)

**Solution**: Validate artifact integrity before treating as checkpoint
```python
def is_valid_checkpoint(artifact_path: Path) -> bool:
    """Check if artifact is valid and complete."""
    if not artifact_path.exists():
        return False

    # Check file size (too small = likely corrupted)
    if artifact_path.stat().st_size < 100:  # Less than 100 bytes
        return False

    # For JSON, try parsing
    if artifact_path.suffix == ".json":
        try:
            with open(artifact_path) as f:
                json.load(f)
            return True
        except json.JSONDecodeError:
            return False

    return True
```

### 2. State Schema Changes
**Problem**: Artifacts saved with old state schema, incompatible with current code

**Solution**:
- Version artifacts with schema version
- Implement migration functions for each schema version
- Fall back to fresh start if migration fails

### 3. Manual Artifact Edits
**Problem**: User manually edits `1-research.json` to add better data

**Solution**: Resume should detect and use edited artifacts transparently
- Current design handles this naturally (loads from disk)
- User workflow: Edit artifact → Resume → System uses edited data

### 4. Partial Section Completion
**Problem**: Writer created 7/10 sections before crashing

**Solution**:
- Detect incomplete section set (< 10 files)
- Resume at `draft` agent, which will regenerate all sections
- Alternative: Smart resume that only writes missing sections (more complex)

### 5. Multi-Version Scenarios
**Problem**: User has v0.0.1, v0.0.2, v0.0.3 - which to resume?

**Solution**:
- Default: Resume latest version only
- Explicit: `--version` flag to specify
- Safety: Warn if multiple incomplete versions exist

## Benefits

### Time Savings
- Skip completed agents (each 2-5 minutes)
- Resume from 80% complete workflow instead of 0%
- **Example**: If interruption happens at citation enrichment (agent 9/13), resume saves ~15 minutes

### Cost Savings
- Avoid redundant API calls:
  - Deck analysis: ~$0.10
  - Research: ~$0.50 (Tavily/Perplexity)
  - Writer: ~$2.00 (10 section drafts)
  - Citation enrichment: ~$1.50
- **Total savings per resume**: ~$4.00

### User Experience
- No frustration from lost progress
- Encourages experimentation (can stop/resume freely)
- Enables manual workflow editing (improve research → resume)

## Alternative: Auto-Save State at Each Agent

Instead of detecting checkpoints, we could save full state after each agent completes:

```python
# In build_workflow(), after each agent execution
def save_state_after_agent(agent_fn):
    def wrapper(state):
        result = agent_fn(state)
        state.update(result)

        # Save state snapshot
        save_state_snapshot(get_latest_output_dir(state["company_name"]), state)

        return result
    return wrapper
```

**Pros**:
- Simpler detection (just load state.json)
- Always have complete state

**Cons**:
- More disk writes (13 state saves vs. 4-5 artifact saves)
- Larger storage footprint
- State might be inconsistent if agent fails mid-execution

**Recommendation**: Use artifact-based detection (more reliable).

## Related Documentation

- `src/workflow.py` - Workflow graph structure and agent sequence
- `src/artifacts.py` - Artifact saving functions
- `src/state.py` - State schema definitions
- `CLAUDE.md` - Artifact trail system documentation

## Next Steps

1. Implement Phase 1 (detection, reconstruction, CLI flag)
2. Test with real interruptions at each checkpoint
3. Add to `CLAUDE.md` essential commands section
4. Create issue if bugs found during testing

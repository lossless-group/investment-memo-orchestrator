# 12Ps Framework Integration Plan

## Overview

This document outlines how to integrate the 12Ps scorecard and outline into the existing investment memo orchestrator **without replacing or modifying existing workflow steps**.

## Current Architecture Summary

### Workflow Sequence (workflow.py)
```
deck_analyst → research → section_research → draft → enrich_trademark → enrich_socials → enrich_links → enrich_visualizations → cite → toc → validate_citations → fact_check → validate → finalize/human_review
```

### How Outlines Work Today
1. `data/{Company}.json` can specify `"outline": "custom-outline-name"`
2. `outline_loader.py` loads from `templates/outlines/{outline-name}.yaml`
3. `writer_agent()` uses the outline's section definitions to write each section
4. Each section is written and saved to `output/{Company}-v0.0.x/2-sections/`

### Key Files
- `data/{Company}.json` - Company config (includes `outline` field)
- `templates/outlines/*.yaml` - Outline definitions
- `templates/scorecards/{type}/*.yaml` - Scorecard definitions (NEW)
- `src/outline_loader.py` - Loads outlines based on state
- `src/agents/writer.py` - Writes sections using outline guidance

---

## Integration Approach: ADDITIVE ONLY

### Principle
We add new capabilities without modifying existing workflow steps. The 12Ps system runs **in parallel** with existing flows or as **post-processing** steps.

---

## Part 1: Using the 12Ps Outline

### How to Activate
Add to `data/{Company}.json`:
```json
{
  "type": "direct",
  "mode": "consider",
  "outline": "direct-early-stage-12Ps",
  "scorecard": "hypernova-early-stage-12Ps",
  ...
}
```

### What Happens
1. `outline_loader.py` already supports custom outlines
2. Adding `"outline": "direct-early-stage-12Ps"` will load `templates/outlines/direct-early-stage-12Ps.yaml`
3. The writer agent will use the 12Ps section structure instead of traditional 10-section structure

### Outline Already Compatible
The `direct-early-stage-12Ps.yaml` outline:
- Has 10 sections (same count as traditional)
- Each section has `number`, `name`, `filename`, `target_length`, `guiding_questions`, etc.
- Follows the exact schema expected by `outline_loader.py`

**No code changes needed** - just add the outline file and reference it in company JSON.

---

## Part 2: Adding Scorecard Evaluation

### New State Fields (Additive)
Add to `src/state.py` - `MemoState`:
```python
# Scorecard evaluation (12Ps)
scorecard_name: Optional[str]  # Name of scorecard to use (e.g., "hypernova-early-stage-12Ps")
scorecard_results: Optional[Dict[str, Any]]  # Full scorecard evaluation results
```

Add to `create_initial_state()`:
```python
scorecard_name: Optional[str] = None
```

### New Scorecard Loader (New File)
Create `src/scorecard_loader.py`:
```python
"""
Scorecard loader for investment evaluation.
Loads YAML scorecard definitions and provides scoring rubrics.
"""

def load_scorecard(scorecard_name: str) -> ScorecardDefinition:
    """Load scorecard from templates/scorecards/{type}/{name}.yaml"""
    pass

def get_dimension_rubric(scorecard: ScorecardDefinition, dimension: str) -> Dict:
    """Get scoring rubric for a specific dimension"""
    pass
```

### New Scorecard Agent (New File)
Create `src/agents/scorecard_evaluator.py`:
```python
"""
Scorecard Evaluator Agent - Scores memo sections against 12Ps dimensions.

This agent evaluates completed sections and produces dimension scores.
It runs AFTER sections are written, not during.
"""

def scorecard_evaluator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Evaluate all sections against scorecard dimensions.

    For 12Ps, maps sections to dimension groups:
    - 02-origins.md → Persona, Pain, Proposition
    - 03-opening.md → Problem, Possibility, Positioning
    - 04-organization.md → People, Process, Product
    - 05-offering.md → Offering Coherence
    - 06-opportunity.md → Potential, Progress, Plan

    Returns:
        Updated state with scorecard_results populated
    """
    pass
```

---

## Part 3: Workflow Integration Options

### Option A: Post-Validation Scorecard (Recommended)
Add scorecard evaluation after `validate` but before `finalize`:

```
... → validate → scorecard_evaluate → finalize/human_review
```

**Pros:**
- All sections written and validated before scoring
- Scorecard results inform final decision
- Doesn't slow down section writing

**Implementation:**
```python
# In workflow.py build_workflow()
workflow.add_node("scorecard_evaluate", scorecard_evaluator_agent)
workflow.add_edge("validate", "scorecard_evaluate")
workflow.add_conditional_edges(
    "scorecard_evaluate",  # Changed from "validate"
    should_continue,
    {"finalize": "finalize", "human_review": "human_review"}
)
```

### Option B: Per-Section Scoring (More Complex)
Score each section immediately after writing:

```
For each section:
  write_section → score_section → save_with_score
```

**Pros:**
- Immediate feedback per section
- Could enable rewrite loops per section

**Cons:**
- More complex implementation
- Slows down overall workflow
- Requires modifying writer_agent internals

**Implementation:**
Would require changes to `writer_agent()` to call scorer after each section.

### Option C: Standalone CLI Tool (Simplest)
Create `cli/score_memo.py` that runs scorecard on existing memo:

```bash
python cli/score_memo.py "Sava" --scorecard hypernova-early-stage-12Ps
```

**Pros:**
- No workflow changes at all
- Can score any existing memo
- Easy to iterate on scoring logic

**Cons:**
- Not integrated into generation flow
- Manual step required

---

## Part 4: Scorecard Output Artifacts

### Output Location
```
output/{Company}-v0.0.x/
├── 2-sections/
│   ├── 01-executive-summary.md
│   ├── 02-origins.md          # Contains Origins scorecard table
│   ├── 03-opening.md          # Contains Opening scorecard table
│   └── ...
├── 5-scorecard/               # NEW: Scorecard artifacts
│   ├── 12Ps-scorecard.md      # Full scorecard document
│   ├── 12Ps-scorecard.json    # Machine-readable results
│   └── dimension-evidence/    # Evidence per dimension
│       ├── persona.md
│       ├── pain.md
│       └── ...
└── state.json                 # Now includes scorecard_results
```

### Scorecard JSON Structure
```json
{
  "scorecard_name": "hypernova-early-stage-12Ps",
  "company": "Sava",
  "date": "2025-11-28",
  "overall_score": 3.3,
  "groups": {
    "origins": {
      "avg_score": 3.7,
      "dimensions": {
        "persona": {"score": 4, "percentile": "Top 10-25%", "evidence": "...", "improvements": ["..."]},
        "pain": {"score": 4, "percentile": "Top 10-25%", "evidence": "...", "improvements": ["..."]},
        "proposition": {"score": 3, "percentile": "Top 50%", "evidence": "...", "improvements": ["..."]}
      }
    },
    ...
  },
  "strengths": ["persona", "pain", "problem", "possibility", "people"],
  "concerns": ["progress"],
  "diligence_questions": ["..."]
}
```

---

## Part 5: Section-Scorecard Mapping

For the 12Ps outline, sections map to scorecard dimensions:

| Section | File | Scorecard Dimensions |
|---------|------|---------------------|
| Executive Summary | 01-executive-summary.md | All (overview) |
| Origins | 02-origins.md | Persona, Pain, Proposition |
| Opening | 03-opening.md | Problem, Possibility, Positioning |
| Organization | 04-organization.md | People, Process, Product |
| Offering | 05-offering.md | Synthesis (P3+P6+P9) |
| Opportunity | 06-opportunity.md | Potential, Progress, Plan |
| Risks | 07-risks.md | (Risk overlay on all) |
| Scorecard Summary | 08-scorecard-summary.md | All 12 (consolidated) |
| Funding & Terms | 09-funding-terms.md | (Informs Plan) |
| Closing Assessment | 10-closing-assessment.md | Overall synthesis |

---

## Part 6: Implementation Order

### Phase 1: Outline Only (No Code Changes)
1. ✅ Create `templates/outlines/direct-early-stage-12Ps.yaml` (DONE)
2. ✅ Create `templates/scorecards/direct-early-stage-12Ps/` (DONE)
3. Update `data/Sava.json` to use new outline:
   ```json
   {
     "outline": "direct-early-stage-12Ps"
   }
   ```
4. Run memo generation - will use 12Ps narrative structure

### Phase 2: Standalone Scorer CLI
1. Create `cli/score_memo.py`
2. Load scorecard YAML
3. Read existing memo sections
4. Use LLM to score each dimension
5. Output scorecard markdown and JSON

### Phase 3: Integrated Scorecard Agent
1. Add `scorecard_name` to `MemoState`
2. Create `src/scorecard_loader.py`
3. Create `src/agents/scorecard_evaluator.py`
4. Add to workflow after `validate`
5. Save scorecard artifacts

### Phase 4: Section-Embedded Scores
1. Modify outline to include scorecard table templates
2. Writer agent renders scorecard tables in sections
3. Scorecard agent fills in scores post-write

---

## Part 7: Company JSON Configuration

### Full Example for 12Ps Evaluation
```json
{
  "type": "direct",
  "mode": "consider",
  "outline": "direct-early-stage-12Ps",
  "scorecard": "hypernova-early-stage-12Ps",
  "description": "Sava is a financial and legal technology platform...",
  "url": "https://www.savahq.com",
  "stage": "Series A",
  "deck": "data/Secure-Inputs/2025-11_Sava-Fundraising-Deck--Series-A.pdf",
  "notes": "Focus on team backgrounds, technology platform..."
}
```

### New Fields
- `outline`: Which memo outline to use (section structure)
- `scorecard`: Which scorecard to evaluate against (scoring rubric)

Both are optional. If not specified:
- `outline` defaults to `direct-investment` or `fund-commitment` based on `type`
- `scorecard` is not run (no evaluation)

---

## Part 8: Scorer Agent Design

### Input
- All written sections from `output/{Company}-v0.0.x/2-sections/`
- Research data from state
- Deck analysis from state
- Scorecard definition with rubrics

### Process (Per Dimension)
1. Identify which section(s) contain evidence for this dimension
2. Extract relevant passages
3. Compare against scoring rubric (1-5 scale)
4. Generate:
   - Score (1-5)
   - Percentile mapping
   - Key evidence summary
   - "What could make this score higher"

### Output
- Scorecard results dict in state
- Scorecard markdown file
- Scorecard JSON file
- Optional: Insert scorecard tables into section files

### LLM Prompt Structure
```
You are evaluating the "{dimension_name}" dimension for {company_name}.

DIMENSION DEFINITION:
{dimension.full_description}

SCORING RUBRIC:
5: {rubric[5]}
4: {rubric[4]}
3: {rubric[3]}
2: {rubric[2]}
1: {rubric[1]}

EVIDENCE FROM MEMO:
{relevant_section_content}

RESEARCH DATA:
{relevant_research}

Evaluate this dimension:
1. What score (1-5) based on the rubric?
2. What evidence supports this score?
3. What would make this score higher?

Output JSON:
{
  "score": N,
  "evidence": "...",
  "improvements": ["...", "..."]
}
```

---

## Summary

### What We're Adding (Not Changing)
1. New outline file: `templates/outlines/direct-early-stage-12Ps.yaml`
2. New scorecard files: `templates/scorecards/direct-early-stage-12Ps/`
3. New state field: `scorecard_name`, `scorecard_results`
4. New loader: `src/scorecard_loader.py`
5. New agent: `src/agents/scorecard_evaluator.py`
6. New workflow node (after validate, before finalize)
7. New output artifacts: `5-scorecard/`

### What We're NOT Changing
- Existing agents (deck_analyst, research, writer, enrichment, validation)
- Existing workflow sequence (additive only)
- Existing outline structure (new outline follows same schema)
- Existing state fields (additive only)
- How traditional memos are generated (12Ps is opt-in via `outline` field)

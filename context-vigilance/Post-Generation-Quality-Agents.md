# Post-Generation Quality Agents

**Date**: 2025-11-28
**Status**: Mini-spec
**Priority**: Next implementation

## Overview

Four agents that run after the main writing pipeline to improve final output quality. These operate on section files in `2-sections/` and run before final assembly.

## Agent 1: `redundancy_reducer`

**Purpose**: Identify and condense heavy redundancies across sections without losing information.

**Location**: `src/agents/redundancy_reducer.py`

**Behavior**:
1. Load all section files from `2-sections/`
2. Identify repeated information across sections:
   - Same metrics cited multiple times (e.g., "$200M Series E" mentioned in 3 sections)
   - Same company descriptions repeated verbatim
   - Same risk factors mentioned outside Section 8
   - Same team member credentials repeated
3. For each redundancy:
   - Keep the most detailed mention (usually first occurrence or in the most relevant section)
   - Replace other occurrences with anchor links: `[as noted in Team](#team)` or `[see Funding & Terms](#funding--terms)`
   - OR condense to brief reference: "The $200M Series E (detailed in Funding & Terms)..."
4. Save edited section files back to `2-sections/`

**Acceptable redundancy** (don't remove):
- Executive Summary naturally summarizes other sections
- Brief context-setting references
- Key metrics in Recommendation that tie back to evidence

**Unacceptable redundancy** (condense):
- Full paragraphs repeated across sections
- Same 3+ sentence block appearing twice
- Metrics with identical surrounding context

**Anchor link format**:
```markdown
## Team

### Leadership

[Jeremy Johnson](https://linkedin.com/in/jeremyjohnson), CEO and co-founder...

---

## Funding & Terms

The company raised $200M in Series E led by SoftBank. [^1] CEO [Jeremy Johnson](#leadership) announced...
```

## Agent 2: `format_checker`

**Purpose**: Clean up formatting inconsistencies before final assembly.

**Location**: `src/agents/format_checker.py`

**Rules to enforce**:

1. **Separator cleanup**:
   - Remove multiple consecutive `---` (keep max 1)
   - Remove `---` at end of sections (assembler adds these)
   - Remove `---` immediately after headers

2. **Header hierarchy**:
   - Section files should use `##` for section title, `###` for subsections
   - No `#` (h1) in section files
   - No jumping levels (`##` → `####`)

3. **List formatting**:
   - Consistent bullet style within a section (all `-` or all `*`)
   - Proper indentation for nested lists
   - Blank line before and after lists

4. **Citation spacing**:
   - Space before citation: `text. [^1]` not `text.[^1]`
   - No double citations: `[^1][^2]` → `[^1], [^2]`

5. **Whitespace**:
   - No triple+ blank lines
   - Single blank line between paragraphs
   - No trailing whitespace

6. **Link formatting**:
   - LinkedIn links have display text: `[Name](url)` not bare `url`
   - No broken markdown links: `[text](` without closing `)`

**Implementation**:
```python
def format_checker_agent(state: MemoState) -> dict:
    """Clean formatting issues in section files."""
    output_dir = get_latest_output_dir(state["company_name"])
    sections_dir = output_dir / "2-sections"

    issues_fixed = []
    for section_file in sorted(sections_dir.glob("*.md")):
        content = section_file.read_text()
        original = content

        # Apply formatting rules
        content = fix_multiple_separators(content)
        content = fix_header_hierarchy(content)
        content = fix_citation_spacing(content)
        content = fix_whitespace(content)

        if content != original:
            section_file.write_text(content)
            issues_fixed.append(section_file.name)

    return {"messages": [f"Format checker: fixed {len(issues_fixed)} files"]}
```

## Agent 3: `summary_revisor`

**Purpose**: Revise Executive Summary / Business Overview based on complete memo content.

**Location**: `src/agents/summary_revisor.py`

**Problem**: Summary sections are written early in the pipeline before all sections exist. They may:
- Miss key insights from later sections
- Have different emphasis than the final narrative
- Lack specific metrics that appear in later sections

**Behavior**:
1. Load all section files (global view)
2. Extract key elements:
   - Most compelling metrics from each section
   - Key risks identified in Section 8
   - Investment thesis from Section 9
   - Recommendation from Section 10
3. Revise `01-executive-summary.md` and/or `02-business-overview.md`:
   - Ensure summary reflects actual content
   - Add specific metrics discovered in research
   - Align tone with recommendation (COMMIT/CONSIDER/PASS)
   - Keep concise (target ~300-400 words for exec summary)

**Prompt structure**:
```
You have written an investment memo. Now revise the Executive Summary to accurately reflect the complete memo.

CURRENT EXECUTIVE SUMMARY:
{current_summary}

KEY CONTENT FROM OTHER SECTIONS:
- Team highlights: {team_highlights}
- Key metrics: {key_metrics}
- Main risks: {main_risks}
- Investment thesis: {thesis}
- Recommendation: {recommendation}

Revise the Executive Summary to:
1. Lead with the most compelling opportunity
2. Include 2-3 specific metrics that support the thesis
3. Acknowledge primary risk (1 sentence)
4. End with clear recommendation alignment
5. Stay under 400 words
```

## Agent 4: `introduction_revisor`

**Purpose**: Revise introduction/opening paragraphs based on global content view.

**Location**: `src/agents/introduction_revisor.py`

**Scope**: Different from summary_revisor - focuses on:
- Opening paragraph of each section (not just summary sections)
- Section transitions
- Narrative flow between sections

**Behavior**:
1. Load all sections
2. For each section, check if opening paragraph:
   - Connects to previous section naturally
   - Sets up the section's key points
   - Avoids redundant context-setting
3. Revise section openings for better flow
4. Add transition sentences where needed

**Example transformation**:
```markdown
# Before (Section 4: Team)
Andela is a technology talent company that connects companies with engineers
from emerging markets. The company was founded in 2014 and has grown
significantly since then. The leadership team includes...

# After (Section 4: Team)
The execution of Andela's ambitious global talent platform depends on
experienced leadership with deep networks in both enterprise tech and
emerging markets. The founding team brings exactly this combination...
```

## Workflow Integration

Add to `src/workflow.py` after `citation_enrichment` and before `toc_generator`:

```python
# Quality improvement agents (run on section files)
workflow.add_node("redundancy_reducer", redundancy_reducer_agent)
workflow.add_node("format_checker", format_checker_agent)
workflow.add_node("summary_revisor", summary_revisor_agent)
workflow.add_node("introduction_revisor", introduction_revisor_agent)

# Sequence
workflow.add_edge("citation_enrichment", "redundancy_reducer")
workflow.add_edge("redundancy_reducer", "format_checker")
workflow.add_edge("format_checker", "summary_revisor")
workflow.add_edge("summary_revisor", "introduction_revisor")
workflow.add_edge("introduction_revisor", "toc_generator")
```

## Order Rationale

1. **redundancy_reducer** first - removes duplicate content before other agents process
2. **format_checker** second - clean formatting for easier LLM processing
3. **summary_revisor** third - needs clean, de-duped content to summarize
4. **introduction_revisor** last - needs final content to write transitions

## CLI Standalone Tools

Each agent should also be callable standalone for post-hoc improvements:

```bash
# Run single agent on existing output
python cli/reduce_redundancy.py output/Andela-v0.0.1
python cli/check_format.py output/Andela-v0.0.1
python cli/revise_summary.py output/Andela-v0.0.1
python cli/revise_introductions.py output/Andela-v0.0.1
```

## Implementation Priority

1. `format_checker` - Rule-based, no LLM needed, quick win
2. `redundancy_reducer` - High value, noticeable quality improvement
3. `summary_revisor` - Ensures summary accuracy
4. `introduction_revisor` - Nice-to-have, polish layer

## Notes

- All agents operate on `2-sections/*.md` files, not final draft
- Final assembly happens AFTER these agents run
- Each agent should be idempotent (safe to run multiple times)
- Log changes made for debugging

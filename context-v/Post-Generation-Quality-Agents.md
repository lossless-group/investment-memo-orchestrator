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

## Agent 3: `revise_summary_sections`

**Purpose**: Revise Executive Summary AND Closing Assessment based on the COMPLETE assembled final draft.

**Location**: `src/agents/revise_summary_sections.py`

**Critical Difference from Other Agents**: This agent runs AFTER `toc_generator` and reads the complete `4-final-draft.md`, not individual section files. This ensures the summary sections are rewritten based on what's ACTUALLY in the final memo.

### Problem Statement

Summary sections are written early in the pipeline before all content exists. This causes:
- **Premature hedging**: Summary contains "excuses" about missing data that IS present in later sections
- **Content mismatch**: Summary doesn't accurately reflect what's in the body
- **Stale framing**: Early drafts frame the thesis differently than the evidence that emerges
- **Placeholder language**: "Data not available" when the data actually exists

**Example Issue (ProfileHealth, Reson8)**:
The Executive Summary made excuses about missing information, even though:
- The deck contained comprehensive data
- The research sections had specific metrics
- The body sections contained all the details

### Sections to Revise

| Section | File | Purpose |
|---------|------|---------|
| Executive Summary | `01-executive-summary.md` | Synthesize entire memo into compelling overview |
| Closing Assessment | `10-closing-assessment.md` (or equivalent) | Final recommendation based on full analysis |

### Behavior

1. **Load complete final draft** (`4-final-draft.md`) - the fully assembled memo
2. **Extract key data points** from the full content:
   - Funding terms (amount, valuation, runway)
   - Team members with backgrounds
   - Traction metrics (users, revenue, growth)
   - Market size claims with sources
   - Key risks identified
   - Investment thesis
3. **Revise Executive Summary**:
   - Use SPECIFIC metrics from the body (not vague language)
   - Remove false hedging ("data not available" when it IS available)
   - Ensure it accurately reflects the full memo content
   - Keep concise (~275-400 words depending on outline)
4. **Revise Closing Assessment**:
   - Synthesize the full analysis (not just repeat summary)
   - Weigh strengths against risks based on ACTUAL content
   - Provide concrete next steps or due diligence items
   - Give clear recommendation with specific rationale
5. **Save revised sections** back to `2-sections/`
6. **Trigger reassembly** of `4-final-draft.md`

### Workflow Position

```
EXISTING PIPELINE:
deck_analyst → research → writer → enrichments → citation → toc_generator
                                                                    │
                                                                    ▼
                                                    ┌─────────────────────────┐
                                                    │ revise_summary_sections │
                                                    │                         │
                                                    │ • Read 4-final-draft.md │
                                                    │ • Extract key data      │
                                                    │ • Revise Exec Summary   │
                                                    │ • Revise Closing        │
                                                    │ • Reassemble draft      │
                                                    └─────────────────────────┘
                                                                    │
                                                                    ▼
                                                    fact_checker / validator
```

### Workflow Integration

```python
# In src/workflow.py - add AFTER toc_generator
workflow.add_node("revise_summary_sections", revise_summary_sections)
workflow.add_edge("toc_generator", "revise_summary_sections")
workflow.add_edge("revise_summary_sections", "fact_checker")
```

### Implementation

```python
def revise_summary_sections(state: MemoState) -> dict:
    """
    Post-generation agent that rewrites Executive Summary and Closing Assessment
    based on the complete final draft content.
    """
    company_name = state["company_name"]
    output_dir = get_latest_output_dir(company_name)

    # 1. Load the COMPLETE final draft
    final_draft_path = output_dir / "4-final-draft.md"
    if not final_draft_path.exists():
        return {"messages": ["No final draft found - skipping summary revision"]}

    full_memo_content = final_draft_path.read_text()

    # 2. Extract key data points from the full memo
    extracted_data = extract_memo_highlights(full_memo_content)

    # 3. Revise Executive Summary
    exec_summary = revise_executive_summary(
        full_memo=full_memo_content,
        extracted_data=extracted_data,
        state=state
    )

    # 4. Revise Closing Assessment
    closing = revise_closing_assessment(
        full_memo=full_memo_content,
        extracted_data=extracted_data,
        state=state
    )

    # 5. Save revised sections
    sections_dir = output_dir / "2-sections"
    (sections_dir / "01-executive-summary.md").write_text(exec_summary)
    # Closing might be 10-closing-assessment.md or similar
    closing_files = list(sections_dir.glob("*closing*.md")) + list(sections_dir.glob("*recommendation*.md"))
    if closing_files:
        closing_files[0].write_text(closing)

    # 6. Trigger reassembly
    reassemble_final_draft(output_dir)

    return {
        "messages": [
            f"Revised Executive Summary based on full memo content",
            f"Revised Closing Assessment based on full memo content",
            f"Reassembled final draft with updated bookend sections"
        ]
    }
```

### Executive Summary Revision Prompt

```
You are revising the Executive Summary for an investment memo.

You have access to the COMPLETE final memo below. Write a NEW Executive Summary that:

1. ACCURATELY REFLECTS the actual content (not speculation)
2. HIGHLIGHTS A FEW KEY METRICS from the body (funding, traction, market size/TAM)
3. AVOIDS hedging language ("data not available") unless truly warranted
4. PROVIDES clear, confident framing of the opportunity

DO NOT:
- Make excuses for missing data if the data IS present in the memo
- Make excuses in general, just try to write a good summary.
- Use vague language when specific numbers are available
- Add information not present in the memo

Target: {target_words} words

FULL MEMO CONTENT:
{full_memo}

EXTRACTED KEY DATA:
- Funding: {funding}
- Traction: {traction}
- Market: {market}

Write the revised Executive Summary:
```

### Closing Assessment Revision Prompt

```
You are revising the Closing Assessment for an investment memo.

Based on the COMPLETE memo content below, write a final assessment that:

1. SYNTHESIZES the full analysis (not just repeats the summary)
2. WEIGHS strengths against risks based on ACTUAL content
3. PROVIDES concrete next steps or due diligence items
4. GIVES clear recommendation with specific rationale
5. TARGETS around 600 words, and up to three paragraphs.

Investment Mode: {mode}
- "consider": Prospective analysis - recommend PASS/CONSIDER/COMMIT
- "justify": Retrospective justification - explain why we invested

FULL MEMO CONTENT:
{full_memo}

KEY STRENGTHS IDENTIFIED:
{strengths}

KEY RISKS IDENTIFIED:
{risks}

Write the revised Closing Assessment ({target_words} words):
```

### CLI Standalone Usage

```bash
# Revise summary sections for a specific company
python -m src.cli.revise_summaries "CompanyName"

# Revise for specific version
python -m src.cli.revise_summaries "CompanyName" --version v0.0.4

# Dry run (preview changes without writing)
python -m src.cli.revise_summaries "CompanyName" --dry-run
```

### Reassembly After Revision

After revising the sections, the final draft must be reassembled:

```python
def reassemble_final_draft(output_dir: Path) -> None:
    """
    Reassemble 4-final-draft.md from all sections after summary revision.

    Preserves:
    - Header (header.md)
    - TOC (existing)
    - All sections in order
    - Citations block
    """
    # Load existing to preserve TOC and citations
    existing = (output_dir / "4-final-draft.md").read_text()
    toc_block = extract_toc_block(existing)
    citations_block = extract_citations_block(existing)

    # Reassemble with revised sections
    parts = []
    if (output_dir / "header.md").exists():
        parts.append((output_dir / "header.md").read_text())
    if toc_block:
        parts.append(toc_block)
    for section in sorted((output_dir / "2-sections").glob("*.md")):
        parts.append(section.read_text())
    if citations_block:
        parts.append(citations_block)

    (output_dir / "4-final-draft.md").write_text("\n\n---\n\n".join(parts))
```

### Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Summary matches body content | ~60% | 95%+ |
| False "data unavailable" statements | Common | 0 |
| Specific metrics in summary | ~3 | 8+ |
| Bookend coherence with body | Medium | High |

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

The quality agents run at different points in the pipeline:

### Pre-Assembly Agents (before toc_generator)

```python
# Quality improvement agents (run on section files BEFORE assembly)
workflow.add_node("redundancy_reducer", redundancy_reducer_agent)
workflow.add_node("format_checker", format_checker_agent)
workflow.add_node("introduction_revisor", introduction_revisor_agent)

# Pre-assembly sequence
workflow.add_edge("citation_enrichment", "redundancy_reducer")
workflow.add_edge("redundancy_reducer", "format_checker")
workflow.add_edge("format_checker", "introduction_revisor")
workflow.add_edge("introduction_revisor", "toc_generator")
```

### Post-Assembly Agent (after toc_generator)

```python
# Summary revision runs AFTER assembly so it can read the complete final draft
workflow.add_node("revise_summary_sections", revise_summary_sections)

# Post-assembly sequence
workflow.add_edge("toc_generator", "revise_summary_sections")
workflow.add_edge("revise_summary_sections", "fact_checker")
```

## Order Rationale

**Pre-Assembly (on section files):**
1. **redundancy_reducer** - removes duplicate content before other agents process
2. **format_checker** - clean formatting for easier LLM processing
3. **introduction_revisor** - improves section transitions and openings

**Assembly:**
4. **toc_generator** - creates TOC and assembles `4-final-draft.md`

**Post-Assembly (on complete draft):**
5. **revise_summary_sections** - reads COMPLETE final draft, rewrites Executive Summary and Closing Assessment based on actual content, then reassembles

**Validation:**
6. **fact_checker** / **validator** - validates the revised memo

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

1. **`revise_summary_sections`** - HIGHEST priority, solves the "making excuses" problem in Executive Summary
2. `format_checker` - Rule-based, no LLM needed, quick win
3. `redundancy_reducer` - High value, noticeable quality improvement
4. `introduction_revisor` - Nice-to-have, polish layer

## Notes

- Pre-assembly agents (`redundancy_reducer`, `format_checker`, `introduction_revisor`) operate on `2-sections/*.md` files
- `revise_summary_sections` is unique: runs AFTER assembly, reads `4-final-draft.md`, then saves revised sections and triggers reassembly
- Final validation happens AFTER `revise_summary_sections`
- Each agent should be idempotent (safe to run multiple times)
- Log changes made for debugging

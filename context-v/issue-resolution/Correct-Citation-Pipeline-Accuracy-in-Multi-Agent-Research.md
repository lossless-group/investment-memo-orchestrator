# Correct Citation Pipeline Accuracy in Multi-Agent Research

**Status**: OPEN
**Priority**: HIGH
**Discovered**: 2025-12-15
**Affected Components**: Perplexity Research, Writer, Citation Enrichment, Revise Summary, Assembly
**Impact**: Final memos contain citation markers `[^N]` with NO corresponding definitions, rendering citations useless and breaking HTML/PDF exports

---

## Executive Summary

The citation pipeline is fundamentally broken across multiple agents. Citations flow through the system in a "lossy" manner where:
1. Perplexity outputs ALL citation definitions with the same key (`[^1]:`)
2. The writer preserves inline refs but strips definitions
3. Citation enrichment adds empty `### Citations` blocks
4. Summary revision generates new citation markers with no definitions
5. Final assembly finds no definitions to consolidate

**Result**: Final memos have 50-100+ inline `[^N]` references pointing to NOTHING, and HTML exports show literal `[^17]` text instead of clickable footnotes.

---

## Detailed Problem Analysis

### The Expected Flow

```
Perplexity Research → Writer Polish → Citation Enrichment → Assembly
     [^1]: URL1           [^1]              [^1]: URL1        [^1]: URL1
     [^2]: URL2           [^2]              [^2]: URL2        [^2]: URL2
     [^3]: URL3           [^3]              [^3]: URL3        [^3]: URL3
```

### The Actual Flow

```
Perplexity Research → Writer Polish → Citation Enrichment → Assembly
     [^1]: URL1           [^1]              [^1]              [^1]
     [^1]: URL2           [^2]              [^2]              [^2]
     [^1]: URL3           [^3]              [^3]              [^3]
     [^1]: URL4           ...               ...               ...
   (ALL same key!)      (no defs)      (### Citations       (NO DEFS!)
                                        but EMPTY)
```

---

## Component-by-Component Failure Analysis

### 1. Perplexity Section Research (`src/agents/research_enhanced.py`)

**File**: `src/agents/research_enhanced.py`
**Function**: `research_section_with_perplexity()`

**Problem**: Perplexity Sonar Pro returns citations, but the response parsing outputs ALL citation definitions with the key `[^1]:`.

**Evidence** (from `io/hypernova/deals/Voicerail/outputs/Voicerail-v0.0.1/1-research/02-origins-research.md`):

```markdown
### Citations: 2025, Jun 23. [Agentic AI Startup...](https://...). PR Newswire.

[^1]: 2025, Jun 23. [VoiceCare AI Raises $4.54 Million...](https://...). The SaaS News.

[^1]: 2024, Oct 15. [Voice AI Market Report 2024](https://...). CB Insights.

[^1]: 2025, Sep 12. [VoiceCare AI Launches...](https://...). Fierce Healthcare.

[^1]: 2025, Jun 23. [VoiceCare AI Raises $4.54 Million...](https://...). The SaaS News.

[^1]: 2025, Sep 12. [VoiceCare AI Launches...](https://...). Fierce Healthcare.

[^1]: 2025, Mar 05. [Call Center Attrition Hits 45%...](https://...). Gartner.

[^1]: 2025, Jan 22. [Global Voice Ops Market $50B...](https://...). IDC.
```

**Note**: EVERY citation definition is `[^1]:` - they are never uniquely numbered.

**Root Cause**: The Perplexity API returns citations in a format that the parsing code doesn't properly enumerate. The code likely extracts citation URLs but assigns them all the same footnote key.

**Location to Fix**: `src/agents/research_enhanced.py` around the `research_section_with_perplexity()` function where Perplexity responses are parsed.

---

### 2. Writer Agent (`src/agents/writer.py`)

**File**: `src/agents/writer.py`
**Function**: `polish_section_research()`

**Problem**: The writer "polishes" Perplexity research output, generating new prose with inline citations `[^1]`, `[^2]`, `[^3]`, etc. BUT it does NOT carry over the citation definitions from the research file.

**Evidence** (from `io/hypernova/deals/Voicerail/outputs/Voicerail-v0.0.1/2-sections/02-origins.md`):

```markdown
# Origins

Voicerail emerges at the intersection of three converging forces...
annually—over 90% still handled manually.[^1] This creates a $50 billion
annual inefficiency burden globally as of 2025...[^2]

...

### Citations

```

**Note**: The `### Citations` header exists but there are NO definitions below it. The file ends with just the header.

**Root Cause**: The `polish_section_research()` function sends research content to Claude for rewriting. Claude generates inline `[^N]` references in the prose but doesn't include the actual URL definitions. The function doesn't extract definitions from the input research and append them to the output.

**Location to Fix**: `src/agents/writer.py` in `polish_section_research()` - need to:
1. Extract citation definitions from input research content
2. Renumber them to match the inline refs Claude generates
3. Append the definitions to the polished output

---

### 3. Citation Enrichment Agent (`src/agents/citation_enrichment.py`)

**File**: `src/agents/citation_enrichment.py`
**Function**: `enrich_section_citations()`

**Problem**: This agent is supposed to add citations to sections that lack them. It adds the `### Citations` header but the definitions block is empty because:
1. The input sections already have inline `[^N]` refs (from writer)
2. The agent calls Perplexity to "enrich" but doesn't properly capture returned citations
3. The global renumbering function `renumber_citations_globally()` looks for definitions under `### Citations` and finds nothing

**Evidence**: Section files have `### Citations` headers with no content below them.

**Root Cause**: The enrichment logic assumes citations will be returned in a parseable format, but the Perplexity response handling has the same `[^1]:` duplication issue as the research phase.

**Location to Fix**: `src/agents/citation_enrichment.py` - specifically the citation extraction and definition handling logic.

---

### 4. Revise Summary Sections Agent (`src/agents/revise_summary_sections.py`)

**File**: `src/agents/revise_summary_sections.py`
**Function**: `revise_summary_sections()`

**Problem**: This agent rewrites the Executive Summary and Closing Assessment sections based on the full memo content. It uses Claude to generate new prose, and Claude often includes inline citation markers like `[^1]`, `[^2]` in its output - BUT these are "hallucinated" citations with no corresponding definitions.

**Evidence** (from final draft Executive Summary):

```markdown
## 01. Executive Summary

# Investment Recommendation: **CONSIDER**

Voicerail is building AI voice infrastructure—a programmable, low-latency API
and orchestration layer that enables businesses to deploy LLM-powered phone
agents at scale.[^1] This memo evaluates a **Seed-stage investment**...
```

The `[^1]` here has no definition because Claude generated it without providing source URLs.

**Root Cause**: The prompts (`EXEC_SUMMARY_PROMPT`, `CLOSING_PROMPT`) don't instruct Claude to avoid citation markers or to only use citations that exist in the source material. Claude is pattern-matching on the input content (which has `[^N]` markers) and reproducing them without understanding they need definitions.

**Location to Fix**: `src/agents/revise_summary_sections.py`:
1. Add prompt instructions to NOT generate citation markers
2. OR extract existing citations from the full memo and instruct Claude to only use those
3. OR post-process to strip undefined citation markers

---

### 5. Assembly / Global Renumbering (`src/agents/citation_enrichment.py`)

**File**: `src/agents/citation_enrichment.py`
**Function**: `renumber_citations_globally()`

**Problem**: This function is supposed to:
1. Collect all citation definitions from each section's `### Citations` block
2. Renumber them sequentially across the entire memo
3. Consolidate into ONE citation block at the end

But since the section files have EMPTY `### Citations` blocks, it collects nothing and produces a final draft with no definitions.

**Evidence** (from `renumber_citations_globally()` at line 302-304):

```python
# Split content from citations
parts = section_content.split("### Citations")
main_content = parts[0].strip() if parts else section_content.strip()
citations_section = parts[1].strip() if len(parts) > 1 else ""
```

When `citations_section` is empty (which it always is), no definitions are collected.

**Root Cause**: Garbage in, garbage out. The function works correctly IF citation definitions exist, but they don't because of upstream failures.

---

### 6. CLI Assembly (`cli/assemble_draft.py`)

**File**: `cli/assemble_draft.py`

**Problem**: The CLI assembly tool calls `renumber_citations_globally()` and has the same issue - it relies on section files having citation definitions which they don't.

**Additional Issue**: Running `assemble_draft.py` on a memo that previously had citation definitions (from the workflow's original assembly) will OVERWRITE the file and LOSE all definitions because it re-reads from the empty section files.

**Evidence**: Running `python cli/assemble_draft.py io/hypernova/deals/Voicerail/outputs/Voicerail-v0.0.1` resulted in:
- Before: 258 footnote definitions in final draft
- After: 0 footnote definitions (Summary showed "Citations: 69" but these were inline refs with no definitions)

---

## Impact Analysis

### User-Facing Impact

1. **Broken Footnotes in HTML**: Pandoc converts `[^N]` to clickable footnotes only if `[^N]:` definitions exist. Without definitions, literal `[^17]` text appears in the HTML.

2. **Professional Credibility**: Investment memos with broken citations look unprofessional and undermine trust in the analysis.

3. **Verification Impossible**: Readers cannot verify claims because citation sources are missing.

### Quantified Impact (Voicerail Example)

- **Inline citations**: 69+ `[^N]` references throughout the memo
- **Definitions available**: 0
- **Unconverted in HTML**: 36 literal `[^N]` markers visible to readers
- **Converted but dangling**: 153 footnote links pointing to nonexistent definitions

---

## Proposed Solutions

### Phase 1: Immediate Fixes (Stop the Bleeding)

#### 1.1 Fix Perplexity Citation Parsing

**File**: `src/agents/research_enhanced.py`

```python
def parse_perplexity_citations(response_text: str) -> Tuple[str, List[str]]:
    """
    Parse Perplexity response and extract citations with UNIQUE numbering.

    Returns:
        Tuple of (content_with_numbered_refs, list_of_citation_definitions)
    """
    # Extract citation URLs from Perplexity response
    # Assign unique [^1], [^2], [^3] numbers
    # Return both the renumbered content AND the definitions list
```

#### 1.2 Fix Writer to Preserve Definitions

**File**: `src/agents/writer.py`

```python
def polish_section_research(research_content: str, ...) -> str:
    # BEFORE calling Claude:
    # 1. Extract citation definitions from research_content
    # 2. Build mapping: old_num -> definition_text

    # AFTER getting Claude response:
    # 1. Parse inline [^N] refs in Claude's output
    # 2. Match to original definitions where possible
    # 3. Append ### Citations block with definitions

    return polished_content + "\n\n### Citations\n\n" + definitions_block
```

#### 1.3 Fix Revise Summary Agent

**File**: `src/agents/revise_summary_sections.py`

Add to prompts:
```python
EXEC_SUMMARY_PROMPT = """...

IMPORTANT: Do NOT include citation markers like [^1] or [^2] in your response.
The Executive Summary should be a clean narrative without inline citations.
Specific claims will be cited in the body sections.

..."""
```

### Phase 2: Architectural Improvements

#### 2.1 Citation Registry Pattern

Create a centralized citation registry that:
1. Assigns globally unique IDs to each citation URL
2. Maintains URL -> citation_id mapping across all agents
3. Prevents duplicates
4. Provides lookup for any agent that needs to reference a citation

```python
# src/citations/registry.py
class CitationRegistry:
    def __init__(self):
        self._citations: Dict[str, int] = {}  # URL -> citation_id
        self._definitions: Dict[int, str] = {}  # citation_id -> full definition
        self._counter = 1

    def add(self, url: str, title: str, source: str, date: str) -> int:
        """Add citation and return its ID. Returns existing ID if URL already registered."""
        if url in self._citations:
            return self._citations[url]

        citation_id = self._counter
        self._counter += 1
        self._citations[url] = citation_id
        self._definitions[citation_id] = f"[^{citation_id}]: {date}. [{title}]({url}). {source}."
        return citation_id

    def get_definition(self, citation_id: int) -> Optional[str]:
        return self._definitions.get(citation_id)

    def get_all_definitions(self) -> str:
        return "\n\n".join(self._definitions.values())
```

#### 2.2 Citation Validation Gate

Add a validation step that runs BEFORE final assembly:

```python
def validate_citations(output_dir: Path) -> Tuple[bool, List[str]]:
    """
    Validate that all inline [^N] refs have corresponding [^N]: definitions.

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    # Collect all inline refs
    # Collect all definitions
    # Report any refs without definitions
    # Report any definitions without refs (orphans)
```

#### 2.3 State-Based Citation Tracking

Add citation tracking to `MemoState`:

```python
class MemoState(TypedDict):
    # ... existing fields ...

    # Citation tracking
    citation_registry: Dict[str, int]  # URL -> citation_id
    citation_definitions: Dict[int, str]  # citation_id -> full definition
```

This allows citations to persist across agent boundaries without relying on file parsing.

### Phase 3: Testing Infrastructure

#### 3.1 Citation Unit Tests

```python
def test_perplexity_citation_parsing():
    """Verify Perplexity responses are parsed with unique citation IDs."""

def test_writer_preserves_definitions():
    """Verify writer output includes all citation definitions from input."""

def test_assembly_consolidates_citations():
    """Verify final assembly has all citations properly numbered."""

def test_no_orphan_citations():
    """Verify no [^N] refs exist without corresponding definitions."""
```

#### 3.2 Integration Test

```python
def test_full_citation_flow():
    """End-to-end test: research -> write -> enrich -> assemble -> validate."""
    # Run mini-workflow on test company
    # Verify final draft has:
    #   - All inline [^N] refs
    #   - Matching [^N]: definitions
    #   - No duplicates
    #   - Sequential numbering
```

---

## Verification Checklist

After implementing fixes, verify:

- [ ] Research files have uniquely numbered `[^1]:`, `[^2]:`, etc.
- [ ] Section files in `2-sections/` have non-empty `### Citations` blocks
- [ ] `01-executive-summary.md` either has no citations OR has valid definitions
- [ ] `10-closing-assessment.md` either has no citations OR has valid definitions
- [ ] Final draft has ONE consolidated `### Citations` block
- [ ] All inline `[^N]` have matching `[^N]:` definitions
- [ ] HTML export shows zero literal `[^N]` text
- [ ] PDF export has clickable footnotes

---

## Files to Modify

| File | Priority | Change Required |
|------|----------|-----------------|
| `src/agents/research_enhanced.py` | HIGH | Fix Perplexity citation parsing to use unique IDs |
| `src/agents/writer.py` | HIGH | Preserve citation definitions through polish step |
| `src/agents/citation_enrichment.py` | MEDIUM | Ensure enrichment adds real definitions |
| `src/agents/revise_summary_sections.py` | MEDIUM | Prevent hallucinated citations in summaries |
| `cli/assemble_draft.py` | LOW | Add warning if sections have empty citation blocks |
| `src/state.py` | MEDIUM | Add citation registry to MemoState (Phase 2) |

---

## Related Documentation

- `CLAUDE.md` - Citation System section documents expected format
- `context-vigilance/Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` - Agent pipeline overview
- `changelog/2025-11-20_01.md` - Section-by-section processing migration

---

## Appendix: Raw Evidence

### A. Research File with Duplicate `[^1]:` Keys

```
File: io/hypernova/deals/Voicerail/outputs/Voicerail-v0.0.1/1-research/02-origins-research.md

[^1]: 2025, Jun 23. [VoiceCare AI Raises $4.54 Million...]. The SaaS News.
[^1]: 2024, Oct 15. [Voice AI Market Report 2024]. CB Insights.
[^1]: 2025, Sep 12. [VoiceCare AI Launches...]. Fierce Healthcare.
[^1]: 2025, Jun 23. [VoiceCare AI Raises $4.54 Million...]. The SaaS News.
[^1]: 2025, Sep 12. [VoiceCare AI Launches...]. Fierce Healthcare.
[^1]: 2025, Mar 05. [Call Center Attrition Hits 45%...]. Gartner.
[^1]: 2025, Jan 22. [Global Voice Ops Market $50B...]. IDC.
```

### B. Section File with Empty Citations Block

```
File: io/hypernova/deals/Voicerail/outputs/Voicerail-v0.0.1/2-sections/02-origins.md

...content with [^1], [^2], [^3] inline refs...

### Citations

(END OF FILE - nothing below this header)
```

### C. Final Draft Citation Numbering Gap

```
File: io/hypernova/deals/Voicerail/outputs/Voicerail-v0.0.1/6-Voicerail-v0.0.1.md

Body uses: [^16], [^17], [^18], [^19], [^20], [^21], [^22]

Definitions jump from [^15] to [^23] - NO definitions for [^16] through [^22]
```

### D. HTML Export with Unconverted Citations

```
grep output showing 36 literal [^N] markers in HTML:

587:        annually—over 90% still handled manually.[^22] This creates a
596:        year-over-year driven by e-commerce growth.[^17] Human agents
599:        work.[^18] The result is a vicious cycle...
```

---

## Conclusion

This is a systemic failure across the citation pipeline, not a single-point bug. Each agent assumes the previous agent produced valid citation data, but none of them actually do. The fix requires:

1. **Immediate**: Patch each agent to handle citations correctly
2. **Medium-term**: Implement centralized citation registry
3. **Long-term**: Add comprehensive citation validation and testing

Until fixed, all generated memos should be manually reviewed for citation accuracy, and HTML/PDF exports may contain broken footnote references.

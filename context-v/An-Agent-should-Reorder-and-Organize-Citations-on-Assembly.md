# Agent Should Reorder and Organize Citations on Assembly

## Problem Statement

When the final draft is assembled from individual section files, citations end up:
1. **Scattered** - Each section has its own citation definitions at the bottom
2. **Duplicate numbered** - Multiple sections may have `[^1]`, `[^2]`, etc.
3. **Non-sequential** - After invalid citations are removed, gaps appear (e.g., `[^1]`, `[^3]`, `[^5]`)
4. **Not consolidated** - Citations should be in ONE block at the end of the document

## Current Architecture Gap

The current flow:
```
1-research/ → 2-sections/ → [enrichment agents] → assembly → 6-final-draft.md
```

Each section file maintains its own citations:
```markdown
## 3. Opening

Content with [^1] and [^2] citations...

[^1]: Source A...
[^2]: Source B...
```

When assembled, the final draft concatenates sections without:
- Renumbering citations globally
- Consolidating citation definitions to one block
- Removing duplicate definitions

## Required Behavior

### During Assembly Phase

The `assemble_draft` function (or a dedicated citation assembly agent) should:

1. **Extract all inline citation references** from all sections
   - Pattern: `[^N]` where N is any number
   - Track which sections use which citation numbers

2. **Extract all citation definitions** from all sections
   - Pattern: `[^N]: ...` at end of each section
   - Map old numbers to their full definition text

3. **Build a global renumbering map**
   - Assign new sequential numbers starting at 1
   - Order by first appearance in document

4. **Update inline references** in all content
   - Replace `[^old]` with `[^new]` throughout

5. **Consolidate all definitions** into ONE block at the end
   - Remove citation definitions from section bodies
   - Append single `### Citations` section at document end
   - List all citations in new numerical order

### Example Transformation

**Before (scattered per-section):**
```markdown
## 2. Origins
Content [^1] and [^3]...
[^1]: Source A...
[^3]: Source C...

## 3. Opening
Content [^1] and [^2]...
[^1]: Source D (different!)...
[^2]: Source E...
```

**After (consolidated):**
```markdown
## 2. Origins
Content [^1] and [^2]...

## 3. Opening
Content [^3] and [^4]...

---

### Citations

[^1]: Source A...
[^2]: Source C...
[^3]: Source D...
[^4]: Source E...
```

## Implementation Options

### Option 1: Enhance `assemble_draft` CLI

Update `cli/assemble_draft.py` to:
1. Parse sections for citations before concatenation
2. Build global numbering
3. Transform content during assembly
4. Append consolidated citation block

### Option 2: Dedicated Citation Assembly Agent

Create `src/agents/citation_assembly.py` that:
1. Runs after all enrichment
2. Processes all files in `2-sections/`
3. Removes per-section citation blocks
4. Updates inline references with global numbers
5. Writes consolidated citations to a separate file or appends to sections

### Option 3: Modify Citation Enrichment Agent

Update `src/agents/citation_enrichment.py` to:
1. Track citations globally across all sections
2. Perform consolidation as final step
3. Write the assembled draft directly

## Recommended Approach

**Option 1 (Enhance `assemble_draft`)** is recommended because:
- Assembly is the natural point for consolidation
- Keeps citation logic centralized
- Works regardless of which agents ran
- Single source of truth for final output format

## Workflow Position

```
revise_summaries → remove_invalid_sources → [CITATION ASSEMBLY] → validate_citations → fact_check
```

Or integrated into the existing flow:
```
citation_enrichment (per-section) → toc_generator → revise_summaries → remove_invalid_sources → assemble_draft (WITH CITATION CONSOLIDATION) → validate_citations
```

## Key Functions Needed

```python
def extract_inline_citations(content: str) -> List[str]:
    """Extract all [^N] references from content."""
    pass

def extract_citation_definitions(content: str) -> Dict[str, str]:
    """Extract all [^N]: ... definitions from content."""
    pass

def remove_citation_definitions(content: str) -> str:
    """Remove citation definition blocks from content."""
    pass

def renumber_citations(content: str, old_to_new: Dict[str, str]) -> str:
    """Replace all [^old] with [^new] in content."""
    pass

def format_citation_block(citations: Dict[str, str]) -> str:
    """Format consolidated citations as markdown block."""
    pass
```

## Citation Format Standard

All citations should follow this format:
```
[^N]: YYYY, MMM DD. [Title](URL). Source. Published: YYYY-MM-DD | Updated: N/A
```

Example:
```
[^1]: 2024, Mar 05. [Generative AI in healthcare](https://www.mckinsey.com/...). McKinsey & Company. Published: 2024-03-05 | Updated: N/A
```

## Acceptance Criteria

After assembly, the final draft should have:
- [ ] Sequential citation numbers starting at `[^1]`
- [ ] No gaps in numbering (1, 2, 3... not 1, 3, 5...)
- [ ] No duplicate citation numbers
- [ ] All citation definitions in ONE block at document end
- [ ] No citation definitions scattered within section bodies
- [ ] Inline references match their definitions exactly

## Related Files

- `cli/assemble_draft.py` - Current assembly logic
- `src/agents/citation_enrichment.py` - Adds citations per-section
- `src/agents/remove_invalid_sources.py` - Removes invalid citations
- `src/agents/citation_validator.py` - Validates citation format/URLs

## Current Issue (2025-12-14)

The `remove_invalid_sources` agent successfully:
1. Validated 28 citations
2. Identified 10 invalid (404s and XXXXX placeholder)
3. Cleaned `1-research/` files (10 updated)
4. Cleaned `2-sections/` files (8 updated)

However, the assembly step failed because:
- `cli.assemble_draft` module could not be imported
- Fallback assembly just concatenated files without citation consolidation
- Result: 93 citations in final draft (scattered, not renumbered)

The assembly CLI needs to be fixed to be importable as a module, OR the citation consolidation logic needs to be moved into the `remove_invalid_sources` agent or a new dedicated agent.

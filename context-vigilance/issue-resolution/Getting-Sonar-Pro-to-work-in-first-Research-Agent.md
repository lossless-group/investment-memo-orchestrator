# Issue Resolution: Getting Sonar Pro to Work in Research Agent with Citations in Original Section Development

**Date Started**: 2025-11-21
**Status**: =
 Diagnosis Complete - Solution Planning
**Priority**: High
**Impact**: Citations are added as post-processing instead of during initial section writing

---

## Problem Statement

**Expected Behavior:**
- Research agent should use Perplexity `sonar-pro` API to gather information WITH citations on the first web research performed by the research agent.  
   - Research agent should use the UNCITED research.json and research.md, which is output of the [Tavily API](https://tavily.com)
- Writer agent should include citations in the original section drafts (not as post-processing)
- When deck exists, deck should be cited as the first reference source before web research
- Citations should be integral to the writing process, not retrofitted later

# Integrate Premium Data Sources
https://www.perplexity.ai/help-center/en/articles/12870803-premium-data-sources

**Actual Behavior:**
- Research agent DOES use `sonar-pro` for data gathering
- BUT: Research sources are NOT translated into citations during section writing
- Writer agent writes sections WITHOUT any citations
- Citations are only added MUCH LATER by Citation Enrichment Agent (separate pipeline step)
- This creates a disconnect between research and writing phases

**Why This Matters:**
1. **Quality**: Citations should inform the writing, not be added retroactively
2. **Accuracy**: Writer should know what claims have source support during composition
3. **Efficiency**: Retrofitting citations requires re-reading all sections
4. **Deck Priority**: Deck data should be cited first, then augmented with web research citations

---

## Workflow Architecture Analysis

### Current Pipeline Flow

```
deck_analyst � research � draft � trademark � socials � links � viz � CITE � validate � finalize
    �            �          �                                        �
 (no cites)  (has sources) (no cites)                        (adds cites HERE)
```

**Detailed Agent Sequence** (from `src/workflow.py:219-231`):

1. **Deck Analyst** (`src/agents/deck_analyst.py`)
   - Extracts info from pitch deck PDF
   - Creates initial section drafts via `create_initial_section_drafts()`
   - Section drafts have `citations=[]` (line 432)
   - **NO CITATIONS ADDED**

2. **Research Agent** (`src/agents/research_enhanced.py`)
   - **DOES use sonar-pro** (line 92: `model="sonar-pro"`)
   - Searches web via Perplexity or Tavily
   - Synthesizes findings into structured JSON
   - Returns `ResearchData` with `sources` field
   - **Sources exist but NOT formatted as citations**

3. **Writer Agent** (`src/agents/writer.py`)
   - Takes `research` data from state
   - Writes sections iteratively using outline guidance
   - Research JSON passed to prompts (line 215: truncated to 3k chars)
   - **Writer prompts DO NOT instruct adding citations**
   - Sections written WITHOUT citation markers

4. **Enrichment Agents** (trademark, socials, links, visualizations)
   - Modify section content for various enrichments
   - Still no citations

5. **Citation Enrichment Agent** (`src/agents/citation_enrichment.py`)
   - **DOES use sonar-pro** (line 121: `model="sonar-pro"`)
   - Reads already-written sections
   - Calls Perplexity to ADD citations retroactively
   - Inserts `[^1] [^2]` markers and builds citation list
   - **Citations added as POST-PROCESSING**

### Key Files Reference

| File | Lines | Purpose | Sonar-Pro Usage |
|------|-------|---------|-----------------|
| `src/workflow.py` | 219-231 | Pipeline orchestration | N/A |
| `src/agents/deck_analyst.py` | 381-435 | Creates initial drafts | L No citations |
| `src/agents/research_enhanced.py` | 88-109 | Web research synthesis |  Line 92 |
| `src/agents/writer.py` | 187-281 | Section writing | L No citation instructions |
| `src/agents/citation_enrichment.py` | 87-130 | Retroactive citation adding |  Line 121 |

---

## Root Cause Analysis

### Discovery 1: Research Agent DOES Use Sonar-Pro

**Evidence:**
```python
# src/agents/research_enhanced.py:88-109
class PerplexityProvider(WebSearchProvider):
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        response = self.client.chat.completions.create(
            model="sonar-pro",  #  CONFIRMED: Using sonar-pro
            messages=[...]
        )
```

**What This Means:**
- Sonar-pro IS being called during research phase
- Research data DOES include source information
- Problem is NOT with sonar-pro availability

### Discovery 2: Research Sources Are Not Citation-Ready

**Evidence:**
```python
# src/agents/research_enhanced.py:101-106
return [{
    'title': 'Perplexity Research',
    'url': 'perplexity://research',  # L NOT a real URL
    'content': content               # L Citations embedded in content, not structured
}]
```

**What This Means:**
- Perplexity sonar-pro returns text WITH inline citations
- BUT: Citations are embedded in the response text, not extracted
- Research provider returns synthetic URL (`perplexity://research`)
- Sources are not structured as citation objects

### Discovery 3: Writer Agent Ignores Citation Capability

**Evidence:**
```python
# src/agents/writer.py:254-278
user_prompt = f"""Write ONLY the "{section_def.name}" section...

RESEARCH DATA (summary):
{research_json}

STYLE GUIDE:
{style_guide}

Write ONLY this section's content (no section header, it will be added automatically).
Be specific, analytical, use metrics from research.
"""
```

**What This Means:**
- Research data is passed to writer (truncated to 3k chars)
- Prompt does NOT instruct "add inline citations"
- Prompt does NOT provide citation format guidance
- Writer has NO INSTRUCTIONS to use `[^1]` citation markers

### Discovery 4: Deck Citations Are Not Preserved

**Evidence:**
```python
# src/agents/deck_analyst.py:428-433
drafts[section_key] = SectionDraft(
    section_name=section_name,
    content=content,
    word_count=len(content.split()),
    citations=[]  # L Empty - deck not cited
)
```

**What This Means:**
- Deck data is extracted and used for drafting
- BUT: Deck itself is NOT added as a citation source
- Deck should be `[^1]` for any deck-derived claims
- Initial drafts lose provenance of information source

---

## Gap Analysis

### Missing Components

1. **Citation-Ready Research Sources**
   - Current: Research returns free-text content
   - Needed: Structured citation objects with proper URLs, dates, authors

2. **Writer Citation Instructions**
   - Current: Writer prompts say "be specific, analytical"
   - Needed: Writer prompts must say "add inline citations [^1] [^2] for all factual claims"

3. **Deck as Citation Source**
   - Current: Deck data used but not cited
   - Needed: Deck added to state as `[^deck]` or `[^1]` citation source

4. **Source Propagation**
   - Current: Research sources exist but not passed to writer in usable form
   - Needed: Sources formatted as citation list, passed to writer prompts

### Why Current Approach Works (But Is Suboptimal)

**Citation Enrichment Agent Workaround:**
- Runs AFTER writing is complete
- Calls sonar-pro AGAIN to find sources
- Adds citations retroactively
- **Problem**: Wastes API calls (research + enrichment both call sonar-pro)
- **Problem**: Citations not available during writing (can't inform content decisions)

---

## Attempt Log

### Attempt #1: Diagnosis Phase (2025-11-21)

**Goal:** Understand current architecture and identify why citations aren't in original drafts

**Actions Taken:**
1.  Reviewed workflow orchestration (`src/workflow.py`)
2.  Traced pipeline: deck_analyst � research � writer � citation_enrichment
3.  Confirmed research agent DOES use sonar-pro (line 92)
4.  Confirmed writer agent does NOT add citations
5.  Identified gap: research sources not passed to writer in citation-ready format
6.  Identified gap: deck data not preserved as citation source

**Findings:**
- Research agent works correctly (uses sonar-pro)
- Writer agent is missing citation instructions
- Deck analyst doesn't preserve deck as citation source
- Citation enrichment duplicates work (calls sonar-pro again)

**Next Steps:**
- [ ] Design solution: How to structure research sources as citations
- [ ] Design solution: How to instruct writer to use citations
- [ ] Design solution: How to cite deck as primary source
- [ ] Plan implementation without breaking existing pipeline

**Status:**  Diagnosis Complete

---

## Proposed Solutions (To Be Attempted)

### Option A: Enhance Research Agent Output (Recommended)

**Concept:** Restructure research sources as citation-ready objects

**Changes Required:**
1. Modify `PerplexityProvider.search()` to extract citations from sonar-pro response
2. Parse Perplexity's embedded citations into structured format
3. Add citations to `ResearchData` as list of `Citation` objects
4. Update writer prompts to include citation list and instruction to use them

**Pros:**
- Citations available during writing
- Single sonar-pro call (research phase only)
- Deck can be citation #1
- Writer makes informed decisions about what to cite

**Cons:**
- Requires parsing Perplexity's citation format
- May need new state schema for `Citation` type
- Writer prompts get longer (citation list + instructions)

**Estimated Complexity:** Medium

---

### Option B: Make Deck a Citation Source

**Concept:** Add deck as first citation in research sources

**Changes Required:**
1. In `deck_analyst_agent()`, create a `Citation` object for the deck
2. Add deck citation to state (e.g., `state["deck_citation"]`)
3. Research agent prepends deck citation to sources list
4. Writer includes deck as `[^1]` in sections using deck data

**Pros:**
- Simple to implement
- Deck gets proper attribution
- Works with existing citation enrichment

**Cons:**
- Doesn't solve missing citations in writer phase
- Still requires Option A or C for web research citations

**Estimated Complexity:** Low

---

### Option C: Hybrid Approach (Writer + Enrichment)

**Concept:** Writer adds deck citations, enrichment adds web citations

**Changes Required:**
1. Implement Option B (deck as citation source)
2. Writer adds citations ONLY for deck-derived claims
3. Citation enrichment adds citations for web research claims
4. Merge citation lists at end

**Pros:**
- Incremental improvement
- Deck properly cited immediately
- Web citations added later (existing flow)

**Cons:**
- Maintains dual-citation approach
- Still makes extra sonar-pro calls
- Doesn't fully solve efficiency issue

**Estimated Complexity:** Low-Medium

---

### Option D: Single-Pass Citation Writing (Ideal State)

**Concept:** Research returns content with citations pre-embedded, writer uses as-is

**Changes Required:**
1. Research agent requests sonar-pro to return content with inline `[^1]` markers
2. Research agent also requests citation list
3. Research stores: `{content_with_citations, citation_list}`
4. Writer incorporates content that already has citations
5. Skip citation enrichment agent entirely

**Pros:**
- Most efficient (single sonar-pro call)
- Citations native to content
- Eliminates citation enrichment step

**Cons:**
- Hardest to implement
- Perplexity format may not match our citation style
- Writer has less control over citation placement
- May break existing enrichment pipeline

**Estimated Complexity:** High

---

## Technical Notes

### Perplexity Sonar-Pro Citation Format

**What Perplexity Returns:**
- Text with inline numbered citations: `"Company was founded in 2023[1] and raised $10M[2]."`
- Sources list at end with URLs, titles, dates

**Our Format:**
- Text with Obsidian-style citations: `"Company was founded in 2023. [^1] Raised $10M. [^2]"`
- Citation list: `[^1]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: N/A`

**Mapping Required:**
- Extract Perplexity's `[1]` citations and sources
- Renumber to `[^1]` format
- Reformat source list to our template
- Adjust spacing (after punctuation, not before)

### State Schema Considerations

**Current:**
```python
ResearchData(
    company: dict,
    market: dict,
    sources: list[str]  # L Just URLs, not structured citations
)
```

**Needed:**
```python
Citation(
    id: int,
    title: str,
    url: str,
    author: Optional[str],
    publisher: Optional[str],
    published_date: str,
    updated_date: Optional[str]
)

ResearchData(
    company: dict,
    market: dict,
    sources: list[str],        # Original URLs
    citations: list[Citation]  #  NEW: Structured citations
)
```

---

## Success Criteria

Solution will be considered successful when:

1.  Deck data includes citation to deck PDF as first source
2.  Research agent returns structured citations (not just URLs)
3.  Writer agent includes inline citation markers `[^1] [^2]` in section content
4.  Citations are present in section files BEFORE enrichment agents run
5.  Citation enrichment agent either:
   - Skipped entirely (if writer handles all citations), OR
   - Only adds NEW citations for claims writer didn't cite
6.  No duplicate sonar-pro API calls for same information
7.  Final memo has comprehensive citations from deck + web sources

---

## Related Files

**Core Workflow:**
- `src/workflow.py` - Pipeline orchestration
- `src/state.py` - State schema definitions

**Agents:**
- `src/agents/deck_analyst.py` - Initial section drafts from deck
- `src/agents/research_enhanced.py` - Web research with sonar-pro
- `src/agents/writer.py` - Section writing (currently no citations)
- `src/agents/citation_enrichment.py` - Retroactive citation addition

**Utilities:**
- `src/artifacts.py` - Saving research and section files
- `improve-section.py` - Section improvement tool (uses sonar-pro with citations)

---

## References

**Documentation:**
- Perplexity Sonar Pro API: https://docs.perplexity.ai/
- Obsidian Citation Format: https://help.obsidian.md/Editing+and+formatting/Basic+formatting+syntax#Footnotes

**Related Issues:**
- `context-vigilance/Format-Memo-According-to-Template-Input.md` - Original issue documentation
- `changelog/2025-11-16_03.md` - Sonar-pro integration history

**Working Examples:**
- `improve-section.py:251` - Successfully uses sonar-pro with citations in single call
- `run-citations-now.py:40` - Citation enrichment sonar-pro usage

---

## Next Actions

**Immediate:**
1. [ ] Decide on solution approach (A, B, C, or D)
2. [ ] Create proof-of-concept for chosen approach
3. [ ] Test with single section first
4. [ ] Verify citation format matches Obsidian style

**Follow-up:**
1. [ ] Implement across all sections
2. [ ] Update state schema if needed
3. [ ] Test with deck + research pipeline
4. [ ] Validate no regression in existing citations
5. [ ] Update documentation

**Documentation:**
1. [ ] Update CLAUDE.md with new citation flow
2. [ ] Update architecture diagrams
3. [ ] Add citation flow to README

---

**Log History:**
- 2025-11-21: Initial diagnosis - identified research uses sonar-pro but writer doesn't add citations
- 2025-11-21: Analyzed pipeline flow, identified 4 solution options
- 2025-11-21: Documented success criteria and next steps

---

*This is a living document. Update with each troubleshooting attempt, preserving the journey.*

---

### Attempt #3: POC Success + Integration Planning (2025-11-21)

**Goal:** Successfully implemented POC, discovered integration gap with outline system

**What We Built:**
Created `poc-perplexity-section-research.py` that implements:
1. Perplexity Sonar Pro generates section-specific research WITH citations
2. Claude Sonnet polishes research while preserving all citations
3. Validation: minimum 5 citations, citation preservation, format checking

**POC Results: ✅ SUCCESS**

**Test: Market Context section for Avalanche**
- ✅ Perplexity generated 8 diverse sources (passed minimum 5)
- ✅ Citations in correct format: `. [^1]` (space before bracket, after punctuation)
- ✅ Citation list included at end with proper format
- ✅ Claude preserved all 8 citations during polishing (8→8)
- ✅ All validations passed

**Sources Quality:**
- Grand View Research (market sizing)
- MarketsandMarkets (AI data centers)
- JLL (data center outlook)
- McKinsey (infrastructure costs)
- Synergy Research Group (competitive landscape)
- Omdia (DCIM)
- Statista (market forecast)
- Frost & Sullivan (observability TAM)

**Citation Format Examples (CORRECT):**
```markdown
The market reached $110.53 billion in 2024. [^1]
Growing at 12.4% CAGR. [^1] [^2]
Cloud adoption accelerating. [^1]

### Citations

[^1]: 2024, May 01. [Enterprise Data Management Market](https://url.com). Publisher. Published: 2024-05-01 | Updated: N/A
```

**Validation Logic Implemented:**
1. **Minimum Citations Check**: Fails if < 5 sources
2. **Preservation Check**: Fails if Claude removes any citations
3. **Format Check**: Warns if citations don't follow `. [^N]` pattern
4. **Citation List Check**: Fails if "### Citations" section missing

**The Problem Discovered:**

**User Insight:** "We got the citations to work as expected but without the outline system we just built. They should work together elegantly, and not as a `poc` but in the system itself."

**Architecture Gap Identified:**

```
POC (Standalone):
  perplexity_research(with citations) → claude_polish(preserve) → ✅ WORKS

Main Workflow (Broken):
  outline_loaded → writer(no citations) → citation_enrichment(retrofit) → ❌ BROKEN

Outline System (Unused for citations):
  templates/outlines/*.yaml - Has citation requirements
  BUT: writer.py doesn't use them!
```

**Root Cause:**
- We built TWO separate systems instead of ONE integrated system
- POC works but doesn't use outline
- Outline exists but writer ignores citation requirements
- Citation format rules defined in multiple places inconsistently

**Files With Citation Format Rules (Found via grep):**
- `src/agents/citation_enrichment.py:67` - Retrofit approach
- `improve-section.py:219` - Improvement tool
- `poc-perplexity-section-research.py:45` - POC approach (NEW, works)
- `templates/outlines/direct-investment.yaml:1009` - Outline definition (unused)
- `templates/outlines/fund-commitment.yaml:840` - Outline definition (unused)

**Integration Required:** Merge POC approach into main workflow using outline system

---

## Integration Plan: Make POC the Real System

### Target Architecture

**New Flow:**
```
deck_analyst → tavily_research → perplexity_section_researcher → writer_polisher → enrichments → validate
                                         ↓                              ↓
                                   (WITH citations)              (preserves citations)
                                   Uses outline guidance         Uses outline format rules
                                   5-10 diverse sources         Validation: 100% preserved
```

**vs. Current (Broken) Flow:**
```
deck_analyst → tavily_research → writer → enrichments → citation_enrichment → validate
                                    ↓                           ↓
                              (no citations)              (retrofitted, often wrong format)
```

### Implementation Steps

#### 1. Create New Agent: `perplexity_section_researcher.py`

**Location:** `src/agents/perplexity_section_researcher.py`

**Purpose:** Generate section-specific research with citations BEFORE writing

**Functionality:**
- Takes: `MemoState` with research data, outline
- For EACH section in outline:
  - Build section-specific query using outline's guiding questions
  - Call Perplexity Sonar Pro with citation requirements from outline
  - Enforce minimum 5-10 diverse sources
  - Validate citation format: `. [^N]` (from outline)
  - Save to `output/{company}/1-research/{section-number}-{section-name}-research.md`
- Returns: Updated state with section research files created

**Key Features:**
- Uses outline's `guiding_questions` for targeted queries
- Uses outline's `vocabulary.citation_format` for formatting
- Uses outline's `section_vocabulary.preferred_terms` for source prioritization
- Validates minimum source diversity

#### 2. Refactor Writer Agent

**Changes to:** `src/agents/writer.py`

**Current Behavior:** Write sections from scratch using research JSON

**New Behavior:** Polish section research files while preserving citations

**Changes Required:**
```python
def write_single_section(section_def, research_file_path, ...):
    """
    Polish Perplexity research into final section.
    
    CHANGED: Now reads research file instead of creating from scratch
    """
    # Load research file (already has citations)
    research_content = research_file_path.read_text()
    
    # Count citations before polishing
    citations_before = count_citations(research_content)
    
    # Build prompt that EMPHASIZES preservation
    prompt = f"""
    Polish this research into professional section.
    
    CRITICAL: PRESERVE ALL {citations_before} CITATIONS EXACTLY.
    Citation format from outline: {outline.vocabulary.citation_format}
    
    RESEARCH WITH CITATIONS:
    {research_content}
    
    Polish for flow, structure, tone. DO NOT remove citations.
    """
    
    polished = claude.invoke(prompt)
    
    # Validate citations preserved
    citations_after = count_citations(polished)
    if citations_after != citations_before:
        raise ValueError(f"Citation preservation failed: {citations_before} → {citations_after}")
    
    return polished
```

#### 3. Update Workflow

**Changes to:** `src/workflow.py`

**Add Node:**
```python
workflow.add_node("perplexity_section_researcher", perplexity_section_researcher_agent)
```

**Update Sequence:**
```python
# OLD:
workflow.add_edge("research", "draft")

# NEW:
workflow.add_edge("research", "perplexity_section_researcher")  # ADD
workflow.add_edge("perplexity_section_researcher", "draft")
```

**Citation Enrichment Changes:**
```python
# Option A: Remove it entirely (no longer needed)
# workflow.add_node("cite", citation_enrichment_agent)  # REMOVE

# Option B: Keep as optional validator/enhancer
# workflow.add_node("cite_validate", citation_validator_agent)  # RENAME
# Only runs if initial citation count < threshold
```

#### 4. Update Outline Schema

**Add to outlines:** `templates/outlines/*.yaml`

**New Section: `citation_requirements`**
```yaml
citation_requirements:
  minimum_sources: 5
  maximum_sources: 10
  
  format:
    inline: ". [^N]"  # Space before bracket, after punctuation
    multiple: ". [^1] [^2]"  # Space before each
    list_header: "### Citations"
    
  source_diversity:
    required_types:
      - "Industry analyst reports"
      - "Financial journalism"
      - "Company sources"
    
  validation:
    - "Minimum 5 sources"
    - "Citation format correct"
    - "URLs valid and accessible"
    - "Dates included (Published/Updated)"
```

#### 5. Deprecate/Remove

**Files to deprecate:**
- `poc-perplexity-section-research.py` → Logic moves into agent
- Keep as reference/example

**Functions to modify:**
- `citation_enrichment_agent()` → Optional validator only
- OR remove entirely if not needed

### Benefits of Integration

| Aspect | Before | After |
|--------|--------|-------|
| **Citations** | Retrofitted by separate agent | Integral from the start |
| **Format** | Inconsistent, often wrong | Enforced by outline |
| **Sources** | 1-3 sources | 5-10 diverse sources |
| **API Calls** | 2× sonar-pro (research + enrich) | 1× sonar-pro (section research) |
| **Quality** | Hit or miss | Validated (fail if < 5) |
| **Architecture** | POC separate from outline | POC IS the system |
| **Maintenance** | Citation rules in 5 places | Citation rules in outline |

### Migration Path

**Phase 1: Add New Agent (No Breaking Changes)**
1. Create `perplexity_section_researcher.py`
2. Add to workflow as OPTIONAL node
3. Test with flag: `USE_SECTION_RESEARCH=true`
4. Compare output quality vs old approach

**Phase 2: Refactor Writer (Breaking Change)**
1. Update `writer.py` to read research files
2. Add validation for citation preservation
3. Test end-to-end with both agents

**Phase 3: Switch Over**
1. Make section researcher DEFAULT
2. Deprecate citation enrichment
3. Update documentation

**Phase 4: Cleanup**
1. Remove old citation enrichment if unused
2. Delete POC file (logic now in agents)
3. Consolidate citation format rules in outlines only

### Success Criteria

Integration will be considered successful when:

1. ✅ Perplexity section researcher agent exists in `src/agents/`
2. ✅ Writer agent polishes research files (not write from scratch)
3. ✅ Workflow includes section researcher before writer
4. ✅ Outline controls citation format (single source of truth)
5. ✅ All sections have 5-10 citations from diverse sources
6. ✅ Citation format validated: `. [^N]` with space
7. ✅ No duplicate sonar-pro calls (efficient)
8. ✅ POC logic integrated, not standalone

### Files to Create/Modify

**New Files:**
- `src/agents/perplexity_section_researcher.py` (extract from POC)

**Modified Files:**
- `src/agents/writer.py` (polish research, not write from scratch)
- `src/workflow.py` (add section researcher node)
- `templates/outlines/direct-investment.yaml` (add citation_requirements)
- `templates/outlines/fund-commitment.yaml` (add citation_requirements)

**Deprecated/Removed:**
- `poc-perplexity-section-research.py` (keep as reference)
- `src/agents/citation_enrichment.py` (optional: keep as validator or remove)

**Documentation Updates:**
- `CLAUDE.md` - Update architecture section
- `README.md` - Update workflow diagram
- `templates/outlines/README.md` - Document citation_requirements

---

## Status: Ready to Implement

**Next Steps:**
1. [ ] Create `src/agents/perplexity_section_researcher.py`
2. [ ] Refactor `src/agents/writer.py` to polish research
3. [ ] Update `src/workflow.py` to add section researcher node
4. [ ] Add `citation_requirements` to outline YAML files
5. [ ] Test end-to-end with WorkBack company
6. [ ] Validate all sections have 5-10 citations in correct format
7. [ ] Update documentation

**User Decision Point:** Proceed with integration? This makes the POC the real system.

---

**Log History:**
- 2025-11-21: Initial diagnosis - identified research uses sonar-pro but writer doesn't add citations
- 2025-11-21: Analyzed pipeline flow, identified 4 solution options
- 2025-11-21: Documented success criteria and next steps
- 2025-11-21: **POC SUCCESS** - Perplexity research → Claude polish works perfectly
- 2025-11-21: **REALIZATION** - POC separate from outline system, need integration
- 2025-11-21: Documented integration plan to merge POC into main workflow using outlines

---

*This is a living document. Update with each troubleshooting attempt, preserving the journey.*

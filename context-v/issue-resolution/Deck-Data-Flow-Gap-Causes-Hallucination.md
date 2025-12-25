# Issue Resolution: Deck Data Flow Gap Causes Hallucination

**Date Started**: 2025-12-05
**Status**: ✅ RESOLVED - Phase 1 Complete (Gap 3 Fixed)
**Priority**: CRITICAL (was)
**Impact**: Correct deck data (funding, team, metrics) is lost between agents, causing writer to hallucinate from failed web research

---

## Problem Statement

**Expected Behavior:**
- Deck Analyst extracts accurate data from pitch deck (e.g., $15M round at $65M cap)
- Writer uses deck data as primary source for writing sections
- Web research supplements deck data, doesn't replace it
- Final memo reflects deck accuracy even when web search fails

**Actual Behavior:**
- Deck Analyst correctly extracts data → saves to `0-deck-sections/`
- Perplexity Researcher receives deck data BUT discards it when web search fails
- Researcher writes "search returned different companies" garbage to `1-research/`
- Writer ONLY reads `1-research/`, **NEVER** reads `0-deck-sections/`
- Writer hallucinates completely wrong numbers (e.g., $2M seed at $10M cap)

**Case Study: Reson8 Funding Section**

| Data Point | Deck Says (Correct) | Research Output | Final Memo (Wrong) |
|------------|---------------------|-----------------|-------------------|
| Round Size | $15M Growth Round | "Different companies returned" | $2M seed round |
| Valuation Cap | $65M | No data | $10M |
| Runway | 36 months | No data | 18-24 months |

The deck analyst did its job perfectly. The data just never reached the writer.

---

## Root Cause Analysis

### What DOES Exist (Working Components)

**Deck Analyst creates section drafts** (`src/agents/deck_analyst.py:388-462`):
```python
def create_initial_section_drafts(deck_analysis: Dict, state: Dict, llm: ChatAnthropic):
    """Create draft sections based on deck content and outline definition."""
    # Uses outline to determine which sections to draft
    # Creates drafts for: Business, Market, Team, Funding, Traction, etc.
    # Saves to 0-deck-sections/ via save_deck_analysis_artifacts()
```

**Artifacts save deck sections** (`src/artifacts.py:107-116`):
```python
# Save initial section drafts to 0-deck-sections/
deck_sections_dir = output_dir / "0-deck-sections"
deck_sections_dir.mkdir(exist_ok=True)
for filename, content in section_drafts.items():
    with open(deck_sections_dir / filename, "w") as f:
        f.write(f"<!-- DRAFT FROM DECK ANALYSIS - Cite as [Company Pitch Deck] -->\n\n{content}")
```

**Perplexity Researcher loads deck sections** (`src/agents/perplexity_section_researcher.py:271-320`):
```python
# Load deck section drafts if available (from 0-deck-sections/)
deck_sections_dir = output_dir / "0-deck-sections"
deck_drafts = {}
if deck_sections_dir.exists():
    for deck_file in deck_sections_dir.glob("*.md"):
        section_num_str = deck_file.stem.split("-")[0]
        deck_drafts[section_num_str] = deck_file.read_text()

# Pass to query builder
query = build_section_research_query(
    ...
    deck_draft_content=deck_draft_content,  # ✓ Deck content IS passed
    ...
)
```

---

### What's BROKEN (Two Gaps)

#### Gap 1: Researcher Discards Deck When Perplexity Returns Garbage

**Location:** `src/agents/perplexity_section_researcher.py:348-350`

```python
# Save research file - ALWAYS saves Perplexity response, even if garbage
research_file = research_dir / section_filename
research_file.write_text(research_content)  # ← No fallback to deck!
```

**The Problem:** Even though deck content is passed to Perplexity, when web search returns wrong entities, the researcher just saves whatever Perplexity returns. The deck content that was passed in is DISCARDED.

**What Should Happen:** If Perplexity response is garbage (detected by indicators like "different companies", "unable to find"), the researcher should fallback to saving the deck content instead.

---

#### Gap 2: Writer Has No Fallback to Deck Sections

**Evidence from `src/agents/writer.py`:**

```bash
$ grep -n "0-deck-sections" src/agents/writer.py
# 0 matches found
```

The writer agent's `polish_section_research()` function ONLY loads research files:

```python
def polish_section_research(state: MemoState, company_name: str, output_dir: Path) -> dict:
    research_dir = output_dir / "1-research"  # ← ONLY reads this directory
    # No reference to 0-deck-sections anywhere
    # No fallback to deck data if research is empty/garbage
```

**Conclusion:** Even if Gap 1 were fixed, the writer should STILL have a fallback to `0-deck-sections/` as a safety net.

---

#### Gap 3: Deck Analyst Creates Almost No Section Drafts for 12Ps Outlines

**Location:** `src/agents/deck_analyst.py:406-420`

The concept mapping is hardcoded for standard section names:

```python
deck_field_to_concept = {
    "problem_statement": ["business", "overview", "problem"],
    "solution_description": ["business", "overview", "solution", "product", "technology"],
    "market_size": ["market", "context"],
    "team_members": ["team", "gp", "background", "credibility"],
    "funding_ask": ["funding", "terms", "fee", "economics"],
    # ...
}
```

**The Problem:** The 12Ps outline uses creative section names that DON'T contain these keywords:

| 12Ps Section | Contains Keywords? | Deck Data Available? |
|--------------|-------------------|---------------------|
| Origins | ❌ No match | ✓ Problem, solution |
| Opening | ❌ No match | ✓ Business model |
| Organization | ❌ No match | ✓ **8 team members** |
| Offering | ❌ No match | ✓ Product description |
| Opportunity | ❌ No match | ✓ Market size, TAM |
| Funding & Terms | ✅ "funding", "terms" | ✓ $15M, $65M cap |

**Result:** A 32-page deck with comprehensive data produces only ONE section draft!

**Evidence from Reson8 v0.0.3:**
```
0-deck-analysis.md: 8 team members extracted with full backgrounds
0-deck-analysis.md: Market TAM $5T+ wellness, $60-70B genomic health
0-deck-analysis.md: Traction: 300+ beta users, 1,000+ waitlist
0-deck-analysis.md: Financial projections: $0.25M → $6.1M → $18M

0-deck-sections/: ONLY 09-funding-terms.md created
```

**What Should Happen:** The deck analyst should:
1. Use the outline's `guiding_questions` to map deck fields to sections
2. Or: Generate drafts for ALL sections with available deck data
3. Or: Use LLM to intelligently match deck data to outline sections

---

### Discovery: Web Search Failure Causes Entity Confusion

**Evidence from `1-research/09-funding-terms-research.md` (Reson8 v0.0.3):**

```markdown
# Funding & Terms Research

The search results returned information about different companies named "Reson8":
- Reson8 Group (marketing agency)
- Reson8 Media (podcasting)
- Reson8 SMS (messaging platform)

None of these appear to be the biotech company focused on wave frequency healing.
Unable to find relevant funding information for the target company.
```

**What Should Have Happened:**
The researcher should have:
1. Recognized web search failed
2. Fallen back to deck content
3. Written deck data to `1-research/` file

**What Actually Happened:**
1. Perplexity returned wrong-entity results
2. Researcher wrote "unable to find" to `1-research/`
3. Deck content was discarded
4. Writer received empty/garbage research
5. Writer hallucinated everything

---

### Updated Data Flow Diagram (With Gap Annotations)

The diagram below shows where data flows correctly vs where it breaks down:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DATA FLOW DIAGRAM                             │
└──────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   Pitch Deck  │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐      ┌─────────────────────────────────┐
    │ Deck Analyst  │─────▶│  0-deck-sections/*.md           │
    └──────────────┘      │  (CORRECT - $15M, $65M cap)      │
                          └─────────────────────────────────┘
                                         │
                                         │ (passed to researcher)
                                         ▼
                          ┌─────────────────────────────────┐
                          │  Perplexity Researcher          │
    ┌──────────────┐      │  - Receives deck content ✓      │
    │  Web Search   │─────▶│  - Web search fails ✗          │
    │  (Wrong Entity)│      │  - DISCARDS deck content ✗    │
    └──────────────┘      │  - Writes garbage to research   │
                          └─────────────────────────────────┘
                                         │
                                         ▼
                          ┌─────────────────────────────────┐
                          │  1-research/*.md                │
                          │  (GARBAGE - "different company")│
                          └─────────────────────────────────┘
                                         │
                                         │ (ONLY source for writer)
                                         ▼
                          ┌─────────────────────────────────┐
                          │  Writer Agent                   │
                          │  - ONLY reads 1-research/       │
                          │  - NEVER reads 0-deck-sections/ │
                          │  - No deck context available    │
                          │  - HALLUCINATES FROM NOTHING    │
                          └─────────────────────────────────┘
                                         │
                                         ▼
                          ┌─────────────────────────────────┐
                          │  2-sections/*.md                │
                          │  (HALLUCINATED - $2M, $10M cap) │
                          └─────────────────────────────────┘


                         ╔═══════════════════════════════════╗
                         ║  DATA NEVER FLOWS FROM:           ║
                         ║  0-deck-sections/ → Writer        ║
                         ║                                   ║
                         ║  THIS IS THE ROOT CAUSE           ║
                         ╚═══════════════════════════════════╝
```

---

## Why This Matters

### Impact Assessment

1. **Complete Data Loss**: Accurate pitch deck data is extracted correctly but never reaches the final memo
2. **Fabrication Cascade**: Missing data triggers hallucination, replacing accurate numbers with plausible-sounding fiction
3. **Trust Destruction**: Founders see wrong numbers about their own company
4. **Investment Risk**: Partners make decisions on completely fabricated data
5. **Legal Liability**: Material misrepresentation of funding terms

### Frequency

This happens whenever:
- Company name is shared by other entities (common with startups using short/creative names)
- Company is in stealth mode with no web presence
- Web search API returns irrelevant results
- Perplexity fails to disambiguate correctly

For seed/pre-seed companies with limited online presence, this could affect **30-50% of memos**.

---

## Proposed Solutions

### Three Gaps Summary

| Gap | Location | Problem | Fix Priority |
|-----|----------|---------|--------------|
| **Gap 1** | `perplexity_section_researcher.py:348-350` | Discards deck when web fails | HIGH |
| **Gap 2** | `writer.py` (missing code) | No fallback to deck sections | HIGH |
| **Gap 3** | `deck_analyst.py:406-420` | Hardcoded keywords don't match 12Ps | CRITICAL |

**Gap 3 is the root cause** - if deck analyst created proper section drafts, Gaps 1 and 2 would have data to work with.

---

### Solution A: Fix Deck Analyst - Create Sections for ALL Extracted Data (Gap 3 - CRITICAL)

**Approach:** Don't try to match outline sections. Just create a draft for EVERY deck field that has data. Let downstream agents use them.

**Current broken logic:** Tries to match `deck_field_to_concept` keywords to outline section names (fails for 12Ps).

**Simpler fix - create drafts for ALL fields with data:**
```python
def create_initial_section_drafts(deck_analysis: Dict, state: Dict, llm: ChatAnthropic):
    """Create a section draft for EVERY deck field that has substantial data."""
    drafts = {}

    # Standard field-to-filename mapping (outline-agnostic)
    DECK_FIELD_TO_SECTION = {
        "problem_statement": "deck-problem.md",
        "solution_description": "deck-solution.md",
        "product_description": "deck-product.md",
        "market_size": "deck-market.md",
        "competitive_landscape": "deck-competitive.md",
        "traction_metrics": "deck-traction.md",
        "milestones": "deck-milestones.md",
        "team_members": "deck-team.md",
        "funding_ask": "deck-funding.md",
        "use_of_funds": "deck-use-of-funds.md",
        "go_to_market": "deck-gtm.md",
        "business_model": "deck-business-model.md",
    }

    for field, filename in DECK_FIELD_TO_SECTION.items():
        data = deck_analysis.get(field)

        # Skip empty/placeholder values
        if not data or data == "Not mentioned" or data == "" or data == [] or data == {}:
            continue

        # Generate draft content using LLM
        content = create_section_draft_from_deck(llm, field.replace("_", " ").title(), deck_analysis, [field])
        drafts[filename] = SectionDraft(section_name=field, content=content, word_count=len(content.split()), citations=[])

    return drafts
```

**Expected Result for Reson8:**
```
0-deck-sections/
├── deck-problem.md        ← 970M people suffer from anxiety...
├── deck-solution.md       ← DNA to recovery protocol...
├── deck-business-model.md ← B2B, B2C, IP licensing...
├── deck-market.md         ← $5T+ wellness, $60-70B genomic...
├── deck-traction.md       ← 300+ beta users, 1,000+ waitlist...
├── deck-team.md           ← Marc Benardout, Nicolas Rosen, 6 advisors
├── deck-funding.md        ← $15M at $65M cap, 36 months
├── deck-gtm.md            ← Hybrid B2B + B2C launch...
└── deck-competitive.md    ← First clinically validated...
```

**Impact:** 9 section drafts instead of 1. Writer/researcher can reference ANY of these.

---

### Solution B: Writer Direct Fallback to Deck Sections (Gap 2)

**Approach:** Modify writer agent to check `0-deck-sections/` when `1-research/` is empty or garbage.

**Implementation in `src/agents/writer.py`:**

```python
GARBAGE_INDICATORS = [
    "different compan",
    "unable to find",
    "no relevant",
    "search results returned",
    "not the company we're looking for",
    "disambiguation needed"
]

def load_section_context(output_dir: Path, section_num: int, section_slug: str) -> dict:
    """
    Load section context with fallback chain:
    1. Primary: 1-research/{section}-research.md (web research)
    2. Fallback: 0-deck-sections/{section}.md (deck analysis)
    3. Last resort: Return empty with warning
    """
    research_file = output_dir / "1-research" / f"{section_num:02d}-{section_slug}-research.md"
    deck_file = output_dir / "0-deck-sections" / f"{section_num:02d}-{section_slug}.md"

    context = {"research": "", "deck": "", "source": "none", "warning": ""}

    # Try research first (check for garbage)
    if research_file.exists():
        research_content = research_file.read_text()
        is_garbage = any(ind in research_content.lower() for ind in GARBAGE_INDICATORS)
        if not is_garbage and len(research_content.strip()) > 200:
            context["research"] = research_content
            context["source"] = "research"

    # Try deck as fallback or supplement
    if deck_file.exists():
        context["deck"] = deck_file.read_text()
        if context["source"] == "none":
            context["source"] = "deck_only"
            context["warning"] = "⚠️ Using deck analysis only - web research unavailable"

    if context["source"] == "none":
        context["warning"] = "⚠️ NO DATA AVAILABLE - do not fabricate"

    return context
```

**Pros:** Direct fix at point of failure, writer always has deck access
**Cons:** Requires modifying writer agent

---

### Solution C: Researcher Preserves Deck When Web Fails (Gap 1)

**Approach:** Modify Perplexity researcher to write deck content to `1-research/` when web search fails.

**Implementation in `src/agents/perplexity_section_researcher.py`:**

```python
def write_research_with_fallback(
    output_dir: Path,
    section_num: int,
    section_slug: str,
    perplexity_response: str,
    deck_content: str
) -> None:
    """
    Write research file with deck fallback when web search fails.
    """
    research_file = output_dir / "1-research" / f"{section_num:02d}-{section_slug}-research.md"

    # Check if Perplexity response is garbage
    garbage_indicators = [
        "different compan",
        "unable to find",
        "no relevant",
        "search results returned information about other"
    ]

    is_garbage = any(indicator in perplexity_response.lower() for indicator in garbage_indicators)

    if is_garbage and deck_content:
        # Write deck content as the research
        output = f"""# {section_slug.replace('-', ' ').title()} Research

⚠️ **NOTE**: Web search returned irrelevant results. Using pitch deck analysis as primary source.

## From Pitch Deck (Authoritative)

{deck_content}

## Web Search Status

Web search was attempted but returned results for unrelated companies. The above deck analysis should be treated as the authoritative source for this section.
"""
    elif deck_content:
        # Combine research with deck
        output = f"""# {section_slug.replace('-', ' ').title()} Research

## From Pitch Deck (Authoritative)

{deck_content}

## Web Research (Supplementary)

{perplexity_response}
"""
    else:
        # Just research
        output = perplexity_response

    with open(research_file, 'w') as f:
        f.write(output)
```

**Pros:**
- Fixes data loss at the source
- Writer doesn't need modification
- Deck data flows through existing pipeline

**Cons:**
- Requires researcher modification
- Deck content could be duplicated
- Harder to distinguish deck vs research in downstream agents

---

### Solution D: Unified Context Loader (Architecture Best Practice)

**Approach:** Create a centralized context loader that all agents use, implementing proper fallback chains.

**New file: `src/context_loader.py`:**

```python
"""
Unified Context Loader - Provides consistent access to all available data sources.

This module ensures agents have access to:
1. Deck analysis (authoritative, from pitch deck)
2. Web research (supplementary, from Perplexity/Tavily)
3. Company data file (configuration)
4. Previous sections (for cross-referencing)

Implements proper fallback chains and garbage detection.
"""

from pathlib import Path
from typing import Optional, Dict, Any
import json

GARBAGE_INDICATORS = [
    "different compan",
    "unable to find",
    "no relevant information",
    "search results returned",
    "not the company",
    "unrelated entities",
    "disambiguation needed"
]


def is_garbage_content(content: str) -> bool:
    """Detect if content is garbage (wrong entity, failed search, etc.)"""
    if not content or len(content.strip()) < 100:
        return True

    content_lower = content.lower()
    return any(indicator in content_lower for indicator in GARBAGE_INDICATORS)


def load_section_context(
    output_dir: Path,
    section_num: int,
    section_slug: str,
    company_name: str
) -> Dict[str, Any]:
    """
    Load all available context for a section with proper fallback chain.

    Returns:
        {
            "deck": str,           # Deck analysis content
            "research": str,       # Web research content
            "combined": str,       # Best available context
            "source": str,         # "deck+research", "deck_only", "research_only", "none"
            "warnings": list[str], # Any issues detected
            "is_reliable": bool    # Whether we have reliable data
        }
    """
    result = {
        "deck": "",
        "research": "",
        "combined": "",
        "source": "none",
        "warnings": [],
        "is_reliable": False
    }

    # Load deck section
    deck_file = output_dir / "0-deck-sections" / f"{section_num:02d}-{section_slug}.md"
    if deck_file.exists():
        with open(deck_file) as f:
            deck_content = f.read()
        if not is_garbage_content(deck_content):
            result["deck"] = deck_content

    # Load research section
    research_file = output_dir / "1-research" / f"{section_num:02d}-{section_slug}-research.md"
    if research_file.exists():
        with open(research_file) as f:
            research_content = f.read()
        if not is_garbage_content(research_content):
            result["research"] = research_content

    # Determine source and build combined context
    has_deck = bool(result["deck"])
    has_research = bool(result["research"])

    if has_deck and has_research:
        result["source"] = "deck+research"
        result["combined"] = f"""## Pitch Deck Analysis (Primary Source)

{result["deck"]}

## Web Research (Supplementary)

{result["research"]}"""
        result["is_reliable"] = True

    elif has_deck:
        result["source"] = "deck_only"
        result["combined"] = f"""## Pitch Deck Analysis (Only Source Available)

{result["deck"]}

⚠️ Note: Web research was unavailable or returned irrelevant results."""
        result["is_reliable"] = True
        result["warnings"].append("Web research unavailable - using deck only")

    elif has_research:
        result["source"] = "research_only"
        result["combined"] = f"""## Web Research

{result["research"]}

⚠️ Note: No pitch deck analysis available for this section."""
        result["is_reliable"] = True
        result["warnings"].append("No deck data - using web research only")

    else:
        result["source"] = "none"
        result["combined"] = """⚠️ NO DATA AVAILABLE

Neither pitch deck analysis nor web research provided usable data for this section.

CRITICAL: Do not fabricate information. State "Data not available" for any metrics,
figures, or specific claims that cannot be verified from available sources."""
        result["is_reliable"] = False
        result["warnings"].append("CRITICAL: No reliable data source available")

    return result


def load_full_memo_context(output_dir: Path, company_name: str) -> Dict[str, Any]:
    """
    Load all context for entire memo generation.

    Returns comprehensive context including:
    - All deck sections
    - All research sections
    - Company data file
    - State file
    """
    # Implementation for full memo context loading
    pass
```

**Update `src/agents/writer.py` to use context loader:**

```python
from ..context_loader import load_section_context

def polish_section_research(state: MemoState, company_name: str, output_dir: Path) -> dict:
    """Write sections using unified context loader."""

    for section in SECTION_ORDER:
        section_num = section["number"]
        section_slug = section["slug"]
        section_name = section["name"]

        # Use unified context loader with fallback chain
        context = load_section_context(output_dir, section_num, section_slug, company_name)

        if context["warnings"]:
            for warning in context["warnings"]:
                print(f"  ⚠️  {warning}")

        # Build prompt with available context
        prompt = build_section_prompt(
            section_name=section_name,
            context=context["combined"],
            is_reliable=context["is_reliable"],
            source=context["source"]
        )

        # Generate section...
```

**Pros:**
- Clean architecture with single source of truth
- All agents benefit from consistent fallback behavior
- Easy to extend with additional data sources
- Garbage detection is centralized
- Testable in isolation

**Cons:**
- Requires more significant refactoring
- Need to update multiple agents to use it

---

## Implementation Plan

### Phase 1: Fix Deck Analyst (Solution A) - CRITICAL - Immediate

**Goal:** Make deck analyst create drafts for ALL extracted data, not just outline-matching sections.

1. **Modify `src/agents/deck_analyst.py`** (45 mins)
   - Replace `deck_field_to_concept` matching with simple field-to-filename mapping
   - Create drafts for EVERY field with data (team, market, traction, funding, etc.)
   - Use consistent naming: `deck-{field}.md`

2. **Test on Reson8** (15 mins)
   - Re-run deck analyst
   - Verify 8-10 section drafts created (not just 1)
   - Check team members, traction, market data all preserved

3. **Deploy** (5 mins)
   - Commit with clear description

### Phase 2: Writer Fallback (Solution B) - HIGH - Same Day

**Goal:** Ensure writer can access deck data even if research fails.

1. **Modify `src/agents/writer.py`** (30 mins)
   - Add `load_section_context()` with fallback chain
   - Check `0-deck-sections/` when `1-research/` is garbage
   - Add garbage detection for research files

2. **Test end-to-end** (15 mins)
   - Run full pipeline on Reson8
   - Verify correct funding data ($15M, $65M) in final memo

### Phase 3: Researcher Preservation (Solution C) - This Week

**Goal:** Preserve deck content in research files when web search fails.

1. **Modify `src/agents/perplexity_section_researcher.py`** (30 mins)
   - Add garbage detection for Perplexity responses
   - Write deck content to `1-research/` when web fails
   - Mark source clearly (deck vs web)

### Phase 4: Architecture Cleanup (Solution D) - Next Sprint

**Goal:** Clean, maintainable architecture.

1. **Create `src/context_loader.py`** - Unified context loading
2. **Update consuming agents** - Writer, citation enrichment, fact checker
3. **Add unit tests** - Fallback chains, garbage detection

---

## Validation Criteria

### Test Cases

**Test 1: Entity Confusion (Reson8)**
- Deck says: $15M round at $65M cap
- Web returns: Wrong entity results
- Expected: Final memo shows $15M, $65M cap from deck

**Test 2: Normal Flow (Company with Web Presence)**
- Deck says: $5M Series A
- Web confirms: $5M Series A + additional context
- Expected: Combined deck + web data

**Test 3: No Deck Available**
- No deck provided
- Web research available
- Expected: Research data used, no fabrication

**Test 4: No Data at All**
- No deck, web search fails
- Expected: "Data not available" - no fabrication

### Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Deck data reaching writer | 0% (never) | 100% |
| Fabricated funding terms | High | 0% |
| Correct deck numbers in final memo | 0% | 100% |
| "Data not available" usage (appropriate) | 0% | 15-25% |

---

## Related Issues

- **Preventing Hallucinations in Memo Generation** - Addresses question demand pressure; this doc addresses data flow gap
- **Getting AI to Refocus when Web Research is Empty** - Related but focused on re-prompting, not fallback chain

---

## Files to Modify

| File | Change |
|------|--------|
| `src/agents/writer.py` | Add deck section fallback, garbage detection |
| `src/agents/perplexity_section_researcher.py` | Write deck content when web fails |
| `src/context_loader.py` (new) | Unified context loading with fallbacks |
| `src/agents/citation_enrichment.py` | Update to use context loader |
| `src/agents/fact_checker.py` | Verify against deck AND research |

---

## Status Updates

**2025-12-05 (Initial)**: Root cause identified and documented. Writer agent has no code path to `0-deck-sections/`. When Perplexity researcher writes garbage to `1-research/`, the accurate deck data is lost.

**2025-12-05 (Gap 3 Fixed)**: Implemented Solution A - deck analyst now creates drafts for ALL extracted data.

### Test Results: Reson8 v0.0.4 vs v0.0.3

**Before Fix (v0.0.3):**
```
0-deck-sections/
└── 09-funding-terms.md  ← ONLY 1 file despite 32-page deck!
```

**After Fix (v0.0.4):**
```
0-deck-sections/
├── deck-problem.md
├── deck-solution.md
├── deck-product.md
├── deck-business-model.md
├── deck-market.md
├── deck-competitive.md
├── deck-traction.md
├── deck-team.md
├── deck-funding.md
└── deck-gtm.md           ← 10 comprehensive drafts!
```

**Research Now Includes Deck Data:**

The Perplexity researcher correctly incorporates deck drafts with `[^deck]` citations:

From `01-executive-summary-research.md`:
> The current round is marketed as a **$15M growth raise at a roughly $65M pre-money valuation** via SAFE or Series A equity, with a stated **36-month runway**.[^deck]

From `04-organization-research.md`:
> Marc Benardout (Co-Founder & Co-CEO): Benardout has a long career in creative direction and production for global brands including Pepsi, L'Oréal, General Motors, Google, and Levi's.[^deck]
>
> Nicolas Rosen (Co-Founder & Co-CEO): Rosen is described as a composer and "auditory technologist" with claimed experience in neuroacoustics.[^deck]
>
> Critical organizational gaps remain: No named CTO, Chief Scientific Officer, or Chief Medical Officer.[^deck]

**Key Improvements:**
- ✅ Funding data: $15M, $65M cap (not hallucinated $2M/$10M)
- ✅ All 8 team members with backgrounds preserved
- ✅ Revenue projections: $0.25M → $6.1M → $18M
- ✅ Traction: 300+ beta users, 1,000+ waitlist
- ✅ Critical gaps flagged (no CTO, no CSO, no CMO)

**Gaps 1 & 2 may not need separate fixes** - with comprehensive deck drafts, the researcher now has enough context to write quality research even when web search returns limited results.

---

**Resolution Owner**: Claude Code session
**Reviewers**: TBD
**Target Completion**: ✅ Phase 1 COMPLETE, Phase 2-4 - Evaluate after full test

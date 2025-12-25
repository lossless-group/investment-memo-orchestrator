# Containerizing Internal Comments and Recommendations for Consideration

## The Problem: LLM Process Commentary Leaks Into Final Output

Despite aggressive prompt engineering, LLMs consistently inject meta-commentary into generated content. This includes:

### Types of Leaked Content

| Type | Example | Problem |
|------|---------|---------|
| **Process narration** | "Let me search for more specific information about the company's funding..." | Exposes the generation process |
| **Capability caveats** | "Note: This section does not contain any mentions of investors..." | Undermines document authority |
| **Data gap confessions** | "Data not verified for this entity" | Signals uncertainty inappropriately |
| **User instructions** | "If you have an actual Opening section... please share that content and I'll add citations" | Breaks fourth wall entirely |
| **Hedging statements** | "Unfortunately, I was unable to find specific metrics..." | Makes memo appear incomplete |
| **Task acknowledgments** | "I'll add appropriate hyperlinks once the content is provided" | Reveals document is AI-generated |

### Real Example from Reson8 Memo (v0.0.3)

```markdown
## 01. Executive Summary

Let me search for more specific information about the company's funding, team, and market positioning. [^1]

---

**Note:** This Executive Summary section does not contain any mentions of investors,
government bodies, partners, competitors, universities, or industry organizations
that can be linked. [^1] The section appears to be a placeholder or introductory
statement indicating that additional research is needed. [^1] Once the actual
executive summary content with specific entity mentions is provided, I can add
appropriate hyperlinks to organizations and entities mentioned. [^1]
```

This content is **unacceptable** for external documents sent to:
- LPs and potential investors
- Portfolio company founders
- Co-investors and syndicate partners
- Board members and advisors

---

## Root Cause Analysis

### Why This Happens

1. **Training Artifacts**: LLMs are trained on assistant-style conversations where explaining limitations is helpful
2. **RLHF Patterns**: Models are rewarded for transparency about uncertainty
3. **Instruction Following**: When asked to "add citations" or "enrich links," models explain what they're doing
4. **Failure Gracefully**: Models prefer to explain why they can't do something rather than producing nothing

### Why Prompt Engineering Alone Fails

Even with explicit instructions like:
- "Never include meta-commentary"
- "Do not explain your process"
- "Output only the final content"

Models still leak process commentary because:
1. The behavior is deeply embedded in base training
2. Edge cases trigger fallback behaviors
3. Multi-step pipelines compound the problem
4. Different agents have different prompt contexts

---

## Solution Architecture

### Dual-Track Output System

Instead of fighting LLM nature, **containerize** the commentary:

```
output/{Company}-v0.0.x/
├── 2-sections/                    # Clean, external-ready content
│   ├── 01-executive-summary.md
│   └── ...
├── 2-sections-internal/           # NEW: Process commentary container
│   ├── 01-executive-summary-notes.md
│   └── ...
├── 4-final-draft.md              # Clean assembled memo
└── 4-internal-notes.md           # NEW: Consolidated internal notes
```

### Two Implementation Approaches

#### Approach A: Inline Tagging + Extraction

Agents wrap commentary in special tags during generation:

```markdown
## Executive Summary

Reson8 represents a high-conviction bet on the convergence of genomics...

<!-- INTERNAL
Unable to verify specific funding amounts from public sources.
Recommend requesting cap table from company.
-->

The global longevity market was estimated at $25-30B in 2022...

<!-- INTERNAL
Market sizing varies significantly across sources:
- Grand View Research: $27.1B (2022)
- Allied Market Research: $25.5B (2022)
- MarketsandMarkets: $29.4B (2022)
Consider which source to cite based on methodology alignment.
-->
```

A **Comment Extractor Agent** then:
1. Scans all sections for `<!-- INTERNAL ... -->` blocks
2. Extracts content to `2-sections-internal/{section}-notes.md`
3. Removes tags from clean output
4. Consolidates all notes into `4-internal-notes.md`

#### Approach B: Post-Processing Sanitizer Agent

A **Memo Sanitizer Agent** runs after all enrichment:

1. **Pattern Detection**: Identifies leaked commentary using regex and LLM classification
2. **Content Migration**: Moves flagged content to internal notes folder
3. **Gap Filling**: Optionally replaces removed content with placeholder or removes entirely
4. **Audit Trail**: Logs what was removed and why

---

## Detection Patterns

### Regex-Based Detection

```python
LEAKED_COMMENTARY_PATTERNS = [
    # Process narration
    r"^Let me (search|look|find|check|verify|research)",
    r"^I('ll| will) (add|include|search|look|find)",
    r"^(Searching|Looking|Checking|Verifying) for",

    # Capability caveats
    r"\*\*Note:\*\*.*does not contain",
    r"\*\*Note:\*\*.*unable to",
    r"\*\*Note:\*\*.*could not (find|verify|locate)",

    # Data gap confessions
    r"Data not verified for this entity",
    r"Unable to (find|verify|locate|confirm)",
    r"No (specific|concrete|verified) (data|information|metrics)",

    # User instructions
    r"(please|kindly) (share|provide|send)",
    r"Once (the|you|we) (actual|have|receive)",
    r"If you have.*please",

    # Hedging
    r"^Unfortunately,",
    r"I was unable to",
    r"could not be (verified|confirmed|found)",

    # Task acknowledgments
    r"I('ll| will) add (appropriate|relevant)",
    r"hyperlinks (can|will) be added",
    r"citations (can|will) be added",
]
```

### LLM-Based Classification

For edge cases, use a fast classifier:

```python
SANITIZER_PROMPT = """
Classify whether this text is INTERNAL COMMENTARY or EXTERNAL CONTENT.

INTERNAL COMMENTARY includes:
- Explanations of the generation process
- Acknowledgments of limitations or missing data
- Instructions to the user about what to provide
- Caveats about data verification
- Meta-discussion about the document itself

EXTERNAL CONTENT is:
- Actual analysis and findings
- Market data and metrics
- Company information
- Investment thesis arguments

Text to classify:
{text}

Classification (INTERNAL or EXTERNAL):
"""
```

---

## Agent Specification: Memo Sanitizer

### Position in Pipeline

```
... → cite → toc → validate_citations → fact_check → SANITIZE → validate → scorecard → finalize
```

### Agent Implementation

```python
def memo_sanitizer_agent(state: MemoState) -> dict:
    """
    Sanitizes memo by extracting internal commentary to separate files.

    1. Scans all section files for leaked commentary
    2. Extracts to 2-sections-internal/ folder
    3. Removes from clean output
    4. Consolidates into 4-internal-notes.md
    5. Reassembles 4-final-draft.md without commentary
    """
    company_name = state["company_name"]
    firm = state.get("firm")

    output_dir = get_latest_output_dir(company_name, firm=firm)
    sections_dir = output_dir / "2-sections"
    internal_dir = output_dir / "2-sections-internal"
    internal_dir.mkdir(exist_ok=True)

    total_extracted = 0
    all_internal_notes = []

    for section_file in sorted(sections_dir.glob("*.md")):
        content = section_file.read_text()

        # Extract commentary
        clean_content, extracted_notes = extract_commentary(content)

        if extracted_notes:
            # Save internal notes
            notes_file = internal_dir / f"{section_file.stem}-notes.md"
            notes_file.write_text(extracted_notes)

            # Update clean section
            section_file.write_text(clean_content)

            all_internal_notes.append(f"## {section_file.stem}\n\n{extracted_notes}")
            total_extracted += 1

    # Consolidate all internal notes
    if all_internal_notes:
        consolidated = "# Internal Notes and Recommendations\n\n"
        consolidated += "These notes were extracted from the memo during sanitization.\n"
        consolidated += "They contain process commentary, data gaps, and recommendations.\n\n"
        consolidated += "---\n\n"
        consolidated += "\n\n---\n\n".join(all_internal_notes)

        (output_dir / "4-internal-notes.md").write_text(consolidated)

    # Reassemble final draft
    reassemble_final_draft(output_dir)

    return {
        "messages": [f"Sanitized memo: {total_extracted} sections had internal commentary extracted"]
    }
```

---

## Internal Notes Format

### Per-Section Notes (`2-sections-internal/01-executive-summary-notes.md`)

```markdown
# Internal Notes: Executive Summary

## Data Gaps Identified

- [ ] Specific funding amounts not verified from public sources
- [ ] Team LinkedIn profiles not found
- [ ] Revenue metrics not disclosed

## Recommendations

1. Request cap table from company for accurate funding data
2. Ask founder for team bios and LinkedIn URLs
3. Clarify whether "tens of millions of users" refers to registered or active

## Sources Attempted But Failed

- Crunchbase: No profile found
- PitchBook: Requires subscription
- LinkedIn: Company page not found

## Process Notes

Original content included:
> "Let me search for more specific information about the company's funding..."

This was removed as it exposes the AI generation process.
```

### Consolidated Notes (`4-internal-notes.md`)

```markdown
# Internal Notes and Recommendations

**Memo:** Reson8 Investment Memo v0.0.3
**Generated:** 2025-12-05
**Sanitized:** 2025-12-05

---

## Summary of Gaps

| Section | Data Gaps | Priority |
|---------|-----------|----------|
| Executive Summary | Funding amounts, team details | HIGH |
| Team | LinkedIn profiles, backgrounds | HIGH |
| Traction | Revenue, user metrics | CRITICAL |
| Market Context | TAM source verification | MEDIUM |

---

## Section-by-Section Notes

### 01. Executive Summary
[notes...]

### 02. Origins
[notes...]

...
```

---

## Benefits of Containerization

### For Internal Teams

1. **Audit Trail**: See what data gaps exist without cluttering memo
2. **Follow-up Actions**: Clear list of what to request from company
3. **Source Transparency**: Know which claims need verification
4. **Process Visibility**: Understand how the memo was generated

### For External Documents

1. **Clean Output**: No leaked process commentary
2. **Professional Appearance**: No caveats or hedging
3. **Authority**: Document reads as definitive analysis
4. **Shareability**: Ready for LPs, co-investors, boards

### For Development

1. **Debuggability**: Internal notes reveal where agents struggle
2. **Improvement Signals**: Patterns in gaps inform prompt refinement
3. **Quality Metrics**: Track ratio of clean vs. extracted content

---

## Implementation Phases

### Phase 1: Regex-Based Extraction (Quick Win)

1. Add `memo_sanitizer_agent` to pipeline
2. Implement regex pattern detection
3. Create `2-sections-internal/` folder structure
4. Generate consolidated `4-internal-notes.md`

### Phase 2: Inline Tagging (Upstream Fix)

1. Update all agent prompts to use `<!-- INTERNAL ... -->` tags
2. Add tag extraction to sanitizer
3. Reduce reliance on post-hoc detection

### Phase 3: LLM Classification (Edge Cases)

1. Add classifier for ambiguous content
2. Human-in-the-loop for uncertain classifications
3. Feedback loop to improve patterns

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Clean output rate | 100% of external memos | Grep for leaked patterns |
| Internal notes captured | >90% of useful commentary | Manual review sample |
| False positives | <5% of extracted content | Manual review sample |
| Processing time | <10s per memo | Agent timing |

---

## Related Documentation

- `context-vigilance/Anti-Hallucination-Fact-Checker-Agent.md` - Fact-checking integration
- `context-vigilance/Disambiguation-Management-across-Agents.md` - Entity verification
- `templates/style-guide.md` - Writing standards

---

## Appendix: Common Leaked Phrases to Detect

```
# Process Narration
"Let me search"
"Let me look"
"I'll add"
"I will include"
"Searching for"
"Looking for"

# Capability Caveats
"Note: This section does not"
"Note: Unable to"
"Note: Could not find"
"Data not verified"
"Unable to verify"
"Could not locate"

# User Instructions
"Please share"
"Please provide"
"Once you have"
"If you have"
"When the actual"

# Task Acknowledgments
"hyperlinks can be added"
"citations will be added"
"I'll add appropriate"
"Once the content is provided"

# Hedging
"Unfortunately"
"I was unable"
"could not be verified"
"appears to be a placeholder"
```

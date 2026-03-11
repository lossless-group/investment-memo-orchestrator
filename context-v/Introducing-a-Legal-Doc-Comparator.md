---
title: Introducing a Legal Doc Comparator
lede: An agent that compares deal-specific legal documents (SAFEs, convertible notes, term sheets, incorporation docs) against firm-maintained standard templates, surfacing deviations and flagging common legal risks using a shared reference document.
date_authored_initial_draft: 2026-03-10
date_authored_current_draft: 2026-03-10
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-10
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Agent-Design, Legal-Analysis, Diligence, Document-Comparison, Risk-Flags]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: Two legal documents side by side with highlighted diff regions—one labeled "Standard SAFE" and the other "Deal SAFE"—with red flag icons marking deviations and a checklist of common legal flags between them.
date_created: 2026-03-10
date_modified: 2026-03-10
---

# Introducing a Legal Doc Comparator

**Status**: Draft
**Date**: 2026-03-10
**Last Updated**: 2026-03-10
**Author**: AI Labs Team
**Related**: Dataroom-Analyzer-Agent.md, Containerizing-Risk-Assessments-and-Diligence-Skepticism.md, Anti-Hallucination-Fact-Checker-Agent.md

---

## Executive Summary

Legal document review is one of the most time-consuming and error-prone parts of venture diligence. Partners and associates spend hours comparing a deal's SAFE or term sheet against the firm's preferred standard, looking for unusual clauses, missing protections, or founder-favorable deviations. This is exactly the kind of structured comparison that an AI agent can do reliably — the inputs are well-defined, the outputs are objective, and the failure mode (missing a non-standard clause) is detectable.

This specification introduces:

1. **Legal Doc Comparator Agent** (`legal_doc_comparator.py`): Scans a deal-specific legal document, compares it clause-by-clause against a firm-maintained standard template of the same document type, and produces a structured deviation report.
2. **Standard Legal Templates** (`templates/legal-standards/`): Firm-maintained reference versions of common legal instruments (SAFE, convertible note, term sheet, etc.), with global defaults and firm-specific overrides in `io/{firm}/templates/legal-standards/`.
3. **Common Legal Flags Reference** (`templates/common-legal-flags.md`): A shared reference document enumerating known red flags, unusual clauses, and deviation patterns across all legal instrument types.

---

## Problem Statement

### Manual Comparison Is Slow and Inconsistent

Associates currently compare legal docs by reading them side-by-side with a standard template. This is:
- **Time-consuming**: 1-3 hours per document, longer for complex term sheets
- **Inconsistent**: Different associates flag different things depending on experience
- **Error-prone**: Subtle deviations (changed thresholds, missing clauses, redefined terms) are easy to miss
- **Undocumented**: The comparison reasoning lives in an associate's head, not in the memo artifact trail

### Standard Documents Vary by Firm

Every VC firm has preferences about what "standard" looks like. One firm's standard SAFE might include a pro-rata side letter; another might not. A fund-of-funds evaluating an LP agreement has completely different standards than a direct investor evaluating a SAFE. The comparator must support firm-specific standards with sensible global defaults.

### Legal Flags Are Learnable

Across hundreds of deals, the same problematic patterns recur: MFN clauses with carve-outs, unusual liquidation preferences, non-standard conversion mechanics, broad founder vesting acceleration triggers. These patterns are documentable and should be checked systematically, not left to memory.

---

## Architecture

### Document Flow

```
dataroom / deal folder
       │
       ▼
  legal_doc_comparator
       │
       ├── Loads deal legal doc (PDF/DOCX from dataroom or data/{company}/)
       ├── Identifies document type (SAFE, convertible note, term sheet, etc.)
       ├── Loads matching standard template (PDF, DOCX, or MD)
       │     ├── 1st: io/{firm}/templates/legal-standards/{type}.[pdf|docx|md]
       │     └── 2nd: templates/legal-standards/{type}.[pdf|docx|md] (global fallback)
       ├── Loads common-legal-flags.md
       │     ├── 1st: io/{firm}/templates/common-legal-flags.md
       │     └── 2nd: templates/common-legal-flags.md (global fallback)
       ├── Clause-by-clause comparison
       └── Structured deviation report
              │
              ▼
       output/{Company}-v0.0.x/5-legal-comparison.md + .json
```

### Template Resolution (Firm-First, Global Fallback)

Every agent in the orchestrator follows the same resolution pattern: check for firm-specific templates first, fall back to global templates. The legal doc comparator is no different.

**Resolution order for standard templates:**
1. `io/{firm}/templates/legal-standards/{document-type}.[pdf|docx|md]` — firm-specific standard
2. `templates/legal-standards/{document-type}.[pdf|docx|md]` — global default

**Supported standard template formats** (in preference order per directory):
1. **PDF** (`.pdf`) — most likely format; law firms distribute standards as PDFs
2. **Word** (`.docx`) — common for editable templates from legal counsel
3. **Markdown** (`.md`) — machine-friendly format if the firm maintains structured standards

If multiple formats exist for the same document type in a directory, prefer PDF > DOCX > MD. The agent parses all formats into structured text before comparison (reusing the existing PDF and DOCX parsing infrastructure from the dataroom analyzer).

**Resolution order for common legal flags:**
1. `io/{firm}/templates/common-legal-flags.md` — firm-specific flags (may extend or override global)
2. `templates/common-legal-flags.md` — global default

This means a firm like Hypernova can maintain their own preferred SAFE standard with specific pro-rata provisions, while a firm like Humain can use the global defaults or define their own. Firms can also add firm-specific legal flags (e.g., specific clauses they always reject) without modifying the shared global reference.

---

## Standard Legal Templates

### Directory Structure

```
templates/
├── legal-standards/                     # Global defaults
│   ├── safe-post-money.pdf             # Y Combinator post-money SAFE
│   ├── safe-pre-money.pdf             # Pre-money SAFE (less common)
│   ├── convertible-note.pdf           # Standard convertible note
│   ├── term-sheet-series-seed.pdf     # Seed-stage term sheet
│   ├── term-sheet-series-a.pdf        # Series A term sheet
│   ├── lp-agreement.pdf              # LP agreement (fund commitments)
│   ├── side-letter.pdf               # Common side letter provisions
│   ├── certificate-of-incorporation.pdf # Delaware C-Corp standard
│   └── README.md                      # Index and usage guide
│
├── common-legal-flags.md              # Global legal flags reference
│
io/{firm}/templates/
├── legal-standards/                    # Firm-specific overrides (PDF, DOCX, or MD)
│   ├── safe-post-money.docx          # Firm's preferred SAFE terms (from legal counsel)
│   ├── term-sheet-series-seed.pdf    # Firm's preferred seed terms
│   └── ...
├── common-legal-flags.md             # Firm-specific additional flags
```

**Note on format reality**: Standard legal documents almost always originate as Word docs from law firms or PDFs from accelerators (e.g., Y Combinator's SAFE). The agent must parse these native formats — expecting firms to maintain markdown versions of legal templates is unrealistic. The document type is matched by filename stem (e.g., `safe-post-money`), not extension.

### Standard Template Format

Standard templates will typically be PDFs or Word documents sourced from law firms, accelerators, or industry groups. The agent parses these into structured text before comparison using the same PDF/DOCX extraction infrastructure as the dataroom analyzer. These are reference documents for machine comparison, not binding instruments.

**For markdown standards** (when a firm maintains structured versions), the following format is recommended. For PDF/DOCX standards, the agent extracts clause structure automatically by identifying section headers, numbered provisions, and defined terms.

```markdown
# Standard: Post-Money SAFE

**Document Type**: safe-post-money
**Base Reference**: Y Combinator Post-Money SAFE (2023 template)
**Last Reviewed**: 2026-03-01

---

## Clause Index

### 1. Valuation Cap
- **Standard provision**: Fixed valuation cap stated as dollar amount
- **Expected range**: $4M–$30M for pre-seed/seed
- **Watch for**: No cap (uncapped SAFEs), cap with adjustment mechanisms

### 2. Discount Rate
- **Standard provision**: Fixed discount rate on next priced round
- **Expected range**: 15%–25%
- **Watch for**: No discount, discount compounding, discount floors

### 3. Most Favored Nation (MFN)
- **Standard provision**: MFN clause allowing amendment to match better terms
- **Expected terms**: Applies to subsequent SAFEs before next priced round
- **Watch for**: MFN carve-outs, MFN expiration dates, MFN exclusions for strategic investors

### 4. Pro-Rata Rights
- **Standard provision**: Right to participate in next priced round
- **Expected terms**: Pro-rata based on as-converted ownership
- **Watch for**: No pro-rata, pro-rata with minimum check size, pro-rata sunset clauses

### 5. Conversion Mechanics
- **Standard provision**: Automatic conversion on equity financing above threshold
- **Expected terms**: Converts at lower of cap or discount
- **Watch for**: Conversion triggers changed, shadow series provisions, anti-dilution ratchets added

### 6. Dissolution / Liquidation
- **Standard provision**: Return of purchase amount on dissolution
- **Expected terms**: Pari passu with other SAFEs, before common
- **Watch for**: Preferential liquidation multiples, participation rights on dissolution

### 7. Governance / Information Rights
- **Standard provision**: Minimal or none in standard SAFE
- **Watch for**: Board observer rights, information rights, consent requirements — unusual in SAFEs

### 8. Transfer Restrictions
- **Standard provision**: Non-transferable without company consent
- **Watch for**: Unrestricted transfer rights, carve-outs for affiliates
```

---

## Common Legal Flags Reference

### Purpose

`templates/common-legal-flags.md` is a shared reference document that catalogs known problematic patterns across all legal instrument types. The comparator agent loads this document alongside the standard template and checks the deal document against both.

### Why a Separate Document?

Standard templates describe what "normal" looks like for a specific document type. Common legal flags describe what "problematic" looks like across all document types. A non-standard liquidation preference is flagged by comparison to the standard template. A change-of-control acceleration clause is flagged by the common legal flags reference, regardless of whether the standard template mentions it.

### Structure

```markdown
# Common Legal Flags

**Last Updated**: 2026-03-01
**Maintained By**: AI Labs Team

---

## Severity Levels

- **RED**: Highly unusual, potentially deal-breaking. Requires partner review.
- **YELLOW**: Non-standard but not uncommon. Should be noted in memo.
- **INFO**: Deviation from standard but within acceptable range. Note for completeness.

---

## Flags by Category

### Valuation & Economics

| Flag ID | Flag | Severity | Applies To | Description |
|---------|------|----------|------------|-------------|
| VAL-001 | Uncapped SAFE | RED | SAFE | No valuation cap; unlimited dilution risk to investor |
| VAL-002 | Cap with adjustment mechanism | YELLOW | SAFE | Cap changes based on milestones or time |
| VAL-003 | No discount | YELLOW | SAFE, Note | No discount rate; investor gets no benefit vs next round |
| VAL-004 | Discount above 30% | INFO | SAFE, Note | Higher than typical; may signal distressed deal |
| VAL-005 | Participating preferred | RED | Term Sheet | Double-dip: preference + pro-rata common participation |
| VAL-006 | Liquidation multiple >1x | RED | Term Sheet | Non-standard; >1x preference unusual for early stage |
| VAL-007 | Full ratchet anti-dilution | RED | Term Sheet | Extreme founder dilution on down round |
| VAL-008 | Pay-to-play provisions | YELLOW | Term Sheet | Requires follow-on or lose preference rights |

### Governance & Control

| Flag ID | Flag | Severity | Applies To | Description |
|---------|------|----------|------------|-------------|
| GOV-001 | Board seats disproportionate to ownership | YELLOW | Term Sheet | Investor board seats exceed economic stake |
| GOV-002 | Protective provisions unusually broad | YELLOW | Term Sheet | Veto rights on routine operations |
| GOV-003 | Drag-along below typical threshold | RED | Term Sheet, Incorp | Drag-along at <50% or without common consent |
| GOV-004 | Founder vesting reset | YELLOW | Term Sheet | Existing founder shares re-vested on investment |
| GOV-005 | Single-trigger acceleration | RED | Term Sheet | Acceleration on acquisition alone (no termination required) |
| GOV-006 | No-shop / exclusivity period >60 days | YELLOW | Term Sheet | Extended exclusivity unusual for early stage |

### Conversion & Dilution

| Flag ID | Flag | Severity | Applies To | Description |
|---------|------|----------|------------|-------------|
| CONV-001 | Conversion threshold unusually high | YELLOW | SAFE, Note | Only converts on very large round; delays conversion |
| CONV-002 | Shadow series with extra rights | RED | SAFE | Converted shares get additional rights beyond standard preferred |
| CONV-003 | Anti-dilution on SAFE conversion | RED | SAFE | Anti-dilution mechanism in a SAFE is non-standard |
| CONV-004 | Maturity date with repayment (notes) | YELLOW | Note | Repayment at maturity instead of conversion; misaligned incentives |

### Information & Reporting

| Flag ID | Flag | Severity | Applies To | Description |
|---------|------|----------|------------|-------------|
| INFO-001 | Quarterly reporting obligations | INFO | SAFE, Note | Unusual for pre-priced-round instruments |
| INFO-002 | Audit rights | YELLOW | SAFE | Audit rights in a SAFE are non-standard |
| INFO-003 | No information rights in term sheet | YELLOW | Term Sheet | Standard term sheets include basic information rights |

### Transfer & Liquidity

| Flag ID | Flag | Severity | Applies To | Description |
|---------|------|----------|------------|-------------|
| XFER-001 | ROFR with non-standard pricing | YELLOW | Term Sheet, Incorp | Right of first refusal at non-market price |
| XFER-002 | Lock-up period >180 days | YELLOW | Term Sheet | Extended lock-up post-IPO |
| XFER-003 | Secondary sale restrictions | INFO | Side Letter | Restrictions on secondary market transactions |
```

### Firm-Specific Flags

A firm can maintain `io/{firm}/templates/common-legal-flags.md` with additional flags specific to their investment strategy. The comparator loads both files and merges them, with firm-specific flags taking precedence where Flag IDs overlap.

**Example firm-specific addition:**
```markdown
### Firm-Specific: Hypernova Capital

| Flag ID | Flag | Severity | Applies To | Description |
|---------|------|----------|------------|-------------|
| HN-001 | No pro-rata rights | RED | SAFE, Term Sheet | Hypernova requires pro-rata in all deals |
| HN-002 | Information rights below quarterly | RED | Term Sheet | Hypernova requires at least quarterly updates |
| HN-003 | Board observer not included | YELLOW | Term Sheet | Hypernova prefers board observer seat at seed |
```

---

## Agent: Legal Doc Comparator

### Location

`src/agents/legal_doc_comparator.py`

### Pipeline Position

Runs in the research/analysis phase, after dataroom analysis (which extracts the legal docs), before the writer.

```
dataroom → deck_analyst → research → section_research
                                          │
                                    legal_doc_comparator
                                          │
                              competitive_researcher → ...
```

**Why this position**: The comparator needs dataroom-extracted legal docs as input. Its output feeds into the Risks & Mitigations section and the Funding & Terms section of the memo. It must run before the writer so the writer has deviation data.

### Inputs

1. **Deal legal document**: PDF or DOCX from the dataroom or `data/{company}/` directory
   - The agent identifies the document type from content (not filename)
   - Supports: SAFE, convertible note, term sheet, LP agreement, certificate of incorporation, side letter
2. **Standard template**: Loaded via firm-first resolution (see above)
3. **Common legal flags**: Loaded via firm-first resolution (see above)
4. **Company data context**: Company name, stage, deal size from state (for contextualizing severity)

### Processing Steps

1. **Extract deal document text**: Parse PDF/DOCX into structured text (reuse existing PDF/DOCX parser infrastructure from dataroom analyzer)
2. **Identify document type**: Classify the legal document (SAFE, note, term sheet, etc.) based on content keywords and structure
3. **Load matching standard**: Resolve the correct standard template for the identified document type (PDF, DOCX, or MD — parsed into structured text using the same extraction pipeline)
4. **Load legal flags**: Resolve and merge global + firm-specific legal flags
5. **Clause-by-clause comparison**: For each clause in the standard template (extracted from whichever format the standard is in):
   - Find the corresponding provision in the deal document
   - Classify as: `matches_standard`, `deviates`, `missing`, `additional`
   - For deviations: describe the specific difference
6. **Flag scan**: Check the deal document against all applicable flags from common-legal-flags.md
   - Match by document type applicability
   - Record Flag ID, severity, and specific evidence from the document
7. **Generate deviation report**: Structured output with severity ratings

### Document Type Detection

```python
DOCUMENT_TYPE_SIGNALS = {
    "safe-post-money": ["safe", "simple agreement for future equity", "post-money"],
    "safe-pre-money": ["safe", "simple agreement for future equity", "pre-money"],
    "convertible-note": ["convertible", "promissory note", "maturity date", "interest rate"],
    "term-sheet-series-seed": ["term sheet", "series seed", "seed preferred"],
    "term-sheet-series-a": ["term sheet", "series a", "preferred stock"],
    "lp-agreement": ["limited partner", "capital commitment", "management fee", "carried interest"],
    "side-letter": ["side letter", "supplemental", "in connection with"],
    "certificate-of-incorporation": ["certificate of incorporation", "authorized shares", "delaware"],
}
```

The agent uses keyword frequency and structural analysis to classify. If ambiguous, it includes a confidence score and a note in the output.

### Output Schema

```python
class ClauseComparison(TypedDict):
    clause_name: str              # e.g., "Valuation Cap"
    clause_number: str            # e.g., "1" (from standard template)
    status: str                   # "matches_standard", "deviates", "missing", "additional"
    standard_provision: str       # What the standard says
    deal_provision: str           # What the deal doc says (empty if missing)
    deviation_description: str    # Human-readable description of the difference
    severity: str                 # "RED", "YELLOW", "INFO", "OK"
    relevant_flags: list[str]     # Flag IDs triggered (e.g., ["VAL-001", "GOV-003"])

class LegalFlag(TypedDict):
    flag_id: str                  # e.g., "VAL-005"
    flag_name: str                # e.g., "Participating preferred"
    severity: str                 # "RED", "YELLOW", "INFO"
    evidence: str                 # Specific text or provision from deal doc
    applies_to: str               # Document type
    firm_specific: bool           # Whether this flag came from firm-specific file

class LegalDocComparison(TypedDict):
    document_type: str            # Detected document type
    document_type_confidence: str # "high", "medium", "low"
    standard_template_used: str   # Path to standard template loaded
    flags_reference_used: str     # Path to flags reference loaded
    firm: str                     # Firm name (for resolution context)
    clause_comparisons: list[ClauseComparison]
    flags_triggered: list[LegalFlag]
    summary: LegalComparisonSummary

class LegalComparisonSummary(TypedDict):
    total_clauses_compared: int
    matches_standard: int
    deviations: int
    missing_clauses: int
    additional_clauses: int
    red_flags: int
    yellow_flags: int
    info_flags: int
    overall_assessment: str       # 2-3 sentence summary
    recommendation: str           # "standard", "review_recommended", "partner_review_required"
```

### State Updates

```python
return {
    "legal_comparison": legal_doc_comparison,
    "messages": [
        f"Legal doc comparison ({doc_type}): {deviations} deviations, {red} RED flags, {yellow} YELLOW flags",
        f"Recommendation: {recommendation}"
    ]
}
```

---

## Artifact Output

Saves to `output/{Company}-v0.0.x/5-legal-comparison.md` and `.json`:

```markdown
# Legal Document Comparison

**Document Type**: Post-Money SAFE
**Standard Used**: io/hypernova/templates/legal-standards/safe-post-money.md
**Flags Reference**: templates/common-legal-flags.md (global) + io/hypernova/templates/common-legal-flags.md (firm)
**Overall Assessment**: Review Recommended — 2 deviations, 1 RED flag

---

## Summary

The deal SAFE is largely standard (Y Combinator post-money template) with two notable deviations:
an MFN clause with a strategic investor carve-out and the absence of pro-rata rights.
One RED flag triggered: Hypernova requires pro-rata rights in all deals (HN-001).

## Clause Comparison

| # | Clause | Status | Severity | Details |
|---|--------|--------|----------|---------|
| 1 | Valuation Cap | Matches Standard | OK | $12M cap, within expected range |
| 2 | Discount Rate | Matches Standard | OK | 20% discount |
| 3 | MFN Clause | **Deviates** | YELLOW | MFN excludes "strategic investors" — standard has no exclusions |
| 4 | Pro-Rata Rights | **Missing** | RED | No pro-rata provision; standard includes pro-rata [HN-001] |
| 5 | Conversion Mechanics | Matches Standard | OK | Standard conversion on qualified financing |
| 6 | Dissolution | Matches Standard | OK | Return of purchase amount, pari passu |
| 7 | Transfer Restrictions | Matches Standard | OK | Non-transferable without consent |

## Flags Triggered

| Flag ID | Flag | Severity | Evidence |
|---------|------|----------|----------|
| HN-001 | No pro-rata rights | RED | Pro-rata section absent from document |
| VAL-003 | MFN with carve-outs | YELLOW | Section 3(b): "excluding investors designated as strategic by the Company" |

## Additional Clauses (Not in Standard)

| Clause | Assessment |
|--------|------------|
| Information rights (quarterly financials) | INFO — unusual for SAFE but not problematic |

## Deviations Detail

### MFN Clause — Strategic Investor Exclusion
**Standard**: MFN applies to all subsequent SAFEs before next priced round, no exclusions.
**Deal**: MFN applies "excluding investors designated as strategic by the Company at its sole discretion."
**Risk**: Company could issue SAFEs on better terms to "strategic" investors without triggering MFN for this investor. The "sole discretion" language gives the company broad latitude.

### Pro-Rata Rights — Missing
**Standard**: Investor has right to participate pro-rata in next equity financing.
**Deal**: No pro-rata provision included.
**Risk**: Investor has no guaranteed allocation in follow-on round. Combined with MFN carve-out, this reduces investor protections significantly.
```

---

## How the Writer Uses This Data

The legal comparison data feeds into two memo sections:

### Funding & Terms Section
The writer receives `state["legal_comparison"]` and includes:
- Document type and key terms (cap, discount, conversion mechanics)
- Notable deviations from standard, with severity context
- Additional clauses not in the standard template

### Risks & Mitigations Section
RED and YELLOW flags surface as risk items:
- RED flags become explicit risk entries with mitigation recommendations
- YELLOW flags are noted as "terms to monitor" or "negotiate before close"

### Writer Prompt Addition

```
LEGAL DOCUMENT COMPARISON (pre-analyzed):

Document Type: {document_type}
Overall Assessment: {recommendation}

Key Deviations:
{deviation_summaries}

Flags Triggered:
{flags_with_severity}

IMPORTANT: When writing Funding & Terms, include the document structure
and any notable deviations. When writing Risks & Mitigations, include
RED flags as explicit risk items. Do not editorialize beyond the
deviation report — state the facts and their implications.
```

---

## Multiple Documents Per Deal

A single deal may include multiple legal documents (SAFE + side letter, term sheet + certificate of incorporation). The agent handles this by:

1. Iterating over all legal documents found in the dataroom or data directory
2. Running a separate comparison for each document
3. Producing a combined report with per-document sections
4. Cross-referencing: if a side letter modifies a provision in the main SAFE, note the interaction

The output file remains singular (`5-legal-comparison.md`) but contains sections per document.

---

## Company JSON Config

```json
{
  "type": "direct",
  "mode": "consider",
  "legal_docs": [
    "data/CompanyName/safe-agreement.pdf",
    "data/CompanyName/side-letter.pdf"
  ],
  "firm": "hypernova"
}
```

**Field descriptions:**
- `legal_docs` (optional): Explicit paths to legal documents. If omitted, the agent scans the dataroom for legal documents automatically.
- `firm`: Already used for template resolution; the legal comparator uses this to find firm-specific standards and flags.

If no legal documents are found (no `legal_docs` field, no legal docs in dataroom), the agent skips gracefully and logs a message.

---

## State Schema Additions

```python
# In src/state.py - add to MemoState TypedDict

class MemoState(TypedDict):
    # ... existing fields ...
    legal_comparison: Optional[LegalDocComparison]  # Comparison results
```

---

## Interaction with Existing Agents

### Dataroom Analyzer (`dataroom_analyzer.py`)
The dataroom analyzer already extracts and categorizes documents. Legal documents identified during dataroom analysis should be tagged and their paths passed to the legal doc comparator. No changes to the dataroom analyzer are required — just consume its output.

### Risk Containerization (`risk_assessment.py`)
The legal comparison feeds directly into risk containerization. RED flags become first-class risk items with structured severity, evidence, and mitigation recommendations. This is a natural fit with the existing risk assessment framework.

### Fact Checker (`fact_checker.py`)
The fact checker can verify that legal terms stated in the memo (cap amount, discount rate, conversion triggers) match the actual deal document. The legal comparison provides the authoritative source for these facts.

### Citation Enrichment
Legal comparison findings reference specific document provisions (e.g., "Section 3(b)"). These are internal document references, not web citations. The citation system should preserve these as-is without attempting to enrich them with web sources.

---

## Implementation Priority

1. **Standard templates for SAFE (post-money)**: Most common instrument at pre-seed/seed; highest immediate value
2. **Common legal flags reference**: Core reference document used by all comparisons
3. **Legal doc comparator agent**: Core comparison logic
4. **Term sheet standard template**: Second most common instrument
5. **Firm-specific template overrides**: Enable Hypernova/Humain customization
6. **Convertible note and LP agreement templates**: Broader coverage
7. **Multi-document cross-referencing**: Side letters modifying main instruments

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Deviation detection accuracy | >90% of non-standard clauses identified |
| False positive rate (standard clause flagged as deviation) | <10% |
| RED flag recall (known problematic clauses caught) | >95% |
| Time to legal summary in memo | <60 seconds (vs 1-3 hours manual) |
| Firm-specific template loaded when available | 100% |
| Graceful skip when no legal docs present | 100% |

---

## Open Questions

1. **Should the comparator suggest negotiation language?** When a RED flag is found, the agent could suggest specific counter-language based on the standard template. This adds value but risks overstepping into legal advice territory. Recommendation: defer to v2; for now, flag and describe, don't prescribe.

2. **How to handle non-English legal documents?** Some international deals may have legal docs in other languages. The agent should detect language and skip with a message rather than produce unreliable analysis.

3. **Should prior deal comparisons inform future runs?** If Hypernova has seen 50 SAFEs, the comparator could surface "this deviation appeared in 3 of your last 10 deals" for context. This requires cross-run data persistence, which is a broader system concern (see competitive landscape spec's notes on cross-run data continuity).

4. **Interaction with the Scorecard system**: Should legal flag counts contribute to the overall memo quality score? A memo with unaddressed RED flags could receive a score penalty. This ties into the Model-Scorecard-Agent-and-Template-System.md spec.

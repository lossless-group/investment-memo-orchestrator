---
title: "Ideal Orchestration Agent Workflow"
lede: "Canonical reference for the correct ordering of agents in the memo generation pipeline, with emphasis on final draft assembly, citation renumbering, and TOC generation."
date_authored_initial_draft: 2026-03-23
date_authored_current_draft: 2026-03-23
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-03-23
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Reminder
date_created: 2026-03-23
date_modified: 2026-03-23
tags: [Orchestration, Workflow, Pipeline, Citations, TOC, Assembly, Architecture]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.6"
---

# Ideal Orchestration Agent Workflow

## Why This Document Exists

This workflow keeps getting broken during iterative troubleshooting. Claude's context window doesn't retain the ideal sequence across conversations, so we fix one thing and create a problem we already solved. This document is the single source of truth for **what runs when and why**.

## Core Architectural Principles

### 1. The Orchestrator Owns the Sequence

The `workflow.py` graph is the **single source of truth** for agent execution order. Individual agents should not embed knowledge of other agents' responsibilities. If the TOC needs to run after assembly, the orchestrator calls it after assembly — the assembly agent should not call the TOC agent internally.

### 2. Agents Are Idempotent and Self-Contained

Each agent should:
- Check if its work is needed (skip gracefully if not)
- Validate its own output before returning
- Read from and write to the artifact trail (files on disk), not rely on in-memory state for content

### 3. Section-Local Citations, Globally Renumbered at Assembly

**Within each section file** (`2-sections/01-executive-summary.md`, etc.), citations use local 1-n numbering starting at `[^1]`. This is intentional:
- Users can edit or rewrite a single section independently
- The `improve-section.py` tool works on individual sections with their own citation numbering
- Citation enrichment agents process sections independently

**At final draft assembly**, a renumbering step reassigns all citations globally so there are no conflicts (section 1 uses `[^1]-[^5]`, section 2 uses `[^6]-[^12]`, etc.), and consolidates all citation definitions into ONE block at the end of the document.

### 4. Final Draft Assembly Is a Multi-Step Process

Assembly is NOT a single monolithic operation. It is a sequence of steps orchestrated by the workflow:

1. **Renumber citations** globally across all sections
2. **Concatenate** header + sections + citation block into the final draft file
3. **Generate TOC** from the assembled final draft (reads headers, inserts TOC)

The TOC must run LAST because it reads the final document structure. If any agent modifies content after the TOC is inserted, the TOC becomes stale or gets destroyed.

### 5. No Agent Should Run Before Its Input Exists

This is the recurring bug pattern: an agent is placed in the workflow sequence before the artifact it reads has been created. The TOC agent reads the final draft file — it MUST run after the final draft file is created by assembly.

---

## The Pipeline: Complete Agent Sequence

### Phase 1: Data Gathering

These agents collect raw information. Each skips gracefully if its input is not provided.

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 1 | `dataroom` | `data/{Company}/` directory | `0-dataroom-analysis.json` + `.md` | Richest source. Skips if no dataroom path. |
| 2 | `deck_analyst` | Pitch deck PDF | `0-deck-analysis.json` + `.md` | Skips if no deck. |
| 3 | `research` | Company name, URL, description | `1-research/` files | Web search via Tavily/Perplexity. |
| 4 | `section_research` | Outline + research | `1-research/` section-specific files | Perplexity section-by-section research with citations. |
| 5 | `competitive_researcher` | Research data | Candidate competitor list | Discovers potential competitors. |
| 6 | `competitive_evaluator` | Candidate list | Evaluated competitor landscape | Classifies and scores competitors. |

### Phase 2: Citation Enrichment on Research (BEFORE Writer)

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 7 | `cite` | `1-research/` files | Enriched `1-research/` files | Adds citations via Perplexity Sonar Pro. |
| 8 | `cleanup_research` (GATE 1) | `1-research/` files | Cleaned `1-research/` files | Validates URLs, removes hallucinated citations. Writer receives ONLY clean data. |

### Phase 3: Writing

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 9 | `draft` (writer) | Clean research + outline | `2-sections/*.md` (10 files) | Writes ONE SECTION AT A TIME. Each section has local 1-n citation numbering. |

### Phase 4: Section Enrichment

These agents modify individual section files in `2-sections/`. Order matters where noted.

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 10 | `inject_deck_images` | Deck screenshots + sections | Updated `2-sections/` files | Inserts deck image references. |
| 11 | `enrich_trademark` | Company data + sections | `header.md` | Creates header with company logo. |
| 12 | `enrich_socials` | `04-team.md` | Updated `04-team.md` | Adds LinkedIn profile links. |
| 13 | `enrich_links` | All section files | Updated section files | Adds hyperlinks to orgs, investors, etc. |
| 14 | `generate_tables` | Section files | Updated section files | Converts structured data to markdown tables. |
| 15 | `generate_diagrams` | Section files | Updated section files | Generates TAM/SAM/SOM and other diagrams. |
| 16 | `enrich_visualizations` | Section files | Updated section files | (Currently disabled, being refactored.) |

### Phase 5: Content Revision

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 17 | `revise_summaries` | All section files | Updated bookend sections | Revises Executive Summary and Recommendation based on full draft content. |

### Phase 6: Pre-Assembly Cleanup

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 18 | `cleanup_sections` (GATE 2) | `2-sections/` files | Cleaned `2-sections/` files | Validates URLs, removes hallucinated citations from sections. |

### Phase 7: Final Draft Assembly

**CRITICAL SEQUENCE** — this is where ordering bugs keep recurring.

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 19 | `assemble_citations` | `2-sections/` + `header.md` + `1-research/` | **Final draft file** (`7-{Deal}-{Version}.md`) | Renumbers citations globally, concatenates all sections, appends consolidated citation block. **This creates the final draft file.** |
| 20 | `toc` | Final draft file | Updated final draft file | Reads assembled draft, extracts headers, generates TOC, inserts after Executive Summary. **MUST run after assembly creates the file.** |

### Phase 8: Validation & Fact-Check Pipeline

The fact-check pipeline is a three-step process: **extract → verify → correct**.

This is where the system defends against hallucinated metrics, unsourced claims, and inaccurate data. The mechanical extractor identifies claims, the LLM verifier checks them against real sources, and the LLM corrector surgically fixes the section files.

| Order | Agent | Input | Output | Uses LLM? | Notes |
|-------|-------|-------|--------|-----------|-------|
| 21 | `validate_citations` | Final draft | `3-validation.json` | No | Checks citation format, dates, URL accessibility, duplicates. |
| 22 | `fact_check` | `2-sections/` + research | `4-fact-check.json` + `.md` | No (regex) | **EXTRACT**: Identifies claims (metrics, financials, dates, names) and checks if they have citations or appear in research data. Flags unsourced/suspicious claims. |
| 23 | `fact_verify` | `4-fact-check.json` | `4-fact-check-verified.json` + `.md` | **Yes** (Perplexity Sonar Pro) | **VERIFY**: Sends suspicious/critical claims to Perplexity for independent real-time verification. Each claim gets: confirmed / contradicted / corrected / unverifiable. Finds better sources. |
| 24 | `fact_correct` | `4-fact-check-verified.json` + `2-sections/` | Updated sections + `4-corrections-log.json` + `.md` | **Yes** (Claude) | **CORRECT**: Surgically updates specific sentences in section files with verified corrections. Adds new citations. Does NOT rewrite sections wholesale. |
| 25 | `validate` | Final draft | Validation score (0-10) | Yes | Quality scoring. |

**Traceability chain** (logged in `4-corrections-log.json`):
```
claim found → checked for accuracy → found better source → updated claim → added citation → logged change
```

**Artifact trail for fact-checking:**
- `4-fact-check.json` — Raw claim extraction with sourcing status (mechanical)
- `4-fact-check.md` — Human-readable version
- `4-fact-check-verified.json` — Claims enriched with LLM verification results
- `4-fact-check-verified.md` — Human-readable verification report
- `4-corrections-log.json` — Full traceability: old claim → finding → new claim → new citation
- `4-corrections-log.md` — Human-readable corrections report

### Phase 9: Scorecard & Finalization

| Order | Agent | Input | Output | Notes |
|-------|-------|-------|--------|-------|
| 26 | `scorecard` | Final draft + research | `5-scorecard/12Ps-scorecard.md` | 12Ps evaluation. |
| 27 | `integrate_scorecard` | Scorecard + section 8 | Updated final draft | Replaces section 8 with scorecard, **reassembles final draft** (calls `cli/assemble_draft.py` which includes TOC). |
| 28 | `finalize` OR `human_review` | Final draft | State snapshot | Score >= 8 finalizes; < 8 routes to human review. |

---

## Known Bug Patterns (Don't Repeat These)

### Bug: TOC Agent Runs Before Final Draft Exists
- **Symptom**: "TOC generation skipped - no final draft found"
- **Cause**: `toc` was placed in the workflow BEFORE `assemble_citations`, which creates the final draft
- **Fix**: Move `toc` to run AFTER `assemble_citations`
- **Lesson**: Always verify that an agent's input artifact exists at its point in the sequence

### Bug: integrate_scorecard Destroys TOC
- **Symptom**: TOC is present after `toc` agent runs, but missing in the final output
- **Cause**: `integrate_scorecard` reassembles the final draft, potentially without TOC
- **Fix**: `integrate_scorecard` uses `cli/assemble_draft.py` which includes TOC generation
- **Lesson**: Any agent that rewrites the final draft must preserve or regenerate the TOC

### Bug: Citation Number Conflicts in Final Draft
- **Symptom**: Multiple sections reference `[^1]` pointing to different sources
- **Cause**: Sections use local numbering; assembly didn't renumber globally
- **Fix**: `assemble_citations` includes a global renumbering step before concatenation
- **Lesson**: Section-local numbering is correct; global renumbering is an assembly responsibility

---

## Edge Ordering in workflow.py

The edges in `build_workflow()` MUST follow this sequence. When modifying, verify against this document:

```
dataroom → deck_analyst → research → section_research →
competitive_researcher → competitive_evaluator →
cite → cleanup_research (GATE 1) →
draft →
inject_deck_images → enrich_trademark → enrich_socials → enrich_links →
generate_tables → generate_diagrams → enrich_visualizations →
revise_summaries →
cleanup_sections (GATE 2) →
assemble_citations → toc →
validate_citations → fact_check → fact_verify → fact_correct →
validate →
scorecard → integrate_scorecard →
[conditional: finalize | human_review] → END
```

**Golden rules**:
- `toc` runs after `assemble_citations`, never before.
- `fact_check → fact_verify → fact_correct` always run as a chain. The verifier needs the extractor's output; the corrector needs the verifier's output.

---

## Reassembly After Manual Edits

When a user edits section files manually or via `improve-section.py`, the final draft must be reassembled. The canonical tool for this is:

```bash
python -m cli.assemble_draft "Company"
```

This CLI tool performs the same sequence as Phase 7 of the pipeline:
1. Renumber citations globally
2. Concatenate sections
3. Generate/update TOC
4. Write final draft

This ensures consistency whether assembly happens during the pipeline or after manual edits.

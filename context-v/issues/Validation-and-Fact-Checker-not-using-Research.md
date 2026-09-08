---
title: "Validation and Fact-Checker Not Using Research"
lede: "Both quality gates score the memo without reading the research the writer was constrained to. The fact-checker looks up claims in a 16.5 KB legacy blob while the codified corpus sits unread in 1-research/; the validator sees only the memo and a style guide, so it cannot tell a dataroom-grounded citation from a missing one. The scores they emit measure citation mechanics, not truth — and the validator's headline finding on ProfileHealth v0.0.3 is false of the memo that actually shipped."
date_authored_initial_draft: 2026-09-04
date_authored_current_draft: 2026-09-04
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-09-04
date_modified: 2026-09-04
tags: [Fact-Checker, Validator, Codified-Sources, Research-Grounding, Quality-Gates, Anti-Hallucination, Issue-Resolution]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: a2d586df-2793-4ea1-a7a8-2182913719e7
hex_code: oyvk7a
status: Open
severity: High
---

# Validation and Fact-Checker Not Using Research

## Status

**Open.** Diagnosed against ProfileHealth v0.0.3 (`io/humain/deals/ProfileHealth/outputs/ProfileHealth-v0.0.3/`, run 2026-08-28). No code changed yet. Every claim below was verified against that run's artifacts and against `src/` at commit time.

## The complaint, in the operator's words

> "I don't get why there is so much argument in fact-check. The idea in constraining the writer agent to research, and constraining the research agent to a set of sources is that there should no longer be so much doubt in sourcing?"

That expectation is correct, and the pipeline honours it right up until the quality gates. The writer *is* constrained: `aggregate_sources` halts the run for analyst curation, the curated `inputs/Sources.md` is promoted to `mode: codified`, and `codified_section_researcher` writes only approved-source research into `1-research/<NN-slug>-research.md` (`src/agents/codified_section_researcher.py:89`, `:358`). The writer then drafts from those files.

**Neither gate reads them.** The constraint is enforced on the way in and abandoned on the way out.

## Defect 1 — the fact-checker validates against the wrong corpus

`fact_checker_agent` pulls its evidence base from state:

```python
# src/agents/fact_checker.py:325
research_data = state.get("research", {})
```

and searches it as one flattened string:

```python
# src/agents/fact_checker.py:152
research_str = json.dumps(research_data).lower() if research_data else ""
```

`state["research"]` is the **legacy generic researcher's** output — the pre-codified blob from `research_enhanced.py`. In ProfileHealth v0.0.3 it totals **16,572 characters** across 14 keys. The codified per-section research the writer actually consumed totals **62,790 characters across 10 files** in `1-research/`. The fact-checker never opens that directory. Nor does it read `3-source-catalog/`, nor `inputs/Sources.md`.

So the agent charged with catching hallucination is looking for the writer's claims in a corpus the writer did not use, and roughly a quarter the size of the one it did.

## Defect 2 — "sourced" means "has a footnote in this sentence"

The entire verification test is one regex:

```python
# src/agents/fact_checker.py:129
has_citation = bool(re.search(r'\[\^\d+\]', claim_text))
```

A claim is `verified` if a footnote marker appears in the same sentence, and unsourced otherwise — regardless of whether it is true, regardless of whether the paragraph around it is cited, regardless of whether it came from a curated dataroom document. The fallback path (`:155`, `:168`) is a bare substring match of digits and key terms against `research_str`, so `$5.9M` in the memo does not match `5,900,000` in research.

### What that produced on ProfileHealth v0.0.3

`4-fact-check.json` — 47 claims, headline score **30%**:

| Count | Verdict reason |
|---|---|
| 14 | has inline citation → **verified** |
| 18 | **"appears in research but lacks citation"** |
| 15 | "no citation and no evidence in research" |

On **18 claims the checker located the supporting evidence and still marked them unsourced**, purely on footnote placement. The remaining 15 were looked up in the 16.5 KB blob rather than the 62.8 KB codified corpus.

**32 of 47 claims are penalised for citation mechanics or a wrong-corpus lookup, not for being wrong.** The 30% is a citation-density metric wearing a fact-check label, and it is the number that drives `sections_to_rewrite`.

For contrast, the gate that *does* test truth — `attribution_audit`, which asks whether a quantitative claim is even about this company — examined **108 claims against 40+ named competitors and flagged zero**. That is the signal. The 30% is noise sitting next to it in the same artifact directory.

## Defect 3 — the validator sees the memo and nothing else

`validator_agent` loads exactly two things:

```python
# src/agents/validator.py:135
memo_content = final_draft_path.read_text()
# src/agents/validator.py:141
style_guide = load_style_guide()
```

and the prompt it builds (`:157` `MEMO TO VALIDATE:`, `:172`) contains only those. No research. No source catalog. No `Sources.md`. No awareness that the run is in codified mode or that the deal is dataroom-grounded.

It is then asked to "Score each category (structure, metrics, risks, tone, **sources**)" with no visibility into what the sources are. It has no way to distinguish a claim grounded in an executed SAFE PDF from one the model invented, so it falls back to judging citations by how they *look*.

### The consequence, verbatim from `3-validation.md`

> **CRITICAL: Source attribution is completely broken. All citations are footnotes to local file paths (e.g., 'file:///Users/mpstaton/code/...') which are inaccessible to readers.**

This is false of the shipped memo. `7-ProfileHealth-v0.0.3.md` contains **zero** `file:///` strings. Nor do any of the ten files in `2-sections/`. The only place they appear is `1-research/*.md` — five files — where a local path is the **correct** citation, because it points at a document in the dataroom.

The validator scored the memo **6.5/10, "NEEDS REVISION"**, on a headline finding that is wrong twice over: wrong that the memo contains those citations, and wrong that a dataroom path is a defect in a codified run.

## Defect 4 — the validator scores a draft that is not the shipped artifact

From the graph in `src/workflow.py:544-557`:

```
assemble_citations → fix_citation_spacing → validate_citations → fact_check
  → attribution_audit → fact_verify → fact_correct → source_catalog
  → validate → scorecard → integrate_scorecard → scorecard_nav → toc → one_pager
```

`fact_correct` writes its corrections to the **section files**. The final draft is not rebuilt until `integrate_scorecard`, three nodes later. So `validate` reads the draft left by `assemble_citations` — before scorecard integration, before the navigator table, before the TOC, and without the fact corrections that were just applied to sections.

Confirmed by mtime in v0.0.3: `4-corrections-log.md` 11:11 → `3-validation.md` 11:12 → `5-scorecard/` 11:14 → `7-ProfileHealth-v0.0.3.md` **11:14**. The validation report is a critique of an intermediate artifact that no longer exists on disk, filed next to the memo as though it described it.

This also explains the `file:///` phantom: per the `manage-memo-citations` contract, the assembler treats `1-research/` as a fallback source for citation definitions. At `validate` time those research-derived definitions were still in the assembled draft; by 11:14 the reassembly had replaced them with the resolved external citations now visible at lines 775-785 of the memo.

## Why this matters more in codified mode than it did before

Codified mode was introduced so the analyst's curated source list is the *only* thing the researcher may use. It changes what a good citation looks like: a dataroom document, a local path, an instrument on file. Both gates were written against the older assumption that every citation should be a public URL from a recognisable market-research brand — which is why the validator's suggestions read like "cite Gartner, Grand View Research" for a company whose numbers live in an executed SAFE and a cap table.

The gates are not just uninformed here; they are **actively pushing the memo away from its grounded sources** and back toward the broad-search behaviour the curation halt exists to prevent.

## Proposed resolution

1. **Point the fact-checker at the corpus the writer used.** Replace `state.get("research", {})` with a loader that reads `1-research/*.md` plus `3-source-catalog/*.md`, falling back to `state["research"]` only when the codified files are absent. Keep the on-disk files authoritative — state is a summary, not the corpus.
2. **Widen the sourcing unit from sentence to paragraph.** A claim should count as sourced when the paragraph or list-item containing it carries a citation, or when its numbers resolve to a codified source. Sentence-level footnote presence is a formatting check and belongs in `citation_validator`, not here.
3. **Normalise numbers before matching.** `$5.9M`, `5.9 million`, and `5,900,000` must compare equal; the current `str.replace(',', '')` substring test fails all three against each other.
4. **Give the validator its grounding.** Pass the source catalog and the codified-mode flag into the prompt, and teach it that a dataroom-relative path is a valid citation for a dataroom-grounded claim. A validator that cannot see the sources should not be scoring a `sources` category.
5. **Move `validate` after the last content mutation.** It belongs after `toc`, or the final draft must be reassembled before it runs. Scoring a draft three nodes stale produces findings no one can act on because the text they quote is already gone.
6. **Separate the two numbers in the artifacts.** "Citation coverage %" and "claims verified against source %" are different measurements. Emitting one number labelled *fact check* trains the analyst to ignore it, which is worse than emitting nothing.

## Verification for the fix

The same run is the regression case. After the change, on ProfileHealth v0.0.3 without regenerating content:

- The 18 "appears in research but lacks citation" claims should resolve to verified or to a distinct citation-coverage finding — not to `unsourced`.
- The 15 "no evidence in research" claims should be re-tested against `1-research/` and only survive as findings if genuinely absent from the codified corpus.
- `3-validation.md` must not assert `file:///` citations in a memo that has none.
- The validation report's quoted examples must all be findable in the shipped `7-*.md`.

## Related

- `context-v/issue-resolution/Preventing-Hallucinations-in-Memo-Generation.md` — the Tier 1/2/3 defence model this agent implements Tier 2 of
- `context-v/issue-resolution/Faked-Sources-from-Perplexity.md` — the failure codified mode was built to close
- `../../../../context-v/explorations/Separating-Retrieval-from-Generation-in-Agent-Pipelines.md` (in the **parent** `memopop-ai` repo, not this one — `CLAUDE.md` cites it as a local path, which is wrong) — the direction this fix should move toward, per `CLAUDE.md` §"Architectural direction"
- `agent-skills/manage-memo-citations` — the assembler's research-files-as-fallback rule that produced the phantom `file:///` finding
- `AGENTS.md` §5, §6 — markers not prose; the same run also shipped a `link_enrichment` refusal into Section 4

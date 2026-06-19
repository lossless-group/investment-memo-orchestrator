---
title: "Research Agent Concatenates Multiple Sources Under One Citation ID — And No Validator Catches It"
lede: "The downstream symptom (orphan `[^N]` markers in exported memos) is a citation-format failure at the very top of the pipeline: `research_enhanced.py` writes multiple sources onto a single line under the same `[^N]:` heading, with no newline separators and frequent ID reuse. Six of nine research files in the Panthalassa-Deck-Series-B v0.0.3 run carry these malformed lines (one section reuses `[^12]` six times). The downstream regex parsers only see the first source per ID and silently drop the rest. The `citation_validator` agent that exists checks claim accuracy, not bibliography format, so the malformation passes through unflagged. The architectural fix is the Source Harvester / Section Writer split documented in CLAUDE.md §'Architectural direction (2026-05)' but not yet built. Three smaller backstops can close the gap before that ships."
date_authored_initial_draft: 2026-06-15
date_authored_current_draft: 2026-06-15
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-06-15
at_semantic_version: 0.0.0.1
usage_index: 0
publish: true
augmented_with: Claude Code (Opus 4.7)
category: Issue-Resolution
tags: [Research-Agent, Citation-Validation, Source-Harvester, Multi-Agent, Validation-Gap, MemoPop, Orchestrator]
authors:
  - Michael Staton
files_changed: []
date_created: 2026-06-15
date_modified: 2026-06-15
---

# Research Agent Concatenates Multiple Sources Under One Citation ID — And No Validator Catches It

## Why this exists

The companion entry `Section-Citations-Orphaned-When-Defs-Live-In-1-Research.md` covers the downstream symptom (CLI assembly path didn't pull defs from `1-research/`) and ships the immediate fix (`cli/utils/hydrate_section_citations.py` wired into `recompile_memo.py`). That patch resolves orphans whose defs *exist somewhere reachable*.

But on the Panthalassa-Deck-Series-B v0.0.3 export, after the patch, the hydrator still reported 12 unresolved orphans — refs in sections 02 and 07 whose defs aren't anywhere readable. That isn't a missing-file problem. The defs exist, but in a *malformed* format that no regex on disk can parse. This entry diagnoses the upstream root cause and what the orchestration system was supposed to do about it.

## The malformation

Six of nine research files in the v0.0.3 run carry concatenated multi-source lines:

| File | Lines with concatenated citations |
|---|---|
| `01-risks-research.md` | 1 |
| `02-diligence-research.md` | 4 |
| `04-category-leadership-research.md` | 1 |
| `05-cagr-compound-annual-revenue-growth-research.md` | 1 |
| `07-colossal-market-size-research.md` | 5 |
| `08-counter-cyclicality-research.md` | 3 |

Example from `02-diligence-research.md`:

```
[^1]: 2025, Jan 13. [On the potential of ocean energy technologies to contribute to future sustainability](https://link.springer.com/...). Springer Nature. Published: 2025-01-13 | Updated: N/A: 2023, Nov 02. [Venture capital due diligence: data rooms and standard materials](https://a16z.com/dataroom-checklist). Andreessen Horowitz. Published: 2023-11-02 | Updated: N/A: 2022, May 18. [Standard documents and data required for startup due diligence](https://www.ycombinator.com/library/d/due-diligence-checklists). Y Combinator. Published: 2022-05-18 | Updated: N/A
```

That single line contains **three distinct sources** stitched together under one `[^1]:` heading. The downstream `^\[\^N\]:` parsers only see the first one (Springer Nature). The other two — perfectly real sources — are silently discarded.

`07-colossal-market-size-research.md` is worse: it defines `[^12]` **six separate times** in the same file, plus `[^14]` twice. Two pages of analyst work, mostly invisible to the assembler.

## Where in the pipeline this happens

The research agent is `src/agents/research_enhanced.py`. Per the orchestrator's own CLAUDE.md §"Architectural direction (2026-05)":

> Today's `research_enhanced.py` both searches *and* writes prose, which is why it hallucinates URLs. The target architecture: a **Source Harvester** that only calls tools and emits a validated corpus, and a **Section Writer** that only writes prose, citing the corpus by ID. The writer never has a search tool.

The malformation is the format-level expression of the same root problem: when one agent owns both retrieval and corpus-emission, its output discipline is whatever the prompt happens to ask for that day. In practice the prompt asks for citation defs with line discipline but doesn't *enforce* it, so when the agent collects N sources for a topic in a single tool call it concatenates them rather than emitting N separate lines with N separate IDs.

## Why the validators didn't catch it

The pipeline does have citation-aware validation agents:

- `src/agents/citation_validator.py` — checks date accuracy, duplicate URLs across cites, broken links
- `src/agents/fact_checker.py` — verifies prose claims against research sources
- `src/agents/validator.py` — overall memo quality score (0–10)

None of them checks **bibliography format**. There is no "every body `[^X]` has exactly one well-formed `[^X]:` definition on its own line" assertion anywhere in the pipeline.

For the v0.0.3 run, `3-validation.md` was generated and contains *zero* mentions of orphans, undefined refs, or missing definitions. The validator pass through these research files without flagging the multi-line concatenation.

## Why the CLI assembly path made it acute

The full pipeline (`python -m src.main`) runs all the enrichment + checking agents end-to-end. Some of those steps would have at least flagged the broken sources downstream, even if the bibliography format itself was missing from the assertion set.

The CLI partial-reassembly path (`python cli/recompile_memo.py`) — the workflow we've been using for analyst-driven edits, deck updates, and the Panthalassa-specific sweeps in this session — runs only `hydrate_section_citations.py` (new today) and `consolidate_citations.py`. It skips every validator. The CLI path was always shakier than the full pipeline; until today it had no orphan-detection at all.

## The chain of system failures, named

1. **Research agent's output discipline is prompt-shaped, not enforced.** `research_enhanced.py` is allowed to concatenate multiple sources under one ID because nothing structurally prevents it.
2. **No citation-format validator exists.** Existing validators check claim accuracy. Bibliography format ("every ref has exactly one def, each def on its own line, IDs unique within the file") was never anyone's responsibility.
3. **The Source Harvester / Section Writer split — the architecturally proper fix — isn't built yet.** It's documented in CLAUDE.md as the target state. The current pipeline is the broken intermediate.
4. **The CLI partial-reassembly path skips validators.** And it's the path analysts use for the kind of iteration we did today on Panthalassa, so problems hit production-export-quality output faster than they'd hit a full-pipeline run.
5. **No end-to-end integrity gate.** Even if every individual validator passes, nothing asserts that the final draft has zero orphans before export. Pandoc dies on broken footnote refs *and also* silently renders some as raw `[^X]` text. The pipeline trusts that upstream got it right.

## Three smaller backstops before the Source Harvester ships

Item 3 below is the real fix. Items 1 and 2 are inexpensive things that close most of the gap today.

### 1. A citation-integrity validator (the highest-leverage small fix)

A new validator step — could live as `src/agents/citation_integrity.py` or as a CLI util in `cli/utils/check_citation_integrity.py` — that walks both `1-research/*.md` and `2-sections/*.md` and asserts:

- Every `[^N]:` definition is on its own line; no concatenation.
- Each ID is unique within its file.
- Every body `[^N]` reference has at least one matching def reachable in either the section file or its corresponding research file.
- No body ref points to an ID that was reused under multiple defs (ambiguous).

Wire into both the full pipeline (after `research_enhanced.py` and before `writer.py`) and the CLI path (in `recompile_memo.py` after `hydrate_section_citations.py`). Exit nonzero on failure with a structured report. The hydrator already prints orphans; this validator would be the hard gate.

### 2. Tighten `research_enhanced.py`'s output discipline

A small prompt change in the research agent: when collecting N sources for a section topic, emit N separate `[^N]:` definitions, each on its own line, each with a fresh sequential ID. No appending under existing IDs. Add a post-emit self-check (a tool call the agent makes to lint its own output) before returning.

This is the cheapest fix and it closes the originating cause. Doesn't replace item 1 — item 1 is the safety net even if the prompt drifts later.

### 3. Ship the Source Harvester / Section Writer split

The CLAUDE.md-documented architectural direction. The Source Harvester only calls retrieval tools and emits a structurally validated corpus (one source per ID, validated URL, deduped). The Section Writer only writes prose citing the corpus by ID, with no search tool of its own. Both items 1 and 2 above become unnecessary in the limit — the harvester produces well-formed output by construction and the writer can only cite IDs that exist.

This is the proper fix. It's also the largest change, since it splits one agent into two and reworks the prompts and state flow between them.

## How we learned this exists, concretely

Working session on 2026-06-14 / 2026-06-15 with the Panthalassa-Deck-Series-B v0.0.3 export. After hand-editing several sections and running the CLI assembly + export path, the rendered PDF showed a large fraction of `[^N]` references as raw text instead of footnote markers. Initial diagnosis was a path-resolution bug in `consolidate_citations.py`. Once that was patched and the CLI path was brought to parity with the full pipeline (via `hydrate_section_citations.py`), 47 of the original ~50 distinct sources started resolving — but 12 didn't. Tracing those 12 back to their research files surfaced the concatenation pattern.

The post-patch state of v0.0.3 is the data referenced in this entry. The remaining 12 orphans are real and survive in the export until either (a) the research files get fixed by hand, (b) the research agent re-runs with better discipline, or (c) the analyst strips the affected refs from the section prose.

## See also

- `Section-Citations-Orphaned-When-Defs-Live-In-1-Research.md` — the downstream-symptom fix (hydrator + CLI wiring) that exposed this root cause
- `context-v/agent-skills/manage-memo-citations/SKILL.md` — the canonical citation discipline (foundational defs in `1-research/`, semantic IDs over numeric)
- `Correct-Citation-Pipeline-Accuracy-in-Multi-Agent-Research.md` — adjacent entry on citation accuracy in the multi-agent flow
- `Faked-Sources-from-Perplexity.md` — adjacent entry on Perplexity-generated source fabrication; same architectural failure mode at a different layer
- `Preventing-Hallucinations-in-Memo-Generation.md` — the broader hallucination-prevention discipline this sits inside
- `CLAUDE.md` §"Architectural direction (2026-05)" — the Source Harvester / Section Writer split that, when shipped, makes this class of bug structurally impossible
- `src/agents/research_enhanced.py` — the agent producing the malformed output
- `src/agents/citation_validator.py` — the existing validator that checks claim accuracy but not bibliography format (the gap)

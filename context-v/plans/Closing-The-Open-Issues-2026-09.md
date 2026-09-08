---
title: "Closing the Open Issues — September 2026"
lede: "Seven steps across four open issues, worked one at a time: implement, test, check off, move on. Ordered so the thing that gates actually running a thesis frame lands first, and the two quality gates that currently read from the wrong place are fixed before anyone trusts their scores again."
date_authored_initial_draft: 2026-09-08
date_authored_current_draft: 2026-09-08
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-09-08
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Plan
date_created: 2026-09-08
date_modified: 2026-09-08
tags: [Thesis-Frames, Citations, Fact-Checker, Validator, Sanitizer, Test-Coverage]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: b1d3bc8f-ed03-4cd2-abeb-6b1eeef51987
hex_code: 1l948w
status: In-Progress
---

# Closing the Open Issues — September 2026

## Method

One step at a time. Implement, run the suite, check the box, commit, move on. Each
step names its own test so "done" is observable rather than asserted.

## Ordering rationale

Evidence ingestion is first because it is the only thing standing between the
thesis-frame feature and a real run — without it a framed run writes prose citing
a document `1-research/` has never seen, which is the same durability hole as #28.
The citation collision is next because it silently mis-attributes sources in every
memo the pipeline produces. The gates come after, because their scores are
currently noise and fixing them changes what "good" means. The sanitizer is last
because it changes what ships and wants a deliberate placement decision.

## Steps

- [x] **1 — Evidence ingestion** (#29). DONE — `src/frame_evidence.py`, 9 tests Frame `evidence[]` documents read into the
      corpus the codified researcher may cite, registered so citations resolve,
      before any section is researched.
      *Test:* a frame with an evidence path produces a research file citing it.

- [x] **2 — Additive research writing + provenance stamps** (#29). DONE — `src/research_append.py`, 10 tests Every block a framed
      run appends carries `<!-- research-block: frame=… run=… appended=… -->`.
      *Test:* appended block carries the stamp; existing content is untouched.

- [x] **3 — The `amend` directive** (#29). DONE — writer reads prior prose, 7 tests The writer receives the prior section
      text and is asked for the minimum consistent change.
      *Test:* `amend` passes prior prose; `rewrite` does not.

- [ ] **4 — `--scope-to-frame` and `re-score`** (#29). Skip inert sections
      entirely; thread the frame into the scorecard evaluator.
      *Test:* scoped run skips inert sections; scorecard receives the frame.

- [ ] **5 — Per-section citation ID scoping** (#28). Resolve definitions within
      the section that references them, so `01`'s `[^1]` and `03`'s `[^1]` stop
      colliding. Enrichment writes definitions to `1-research/`, not to section
      files the assembler strips.
      *Test:* two sections each defining `[^1]` differently both resolve correctly.

- [ ] **6 — Point the gates at the real corpus** (#27). Fact-checker reads
      `1-research/` + `3-source-catalog/`; sourcing widens from sentence to
      paragraph; numbers normalise before matching. Validator receives the source
      catalog and the codified-mode flag, and runs after the last content mutation.
      *Test:* a paragraph-cited claim counts as sourced; a dataroom path is not a defect.

- [ ] **7 — Wire the sanitizer into the graph** (#30). Place it after
      `enrich_links`, before `cleanup_sections`; extracted commentary to a side
      artifact rather than dropped.
      *Test:* a section carrying a refusal is cleaned in a graph run.

## Progress log

### Step 1 — Evidence ingestion. Done (`b9971c7`).

`src/frame_evidence.py` turns a frame's `evidence[]` into `SourceEntry` objects
with `file://` URLs and loads their content into the same `fetched` dict the
codified researcher fills from Sources.md, so per-section synthesis treats them
like any other approved source and needs no special case. Non-markdown reads
through `curation.fetch.fetch_local_file`, which already handles .docx/.pptx/
.xlsx and OCRs image PDFs.

Three decisions worth recording:

- Evidence ranks **0**, ahead of the standing corpus, because the frame's own
  documents are what the thesis rests on.
- It is tagged **only for sections whose directive actually researches**. Tagging
  it for a section the frame preserves would pull new material into prose the
  operator asked to leave alone.
- Sections are matched on the frame's own `affects` keys rather than through
  `sources_for_section`'s forgiving tag matcher, so a rename cannot silently
  drop evidence.

Missing or unreadable evidence is reported, never raised — a bad path should make
a loud run, not a dead one.

9 tests, 84% on the module. ProfileHealth's Prudential proposal ingests at 16,398
chars, tagged for the 5 sections that extend.

**Process note:** the first copy of this plan was written into
`io/humain/context-v/plans/` because the shell was still standing in that
submodule. Removed there and relocated here — orchestrator process docs do not
belong in a firm-private repo.


### Step 2 — Additive research writing + provenance. Done.

The bigger half of this step was not the stamp. Both codified synthesis paths
ended in `write_text`, so research was additive only in the *instruction* given
to the model — the file itself was still being replaced. Under a frame that is
precisely backwards, and it would have quietly destroyed the clinician evidence
base on the first framed run of ProfileHealth.

`src/research_append.py` routes both paths through `write_or_append_research`,
which appends only when all three hold: a frame is active, the section's research
directive is `extend` or `refresh`, and the file already exists with real
content. Anything else writes as before, so an unframed run is untouched.

Appended blocks carry `<!-- research-block: frame=… run=… appended=… -->`.
`has_block` makes the append re-entrant — a resumed run cannot contribute its own
findings twice — while a *later* run appends a second block, which is what makes
a frame reversible: dropping a thesis means dropping its blocks rather than
re-deriving the file.

The appended body is itself a whole research file with its own H1, so the H1 is
demoted to keep one top-level heading in the merged file. Citations blocks are
left alone; the assembler reads definitions wherever they appear.

10 tests. The load-bearing one asserts the prior finding survives:
`assert "350K physicians" in text`.

### Step 3 — The `amend` directive. Done.

`amend` exists so a re-angle does not discard sections that were never wrong,
only narrow — Offering and Risks on ProfileHealth. The directive existed and was
tested, but the writer never fed it the prior section text, and "make the minimum
change" is not followable without the thing being changed.

`_prior_section_prose` reads `2-sections/<filename>` lazily and **only** for
`amend`. Every other directive is either a clean regeneration — which must not
see the old prose, or it anchors on it and defeats the point of reframing — or a
no-op. Both writer paths pass it.

When a section is marked `amend` and no prior prose exists, the block says so
explicitly rather than silently degrading into a rewrite that would throw away
good sentences and their citations.

7 tests, including that citation markers survive into the prompt (they are the
reason amend beats rewrite) and that `rewrite` never sees the old draft.
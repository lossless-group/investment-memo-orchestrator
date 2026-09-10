---
title: "Agent Sequencing for Deals We Already Have Content On"
lede: "The graph runs every stage from dataroom forward on every invocation, and caching is the only thing standing between a re-run and an hour of re-extraction. Every cache is keyed on content that ordinary maintenance changes, so the caches keep silently missing and the pipeline keeps redoing settled work. What is needed is an explicit entry point — resume at web research, or resume at writing — with additive semantics at each, rather than a graph that always starts at the beginning and hopes a hash still matches."
date_authored_initial_draft: 2026-09-10
date_authored_current_draft: 2026-09-10
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-09-10
date_modified: 2026-09-10
tags: [Agent-Sequencing, Resume, Caching, Thesis-Frames, Additive-Research, Deck-Analyst, Dataroom]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: 1fe5a7a3-3ed1-44c8-b8cd-c3b6ac6d3a34
hex_code: nugass
status: Open
severity: High
---

# Agent Sequencing for Deals We Already Have Content On

## Start here

A fresh session can pick this up cold. Read this file, then
[[Thesis-Frames-And-The-Re-Angle-Run]] — the frame work is built and tested, and
this issue is the thing blocking it from running end to end.

## What happened

The ProfileHealth v0.0.4 run (frame `ltc-carrier-b2b2c`) was launched three
times across one session. It never reached the researcher.

The third attempt got further than the others and then died here:

```
♻️  reusing the dataroom analysis from ProfileHealth-v0.0.4 (161 documents, unchanged) — no re-extraction
Extracting text from PDF deck (Profile Deck.pdf)...
⚠️  Minimal text extracted - PDF appears to be image-based
Using Claude's PDF vision to analyze deck...
Processing slides 1-5 (batch 1/5)...
ERROR: Batch 1 failed: Error code: 400 — 'Your credit balance is too low to access the Anthropic API.'
… ×5
Merging 0 batch analyses...
ERROR: No batches were successfully analyzed
```

The dataroom reuse worked — that was fixed earlier in the session. The deck
then re-analysed from scratch, went straight to the metered API, and hit a zero
credit balance. Five vision batches, five failures, zero output.

## Why the deck analyst ran at all

Nothing conditional about it. `src/workflow.py:496` sets the entry point to
`dataroom` and `:526-527` wire `dataroom → deck_analyst → research`. **Every
stage runs on every invocation.** The only thing that makes a re-run cheap is a
cache check *inside* each agent — for the deck, `deck_analyst.py:918-938`.

That cache is keyed on a content hash of the PDF (`fingerprint_file`), stored at
the deal level in `.cache/deck-<fp>/`. It missed because the deck's bytes
changed:

```
current deck : 2.27 MB   fp=7453c0812bd5
cached       :           deck-019b89fa11ce
parked orig  : 63.71 MB  fp=019b89fa11ce
```

Asset normalization (`src/asset_normalize.py`, added the same session)
compressed `Profile Deck.pdf` from 63.71 MB to 2.27 MB. The content the pipeline
reads is identical — OCR yields 2,417 characters against the original's 2,415 —
but the hash is not, so the cache orphaned itself.

**This is the third instance of one pattern in a single session:**

| Cache | Keyed on | Invalidated by |
|---|---|---|
| Dataroom analysis | document count + total bytes | normalization changing 230 MB; media parked as transcripts changing the count |
| Deck analysis | PDF content hash | normalization compressing the deck |
| Frame research append | file present in the *new* version dir | version forking, until seeding was added |

Each was fixed individually — `normalized_byte_delta` discounts, artifact-based
rebuild, `seed_version`. The deck one is **still open**. The pattern says the
design is wrong: *content-hash caching is not a resume mechanism.* It is a
best-effort optimisation that any legitimate maintenance defeats, and the
pipeline has no fallback when it does.

## What is actually wanted

An explicit entry point, chosen by the operator, with clear semantics at each.

### Default: do not repeat settled work

Anything before the chosen entry point is **not re-run**. Not "cheaply re-run
if a hash matches" — not run. The artifacts are on disk, they are the input, and
the operator is asserting they are current.

### Entry point: web research

Re-performs web research only. **Net-new sources are added to the existing
research files** along with the insights and facts drawn from them; everything
already recorded stays. This is exactly the additive contract already built and
tested in `src/research_append.py` (`write_or_append_research`) — appends under
a provenance stamp, never overwrites, re-entrant within a run. That mechanism
exists and works; what is missing is a way to *enter* the pipeline there.

Research needs **arguments for what to look for**, because "re-run research"
is under-specified. The operator knows what changed:

- a new GTM customer base (the ProfileHealth case: LTC carriers)
- a new competitive landscape
- a new round or new terms
- refreshed traction

The thesis-frame object already carries most of this — `premise`, per-section
`questions`, `evidence`, `caveats` — see
[[Thesis-Frames-And-The-Re-Angle-Run]]. A research-scoped run should be able to
take a frame and nothing else.

### Entry point: writing

**No web search at all.** The prior analysts left a paper trail — research
files, source catalog, dataroom extractions — and it is sufficient. The job is
re-synthesis of the sections, not re-gathering. The frame's per-section prose
directives (`rewrite` / `amend` / `re-score` / `unchanged`) already describe
exactly this and are built.

### The operator knows, and sometimes does not

Usually the operator knows whether a new deck or a new dataroom document
arrived. Sometimes not. So:

- Entry point is **explicit and required** for a re-run against existing content;
  there should be no silent "start from the top and hope the caches hit".
- When the operator does not know, a **cheap change-detection report** should be
  available — what is new, changed, or missing since the last run, printed
  without spending a model call — so they can choose an entry point on evidence.
  The scan needed for this already exists; `_reusable_dataroom_analysis` performs
  it on every run.

## Concrete implementation notes

1. **`--from <stage>`** on `src/main.py`, alongside the existing `--resume`,
   `--fresh`, `--frame`, `--version`. Stages worth naming: `dataroom`, `deck`,
   `research`, `write`, `assemble`, `export`. Everything before the named stage
   is skipped outright and its artifacts are read from the seeded version dir.
2. **Seeding already handles the carry-forward** — `src/version_seed.py` copies
   `1-research/` and `2-sections/` from the prior version when a frame is
   active. Widen it to the artifacts each entry point needs (deck analysis,
   dataroom artifacts) and make it apply to any `--from` run, not only framed
   ones.
3. **Fix the deck cache the way the dataroom one was fixed.** Normalization
   writes a ledger (`_zip-originals/normalized.json`, see
   `src/asset_normalize.py:record_normalized`). The deck cache should consult it
   — a deck whose parked original hashes to the cached fingerprint is the same
   deck. The parked original is right there at
   `_zip-originals/oversized/<path>` and still hashes to `019b89fa11ce`.
4. **`--resume` already exists** (`src/main.py`) but resumes a version rather
   than selecting a stage. Reconcile the two rather than adding a third concept.

## Related

- [[Thesis-Frames-And-The-Re-Angle-Run]] — `context-v/specs/`. The frame object,
  the two injection points, the additive-research rule, the per-section
  directives. **All built and tested this session** (`src/frame_loader.py`,
  `src/frame_context.py`, `src/frame_evidence.py`, `src/research_append.py`,
  `src/version_seed.py`; 404 tests pass). Blocked only by this issue.
- [[Closing-The-Open-Issues-2026-09]] — `context-v/plans/`. Steps 1-3 done;
  4-7 open.
- [[Route-Every-Claude-Call-Through-The-CLI-First-Provider]] — the other half of
  why this run died. The deck analyst bills the metered API directly.
- [[Validation-and-Fact-Checker-not-using-Research]] — the gates read the wrong
  corpus; relevant once sections regenerate.
- `src/deck_cache.py` — the deal-level deck cache and its docstring on why it exists.
- `io/humain/deals/ProfileHealth/frames/ltc-carrier-b2b2c.yaml` — the first frame,
  ready to run.

## State of the ProfileHealth run, for whoever picks this up

- `v0.0.4` exists, seeded with v0.0.3's `1-research/` and `2-sections/` (20 files).
- Its dataroom analysis is **complete and current** — 161 documents, reusable.
- `1-research/` has **zero** frame content: no provenance stamps, no mention of
  Prudential or long-term care. The frame has never applied.
- `2-sections/` is byte-identical to v0.0.3.
- No assembled memo. The exported HTML the operator has is v0.0.3, the
  clinician-thesis memo, with a corrected §9.
- §9 is `prose: unchanged` in the frame and carries hand-written work that must
  not be regenerated.

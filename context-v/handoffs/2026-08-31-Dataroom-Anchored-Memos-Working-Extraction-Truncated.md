---
title: "Handoff — dataroom-anchored memos working, extraction still truncated"
lede: "The writer finally reads the dataroom, and CogSciAI's terms section cites its own SAFEs. Extraction still sends 1% of a spreadsheet to the model, so the richest series in the tree never arrive."
date_created: 2026-08-31
date_modified: 2026-08-31
date_authored_initial_draft: 2026-08-31
date_authored_current_draft: 2026-08-31
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5 (1M context)
at_semantic_version: 0.0.1.0
status: Active
publish: false
category: Handoff
tags:
  - Handoff
  - MemoPop
  - Dataroom
  - Time-Series
  - Transcription
  - Source-Curation
  - Extraction
site_uuid: d8106209-f3c3-45d5-af92-77679f01a101
hex_code: t2ww5j
---

## Where things stand

| Repo | HEAD | Branch | Pushed |
|---|---|---|---|
| `apps/memopop-orchestrator` | `ba7afb0` | `fix/timeseries-analyst-defects` | ❌ |
| `memopop-ai` | `3705e3c` | `main` | ✅ |

**282 tests pass, 1 skipped.** A large amount of work is **uncommitted** — 18 modified
files and 10 untracked paths, including the whole `src/agents/timeseries/` package.
Nothing is half-applied; it all runs.

Two memos generated end to end this session:

- **CogSciAI v0.0.3** — 8,585 words, dataroom-anchored, §9 cites both SAFE vehicles by filename
- **ProfileHealth v0.0.2** — generated *before* the writer fix, so its §9 says terms are "not available" while seven signed SAFEs sit in the same folder. **Re-run it.**

## Do this first

1. **Re-run ProfileHealth.** Everything it needs is on disk: curated `Sources.md`
   (29 sources, `mode: codified`), 16 dataroom documents staged into
   `inputs/sources/`, and the dataroom analysis will reuse rather than re-extract.
   The only reason its memo is wrong is that it predates `writer.py`'s grounding.
2. **Re-run CogSciAI** if you want section 3 filled. `03-opening` came out at
   46 words because I tagged no sources for it; `Sources.md` is now corrected
   (Opening 4, Organization 4, Scorecard 2) but the run predates the fix.
3. **Commit.** The branch name (`fix/timeseries-analyst-defects`) no longer
   describes what is on it.

## What landed

**The writer reads the dataroom.** `writer.py` gained `dataroom_facts_for_section()`,
threaded into both writer paths. It was the single biggest defect in the system:
`dataroom_analysis` sat fully populated in state and no writer path ever read it,
so an hour of extraction informed zero words of prose. Grounding is additive and
cannot raise — verified against real states for portfolio companies *and* pipeline
deals (`None`, key-absent, malformed all return `""`).

**Time-series transcription runs in the pipeline.** `timeseries/from_dataroom.py`
converts extractor output to `Observation`s; `_transcribe_time_series()` calls it
from the dataroom step, on both the fresh and reuse paths. CleatusAI produced the
first pipeline-generated grid: **44 observations, 11 dense months, 4 metrics, zero gaps.**

**The transcriber/analyst split is specced and implemented.** `time-series_analyst`
became `time-series_transcriber` and computes nothing. Roll-up, `declare_metric_kind()`,
`is_rolled_up` and fiscal-quarter derivation moved to
[[../specs/Timeseries-Analyst-Post-Transcription]], which is `In-Review` and unbuilt.

**Extractors stopped masking their own failures.** Four of them did raw `json.loads`
on a completion, so a fenced-but-valid reply and a failed API call produced the same
message — and neither triggered the CLI→API fallback. They now use `.ok` / `.json()`.
The cap table this hid was ProfileHealth's, holding all seven SAFEs.

**Every step writes as it goes.** The dataroom pass held eight extractors in memory
and wrote once at the end; a kill at minute 20 produced an empty directory. Now each
result lands as it completes. Reminder: [[../reminders/Every-Step-Writes-Its-Output-To-File]].

**Dataroom analysis is reused** when path, document count and total bytes are unchanged.
`--fresh` overrides.

**Local files became first-class sources.** `fetch_local_file` only handled
PDF/MD/TXT/HTML — most of a dataroom is `.docx`/`.pptx`/`.xlsx`. It now delegates to
the shared text layer and OCRs image-based PDFs.

**Two settings** in `src/source_priority.py`: `MEMOPOP_SOURCE_PRIORITY`
(`local-first` default) and `MEMOPOP_RESEARCH_PROVIDER` (`perplexity` default,
`claude-code` selectable). Perplexity is selected away from, never removed.

## The finding that matters most

**Extraction truncates spreadsheets to 6–8k characters.** The Unnatural Products
operating model extracts to **720,696 characters**; the extractor sends **8,000** — 1.1%.
The model sees the cover matter, reports *"Data values not visible in provided extract"*,
and is not wrong.

| Unnatural Products | observations |
|---|---|
| hand adapter reading the workbook | **11,919** |
| pipeline, via the extractor | **0** |

Same files. CleatusAI only worked because its sheet was small enough to fit.

**The transcriber is not the bottleneck. Extraction is.** Fix: route spreadsheets
sheet-by-sheet rather than truncating the workbook — `HistIS` alone is 85 columns of
dated monthly actuals and fits comfortably.

## Gotchas that cost real time

- **`analyze_dataroom` sends `charter_document` to the legal extractor.** ProfileHealth
  sent **109 documents** where 8 carry terms; 76 were incorporation certificates and
  83(b) elections. Par value from a charter leaked into the reconciled term set as
  `share_price: 0.00001`. Spec written: [[../specs/Targeted-Legal-Scan-of-Datarooms]].
- **`reconcile_legal_docs` collapses instruments.** Seven SAFEs at three caps become one
  `terms` dict plus invented "conflicts". **Per-document records are correct** — use
  `legal_docs`, never `legal_summary`. The grounding block already does.
- **`scorecard` is per-firm.** Humain uses `direct-early-stage-12Ps`; `early-stage-12Ps`
  is dark-matter's. Read a sibling config before writing one.
- **`portfolio/` is the record of an investment; `deals/` is the memo workspace.**
  Submersive is the precedent — one executed SPA in portfolio, deck and config in deals.
  A memo needs a deal folder.
- **`io/humain/portfolio/` is gitignored** — 258 MB, zero files tracked, and it holds
  every portfolio dataroom plus `_analysis/` and `_source-transcriptions/`. Not backed
  up by git. Dark-matter's `deals/` is tracked, which is why the Radicle deck survives
  there and not in Humain.
- **Google Drive zips break macOS `unzip`.** UTF-8 names without the flag bit; it fails
  with "illegal byte sequence" and silently drops files. Extract with Python `zipfile`,
  recovering names via cp437→utf-8.
- **A crashed run cannot be reused** — reuse needs `state.json`, which a crash never
  writes, even though every numbered artifact is on disk. Worth a fallback.
- **Perplexity 429s drop a section's research silently.** There is retry logic for
  garbage content, none for rate limits.

## Loose ends

- ProfileHealth `03-opening` equivalent: CogSciAI's is a 46-word stub
- `08-scorecard-summary` is 3,457 words — 40% of the CogSciAI memo
- Ungrounded evidence spans are logged, not stripped: 0/3/7/3/4 across sections
- `Shankar13a` paper path unresolved in CogSciAI `Sources.md` (14 of 15 staged)
- `deck_analyst` still calls `PdfReader`-era paths elsewhere; only the page count was fixed
- D1–D8 in [[../issue-resolution/Archive-Dating-And-Time-Series-Defect-Hitlist]] untouched —
  PDF creation timestamps still asserted as authorship

## Map

| Path | What |
|---|---|
| `src/agents/writer.py` | `dataroom_facts_for_section()` — the grounding block |
| `src/agents/timeseries/` | transcriber, `from_dataroom.py`, periods, timeline |
| `src/agents/anomalies.py` | the pressure valve; nothing reads it into the memo |
| `src/source_priority.py` | the two settings |
| `src/curation/fetch.py` | local-file reading, now Office + OCR |
| `context-v/specs/Company-Timeline-And-Month-Indexed-Time-Series.md` | transcription contract, `Partially-Shipped` |
| `context-v/specs/Timeseries-Analyst-Post-Transcription.md` | the analyst, `In-Review`, unbuilt |
| `context-v/specs/Targeted-Legal-Scan-of-Datarooms.md` | 109 → 9, `Draft` |
| `context-v/reminders/` | three new: write-to-file, round-closing, normalize-labels |

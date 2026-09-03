---
title: "Archive Dating and Time-Series Defect Hitlist"
lede: "Seventeen defects found by the first live run of the time-series analyst, ordered so the ones that corrupt the archive's chronology get fixed before the ones that only corrupt a grid. The dating defects come first because a wrong date is written into a filename, looks exactly like a right one, and silently re-anchors every analysis that reads it afterward."
date_authored_initial_draft: 2026-08-24
date_authored_current_draft: 2026-08-24
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-08-24
date_modified: 2026-08-24
tags: [Time-Series, Archive-Rename, Date-Resolution, Company-Timeline, Dataroom-Extraction, Provenance, Issue-Resolution]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
status: Partially-Resolved
severity: High
---

# Archive Dating and Time-Series Defect Hitlist

## Status

T1, T2, T4, T6 and T9 are **fixed** (T3 is withdrawn — see below) and verified against a second Unnatural
Products run; regression tests were added and the suite stands at 94 passing. The agent is now `time-series_transcriber`; counts and date parts are zero-padded; the column contract is `date` + `YYYY`/`HH`/`QQ`/`MM`/`DD`/`FM`.
The dating defects (D1–D8) and the wiring defects (T5, T7, T8) are **open** — they
live in the rename and extraction pipelines, which the spreadsheet-fed run does
not exercise.

## How this was found

First live run of `src/agents/timeseries/`. Two datarooms:

- **CogSciAI** (`io/humain/portfolio/CogSciAI`) — ran the full extraction pipeline
  twice, once on the existing 2026-08-23 analysis and once fresh on the renamed
  archive. Both produced **zero observations and zero origin candidates**.
- **Unnatural Products** (`io/humain/portfolio/Unnatural Products`) — read the six
  workbooks directly with `openpyxl`, no LLM pass. **11,919 observations, 8 CSVs.**

The Unnatural Products run proves the analyst's core mechanism is sound. Its
historical income statement and its forecast landed in separate files that join
on `month_count` with no overlap and no gap — `month_count` 63 is the last
`actual` (2023-03), 64 is the first `projection` (2023-04) — with `basis`
preserved across the seam and a spot-check against the source matching exactly.

Everything below is what broke around that working core.

---

## Part 1 — Dating. Fix these first.

A wrong date is not like a wrong number. A wrong number is visible next to a
right one and someone argues about it. A wrong date gets written into a filename,
becomes the archive's sort order, becomes the analyst's file stamp, and then
silently re-anchors every count in every grid derived from it. There is no
downstream check that can catch it, because by then it is indistinguishable
from a fact.

### D1 — A PDF creation timestamp is asserted to be the document's own date

**Severity: High.** `src/agents/slides/date_resolution.py:341-344`

```python
candidates.append(DateCandidate(
    value=meta_date, source="pdf-meta", confidence="medium",
    kind="deck_date", context="PDF creationDate",
))
```

`kind="deck_date"` is hardcoded. A PDF's creation timestamp records when *that
file* was made — which, for a downloaded paper, a printed-to-PDF contract, or a
re-saved form, is a download or print date, not the document's date. Asserting
`deck_date` launders a filesystem fact into a claim about authorship, and
`DECK_DATING_KINDS` (line 84) then lets it date the archive.

**Evidence.** `shankar13a-Optimal Fuzzy Temporal Memory.pdf` was renamed to
`20140104_…`. The `shankar13a` token is the PMLR/JMLR convention — author, two-digit
year, disambiguator — meaning **Shankar 2013**. The PDF has no extractable text
(it is scanned), so `pdf-meta` was the only surviving candidate and it won
unopposed. The paper is filed a year after it was written.

`pdf-meta` accounts for **11 of CogSciAI's 22 renames**.

**Fix.** Give `pdf-meta` `kind="file_created"`, and leave `file_created` out of
`DECK_DATING_KINDS`. It should be recorded, rankable, and usable as a
last-resort *bound* — "not authored after this" — never as the document's date.

### D2 — The date's *kind* is computed and then thrown away

**Severity: High.** `src/agents/slides/archive_rename.py:48-65`

`date_resolution` does the hard part well. It classifies every date it finds into
`deck_date | meeting_date | closing_deadline | as_of | mentioned | projection |
historical` (`classify_date_kind`, line 98), keeps every candidate with its
surrounding context in `dates_mentioned`, and exposes all of it through
`DeckDates.as_frontmatter()` (line 70).

`RenamePlan` then records `date_used`, `date_source`, `date_confidence`,
`collection`, `doc_name`, `notes` — and **not `kind`, and not `dates_mentioned`**.

This is the defect that matters most for the concern that prompted this document.
The system already knows the difference between when a document was written, when
it was presented, what it is as-of, and when a deal closes. That knowledge is
computed, used once to pick a winner, and then discarded at the archive boundary.

**Fix.** Add `date_kind` and `dates_considered` to `RenamePlan.as_dict()`. They
already exist upstream; this is plumbing, not new inference.

### D3 — The filename carries a value with no confidence and no meaning

**Severity: High.** `archive_rename.py` naming; consumed by
`src/agents/timeseries/analyst.py:247` (`_filename`)

`20240820_` looks identical whether it came from a signature block or from the
median of eight siblings spanning five months. Once the extractor reads the
filename — which is the recommended fix for D5 below — the confidence and the
kind are gone, and a low-confidence guess enters the time series as a stated fact.

**Fix.** The filename stays as it is; it is a sort key, not a record. But the
manifest must be the authority, and anything reading a date *off a filename* must
be able to look up its kind and confidence. Options, in order of preference:

1. A per-company `dates.yaml` written beside the archive, keyed by final filename.
2. A sidecar `.meta.yaml` per document.
3. A confidence marker in the name itself (`20240820~_…` for inferred). Rejected
   unless 1 and 2 prove impractical — it makes the name lossy in a new way.

### D4 — Sibling inference produces a precise-looking date from a five-month spread

**Severity: Medium.** `date_resolution.py:370-381`

```python
ordered = sorted(sibling_dates)
inferred = ordered[len(ordered) // 2]
```

The median of the neighbours. The note is honest — *"inferred from 8 sibling
document(s) spanning 2024-07-10–2024-12-19"* — but the note lives in the manifest
and the **day-precision date** lives in the filename.

**7 of CogSciAI's 22 renames (32%) are sibling-inferred**, including all three
Deal Memo / IP documents and `MVP.pdf`.

Worse, the inference is sometimes circular. Both copies of
`Cognitive Scientific -2024 SAFE (Cap and Discount)` resolved to `2024-10-21`
*"inferred from 2 sibling document(s) spanning 2024-10-21–2024-10-21"* — the
siblings are the other copy of the same document and the enclosing folder
`20241021_CogSciAI_SeedDocuments--Seed`. The folder dated the document, and then
the document corroborated the folder.

**Fix.** Sibling inference should degrade precision, not just confidence: emit
`2024-Q4` or `2024-10` rather than `2024-10-21`, and exclude same-stem siblings
and the enclosing folder's own stamp from the candidate pool.

### D5 — Extractors never read the date that renaming just established

**Severity: High.** `src/agents/dataroom/extractors/legal_extractor.py`

The fresh CogSciAI run found four SAFEs with real money — `investment_amount`
200,000 / 200,000 / 182,000, `valuation_cap` 120,000,000 — and returned
`document_date: null` and `effective_date: null` on **all four**. Eight real
numbers dropped for want of a period, and no `first_financing_close` origin
candidate could be offered.

The instruments themselves say *"on or about \_\_\_, 2024"* — the blank is
literally unfilled. The filename is the only date evidence that exists for these
documents, and nothing reads it.

**Fix.** Filename date as a fallback in the legal extractor, tagged with the kind
and confidence recovered per D3 — never silently promoted to `effective_date`.

### D6 — Two vehicles, four documents, and no way to say what kind each date is

**Severity: High.** Analysis finding, not a single code site.

Humain came into CogSciAI through **two separate vehicles**, both on identical
terms ($120M post-money cap, 15% discount):

| Vehicle | Amount | Documents | Stamped | Source | Confidence |
|---|---|---|---|---|---|
| Humain Ventures Fund I, LP | $200,000 | signed SAFE | 2024-08-20 | pdf-meta | medium |
| " | " | unexecuted SAFE (.docx + .pdf) | 2024-10-21 | sibling | **low** |
| " | " | ACH/wire confirmation | 2024-08-14 | pdf-meta | medium |
| Humain Ventures CogScAI SPV, a Series of Decile SPV, LLC | $182,000 | SAFE | 2024-12-10 | pdf-meta | medium |

Total exposure is **$382,000**, not $200,000 — see D8.

**The wire landing six days before the signed SAFE is not a defect.** That is
ordinary practice: an investor wires against an agreed close and the paper gets
countersigned afterward. Sequence alone proves nothing here.

The defect is that the archive gives no way to *tell the difference* between that
normal case and a real problem. Every row above is a bare `YYYYMMDD_` with no kind
attached, so a settlement date, an execution date, and a PDF creation timestamp
render identically. A reader cannot ask "did the wire settle before or after
execution" — only "which number is smaller," which is a different question and
does not have the same answer.

What *is* substantively wrong in this set:

- The 10-21 pair is folder-dated by the circular sibling inference in D4 — the
  only evidence for that date is the folder it sits in. These are the *unexecuted*
  copies of the same Fund I instrument the 08-20 document executes, so their date
  is close to meaningless and is currently indistinguishable from a real one.
- A prior extraction run flagged *"filename says executed but the text says
  unexecuted — verify manually"* on the 08-20 document, and nothing carries that
  caveat forward.
- Three of the four dates are `pdf-meta`, which per D1 is a file-creation
  timestamp asserted as the document's own date.
- The SPV closed roughly four months after the fund position. That two-stage
  story is the single most useful fact in this folder, and it survives only
  because someone reads the filenames.

**Fix.** This is the concrete case D1–D5 must be validated against. A wire
confirmation carries a `settled` date; a signature block carries an `executed`
date; an unexecuted form carries neither. Success looks like the archive stating
"Fund I wire settled 08-14, instrument executed 08-20; SPV instrument dated
12-10" — and being equally able to say "we do not know when this was executed"
for the 10-21 pair, rather than inventing a day-precision date for it.

### D8 — Distinct vehicles are collapsed into one term set and their differences reported as conflicts

**Severity: High.** `src/agents/dataroom/extractors/legal_extractor.py`, legal summary

The fresh CogSciAI run produced:

```json
"terms": { "valuation_cap": 120000000.0, "discount_rate": 15.0,
           "investment_amount": 200000.0 },
"conflicts": [ { "field": "investment_amount",
                 "values": [182000.0, 200000.0] } ]
```

One `investment_amount` for the whole company, and the SPV's $182,000 filed as a
*conflict* against it. It is not a conflict. They are two different investors
subscribing through two different vehicles, and the extractor's own captured
evidence says so in as many words — *"Humain Ventures Fund I, LP … of $200,000"*
versus *"Humain Ventures CogScAI SPV, a Series of Decile SPV, LLC … of $182,000"*.

The summary shape assumes one round with one set of terms. Real seed positions are
routinely a fund plus one or more SPVs, often on identical terms, and the whole
point of tracking them separately is that they are separate subscriptions with
separate closes.

Two consequences, both silent:

1. **Reported exposure is wrong** — $200,000 against an actual $382,000.
2. **A genuine signal is spent as noise.** The one thing flagged for human review
   is the thing that was correct.

Also: `investors: []` on all four documents, despite the investor's full legal
name sitting in the evidence string the extractor itself captured. That field is
what would key the instruments to their vehicles.

**Fix.** Key terms by *instrument*, not by company: a list of
`{investor, vehicle, amount, cap, discount, executed, dates}` records. Reserve
`conflicts` for two documents making incompatible claims about the *same*
instrument. Populate `investors` from the evidence already in hand.

### D7 — There is no date-kind vocabulary at the archive level

**Severity: Medium.** Design gap.

`date_resolution` has a kind vocabulary tuned for decks. The archive needs one
tuned for a dataroom, covering at least:

`authored` · `file_created` · `sent` · `received` · `executed` · `effective` ·
`settled` · `as_of` · `filed`

with the rule that the **filename stamp is whichever kind the document's own
class makes canonical** — `executed` for a signed instrument, `as_of` for a cap
table, `authored` for a paper — and every other kind is retained alongside it
rather than discarded.

---

## Part 2 — The time-series analyst

### T1 — Annual rows are stamped H1

**Status: fixed** — annual grain now nulls `year_half`/`half_id`/`half` in both `columns_for` and `_DROP_BY_GRAIN`. Verified on the Unnatural Products re-run.

**Severity: High.** `src/agents/timeseries/timeline.py:155-158`,
`src/agents/timeseries/analyst.py:57-62`

At annual grain `columns_for` nulls `date`, `year_month`, `month`, `day`,
`year_quarter`, `quarter_id`, `quarter`, `timeframe_id` — and leaves `year_half`,
`half_id`, `half` populated. `_DROP_BY_GRAIN["annual"]` omits them too. A half is
finer than a year, so a full-year row claims to be first-half.

Live output, Unnatural Products historical income statement:

```
year_count  year  year_half  half_id  half       value  basis
         1  2018    2018-H1   2018H1    H1    10000.00  actual
         3  2020    2020-H1   2020H1    H1   477777.76  actual
```

Group a concatenated frame by `half` and every full-year figure lands in H1.

The existing test `test_coarse_grains_do_not_invent_finer_columns`
(`tests/test_dataroom_extraction.py:594`) asserts only `month` and `date`. The bug
sits precisely in its blind spot, which is why 75 tests pass over it.

**Fix.** Null the three half columns at annual grain in both places, and extend
the test to assert on every column coarser-than-grain.

### T2 — Density is specified, half-built, and never invoked

**Status: fixed** — `_write_series` densifies against `Timeline.range_for`; `quarter_range` and `year_range` added. Verified on the Unnatural Products re-run.

**Severity: High.** `timeline.py:183-199`, `analyst.py:_write_series`

The spec calls this load-bearing: *"A missing row is a wrong answer."*
`Timeline.month_range()` exists, is documented as the mechanism, and says
*"Callers fill the missing ones with null values and `is_gap_fill`."*
`_write_series` never calls it. There is no `quarter_range` or `year_range` at all.

Consequences: `is_gap_fill` is `False` on all 11,919 rows ever written, the
README's Gaps column can only ever print 0, and `pct_change(12)` — the spec's
entire justification for `month_count` — is unsafe on the output.

Live evidence, `UNP Deals.xlsx` at annual grain: `year_count` runs 4, 6, 7, 8.
Year 5 (2022) has no row. A one-period lag across that file compares 2021 to 2023
as though adjacent.

The Unnatural Products monthly grids happened to be dense — because the source
workbooks are dense, not because anything enforced it.

**Fix.** Densify in `_write_series` against the grain's own range; add
`quarter_range` and `year_range`.

### T3 — Roll-up is unimplemented — **WITHDRAWN**

**Status: withdrawn** — this was never a defect in the code. It was a defect in
the spec.

The original spec's §"Roll up, never down" required the transcriber to aggregate
monthly figures into the quarterly and annual grids. It was implemented, verified
against the source, and then removed, because roll-up produces a number no
document states and a derived row in a transcription cannot be distinguished from
a transcribed one — which destroys the provenance breadcrumb the whole artifact
exists to preserve.

Roll-up now belongs to the `data-analyst_agent`, which reads these files and
writes to its own directory. `Company-Timeline-And-Month-Indexed-Time-Series.md`
v0.0.0.2 states the division of labour; `is_rolled_up` and
`declare_metric_kind()` are gone from the contract and the code.

### T4 — An undefined `daily` grain swallows every as-of-dated document

**Status: fixed** — `grid_grain()` maps daily onto the monthly grid; the stated day survives in `date`, `day`, `source_raw_period`. Verified on the Unnatural Products re-run.

**Severity: Medium.** `analyst.py:57` (`_DROP_BY_GRAIN`), `periods.py`

The spec defines three grids: monthly, quarterly, annual. `parse_period` also
produces `daily`, which has no `_DROP_BY_GRAIN` entry and no place in the design.

Live: the cap table as-of `9/29/2024` became
`…detailed-cap--By-Holder-SecurityClass--Daily.csv`. All 112 rows share **one**
`timeframe_id` — `timeframe_id` is composed from `month_count`, so at daily grain
it is constant within a month, against the spec's "unique per period."

**Fix.** Collapse `daily` to `monthly` on write, preserving the stated day in
`source_raw_period` and `date`. A cap table as-of a date is a monthly-grid
observation with a precise `date`, not its own grid.

### T5 — `document_source` is plural; the analyst assumes singular

**Severity: High.** `analyst.py:_write_series` grouping key; extractor side

Extractors emit comma-joined lists. The fresh CogSciAI traction record:

```
"20240910_CogSciAI_Deck--Seed.pdf, 20240913_CogSciAI_ReadingDeck--Updated--Seed.pdf"
```

That string is the file-grouping key. Two decks silently merge into one CSV,
defeating *"one file per source, never a merge"* — the rule the spec calls the
whole point — and producing
`00000000_CogSciAI_20240910-CogSciAI-Deck--Seed-pdf-2024…--Annual.csv`.

**Fix.** Make `document_source` singular per record at the extractor boundary.

### T6 — Every file is stamped `00000000_`

**Status: fixed** — `declare_source_date()` added; falls back to the filename stamp, then `undated_` — `00000000` is gone. Verified on the Unnatural Products re-run.

**Severity: Medium.** `analyst.py:247` (`_filename`)

The stamp is parsed from the source filename's `YYYYMMDD_` prefix. Unnatural
Products' workbooks are not on the house convention, so **all 8 output files**
came out `00000000_…`. The spec's stated payoff — *"two projection files a year
apart sort beside each other and their divergence is visible from the listing
alone"* — is entirely lost.

The analyst has a hard, undeclared dependency on the rename step, which is what
ties Part 2 back to Part 1.

**Fix.** Fall back to a date the caller supplies with the observations; fail loud
rather than emitting `00000000`.

### T7 — Nothing calls the analyst

**Severity: High.** `src/agents/dataroom/dataroom_analyzer.py:525`

`TimeSeriesAnalyst` has zero callers. Artifacts are numbered `0-dataroom-inventory`
through `6-synthesis-report`; the analyst writes `timeseries/`. The seat is
reserved and empty. Both runs in this session required a hand-written adapter.

**Fix.** Call it as step 7 of `save_dataroom_analysis_artifacts`. The adapter
written for this run is the working reference for that interface.

### T8 — `extract_pdf_tables` also has no callers

**Severity: High.** `src/agents/dataroom/document_text.py:420`

Only **12 spreadsheets exist across ~5,350 files in `io/`**; 7 of them are
Humain's. The numbers in this corpus live overwhelmingly in decks and PDFs. A
spreadsheet-fed time-series agent will be idle across nearly the whole portfolio
however well it works, and the function that would fix that is written and unused.

Probably the highest-leverage item in this document, and the one least about a bug.

### T9 — Metric names change across a seam, and nothing warns

**Status: fixed** — README lists per-grain metrics unique to a file, with a `shared` count so a real divergence is distinguishable from an unrelated subject. Verified on the Unnatural Products re-run.

**Severity: Low.** README generation, `analyst.py:_write_readme`

The historical sheet says `Total Revenue`; the forecast says `Revenue`. That is
*correct* — metrics are named as the source names them, never renamed. But a
reader filtering `metric == 'Revenue'` on the concatenated frame silently gets
only the projection half.

**Fix.** Have the README list metric names that appear in some files and not
others. The information is already in hand at write time.

---

## Suggested order

1. **D1, D2** — stop mislabelling, stop discarding. Cheap, and everything else
   depends on the archive being honest about what its dates mean.
2. **D7, D3** — settle the kind vocabulary, then decide where kind and confidence
   live so a downstream reader can recover them.
3. **D8** — key legal terms by instrument rather than by company. Currently
   misreports exposure and burns the review signal on a non-issue.
4. **D5, D6** — validate against the CogSciAI Fund I / SPV pair. That two-vehicle,
   four-document case is the acceptance test for everything above it.
5. **T1** — one-line class of fix, currently producing silent wrong answers.
6. **T7, T5** — wire the analyst in and give it a singular source per record.
7. **T2, T4, T6** — density, the daily grain, the filename stamp.
8. **T8** — PDF table extraction. Largest payoff, largest job.
9. **T3, D4, T9** — roll-up, sibling precision, README warnings.

## Artifacts from the run

Adapters and output are in the session scratchpad, not committed:

- `unp_timeseries.py` — workbook → `Observation` adapter for Unnatural Products.
  The working reference for the T7 interface.
- `run_timeseries.py` — extraction-JSON → `Observation` adapter, with a trace of
  what was dropped and why.
- `run-C-unp/7-timeseries/` — 8 CSVs, `timeline.yaml`, generated README.

Nothing was written into `io/humain/`.

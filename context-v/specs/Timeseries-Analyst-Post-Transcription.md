---
title: "Time-Series Analyst — Post-Transcription"
lede: "The agent that computes. It reads the transcriber's stated-only CSVs and derives — rolling up, cutting fiscal periods, naming its sources."
date_authored_initial_draft: 2026-08-24
date_authored_current_draft: 2026-08-24
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-08-24
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-08-24
date_modified: 2026-08-24
tags: [Time-Series, Data-Analyst, Roll-Up, Fiscal-Periods, Provenance, Derivation, MemoPop]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
status: In-Review
---

# Time-Series Analyst — Post-Transcription

## Why this agent exists separately

`time-series_transcriber` writes what documents state and nothing else. That
constraint is what makes its output trustworthy: every non-gap row points at a
value someone can find in a workbook. The moment it computes, that guarantee is
gone, because a derived row and a transcribed row look identical once written.

But the computations are still needed. A monthly operating model has to become a
quarterly view. A fiscal year has to be cut. Two disagreeing sources have to be
weighed. This agent does all of it, in a separate pass, writing to a separate
directory, with every derived value carrying a pointer back to the rows that
produced it.

**The split is the design.** Not a phasing decision to be collapsed later.

| | `time-series_transcriber` | `time-series_analyst` (this spec) |
|---|---|---|
| Reads | Source workbooks, decks, PDFs | Transcriptions only |
| Writes | `_source-transcriptions/<Company>/timeseries/` | `_analysis/<Company>/` |
| Computes | Nothing | Roll-ups, fiscal periods, derived metrics, reconciliations |
| Provenance unit | `source_document` + `source_detail` | `derived_from` — the transcription rows consumed |

**This agent never edits a transcription.** Not to fix a typo, not to add a
column, not to fill a gap. A transcription is corrected by re-running the
transcriber against a corrected source.

## Input contract

Everything under `_source-transcriptions/<Company>/`:

- `timeline.yaml` — the company origin, its basis, its confidence, and the
  alternatives considered. **The analyst adopts this origin. It does not
  re-derive one.** Two artifacts indexing from different origins cannot be joined,
  which defeats the exercise.
- `timeseries/*.csv` — one file per source document per grid per dimension shape.
- `timeseries/README.md` — gap counts, undated sources, and the per-grain list of
  metric labels that appear in some files and not others.

The column contract is specified in
`context-v/specs/Company-Timeline-And-Month-Indexed-Time-Series.md` v0.0.0.2.
Two properties matter here:

1. **Counts and date parts are zero-padded strings.** `month_count` is `"01"`,
   `MM` is `"01"`. Sort and compare on `int(...)`, never lexically — `"100"`
   precedes `"99"` as a string.
2. **Each grid is dense from count `01`.** A period no source described is
   present as a row with `is_gap_fill: true` and a null `value`. Those rows are
   what make lag operators index arithmetic; they are **not** observations and
   must be excluded from every aggregation.

## Roll-up

**Roll up, never down.** Monthly may be aggregated into quarterly and annual.
Splitting a quarterly figure across three months is forbidden — it invents a
seasonality the company never reported, and once written it is indistinguishable
from data.

### `declare_metric_kind(metric, kind)`

Roll-up is **off for every metric** until a caller declares it:

```python
analyst.declare_metric_kind("Total Revenue", "flow")    # sums
analyst.declare_metric_kind("Cash", "stock")            # carries
```

`kind` is `"flow"` or `"stock"`; anything else raises `ValueError`.

**Whether a series sums or carries is a fact about the account, not something to
be read off its name.** In the Unnatural Products operating model, `Cash` and
`Net Change in Cash` sit in the same sheet and behave oppositely — one is a
balance, one is a period movement. `Accounts Payable` and `Accounts Payable
Balance` sit next to each other. A model asked to classify these will be
confident and sometimes wrong, and the error is silent.

So the declaration comes from a person, or from a registry a person maintains —
the same discipline as the label registry in
`context-v/reminders/Normalize-Labels-Gradually.md`. **An undeclared metric is
simply not rolled up.** That is a correct outcome, not a gap.

### `_roll_up()` — the three rules

```
for each (source_document, metric, dimensions) with monthly rows:
    kind = declared kind, else skip
    for target in (quarterly, annual):
        if the source already stated this metric at this grain:  skip
        bucket the monthly rows by target period
        for each bucket:
            if months present != 3 (quarterly) or 12 (annual):    skip
            if the bucket spans more than one basis:               skip
            if any value is null or is_gap_fill:                   skip
            flow  -> sum(values)
            stock -> value of the latest month in the bucket
            emit with is_rolled_up = true
```

**1. Complete periods only.** A three-month sum built from two months is not a
quarter. An eleven-month year is not a year. Incomplete buckets are skipped
silently — the absence of a rolled row is itself the statement that the period
was not fully reported.

**2. Never blend bases.** A bucket containing both `actual` and `projection` rows
produces nothing. Six actual months and six projected ones do not make a year;
the result would be neither history nor forecast, and plotting it as either is the
worst failure available to this system.

Note the asymmetry this produces, and that it is correct: a year split at Q2/Q3
between actuals and projections yields **four rolled quarters** — each internally
uniform — and **no rolled year**.

**3. Never into a grain the source already stated.** A document that reported its
own `Full Year` column has spoken. Emitting a derived annual row beside it would
create two values for one period from one document, inviting exactly the
reconciliation this system refuses to do implicitly. If the two disagree, that is
a finding for the reconciliation pass below — not something to paper over by
preferring the derived one.

### Worked examples

Verified against the Unnatural Products operating model:

| Case | Input | Output |
|---|---|---|
| Flow, complete | 2022-Q4 `Total Revenue`, three monthly rows | `188,404.78` — the exact sum |
| Stock, complete | 2023-Q2 `Cash`, three monthly rows | `9,963,415.53` — the period-end month. Summing would have produced `21,032,762.28`, a number meaning nothing |
| Grain already stated | monthly rows + the sheet's own `Full Year` column | no rolled annual row at all |
| Mixed basis | six `actual` months, six `projection` months | four rolled quarters, no rolled year |

## The derived-row contract

Analyst output uses the transcription column contract **plus** derivation
provenance, so the two can be concatenated and told apart:

| Column | Type | Example | Notes |
|---|---|---|---|
| `is_rolled_up` | bool | `true` | True on any row this agent computed rather than read. False on a row passed through from a transcription |
| `derived_from` | str | `20230511_…HistIS--Monthly.csv#2022-10,2022-11,2022-12` | The file and the periods consumed. A derived value a reader cannot reconstruct is not auditable |
| `derivation` | str | `sum of 3 monthly rows (flow)` | Human-readable statement of what was done |

`Observation.is_rolled_up` defaults to `False` and is set only by `_roll_up()`.

**`is_rolled_up` is not sufficient on its own.** A bool says a row was computed;
it does not say from what. `derived_from` is what lets a partner ask "where did
this quarter come from" and get an answer without re-running anything. This is
the breadcrumb the transcriber protects by refusing to compute at all, and the
analyst preserves by naming its inputs.

## Fiscal periods

The transcriber writes one fiscal column, **`FM`** — the month's ordinal position
within the fiscal year, zero-padded, null when the fiscal year is the calendar
year. It writes no fiscal quarter and no fiscal year, deliberately: those are
cuts, and cutting is analysis.

Everything else follows from `FM`:

```
fiscal_quarter_number = ceil(int(FM) / 3)            # 01–03 -> 1, 04–06 -> 2, …
fiscal_year           = int(YYYY) + (1 if int(MM) >= fiscal_year_start_month else 0)
```

A fiscal year is named for the calendar year it **ends** in, which is the common
convention and the one that surprises people: with an April start, April 2024
opens fiscal 2025.

| `date` | `MM` | `FM` | Fiscal quarter | Fiscal year |
|---|---|---|---|---|
| `2024-04-01` | `04` | `01` | Q1 | FY2025 |
| `2024-12-01` | `12` | `09` | Q3 | FY2025 |
| `2025-03-01` | `03` | `12` | Q4 | FY2025 |

Emit `fiscal_quarter` as `FY2025-Q1` when writing it as a column. `FM` is null
whenever `fiscal_year_start_month` is null or unestablished, and every fiscal
derivation is null with it — never defaulted to a calendar year, which would
silently mislabel every period.

**Fiscal roll-ups use the fiscal bucket, not the calendar one**, and the two live
in separate output files. A fiscal Q1 that spans April–June is a different bucket
from calendar Q1, and merging them is a category error.

## The rest of the analyst's job

Roll-up is the first capability, not the whole agent. The transcription spec's
division of labour assigns all of the following here. Each deserves its own
section as it is built; listed now so the boundary stays visible.

| Capability | Note |
|---|---|
| **Reconciliation** | Two documents stating different values for one period. The divergence is a finding; the analyst surfaces and weights it, and records which it used and why. It never silently averages or prefers |
| **Label clustering** | Applying the human-maintained registry from `Normalize-Labels-Gradually.md` so `Total Revenue` and `Revenue` can be read as one series. Applied as a `canonical_metric` column **alongside** `metric`, never replacing it. Only `status: settled` clusters are applied |
| **Gap policy** | Deciding whether a gap is interpolated, carried forward, or left null — per metric, per chart, recorded |
| **Derived metrics** | Growth, margin, burn, runway, IRR. Each names the stated date it keys on, since that choice is itself a judgment (see `Round-Closing-Timeline-Nuances.md` §2) |
| **Currency** | Translation with a stated rate and rate source, per row |

## Output

```
io/<firm>/portfolio/_analysis/<Company>/
├── 7-timeseries-analysis/
│   ├── <Company>--Rolled-Up--Quarterly.csv
│   ├── <Company>--Rolled-Up--Annual.csv
│   ├── <Company>--Rolled-Up--Fiscal-Quarterly.csv
│   └── README.md
└── analysis-manifest.yaml
```

`analysis-manifest.yaml` records what the run was told, so a result can be
reproduced and a disagreement can be traced to an input rather than to the agent:

```yaml
company: Unnatural Products
origin: 2018-01                       # adopted from timeline.yaml, never re-derived
transcription_source: _source-transcriptions/Unnatural-Products/timeseries/
fiscal_year_start_month: null
metric_kinds:
  Total Revenue: flow
  Cash: stock
label_clusters_applied: []            # settled clusters only
skipped:
  - {metric: "Total Operating Expenses", reason: "no kind declared"}
  - {metric: "Revenue", period: "2023", reason: "bucket spans actual and projection"}
  - {metric: "Total Revenue", period: "2022", reason: "grain stated by the source"}
generated_by: time-series_analyst
generated_on: 2026-08-24
```

**`skipped` is not an error log.** Every entry is a place the agent declined to
compute, which is the behaviour this spec is mostly about. A run with a long
`skipped` list and few derived rows has probably done its job correctly.

## Open questions

1. **Where do metric kinds live long-term?** Per-run declarations do not
   accumulate. A per-company `metric-kinds.yaml` beside the transcriptions is the
   obvious home, but it is arguably firm knowledge rather than company data.
2. **Cross-source roll-up.** Roll-up is currently scoped to one source document,
   preserving the one-file-per-source rule. Rolling across sources would require
   reconciliation first, which is a later capability.
3. **Dimensioned roll-up.** Summing `shares` across `security_class` for one
   holder is arithmetic on a dimension rather than on time. Probably legitimate,
   probably needs its own rules.
4. **Does the analyst emit gap rows?** Derived grids inherit density from their
   inputs, but a quarter skipped for incompleteness leaves a hole a lag operator
   will trip on.

## Related

- `context-v/specs/Company-Timeline-And-Month-Indexed-Time-Series.md` — the transcription contract this reads
- `context-v/reminders/Normalize-Labels-Gradually.md` — the label registry, and who is allowed to author it
- `context-v/reminders/Round-Closing-Timeline-Nuances.md` — why the choice of stated date is a judgment, and the `anomalies.json` pressure valve
- `context-v/issue-resolution/Archive-Dating-And-Time-Series-Defect-Hitlist.md` — T3, withdrawn from the transcriber and landing here

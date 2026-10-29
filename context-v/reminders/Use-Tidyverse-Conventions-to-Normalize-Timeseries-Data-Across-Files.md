---
title: "Use Tidyverse Conventions to Normalize Timeseries Data Across Files"
lede: "Timeseries collected from many documents is tidy data, not a finance workbook. Long over wide, one table per observational unit, one file per source, and a count index from a company-wide origin that makes any metric matchable to any other."
date_authored_initial_draft: 2026-08-23
date_authored_current_draft: 2026-08-23
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Reference
date_created: 2026-08-23
date_modified: 2026-08-23
tags: [Tidy-Data, Timeseries, KPI-Extraction, Financials, Cap-Table, Data-Normalization, Reminder]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
status: Active
---

# Use Tidyverse Conventions to Normalize Timeseries Data Across Files

**Load this before writing any agent that emits numbers over time** — financials,
KPIs, cap tables, traction, projections — or before writing code that reads them.
The full contract is
[[specs/Company-Timeline-And-Month-Indexed-Time-Series]]; this is the rule set.

## The frame

Numbers pulled out of a company's documents are **collected data, not a model**.
The instinct in venture and private equity is an operating workbook: months
across the top, one authoritative sheet, everything reconciled. That target is
wrong for this and produces a structure nothing else can join to.

The standard is Hadley Wickham's tidy data (*Journal of Statistical Software*,
2014):

1. Each variable forms a column.
2. Each observation forms a row.
3. Each type of observational unit forms a table.

## The rules

### 1. Long, not wide — because the metric set is open

Emit one row per observation, with `metric` and `value` as columns.

```
month_count  year_month  metric     value   basis
         12     2024-01  revenue   125000   actual
         12     2024-01  headcount     14   actual
```

**Be precise about why.** "Tidy" does not mean "long" — that conflation is easy
and wrong. Wickham's rule is that each *variable* gets a column, and for a fixed,
known metric set, `revenue` and `headcount` genuinely are separate variables, so
wide is the tidy shape. `analysis/private-data/timeframe-KPIs.csv` is wide and
correct for what it does.

Long is right in *this* setting because the metric set is **open**: every
document reports whatever it reports, names are not canonical, and new documents
arrive continuously. When the variables are not known in advance, `metric` is the
variable. A wide file built from an open metric set puts source-specific
vocabulary in the header row — Wickham's messy-data problem #1, *column headers
are values rather than variable names*.

Wide is one line away when a chart or a human wants it:

```python
df.pivot(index=["month_count", "year_month"], columns="metric", values="value")
```

### 2. ISO 8601 always — parse the source's format, never propagate it

Dates are written `2023-02`. Never `Feb-23`, `Feb 2023`, `2/23`, `23-Feb`, or
`FY23-M02`.

Source documents use every one of those. A spreadsheet header reads `Feb-23`, a
deck axis reads `Q1'24`, a board pack reads `2/1/2023`. **Parse them and discard
the form.** The source's spelling is not data; the period is.

This is not tidiness, it is disambiguation. `03-04-2023` is March 4th to an
American and April 3rd to everyone else, and a two-digit year loses the century.
Anything that survives into a written file must already be unambiguous, because
whoever reads it later has no access to the workbook it came from.

The forms that appear in output, and nothing else:

| Column | Form | Example |
|---|---|---|
| `date` | `YYYY-MM-DD` | `2023-02-01` |
| `year_month` | `YYYY-MM` | `2023-02` |
| `year_quarter` | `YYYY-Qn` | `2023-Q1` |
| `year_half` | `YYYY-Hn` | `2023-H1` |
| `year` | `YYYY` | `2023` |
| `month` / `day` | integer | `2` / `1` |

`quarter_id` and `half_id` keep their compact prior-art spelling — `2023Q1`,
`2023H1` — because existing files join on them. Those are the only exceptions,
and they are still unambiguous.

**Zero-pad everything with a fixed width.** `2023-02`, not `2023-2`. `month_count`
`01`, not `1`. Unpadded values sort wrong as strings, which is how month 10 ends
up between month 1 and month 2 in every listing and chart axis.

Record what the source said, once, in `source_detail` — `"column header 'Feb-23'"`
— so a reader can trace the parse without the ambiguous form leaking into a
column anything joins on.

### 3. One table per observational unit — but every table shares the timeline

Not everything is a company-period series.

| Series | Observational unit | Extra dimension columns |
|---|---|---|
| Financials, KPIs, traction | company-period | — |
| **Cap table** | **holder-period** | `holder`, `security_class` |
| Revenue by product | product-period | `product` |
| Headcount by function | function-period | `department` |

Mixing units in one table is messy-data problem #4 and forces null dimension
columns onto every row that has no dimension. Give each its own file.

**Separate table, same timeline.** This is a storage decision, not a statement
that ownership sits outside the company's history. Every table carries the same
`month_count` from the same origin, so a cap table maps onto the financials and
the KPIs by joining on the count — which is the whole point of having the count.

**Cap tables are sparse by nature and continuous in meaning.** Ownership changes
at financing events, every six to thirty-six months, so the file holds a row only
at the months an event is evidenced — three or four rows across a company's
history, not one per month. But ownership *between* events is not unknown; it is
unchanged. It is a stock metric, a step function.

So the file records events, and analysis forward-fills to get a continuous
series:

```python
cap.sort("month_count").group_by("holder").fill_null(strategy="forward")
```

Do the fill in analysis, never on write. A forward-filled row on disk is
indistinguishable from a stated one, and it would assert an ownership percentage
for a month no document covers. Sparse on disk, continuous when asked for.

### 4. One file per source document, never a merge

A restatement is a **new file**, not an edit. A revised projection does not
overwrite last year's — it sits beside it, named for the document that stated it:

```
20240115_Company_Financials--Projections--Monthly.csv
20250203_Company_Financials--Projections--Monthly.csv
```

`YYYYMMDD_Company_Thing--Qualifier`, where the date is **the document's date, not
the data's range**. `Actuals` versus `Projections` is the qualifier that must
never be lost — plotting a projection as history is the worst failure available.

This looks like messy-data problem #5, *one observational unit spread across
tables*, and Wickham's fix for it is already in the schema: every file carries
identical columns including `source_document`, so the union is a `concat`.
Splitting on disk buys immutability and provenance; a file is what one document
said and is never edited.

### 5. Juxtapose. Do not reconcile.

When two documents disagree about the same month, **show both**. No averaging, no
choosing a winner, no reconciliation logic anywhere in the pipeline.

```python
both[both.metric == "revenue"].pivot(index="month_count",
                                     columns="source_document", values="value")
```

```
source_document   20240115_Financials--Projections   20250203_Financials--Actuals
month_count
12                                          125000                         118000
13                                          141000                         152000
```

The divergence is the finding. This is not accounting; nothing has to tie out.

### 6. Do not normalize metric names on write

One source says `ARR`, another `Annual Recurring Revenue`, a third `Recurring
Rev`. Record each as its source states it. Mapping them together is a judgment
that belongs in analysis, where it is visible and revisable — not in collection,
where it silently merges two things that may not be the same measure.

### 7. The count index comes from the company, never the document

`month_count` `01` is the earliest month the archive can evidence **for the
company**. Every source is indexed onto that origin regardless of where the
source itself begins. With a February 2023 origin, a spreadsheet starting January
2024 lands at `month_count` **12**, not `01`.

This is the whole mechanism. Two spreadsheets covering different spans, a deck's
chart, and a board pack's KPI table all describe the same company at the same
offsets, so they match on the count rather than being reconciled by hand.

Counts are **zero-padded** — `01`, not `1`. Parallel grids by native periodicity:
`month_count`, `quarter_count`, `year_count`, all from the same origin. Roll up
from finer to coarser; **never** split a quarterly figure into months, which
invents a seasonality nobody reported.

### 8. Gaps are rows, not absences

A period with no data gets a row with a null value and `is_gap_fill: true`. Never
a skipped row.

Lag operators are index arithmetic — `pct_change(12)` means "the row twelve
above". One skipped month shifts every comparison after it and the result still
looks plausible. A visible null is a known gap; a missing row is a wrong answer.

## The tell

If you are about to write a column per metric, ask whether you know the full
metric set in advance and whether it will still be complete after the next
document arrives. If not, you want `metric` and `value`.

If you are about to reconcile two figures into one, stop. Emit both with their
sources and let the reader see the gap.

## Related

- [[specs/Company-Timeline-And-Month-Indexed-Time-Series]] — the full contract:
  column list, origin precedence, fiscal years, output layout
- `analysis/private-data/timeframe-KPIs.csv` — the prior art, and an example of
  the *analysis* shape rather than the storage shape
- `notebooks/derivations/kpi-timeframes.py` — where `pct_change(12)` shows why
  density is load-bearing
- Wickham, H. (2014). "Tidy Data". *Journal of Statistical Software*, 59(10)

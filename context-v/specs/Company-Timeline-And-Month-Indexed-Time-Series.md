---
title: "Company Timeline and Month-Indexed Time Series"
lede: "A transcription contract. Rewrite each company's series into our columns and our grid, unchanged — and compute nothing."
date_authored_initial_draft: 2026-08-23
date_authored_current_draft: 2026-08-24
date_authored_final_draft: null
date_first_published: 2026-08-24
date_last_updated: 2026-08-24
at_semantic_version: 0.0.0.2
usage_index: 2
publish: false
category: Specification
date_created: 2026-08-23
date_modified: 2026-08-24
tags: [Time-Series, Transcription, KPI-Extraction, Financials, Cap-Table, Company-Timeline, Month-Index, MemoPop]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
status: Partially-Shipped
---

# Company Timeline and Month-Indexed Time Series

## This agent transcribes. It does not analyze.

**The only two things this agent does are observe and reformat.** It reads what a
document states and rewrites it — unchanged — into our column layout, on our
grid, with our date scaffolding. Same numbers, same periods, same labels the
company used.

**It performs no arithmetic.** Not a sum, not an average, not a period-end pick,
not a growth rate, not a fill, not a conversion, not a currency translation.

This is stated first, and this bluntly, because the failure it prevents already
happened: a first implementation rolled monthly figures into quarterly and annual
grids, correctly by its own logic, and in doing so put derived numbers into files
whose entire value is that every number in them can be pointed at in a source
document. A derived number in a transcription is indistinguishable from a
transcribed one the moment it is written.

### The division of labour

| Role | Does | Does not |
|---|---|---|
| **Transcriber** (this spec) | Read stated values; write them to the matching grid with full date scaffolding, provenance, and the source's own labels | Any calculation. Any renaming. Any reconciliation. Any judgment about what a number means |
| **`data-analyst_agent`** (not yet built) | Roll monthly into quarterly and annual. Cluster synonymous labels. Reconcile disagreeing sources. Derive growth, margin, runway, IRR. Choose which of several stated dates a calculation should key on | Edit a transcription |

The redundant date columns below exist **so the analyst can do that work** — they
are scaffolding handed forward, not results computed here.

> **Naming.** Settled 2026-08-24. The implementation signs its output
> `time-series_transcriber` (`AGENT_SIGNATURE` in
> `src/agents/timeseries/transcriber.py`). The prior name `time-series_analyst`
> now belongs to the separate agent specified in
> `context-v/specs/Timeseries-Analyst-Post-Transcription.md`.

## The shape

Extractors — financials, KPIs, cap table, chart readings — emit series about the
same company over the same period, from documents that disagree about spans,
grains, and sometimes about the numbers themselves. Unless they share a grid,
nothing can be matched, and every memo re-derives the same arithmetic differently.

The prior art is `analysis/private-data/timeframe-KPIs.csv`:

```
month_count,timeframe_id,half,half_id,quarter,quarter_id,year,month,<metrics…>
1,2017-H1-Q1-1,H1,2017H1,Q1,2017Q1,2017,1,…
2,2017-H1-Q1-2,H1,2017H1,Q1,2017Q1,2017,2,…
```

**Why the redundancy is deliberate.** Every one of those columns is derivable
from the others, and each exists because something downstream wants it as a
column rather than an expression. `half_id` groups a chart axis; `quarter_id`
joins to quarterly financials; `YYYY` and `MM` sort and filter in a spreadsheet
without parsing; `timeframe_id` labels a row uniquely in prose. A reader with a
CSV and no code can do all of it — and so can an analyst agent, without asking
the transcriber for anything.

**Why the count is the load-bearing column.** It turns period arithmetic into
index arithmetic, and it is the join key across documents that share nothing else.
`notebooks/derivations/kpi-timeframes.py` computes year-on-year growth as
`pct_change(12)` — literally "compare to the row twelve above". That is correct
only when row *N−12* is exactly twelve months earlier, which is what the density
rule below protects.

## Tidy data is the standard

The instinct in this domain is a PE/VC operating model: one workbook, months
across the top, everything reconciled into a single authoritative sheet. That is
the wrong target. What this produces is a **collection layer** — and the standard
for one is Wickham's tidy data (*Journal of Statistical Software*, 2014):

1. Each variable forms a column.
2. Each observation forms a row.
3. Each type of observational unit forms a table.

### Long is right here — but "tidy" does not mean "long"

Tidy and long are routinely conflated. Wickham's rule is that each *variable*
gets a column, and whether that produces a long or wide table depends entirely on
what counts as a variable.

If a company reports a fixed, known set of metrics, then `revenue` and
`headcount` **are** separate variables and a wide table is the tidy one — that is
exactly what `timeframe-KPIs.csv` is, and it is correctly shaped for what it does.

Our case is different, and that difference is the justification:

- The metric set is **open**. Each document reports whatever it reports; a deck
  chart, a board KPI table, and an operating model share almost no column names.
- Metric names are **not canonical**. One source says `ARR`, another `Annual
  Recurring Revenue`.
- New documents arrive continuously and must not force a schema migration.

When the set of variables is not known in advance, `metric` is itself the
variable and `value` is the observation. That is honest modeling of what we have,
not a stylistic preference — and it is also Wickham's own fix for messy-data
problem #1, *column headers are values rather than variable names*.

```
month_count  date        metric     value   basis
         12  2024-01-01  revenue   125000   actual
         12  2024-01-01  headcount     14   actual
```

Pivoting to the wide, analysis-ready shape is one line, and reproduces the prior
art exactly:

```python
df.pivot(index=["month_count", "date"], columns="metric", values="value")
```

**So `timeframe-KPIs.csv` is an analysis output, not a storage format.**

### One table per observational unit — which the cap table is not

Rule 3 changes the design rather than the format. Different observational units
belong in different tables, and these series do not share one:

| Series | Observational unit | Dimension columns beyond time |
|---|---|---|
| Financials | company-period | — |
| KPIs | company-period | — |
| **Cap table** | **holder-period** | `holder`, `security_class` |

A cap table is not a company-period series with more metrics; it is a
holder-period series. Putting it in the same table as revenue would be Wickham's
messy-data problem #4, *multiple types of observational unit in one table*. It
gets its own file with its own dimensions, joined on the count when needed.

Any series with a dimension — revenue by product, headcount by department —
takes the same treatment.

### Files split by source, and why that is not a violation

Wickham's messy-data problem #5 is *a single observational unit spread across
multiple tables*, and his fix is to combine them with a column identifying the
source. Writing one file per source document looks like that problem.

It is not, because the fix is already built in: every file carries the identical
schema including `source_document` and `basis`, so the union is a `concat` with
nothing to reconcile. Splitting on disk buys immutability and provenance — a file
is what one document said, and is never edited.

That is also what makes **juxtaposition** free:

```python
both[both.metric == "revenue"].pivot(index="month_count", columns="source_document", values="value")
```

```
source_document   20240115_Financials--Projections   20250203_Financials--Actuals
month_count
12                                          125000                         118000
13                                          141000                         152000
```

No reconciliation logic anywhere. The divergence is the finding; averaging it or
picking a winner is analyst work, done downstream, visibly.

## The column contract

Every emitted CSV is long. **Date scaffolding first, then the observation, then
provenance.** Every column below appears in every file at that grain, whether or
not the source needed it — the duplication is the point, because it is what lets
an analyst roll up, filter, and normalize without reopening the source.

### Date scaffolding

| Column | Type | Example | Notes |
|---|---|---|---|
| `month_count` | str | `01` | Zero-padded, min 2 digits. From the **company** origin, never the source's own start |
| `quarter_count` | str | `01` | Quarterly grid only |
| `year_count` | str | `01` | Annual grid only |
| `date` | str | `2024-01-01` | **Always `YYYY-MM-DD`.** First of the period unless the source stated a day |
| `YYYY` | str | `2024` | Four digits |
| `HH` | str | `H1` | Half. `H1` \| `H2` |
| `QQ` | str | `Q1` | Quarter. `Q1`–`Q4` |
| `MM` | str | `01` | **Zero-padded.** January is `01`, never `1` |
| `DD` | str | `01` | **Zero-padded.** First of the period unless the source stated a day |
| `FM` | str | `10` | Fiscal month, zero-padded `01`–`12`. Month's position within the fiscal year. Null when the fiscal year is the calendar year |
| `year_month` | str | `2024-01` | Composite, kept joinable |
| `year_quarter` | str | `2024-Q1` | Composite, kept joinable |
| `year_half` | str | `2024-H1` | Composite, kept joinable |
| `quarter_id` | str | `2024Q1` | Prior-art spelling |
| `half_id` | str | `2024H1` | Prior-art spelling |
| `timeframe_id` | str | `2024-H1-Q1-12` | Composite, unique per period |

### The observation

| Column | Type | Example | Notes |
|---|---|---|---|
| `metric` | str | `Total Revenue` | Named as the **source** names it. Never renamed — see `context-v/reminders/Normalize-Labels-Gradually.md` |
| `value` | float | `125000` | Exactly as stated. Never converted, scaled, or rounded |
| `unit` | str | `USD` | As stated. Blank when the source does not say — never inferred |
| `basis` | str | `actual` | `actual` \| `projection` \| `restated` \| `chart_read`. Never lost — plotting a projection as history is the worst failure available here |

### Provenance

| Column | Type | Example | Notes |
|---|---|---|---|
| `is_gap_fill` | bool | `false` | True on a scaffolding row that states nothing — see Density |
| `source_document` | str | `20240115_…xlsx` | Exactly one document. Never a list |
| `source_detail` | str | `Sheet 'P&L', row 14` | Where in the document |
| `source_raw_period` | str | `Jan-24` | The period string as the document wrote it |

**There is no `is_rolled_up` column.** Nothing in a transcription is rolled up.
When the analyst produces derived rows they belong in the analyst's own output,
which is a different artifact in a different directory.

### Dimensions

Series with a dimension add it immediately before `metric`:

| Column | Example |
|---|---|
| `holder` | `Keystone Ventures Fund I, LP` |
| `security_class` | `Series A Preferred` |

## Zero-padding is not cosmetic

**Every count and every date part is zero-padded to its natural width and written
as a string.** `01`, never `1`.

- `month_count`, `quarter_count`, `year_count` — minimum two digits
- `MM`, `DD`, `FM` — exactly two digits

Unpadded values sort lexically as `1, 10, 11, 12, 2, 3` in every spreadsheet,
every `sort`, every naive join, and every text-mode read. A single unpadded column
silently reorders a series, and the resulting chart looks fine. This has cost real
time before; it is a hard rule.

## Month 01

**Month 01 is the earliest month the archive can evidence for this company,
whatever document that comes from.** If the deepest thing anyone has is a
spreadsheet beginning February 2023, February 2023 is month `01`.

**The origin belongs to the company, not to the document.** A chart that starts
January 2024 does not restart the count — with a February 2023 origin, January
2024 is `month_count` **12**:

```
2023-02   month_count=01   ← origin
2023-12   month_count=11
2024-01   month_count=12   ← a source that begins here still lands on 12
2025-04   month_count=27
```

Getting that right is what makes every metric joinable.

### Establishing the origin

Take the earliest month evidenced anywhere, then check whether an earlier one is
*provable* and revise:

1. Scan every extracted series and take the earliest period any of them state.
2. If a charter, a deck, or an instrument evidences the company existed earlier,
   move the origin back to that month. A company incorporated in April 2019 whose
   earliest data is 2023 has an origin of 2019-04, and 2023 lands at `month_count`
   46 — itself informative, because it says three and a half years are undocumented.
3. Record which of the two produced the origin.

Choosing the earliest of several stated dates is selection, not calculation: no
new number is produced, and the alternatives are all recorded.

**One origin per company, applied to every grid.**

### Recording the origin

`timeline.yaml`, beside the series:

```yaml
company: MeridianAI
origin: 2023-02
origin_basis: earliest_data_point
origin_confidence: medium
origin_evidence:
  source_document: 20240115_MeridianAI_OperatingModel--SeriesA.xlsx
  detail: "Revenue sheet's first column is Feb-2023"
  extracted_by: financial_extractor
earlier_existence_evidenced: null
alternatives_considered:
  - {basis: incorporation, date: null, note: "no charter in the archive"}
  - {basis: first_financing_close, date: 2023-11, source: 20231112_..._SAFE--Signed.pdf}
notes:
  - "Deck claims 'founded 2021'; nothing in the archive evidences activity before 2023-02."
```

## More than one anchor

`month_count` from incorporation answers *how old is this company*. It is the
default and the join key, because every company has exactly one of it and files
that share it can be concatenated.

It is not the only question worth asking. **How long since they launched** is a
different question, and for comparing two companies it is often the better one:
a company incorporated in 2019 that shipped in 2024 and one incorporated and
shipped in 2023 are both "two years post-launch" and are eleven years apart on
incorporation. Which anchor is right depends on the chart, and the chart is not
known when the transcription is written.

So a grid may carry **more than one count column**, each from its own anchor:

| Column | Anchor | Answers |
|---|---|---|
| `month_count` | incorporation (or earliest evidenced existence) | how old the company is |
| `month_count_since_launch` | first public availability of the product | how long it has been in market |
| `month_count_since_revenue` | first dollar collected | how long it has been selling |
| `month_count_since_financing` | first executed financing instrument | how long the current capital has been at work |

`quarter_count_*` and `year_count_*` follow the same pattern at their own grains.

### The rules that keep this honest

1. **A column appears only when its anchor is evidenced.** No launch date in the
   archive means no `month_count_since_launch` column — not a column of nulls,
   and never a guessed date. An absent column says "we do not know when they
   launched", which is true and useful; a column full of nulls says the same
   thing while looking like a failure to compute.
2. **Every anchor is evidenced the same way the origin is** — a document states
   it, and the document is recorded. An anchor asserted from the deal config
   (see `incorporation_date` below) counts as evidenced by the operator, and is
   recorded as such.
3. **`month_count` is always present and always the company origin.** The other
   columns are additive. Changing which anchor `month_count` uses would break
   joins across every file ever written for that company.
4. **Counts before an anchor are negative, not clipped.** A revenue figure from
   before first launch is `month_count_since_launch = -3`. Clipping it to zero
   or dropping the row would hide a real observation for the sake of a tidy
   column.
5. **Choosing among anchors is the analyst's.** The transcriber writes every
   column it can evidence and expresses no view about which one a chart should
   use.

### Recording them

`timeline.yaml` gains an `anchors` block, each with the same evidence structure
the origin already carries:

```yaml
company: ProfileHealth
origin: 2025-02                        # month_count 01
origin_basis: incorporation
origin_confidence: high

anchors:
  - name: launch
    column_prefix: since_launch
    date: 2026-07
    basis: first_public_availability
    confidence: medium
    source_document: 20260601_ProfileHealth_GoToMarket.pdf
    detail: "'Clinic pilot opens July 2026' on the go-to-market sheet"
  - name: financing
    column_prefix: since_financing
    date: 2025-05
    basis: first_financing_close
    confidence: high
    source_document: Alan Ritchson_SAFE.docx.pdf
    detail: "earliest executed SAFE, 5/7/2025"
```

### Incorporation outranks a period that merely contains it

A company cannot have a period before it existed. An annual figure for the year
of incorporation begins on 1 January and therefore *sorts* earlier than a
February charter — but it is a statement about the year containing incorporation,
not evidence of earlier existence.

So where a coarser period merely **contains** the incorporation date, the charter
wins and the origin is the incorporation month. Where a source genuinely
evidences activity *before* incorporation, earliest still wins, and the
divergence stays visible in `alternatives_considered` — that gap is a diligence
finding, not an error to smooth over.

ProfileHealth is the worked example: `net_income {"2025": …}` parses to annual
2025, whose first day is 2025-01-01, against a charter of 2025-02-24. The origin
is **2025-02**, and the cap table dated 2026-05-12 lands at `month_count` 16.

### Anchors from the deal config

Some anchors are known to the operator and stated nowhere in the archive. The
deal's JSON may carry them, and they are treated as evidenced-by-the-operator
rather than inferred:

```json
{
  "incorporation_date": "2025-02-24",
  "fiscal_year_start_month": 7,
  "launch_date": "2026-07"
}
```


## Fiscal years

A fiscal year is recorded, not applied. Establish the fiscal year start once —
from an audited statement, a tax filing, or a header reading "FY2024 (ending
March 31)" — and record it:

```yaml
fiscal_year_start_month: 4        # April; null means calendar
```

The transcriber does not re-cut quarters or re-label years. It writes a single
column, **`FM`** — the month's ordinal position within the fiscal year, zero-padded
— and leaves every fiscal aggregation to the analyst:

| `date` | `MM` | `FM` with FY starting April |
|---|---|---|
| `2024-04-01` | `04` | `01` |
| `2024-12-01` | `12` | `09` |
| `2025-03-01` | `03` | `12` |

`FM` is null when `fiscal_year_start_month` is null or unknown. One column is
enough: fiscal quarter is `ceil(FM/3)` and fiscal year is derivable from `FM` and
`YYYY`, and both are the analyst's to compute.

## Density: gaps are rows, not absences

**Each grid is dense from count `01` to its last period with data.** A period no
source describes gets a row with `is_gap_fill: true`, null `metric`, and null
`value` — never a skipped row.

This is scaffolding, not inference. **A gap row asserts nothing.** It carries the
date columns for a period and explicitly says no source spoke to it, which is a
different statement from a value.

It exists because `pct_change(12)` and every other lag operator are index
arithmetic; one skipped period silently shifts every comparison after it, and the
result looks plausible. A visible null row is a known gap. A missing row is a
wrong answer.

## Three grids, not one

**Data is written to the grid matching the periodicity it was stated in.** A
quarterly income statement goes to the quarterly CSV. A Q2 2025 figure is a Q2
2025 row, not three interpolated months.

Each grid carries its own count, all from the same origin:

| Grid | Index | Origin at 2023-02 |
|---|---|---|
| `…--Monthly.csv` | `month_count` | 2023-02 = `01`, 2024-01 = `12` |
| `…--Quarterly.csv` | `quarter_count` | 2023-Q1 = `01`, 2025-Q2 = `10` |
| `…--Annual.csv` | `year_count` | 2023 = `01`, 2025 = `03` |

The quarterly and annual grids begin at the period **containing** the origin, so
calendar alignment survives: a February origin sits inside 2023-Q1, and that
quarter is `quarter_count` `01`.

**A daily-dated document is a monthly-grid row.** A cap table as of 2024-09-29 is
one monthly row whose `date` is `2024-09-29` and whose `DD` is `29`. There is no
daily grid.

**A metric appears at exactly the grain its source stated, and at no other.** A
monthly series does not also appear annually. A quarterly figure is not split into
months. Both directions are forbidden, for the same reason: neither is transcription.

## What the analyst does — not the transcriber

Listed so it is unambiguous where each belongs. Every one of these is legitimate
and necessary work; none of it happens here.

| Operation | Why it is not transcription |
|---|---|
| **Roll monthly into quarterly / annual** | Produces a number no document states. Requires knowing whether a series sums or carries — `Cash` and `Net Change in Cash` sit side by side in one workbook and behave oppositely |
| **Fill a gap with an interpolated value** | Invents the observation the gap row exists to declare missing |
| **Reconcile two sources that disagree** | The disagreement is the finding. Collapsing it destroys it |
| **Map `ARR` onto `Annual Recurring Revenue`** | A vocabulary judgment built from many portfolios over time |
| **Convert currency, rescale units, restate** | Produces a number the document did not state |
| **Derive growth, margin, burn, runway, IRR** | Analysis, and the choice of which stated date to key on is itself a judgment |

## Output — one file per source, never a merge

**A restatement is a new file, not an edit.** When a later document revises an
earlier month's revenue, that is a second CSV named for the document that stated
it. Nothing is merged, reconciled, or overwritten.

Transcriptions are **organized by company** and live under
`_source-transcriptions/`, never under `_analysis/` — that directory is for
output an analyst produced, and mixing the two is the role confusion this spec
exists to prevent:

```
io/<firm>/portfolio/_source-transcriptions/<Company>/
├── timeline.yaml                                       ← the origin and its evidence
└── timeseries/
    ├── 20240115_MeridianAI_Financials--Actuals--Monthly.csv
    ├── 20240115_MeridianAI_Financials--Projections--Monthly.csv
    ├── 20250203_MeridianAI_Financials--Projections--Monthly.csv    ← supersedes nothing
    ├── 20250924_MeridianAI_Financials--Actuals--Quarterly.csv
    ├── 20250924_MeridianAI_CapTable--Snapshots--Monthly.csv
    └── README.md
```

> **Settled 2026-08-24.** The directory is `timeseries/`, not `7-timeseries/`.
> The numbered sequence belongs to the dataroom analysis pipeline
> (`0-dataroom-inventory` … `6-synthesis-report`); transcription is not a step in
> it, so the number misled.

Filenames follow the house convention — `YYYYMMDD_Company_Thing--Qualifier` —
where the date is **the document's date, not the data's range**. A document with
no evidenced date is named `undated_…` rather than given a plausible-looking
stamp, and is listed as undated in the README.

Qualifiers that carry meaning: `Actuals` versus `Projections` must never be lost.
`Monthly` / `Quarterly` / `Annual` names the grid.

`README.md` carries what a CSV cannot: which periods are gaps, which documents fed
which file, which sources had no date, and which metric labels appear in some
files of a grain and not others.

No merged file and no `combined.csv`.

## Remaining work (as of 2026-08-24)

The contract is implemented and covered; what is missing is everything that would
let it run without a person driving it, plus the upstream dating it depends on.

### Shipped

- `time-series_transcriber` — renamed from `time-series_analyst`; module
  `src/agents/timeseries/transcriber.py`, class `TimeSeriesTranscriber`
- **Computes nothing.** `_roll_up()`, `declare_metric_kind()`, `is_rolled_up`,
  and `Observation.is_rolled_up` removed from the contract and the code
- Column contract: `date` + `YYYY` / `HH` / `QQ` / `MM` / `DD` / `FM`, plus the
  composite IDs
- Zero-padded counts and date parts, sorted on the integer so `100` cannot
  precede `99`
- Three grids; a daily-dated document is a monthly row keeping its stated `DD`
- Density — every grid dense from count `01`, gaps as `is_gap_fill` rows
- One file per source; `declare_source_date()`, with `undated_…` rather than a
  stamp a document cannot support
- Origin establishment and `timeline.yaml`, including alternatives considered
- `README.md` carrying gaps, undated sources, and per-grain metric asymmetry
- Output at `_source-transcriptions/<Company>/timeseries/`
- 94 passing tests, including regressions for every defect the first run exposed

### Remaining

| Item | Where | Note |
|---|---|---|
| **Nothing calls the transcriber** | `dataroom_analyzer.save_dataroom_analysis_artifacts` | Both runs so far needed a hand-written adapter. Hitlist **T7** |
| **`document_source` is plural upstream** | `src/agents/dataroom/extractors/` | Extractors emit comma-joined lists; that string is the file-grouping key, so two decks silently merge into one file. Hitlist **T5** |
| **PDF tables unreachable** | `document_text.extract_pdf_tables` | Written, zero callers. Only 12 spreadsheets exist across ~5,350 files in `io/`, so most numbers in the corpus are in decks and PDFs. Hitlist **T8** |
| **Upstream dating** | `slides/date_resolution.py`, `slides/archive_rename.py` | Filename dates feed `declare_source_date`'s fallback. A PDF creation timestamp is still asserted as authorship, and the date's *kind* is discarded at the archive boundary. Hitlist **D1–D8** |
| **Exercised on one company** | — | Unnatural Products transcribed cleanly, 11,919 stated rows. CogSciAI produced zero, because its dataroom holds no spreadsheet and no dated instrument the extractors read |

Open questions 1 and 2 below are unresolved and block nothing today.

## Open questions

1. **Pre-origin data.** If a source states a period earlier than the established
   origin, the origin was wrong — move it back and reindex, or admit a negative
   count? Moving it is more correct and invalidates every previously written count.
2. **Currency.** Multi-currency series need a stated reporting currency recorded
   per row. The conversion itself is the analyst's.

## Related

- `context-v/reminders/Normalize-Labels-Gradually.md` — why labels are transcribed, not mapped
- `context-v/reminders/Round-Closing-Timeline-Nuances.md` — why dates are never revised to tidy a sequence
- `context-v/issue-resolution/Archive-Dating-And-Time-Series-Defect-Hitlist.md` — open defects
- `analysis/private-data/timeframe-KPIs.csv` — the prior art this codifies
- `notebooks/derivations/kpi-timeframes.py` — where `pct_change(12)` demonstrates why the grid must be dense
- `context-v/Introducing-a-KPI-Extractor-Agent.md` — the KPI extractor; a producer of these files

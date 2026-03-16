---
title: "Introducing a KPI Extractor Agent"
lede: "A zero-hallucination agent that extracts verifiable KPIs from pitch decks, dataroom documents, and spreadsheets, then cross-references with Perplexity internet search to validate accuracy."
date_authored_initial_draft: 2026-03-13
date_authored_current_draft: 2026-03-13
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.2
usage_index: 1
publish: false
category: Specification
date_created: 2026-03-13
date_modified: 2026-03-13
tags: [KPI, Extraction, Anti-Hallucination, Data-Validation, Charts, Spreadsheets, Vision-API, Perplexity, Tidyverse, CSV-Timeline]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.6"
---

# KPI Extractor Agent

**File**: `src/agents/kpi_extractor.py` (proposed)
**Status**: Specification
**Date**: 2026-03-13
**Related**: Deck-Analyzer-Agent.md, Dataroom-Analyzer-Agent.md, Anti-Hallucination-Source-Validation-and-Removal.md

---

## Executive Summary

The KPI Extractor Agent scans pitch decks and dataroom documents to find concrete, quantitative KPIs — revenue figures, growth rates, customer counts, unit economics, retention metrics, and any other numerical performance indicators. It extracts these from charts, tables, spreadsheets, and inline text, then **validates every extracted value** against external sources via Perplexity search.

**Core constraint**: This agent produces **zero hallucinated data**. Every KPI in its output is either (a) directly extracted from a provided document with a precise source reference, or (b) validated against a credible external source. If a KPI cannot be verified, it is flagged as **unverified/document-only** rather than presented as fact.

---

## Problem Statement

### Why This Agent Is Needed

1. **KPIs are scattered across documents**: A typical dataroom has metrics buried in deck slides, Excel projections, PDF financials, and one-pagers. No single document has the complete picture.
2. **Charts contain data that text extraction misses**: Growth charts, cohort heatmaps, and waterfall diagrams contain critical metrics that text-based extraction completely overlooks.
3. **Startups self-report selectively**: Companies highlight favorable metrics and omit or obscure unfavorable ones. The agent must extract what's actually there AND flag what's suspiciously absent.
4. **Downstream agents need structured KPI data**: The writer, fact-checker, and validator agents all benefit from a canonical, structured KPI dataset rather than reconstructing metrics from prose.
5. **Hallucination risk is highest with numbers**: LLMs are most likely to fabricate or misremember specific figures. A dedicated extraction-and-validation pipeline is the defense.

### What Makes This Different from Deck Analyst

The Deck Analyst extracts **narrative content** — problem statements, business models, team bios. It captures KPIs incidentally as part of `traction_metrics`. The KPI Extractor is **purpose-built for quantitative data**:

| Deck Analyst | KPI Extractor |
|---|---|
| Extracts narrative + structure | Extracts numbers + metrics only |
| Single document (deck) | All dataroom documents |
| Text and vision modes | Text, vision, AND spreadsheet parsing |
| Best-effort extraction | Extraction + external validation |
| Outputs prose drafts | Outputs structured JSON with provenance |

---

## Anti-Hallucination Architecture

This is the defining characteristic of the agent. The system enforces accuracy through a multi-layer approach:

### Layer 1: Extract Only What's Literally There

The extraction prompt is **constrained to transcription, not interpretation**:

```
You are a data transcription tool. Extract ONLY the exact numbers,
percentages, currency amounts, and metrics that are explicitly visible
in this document.

DO NOT:
- Estimate, round, or approximate any values
- Infer metrics that are not explicitly stated
- Calculate derived metrics (e.g., don't compute CAC from spend/customers)
- Fill in missing data points with industry averages
- Assume time periods not explicitly labeled

For each metric, record:
- The exact value as written (e.g., "$2.3M" not "approximately $2 million")
- The exact location (page number, chart title, cell reference)
- The exact context (what time period, what segment, what definition)
- Your confidence: HIGH (clearly readable), MEDIUM (partially obscured/ambiguous), LOW (inferred from chart axis)
```

### Layer 2: Source Provenance Tracking

Every extracted KPI carries a provenance record:

```json
{
  "metric_name": "Annual Recurring Revenue",
  "value": "$2.3M",
  "as_of": "Q3 2025",
  "source": {
    "document": "Acme-Pitch-Deck-2025.pdf",
    "location": "Page 12, chart titled 'Revenue Growth'",
    "extraction_method": "vision_api",
    "confidence": "HIGH",
    "raw_text_or_description": "Bar chart showing ARR progression: Q1=$1.1M, Q2=$1.6M, Q3=$2.3M"
  },
  "validation": {
    "status": "verified",
    "external_source": "Crunchbase company profile",
    "external_value": "$2.3M ARR (reported Oct 2025)",
    "match": true,
    "perplexity_citation": "[^12]"
  }
}
```

### Layer 3: Perplexity Cross-Validation

After extraction, every KPI with a publicly verifiable equivalent is checked:

```python
def validate_kpi_externally(kpi: ExtractedKPI) -> ValidationResult:
    """
    Query Perplexity Sonar Pro to find external corroboration.

    Uses @source syntax for authoritative data:
    - @crunchbase for funding, ARR, headcount
    - @pitchbook for valuations, round sizes
    - @statista for market size claims
    - @sec for regulatory filings
    - @bloomberg for public market data
    """
    query = f"""
    What is {kpi.company_name}'s {kpi.metric_name} as of {kpi.as_of}?
    Only report figures from credible sources. If no reliable data exists,
    say "No verifiable data found."
    @crunchbase @pitchbook @bloomberg
    """

    result = perplexity_search(query)

    return ValidationResult(
        status=classify_match(kpi.value, result),
        external_source=result.citations[0] if result.citations else None,
        external_value=result.extracted_figure,
        discrepancy=compute_discrepancy(kpi.value, result.extracted_figure)
    )
```

### Layer 4: Discrepancy Classification

When document values and external sources disagree:

| Discrepancy | Classification | Action |
|---|---|---|
| < 5% difference | `MATCH` | Accept document value, note both sources |
| 5-20% difference | `MINOR_DISCREPANCY` | Flag both values, note possible rounding/timing difference |
| 20-50% difference | `MAJOR_DISCREPANCY` | Flag prominently, recommend manual verification |
| > 50% difference | `CONFLICT` | Do not use in memo without human review |
| External not found | `UNVERIFIED` | Use document value, label as "company-reported" |
| Document value missing | `EXTERNAL_ONLY` | Include with caveat, cite external source only |

### Layer 5: Output Segregation

The final output explicitly separates KPIs by verification status:

```markdown
## Verified KPIs (Document + External Source)
| Metric | Value | As Of | Document Source | External Source |
|---|---|---|---|---|
| ARR | $2.3M | Q3 2025 | Deck p.12 | Crunchbase [^12] |
| Total Funding | $8.5M | 2025 | Deck p.18 | PitchBook [^14] |

## Company-Reported Only (Unverified)
| Metric | Value | As Of | Document Source | Notes |
|---|---|---|---|---|
| Net Revenue Retention | 135% | Q3 2025 | Deck p.14 | No external source found |
| CAC Payback | 8 months | Q2 2025 | Financial model row 47 | Private metric |

## Discrepancies Requiring Review
| Metric | Document Value | External Value | Discrepancy | Sources |
|---|---|---|---|---|
| Headcount | 85 | 62 | +37% | Deck p.6 vs LinkedIn [^15] |
```

---

## Input Sources and Extraction Methods

### 1. Pitch Deck Charts (Vision API)

Charts are the richest KPI source and the hardest to extract from.

**Supported chart types**:
- Bar/column charts (revenue progression, customer growth)
- Line charts (growth trajectories, retention curves)
- Pie/donut charts (revenue mix, market share)
- Waterfall charts (unit economics breakdowns)
- Cohort heatmaps (retention by cohort)
- Gauge/KPI cards (single metric callouts)

**Extraction approach**:

```python
def extract_kpis_from_chart(page_image: bytes, page_number: int) -> List[ExtractedKPI]:
    """
    Use Claude Vision to read exact values from chart images.

    The prompt instructs Claude to:
    1. Identify the chart type
    2. Read axis labels and scales
    3. Extract every data point visible
    4. Note the chart title and any annotations
    5. Flag any values that are estimated from visual position
    """
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "data": page_image}},
                {"type": "text", "text": CHART_EXTRACTION_PROMPT}
            ]
        }],
        max_tokens=4096
    )
    return parse_kpi_response(response, source_page=page_number)
```

**Confidence scoring for chart reads**:
- **HIGH**: Value is explicitly labeled on the chart (data label, annotation)
- **MEDIUM**: Value is readable from axis alignment (bar height matches grid line)
- **LOW**: Value is estimated from visual position between grid lines

### 2. Spreadsheets (Direct Parsing)

Excel and CSV files in the dataroom contain the most granular financial data.

**Target spreadsheet types**:
- Financial models (P&L projections, cash flow)
- Cap tables (ownership, dilution)
- Cohort analysis (retention by month)
- Unit economics breakdowns
- Operational dashboards

**Extraction approach**:

```python
import openpyxl

def extract_kpis_from_spreadsheet(file_path: str) -> List[ExtractedKPI]:
    """
    Parse Excel files for KPI data.

    Strategy:
    1. Identify sheets with financial/metric data (skip cover sheets, notes)
    2. Find header rows (look for metric names, date columns)
    3. Extract named metrics with their values and time periods
    4. Preserve cell references for provenance
    5. Handle merged cells, hidden rows, named ranges
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)  # data_only=True resolves formulas

    kpis = []
    for sheet in wb.worksheets:
        if is_data_sheet(sheet):
            header_row = find_header_row(sheet)
            kpis.extend(extract_metrics_from_sheet(sheet, header_row, file_path))

    return kpis
```

**Key considerations**:
- Use `data_only=True` to get computed formula results, not formula strings
- Handle multiple sheets (actuals vs. projections — label appropriately)
- Distinguish between historical actuals and forward projections
- Preserve the original cell reference (e.g., "Sheet 'Financials', cell D14")

### 3. PDF Tables (Hybrid Text + Vision)

Financial summaries, term sheets, and reports often contain tabular KPI data in PDF form.

**Extraction approach**:
1. Attempt text-based table extraction first (faster, cheaper)
2. If text extraction yields malformed tables, fall back to Vision API
3. Use table structure detection to identify rows/columns
4. Map headers to values maintaining row-column relationships

### 4. Inline Text Metrics

KPIs mentioned in prose throughout any document type.

**Pattern matching for**:
- Currency amounts: `$X.XM`, `$XXK`, `€XX million`
- Percentages: `XX% growth`, `XXx return`
- Counts: `X,XXX customers`, `XX employees`
- Ratios: `X.Xx LTV/CAC`, `XXx ARR multiple`
- Time-based: `X months payback`, `XX-month runway`

```python
import re

KPI_PATTERNS = {
    "currency": r'\$[\d,.]+\s*[KMBTkmbt](?:illion)?',
    "percentage": r'[\d.]+%',
    "multiplier": r'[\d.]+[xX]',
    "count_with_unit": r'[\d,]+\s+(?:customers|users|employees|clients|partners)',
    "time_metric": r'[\d.]+\s*(?:month|year|week|day)s?\s+(?:runway|payback|churn)',
}
```

---

## KPI Taxonomy

The agent classifies extracted KPIs into standardized categories:

### Revenue & Growth
- Annual Recurring Revenue (ARR)
- Monthly Recurring Revenue (MRR)
- Revenue (total, by segment)
- Revenue growth rate (MoM, QoQ, YoY)
- Average Contract Value (ACV)
- Average Revenue Per User (ARPU)

### Unit Economics
- Customer Acquisition Cost (CAC)
- Lifetime Value (LTV)
- LTV/CAC ratio
- CAC payback period
- Gross margin
- Contribution margin
- Burn multiple

### Engagement & Retention
- Net Revenue Retention (NRR/NDR)
- Gross Revenue Retention
- Monthly/annual churn rate
- DAU/MAU ratio
- Session frequency/duration
- Cohort retention curves

### Scale & Traction
- Total customers/users
- Paying customers
- Logo count by segment
- Pipeline/bookings
- Win rate

### Operational
- Employee headcount
- Revenue per employee
- Burn rate (monthly/annual)
- Runway (months)
- Cash on hand

### Market
- TAM/SAM/SOM
- Market share
- Market growth rate

### Funding
- Total raised to date
- Latest round size
- Pre/post-money valuation
- Implied ARR multiple

---

## Output Schema

### Artifact: `0-kpi-extraction.json`

```json
{
  "company_name": "Acme Corp",
  "extraction_timestamp": "2026-03-13T14:30:00Z",
  "documents_processed": [
    {
      "filename": "Acme-Pitch-Deck-2025.pdf",
      "type": "pitch_deck",
      "pages_analyzed": 22,
      "kpis_extracted": 34
    },
    {
      "filename": "Acme-Financial-Model-2025.xlsx",
      "type": "financial_model",
      "sheets_analyzed": 4,
      "kpis_extracted": 87
    }
  ],
  "kpis": [
    {
      "id": "kpi-001",
      "category": "revenue_growth",
      "metric_name": "Annual Recurring Revenue",
      "metric_abbreviation": "ARR",
      "value": 2300000,
      "display_value": "$2.3M",
      "unit": "USD",
      "as_of": "2025-09-30",
      "time_period": "Q3 2025",
      "is_projection": false,
      "source": {
        "document": "Acme-Pitch-Deck-2025.pdf",
        "location": "Page 12, bar chart 'Revenue Growth'",
        "extraction_method": "vision_api",
        "confidence": "HIGH",
        "raw_context": "Bar chart showing quarterly ARR: Q1=$1.1M, Q2=$1.6M, Q3=$2.3M"
      },
      "validation": {
        "status": "verified",
        "external_source": "Crunchbase",
        "external_url": "https://crunchbase.com/organization/acme-corp",
        "external_value": "$2.3M ARR",
        "match": true,
        "discrepancy_pct": 0,
        "perplexity_citation": "[^12]"
      },
      "related_kpis": ["kpi-002", "kpi-003"],
      "notes": null
    }
  ],
  "summary": {
    "total_kpis_extracted": 121,
    "verified": 28,
    "unverified_document_only": 76,
    "external_only": 5,
    "discrepancies": 3,
    "conflicts": 1,
    "projections_excluded": 8
  },
  "notable_absences": [
    "No churn rate disclosed in any document",
    "No unit economics (CAC, LTV) found — unusual for Series A",
    "Revenue breakdown by customer segment not provided"
  ]
}
```

### Artifact: `0-kpi-extraction.md`

Human-readable summary for review, structured as the verification-status tables shown in the Anti-Hallucination Architecture section above.

### Artifact: `0-kpi-timeline.csv` (Tidy Format)

The agent produces a **tidy data** CSV following Tidyverse conventions — one observation per row, one variable per column. This makes the data immediately usable in R, Python pandas, Observable, or any analysis tool without reshaping.

#### Timeline Structure

The timeline spans from the company's founding date (or earliest plausible data point) through the most recent period with data. Every month gets a row for every metric, even if the value is `NA` — this preserves the time axis and makes gaps explicit rather than hidden.

#### Column Schema

| Column | Type | Description | Example |
|---|---|---|---|
| `month_number` | integer | Monotonic counter from month 1 (founding) through month n (latest) | `1`, `2`, ... `36` |
| `year` | integer | ISO year | `2023`, `2024`, `2025` |
| `month` | string | ISO month, zero-padded | `01`, `02`, ... `12` |
| `year_month` | string | ISO year-month composite | `2023-01`, `2024-06`, `2025-09` |
| `metric_name` | string | Human-readable KPI name | `Annual Recurring Revenue` |
| `metric_abbreviation` | string | Short form | `ARR` |
| `category` | string | KPI taxonomy category | `revenue_growth` |
| `value` | numeric | Raw numeric value (no formatting) | `2300000` |
| `display_value` | string | Formatted for humans | `$2.3M` |
| `unit` | string | Unit of measurement | `USD`, `%`, `count`, `months`, `ratio` |
| `is_projection` | boolean | `FALSE` for actuals, `TRUE` for forecasts | `FALSE` |
| `source_document` | string | Which document this value came from | `Acme-Pitch-Deck-2025.pdf` |
| `source_location` | string | Page, cell, or chart reference | `Page 12, bar chart` |
| `confidence` | string | Extraction confidence | `HIGH`, `MEDIUM`, `LOW` |
| `validation_status` | string | External verification result | `verified`, `unverified`, `discrepancy` |

#### Example CSV

```csv
month_number,year,month,year_month,metric_name,metric_abbreviation,category,value,display_value,unit,is_projection,source_document,source_location,confidence,validation_status
1,2023,03,2023-03,Monthly Recurring Revenue,MRR,revenue_growth,12000,$12K,USD,FALSE,Acme-Financial-Model-2025.xlsx,Sheet 'Monthly' cell C4,HIGH,unverified
1,2023,03,2023-03,Total Customers,Customers,scale_traction,3,3,count,FALSE,Acme-Pitch-Deck-2025.pdf,Page 14 timeline,MEDIUM,unverified
2,2023,04,2023-04,Monthly Recurring Revenue,MRR,revenue_growth,18000,$18K,USD,FALSE,Acme-Financial-Model-2025.xlsx,Sheet 'Monthly' cell D4,HIGH,unverified
2,2023,04,2023-04,Total Customers,Customers,scale_traction,5,5,count,FALSE,Acme-Financial-Model-2025.xlsx,Sheet 'Monthly' cell D8,HIGH,unverified
...
30,2025,08,2025-08,Monthly Recurring Revenue,MRR,revenue_growth,192000,$192K,USD,FALSE,Acme-Pitch-Deck-2025.pdf,Page 12 bar chart,HIGH,verified
30,2025,08,2025-08,Annual Recurring Revenue,ARR,revenue_growth,2300000,$2.3M,USD,FALSE,Acme-Pitch-Deck-2025.pdf,Page 12 bar chart,HIGH,verified
30,2025,08,2025-08,Total Customers,Customers,scale_traction,340,340,count,FALSE,Acme-Pitch-Deck-2025.pdf,Page 14 KPI card,HIGH,verified
30,2025,08,2025-08,Net Revenue Retention,NRR,engagement_retention,135,135%,%,FALSE,Acme-Pitch-Deck-2025.pdf,Page 14 KPI card,MEDIUM,unverified
31,2025,09,2025-09,Monthly Recurring Revenue,MRR,revenue_growth,NA,NA,USD,TRUE,Acme-Financial-Model-2025.xlsx,Sheet 'Projections' cell AF4,HIGH,unverified
31,2025,09,2025-09,Annual Recurring Revenue,ARR,revenue_growth,3000000,$3.0M,USD,TRUE,Acme-Financial-Model-2025.xlsx,Sheet 'Projections' cell AF5,HIGH,unverified
```

#### Design Decisions (Tidyverse Principles)

1. **One observation per row**: Each row is one metric at one point in time. No wide-format "Jan, Feb, Mar" columns.
2. **`month_number` as monotonic index**: Starts at 1 from founding month, increments by 1 per month. This makes time-series math trivial (`month_number` 24 = 2 years in) without requiring date arithmetic.
3. **Separate `year` and `month` columns**: Enables easy faceting (`group_by(year)`) and filtering (`filter(month == "01")` for January snapshots) without string parsing.
4. **`year_month` composite**: Convenience column for plotting x-axes and joins. ISO format `YYYY-MM` sorts lexicographically.
5. **Explicit `NA` for missing periods**: If a metric is known to exist but has no data for a given month, the row exists with `value = NA`. This distinguishes "no data" from "metric didn't exist yet." Rows are omitted only for months before the metric's earliest known observation.
6. **Projections inline but flagged**: Projections appear in the same timeline (they ARE time-series data) but `is_projection = TRUE` makes filtering trivial: `df[df.is_projection == False]` for actuals-only analysis.
7. **No derived metrics in raw output**: The CSV contains only directly extracted values. Computed metrics (growth rates, ratios between metrics) belong in analysis notebooks, not the extraction artifact.

#### Month Number Calculation

```python
from datetime import date

def calculate_month_number(founding_date: date, target_year: int, target_month: int) -> int:
    """
    Calculate monotonic month number from founding date.

    Month 1 = founding month.
    Example: founded 2023-03, target 2025-08 → month 30
    """
    return (target_year - founding_date.year) * 12 + (target_month - founding_date.month) + 1
```

#### Founding Date Resolution

The agent determines the timeline start (`month_number = 1`) using this priority:

1. **Company data file**: `data/{Company}.json` → `"founded": "2023-03"` (if provided)
2. **Incorporation date**: Extracted from legal docs in dataroom
3. **Earliest data point**: The oldest dated metric found across all documents
4. **Crunchbase founding date**: Via Perplexity search as fallback

If ambiguous, the agent logs the chosen start date and rationale in `0-kpi-extraction.json` under `"timeline_start"`.

#### CSV Generation

```python
import csv
from datetime import date
from typing import List

def generate_kpi_timeline_csv(
    kpis: List[ExtractedKPI],
    founding_date: date,
    output_path: str
) -> str:
    """
    Transform extracted KPIs into tidy-format timeline CSV.

    Rules:
    - One row per metric per month
    - Only include months where at least one metric has data
    - Fill NA for metrics that exist but lack data in a given month
    - Sort by month_number, then metric_name
    """
    # Collect all unique (year, month) periods across all KPIs
    periods = sorted(set(
        (kpi.as_of_year, kpi.as_of_month)
        for kpi in kpis
        if kpi.as_of_year and kpi.as_of_month
    ))

    # Collect all unique metric names
    metrics = sorted(set(kpi.metric_name for kpi in kpis))

    # Build lookup: (year, month, metric_name) → kpi
    lookup = {}
    for kpi in kpis:
        if kpi.as_of_year and kpi.as_of_month:
            lookup[(kpi.as_of_year, kpi.as_of_month, kpi.metric_name)] = kpi

    fieldnames = [
        "month_number", "year", "month", "year_month",
        "metric_name", "metric_abbreviation", "category",
        "value", "display_value", "unit",
        "is_projection", "source_document", "source_location",
        "confidence", "validation_status"
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for (yr, mo) in periods:
            month_num = calculate_month_number(founding_date, yr, mo)
            year_month = f"{yr}-{mo:02d}"

            for metric in metrics:
                kpi = lookup.get((yr, mo, metric))

                writer.writerow({
                    "month_number": month_num,
                    "year": yr,
                    "month": f"{mo:02d}",
                    "year_month": year_month,
                    "metric_name": metric if kpi else metric,
                    "metric_abbreviation": kpi.metric_abbreviation if kpi else "NA",
                    "category": kpi.category if kpi else "NA",
                    "value": kpi.value if kpi else "NA",
                    "display_value": kpi.display_value if kpi else "NA",
                    "unit": kpi.unit if kpi else "NA",
                    "is_projection": kpi.is_projection if kpi else "NA",
                    "source_document": kpi.source.document if kpi else "NA",
                    "source_location": kpi.source.location if kpi else "NA",
                    "confidence": kpi.source.confidence if kpi else "NA",
                    "validation_status": kpi.validation.status if kpi else "NA",
                })

    return output_path
```

#### Artifact Location

```
output/{Company-Name}-v0.0.x/
├── 0-kpi-extraction.json       # Full structured KPI data
├── 0-kpi-extraction.md         # Human-readable summary
├── 0-kpi-timeline.csv          # Tidy timeline ← NEW
├── 0-deck-analysis.json
└── ...
```

---

## Pipeline Integration

### Position in Workflow

```
deck_analyst → kpi_extractor → research → writer → ...
```

The KPI Extractor runs **after** the Deck Analyst (reuses deck text/vision extraction) and **before** Research (so the research agent can target gaps identified by absent KPIs).

### State Updates

```python
def kpi_extractor(state: MemoState) -> dict:
    return {
        "kpi_data": extracted_kpis,          # Full structured KPI dataset
        "kpi_gaps": notable_absences,         # Missing metrics to research
        "messages": ["KPI extraction complete: 121 KPIs, 28 verified, 3 discrepancies"]
    }
```

### Downstream Consumption

**Research Agent**: Uses `kpi_gaps` to focus web searches on missing metrics
```python
# If no churn rate found in documents, research agent searches for it
for gap in state["kpi_gaps"]:
    queries.append(f"{company_name} {gap} @crunchbase @pitchbook")
```

**Writer Agent**: Uses `kpi_data` to insert verified metrics into sections
```python
# Writer can pull exact, cited figures instead of paraphrasing deck content
verified_kpis = [k for k in state["kpi_data"]["kpis"] if k["validation"]["status"] == "verified"]
```

**Fact Checker Agent**: Uses `kpi_data` as ground truth for claim verification
```python
# If memo says "$2.3M ARR" and kpi_data confirms it, fact checker approves
# If memo says "$3M ARR" but kpi_data shows $2.3M, fact checker flags it
```

---

## Handling Projections vs. Actuals

A critical distinction the agent must maintain:

| Data Type | Treatment | Label in Output |
|---|---|---|
| Historical actuals | Extract, validate externally | `"is_projection": false` |
| Current period metrics | Extract, validate if possible | `"is_projection": false` |
| Forward projections | Extract but **segregate** | `"is_projection": true` |
| Assumptions/targets | Extract but **segregate** | `"is_projection": true, "is_target": true` |

**Rule**: Projections are NEVER mixed with actuals in the verified KPI tables. They appear in a separate "Projections" section with clear labeling. The writer agent must never present a projected figure as an achieved metric.

---

## Performance Estimates

| Input Type | Documents | Estimated Time | Estimated Cost |
|---|---|---|---|
| Deck only (20 pages) | 1 | 30-60 seconds | $0.50-1.00 |
| Deck + financial model | 2 | 60-90 seconds | $1.00-2.00 |
| Full dataroom (10 docs) | 10 | 3-5 minutes | $3.00-5.00 |
| Perplexity validation (per KPI) | — | ~2 seconds | ~$0.05 |
| Batch validation (30 KPIs) | — | ~30 seconds | ~$1.50 |

**Optimization**: Batch Perplexity queries by category (all revenue metrics in one query, all funding metrics in another) to reduce API calls.

---

## Implementation Phases

### Phase 1: Deck Chart Extraction
- Vision API chart reading with confidence scoring
- KPI taxonomy classification
- JSON + markdown artifact output
- Integration with existing deck analyst output

### Phase 2: Spreadsheet Parsing
- Excel/CSV parsing with openpyxl
- Header detection and metric identification
- Cell reference provenance tracking
- Projection vs. actuals separation

### Phase 3: Perplexity Cross-Validation
- External validation pipeline
- Discrepancy classification
- Batch query optimization
- Citation generation for verified KPIs

### Phase 4: Gap Analysis
- Notable absence detection (compare extracted KPIs against expected KPIs for company stage)
- Feed gaps to research agent
- Stage-appropriate expectations (Seed vs. Series A vs. Series B)

---

## Dependencies

**Python packages** (most already in project):
- `anthropic` — Claude Vision API for chart extraction
- `openpyxl` — Excel file parsing
- `PyMuPDF` or `pdf2image` — PDF page rendering (already used by deck analyst)
- `httpx` — Perplexity API calls (already used by citation enrichment)

**New dependency**:
- `openpyxl` — If not already installed, add to `pyproject.toml`

**System dependencies**: None beyond what deck analyst already requires.

---

## Related Documentation

- [Deck-Analyzer-Agent.md](./Deck-Analyzer-Agent.md) — Upstream agent, provides initial deck extraction
- [Dataroom-Analyzer-Agent.md](./Dataroom-Analyzer-Agent.md) — Broader dataroom processing system
- [Anti-Hallucination-Source-Validation-and-Removal.md](./Anti-Hallucination-Source-Validation-and-Removal.md) — Validation patterns this agent extends
- [Faked-Sources-from-Perplexity.md](./Faked-Sources-from-Perplexity.md) — Known Perplexity citation reliability issues
- [Preventing-Hallucinations-in-Memo-Generation.md](./issue-resolution/Preventing-Hallucinations-in-Memo-Generation.md) — Anti-hallucination strategies

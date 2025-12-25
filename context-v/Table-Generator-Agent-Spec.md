# Table Generator Agent Specification

## Overview

The `table_generator` agent scans memo sections and source materials (decks, datarooms, research) to identify numerical data that would be more effectively communicated in tabular format. It then generates markdown tables and saves them to a dedicated output folder, while also inserting them into relevant sections.

## Purpose

Investment memos often contain series of numbers, comparisons, or structured data that get buried in prose. Tables improve:
- **Scannability**: Readers can quickly compare metrics
- **Clarity**: Relationships between data points become obvious
- **Credibility**: Structured presentation signals analytical rigor
- **Density**: More information in less space

---

## Upstream Agent Responsibilities

Table data detection should happen **early in the pipeline**, not just at the `table_generator` stage. The following agents are responsible for flagging tabular data opportunities as they encounter them.

### 1. `deck_analyst` Agent

The deck analyst should actively identify and extract tabular data during PDF analysis.

**Responsibilities:**
- Flag slides containing tables, charts, or data grids
- Extract structured data from financial projection slides
- Capture funding history tables verbatim
- Parse team/org slides into structured format
- Identify competitive matrices and comparison charts
- Note market sizing slides with TAM/SAM/SOM breakdowns

**Output Schema Addition:**
```python
# In DeckAnalysisData (src/state.py)
class DeckAnalysisData(TypedDict):
    # ... existing fields ...
    tabular_data: list[TabularDataCandidate]  # NEW

class TabularDataCandidate(TypedDict):
    source: str  # "deck_slide_12", "deck_table_3"
    table_type: str  # "funding_history", "team_credentials", "financials", etc.
    raw_data: list[dict]  # Extracted rows as dicts
    suggested_section: str  # "Funding & Terms", "Organization", etc.
    confidence: float  # 0.0-1.0 extraction confidence
```

**Example Extraction:**
```json
{
  "source": "deck_slide_8",
  "table_type": "funding_history",
  "raw_data": [
    {"round": "Pre-Seed", "date": "Q1 2023", "amount": "$500K", "lead": "Angels"},
    {"round": "Seed", "date": "Q4 2023", "amount": "$2M", "lead": "Acme Ventures"}
  ],
  "suggested_section": "Funding & Terms",
  "confidence": 0.95
}
```

### 2. `dataroom_analyzer` Agent

The dataroom analyzer should extract tabular data from financial documents, cap tables, and other structured materials.

**Responsibilities:**
- Parse cap tables into standardized format
- Extract financial statements (P&L, balance sheet, cash flow)
- Identify customer/contract tables
- Capture pipeline/funnel metrics
- Extract KPI dashboards and metric summaries
- Flag spreadsheets and CSVs for direct table conversion

**Output Schema Addition:**
```python
# In DataroomAnalysisData (src/state.py) - NEW
class DataroomAnalysisData(TypedDict):
    documents_analyzed: list[str]
    tabular_data: list[TabularDataCandidate]
    cap_table: Optional[CapTableData]
    financials: Optional[FinancialsData]

class CapTableData(TypedDict):
    shareholders: list[dict]  # name, shares, percentage, type
    total_shares: int
    option_pool: float
    as_of_date: str

class FinancialsData(TypedDict):
    revenue_by_period: list[dict]  # period, revenue, growth
    expenses_by_category: list[dict]
    key_metrics: list[dict]  # metric_name, value, period
```

**Example Extraction:**
```json
{
  "source": "dataroom/cap_table_2024.xlsx",
  "table_type": "cap_table",
  "raw_data": [
    {"shareholder": "Founder A", "shares": 4000000, "percentage": "40%", "type": "Common"},
    {"shareholder": "Founder B", "shares": 3000000, "percentage": "30%", "type": "Common"},
    {"shareholder": "Acme Ventures", "shares": 2000000, "percentage": "20%", "type": "Series Seed"},
    {"shareholder": "Option Pool", "shares": 1000000, "percentage": "10%", "type": "Reserved"}
  ],
  "suggested_section": "Funding & Terms",
  "confidence": 1.0
}
```

### 3. `research_enhanced` Agent

The research agent should flag data series and comparisons discovered during web research.

**Responsibilities:**
- Identify competitor metrics mentioned across sources
- Capture market sizing data from research reports
- Flag funding data for comparable companies
- Note industry benchmarks and growth rates
- Collect analyst estimates and forecasts

**Output Schema Addition:**
```python
# In ResearchData (src/state.py)
class ResearchData(TypedDict):
    # ... existing fields ...
    tabular_data: list[TabularDataCandidate]  # NEW
```

**Example Extraction:**
```json
{
  "source": "research_competitor_analysis",
  "table_type": "competitor_comparison",
  "raw_data": [
    {"company": "Calm", "funding": "$218M", "valuation": "$2B", "users": "4M"},
    {"company": "Headspace", "funding": "$215M", "valuation": "$1.5B", "users": "2.5M"},
    {"company": "Noom", "funding": "$540M", "valuation": "$3.7B", "users": "1M"}
  ],
  "suggested_section": "Opportunity",
  "confidence": 0.85
}
```

---

## Output Directory Structure

Tables are saved to a dedicated `2-tables/` folder, pushing subsequent artifacts to higher numbers:

```
output/{Company}-v0.0.x/
├── 0-deck-analysis.json + .md
├── 1-research/
│   └── *.md (section research files)
├── 2-tables/                          # NEW - Table artifacts
│   ├── tables-manifest.json           # Index of all tables
│   ├── funding-history.md             # Individual table files
│   ├── team-credentials.md
│   ├── competitor-comparison.md
│   ├── market-sizing.md
│   ├── financial-projections.md
│   └── cap-table.md
├── 3-sections/                        # Was 2-sections
│   └── *.md
├── 4-validation.json + .md            # Was 3-validation
├── 5-final-draft.md                   # Was 4-final-draft
└── state.json
```

### `tables-manifest.json` Schema
```json
{
  "generated_at": "2024-01-15T10:30:00Z",
  "tables": [
    {
      "id": "funding-history",
      "file": "funding-history.md",
      "type": "funding_history",
      "source": "deck_slide_8",
      "target_section": "09-funding-terms.md",
      "rows": 3,
      "columns": ["Round", "Date", "Amount", "Lead", "Participants"],
      "inserted": true
    },
    {
      "id": "competitor-comparison",
      "file": "competitor-comparison.md",
      "type": "competitor_comparison",
      "source": "research_competitor_analysis",
      "target_section": "06-opportunity.md",
      "rows": 4,
      "columns": ["Company", "Funding", "Valuation", "Users"],
      "inserted": true
    }
  ],
  "summary": {
    "total_tables": 5,
    "tables_inserted": 5,
    "sources": {
      "deck": 2,
      "dataroom": 1,
      "research": 2
    }
  }
}
```

---

## Data Sources to Scan

### 1. Pitch Deck Analysis (`0-deck-analysis.json`)
- Financial projections (revenue, costs, margins by year)
- Funding history (round, date, amount, investors)
- Team credentials (name, role, prior companies)
- Competitive matrices
- Market sizing breakdowns (TAM/SAM/SOM)
- Milestone timelines
- **Pre-extracted `tabular_data` from deck_analyst**

### 2. Dataroom Materials (if available)
- Cap tables
- Financial statements
- Customer lists with contract values
- Pipeline/funnel metrics
- **Pre-extracted `tabular_data` from dataroom_analyzer**

### 3. Research Files (`1-research/*.md`)
- Competitor funding amounts
- Market size estimates from multiple sources
- Industry growth rates
- **Pre-extracted `tabular_data` from research_enhanced**

### 4. Section Content (`3-sections/*.md`)
- Inline number series (e.g., "revenue grew from $1M in 2022 to $3M in 2023 to $8M in 2024")
- Repeated metric patterns (e.g., multiple competitors with funding amounts)
- Lists that follow a consistent structure

## Detection Patterns

### Pattern 1: Temporal Series
Numbers associated with time periods that show progression.

**Input (prose):**
```
Revenue grew from $1.2M in 2022 to $3.4M in 2023, reaching $8.1M in 2024.
The company projects $18M for 2025.
```

**Output (table):**
```markdown
| Year | Revenue |
|------|---------|
| 2022 | $1.2M   |
| 2023 | $3.4M   |
| 2024 | $8.1M   |
| 2025 | $18M (projected) |
```

### Pattern 2: Entity Comparisons
Multiple entities with the same attributes mentioned.

**Input (prose):**
```
Key competitors include Calm, which has raised $218M and serves 4M subscribers,
Headspace with $215M raised and 2.5M subscribers, and Noom at $540M raised
with 1M subscribers.
```

**Output (table):**
```markdown
| Competitor | Funding Raised | Subscribers |
|------------|----------------|-------------|
| Calm       | $218M          | 4M          |
| Headspace  | $215M          | 2.5M        |
| Noom       | $540M          | 1M          |
| **Reson8** | $2.5M          | 50K         |
```

### Pattern 3: Funding History
Investment rounds with dates and participants.

**Input (prose):**
```
The company raised a $500K pre-seed from angels in Q1 2023, followed by a
$2M seed led by Acme Ventures in Q4 2023 with participation from XYZ Capital.
```

**Output (table):**
```markdown
| Round    | Date    | Amount | Lead Investor | Participants |
|----------|---------|--------|---------------|--------------|
| Pre-Seed | Q1 2023 | $500K  | Angels        | -            |
| Seed     | Q4 2023 | $2M    | Acme Ventures | XYZ Capital  |
```

### Pattern 4: Team Credentials
Founder/executive backgrounds with structured information.

**Input (prose):**
```
CEO Jane Smith previously founded DataCo (acquired by Google, 2019) and
spent 8 years at McKinsey. CTO Bob Chen was VP Engineering at Stripe and
holds 12 patents in ML infrastructure.
```

**Output (table):**
```markdown
| Role | Name       | Prior Experience                          | Notable Achievement        |
|------|------------|-------------------------------------------|----------------------------|
| CEO  | Jane Smith | Founder, DataCo; McKinsey (8 yrs)         | DataCo acquired by Google  |
| CTO  | Bob Chen   | VP Engineering, Stripe                    | 12 patents in ML infra     |
```

### Pattern 5: Market Sizing
TAM/SAM/SOM or segmented market estimates.

**Input (prose):**
```
The global wellness market is $4.4T, with digital health at $330B.
The longevity segment represents $44B, of which frequency therapeutics
could capture $2-4B.
```

**Output (table):**
```markdown
| Market Segment          | Size    | Notes                    |
|-------------------------|---------|--------------------------|
| Global Wellness (TAM)   | $4.4T   | Total addressable        |
| Digital Health          | $330B   | Technology-enabled       |
| Longevity (SAM)         | $44B    | Serviceable addressable  |
| Frequency Therapeutics  | $2-4B   | Serviceable obtainable   |
```

### Pattern 6: Scorecard/Rating Data
Any existing scoring or rating information.

**Input (from scorecard evaluation):**
```json
{
  "scores": {
    "Problem": 7,
    "Product": 8,
    "People": 6,
    "Positioning": 9,
    "Potential": 8
  }
}
```

**Output (table):**
```markdown
| Dimension   | Score | Assessment |
|-------------|-------|------------|
| Problem     | 7/10  | Strong     |
| Product     | 8/10  | Strong     |
| People      | 6/10  | Moderate   |
| Positioning | 9/10  | Excellent  |
| Potential   | 8/10  | Strong     |
```

## Agent Architecture

### Input
```python
def table_generator(state: MemoState) -> dict:
    """
    Scans sections and source materials for tabular data opportunities.
    Inserts markdown tables into relevant sections.
    """
```

### Processing Steps

1. **Load Source Data**
   - Deck analysis JSON with pre-extracted `tabular_data` (if available)
   - Dataroom analysis with pre-extracted `tabular_data` (if available)
   - Research data with pre-extracted `tabular_data`
   - Section markdown files from `3-sections/`

2. **Consolidate Pre-Extracted Data**
   - Merge `tabular_data` from all upstream agents
   - Deduplicate overlapping data (prefer higher confidence sources)
   - Validate data completeness (minimum 3 rows per table)

3. **Scan Prose for Additional Patterns**
   - Parse section content for inline number series
   - Identify repeated entity-attribute patterns not caught upstream
   - Use regex + LLM classification for edge cases

4. **Match Data to Sections**
   - Funding tables → "Funding & Terms" section
   - Team tables → "Team" or "Organization" section
   - Competitor tables → "Market Context" or "Opportunity" section
   - Financial projections → "Traction" or "Business Overview" section
   - Scorecard tables → "Scorecard Summary" section
   - Cap tables → "Funding & Terms" section

5. **Generate Tables**
   - Format as GitHub-flavored markdown
   - Include column alignment (right-align numbers)
   - Add source citations where available
   - Bold the subject company row in comparison tables

6. **Save Table Artifacts**
   - Create `2-tables/` directory
   - Save each table as individual `.md` file
   - Generate `tables-manifest.json` with metadata

7. **Insert Tables into Sections**
   - Find optimal insertion point (after relevant prose, before next subsection)
   - Preserve surrounding content
   - Add brief caption if context needed
   - Write back to `3-sections/*.md`
   - Update manifest with `inserted: true`

### Output
```python
return {
    "tables_generated": {
        "tables_dir": "2-tables/",
        "manifest": "2-tables/tables-manifest.json",
        "tables": [
            {"id": "team_credentials", "file": "team-credentials.md", "inserted_in": "04-organization.md"},
            {"id": "advisory_board", "file": "advisory-board.md", "inserted_in": "04-organization.md"},
            {"id": "competitor_comparison", "file": "competitor-comparison.md", "inserted_in": "06-opportunity.md"},
            {"id": "market_sizing", "file": "market-sizing.md", "inserted_in": "06-opportunity.md"},
            {"id": "funding_history", "file": "funding-history.md", "inserted_in": "09-funding-terms.md"}
        ],
        "sections_updated": ["04-organization.md", "06-opportunity.md", "09-funding-terms.md"],
        "source_breakdown": {
            "deck_analyst": 2,
            "dataroom_analyzer": 1,
            "research_enhanced": 1,
            "prose_extraction": 1
        }
    },
    "messages": ["Table generation complete: 5 tables saved to 2-tables/, inserted into 3 sections"]
}
```

## Table Formatting Standards

### Markdown Syntax
```markdown
| Header 1 | Header 2 | Header 3 |
|:---------|:--------:|---------:|
| Left     | Center   | Right    |
```

### Number Formatting
- Currency: `$1.2M`, `$500K`, `$4.4T`
- Percentages: `45%`, `12.5%`
- Large numbers: `4M users`, `1.2B requests`
- Dates: `Q1 2023`, `2024`, `Mar 2024`

### Visual Hierarchy
- **Bold** the subject company in comparison tables
- Use consistent decimal precision within columns
- Include units in headers, not cells (e.g., "Revenue ($M)" not "$1M, $2M")

### Table Placement
- After the prose that references the data
- Before the next `###` subsection header
- With one blank line above and below

## Edge Cases

### Insufficient Data
If only 2 data points exist, keep as prose. Tables require 3+ rows to add value.

### Conflicting Sources
If multiple sources give different numbers, note the range or pick the most credible source with citation.

### Already Tabular
If data is already in a table (from deck or dataroom), preserve format but standardize styling.

### Missing Values
Use `-` or `N/A` for missing cells, never leave blank.

## Pipeline Position

```
deck_analyst ──────────────────┐
                               │
dataroom_analyzer ─────────────┼──→ [tabular_data collected in state]
                               │
research_enhanced ─────────────┘
        │
        ▼
writer → trademark_enrichment → socials_enrichment → link_enrichment
       → TABLE_GENERATOR → visualization_enrichment → citation_enrichment
```

**Upstream (data collection):**
- `deck_analyst`: Extracts tabular data from pitch deck slides
- `dataroom_analyzer`: Extracts tables from financial docs, cap tables, spreadsheets
- `research_enhanced`: Flags competitor comparisons, market data from web research

**Table generator runs:**
- **After** link enrichment (so entity links are already in place)
- **Before** citation enrichment (so tables can receive citations)
- **Before** visualization (tables inform what charts might help)
- **Consumes** pre-extracted `tabular_data` from upstream agents
- **Outputs** to `2-tables/` folder AND inserts into `3-sections/`

## Success Metrics

- Tables per memo: Target 3-8 tables for a complete memo
- Data coverage: >80% of structured data from deck should appear in tables
- Readability: Tables should reduce word count while preserving information

## Example Section Transformation

### Before (prose-heavy)
```markdown
## Funding & Terms

The company has raised capital across multiple rounds. In January 2023,
they closed a $500K pre-seed round from angel investors. This was followed
by a $2.5M seed round in September 2023 led by Acme Ventures with participation
from XYZ Capital and several angels. The current round is a $5M Series A at
a $25M pre-money valuation, led by Growth Partners.
```

### After (with table)
```markdown
## Funding & Terms

The company has raised capital across multiple rounds, demonstrating
consistent investor interest and valuation step-ups.

| Round    | Date     | Amount | Pre-Money | Lead          | Participants        |
|----------|----------|--------|-----------|---------------|---------------------|
| Pre-Seed | Jan 2023 | $500K  | $2.5M     | Angels        | -                   |
| Seed     | Sep 2023 | $2.5M  | $10M      | Acme Ventures | XYZ Capital, Angels |
| Series A | Current  | $5M    | $25M      | Growth Partners | TBD               |

The current round represents a 2.5x step-up from the seed valuation,
reflecting progress on [key milestones].
```

## Implementation Notes

### LLM Prompting Strategy
Use Claude to:
1. Identify candidate data patterns in prose
2. Extract structured fields from unstructured text
3. Determine optimal table schema (columns, ordering)
4. Generate natural transition sentences around tables

### Regex Patterns for Detection
```python
# Currency series
r'\$[\d.]+[KMB]?\s+(?:in\s+)?\d{4}'

# Percentage series
r'\d+(?:\.\d+)?%\s+(?:in\s+)?\d{4}'

# Entity with metrics
r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:raised|has|with)\s+\$[\d.]+[KMB]?'
```

### Validation
- Verify table renders correctly in markdown preview
- Check column alignment consistency
- Ensure no data loss from prose→table conversion

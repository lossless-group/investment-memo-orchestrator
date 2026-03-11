---
title: Introducing a Table Generator Agent
lede: A post-writer enrichment agent that identifies tabular data opportunities in memo sections and generates markdown tables with overflow anchor linking, configurable column schemas, and firm-specific customization.
date_authored_initial_draft: 2026-03-10
date_authored_current_draft: 2026-03-10
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-10
at_semantic_version: 0.2.0
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Agent-Design, Tables, Data-Visualization, Markdown, Enrichment]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A markdown table with clean columns and rows displaying competitor data, with an anchor link icon pointing to a detailed section below, surrounded by other table types like funding history and team credentials.
date_created: 2026-03-10
date_modified: 2026-03-10
---

# Introducing a Table Generator Agent

**Status**: Draft (v0.2.0 — supersedes Table-Generator-Agent-Spec.md)
**Date**: 2026-03-10
**Last Updated**: 2026-03-10
**Author**: AI Labs Team
**Related**: Table-Generator-Agent-Spec.md (original spec), Introducing-a-Competitive-Landscape-Research-and-Evaluation-System.md, Format-Memo-According-to-Template-Input.md
**Supersedes**: context-v/Table-Generator-Agent-Spec.md (original spec remains for reference)

---

## Executive Summary

The table generator agent scans written memo sections and structured data from upstream agents to identify content that would be more effectively communicated in tabular format. It generates markdown tables, inserts them into relevant sections, and handles overflow data through anchor links to detail sections.

This is a revised specification that incorporates design decisions from architecture discussions, including:
- **Configurable table schemas** defined in outline YAML or `templates/table-schemas/`
- **Anchor link overflow pattern** for data that doesn't fit in table cells (e.g., long investor lists)
- **Integration with the Competitive Landscape system** for the competitive comparison table
- **Firm-specific customization** with system defaults as fallback

---

## Goals

1. **Enhance readability** by converting inline data series into scannable tables
2. **Leverage structured data** from upstream agents (competitive landscape, deck analysis, dataroom)
3. **Handle data overflow** gracefully via anchor links to detail sections
4. **Support firm customization** of table schemas through outline YAML or template files
5. **Complement, don't replace** narrative prose (tables are additive in default mode)

---

## Pipeline Position

```
dataroom → deck → research → section_research → competitive_researcher
    → competitive_evaluator → cite → cleanup_research → writer
    → inject_deck_images → enrich_trademark → enrich_socials → enrich_links
    → TABLE_GENERATOR → enrich_visualizations → toc → revise_summaries
    → cleanup_sections → assemble_citations → validate_citations
    → fact_check → validate → scorecard
```

**Runs after**: `enrich_links` (entity links are already in place)
**Runs before**: `enrich_visualizations` and `toc` (tables inform what visualizations might help; TOC needs final headers)

### Why This Position?

- **After writer**: Tables are generated from written content + structured data, not the other way around
- **After link enrichment**: Entity links (LinkedIn, company URLs) are already in place, so tables can include linked names
- **Before citation assembly**: Tables may reference cited data; citation renumbering happens later
- **Before TOC**: If tables add new subsection headers (e.g., "### Investor Details"), the TOC needs to capture them

---

## Table Types and Priority

### Priority 1: Competitive Comparison Table

The most requested and highest-value table. Fed directly by the Competitive Landscape system.

**Data source**: `state["competitive_landscape"]["evaluated_competitors"]`

**Default columns**:
| Column | Source | Notes |
|--------|--------|-------|
| Company | `name` | Bold the subject company row |
| Founded | `founded` | Year only |
| Funding | `funding_total` | Formatted: $50M |
| Stage | `funding_stage` | Seed, Series A, etc. |
| Notable Investors | `notable_investors` | Max 2 inline, anchor link for full list |
| Key Differentiator | `key_differentiator` | Brief phrase |
| Overlap | `classification` | Direct / Indirect |

**Example output**:

```markdown
### Competitive Landscape

> _Use Markdown syntax to link out to external sources where appropriate. For example, if a company has a website, link to it. Investors, key customers, etc will all have websites that can be linked._

| Company | Founded | Funding | Stage | Notable Investors | Differentiator | Overlap |
|---------|---------|---------|-------|-------------------|----------------|---------|
| **Metabologic** | 2024 | $1.8M | Pre-Seed | Nucleus Capital | AI-designed enzymes | — |
| [Sweet Defeat](https://www.sweetdefeat.com/) | 2016 | $5M | Seed | [Full list](#sweet-defeat-investors) | Sugar-blocking lozenges | Direct |
| [SENS.life](https://sens.life/) | 2019 | $3M | Seed | [Full list](#sens-investors) | Enzymatic sugar blockers | Direct |
| [Pendulum](https://www.pendulum.health/) | 2019 | $100M | Series C | [Full list](#pendulum-investors) | Probiotic-based gut health | Indirect |

#### Investor Details {#investor-details}

##### Sweet Defeat Investors {#sweet-defeat-investors}
[Y Combinator](https://www.ycombinator.com/), [First Round Capital](https://www.frc.com/), [500 Startups](https://500.co/)

##### SENS Investors {#sens-investors}
[IndieBio](https://www.indiebio.vc/), [SOSV](https://sosv.com/), [European Angels Fund](https://www.europeanangelsfund.com/)

##### Pendulum Investors {#pendulum-investors}
[Sequoia Capital](https://www.sequoiacap.com/), [8VC](https://8vc.com/), [Meritech Capital](https://www.meritech.com/), [True Ventures](https://www.trueventures.com/), ...
```

### Priority 2: Funding History Table

**Data source**: Deck analysis, research data, section prose
**Target section**: Funding & Terms

| Round | Date | Amount | Pre-Money | Lead Investor | Participants |
|-------|------|--------|-----------|---------------|--------------|

### Priority 3: Team Credentials Table

**Data source**: Deck analysis, section prose, socials enrichment
**Target section**: Team / Organization

| Role | Name | Prior Experience | Notable Achievement |
|------|------|------------------|---------------------|

### Priority 4: Market Sizing Table

**Data source**: Research data, deck analysis
**Target section**: Market Context / Opening

| Market Segment | Size | Growth | Source |
|----------------|------|--------|--------|

### Priority 5: Key Customers / Traction Table

**Data source**: Deck analysis, dataroom, research
**Target section**: Traction & Milestones

| Customer | Contract Value | Use Case | Status |
|----------|---------------|----------|--------|

### Priority 6: Cap Table (if available)

**Data source**: Dataroom analysis
**Target section**: Funding & Terms

| Shareholder | Shares | Percentage | Type |
|-------------|--------|------------|------|

---

## Table Schema Configuration

### Option 1: Defined in Outline YAML (Preferred)

Table schemas can be defined directly in the outline YAML, keeping content structure and table definitions together.

```yaml
# In templates/outlines/direct-investment.yaml

tables:
  competitive_comparison:
    target_section: "03-market-context.md"  # Or "06-opportunity.md"
    placement: "after_prose"  # "after_prose", "before_prose", "replace_list"
    columns:
      - name: "Company"
        source_field: "name"
        bold_subject_company: true
      - name: "Founded"
        source_field: "founded"
        align: "center"
      - name: "Funding"
        source_field: "funding_total"
        align: "right"
      - name: "Stage"
        source_field: "funding_stage"
      - name: "Notable Investors"
        source_field: "notable_investors"
        overflow:
          max_inline: 2
          anchor_pattern: "{company}-investors"
          detail_header: "Investor Details"
      - name: "Differentiator"
        source_field: "key_differentiator"
      - name: "Overlap"
        source_field: "classification"
    min_rows: 3  # Don't generate table if fewer than 3 competitors

  funding_history:
    target_section: "07-funding-terms.md"
    placement: "after_prose"
    columns:
      - name: "Round"
        source_field: "round"
      - name: "Date"
        source_field: "date"
      - name: "Amount"
        source_field: "amount"
        align: "right"
      - name: "Pre-Post Money"
        source_field: "pre_post_money"
        align: "right"
      - name: "Valuation"
        source_field: "valuation"
        align: "right"
      - name: "Stage"
        source_field: "funding_stage"
      - name: "Structure"
        source_field: "structure" # SAFE, Convertible Note, Priced Round
      - name: "Lead Investor"
        source_field: "lead"
      - name: "Participants"
        source_field: "participants"
        overflow:
          max_inline: 3
          anchor_pattern: "{round}-participants"
```

### Option 2: Standalone Table Schema Templates

For firms that want to customize tables independently of the outline, schemas can live in `templates/table-schemas/`.

```
templates/
├── table-schemas/
│   ├── default/                    # System defaults (ships with repo)
│   │   ├── competitive-comparison.yaml
│   │   ├── funding-history.yaml
│   │   ├── team-credentials.yaml
│   │   ├── market-sizing.yaml
│   │   └── cap-table.yaml
│   └── custom/
│       └── hypernova/              # Firm-specific overrides
│           └── competitive-comparison.yaml
```

### Resolution Order

1. Check outline YAML for `tables:` section → use if present
2. Check `templates/table-schemas/custom/{firm}/` → use if present
3. Fall back to `templates/table-schemas/default/` → system defaults

---

## Anchor Link Overflow Pattern

### Problem

Some data doesn't fit in a table cell. An investor list might include 20+ names. A customer list might have detailed use cases. Cramming this into a table cell destroys readability, especially in portrait-layout PDFs.

### Solution: Inline Summary + Anchor Link to Detail

For columns marked with `overflow` configuration:

1. Show the N most notable items inline in the cell
2. Add an anchor link `[Full list](#anchor-id)` to a detail section
3. Generate the detail section below the table (or at end of the memo section)

### Implementation

```python
def format_overflow_cell(
    items: list[str],
    max_inline: int,
    anchor_id: str,
    anchor_label: str = "Full list"
) -> str:
    """Format a cell with overflow items."""
    if len(items) <= max_inline:
        return ", ".join(items)

    inline = ", ".join(items[:max_inline])
    return f"{inline}, [{anchor_label}](#{anchor_id})"


def generate_overflow_details(
    overflow_data: dict[str, list[str]],
    detail_header: str
) -> str:
    """Generate the detail section for overflow data."""
    lines = [f"\n#### {detail_header}\n"]
    for anchor_id, items in overflow_data.items():
        display_name = anchor_id.replace("-", " ").title()
        lines.append(f"##### {display_name} {{#{anchor_id}}}")
        lines.append(", ".join(items))
        lines.append("")
    return "\n".join(lines)
```

### Export Compatibility

- **HTML**: Anchor links work natively with `id` attributes
- **PDF (WeasyPrint)**: Internal anchor links work in generated PDFs
- **DocX (Pandoc)**: Pandoc converts markdown anchor links to Word bookmarks

---

## Table Placement and Prose Handling

### Default Mode: Additive

Tables are inserted after the relevant prose. The prose is NOT modified. This means some data appears both in prose and in the table — this is intentional for skimmable documents.

### Concise Mode (Future)

When `content_mode: "concise"` is set in the outline, the table generator also trims the prose:
- Remove inline enumerations that the table now handles (e.g., "competitors include A ($X), B ($Y), C ($Z)")
- Replace with a brief reference: "Key competitors are summarized below."
- Keep narrative analysis that adds context beyond the table

**Note**: Concise mode is a future enhancement. The initial implementation should be additive only.

### Placement Rules

1. **After the prose** that references the data, not before
2. **Before the next `###` subsection header**
3. **One blank line** above and below the table
4. If a section has multiple table opportunities, order them by relevance to the surrounding text

---

## Detection Patterns

The table generator uses two approaches:

### 1. Structured Data Consumption (Primary)

Consume pre-structured data from upstream agents:
- `state["competitive_landscape"]` → competitive comparison table
- `state["deck_analysis"]` → funding history, team credentials, market sizing
- `state["dataroom_analysis"]` → cap table, financials
- `state["research"]` → market data comparisons

This is the primary approach. Most tables should come from structured data, not prose parsing.

### 2. Prose Pattern Detection (Secondary)

Scan section content for patterns that indicate tabular data embedded in prose:

**Temporal series**: Numbers associated with time periods
```python
r'\$[\d.]+[KMB]?\s+(?:in\s+)?\d{4}'  # "$1.2M in 2022"
```

**Entity comparisons**: Multiple entities with same attributes
```python
r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:raised|has|with)\s+\$[\d.]+[KMB]?'
```

**Repeated list structures**: Bullet lists where each item has consistent data fields

For edge cases where regex is insufficient, use an LLM call to identify and extract tabular data patterns.

---

## Agent Architecture

### Input

```python
def table_generator(state: MemoState) -> dict:
    """
    Generate markdown tables from structured data and prose patterns.
    Insert tables into relevant sections with overflow anchor links.
    """
```

### Processing Steps

1. **Load table schemas** (outline YAML → custom templates → defaults)
2. **Collect structured data** from state (competitive landscape, deck, dataroom, research)
3. **Match data to table types** based on available data and schema definitions
4. **Scan prose** for additional tabular patterns not covered by structured data
5. **Generate tables** with proper formatting, overflow handling, and anchor links
6. **Insert tables** into section files at optimal positions
7. **Generate overflow detail sections** for columns with anchor links
8. **Save table artifacts** to output directory

### Output

```python
return {
    "tables_generated": {
        "tables": [
            {
                "id": "competitive-comparison",
                "type": "competitive_comparison",
                "inserted_in": "03-market-context.md",
                "rows": 5,
                "columns": 7,
                "overflow_anchors": ["sweet-defeat-investors", "sens-investors"]
            },
            # ...
        ],
        "total_tables": 4,
        "sections_updated": ["03-market-context.md", "04-organization.md", "07-funding-terms.md"]
    },
    "messages": ["Table generation complete: 4 tables inserted into 3 sections"]
}
```

---

## Output Artifacts

### Table Files

Each table is saved individually for debugging and reuse:

```
output/{Company}-v0.0.x/
├── 2-tables/                          # Table artifacts
│   ├── tables-manifest.json           # Index of all tables
│   ├── competitive-comparison.md      # Individual table files
│   ├── funding-history.md
│   ├── team-credentials.md
│   └── market-sizing.md
```

### Tables Manifest

```json
{
  "generated_at": "2026-03-10T10:30:00Z",
  "schema_source": "outline_yaml",
  "tables": [
    {
      "id": "competitive-comparison",
      "file": "competitive-comparison.md",
      "type": "competitive_comparison",
      "data_source": "competitive_landscape",
      "target_section": "03-market-context.md",
      "rows": 5,
      "columns": ["Company", "Founded", "Funding", "Stage", "Notable Investors", "Differentiator", "Overlap"],
      "overflow_columns": ["Notable Investors"],
      "inserted": true
    }
  ]
}
```

---

## Formatting Standards

### Markdown Syntax

```markdown
| Header 1 | Header 2 | Header 3 |
|:---------|:--------:|---------:|
| Left     | Center   |    Right |
```

### Number Formatting

- Currency: `$1.2M`, `$500K`, `$4.4T`
- Percentages: `45%`, `12.5%`
- Large numbers: `4M users`, `1.2B requests`
- Dates: `Q1 2023`, `2024`, `Mar 2024`

### Visual Hierarchy

- **Bold** the subject company row in comparison tables
- Right-align numeric columns
- Use consistent decimal precision within columns
- Include units in headers, not cells (e.g., "Revenue ($M)" not "$1M, $2M")

### Missing Values

- Use `—` (em dash) for missing cells, never leave blank
- Use `N/A` only when the field is known to not apply

---

## Edge Cases

### Insufficient Data
If fewer rows than `min_rows` (default: 3), skip table generation for that type. Keep data in prose only.

### Conflicting Sources
If multiple sources give different numbers for the same metric, use the most recent source with citation. Note the discrepancy in the table artifact file.

### Already Tabular
If data is already in a table in a section (from deck screenshots or prior processing), do not create a duplicate. Check for existing markdown table syntax before inserting.

### Very Wide Tables
If a table exceeds 7 columns, consider splitting into two tables or moving lower-priority columns to an overflow detail section.

---

## Interaction with Other Agents

### Competitive Landscape System
The competitive comparison table is the primary consumer of competitive landscape data. The table generator formats it; the competitive researcher and evaluator produce it.

### Citation Assembly
Tables may contain data that needs citations. The citation assembly agent (which runs later) should handle citations within table cells. Table cells with `[^N]` references are valid markdown.

### TOC Generator
If tables add new subsection headers (e.g., "#### Investor Details"), the TOC generator should capture these. Since the table generator runs before TOC, this works naturally.

### Revise Summary Sections
The summary revision agent runs after TOC and should be aware of tables when summarizing. Tables add information density that the summary should reflect.

---

## Implementation Priority

1. **Competitive comparison table**: Highest value, most requested by clients
2. **Funding history table**: Common data, straightforward extraction
3. **Team credentials table**: Enhances readability of team section
4. **Market sizing table**: TAM/SAM/SOM data benefits from tabular presentation
5. **Schema configuration system**: Allow firm customization
6. **Prose detection patterns**: Catch data not in structured sources

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Tables per memo | 3-6 for a complete memo |
| Competitive table present | 100% of memos with 3+ competitors |
| Overflow anchors working in HTML export | 100% |
| Overflow anchors working in PDF export | 95%+ |
| No duplicate data display (table + identical prose) in concise mode | 100% |
| Firm-specific schema loaded when available | 100% |

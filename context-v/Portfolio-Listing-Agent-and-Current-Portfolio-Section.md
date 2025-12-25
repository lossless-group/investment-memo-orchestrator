---
date_created: 2025-11-27
date_modified: 2025-11-27
publish: true
title: "Portfolio Listing Agent and Current Portfolio Section"
slug: portfolio-listing-agent-current-portfolio
at_semantic_version: 0.0.1.0
authors:
  - Michael Staton
augmented_with: "Claude Code (Cascade)"
site_uuid: d926a656-1323-456f-8b48-4195ca31d371
lede: "Design notes for the portfolio_listing_agent that builds a Current Portfolio subsection and structured JSON for LP-commit emerging manager fund memos."
---

# Portfolio Listing Agent and Current Portfolio Section

*Design and behavior of the `portfolio_listing_agent` that exhaustively enumerates current portfolio companies and wires them into the Portfolio Construction section for LP-commit emerging manager memos*

## Problem

For LP-commit / emerging manager fund memos, the Portfolio Construction section needs to:

- **Explicitly enumerate all current portfolio companies** that appear in the deck or dataroom
- **Avoid hallucinating names** or funds that are not actually listed in those materials
- Provide **short, consistent descriptions** and **links** for each company

Historically, this responsibility was left to generic section writers (research + writer agents) that:

- Often mentioned **one example company** ("representative investment") but did not list the full portfolio
- Were prone to **hallucinating company names** based on sector themes
- Produced **inconsistent detail** (some companies deeply described, others omitted)

We needed a dedicated agent that treats the portfolio list as a **first-class artifact** and a **source of truth**.

## High-Level Design

### Goals

- **Exhaustive enumeration** of all portfolio companies visible in internal materials (deck, state.json, dataroom-derived data)
- **Structured representation** saved as `current_portfolio.json`
- **Deterministic markdown subsection** `## Current Portfolio` injected into the Portfolio Construction section (`04-portfolio-construction.md`)
- **Link and logo enrichment** that stays grounded in already-listed companies

### Scope

The `portfolio_listing_agent` is **only** intended for:

- **Fund** memos (investment_type == "fund")
- **Emerging manager LP commit** outline: `outline: "lpcommit-emerging-manager"` in the company JSON

It should be **no-op** for:

- Direct company memos
- Other fund memo outlines that do not need exhaustive portfolio enumeration

## When the Agent Runs

### Trigger Condition

The agent is integrated into the enhancement workflow for fund memos and gated on the outline:

```python
if state.get("outline_name") == "lpcommit-emerging-manager":
    portfolio_listing_agent(state)
```

Notes:

- `outline_name` is populated from the company JSON field `outline` (e.g. `"lpcommit-emerging-manager"`).
- If `outline_name` is missing, we can safely derive it from `state["company_data"]["outline"]` when constructing `MemoState`.

### Position in Workflow

The intended ordering is:

1. **Deck / dataroom analysis** (if present) populates `deck_analysis` and any initial section drafts.
2. **Research agent** enriches `state["research"]`.
3. **Portfolio Listing Agent** reads `state`, the latest output directory, and constructs:
   - `current_portfolio.json`
   - `## Current Portfolio` subsection under Portfolio Construction
   - Calls `link_enrichment_agent` to add hyperlinks to portfolio companies
4. **Writer agent** can still refine the Portfolio Construction narrative, but the portfolio list is already present and should be treated as source-of-truth.

This ensures that:

- The agent has **maximum context** (deck, state.json, research.json) before running.
- The writer agent doesnt have to guess the portfolio list; it can refer to the structured artifact.

## Inputs and Data Sources

The agent reads from the same artifact stack used by other agents:

- **Company name** and metadata from `MemoState` / `data/<Company>.json`
- **State file**: `output/<Company>-vX.Y.Z/state.json`
  - Especially `deck_analysis` and any `portfolio`-like fields that already exist
- **Research file**: `output/<Company>-vX.Y.Z/1-research.json`
- **Existing sections**: `output/<Company>-vX.Y.Z/2-sections/*.md`

Within these, it looks for:

- Slide- or state-level references to specific portfolio companies
- Any already-structured portfolio data (e.g., lists of investments in deck analysis)
- Mentions of portfolio holdings in the existing Portfolio Construction section

The rule is: **only list companies that appear in the deck / internal materials or derived structured data**, never purely from web research.

## Outputs

### 1. `current_portfolio.json`

A structured artifact in the output version directory, with a schema along the lines of:

```json
{
  "fund_name": "Watershed VC",
  "as_of": "2025-04-03",
  "portfolio_companies": [
    {
      "name": "Watershed Health",
      "description": "Seed-stage health data platform for value-based care",
      "thematic_fit": "HealthCare / care delivery transformation",
      "stage": "Seed",
      "check_size": null,
      "initial_investment_date": null,
      "company_url": "https://...",
      "portfolio_page_url": "https://fund-site/portfolio/...",
      "logo_url": "https://.../logo.png",
      "notes": "Derived from deck; missing explicit round size."
    }
  ]
}
```

Design principles:

- Prefer **explicit values from the deck**; mark unknowns as `null` or `"Unknown"` rather than guessing.
- Include a short **50	6 character description** for each company, tuned for table/list usage in memos.
- Include **URLs** where possible:
  - Company site
  - Fund portfolio page entry
  - Logo URL (if discoverable)

### 2. Markdown Subsection: `## Current Portfolio`

The agent writes or updates a subsection inside `2-sections/04-portfolio-construction.md`:

- Heading: `## Current Portfolio`
- Body: markdown list or table of all `portfolio_companies` from `current_portfolio.json`
- Each row includes:
  - Company name (with markdown link when available)
  - Short description (50	6 characters)
  - Stage and thematic fit (if known)

This subsection is designed to satisfy the outlines **validation criteria** for Portfolio Construction:

- **EXHAUSTIVE list** of all current portfolio companies in the fund (as seen in deck/dataroom)
- **Per-company description** and link

### 3. Link Enrichment

After the markdown subsection is created/updated, `portfolio_listing_agent` invokes the existing `link_enrichment_agent` to:

- Add hyperlinks to the first mention of each portfolio company
- Prefer official company sites, fund portfolio pages, or authoritative profiles

Crucially, link enrichment is allowed to **add URLs**, but **not new company names**.

## Link and Logo Discovery Strategy

The agent follows a conservative enrichment strategy:

1. **Fund website portfolio pages**
   - Use `company_data["url"]` (e.g., `https://www.watershed.vc/`) as the base
   - Look for `/portfolio`, `/companies`, `/investments`, `/funds` paths
2. **Per-company portfolio entries**
   - From the fund site, identify individual company pages matching names from the deck
3. **Company websites and logos**
   - For each known company name, search for:
     - Official website
     - Logo asset URLs (png/svg/jpg)

If the agent cannot confidently match a URL to a company, it **leaves the URL fields blank** and does not invent.

## Safety and Anti-Hallucination Rules

To keep the portfolio list trustworthy:

- **No synthetic companies**
  - A company must be explicitly mentioned in the deck, dataroom-derived JSON, or existing internal state.
- **No synthetic allocations or outcomes**
  - Do not infer check sizes, ownership, or realized returns unless those numbers are explicitly present.
- **No overfitting to web research**
  - Web research is allowed to fill in missing URLs and logo paths, not to invent portfolio names.
- **Describe, dont overclaim**
  - Use short, factual descriptors ("Seed-stage cardiac monitoring platform"), not marketing language.

If input signals are weak or inconsistent, the agent should still:

- Produce a **minimal but explicit** `## Current Portfolio` subsection, possibly with notes that certain details are missing
- Avoid filling gaps with speculation

## Failure Modes and Degradation Behavior

### 1. Missing Output Directory / Artifacts

If the agent cannot find an existing output directory for the company (e.g., early in a pipeline, or an unexpected path issue):

- Log / print a message like: `"⊘ Portfolio listing skipped - no output directory found"`
- Return without raising, so the rest of the workflow continues

### 2. No Deck / No Portfolio Signals

If there is no deck, state.json, or research.json with identifiable portfolio companies:

- Write a **stub** `current_portfolio.json` with an empty `portfolio_companies` list
- Optionally add a short note in the `## Current Portfolio` subsection indicating that no current portfolio companies were identified in available materials
- Do **not** attempt to infer portfolio holdings from public web research alone

### 3. API / Network Failures for Enrichment

If link/logo enrichment fails (Anthropic/Perplexity/network issues):

- Leave `current_portfolio.json` in place with whatever structured data exists
- Keep the `## Current Portfolio` subsection without enriched links
- The memo remains usable; the portfolio list just has fewer conveniences

## Interaction with Outline and Validation

For `lpcommit-emerging-manager` outline, the outline file encodes:

- That Portfolio Construction must include an **exhaustive list of portfolio companies**
- That each company must have **short description + link + context** (stage, thematic fit)

The combination of:

- `portfolio_listing_agent` (structured enumeration and markdown) and
- Outline `validation_criteria` (content contract)

is intended to:

- Make the portfolio list **deterministic and repeatable** across runs
- Reduce the chance that later agents or edits accidentally **drop companies** or introduce **hallucinated holdings**

## Future Extensions

- Integrate more tightly with a **Portfolio Data MCP server** to:
  - Cross-check deck-derived portfolio against firms source-of-truth portfolio database
  - Flag discrepancies (e.g., deck mentions a company not in portfolio DB)
- Add **allocation-aware** views (e.g., % of capital by sector, geography), while still refusing to guess missing allocations
- Support **multi-fund complexes**, where one GP runs several vehicles and the memo must clarify which companies sit in which fund.

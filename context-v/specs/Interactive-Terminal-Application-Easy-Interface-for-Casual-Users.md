---
title: Interactive Terminal Application — Easy Interface for Casual Users
lede: A guided CLI application that walks users through memo generation, export, and iteration without requiring knowledge of individual commands, flags, or file paths.
date_authored_initial_draft: 2026-03-24
date_authored_current_draft: 2026-03-24
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-24
at_semantic_version: 0.0.0.1
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [CLI, UX, Terminal, Interactive, Rich, Onboarding]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A modern terminal application with colored panels, progress indicators, and interactive menus guiding a user through investment memo generation — polished and professional, not a raw command line.
date_created: 2026-03-24
date_modified: 2026-03-24
---

# Interactive Terminal Application — Easy Interface for Casual Users

**Status**: Draft (v0.0.1)
**Date**: 2026-03-24
**Author**: AI Labs Team

---

## Priority Feature: Integrate Content from Previous Versions

The most valuable feature this CLI enables — beyond convenience — is **human-in-the-loop content integration across versions**. Each pipeline run produces artifacts (research, sections, sources, fact-checks) that represent significant AI compute and, increasingly, human review. When re-running the pipeline, all of that prior work is discarded with `--fresh`. This is wasteful and frustrating.

The interactive CLI should offer an **"Integrate Content from Versions"** flow that lets users selectively carry forward, override, and curate content from prior runs.

### Source Selector (First Priority)

The Source Selector walks a user through every source the system has encountered across all versions of a deal, using the `3-source-catalog/` artifacts as the starting point.

**Flow:**

```
? Select firm: Humain Ventures
? Select deal: Metabologic

  Loading source catalog from v0.2.4...
  Found 42 sources across 7 sections

? How would you like to review sources?
  ❯ By section (walk through each section's sources)
    All sources (flat list, sorted by status)
    Only excluded sources (review what was removed)
    Only unverified sources (review uncertain ones)

── Section: Market Overview (8 sources) ──────────────

1/8  [INCLUDED] Goldman Sachs Research — GLP-1 Market Report
     URL: https://www.goldmansachs.com/insights/...
     Status: Valid (HTTP 200) · Cited 3 times

     ? Source action:
       ❯ ✓ Keep (no change)
         ⭐ Emphasize (prioritize in next run)
         ✗ Exclude (remove in next run)

2/8  [EXCLUDED — INVALID] McKinsey — Metabolic Health Market 2025
     URL: https://www.mckinsey.com/industries/healthcare/...
     Status: HTTP 404 · Was cited 2 times before removal

     ? Source action:
       ❯ ✗ Keep excluded
         🔄 Override: I found the real URL (enter new URL)
         ⭐ Emphasize: Source is real, URL just moved
         ? Maybe: Flag for re-check on next run

3/8  [EXCLUDED — HALLUCINATED] Fake Perplexity Source
     URL: https://www.nature.com/articles/XXXXX-fake-path
     Status: Hallucination pattern detected

     ? Source action:
       ❯ ✗ Keep excluded (confirmed hallucination)
         🔄 Override: This is actually real (enter correct URL)
```

**Source Designations:**

| Designation | Meaning | Effect on Next Run |
|-------------|---------|-------------------|
| **Emphasize** | High-value source, prioritize | Research agents explicitly seek this source; writer prioritizes citing it |
| **Keep** | Source is fine as-is | No change, included normally |
| **Maybe** | Uncertain, re-check | Validation agent re-checks URL; source included tentatively |
| **Exclude** | Do not use | Source filtered out before writer sees it |
| **Override URL** | Source is real but URL changed | User provides correct URL; source status flipped to valid |

**Output:**

The Source Selector saves a `{Company-Name}_source-curation.json` in the **deal root directory** — NOT inside any version folder. This is critical: the human's curation work persists across ALL subsequent pipeline runs. Once a user has reviewed sources, every future version of that deal benefits from their judgment.

```
io/humain/deals/Metabologic/
├── Metabologic.json              # Deal config
├── source-curation.json          # ← Human-curated source designations (persists across versions)
├── inputs/                       # Deck, dataroom
└── outputs/
    ├── Metabologic-v0.2.4/       # Version-specific artifacts
    └── Metabologic-v0.2.5/       # Next run reads source-curation.json automatically
```

```json
{
  "deal": "Metabologic",
  "curated_at": "2026-03-24T10:30:00",
  "curated_from_version": "v0.2.4",
  "sources": [
    {
      "url": "https://www.goldmansachs.com/insights/...",
      "designation": "emphasize",
      "notes": null
    },
    {
      "original_url": "https://www.mckinsey.com/industries/healthcare/old-path",
      "corrected_url": "https://www.mckinsey.com/industries/healthcare/new-path",
      "designation": "override",
      "notes": "URL moved, found via Google search"
    },
    {
      "url": "https://www.nature.com/articles/XXXXX-fake-path",
      "designation": "exclude",
      "notes": "Confirmed hallucination"
    }
  ]
}
```

**Pipeline Integration:**

On the next pipeline run, agents read `source-curation.json` and:
1. **Research agents**: Include "emphasized" source URLs in search queries; exclude "excluded" URLs
2. **Cleanup gates**: Skip validation for "override" sources (user confirmed they're real); use corrected URLs
3. **Writer**: Prioritize citing "emphasized" sources
4. **Source cataloger**: Carry forward designations, mark which are user-curated vs. AI-determined

### Competitive Landscape Review (Second Priority)

The Competitive Landscape Review walks a user through every competitor the system has identified across ALL previous versions of a deal. It merges `1-competitive-evaluation.json` from every version, deduplicates by company name/URL, and presents a unified list for human classification.

This is important because:
- The AI classifications (`direct_competitor`, `adjacent`, `indirect_competitor`) are rough guesses
- Different versions may discover different competitors — the union is more valuable than any single run
- Human judgment about competitive positioning is critical for the investment thesis
- Once classified, this becomes canonical data that shapes the competitive landscape section across all future versions

**Flow:**

```
? Select firm: Humain Ventures
? Select deal: Metabologic

  Loading competitive analysis from all versions...
  v0.2.1: 12 competitors
  v0.2.2: 15 competitors
  v0.2.4: 19 competitors
  Merged & deduplicated: 24 unique competitors

? How would you like to review?
  ❯ All competitors (walk through each)
    Only AI-classified as "direct" (review first)
    Only new since last curation
    By category (grouped by AI classification)

── Competitor 1/24 ────────────────────────────

  Enzymedica
  AI classified as: direct_competitor
  Description: Leading enzyme supplement brand focusing on
    digestive health and metabolic support
  Key differentiator: Broad enzyme supplement portfolio with
    established retail distribution
  Overlap: Competes for same consumer seeking enzyme-based
    metabolic improvement
  Funding: Unknown
  Website: enzymedica.com
  First seen: v0.2.1

  ? Classification:
    ❯ 🎯 Primary Competitor (head-to-head, same market)
      ⚔️  Direct Competitor (overlapping product/market)
      🏛️  Incumbent Nose (established player sniffing at this space)
      ↗️  Indirect Competitor (different approach, same customer need)
      🔄 Loose Comparable (similar-ish, useful for context)
      💡 Inspiration Set (admire their approach, not a threat)
      ✗  Not a Competitor (remove from landscape)

  ? Add notes? (optional)
  > "Largest enzyme supplement brand. $200M+ revenue.
     Key comparison for investor deck."

── Competitor 2/24 ────────────────────────────

  Twin Health
  AI classified as: indirect_competitor
  Description: AI-powered "metabolic twins" for drug-free
    diabetes reversal; raised $53M Feb 2026
  ...

  ? Classification:
    ❯ ↗️  Indirect Competitor
      (digital approach vs biological — different mechanism,
       same patient population)
```

**Competitor Designations:**

| Designation | Meaning | Use in Memo |
|-------------|---------|-------------|
| **Primary Competitor** | Head-to-head, same market, same customer, substitutable product | Featured prominently in competitive landscape section; direct comparison table |
| **Direct Competitor** | Overlapping product or market, but not identical | Listed in competitive section with differentiation analysis |
| **Incumbent Nose** | Established player (big pharma, big tech) that could enter this space | Mentioned as risk/moat consideration |
| **Indirect Competitor** | Different approach to the same customer need | Brief mention for market context |
| **Loose Comparable** | Useful for valuation comps or market sizing, not a real competitor | Used in funding/valuation context, not competitive section |
| **Inspiration Set** | Admire their GTM, tech, or business model; not a threat | May inform strategy discussion, not listed as competitor |
| **Not a Competitor** | AI was wrong, remove from landscape | Excluded from all future runs |

**Output:**

Saved as `{Company-Name}_competitive-curation.json` in the deal root directory:

```
io/humain/deals/Metabologic/
├── Metabologic.json                      # Deal config
├── Metabologic_source-curation.json      # Human-curated sources
├── Metabologic_competitive-curation.json # ← Human-curated competitive landscape
├── inputs/
└── outputs/
```

```json
{
  "deal": "Metabologic",
  "curated_at": "2026-03-24T11:00:00",
  "integrated_from_versions": ["v0.2.1", "v0.2.2", "v0.2.4"],
  "total_unique_competitors": 24,
  "competitors": [
    {
      "name": "Enzymedica",
      "website": "enzymedica.com",
      "ai_classification": "direct_competitor",
      "human_classification": "primary_competitor",
      "notes": "Largest enzyme supplement brand. $200M+ revenue. Key comparison for investor deck.",
      "first_seen_version": "v0.2.1",
      "description": "Leading enzyme supplement brand focusing on digestive health and metabolic support",
      "key_differentiator": "Broad enzyme supplement portfolio with established retail distribution"
    },
    {
      "name": "Twin Health",
      "website": "twinhealth.com",
      "ai_classification": "indirect_competitor",
      "human_classification": "indirect_competitor",
      "notes": null,
      "first_seen_version": "v0.2.2",
      "description": "AI-powered metabolic twins for drug-free diabetes reversal",
      "key_differentiator": "Digital twin technology vs biological intervention"
    },
    {
      "name": "Codexis Inc",
      "website": null,
      "ai_classification": "adjacent",
      "human_classification": "not_competitor",
      "notes": "B2B enzyme engineering for pharma manufacturing. Completely different customer.",
      "first_seen_version": "v0.2.4",
      "description": "Enzyme engineering for pharmaceuticals and industrial applications"
    }
  ]
}
```

**Pipeline Integration:**

On the next pipeline run, agents read `{Company-Name}_competitive-curation.json` and:
1. **Competitive researcher**: Skips companies marked "not_competitor"; focuses deeper research on "primary_competitor" and "direct_competitor"
2. **Competitive evaluator**: Uses human classifications instead of AI guesses; preserves human notes
3. **Writer**: Structures competitive landscape section using the human hierarchy — primary competitors get detailed comparison, indirect get brief mention, inspiration set informs strategy narrative
4. **Table generator**: Builds competitive comparison table using only primary + direct competitors
5. **One-pager**: Features primary competitors by name in the competitive positioning card

**Version Merging Logic:**

When loading competitors from multiple versions:
1. Scan all `outputs/*/1-competitive-evaluation.json` files
2. Deduplicate by company name (fuzzy match: "Twin Health" = "TwinHealth" = "twin health")
3. If the same competitor appears in multiple versions with different data, keep the most complete record (most non-null fields)
4. Track `first_seen_version` for each competitor
5. If a previous curation exists, carry forward human classifications and only prompt for NEW competitors not yet curated

### Table Proposals Review (Third Priority)

The Table Proposals flow runs the `table_generator` agent in a "propose" mode — it scans the memo sections and structured data, identifies opportunities for tabular presentation, and generates table drafts. The user then reviews each proposal interactively: approve, reject, edit column structure, or suggest a different table entirely.

This is valuable because:
- The AI identifies tabular data opportunities that humans miss (funding history buried in prose, team credentials scattered across paragraphs)
- But the AI also proposes tables that are wrong, redundant, or poorly structured
- Human review catches bad proposals before they pollute the memo
- Users can propose tables the AI didn't think of — "I want a comparison table of GLP-1 drugs vs. enzyme approaches"

**Flow:**

```
? Select firm: Humain Ventures
? Select deal: Metabologic (v0.2.4)

  Scanning sections and structured data for table opportunities...

  Found 6 table proposals:

? Review table proposals:
  ❯ Walk through all 6
    Only proposals for sections that don't have tables yet
    Skip — accept all AI proposals

── Table Proposal 1/6 ─────────────────────────

  📊 Funding History
  Target section: 06 Fundraising Round
  Data source: state.json (funding data) + deck analysis
  Rows: 2 rounds found

  Preview:
  ┌──────────┬──────────┬────────────┬──────────────────┐
  │ Round    │ Amount   │ Date       │ Lead Investor    │
  ├──────────┼──────────┼────────────┼──────────────────┤
  │ Pre-Seed │ $500K    │ 2025       │ Angel syndicate  │
  │ Seed     │ $3M      │ 2026       │ TBD              │
  └──────────┴──────────┴────────────┴──────────────────┘

  ? Action:
    ❯ ✓ Approve (insert into section)
      ✎ Edit columns (add/remove/rename)
      ✎ Edit data (correct values)
      ✗ Reject (don't insert)
      💡 Suggest different table for this section

── Table Proposal 2/6 ─────────────────────────

  📊 Competitive Comparison
  Target section: 03 Market Overview
  Data source: 1-competitive-evaluation.json + competitive curation
  Rows: 5 competitors (primary + direct only)

  Preview:
  ┌─────────────┬──────────────┬──────────┬───────────────────┐
  │ Company     │ Approach     │ Funding  │ Key Difference    │
  ├─────────────┼──────────────┼──────────┼───────────────────┤
  │ Enzymedica  │ Supplements  │ Private  │ Generic enzymes   │
  │ Twin Health │ AI/Digital   │ $53M     │ Behavioral, not   │
  │             │              │          │ biological        │
  │ Virta       │ Coaching     │ $100M+   │ Nutrition-only    │
  │ ZBiotics    │ Probiotics   │ Unknown  │ Alcohol, not      │
  │             │              │          │ metabolic health  │
  │ FODZYME     │ Enzyme supp  │ Unknown  │ Digestive-only    │
  └─────────────┴──────────────┴──────────┴───────────────────┘

  ? Action:
    ❯ ✓ Approve
      ✎ Edit columns
      ✗ Reject
      💡 Suggest different table

  ? Edit columns:
    Current: Company, Approach, Funding, Key Difference
    ❯ Add column: "Revenue"
      Add column: "Founded"
      Remove column: "Funding"
      Rename "Key Difference" → "Why We're Different"
      Done editing

── Table Proposal 3/6 ─────────────────────────

  📊 Key Metrics Summary
  Target section: 01 Overview (Executive Summary)
  Data source: state.json (traction + financial projections)

  Preview:
  ┌────────────────────┬─────────────────────────────┐
  │ Metric             │ Value                       │
  ├────────────────────┼─────────────────────────────┤
  │ Target CAC         │ <$300 via clinician referral │
  │ Projected LTV      │ $2,500 (3-year retention)   │
  │ Gross Margin       │ 85% post-scale              │
  │ Price Point        │ $60-120/month subscription  │
  │ Beta Target        │ 5,000 users, $2M ARR Q2 '27│
  └────────────────────┴─────────────────────────────┘

  ? Action: ✓ Approve

── No more AI proposals. ──────────────────────

? Would you like to suggest additional tables?
  ❯ Yes, I have an idea
    No, done reviewing

? Describe the table you want:
  > "Compare GLP-1 drugs (Ozempic, Wegovy, Mounjaro) vs Metabologic's
     enzyme approach on: mechanism, cost/month, prescription required,
     side effects, discontinuation rate"

  Generating custom table from your description...
  ● Researching via Perplexity Sonar Pro...

  Preview:
  ┌────────────┬──────────────┬──────────┬──────────┬──────────┐
  │ Treatment  │ Mechanism    │ Cost/Mo  │ Rx Req'd │ Discont. │
  ├────────────┼──────────────┼──────────┼──────────┼──────────┤
  │ Ozempic    │ GLP-1 agonist│ $1,000+  │ Yes      │ 85%/2yr  │
  │ Wegovy     │ GLP-1 agonist│ $1,300+  │ Yes      │ ~80%/2yr │
  │ Mounjaro   │ Dual GIP/GLP │ $1,100+  │ Yes      │ ~75%/2yr │
  │ Metabologic│ Enzyme design│ $60-120  │ No       │ TBD      │
  └────────────┴──────────────┴──────────┴──────────┴──────────┘

  ? Target section for this table:
    ❯ 03 Market Overview
      05 Business Economics
      Other (specify)

  ? Action: ✓ Approve
```

**Table Proposal Types:**

The agent proposes tables based on data it finds in structured artifacts:

| Proposal Type | Data Source | Typical Sections |
|---------------|------------|-----------------|
| Funding History | state.json funding data, deck | Fundraising Round |
| Team Credentials | state.json team data, deck | Team |
| Competitive Comparison | competitive-evaluation.json, competitive-curation.json | Market Overview |
| Market Sizing | state.json market data, research | Market Overview |
| Traction Metrics | state.json traction data | Business Economics, Overview |
| Key Metrics Summary | Aggregated from all sections | Overview (Executive Summary) |

User-suggested tables use Perplexity Sonar Pro to research the data in real time.

**Output:**

Table approvals and custom table specs are saved as `{Company-Name}_table-curation.json` at the deal root:

```
io/humain/deals/Metabologic/
├── Metabologic.json                      # Deal config
├── Metabologic_source-curation.json      # Human-curated sources
├── Metabologic_competitive-curation.json # Human-curated competitors
├── Metabologic_table-curation.json       # ← Human-reviewed table proposals
├── inputs/
└── outputs/
```

```json
{
  "deal": "Metabologic",
  "curated_at": "2026-03-24T12:00:00",
  "curated_from_version": "v0.2.4",
  "tables": [
    {
      "id": "funding_history",
      "status": "approved",
      "target_section": "06-fundraising-round",
      "columns": ["Round", "Amount", "Date", "Lead Investor"],
      "source": "ai_proposed",
      "edits": null
    },
    {
      "id": "competitive_comparison",
      "status": "approved",
      "target_section": "03-situation--market-overview",
      "columns": ["Company", "Approach", "Funding", "Revenue", "Why We're Different"],
      "source": "ai_proposed",
      "edits": ["added Revenue column", "renamed Key Difference"]
    },
    {
      "id": "glp1_vs_enzyme",
      "status": "approved",
      "target_section": "03-situation--market-overview",
      "columns": ["Treatment", "Mechanism", "Cost/Mo", "Rx Required", "Discontinuation Rate"],
      "source": "user_suggested",
      "description": "Compare GLP-1 drugs vs Metabologic enzyme approach",
      "research_needed": true
    },
    {
      "id": "key_metrics_summary",
      "status": "rejected",
      "reason": "Already covered in sidebar of one-pager"
    }
  ]
}
```

**Pipeline Integration:**

On the next pipeline run, the `table_generator` agent reads `{Company-Name}_table-curation.json` and:
1. **Approved tables**: Generates and inserts without re-proposing
2. **Rejected tables**: Skips, does not regenerate
3. **Edited tables**: Uses the human-specified column structure
4. **User-suggested tables**: Calls Perplexity for data, then generates the table
5. **New proposals**: If the agent finds a new opportunity not in the curation file, it generates normally (will be reviewed next time the user runs the table review flow)

### Future Integration Features (Not Yet Specified)

These flows would also live under "Integrate Content from Versions":

- **Section Selector**: Walk through sections from a prior version, mark which to keep vs. regenerate
- **Fact-Check Review**: Walk through fact-check findings, confirm or dispute each, carry forward verified facts
- **Research Merger**: Combine research from multiple versions, dedup, and create a unified research base for the next run
- **Best-Of Assembly**: Select the best section from each version (e.g., v0.2.2's Team section was better than v0.2.4's) and assemble a composite memo

---

## Problem

The system currently has ~15 CLI commands spread across `src/main.py`, `cli/generate_one_pager.py`, `cli/generate_tables.py`, `cli/export_branded.py`, `cli/assemble_draft.py`, `cli/md2docx.py`, `improve-section.py`, and more. Each requires knowing:

- The exact command and module path
- Required flags (`--firm`, `--brand`, `--mode`, `--version`, `--fresh`)
- File paths to output directories, final drafts, or section files
- Which commands depend on which (e.g., you can't export before generating)

For the person who built the system, this is fine. For a partner, associate, or collaborator who just wants to generate a memo and get a PDF, it's hostile.

---

## Goal

A single entry point that guides users through every operation via interactive prompts:

```bash
python -m cli.app
```

No flags, no file paths, no command knowledge required. The application discovers available firms, deals, versions, and output states automatically and presents contextual options.

---

## User Flows

### Flow 1: New User / First Run

```
┌─────────────────────────────────────────────┐
│  Investment Memo Orchestrator  v0.5.2       │
│  33 agents · Powered by Claude + Perplexity │
└─────────────────────────────────────────────┘

? What would you like to do?
  ❯ 📝 Generate a new investment memo
    📄 Generate a one-pager summary
    📤 Export an existing memo (HTML / PDF / Word)
    🔧 Improve a specific section
    📊 Run a specific agent on existing output
    ⚙️  Configure settings
```

### Flow 2: Generate New Memo

```
? Select firm:
  ❯ Humain Ventures (3 deals)
    Hypernova Capital (5 deals)
    + Configure a new firm

? Select deal:
  ❯ Metabologic (latest: v0.2.4, last run: 2026-03-23)
    ProfileHealth (latest: v0.1.0, last run: 2026-03-15)
    + Set up a new deal

? Metabologic has existing output at v0.2.4. What would you like to do?
  ❯ Generate fresh (v0.2.5, clean slate)
    Resume from v0.2.4
    Start at a specific version number

? Confirm settings:
  ┌─────────────────────────────────┐
  │ Company:  Metabologic           │
  │ Firm:     Humain Ventures       │
  │ Type:     Direct Investment     │
  │ Mode:     Prospective (consider)│
  │ Version:  v0.2.5 (fresh)       │
  │ Deck:     ✓ Found               │
  │ Dataroom: ✓ Found (17 files)    │
  └─────────────────────────────────┘

? Start generation? (Y/n)

  Running pipeline...
  ✓ Dataroom analysis (35s)
  ✓ Deck analysis (12s)
  ● Research (searching...)          ← live spinner
  ○ Section research
  ○ Competitive landscape
  ... (remaining agents listed, dimmed)
```

### Flow 3: Export Existing Memo

```
? Select firm: Humain Ventures
? Select deal: Metabologic
? Select version: v0.2.4 (latest)

? What would you like to export?
  ❯ Full memo (HTML + PDF)
    One-pager summary
    Word document (.docx)
    All formats

? Export mode:
  ❯ Light mode
    Dark mode
    Both

  Exporting...
  ✓ HTML (light): Metabologic-v0.2.4.html
  ✓ PDF (light):  Metabologic-v0.2.4.pdf

? Open in browser? (Y/n)
```

### Flow 4: Improve a Section

```
? Select firm: Humain Ventures
? Select deal: Metabologic (v0.2.4)

? Which section would you like to improve?
  ❯ 01 Overview
    02 Why Invest
    03 Market Overview
    04 Team
    05 Business Economics
    06 Fundraising Round
    07 Flags

? Improvement approach:
  ❯ Enrich with Perplexity (add citations, metrics)
    Rewrite with better sourcing
    Add specific information (you provide context)

  Improving section: 03 Market Overview
  ● Calling Perplexity Sonar Pro...
  ✓ Section improved (11 new citations)
  ✓ Final draft reassembled
```

### Flow 5: Run Specific Agent

```
? Select firm: Humain Ventures
? Select deal: Metabologic (v0.2.4)

? Which agent would you like to run?
  ── Data Gathering ──
    Dataroom analyzer
    Deck analyst
    Research (web search)
  ── Enrichment ──
    Table generator
    Diagram generator
    Link enrichment
    Social links
  ── Validation ──
    Fact checker → Verifier → Corrector
    Citation validator
    Citation spacing fix
  ── Assembly & Export ──
    Assemble final draft
    Generate Table of Contents
    Generate one-pager
    Export (HTML/PDF/Word)
  ── Scoring ──
    Quality validator
    12Ps Scorecard
```

---

## Discovery & Auto-Detection

The app should automatically discover:

### Firms
Scan `io/` for firm directories. Each subdirectory with a `deals/` folder is a firm.

```python
firms = [d.name for d in Path("io").iterdir()
         if d.is_dir() and (d / "deals").exists()]
```

### Deals
Scan `io/{firm}/deals/` for deal directories. Each with a `{DealName}.json` is a configured deal.

```python
deals = [d.name for d in (Path("io") / firm / "deals").iterdir()
         if d.is_dir() and list(d.glob("*.json"))]
```

### Versions & State
Scan `io/{firm}/deals/{deal}/outputs/` for version directories. Read `state.json` for metadata.

### Available Sections
Read `2-sections/*.md` file listing for section improvement flow.

### Available Agents
Hardcoded registry mapping display names to agent functions/CLI commands.

---

## Progress Display During Pipeline

The pipeline has 33+ agents. The progress display should show:

1. **Completed agents** with checkmarks and elapsed time
2. **Current agent** with a live spinner and description
3. **Remaining agents** listed but dimmed
4. **Overall progress** bar or fraction (e.g., "12/33 agents")

```
Pipeline Progress (12/33)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Dataroom analysis          35.2s
✓ Deck analysis              12.1s
✓ Research (web search)      45.3s
✓ Section research           82.4s
✓ Competitive researcher     23.1s
✓ Competitive evaluator      18.7s
✓ Citation enrichment        31.2s
✓ Research cleanup            4.3s
✓ Writer (10 sections)      124.5s
✓ Inject deck images          2.1s
✓ Trademark enrichment        0.8s
● Social links enrichment    ...
○ Link enrichment
○ Table generator
○ Diagram generator
  ... (18 more)
```

### Implementation Note

LangGraph doesn't provide per-node callbacks out of the box. Options:
- **Wrapper pattern**: Wrap each agent function to print status before/after
- **State-based**: Each agent appends to `state["messages"]`, monitor from outside
- **Custom callback handler**: LangGraph supports custom callbacks via `config`

---

## Error Handling & Recovery

The app should handle common failures gracefully:

| Error | Response |
|-------|----------|
| Missing API key | "ANTHROPIC_API_KEY not set. Add it to .env or export it." |
| Missing dependencies | "WeasyPrint not installed. Run: uv pip install -e ." |
| No deals configured | "No deals found for Humain Ventures. Set up a new deal?" |
| Agent failure mid-pipeline | Show error, offer to resume from last successful agent |
| Network timeout | "Perplexity API timed out. Retry? (Y/n)" |

---

## Post-Run Summary

After any operation completes, show a summary with next steps:

```
┌─────────────────────────────────────────────┐
│  ✓ Memo Generated: Metabologic v0.2.5      │
│                                             │
│  Score:     4.5/10 (needs revision)         │
│  Scorecard: 3.2/5                           │
│  Citations: 38 (25 verified)                │
│  Sources:   42 cataloged across 7 sections  │
│                                             │
│  Output: io/humain/deals/Metabologic/       │
│          outputs/Metabologic-v0.2.5/        │
│                                             │
│  Artifacts:                                 │
│    7-Metabologic-v0.2.5.md (final draft)    │
│    8-one-pager.html + .pdf                  │
│    3-source-catalog/ (7 files)              │
│    4-fact-check-verified.json               │
│    5-scorecard/12Ps-scorecard.md            │
└─────────────────────────────────────────────┘

? What next?
  ❯ Export this memo (HTML/PDF/Word)
    Improve a weak section
    View fact-check results
    Generate one-pager
    Return to main menu
    Exit
```

---

## Technical Architecture

### Entry Point

```bash
python -m cli.app          # Interactive mode (default)
python -m cli.app --help   # Show available non-interactive commands
```

### Dependencies

| Library | Purpose | Status |
|---------|---------|--------|
| `rich` | Panels, tables, spinners, progress, colors | Already installed |
| `questionary` or `InquirerPy` | Interactive prompts (select, confirm, text) | Needs install |
| Everything else | Existing pipeline code | Already installed |

### Module Structure

```
cli/
├── app.py                  # Main entry point, top-level menu
├── flows/
│   ├── generate.py         # New memo generation flow
│   ├── export.py           # Export flow (HTML/PDF/Word)
│   ├── improve.py          # Section improvement flow
│   ├── one_pager.py        # One-pager generation flow
│   ├── agent_runner.py     # Run specific agent flow
│   └── configure.py        # Settings and new deal setup
├── discovery.py            # Auto-detect firms, deals, versions
├── progress.py             # Pipeline progress display
└── theme.py                # Colors, branding, styling constants
```

### Theme Constants

```python
# cli/theme.py
BRAND_COLOR = "#51A084"      # Accent (matches Humain's Lochinvar)
PRIMARY_COLOR = "#090E18"    # Dark
SECONDARY_COLOR = "#656F84"  # Muted text
SUCCESS = "green"
WARNING = "yellow"
ERROR = "red"
DIM = "dim"
```

---

## Implementation Phases

### Phase 1: Core Shell + Generate Flow
- `cli/app.py` with main menu
- `cli/discovery.py` for firm/deal/version detection
- Generate flow with confirm and live progress
- Post-run summary

### Phase 2: Export + One-Pager Flows
- Export flow wrapping `cli/export_branded.py` and `cli/md2docx.py`
- One-pager flow wrapping `cli/generate_one_pager.py`
- "Open in browser" option after HTML export

### Phase 3: Improve + Agent Runner
- Section improvement flow wrapping `improve-section.py`
- Agent runner with categorized agent menu
- Resume-from-failure support

### Phase 4: Configuration
- New deal setup wizard (creates `{DealName}.json` from prompts)
- New firm setup (creates `io/{firm}/` directory structure)
- API key configuration
- Default settings (model, strictness, etc.)

---

## Open Questions

1. **Python or Node for the shell?** Rich + questionary is native Python and works today. clack (Node) is prettier but requires a bridge to call Python commands. Hybrid possible: Node shell that spawns Python subprocesses.

2. **Should the app replace `src/main.py`?** Currently `src/main.py` is the CLI entry point for generation. The app could wrap it, or `src/main.py` could become a library function called by the app.

3. **Pipeline progress granularity**: LangGraph doesn't expose per-node progress natively. We need to decide between wrapper functions (invasive but precise) vs. message monitoring (non-invasive but less real-time).

4. **Configuration persistence**: Should the app remember the last firm/deal selected? A `.cli-state.json` in the project root could store recent selections for faster repeat runs.

5. **Multi-deal batch mode**: Should the app support "Generate memos for all deals in Humain"? This is a power-user feature but valuable for firms with many deals.

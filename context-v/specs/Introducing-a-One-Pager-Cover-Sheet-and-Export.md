---
title: Introducing a One-Pager Cover Sheet and Export
lede: A post-pipeline agent and CLI tool that distills the full investment memo into a single-page visual summary, usable as both a standalone deliverable and a cover sheet prepended to the full memo export.
date_authored_initial_draft: 2026-03-23
date_authored_current_draft: 2026-03-23
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-23
at_semantic_version: 0.0.0.1
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Agent-Design, One-Pager, Export, PDF, Cover-Sheet, Branding]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A polished single-page investment summary with a sidebar showing deal terms, a main area with headline thesis and market stats, company logos, and a branded footer — printed on crisp white paper next to the thicker full memo it accompanies.
date_created: 2026-03-23
date_modified: 2026-03-23
---

# Introducing a One-Pager Cover Sheet and Export

**Status**: Draft (v0.0.1)
**Date**: 2026-03-23
**Author**: AI Labs Team
**Related**: Ideal-Orchestration-Agent-Workflow.md, export_branded.py, base-style.css
**Reference**: io/hypernova/deals/10SQ/10SQ-Teaser-11.30.25.pdf (visual reference for layout)

---

## Executive Summary

Investment professionals frequently need a single-page summary that captures the essence of a deal — the thesis, key metrics, deal terms, market context, and recommendation — without reading the full 15-30 page memo. This one-pager serves two purposes:

1. **Standalone deliverable**: A PDF or HTML document shared with partners, LPs, or co-investors as a deal teaser or screening document.
2. **Cover sheet**: Prepended to the full memo export as a visual executive summary, so readers can decide whether to read the full document.

The one-pager is generated from the same artifact trail as the full memo. No new research is needed — it's a distillation and layout exercise.

---

## Goals

1. **Distill** the full memo into fixed content slots using an LLM (narrow extraction task, not creative writing)
2. **Layout Design and Information Architecture** the distilled information needs to be codified in a clever and visually appealing layout, which will involve information hierarchy and appropriate sizing and shaping of layout
3. **Render** the content into a branded single-page HTML template with CSS grid layout
4. **Export** as standalone PDF and HTML, and optionally prepend to the full memo PDF
5. **Reuse** the existing brand config system (`--brand-*` CSS variables, firm logos, fonts)
6. **Support** various template outlines/scorecards for both direct investment and fund commitment memo types with different sidebar fields

---

## Visual Layout

Based on the 10SQ teaser reference (io/hypernova/deals/10SQ/10SQ-Teaser-11.30.25.pdf):

```
┌──────────────────┬──────────────────────────────────────┐
│                  │                                      │
│  COMPANY LOGO    │  HEADLINE THESIS (1-2 sentences)     │
│  Company Name    │  ────────────────────────────────     │
│  Tagline         │  * Key bullet 1 (bold key terms)     │
│                  │  * Key bullet 2                       │
│  ──────────────  │  * Key bullet 3                       │
│                  │                                      │
│  DEAL OVERVIEW:  ├──────────────────────────────────────│
│                  │                                      │
│  STAGE:          │  MARKET OPPORTUNITY HEADER            │
│    Series A      │  ┌────────────┬─────────────────────┐│
│                  │  │ Category   │ Market stat + source ││
│  ROUND SIZE:     │  │ Category   │ Market stat + source ││
│    $5M           │  │ Category   │ Market stat + source ││
│                  │  │ Category   │ Market stat + source ││
│  VALUATION:      │  └────────────┴─────────────────────┘│
│    $25M pre      │                                      │
│                  │  COMPETITIVE POSITIONING              │
│  LEAD INVESTOR:  │  (logos or brief landscape summary)   │
│    Firm Name     │                                      │
│                  │  SYNDICATE PARTICIPANTS               │
│  LOCATION:       │  Firm A | Firm B | Firm C | Firm D    │
│    City, State   │  (investor logos or names in pills)   │
│                  │                                      │
│  TEAM:           │  ┌──────────────────────────────────┐│
│    X people      │  │ KEY INSIGHT / RECOMMENDATION     ││
│                  │  │ Bold callout box with thesis     ││
│  KEY METRICS:    │  │ summary or recommendation        ││
│    ARR: $X       │  └──────────────────────────────────┘│
│    Growth: X%    │                                      │
│                  │  Sources: abbreviated source list     │
│  ──────────────  │                                      │
│                  │                                      │
│  CAP TABLE       │                                      │
│  HIGHLIGHTS:     │                                      │
│    Founders: X%  │                                      │
│    Investors: Y% │                                      │
│    Option Pool:  │                                      │
│      Z%          │                                      │
│                  │                                      │
├──────────────────┴──────────────────────────────────────│
│  VC FIRM LOGO  |  Contact  |  Website  |  Confidential  │
└─────────────────────────────────────────────────────────┘
```

### Layout Variant B: Card-Based Grid

An alternative layout where the main area uses a 2-column card grid. Each card is a self-contained information block with a colored label header (accent background) and fixed-height content body. The sidebar also becomes cards. This creates visual rhythm and lets the eye jump between topics.

```
┌──────────────────┬──────────────────────────────────────┐
│                  │                                      │
│  COMPANY LOGO    │  HEADLINE THESIS                     │
│  Company Name    │  * Bullet 1  * Bullet 2  * Bullet 3  │
│  Tagline         │                                      │
│                  ├──────────────────────────────────────│
│  ──────────────  │                                      │
│                  │  ┌─────────────┐  ┌─────────────────┐│
│  DEAL OVERVIEW   │  │ MARKET      │  │ TECHNOLOGY &    ││
│  ┌────────────┐  │  │ OPPORTUNITY │  │ PRODUCT         ││
│  │ Stage      │  │  │             │  │                 ││
│  │ Series A   │  │  │ TAM: $50B   │  │ AI-engineered   ││
│  │            │  │  │ CAGR: 25%   │  │ enzymes for     ││
│  │ Round      │  │  │ Key driver  │  │ metabolic       ││
│  │ $5M        │  │  │ Key driver  │  │ optimization    ││
│  │            │  │  └─────────────┘  └─────────────────┘│
│  │ Valuation  │  │                                      │
│  │ $25M pre   │  │  ┌─────────────┐  ┌─────────────────┐│
│  │            │  │  │ COMPETITIVE │  │ TRACTION &      ││
│  │ Lead       │  │  │ LANDSCAPE   │  │ MILESTONES      ││
│  │ Firm Name  │  │  │             │  │                 ││
│  └────────────┘  │  │ Blue ocean  │  │ • Milestone 1   ││
│                  │  │ positioning │  │ • Milestone 2   ││
│  ┌────────────┐  │  │ vs X, Y, Z  │  │ • Milestone 3   ││
│  │ KEY        │  │  └─────────────┘  └─────────────────┘│
│  │ METRICS    │  │                                      │
│  │            │  │  ┌─────────────────────────────────┐ │
│  │ ARR: $X    │  │  │ SYNDICATE & CAP TABLE           │ │
│  │ Growth: X% │  │  │ Firm A | Firm B | Firm C        │ │
│  └────────────┘  │  │ (see cap table variants below)  │ │
│                  │  └─────────────────────────────────┘ │
│  ┌────────────┐  │                                      │
│  │ CAP TABLE  │  │  ┌─────────────────────────────────┐ │
│  │ HIGHLIGHTS │  │  │ ★ RECOMMENDATION                │ │
│  │            │  │  │ Bold callout with thesis and    │ │
│  │ Fndrs: X%  │  │  │ investment recommendation       │ │
│  │ Inv:   Y%  │  │  └─────────────────────────────────┘ │
│  │ Pool:  Z%  │  │                                      │
│  └────────────┘  │  Sources: abbreviated source list    │
│                  │                                      │
├──────────────────┴──────────────────────────────────────│
│  VC FIRM LOGO  |  Contact  |  Website  |  Confidential  │
└─────────────────────────────────────────────────────────┘
```

### Syndicate & Cap Table Card Variants

The syndicate/cap table section can be rendered in several ways depending on data density and visual preference. These are options to iterate on.

**Variant 1: Bar chart with percentages**

```
┌─────────────────────────────────────┐
│ SYNDICATE & CAP TABLE               │
│                                     │
│ PARTICIPANTS:                       │
│ Firm A | Firm B | Firm C | Firm D   │
│                                     │
│ CAP TABLE:                          │
│ Founders ████████████████░░  62%    │
│ Firm A   ██████░░░░░░░░░░░░  18%   │
│ Firm B   ████░░░░░░░░░░░░░░  12%   │
│ Option   ███░░░░░░░░░░░░░░░   8%   │
└─────────────────────────────────────┘
```

Best when: Cap table data is available from dataroom extraction. Visual, scannable. The bars make ownership proportions immediately obvious.

**Variant 2: Combined table with role indicators**

```
┌─────────────────────────────────────┐
│ SYNDICATE & CAP TABLE               │
│                                     │
│ Firm A (Lead)              18%      │
│ Firm B                     12%      │
│ Firm C                      5%      │
│ Firm D                      3%      │
│ Founders                   54%      │
│ Option Pool                 8%      │
└─────────────────────────────────────┘
```

Best when: Clean, minimal. Works when exact percentages are available. Good for seed/Series A where the table is simple.

**Variant 3: Pill layout (participants only, no percentages)**

```
┌─────────────────────────────────────┐
│ SYNDICATE PARTICIPANTS              │
│                                     │
│ ┌──────────┐ ┌──────────┐          │
│ │ Firm A   │ │ Firm B   │          │
│ │ (Lead)   │ │          │          │
│ └──────────┘ └──────────┘          │
│ ┌──────────┐ ┌──────────┐          │
│ │ Firm C   │ │ Firm D   │          │
│ └──────────┘ └──────────┘          │
└─────────────────────────────────────┘
```

Best when: Cap table data is not available (common for pre-seed/seed). Shows who's involved without ownership detail.

**Variant 4: Sidebar summary + main area detail**

Cap table highlights live in the sidebar as a summary card (Founders: X%, Investors: Y%, Pool: Z%), while the main area syndicate card shows the per-firm breakdown. This avoids duplicating information and uses each column for what it does best — sidebar for at-a-glance numbers, main area for detail.

### Type Scale

Sizing must balance eye-popping clarity with enough detail. The reader should get the thesis in 3 seconds (headline + bullets), deal terms in 5 seconds (sidebar scan), and market context in 15 seconds (stats cards).

| Element | Size | Weight | Max Lines | Notes |
|---------|------|--------|-----------|-------|
| Headline thesis | 16pt | 700 | 2 | Largest text on the page after logo |
| Key bullets | 11pt | 400 | 2 each | Bold key terms inline |
| Card headers | 8pt | 700 uppercase | 1 | Accent background, contrasting text |
| Card body text | 9pt | 400 | varies | Fixed card height, overflow hidden |
| Bold figures in cards | 11pt | 700 | inline | Numbers pop: "$50B", "25% CAGR" |
| Sidebar labels | 7pt | 700 uppercase | 1 | e.g., "STAGE:", "ROUND SIZE:" |
| Sidebar values | 10pt | 400 | 1-2 | e.g., "Series A", "$5M" |
| Recommendation callout | 10pt | 600 | 3 | Accent border or background |
| Sources footer | 7pt | 400 | 1 | Abbreviated, low visual weight |
| Footer | 7pt | 400 | 1 | Logo + contact + confidential |

These sizes are starting points — they will be tuned during visual iteration with real deal data (Metabologic v0.2.4).

### Layout Principles

- **Single page**: Must fit on one US Letter page (8.5" x 11") or A4 when exported to PDF. Content truncates rather than overflows.
- **Two-column**: Left sidebar (~30% width) for structured deal data. Right main area (~70%) for narrative and visual elements.
- **Card-based**: Main area uses a card grid. Each card has a label header and dense content body. Cards create visual rhythm.
- **Information density**: Every element earns its space. No filler, no decorative whitespace beyond readability.
- **Brand-aware**: Uses `--brand-primary`, `--brand-secondary`, `--brand-text-*` variables. Inherits firm logo from brand config.
- **Company trademark**: The company/fund logo appears in the sidebar (from `trademark_light` / `trademark_dark` in company JSON).
- **VC firm logo**: Appears in the footer (from brand config `logo.*`).
- **Fixed heights, not flexible**: Cards and zones have max heights. Content that exceeds is truncated, not wrapped to a second page.

---

## Content Slots

The LLM's job is to extract/compress the full memo into these fixed slots. No layout decisions — just content.

### Direct Investment Slots

| Slot | Source | Max Length |
|------|--------|-----------|
| **Headline thesis** | Executive Summary first paragraph | 2 sentences |
| **Key bullets** (3) | Executive Summary + Investment Thesis | ~30 words each |
| **Stage** | state.json `company_stage` | 1-2 words |
| **Round size** | Funding & Terms section | e.g., "$5M" |
| **Valuation** | Funding & Terms section | e.g., "$25M pre-money" |
| **Lead investor(s)** | Funding & Terms section | 1-2 names |
| **Location** | state.json or Business Overview | City, State |
| **Team size** | Team section | e.g., "12 people" |
| **Key metrics** (2-4) | Traction section | Label: Value pairs |
| **Market stats** (4-6) | Market Context section | Category + stat + bold figure |
| **Competitive positioning** | Competitive landscape or Technology section | 2-3 sentences or logo grid |
| **Recommendation** | Recommendation section | 1-2 sentences, bold callout |
| **Sources** | Top 3-5 citation sources | Abbreviated titles |

### Fund Commitment Slots

| Slot | Source | Max Length |
|------|--------|-----------|
| **Headline thesis** | Executive Summary | 2 sentences |
| **Key bullets** (3) | Fund Strategy & Thesis | ~30 words each |
| **Target fund size** | Fee Structure & Economics | e.g., "$50MM" |
| **GP commit** | Fee Structure & Economics | e.g., "5%" |
| **Fund term** | Fee Structure & Economics | e.g., "10 years" |
| **Fees** | Fee Structure & Economics | e.g., "2/20" |
| **Investment period** | Fee Structure & Economics | e.g., "5 years" |
| **Location** | GP Background | City, State |
| **Governance** | LP Base & References | e.g., "3-Member LPAC" |
| **Market stats** (4-6) | Fund Strategy & Thesis | Category + stat |
| **Track record highlights** | Track Record Analysis | 2-3 key metrics |
| **Recommendation** | Recommendation section | 1-2 sentences |
| **Sources** | Top 3-5 citation sources | Abbreviated |

---

## Implementation Plan

### Phase 1: HTML Template + CSS

Create `templates/one-pager-template.html` with:
- CSS grid layout (sidebar + main)
- `@page` rules for single-page PDF rendering (no overflow, no page break)
- `--brand-*` CSS variable integration (same variables as base-style.css)
- Placeholder slots as `{{slot_name}}` for Python string substitution
- Print-optimized: no scrolling, fixed dimensions

The template should be self-contained (inline CSS, no external dependencies) so it renders identically in browsers and WeasyPrint.

### Phase 2: Content Extraction Agent

Create `src/agents/one_pager_generator.py`:

```python
def one_pager_generator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Reads the final draft + state.json, uses Claude to extract content
    into fixed slots, renders HTML from template, converts to PDF.

    Output: 8-one-pager.html + 8-one-pager.pdf in output directory.
    """
```

**LLM prompt design**: The prompt gives Claude the full memo text and asks it to fill a JSON schema with the content slots. This is extraction/compression, not creative writing. The prompt should emphasize:
- Use exact numbers and names from the memo (no rounding, no paraphrasing metrics)
- If a slot's data is not available, return `null` (template hides empty slots)
- Maximum lengths are hard limits — truncate if needed
- Do not add information not present in the memo

**Rendering**: Python reads the HTML template, substitutes `{{slot_name}}` values, applies brand CSS variables, and writes the final HTML. WeasyPrint converts to PDF.

### Phase 3: CLI Tool

Create `cli/generate_one_pager.py`:

```bash
# From completed output directory
python -m cli.generate_one_pager "Metabologic" --firm humain

# Direct path
python -m cli.generate_one_pager io/humain/deals/Metabologic/outputs/Metabologic-v0.2.4

# With brand override
python -m cli.generate_one_pager "Metabologic" --brand humain --mode dark

# Prepend to existing memo PDF
python -m cli.generate_one_pager "Metabologic" --prepend
```

### Phase 4: Pipeline Integration

Add `one_pager` node to workflow after `integrate_scorecard`, before `finalize`:

```
... → integrate_scorecard → one_pager → finalize | human_review → END
```

The one-pager runs last (after scorecard integration) so it has access to the complete, final version of all content.

### Phase 5: Cover Sheet Mode

Add `--prepend` flag to `cli/export_branded.py` that:
1. Checks if `8-one-pager.pdf` exists in the output directory
2. Uses PyPDF2 or pikepdf to prepend it to the full memo PDF
3. Outputs a combined PDF: `{Deal}-v{Version}-with-cover.pdf`

This keeps the one-pager and full memo as separate artifacts that can be optionally combined.

---

## Artifact Output

```
output/{Deal}-{Version}/
├── 8-one-pager.html          # Standalone one-pager HTML
├── 8-one-pager.pdf           # Standalone one-pager PDF
└── 8-one-pager-content.json  # Extracted content slots (for debugging/iteration)
```

When `--prepend` is used during export:
```
exports/{mode}/
├── {Deal}-{Version}.html           # Full memo
├── {Deal}-{Version}.pdf            # Full memo PDF
└── {Deal}-{Version}-with-cover.pdf # One-pager + full memo combined
```

---

## Design Decisions

### Why a fixed HTML template, not LLM-generated layout?

LLMs are unreliable at visual layout. They can extract and compress content well, but asking them to produce a visually polished single-page design leads to inconsistent results. By using a fixed template with CSS grid, we get:
- Pixel-perfect consistency across all deals
- Brand compliance (same CSS variables as full memo)
- Predictable PDF rendering via WeasyPrint
- Easy iteration on layout without re-running the LLM

### Why extract content via LLM instead of regex?

The content slots require judgment: "What are the 3 most compelling bullets from a 5-page executive summary?" Regex can find metrics, but selecting the *most relevant* ones for a one-pager requires understanding the investment thesis. The LLM reads the full memo and picks what matters.

### Why `8-one-pager` numbering?

The artifact numbering follows the pipeline sequence:
- `7-{Deal}-{Version}.md` is the final draft
- `8-one-pager.*` is derived from the final draft
- This preserves the artifact trail ordering: research → sections → validation → draft → one-pager

### Why separate from the full memo export?

The one-pager has fundamentally different CSS (single-page grid layout vs. flowing document). Trying to embed it as the first page of the memo HTML would create CSS conflicts. Keeping them separate and optionally combining at the PDF level (page concatenation) is cleaner.

---

## Open Questions

1. **Company logos in the sidebar**: Should we support both URL and local path logos (like trademark enrichment does), or require URLs? Local SVG embedding adds complexity but works offline.

2. **Competitive landscape visualization**: The 10SQ example shows an "Industries" sidebar with category pills. For direct investments, should we show competitor logos, a mini comparison table, or a text summary? This depends on what data the competitive landscape agents produce.

3. **Scorecard integration**: Should the one-pager include the 12Ps scorecard score (e.g., "Scorecard: 3.2/5") as a summary metric? This could be valuable for screening but might be premature for external-facing teasers.

4. **Template variants**: Should there be separate templates for direct investment vs. fund commitment, or one template with conditional sections? The sidebar fields differ significantly between the two types.

5. **Font sizing for single-page fit**: With dense content, font sizes may need to shrink dynamically. Should we use CSS `clamp()` for responsive sizing, or set fixed small sizes and let content truncate?

---

## Related Documents

- `context-v/reminders/Ideal-Orchestration-Agent-Workflow.md` — Pipeline sequence (one-pager goes after scorecard integration)
- `templates/base-style.css` — CSS variable system shared with one-pager template
- `cli/export_branded.py` — Export pipeline that will gain `--prepend` flag
- `src/branding.py` — Brand config loading (logos, colors, fonts)
- `io/hypernova/deals/10SQ/10SQ-Teaser-11.30.25.pdf` — Visual reference for layout

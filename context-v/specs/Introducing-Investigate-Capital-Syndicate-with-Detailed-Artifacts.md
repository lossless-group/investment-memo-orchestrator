---
title: Introducing Investigate Capital Syndicate with Detailed Artifacts
lede: A research agent that investigates every investor, fund, family office, and financial institution on a company's cap table and in the current round — producing detailed profiles, pattern analysis, and signal extraction for investment decision-making.
date_authored_initial_draft: 2026-03-24
date_authored_current_draft: 2026-03-24
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-24
at_semantic_version: 0.0.0.1
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Agent-Design, Syndicate, Cap-Table, Investors, Due-Diligence, Research]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A network graph of investors connected to a central company node, with detailed profile cards showing fund size, portfolio companies, check sizes, and co-investment patterns — overlaid on a cap table spreadsheet.
date_created: 2026-03-24
date_modified: 2026-03-24
---

# Introducing Investigate Capital Syndicate with Detailed Artifacts

**Status**: Draft (v0.0.1)
**Date**: 2026-03-24
**Author**: AI Labs Team

---

## Why This Matters

In venture capital, who is investing is often as important as what they're investing in. The syndicate — the collection of investors participating in a round — tells you:

- **Signal strength**: Is this a "smart money" round? Are thesis-aligned specialists leading, or is it generalist capital filling a gap?
- **Follow-on capacity**: Can these investors support the company through Series A, B, and beyond? What's their fund size relative to this check?
- **Network value**: Do these investors bring operational value (portfolio introductions, hiring networks, customer intros) or just capital?
- **Conflict risk**: Are any investors also backing direct competitors? Are there governance concerns with the investor mix?
- **Social proof**: Have these investors backed breakout companies before? What's their track record in this sector?
- **Cap table health**: Is the cap table clean? Is founder ownership sufficient for motivation? Are there concerning terms or investor concentrations?

Currently, the system extracts cap table data (via the dataroom analyzer) and lists investors mentioned in the deck/research, but does NOT investigate the investors themselves. A name like "Valor Equity Partners" appears in the memo without context about their $1.5B fund, their Tesla/SpaceX track record, or their typical check size.

---

## What This Agent Produces

### Input Sources

The agent aggregates investor information from all available artifacts:

| Source | What it provides |
|--------|-----------------|
| `2-cap-table.json` | Existing shareholders, ownership percentages, share classes |
| `0-deck-analysis.json` | Investors mentioned in the pitch deck, round details |
| `1-research.json` | Investors discovered during web research |
| `1-competitive-evaluation.json` | Investors backing competitors (overlap detection) |
| `{Company}_competitive-curation.json` | Human-curated competitor classifications |
| Deal config (`{Company}.json`) | Any manually specified investors |
| `state.json` | Round terms, funding amounts |

### Output Artifacts

```
output/{Deal}-{Version}/
├── 9-syndicate-investigation/
│   ├── syndicate-overview.md           # Human-readable summary
│   ├── syndicate-overview.json         # Structured data
│   ├── investor-profiles/
│   │   ├── valor-equity-partners.md    # Individual investor deep-dive
│   │   ├── valor-equity-partners.json
│   │   ├── nucleation-capital.md
│   │   ├── nucleation-capital.json
│   │   └── ... (one per investor)
│   ├── syndicate-signals.md            # Pattern analysis and red/green flags
│   └── cap-table-analysis.md           # Ownership structure assessment
```

### Per-Investor Profile

Each investor gets a detailed profile researched via Perplexity Sonar Pro:

```markdown
# Valor Equity Partners

## Fund Overview
- **Type**: Venture Capital / Growth Equity
- **Fund Size**: $1.5B (Fund III, 2023)
- **AUM**: ~$3.5B across all vehicles
- **HQ**: New York, NY
- **Founded**: 2008
- **Key Partners**: Antonio Gracias (Founder/CIO)

## Investment Thesis & Focus
- Growth-stage technology and sustainability investments
- Emphasis on industrial technology, energy, and deep tech
- Typical check: $10M-$50M (growth), $2M-$10M (early stage)
- Stage focus: Series A through growth

## Relevant Track Record
| Company | Sector | Stage | Outcome |
|---------|--------|-------|---------|
| Tesla | EV/Energy | Early | IPO, 100x+ |
| SpaceX | Aerospace | Growth | $180B+ valuation |
| Anduril | Defense Tech | Series D | $14B valuation |

## Portfolio Overlap & Conflicts
- **Competitor investments**: None identified in metabolic health
- **Adjacent investments**: [BioAtla] (biotech), [Relativity Space] (deep tech)
- **Co-investor history**: Frequently co-invests with Founders Fund, 8VC

## Signal Assessment
- **Conviction level**: Lead investor → high conviction signal
- **Sector expertise**: Limited direct metabolic health experience
- **Follow-on capacity**: Strong — fund size supports multi-round participation
- **Value-add potential**: Deep tech operational expertise, board-level involvement
- **Notable**: Antonio Gracias served on Tesla board for 10+ years
```

### Syndicate Signals Analysis

A synthesis document that looks at the investor group as a whole:

```markdown
# Syndicate Signal Analysis — Metabologic Seed Round

## Round Composition
- Lead: [Investor Name] — $X check, $Y fund
- Participating: [List with check sizes if known]
- Follow-on from prior round: [Any returning investors]

## Green Flags 🟢
- Lead investor has relevant sector expertise (biotech/enzyme engineering)
- 3 of 5 investors have prior exits in longevity/metabolic health
- Combined follow-on capacity exceeds $500M for Series A support
- No competitor conflicts identified across syndicate portfolios

## Yellow Flags 🟡
- Lead investor's typical check is 5x larger than this round — may indicate
  low conviction or small exploratory bet
- 2 investors are first-time in biotech (generalists)
- No strategic/corporate investor for commercial partnerships

## Red Flags 🔴
- [Investor X] also backs [Competitor Y] — potential information leakage
- Cap table shows [concerning pattern — e.g., excessive investor ownership at seed]
- No investor with FDA regulatory pathway experience

## Co-Investment Pattern Analysis
- [Investor A] and [Investor B] have co-invested in 4 prior deals — strong
  alignment signal
- [Investor C] typically invests alone — unusual to see in a syndicate

## Follow-on Scenarios
- Series A ($15-25M): Lead can support from existing fund, 3/5 participants
  have follow-on reserves
- Series B ($50M+): Will likely need new lead; current syndicate provides
  warm introductions to [Fund X], [Fund Y] based on co-investment networks
```

### Cap Table Analysis

```markdown
# Cap Table Analysis — Metabologic

## Ownership Summary
| Category | Ownership | Notes |
|----------|-----------|-------|
| Founders | 72% | Healthy at seed stage |
| Angel/Pre-Seed | 8% | Reasonable dilution |
| Seed Round (current) | 12% | Standard for $3M on $15M pre |
| Option Pool | 8% | Standard 8-10% |

## Cap Table Health Assessment
- ✅ Founder ownership above 60% post-seed — strong alignment
- ✅ Option pool sufficient for 2-3 key hires before Series A
- ⚠️ No board seats specified — governance structure TBD
- ⚠️ Convertible note terms from pre-seed not visible — potential hidden dilution

## Pro-Forma Post-Round
[If enough data to model]
```

---

## Agent Architecture

### Pipeline Agent: `syndicate_investigator`

```
Pipeline position: After fact_correct, alongside or after source_catalog

Inputs:
  - 2-cap-table.json (ownership data)
  - 0-deck-analysis.json (investors from deck)
  - 1-research.json (investors from research)
  - 1-competitive-evaluation.json (competitor investors)
  - state.json (round terms)

Process:
  1. Aggregate all investor names from all sources
  2. Deduplicate (fuzzy match: "Valor Equity" = "Valor Equity Partners")
  3. For each investor, call Perplexity Sonar Pro:
     - Fund overview, AUM, fund size
     - Investment thesis and stage focus
     - Notable portfolio companies and outcomes
     - Key partners / decision makers
  4. Cross-reference: check if any investor also backs a competitor
  5. Analyze syndicate signals (green/yellow/red flags)
  6. Assess cap table health
  7. Save all artifacts

Output:
  - 9-syndicate-investigation/ directory with all files
  - State update with syndicate_analysis summary
```

### CLI App Integration

Under "Integrate Content from Versions" or as a standalone flow:

```
? What would you like to do?
  ❯ 📝 Generate a new investment memo
    📄 Generate a one-pager summary
    📤 Export an existing memo
    🔧 Improve a specific section
    👥 Investigate syndicate & investors     ← NEW
    🔄 Integrate content from versions
    📊 Run a specific agent
```

The CLI flow would also allow:

```
? Syndicate Investigation for Metabologic

  Found investors from:
    Cap table: 3 entities
    Deck: 5 mentioned
    Research: 2 additional
    Deduplicated: 7 unique investors

? Review investor list before researching?
  ❯ Yes, let me add/remove
    No, research all 7

? Add investors not found by the system:
  > "Emergence Capital"
  > "Lux Capital"
  > (empty to finish)

? Remove any from the list?
  [ ] Angel syndicate (generic, not researchable)
  [x] Remove

  Researching 8 investors via Perplexity Sonar Pro...
  ✓ Valor Equity Partners (3.2s)
  ✓ Nucleation Capital (2.8s)
  ● Emergence Capital (searching...)
  ○ Lux Capital
  ...

  Investigation complete!
  Profiles: 9-syndicate-investigation/investor-profiles/
  Signals:  9-syndicate-investigation/syndicate-signals.md
  Cap Table: 9-syndicate-investigation/cap-table-analysis.md
```

---

## Data Model

### Investor Profile Schema

```json
{
  "name": "Valor Equity Partners",
  "aliases": ["Valor Equity", "Valor"],
  "type": "venture_capital",
  "website": "https://www.valorep.com",
  "hq": "New York, NY",
  "founded": 2008,
  "fund_size": "$1.5B",
  "aum": "$3.5B",
  "key_partners": [
    {"name": "Antonio Gracias", "title": "Founder & CIO", "background": "Tesla board member 2007-2021"}
  ],
  "investment_focus": {
    "stages": ["Series A", "Series B", "Growth"],
    "sectors": ["Deep Tech", "Industrial", "Energy", "Sustainability"],
    "typical_check": "$2M-$50M",
    "geographic_focus": "US"
  },
  "notable_portfolio": [
    {"company": "Tesla", "sector": "EV", "stage": "Early", "outcome": "IPO, 100x+"},
    {"company": "SpaceX", "sector": "Aerospace", "stage": "Growth", "outcome": "$180B+ valuation"}
  ],
  "competitor_investments": [],
  "co_investment_partners": ["Founders Fund", "8VC", "Lux Capital"],
  "relationship_to_deal": {
    "role": "lead_investor",
    "check_size": "$1.5M",
    "board_seat": true,
    "existing_shareholder": false,
    "introduced_by": null
  },
  "signals": {
    "conviction_level": "high",
    "sector_expertise": "low",
    "follow_on_capacity": "strong",
    "value_add": "operational, board governance",
    "concerns": []
  },
  "sources": ["Crunchbase", "PitchBook", "Company deck", "Perplexity research"]
}
```

### Syndicate-Level Curation (Deal Root)

Like source and competitive curations, human review of investor profiles persists at the deal root:

```
io/humain/deals/Metabologic/
├── Metabologic.json
├── Metabologic_source-curation.json
├── Metabologic_competitive-curation.json
├── Metabologic_table-curation.json
├── Metabologic_syndicate-curation.json   # ← Human-reviewed investor assessments
├── inputs/
└── outputs/
```

The curation file lets users:
- Correct AI-researched investor details
- Add context the AI couldn't find ("I know this GP personally, they're hands-on")
- Flag conflicts the AI missed
- Override signal assessments
- Add investors the system didn't find

---

## Research Approach

### Perplexity Queries Per Investor

Each investor gets 2-3 targeted queries:

1. **Fund overview**: `"{Investor Name}" venture capital fund size AUM portfolio @crunchbase @pitchbook`
2. **Portfolio & track record**: `"{Investor Name}" notable investments exits portfolio companies @crunchbase`
3. **Conflict check**: `"{Investor Name}" investment {competitor_names} @crunchbase @pitchbook`

### Rate & Cost Considerations

- ~3 Perplexity calls per investor × ~8 investors = ~24 API calls
- At Sonar Pro pricing: ~$0.50-1.00 per investor, $4-8 per syndicate investigation
- Parallelize where possible (investor profiles are independent)
- Cache results — if an investor was researched for another deal, reuse within 30 days

### Cross-Deal Intelligence

Over time, the system builds a corpus of investor profiles across all deals in a firm. Future features:
- **Investor database**: Aggregated profiles across all deals for a firm
- **Pattern detection**: "This investor has appeared in 3 of our last 5 deals"
- **Relationship mapping**: Co-investment network graphs
- **Signal correlation**: Track whether investor signals predicted deal outcomes

---

## Open Questions

1. **Artifact numbering**: Using `9-syndicate-investigation/` — does this conflict with any existing artifacts? Current highest is `8-one-pager`.

2. **When in the pipeline**: Should this run after all content is written (post-fact-check, pre-validate), or should it run early (post-research, pre-writer) so the writer can incorporate investor context into the Team and Funding sections?

3. **Investor type taxonomy**: The schema uses `venture_capital` but should support: `vc`, `growth_equity`, `pe`, `family_office`, `angel`, `corporate_vc`, `sovereign_wealth`, `accelerator`, `strategic`, `individual`. What's the right list?

4. **Competitor conflict sensitivity**: How aggressive should the conflict detection be? A mega-fund like a16z invests in everything — does backing a tangentially related company count as a "conflict"?

5. **Integration with one-pager**: The syndicate section on the one-pager currently shows names only. Should it show signal indicators (green/yellow/red dots) next to investor names?

6. **Cross-firm intelligence**: If Humain and Hypernova both evaluate a deal, should investor research be shared across firms or siloed?

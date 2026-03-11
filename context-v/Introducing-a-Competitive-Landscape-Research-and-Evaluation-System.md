---
title: Introducing a Competitive Landscape Research and Evaluation System
lede: Two coordinated agents—a Competitive Landscape Researcher and a Competitive Landscape Evaluator—that produce accurate, validated competitor analysis by combining multi-query web research with structured relevance screening.
date_authored_initial_draft: 2026-03-10
date_authored_current_draft: 2026-03-10
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-10
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Agent-Design, Competitive-Analysis, Research, Evaluation, Anti-Hallucination]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A filtered funnel diagram showing many company logos entering the top, passing through research and evaluation screening layers, with validated competitors emerging at the bottom in a structured comparison grid.
date_created: 2026-03-10
date_modified: 2026-03-10
---

# Introducing a Competitive Landscape Research and Evaluation System

**Status**: Draft
**Date**: 2026-03-10
**Last Updated**: 2026-03-10
**Author**: AI Labs Team
**Related**: Table-Generator-Agent-Spec.md, Multi-Agent-Orchestration-for-Investment-Memo-Generation.md, Anti-Hallucination-Source-Validation-and-Removal.md

---

## Executive Summary

Competitive landscape analysis is consistently cited by Venture Capital firms as one of the most valuable parts of an investment memo, yet it is currently a feature that is not meeting the curiosity of collaborating venture firms. The research agent tends to surface well-known, well-funded companies in the broader industry rather than the actual competitive set—producing errors of both commission (including non-competitors) and omission (missing real competitors, especially startups with modest search presence).

This specification introduces two coordinated agents:

1. **Competitive Landscape Researcher** (`competitive_landscape_researcher.py`): Runs multiple varied search queries to discover candidate competitors, producing a broad initial list with structured data.
2. **Competitive Landscape Evaluator** (`competitive_landscape_evaluator.py`): Screens each candidate against explicit relevance criteria, classifying them as direct, indirect, adjacent, or not-a-competitor... and searching for competitors that were missed.

Both agents run in the **research phase** of the pipeline, before the writer. They produce structured data that the writer consumes, and artifact reports that serve as a paper trail for human reviewers.

---

## Problem Statement

### Errors of Commission (Including Non-Competitors)

The current research agent has a bias toward well-known companies. When asked about competitors in "metabolic health," it returns companies like Zoe (AI nutrition insights), Virta Health (software-based diabetes management), and Pendulum (probiotics)—companies in the broader metabolic health space but not direct competitors for an enzyme supplement company. A human analyst would recognize these as adjacent, not competitive.

**Root cause**: Generic search queries like "metabolic health companies" surface the most prominent names, not the most relevant ones. AI models also exhibit completion bias—they'd rather produce a plausible-sounding answer than admit uncertainty about who the actual competitors are.

### Errors of Omission (Missing Real Competitors)

Real competitors — especially other startups in the same niche — often have modest web presence. They don't rank on the first page for broad category searches. A human analyst finds them by:
- Searching with varied, specific phrasings of the market category
- Going through 3-5 pages of search results, not just page 1
- Looking at "companies like X" and "alternatives to X" queries
- Checking who the company itself considers competitors (from their deck)
- Just clicking through search and paid search alternatives to a direct search for the company for which there is an investment opportunity, as the competitors often create targetted comparative content or pay for search ads for their intended competition.

**Root cause**: The research agent runs too few queries with too-generic phrasing.

### Hallucination of Competitor Data

Even when the right companies are identified, their metrics (funding, revenue, user counts) are often inaccurate or fabricated. "Zoe ($500M funded)" or "Virta Health ($1B+ revenue)" may not be accurate figures. The current pipeline doesn't validate these specific claims, and the bias of AI Models is to complete rather than admit uncertainty.

---

## Architecture: Two Agents, One System

### Why Two Agents Instead of One?

AI models have a strong completion bias. A single agent asked to "find competitors and evaluate their relevance" will tend to justify every competitor it found rather than critically screen them. By separating discovery from evaluation:

- The **researcher** is rewarded for breadth—find as many candidates as possible
- The **evaluator** is rewarded for skepticism—challenge every candidate's relevance
- The evaluator's completion bias works in the right direction: it will find *more* problems with the list, which is exactly what we want

This mirrors how human teams work: one analyst does the initial scan, another reviews the list critically.

---

## Agent 1: Competitive Landscape Researcher

### Purpose

Discover candidate competitors through multi-query web research, producing a broad initial list with structured data for each.

### Location

`src/agents/competitive_landscape_researcher.py`

### Pipeline Position

Research phase, after `section_research`, before `competitive_landscape_evaluator`.

```
dataroom → deck_analyst → research → section_research
                                          │
                                          ▼
                              competitive_landscape_researcher
                                          │
                                          ▼
                              competitive_landscape_evaluator
                                          │
                                          ▼
                                    cite → cleanup_research → writer
```

### Inputs

1. **Company description** from state (`state["description"]`)
2. **Market category / product type** extracted from deck analysis and research
3. **User-provided search variants** from company JSON config (new field, see below)
4. **Deck-identified competitors** from `state["deck_analysis"]` (companies the pitch deck mentions)
5. **Dataroom battlecard data** from `state["dataroom_analysis"]["competitive_data"]` if available

### Search Strategy

The agent generates ~5 search queries using varied phrasings. The goal is to search the way a human analyst would—not just one generic category query, but multiple specific angles.

**Query generation approach:**

1. **Direct competitor query**: `"competitors of [Company Name]"` or `"companies similar to [Company Name]"`
2. **Category query**: `"[specific market category] startups"` — using the most specific category description available, not a broad industry term
3. **Product-type query**: `"[product type] companies [stage/geography]"` — e.g., "enzyme supplement startups" not "metabolic health companies"
4. **Alternative-seeking query**: `"alternatives to [key product/approach]"` — e.g., "alternatives to GLP-1 for weight management"
5. **User-provided variants**: Any `search_variants` from the company JSON config

**Example for Metabologic:**
```
1. "competitors of Metabologic enzyme supplements"
2. "AI-designed enzyme supplement startups"
3. "sugar blocking supplement companies 2025"
4. "GLP-1 alternative supplement startups"
5. "digestive enzyme biotech companies seed stage"
```

**Search execution:**
- Use Perplexity Sonar Pro for each query (consistent with existing research infrastructure)
- Request structured competitor data in each response
- Capture source URLs for citation

### New Company JSON Config Field

```json
{
  "type": "direct",
  "mode": "consider",
  "description": "AI-designed enzyme supplements for metabolic health",
  "search_variants": [
    "enzyme supplement startups",
    "sugar blocking supplement companies",
    "GLP-1 alternative supplement companies",
    "AI enzyme engineering biotech"
  ],
  "known_competitors": [
    "Sweet Defeat",
    "SENS.life"
  ]
}
```

**Field descriptions:**
- `search_variants` (optional): List of market category phrasings the user knows are relevant. Supplements the auto-generated queries. If omitted, the agent generates all queries itself.
- `known_competitors` (optional): Companies the user already knows are competitors. The researcher will include these and look up their data. Useful for ensuring known competitors aren't missed.

### Output Schema

```python
class CompetitorCandidate(TypedDict):
    name: str
    description: str  # What the company does
    website: Optional[str]
    founded: Optional[str]  # Year
    funding_total: Optional[str]  # e.g., "$50M"
    funding_stage: Optional[str]  # e.g., "Series B"
    notable_investors: list[str]
    employee_count: Optional[str]
    online_presence: dict[str, str]  # platform_name → URL (see prompt for expected keys)
    key_differentiator: str  # How they approach the market
    overlap_description: str  # Why they might compete with subject company
    source_queries: list[str]  # Which search queries surfaced this company
    source_urls: list[str]  # Citation sources
    from_deck: bool  # Whether the company's own deck mentioned this competitor
    from_dataroom: bool  # Whether dataroom battlecards covered this competitor

class CompetitiveLandscapeResearch(TypedDict):
    candidates: list[CompetitorCandidate]
    queries_executed: list[str]
    total_candidates_found: int
    sources_consulted: int
    search_variants_used: list[str]  # Including user-provided ones
```

### State Updates

```python
return {
    "competitive_candidates": competitive_landscape_research,
    "messages": [f"Competitive landscape research: found {n} candidate competitors from {q} queries"]
}
```

### Online Presence Discovery

Each competitor's `online_presence` is a simple `dict[str, str]` mapping platform names to URLs. Consistency of keys is managed at the prompt layer, not the schema layer — this keeps the code flexible while handling the long tail of platforms that vary across companies.

**Prompt directive for the researcher:**

```
When capturing online presence for each competitor, use these exact keys
when the profile is found:

  crunchbase, pitchbook, linkedin, twitter, github, website, traxcn,
  brandfetch, producthunt, figma, dribbble, angellist, glassdoor,
  capterra, g2, trustpilot, techcrunch_profile, ycombinator

For platforms not in this list, use a lowercase snake_case key
(e.g., "indie_hackers", "hacker_news").

Only include profiles you actually find with valid URLs.
Do not guess or fabricate profile URLs.
```

This approach means:
- The 80% of common platforms get consistent keys across all runs
- The 20% of unexpected platforms are still captured without schema changes
- Downstream agents (writer, table generator) can access common profiles predictably
- No code changes needed when a new platform becomes relevant — just update the prompt

### Artifact Output

Saves to `output/{Company}-v0.0.x/1-competitive-research.md`:
- List of all candidates found with source queries
- Raw data per candidate (including online presence links)
- Note of which queries produced which candidates

---

## Agent 2: Competitive Landscape Evaluator

### Purpose

Screen each candidate competitor for actual relevance, classify them, identify gaps, and produce a validated competitor list that the writer can trust.

### Location

`src/agents/competitive_landscape_evaluator.py`

### Pipeline Position

Immediately after the researcher, still in the research phase.

### Inputs

1. `state["competitive_candidates"]` — the raw candidate list from the researcher
2. Company description and product details from state
3. Deck analysis (for the company's own competitive claims)

### Evaluation Criteria

For each candidate competitor, the evaluator assesses four dimensions:

| Criterion | Question | Weight |
|-----------|----------|--------|
| **Same customer segment** | Do they sell to the same buyer persona? | High |
| **Substitutability** | Could a customer choose one instead of the other? | High |
| **Same budget line** | Would they compete for the same dollar in a customer's budget? | Medium |
| **Market overlap** | Are they in the same geographic/vertical markets? | Medium |

**Classification rules:**
- **`direct_competitor`**: Scores high on 3-4 criteria. A customer would genuinely evaluate both.
- **`indirect_competitor`**: Scores high on 2 criteria. They compete for attention or budget but solve the problem differently.
- **`adjacent`**: Scores high on only 1 criterion. They're in the same industry but not really competing.
- **`not_a_competitor`**: Scores high on 0 criteria. Incorrectly identified.

### Omission Detection

After classifying existing candidates, the evaluator runs a targeted search for gaps:

1. Examine the classified competitor list—is there a pattern? (e.g., "all direct competitors are biotech, no supplement companies")
2. Run 1-2 additional targeted queries to fill gaps: `"who competes with [Company] in [specific niche]?"`
3. Add any newly discovered competitors to the list (with classification)

### Output Schema

```python
class EvaluatedCompetitor(TypedDict):
    name: str
    classification: str  # "direct_competitor", "indirect_competitor", "adjacent", "not_a_competitor"
    evaluation_reasoning: str  # 1-2 sentences explaining classification
    same_customer: bool
    substitutable: bool
    comparable_pricing: bool
    comparable_features: bool
    overlapping_value_propositions: bool
    market_overlap: bool
    # All fields from CompetitorCandidate carried forward:
    description: str
    website: Optional[str]
    founded: Optional[str]
    funding_total: Optional[str]
    funding_stage: Optional[str]
    notable_investors: list[str]
    complete_investor_list: list[str]
    employee_count: Optional[str]
    online_presence: dict[str, str]  # platform_name → URL (see prompt for expected keys)
    key_differentiator: str
    from_deck: bool
    from_dataroom: bool
    source_urls: list[str]

class CompetitiveLandscapeEvaluation(TypedDict):
    evaluated_competitors: list[EvaluatedCompetitor]
    direct_competitors: list[str]  # Names only, for quick access
    indirect_competitors: list[str]
    removed_as_non_competitors: list[dict]  # name + reasoning
    added_via_gap_analysis: list[str]  # Names of competitors found during omission detection
    evaluation_summary: str  # 2-3 sentence summary of the competitive landscape
    confidence: str  # "high", "medium", "low" — based on data availability
```

### Critical Design Constraint: No Rewrite Loops

The evaluator produces:
1. A **cleaned data structure** (`evaluated_competitors`) that the writer uses
2. An **artifact report** (`1-competitive-evaluation.md`) for human transparency

The evaluator does **NOT**:
- Trigger rewrites of any section
- Send feedback to other agents
- Create a back-and-forth correction cycle

This is intentional. Users want the paper trail (the evaluation report) but don't want an over-enthusiastic evaluator causing churn in the output. The evaluator's job is to clean the input data, not to police the output.

### State Updates

```python
return {
    "competitive_landscape": competitive_landscape_evaluation,
    "messages": [
        f"Competitive evaluation: {d} direct, {i} indirect, {r} removed as non-competitors",
        f"Gap analysis added {g} previously missed competitors"
    ]
}
```

### Artifact Output

Saves to `output/{Company}-v0.0.x/1-competitive-evaluation.md`:

```markdown
# Competitive Landscape Evaluation

## Summary
[A coherent but robust paragraph overview of the competitive landscape]

## Direct Competitors
| Company | Founded | Funding | Stage | Key Differentiator |
|---------|---------|---------|-------|--------------------|
| [...](http[s]://...)     | ...     | ...     | ...   | ...  |
| [list of citations] |

[For each: 1-2 sentence evaluation reasoning]

## Indirect Competitors
[Same format]

## Removed as Non-Competitors
| Company | Reason for Removal |
|---------|--------------------|
| Zoe     | Software-based nutrition insights; different product category, different buyer |
| Virta   | Software diabetes management platform; no supplement or enzyme product |

## Gap Analysis
[Companies added during omission detection, with reasoning]
```

---

## How the Writer Uses This Data

The writer agent receives `state["competitive_landscape"]` containing the validated, classified competitor list. This changes how competitive content is written:

### Current Behavior (Problem)
The writer uses generic research data and writes whatever competitive claims the research surfaced, including non-competitors and unsourced metrics.

### New Behavior (With This System)
The writer has:
1. A classified list of **direct** vs **indirect** competitors with sourced data
2. Clear guidance on who is NOT a competitor (so it won't include them)
3. Structured data per competitor (funding, stage, differentiator) ready for tabular presentation

The writer's competitive content should:
- Lead with direct competitors and explain the actual competitive dynamic
- Mention indirect competitors as context ("adjacent players include...")
- Never present adjacent or non-competitor companies as direct threats
- Use the structured data for the competitive comparison table (generated by the Table Generator agent)

### Writer Prompt Additions

The writer system prompt for Market Context / Opportunity sections should include:

```
COMPETITIVE LANDSCAPE DATA (pre-validated):

Direct Competitors:
{direct_competitors_with_details}

Indirect Competitors:
{indirect_competitors_with_details}

IMPORTANT: Use ONLY the competitors listed above. Do not add competitors
from general knowledge. These have been validated for actual market overlap.
If you believe a relevant competitor is missing, note it as a gap rather
than inventing one.
```

---

## Interaction with Existing Agents

### Dataroom Competitive Extractor (`competitive_extractor.py`)

The existing `competitive_extractor.py` extracts competitive data from dataroom battlecards and analysis documents. This data feeds INTO the Competitive Landscape Researcher:

- If battlecard data exists, those competitors are pre-seeded into the candidate list with `from_dataroom: true`
- The researcher still runs its search queries to find competitors NOT in the battlecards
- The evaluator validates all competitors equally, including battlecard ones

### Research Agent (`research_enhanced.py`)

The general research agent continues to run. Its competitive mentions are supplementary but no longer the primary source. The competitive landscape system produces the authoritative competitor list.

### Fact Checker (`fact_checker.py`)

The fact checker can validate specific competitor metrics (funding amounts, user counts) against citations. With sourced data from the competitive researcher, the fact checker has URLs to verify against.

---

## State Schema Additions

```python
# In src/state.py - add to MemoState TypedDict

class MemoState(TypedDict):
    # ... existing fields ...
    competitive_candidates: Optional[CompetitiveLandscapeResearch]  # Raw candidates
    competitive_landscape: Optional[CompetitiveLandscapeEvaluation]  # Validated & classified
```

---

## Documenting Search Terms in State

Search queries and their results should be captured in `state.json` for two purposes:

1. **Transparency**: Users can see what was searched and iterate on search terms
2. **Resume capability**: If the pipeline is resumed, the competitive research can be skipped if already complete

The `competitive_candidates` object in state already captures `queries_executed` and `search_variants_used`. The `state.json` dump preserves this.

Additionally, successful search terms should be saved back to the company JSON config as suggested `search_variants` for future runs, so the system improves over time.

---

## Implementation Priority

1. **Competitive Landscape Researcher**: Core value — better competitor discovery
2. **Competitive Landscape Evaluator**: Critical complement — prevents the researcher's completion bias from degrading quality
3. **Writer prompt integration**: Wire the validated data into the writer's competitive sections
4. **Company JSON config updates**: Add `search_variants` and `known_competitors` fields

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Non-competitors included in memo | Common (2-3 per memo) | 0 |
| Real competitors missed | Common (3-5 per memo) | ≤1 |
| Competitor metrics sourced with citations | ~30% | >80% |
| Client satisfaction with competitive section | Low (frequently cited as weak) | High |
| Competitive data structured for table generation | No | Yes |

---

## Example: Metabologic (Before vs After)

### Before (Current System)
> Direct competitors are limited: Pendulum focuses on probiotics, while Zoe ($500M funded) emphasizes AI-driven nutrition insights without enzymatic intervention. Indirect competitors like Virta Health ($1B+ revenue) deliver software-based metabolic management rather than biological interventions.

**Problems**: Pendulum, Zoe, and Virta are not direct competitors. Funding/revenue figures are unsourced and possibly hallucinated. Real enzyme supplement competitors are missing entirely.

### After (With This System)

**Researcher finds** (via targeted queries like "enzyme supplement startups", "sugar blocking supplement companies"):
- Sweet Defeat, SENS.life, Phase Scientific, etc.

**Evaluator classifies**:
- Sweet Defeat → `direct_competitor` (sugar-blocking supplement, same buyer, same budget)
- Pendulum → `indirect_competitor` (gut health supplements, different mechanism)
- Zoe → `adjacent` (software, different product entirely)
- Virta Health → `not_a_competitor` (software platform, different buyer, different budget)

**Writer produces**:
> The enzyme supplement space includes direct competitors like Sweet Defeat (sugar-blocking lozenges, $X raised) and SENS.life (enzymatic sugar blockers). Indirect competitors in the broader metabolic supplement category include Pendulum ($X raised, probiotic-based approach). Adjacent players like Zoe and Virta Health operate in metabolic health but through software platforms rather than supplement products, serving different buyers.

---

## Source Priority: Dataroom and Deck as Primary Sources

The orchestrator already follows a clear source hierarchy: dataroom first, then deck, then web research. The competitive landscape system follows the same convention:

1. **Dataroom** (highest priority): If a dataroom exists, it is the primary source. Battlecards, competitive analysis documents, and market positioning materials from the dataroom are treated as ground truth for the company's own competitive claims. The `competitive_extractor.py` already handles this extraction.
2. **Deck** (second priority): If no dataroom exists (or as a supplement), the pitch deck's competitive slides are used. The deck is often inside the dataroom anyway. Deck-identified competitors are pre-seeded into the candidate list with `from_deck: true`.
3. **Web research** (supplementary): The researcher's multi-query search fills gaps — finding competitors NOT mentioned in the dataroom or deck, and enriching competitor entries with external data (funding, employee count, online presence).

Both agents — researcher and evaluator — should have access to dataroom and deck data. The evaluator uses this context to understand the company's own positioning claims, while validating competitor relevance independently through its four-criteria framework. Deck competitive slides may be self-serving, but they are still the best starting signal for who the company itself considers competition.

---

## Multiple Tables by Classification

Rather than cramming all competitors into a single table (which dilutes the signal), the table generator should produce **separate tables by classification**:

### Table 1: Direct Competitive Set (Primary)
The core table. Companies a customer would genuinely evaluate alongside the subject company. Same buyer, same budget, substitutable product.

| Company | Founded | Funding | Stage | Key Differentiator | Overlap |
|---------|---------|---------|-------|--------------------|---------|

This is the table that matters most to investors. It should be tight — typically 3-8 companies.

### Table 2: Indirect Competitors
Companies that compete for attention or budget but solve the problem differently. Different mechanism, different product form factor, but similar value proposition.

| Company | Founded | Funding | Approach | Why Indirect |
|---------|---------|---------|----------|--------------|

### Table 3: Emerging & Stealth Competitors
Companies with similar brand promises, value propositions, or market category positioning but limited web presence or traction data. These are early-stage or stealth companies that may not have much data available — sparse rows are acceptable here. The point is awareness, not detailed benchmarking.

| Company | Description | Signals Found | Confidence |
|---------|-------------|---------------|------------|

**Confidence levels**: `high` (multiple corroborating sources), `medium` (single source or limited data), `low` (mentioned in passing, minimal web presence).

### Why Three Tables?

A single table mixing direct competitors with tangentially related companies undermines the analytical value. Investors scanning a competitive table expect to see the actual competitive set — not a grab bag of loosely related companies. Separating by classification lets each table serve its purpose:
- **Direct**: "Who do they actually compete with?"
- **Indirect**: "What adjacent approaches exist?"
- **Emerging**: "What should we keep an eye on?"

The table generator should produce all three when the data supports it, but only the direct competitive set table is required. Indirect and emerging tables are generated only if there are candidates in those classifications.

---

## On Versioning and Cross-Run Data Continuity

Competitor data is already versioned implicitly — each run produces artifacts in `output/{Company}-v0.0.x/` and the competitive research and evaluation reports live there alongside everything else.

The deeper question — how to distinguish "human-verified, high-value" outputs from "unverified bulk output" and how to selectively carry forward priority data across runs — is a system-wide challenge, not specific to competitive analysis. The orchestrator already generates substantial JSON and Markdown artifacts per run, and the framework for marking certain outputs as trusted inputs to subsequent runs doesn't exist yet.

This is deferred as a cross-cutting concern. For now, competitive landscape data follows the same versioning pattern as all other artifacts. When the broader input-prioritization framework is designed, competitive data (especially human-verified competitor classifications) would be a strong candidate for "preserve and build on" status.

**Current state**: The system is already resonating with professional VCs more than alternative agentic tools in the market. The priority is continuing to improve output quality (which these new agents address), with the input-curation and cross-run continuity framework evolving over time as usage patterns clarify what's worth preserving.

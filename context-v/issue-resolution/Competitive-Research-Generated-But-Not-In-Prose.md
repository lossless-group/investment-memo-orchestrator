---
title: "Competitive Research Generated But Not In Prose"
lede: "The competitive landscape evaluator agent produces rich, named, evidenced competitor data — 9+ companies per memo, with funding, differentiation, and direct/indirect classification — and saves it to disk. The downstream writer agent that drafts the Category Leadership section never sees that data. The section then emits `<needs-source>` markers asking for 'names of the top 3–5 ocean energy competitors' while a file naming 9 of them sits two directories away. Two agents working on the same memo with no pipe between them."
date_authored_initial_draft: 2026-06-08
date_authored_current_draft: 2026-06-08
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-06-08
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
status: Draft
augmented_with: Claude Code (Opus 4.7)
category: Issue Resolution
tags:
  - Competitive-Landscape
  - Agent-Wiring
  - State-Contract
  - Writer-Agent
  - Pipe-Leak
  - Category-Leadership
  - Memo-Generation
authors:
  - Michael Staton
date_created: 2026-06-08
date_modified: 2026-06-08
---

# Competitive Research Generated But Not In Prose

## Problem summary

The orchestrator runs two parallel research streams that should converge in the Category Leadership section of the memo, and they don't.

**Stream A — Codified section research.** For each section in the outline, the codified section researcher produces `outputs/<deal>-v0.0.N/1-research/<NN>-<section>-research.md`. For Category Leadership specifically, this means `04-category-leadership-research.md`. This is the file the writer reads to draft the section.

**Stream B — Competitive landscape evaluation.** A separate agent (`competitive_landscape_researcher.py` + `competitive_landscape_evaluator.py`) runs against the company's deck and research, identifies direct/indirect/adjacent competitors, classifies them, fetches funding and differentiation data, and saves `outputs/<deal>-v0.0.N/1-competitive-research.md` + `1-competitive-evaluation.md` + matching `.json` files. The output is high-quality and well-structured (markdown tables, named companies, evidenced classification).

**The bug:** Stream B's output is never fed into Stream A's downstream writer. The writer reads `1-research/04-category-leadership-research.md` exclusively. Whatever competitor coverage made it into *that* file via the codified researcher's broad-search pass is what the section sees; the dedicated competitive-evaluator's richer output sits orphaned on disk.

## The triggering evidence (2026-06-07, Panthalassa-Deck-Series-B v0.0.2)

The competitive landscape evaluator ran cleanly. Its output (`1-competitive-evaluation.md`) contains:

- **2 direct competitors**: Allseas (Waves AI Data Center project) — listed twice, likely a dedup bug — and a duplicate row of the same company.
- **7 indirect competitors**: Ocean Power Technologies, Mocean Energy, SINN Power, Subsea Cloud, Nautilus Data Technologies, Exa Data Center, Microsoft (Project Natick).
- **3 adjacent companies**: Eco Wave Power, CorPower Ocean, AW-Energy (WaveRoller).

Each entry has founding year, funding-status notes, a one-paragraph differentiation summary, and a classification justification. The agent took the time to do real work.

In the same v0.0.2 run, `2-sections/04-category-leadership.md` contains:

- **Zero mentions of Allseas, Microsoft Natick, Subsea Cloud, Nautilus Data, Ocean Grazer, Kardinia, Ocean Renewable Power, SINN Power, Carnegie, Verdant, Mocean, Exa, Eco Wave Power, CorPower, or AW-Energy.** (Verified by grep across all 11 section files; zero matches.)
- Two explicit `<needs-source>` markers asking for exactly the data the competitive evaluator produced:
  - `<needs-source claim="Names of the top 3–5 ocean energy competitors and their differentiation" />`
  - `<needs-source claim="Panthalassa's operational deployments, MW capacity, or project pipeline vs. nearest competitors" />`
- Generic prose describing "the field comprises dozens of pilot-stage developers" and "wave-energy converters (WECs) dominate the device count" — high-level category color rather than named-competitor analysis.

The writer's `<needs-source>` discipline (per `AGENTS.md` §5) is correct behavior given its input. The problem is the input. The writer was honestly saying *"I don't have competitor data,"* while a sibling agent had finished producing exactly that data minutes earlier in the same run.

## Why this matters

Three reasons this is more than a cosmetic gap:

1. **The Category Leadership section is the load-bearing competitive case.** A 7-Cs framework section titled "Category Leadership" that contains no named competitors is structurally hollow — readers cannot evaluate the company's position without knowing what it's positioned against. The section's stated job per the outline is to *"name the top 3–5 ocean energy competitors and their differentiation"*; it can't do its job without the data.

2. **The user ran a separate, more expensive agent specifically to get this data.** `competitive_landscape_researcher.py` makes its own LLM and search calls — meaningful API spend — to produce competitor profiles. Stranding that output is a direct cost waste on top of the quality loss.

3. **The `<needs-source>` markers create false signal for downstream curation.** Anyone reading the validator output or the final memo and seeing those markers reasonably concludes "we need more research on competitors." The truth is we *have* the research — we just didn't plumb it into the writer's context.

## Hypothesized failure points (to verify during resolution)

The writer (`src/agents/writer.py`) reads its per-section input from `state["research"]` or directly from `1-research/<NN>-<section>-research.md`. The state contract probably has no field for `competitive_landscape` separately, OR has the field but the writer's prompt template doesn't reference it. Likely-correct fix sites, in order of likelihood:

1. **`src/state.py`** — `MemoState` may not have a `competitive_landscape` field that the writer can read. Add one if missing.
2. **`src/agents/competitive_landscape_evaluator.py`** — verify it actually writes its output to state (not just to disk). Many agents that emit artifacts also need to mutate `state` so downstream nodes see the data.
3. **`src/agents/writer.py`** — when drafting the Category Leadership section (and possibly others, per below), the writer's per-section prompt needs to be augmented with `state["competitive_landscape"]` as a structured input block, with explicit framing: *"Below is the competitive analysis already produced for this deal. Use named competitors from this list, not generic descriptions. Do not emit `<needs-source>` markers for competitor names this analysis already provides."*
4. **`src/workflow.py`** — graph order. The competitive evaluator might run after the writer in the current topology, in which case even a perfect state contract wouldn't help because the writer would have already emitted its section file. Reorder if so: competitive evaluator → writer.

Beyond Category Leadership, the same pipe might be needed for:

- **Risks** — direct competitors are a load-bearing risk source.
- **Counter Cyclicality** — incumbent comparisons matter for cycle-resilience claims.
- **Cash on Cash Return Probability** — exit comps require knowing the competitive set.

## Resolution direction (not yet implemented)

This issue is a stub for the conversation. The eventual fix probably composes:

1. **Add `competitive_landscape: CompetitiveLandscapeData` to `MemoState`.** Define the schema as a TypedDict that mirrors what `1-competitive-evaluation.json` already serializes.
2. **Make the competitive evaluator write to state in addition to disk.** Same pattern as the deck analyst — artifact for humans, state for downstream agents.
3. **Augment the writer's section-prompt builder** to include the competitive landscape as structured context for any section whose outline-section name matches a configurable allow-list (default: `category-leadership`, `risks`).
4. **Reorder the graph** so `competitive_landscape_evaluator` runs before `writer`, not in parallel or after.
5. **Add a validation rule** — if `state["competitive_landscape"]` has ≥3 direct/indirect competitors AND the rendered Category Leadership section names zero of them, that's a validator-flagged regression. The same validator should suppress `<needs-source>` markers for competitor-coverage claims when the state field is non-empty.

## Where to dig in code

- `src/state.py` — `MemoState` schema; check for `competitive_landscape` field.
- `src/agents/competitive_landscape_researcher.py` — Stream B step 1; check what it writes to state vs. disk.
- `src/agents/competitive_landscape_evaluator.py` — Stream B step 2; same check.
- `src/agents/writer.py` — `_build_section_prompt()` or equivalent; confirm whether competitive-landscape data is injected for the Category Leadership section.
- `src/workflow.py` — `build_workflow()`; verify the node order between competitive-evaluator and writer.
- `templates/outlines/direct-investment.yaml` and firm-specific descendants — the Category Leadership section's `required_elements` already list "3–5 named competitors with specific differentiation" — the contract is right; the implementation isn't honoring it.

## Related

- [[Limiting-or-Omitting-Investor-Judgement]] — sister issue about agent overreach; this issue is the inverse failure mode (agent under-reach via missing wiring).
- [[Per-Deal-Focal-Points]] — focal points might also need to flow into the writer's section prompts; same plumbing gap.
- [[Separating-Retrieval-from-Generation-in-Agent-Pipelines]] — the broader architectural direction; one of its preconditions is "every relevant retrieval output reaches the writer," which today is not true for the competitive landscape stream.
- `apps/memopop-orchestrator/io/alpha-jwc/deals/Panthalassa-Deck-Series-B/outputs/Panthalassa-Deck-Series-B-v0.0.2/1-competitive-evaluation.md` — the worked example showing the orphaned output.
- `apps/memopop-orchestrator/io/alpha-jwc/deals/Panthalassa-Deck-Series-B/outputs/Panthalassa-Deck-Series-B-v0.0.2/2-sections/04-category-leadership.md` — the worked example showing the resulting `<needs-source>`-laden prose.

## Open questions

- Does the competitive landscape data need to flow into multiple section writers (Category Leadership + Risks + Cash on Cash), or is it scoped to one?
- Should the writer always inject competitive data, or only when the outline section's `required_elements` mentions competitors explicitly?
- Is there a per-section budget concern (prompt size) when adding the full competitive-evaluation table to the writer's context, vs. a summary-only injection?
- Once the wiring exists, should the validator add a "competitive coverage" score that penalizes Category Leadership sections naming fewer than N competitors when competitive data is available?

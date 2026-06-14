---
title: "Including Comparable Exits, Valuations, and IPOs"
lede: "An investment memo's bull/base/bear scenarios are only as honest as the comparable exits they're anchored to. The orchestrator has no dedicated agent for surfacing exit comps — IPOs, M&A outcomes, secondary multiples — for adjacent or analogous companies. The Cash on Cash Return Probability section is expected to render these scenarios but is left to fish for comps via the same generic research path that produces the URL-hallucination problem documented elsewhere. The result is plausible-sounding return math anchored to nothing verifiable."
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
  - Comparable-Exits
  - IPOs
  - Valuation-Comps
  - Return-Scenarios
  - Cash-On-Cash
  - Feature-Gap
  - Memo-Generation
  - Writer-Agent
authors:
  - Michael Staton
date_created: 2026-06-08
date_modified: 2026-06-08
---

# Including Comparable Exits, Valuations, and IPOs

## Problem summary

The seventh and final C in Alpha Partners' / Alpha JWC's framework — **Cash on Cash Return Probability** — requires the memo to render bull/base/bear return scenarios with cash-on-cash multiples and to name comparable exits in the sector. The outline's `required_elements` for that section literally lists *"Comparable exits in sector with multiples"* and *"Exit paths with most likely acquirers or IPO thesis."* This is structurally the same kind of named-evidence requirement that the Category Leadership section has for competitors (see [[Competitive-Research-Generated-But-Not-In-Prose]]) — and it suffers from the same failure mode for the same architectural reason.

**There is no dedicated agent in the orchestrator that harvests comparable exits, IPOs, M&A outcomes, or secondary multiples.** The Cash on Cash section is left to surface this evidence through the codified section researcher's generic broad-search pass, which is the same path that the citation-fabrication problem comes from. The model "knows" that companies in the space have exited and renders plausible-sounding scenarios — but the named acquirers, the valuation multiples, the dates are exactly the kind of specific-numerical-claim slot that the model fills from training-data memory rather than from a tool call that retrieved real data.

The result, observed in `Panthalassa-Deck-Series-B/outputs/.../v0.0.2/2-sections/09-cash-on-cash-return-probability.md`: scenarios cite returns of *"3–8x"* and *"comparable maritime IPOs trading at 5–12x revenue"* without naming the comparable companies, listing the actual exit dates, or pointing to the underlying transactions. The prose reads correct; the evidence doesn't exist.

## Why this matters

Three reasons this gap is more than cosmetic:

1. **Scenarios are the document's load-bearing investment math.** The recommendation (PASS / CONSIDER / COMMIT — see [[Limiting-or-Omitting-Investor-Judgement]] for the related verdict-rendering issue) is supposed to derive from the probability-weighted return analysis. If the return analysis is anchored in unverifiable comps, the recommendation inherits that unreliability. The investment committee reading the memo can't sanity-check the conclusion against the evidence because the evidence is hand-wave.

2. **The exit-comp gap is more dangerous than the competitor-name gap.** For competitors, naming the wrong company is embarrassing but recoverable — the analyst spots it on read. For exit comps, citing the wrong valuation or the wrong acquirer at the right-sounding round of magnitude is plausible enough to slip past review. Wrong return scenarios → wrong recommendations → real capital misallocated.

3. **The space frequently lacks clean comps and that's not allowed to be the answer.** For categories like ocean energy where most prior companies haven't reached commercial exit (or have failed quietly), the *honest* answer is often *"the comp set is thin and tilts negative."* The current pipeline doesn't surface that honesty — it papers over it. A real comp-harvester should be willing to report `<comp-set-thin>` rather than fabricate.

## What "comps" means in this context

Distinguishing the types of comparables a memo needs is the first step in scoping the harvester:

| Comp type | What it shows | Where it lands |
|---|---|---|
| **Direct comps** | Same product/category exits (e.g., wave energy companies, marine renewable IPOs) | Cash on Cash; Category Leadership |
| **Adjacent comps** | Same buyer / same business model, different tech (e.g., offshore wind IPOs, floating solar M&A) | Cash on Cash; Colossal Market Size |
| **Analogous comps** | Same shape of risk/reward (e.g., hard-tech long-development-curve exits like Stoke Space, Climeworks; deep-ocean tech like Anduril marine) | Cash on Cash; Risks |
| **Counter-comps** | Failures and write-downs in the category | Risks; Diligence; honest Cash on Cash |
| **Multiple comps** | Public-market trading multiples for category-comparable companies | Cash on Cash (valuation anchor) |

Currently the pipeline implicitly treats all comps as the same — a generic "find me some comps" prompt — which is why adjacent-or-analogous-but-not-direct comps rarely surface, and counter-comps almost never do. A real comp-harvester should classify by type, surface all four positive types, and explicitly seek counter-comps as a separate retrieval pass.

## The data shape (proposed)

A comp record probably needs fields like:

```yaml
- company: <name>
  type: <direct | adjacent | analogous | counter>
  outcome: <ipo | acquisition | spac | secondary | write-down | shutdown>
  outcome_date: YYYY-MM-DD
  outcome_valuation_usd: <number>
  exit_multiple_revenue: <number | null>
  exit_multiple_paid_in: <number | null>  # cash-on-cash from last-round to exit
  acquirer: <name | null>
  sector_match: <"same-product" | "same-buyer" | "same-risk-shape" | "category-analog">
  why_relevant: <one to two sentences>
  source_urls: [<url>, <url>]              # MUST come from harvester tool calls, not LLM memory
  source_verdict: <"verified" | "thin" | "founder-asserted">
```

Source discipline matters here more than anywhere else in the pipeline, per the broader argument in [[Separating-Retrieval-from-Generation-in-Agent-Pipelines]]. A comp record without `verified` source URLs is a comp record that's probably hallucinated. The schema should make this hard to skip.

## Hypothesized fix shape

This is a feature gap. The eventual implementation probably composes:

1. **A new `comparable_exits_harvester` agent** structured the same way the competitive landscape evaluator is — discovery via search-tool calls (Crunchbase, PitchBook, CB Insights, SEC EDGAR for IPOs), validation, classification by comp type, body-grounded extraction of valuation/multiple fields. Saves to `outputs/<deal>-v0.0.N/1-comparable-exits.json` + `.md`.

2. **Wiring into the writer's section prompts.** Same plumbing problem as [[Competitive-Research-Generated-But-Not-In-Prose]]: the harvester's output has to reach `state["comparable_exits"]` and the writer's Cash on Cash, Colossal Market Size, and Risks section prompts have to inject it as structured context with explicit framing.

3. **Per-deal analyst input.** The analyst often knows the right comp set better than the agent (e.g., *"compare this to Stoke Space, not to oil-and-gas marine"*). Per-deal comp seeds should be supportable, probably via [[Per-Deal-Focal-Points]] or a sibling `inputs/comp-seeds.md`.

4. **Explicit `<comp-set-thin>` discipline.** When the harvester returns fewer than N validated direct+adjacent comps for the category, the writer should be required to surface that thinness in prose rather than inventing scenarios. Honest scarcity beats fabricated abundance.

5. **Cross-reference into the Risks section.** Counter-comps (failures, write-downs, stalled IPOs in the category) belong in Risks. The harvester should emit them as a distinct slice and the Risks section should consume them.

6. **Public-market multiples as a separate harvester step.** For categories with public comps (offshore wind, hard-tech IPOs), trading multiples from SEC filings or financial data providers are a different retrieval problem than M&A comps — different sources, different validation. Probably worth a second sub-agent.

## Where it surfaces in current code

- `src/agents/codified_section_researcher.py` — currently the only path that surfaces anything comp-like, via generic search. The hallucination surface lives here for now.
- `src/agents/writer.py` — drafts Cash on Cash section 9 from `1-research/09-cash-on-cash-return-probability-research.md`; has no comp-specific input.
- `templates/outlines/direct-investment.yaml` and firm descendants (`alpha-jwc-7Cs-customized.yaml`) — section 9 `required_elements` includes `"Comparable exits in sector with multiples"` and `"Exit paths with most likely acquirers or IPO thesis"`. The contract is right; the implementation can't honor it without a harvester.
- `src/agents/competitive_landscape_evaluator.py` — closest existing template; the comp-harvester should be modeled on its retrieval-then-classify-then-evaluate shape.
- `src/state.py` — needs a `comparable_exits: ComparableExitsData` field if this lands.

## Open questions

- Should the comp-harvester run per-deal once (results cached for re-runs), or per-version (fresh each time)? Comps don't change daily — caching with a TTL is probably right.
- Should it be allowed to fetch SEC EDGAR directly for IPO data, or rely on third-party aggregators (Crunchbase / PitchBook) that are paywalled but cleaner? Mixed approach probably correct.
- How does this interact with the firm-level outline customization? Some firms care more about M&A comps than IPO comps (or vice versa); should the comp-type weighting be firm-configurable in the outline YAML?
- For very early-stage companies (pre-Series-A) where the analyst's stage-aware fallback (per `alpha-jwc-7Cs-customized.yaml` notes) says "use category comps not company numbers," the comp-harvester is doing even more load-bearing work. Should there be a "stage-mode" that affects how aggressively the harvester is run?
- Should the harvester also surface *unsuccessful* outcomes (shutdowns, down-rounds, write-downs) by default, or only on explicit Risks-section requests?

## Related

- [[Competitive-Research-Generated-But-Not-In-Prose]] — sister issue; same architectural shape (dedicated agent → orphaned output → writer fishes with `<needs-source>` markers).
- [[Limiting-or-Omitting-Investor-Judgement]] — the verdict-rendering issue; comp-quality directly affects whether any verdict is defensible.
- [[Per-Deal-Focal-Points]] — analyst-supplied comp seeds plausibly belong here.
- [[Separating-Retrieval-from-Generation-in-Agent-Pipelines]] — the broader architectural direction; comp data is one of the most expensive places to keep retrieval and generation entangled.
- [[Faked-Sources-from-Perplexity]] — the URL-hallucination pattern that the current implicit-comp path inherits.
- `io/alpha-jwc/templates/outlines/alpha-jwc-7Cs-customized.yaml` — section 9 `structure_template` already names the slots a comp-harvester would fill.
- `apps/memopop-orchestrator/io/alpha-jwc/deals/Panthalassa-Deck-Series-B/outputs/Panthalassa-Deck-Series-B-v0.0.2/2-sections/09-cash-on-cash-return-probability.md` — the worked example showing the gap in action.

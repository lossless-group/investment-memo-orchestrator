---
title: "Limiting or Omitting Investor Judgement"
lede: "The memo pipeline renders unsolicited investment verdicts (PASS / CONSIDER / COMMIT) at the end of the Cash on Cash Return Probability and Closing Assessment sections — even when the human analyst is actively preparing the memo to advocate for the company in front of the investment committee. The agent has no signal that the analyst's job here is advocacy, not adjudication, and that an automated PASS in that context is worse than no verdict at all."
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
  - Investor-Judgement
  - Verdict-Rendering
  - Analyst-Authority
  - Agent-Overreach
  - Memo-Generation
  - Writer-Agent
  - Tone
authors:
  - Michael Staton
date_created: 2026-06-08
date_modified: 2026-06-08
---

# Limiting or Omitting Investor Judgement

## Problem summary

The orchestrator's writer and closing-assessment agents render a *verdict* on whether the firm should invest — `PASS`, `CONSIDER`, or `COMMIT` — and they do this **unconditionally**, on every run, regardless of the analyst's intent in producing the memo.

In `consider` mode this is partially expected: the outline (`templates/outlines/direct-investment.yaml` and firm-specific descendants such as `alpha-jwc-7Cs-customized.yaml`) lists `PASS / CONSIDER / COMMIT` as the recommendation options. The model dutifully picks one. But the analyst's reason for generating the memo is not always *"decide for me whether to invest."* Far more often, the analyst is preparing a memo to **present to the investment committee in support of a deal they have already decided is worth presenting**. In that context, an automated `PASS` rendered at the end of the document is not "neutral analytical output." It is the system overriding the analyst's stated direction — and doing so publicly, in the same document the analyst plans to hand to colleagues.

## The triggering incident (2026-06-07, Panthalassa-Deck-Series-B v0.0.2)

The user generated v0.0.2 of the Panthalassa memo. Mode was set to `consider` (the standard prospective-analysis mode). The closing section rendered a `PASS` recommendation. The user's response, verbatim:

> "Why the fuck is it telling me to pass on a company I am trying to present to the investment team? Yeah, the mode is consider, but I didn't ask it to pass."

The user is not arguing that the model's reasoning was wrong. Even if every analytical conclusion in the document were correct, **a system that renders unsolicited PASS verdicts cannot be safely placed in the analyst's IC-prep workflow.** The cost of a false-positive PASS is asymmetric: a single agent-rendered `PASS` in a memo the analyst intends to advocate for is a credibility hit the analyst then has to manually overwrite or apologize for. The cost of an omitted verdict is zero — the analyst writes their own recommendation.

## Why the current behavior is wrong

Three distinct framings, all converging on the same conclusion:

### 1. The analyst is the decision-maker; the memo is the analyst's instrument

In a venture firm, investment recommendations are made by humans accountable to capital. The memo is a tool the analyst uses to communicate with the partnership. An agent that auto-renders `PASS` is asserting decision authority it does not have and was not granted — even when the prompt nominally invites that output.

### 2. Mode = `consider` is about analysis posture, not delegation of judgement

`consider` was designed to mean *"the memo evaluates the opportunity prospectively"* (vs. `justify` which is retrospective). Conflating *posture* (prospective vs. retrospective) with *verdict-rendering authority* (who calls PASS) was an implicit modeling decision that the current architecture inherits without intending to.

### 3. The default behavior is the wrong default

In any system where one of the outputs has high asymmetric cost, the default must protect against the high-cost case. Here:

- Cost of an agent-rendered PASS the analyst didn't want: high (credibility, IC time, analyst frustration, possibly the deal).
- Cost of an omitted verdict when the analyst wanted one: low (analyst writes 1–3 sentences).

The default should be **omit**. Verdict-rendering should be explicit opt-in via the analyst's input, not default-on.

## What other agent outputs share the same shape

This is not just about the `PASS / CONSIDER / COMMIT` verdict — it's a category of agent overreach. Other instances:

- **Closing-assessment prose** that summarizes "the case against" without being asked, when the analyst's intent is "make the case for."
- **Citation enrichment** that adds skeptical citations to balance bullish prose (the system trying to be "fair" in a context where the analyst wanted advocacy).
- **Risks-section autonomy** — the Alpha JWC outline explicitly front-loads Risks (intentionally), but even within that, the section sometimes renders meta-commentary like "these risks suggest caution is warranted." The analyst asked for risks articulated; they didn't ask for caution-rendering.
- **Scorecards** that produce numeric "buy / hold / sell" type aggregations the firm doesn't actually use that way.

## Resolution direction (not yet implemented)

This issue is a stub for the conversation. The eventual resolution probably composes the following:

1. **Couple verdict-rendering to analyst `intent:`** (per the proposed `intent:` field in [[Per-Deal-Focal-Points]]). When `intent: present-for-commit`, the writer should not render a contradicting verdict. When `intent: rule-out`, the writer can render `PASS` freely. When `intent: present-for-consider` or `intent: exploratory`, the writer renders the verdict with caveats explicit.
2. **Default to omission for verdict-shaped outputs.** Sections like Cash on Cash Return Probability should end with analyst-prompt placeholders (e.g., *"Analyst recommendation: [ ]"*) rather than agent-rendered verdicts, unless the analyst's `intent:` explicitly authorizes a verdict.
3. **Separate "analytical conclusion" from "recommendation."** It's fine for a section to conclude *"the bull-case math requires capturing 8% of category share by year 5, which has been done by 2 of 11 comparable companies."* That is analysis. Rendering *"Therefore: PASS"* is judgement. Today these are entangled.
4. **Tone calibration per `intent:`.** Advocacy mode = lean bullish, surface counter-arguments inside Risks (the front-loaded section already exists for this), avoid meta-commentary. Rule-out mode = lean skeptical, demand strong evidence for any bullish claim.
5. **Reaffirm the outline as a contract.** The outline lists `PASS / CONSIDER / COMMIT` as *available* outputs for the Recommendation section. Available ≠ required. The writer should be told that *"required_terms"* in the outline are required *if a recommendation is rendered at all*, not that a recommendation must be rendered.

## Where the bug surfaces in code

- `src/agents/writer.py` — the per-section writer, particularly when handling the final section (number 9 in alpha-jwc-7Cs-customized, named "Cash on Cash Return Probability"). The structure_template explicitly lists `"Recommendation: [PASS / CONSIDER / COMMIT]"` as a required element. The writer renders it.
- `src/agents/revise_summary_sections.py` — if this agent revises closing/summary sections it inherits the same verdict-rendering expectation.
- `src/agents/validator.py` — may score-penalize a section that *omits* the recommendation, creating a reverse-pressure on the writer to always include one.
- The outline YAML itself (`templates/outlines/direct-investment.yaml`, `io/alpha-jwc/templates/outlines/alpha-jwc-7Cs-customized.yaml`) — the `required_elements` and `recommendation_options` blocks are the contractual source of the requirement.

## Related

- [[Per-Deal-Focal-Points]] — the sister spec where the `intent:` field is proposed; this issue is one of the primary motivations for that field
- [[Separating-Retrieval-from-Generation-in-Agent-Pipelines]] — broader architectural direction; the verdict-rendering issue is the *prose-and-tone* analog of the citation-fabrication issue
- [[Faked-Sources-from-Perplexity]] — similar pattern of "agent doing more than asked, with asymmetric downside cost"
- `io/alpha-jwc/templates/outlines/alpha-jwc-7Cs-customized.yaml` — section 9 `recommendation_options: ["PASS", "CONSIDER", "COMMIT"]`
- `apps/memopop-orchestrator/AGENTS.md` — the operating contract for runtime agents; should be updated when the resolution lands here

## Open questions

- Is the right fix at the outline level (make recommendation optional / per-intent), the writer level (gate verdict-rendering on analyst signal), or both?
- Should the analyst be able to *pre-supply* the recommendation, and have the writer compose the closing prose around it? (Likely yes — this is the cleanest version of "analyst as decision-maker.")
- For `justify` mode where the firm has already invested, the recommendation is structurally always `COMMIT`. Is that the right default, or should `justify` mode also omit verdict-rendering entirely and let the analyst supply post-hoc framing?
- How should this interact with firm-level conventions? Some firms genuinely want an agent-rendered verdict as a draft starting point.

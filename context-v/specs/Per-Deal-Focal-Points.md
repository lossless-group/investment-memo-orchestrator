---
title: "Per-Deal Focal Points"
lede: "Analysts know things about a company that no automated pipeline will surface — the founder's prior wins, the partner thesis match, the IC concern to preempt, the angle that makes this deck worth the partnership's time. Per-deal focal points are the small, ordered list of human-supplied bullets that the writer agents must respect as load-bearing emphasis, not optional context."
date_authored_initial_draft: 2026-06-08
date_authored_current_draft: 2026-06-08
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-06-08
at_semantic_version: 0.0.0.1
status: Draft
augmented_with: Claude Code (Opus 4.7)
category: Specification
tags:
  - Analyst-Input
  - Memo-Generation
  - Writer-Agent
  - Per-Deal-Configuration
  - Prompt-Engineering
authors:
  - Michael Staton
image_prompt: A magnifying glass hovering over a single bullet point in a list, with light beams from the bullet illuminating downstream document sections highlighted in matching color; the rest of the bullets dimmed; deep-violet background, technical annotation labels in a monospaced font, analyst's desk aesthetic.
date_created: 2026-06-08
date_modified: 2026-06-08
---

# Per-Deal Focal Points

## Why this matters

Every memo the orchestrator writes is the *output of a system the analyst trusts to do most of the work* — research, drafting, citation, validation. But the system has no view into the things the analyst learned over coffee with the founder, the things the partner said in the pre-IC chat, or the things the firm's existing portfolio context implies for this specific deal. Without a place to put those, the analyst either (a) lets the memo be generic and edits afterward, or (b) stuffs the same intent into `notes:` on the deal JSON where it competes with logistics metadata. Neither is sufficient.

Per-deal focal points are a small, ordered list of bullets that the analyst supplies before any run. The writer agents read them, treat them as **load-bearing emphasis**, and shape section-level prose to reflect them. They are not research questions (those live in the outline). They are not facts (those live in the deck and Sources.md). They are *the angles the analyst wants foregrounded* — the thesis the memo is making the case for.

This document is the spec for the feature. It also includes a placeholder bullet list at the bottom that the analyst should fill in per deal.

## What problem this solves

Three failure modes the current pipeline has, each rooted in the absence of analyst-supplied emphasis:

1. **Generic prose that doesn't land for this firm + this deal.** The writer drafts plausible memo sections but doesn't know that *this firm cares about Indonesia exposure*, or *this partner's last deal was in the adjacent category*, or *the IC needs to hear about the team's prior IPO experience because we passed on the founders' last company*. The result reads correct but uncalibrated.
2. **Unsolicited verdicts that contradict the analyst's stance.** See [[Limiting-or-Omitting-Investor-Judgement]] — the memo rendered a `PASS` recommendation on a company the analyst was actively trying to present positively to the IC. The agent had no signal that the human's job here is advocacy, not adjudication.
3. **Buried strengths the deck doesn't fully argue.** Decks have to be short. The actual case is often something the founder told the analyst directly that didn't make slide N. Focal points are the channel for those.

## The artifact

Per-deal focal points live in the deal directory alongside `Sources.md`:

```
io/<firm>/deals/<deal>/inputs/
├── Sources.md
├── <deck>.pdf
└── focal-points.md         ← this file
```

`focal-points.md` is markdown with optional YAML frontmatter. The body is an ordered list of bullets; order matters (higher = more load-bearing). Each bullet is one to three sentences max — focal points, not paragraphs.

### Schema (proposed; refine during sign-off)

```yaml
---
deal: <DealName>
firm: <firm-slug>
date_authored_initial_draft: YYYY-MM-DD
date_last_updated: YYYY-MM-DD
analyst: <analyst-name>
at_semantic_version: 0.0.0.1
intent: <"present-for-commit" | "present-for-consider" | "rule-out" | "exploratory">
---

# Focal Points — <DealName>

1. **<short heading>** — <one to three sentences of analyst emphasis>
2. **<short heading>** — <…>
3. **<short heading>** — <…>
```

The `intent:` field is critical. It tells downstream agents whether the analyst is making the case (`present-for-commit`), exploring the case (`present-for-consider`), trying to find the kill-shot (`rule-out`), or doing pre-thesis research (`exploratory`). The agent's tone, verdict-rendering, and emphasis defaults all key off this.

## How agents consume it

Each affected agent gets a small change. None require new tools or model changes — only prompt updates.

1. **`writer.py`** — Inject the focal-points list at the top of each per-section prompt with explicit framing: *"These are analyst-supplied emphases for this deal. Treat them as load-bearing. If a section is the natural place to argue a focal point, argue it. Do not contradict a focal point."*
2. **`citation_enrichment.py`** (if retained per [[Separating-Retrieval-from-Generation-in-Agent-Pipelines]]) — Bias source-selection toward sources that support focal points where the focal point is a factual claim.
3. **`validator.py`** — Score docks if a focal point appears in the analyst input but does not appear (or is contradicted) anywhere in the memo body.
4. **Verdict-rendering agents** — Cross-reference `intent:` before emitting a verdict. See [[Limiting-or-Omitting-Investor-Judgement]] for the broader question of when agents should render verdicts at all.

## What this does NOT do

- **Does not become a backdoor for hallucination.** Focal points are emphasis, not facts. The writer is still constrained to ground claims in the corpus / deck / sources per the harvester-writer split.
- **Does not replace the outline.** Outlines define section structure, vocabulary, and source-tagging. Focal points sit on top.
- **Does not override `<insufficient-data>`.** If the analyst supplies a focal point that the research can't substantiate, the writer should attempt the angle, flag the gap, and surface it in the Diligence section. It does not invent.
- **Does not lock the prose.** Analyst-edited prose downstream of the agent run is still the source of truth. Focal points are inputs, not the contract.

## Open questions

- Should focal points appear in the rendered memo, or stay invisible (inputs only)? Default: invisible — the memo reads as memo, not as analyst commentary.
- Should there be a maximum number of bullets? Default: aim for 3–7, hard cap at 10. Beyond that the "focal" loses meaning.
- Should agents be allowed to *propose* additional focal points after a run, for the analyst to accept or reject in the next iteration? Tempting but adds complexity — defer.

## Related

- [[Limiting-or-Omitting-Investor-Judgement]] — sister issue that motivated the `intent:` field
- [[Separating-Retrieval-from-Generation-in-Agent-Pipelines]] — the architectural direction this spec composes with
- `apps/memopop-orchestrator/io/<firm>/deals/<deal>/inputs/Sources.md` — the sibling artifact (sources are facts; focal points are emphasis)

---

# Focal Points — Panthalassa (placeholder bullets — analyst to fill in)

> Replace the placeholders below with real focal points for the Panthalassa
> Series B memo, then move this file (or its body) to
> `io/alpha-jwc/deals/Panthalassa-Deck-Series-B/inputs/focal-points.md`.

1. **<focal point 1 — short heading>** — <analyst writes one to three sentences here>
2. **<focal point 2 — short heading>** — <…>
3. **<focal point 3 — short heading>** — <…>
4. **<focal point 4 — short heading>** — <…>
5. **<focal point 5 — short heading>** — <…>

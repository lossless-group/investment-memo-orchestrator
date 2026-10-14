---
title: "Funding Terms Invented Against the Deck Analysis"
lede: "A final draft stated a priced round three times the real raise; its own deck analysis had the right figure. Nothing caught it before it shipped."
publish: false
date_created: 2026-10-13
date_modified: 2026-10-13
date_authored_initial_draft: 2026-10-13
date_authored_current_draft: 2026-10-13
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5 (1M context)
at_semantic_version: 0.0.1.0
status: Open
site_uuid: 7be10d02-9974-4c92-b051-3fc77b8a0f8f
hex_code: xql64k
summary: >-
  A final draft (company codenamed Company A) stated the current round as a
  $35M Series A at a $300M post-money valuation. The actual round is a $12M
  SAFE bridge at a $100M post-money cap. The same run's 0-deck-analysis had the
  $12M figure, so the section writer contradicted its own input and validation
  and fact-check both passed it. Also covers operator-addressed chatter leaking
  into final drafts. Company, investor and client names are deliberately left
  out.
tags:
  - Issue-Resolution
  - Hallucination
  - Fact-Checking
  - Funding-Terms
---

# Funding Terms Invented Against the Deck Analysis

Names are codenamed throughout: **Company A** is the portfolio company,
**Lead Investor** its seed and bridge lead, **Workspace X** the workspace that
produced the bad draft, **Workspace Y** the workspace whose earlier memo had the
correct terms.

## What happened

A Workspace X final draft for Company A (`7-<Deal>-v0.0.1.md`, "Current
Round" in the Funding section) stated:

> Company A is raising a **$35M Series A** at a **$300M post-money valuation**
> ($265M pre-money). The round is led by Lead Investor...

The actual round, as an earlier Workspace Y memo recorded it from the signed
SAFE and founder conversations: a **Pre-Series A SAFE bridge** on the YC
post-money SAFE (v1.2), **$100M post-money cap**, **$12M target**, with Lead
Investor following on.

The same run's `0-deck-analysis.md` says "Specific Series A terms: $12M total,
$10M committed by insiders, $2M available". So the section writer did not just
lack the figure: it overrode its own input with a larger, rounder one. Neither
`3-validation` nor `4-fact-check` flagged it.

## Where the error travelled

- It was published on a public personal site as that company's investment memo
  (fixed 2026-10-13 by swapping in the Workspace Y memo).
- It was nearly re-issued for a second firm (caught before upload; that firm's
  memo is now built from the Workspace Y memo).
- A separate, earlier promotional page for the same company claimed a
  "$1B Series B" led by two large firms that are not in the round. Same failure
  shape, different run; also corrected.

## Related: chatter in final drafts

Two final drafts in another workspace carry a line addressed to the operator
from a revision step, for example "I'll apply the corrections now. Here is the
complete section with only the specified corrections applied:" and "Here is
the complete section with all appropriate links...". A downstream site import
now strips these, but the drafts themselves still contain them.

## What would have caught it

- A deterministic check in fact-check: every dollar figure in a Funding/Round
  section must appear in the deck analysis, the dataroom extraction, or a cited
  source; anything else is flagged, not passed.
- Treat terms from the deck and dataroom as authoritative over research results
  for the company's own round.
- Reject a section revision whose output starts with an instruction-following
  preamble.

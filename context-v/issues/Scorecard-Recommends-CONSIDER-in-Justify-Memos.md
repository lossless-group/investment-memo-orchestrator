---
title: "Scorecard Recommends CONSIDER in Justify Memos"
lede: "A deal config with a scorecard gets a recommendation block, a second set of numbered headings, and diligence questions in its memo, even in justify mode, where the decision is already made. The overview also scores dimensions from another framework as 0.0/5."
date_created: 2026-11-21
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Scorecard, Justify-Mode, Assembly]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
---

# Scorecard Recommends CONSIDER in Justify Memos

## What happens

A `justify` run whose deal config sets `"scorecard": "direct-early-stage-12Ps"` produced a memo with:

1. **A recommendation in the Executive Summary.** "Recommendation: CONSIDER", an overall score, and a table of dimension scores. `src/agents/scorecard_navigator.py` picks PASS / CONSIDER / COMMIT from score thresholds and never reads `memo_mode`. The scorecard agent's prompt is mode-aware, but the navigator isn't.
2. **Dimensions from another framework.** The navigator's `dim_display_names` and group map list the 7 Cs (Capital Syndicate, Category Leadership, …). With a 12Ps scorecard, the overview shows four rows at 0.0/5.
3. **A second set of numbered headings.** The scorecard block repeats the 12Ps group names as `## 1. Origins` … `## 5. Opportunity` inside the memo, so section numbers repeat.
4. **Diligence content.** "Areas of Concern" and "Critical Questions for Diligence" also appear in a memo supporting a decision already made. The firm's register keeps risks in the Risks section, mitigation-first.

Found 2026-11-21 in a fresh `justify` run. The memo was fixed by hand, and the deal config no longer sets `scorecard`. Other justify deals at the same firm don't set it, which is why this hadn't shown up.

## Fix

- In `justify` mode, the navigator emits no recommendation and no diligence questions. Either skip the scorecard insertion entirely, or keep a scores-only appendix with no PASS/CONSIDER line; decide which with the operator.
- Build the overview's display names from the scorecard definition being used, not a hard-coded 7 Cs map. A dimension the scorecard doesn't define must not render as 0.0/5.
- Insert the scorecard under one heading, with its groups as `###` subheadings, so the memo's section numbers stay unique.
- Tests: a justify run with a scorecard has no "Recommendation:" line, no repeated `## N.` headings, and no 0.0/5 rows for dimensions outside its scorecard.

## Second case: consider mode (2026-11-22)

A consider-mode 12Ps run (`io/humain`, deal Rockland, v0.0.2) shows the same overview bug. `src/agents/scorecard_navigator.py` hard-codes another framework's groups (`capital_quality`, `market_dominance`, `growth_durability`, `return_profile`) in `group_display`, so a 12Ps scorecard renders four rows of **0.0/5** in the Executive Summary under "Overall Score: 3.2/5 | Recommendation: CONSIDER". The overview should read its groups and dimension names from the scorecard JSON it was given, not from a fixed table. The scorecard section's "Critical Questions for Diligence" also leaked into this memo; see [[Consider-Mode-Has-No-Due-Diligence-Questionnaire]].

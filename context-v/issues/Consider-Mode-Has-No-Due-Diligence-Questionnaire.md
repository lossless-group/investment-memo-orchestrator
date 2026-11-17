---
title: "Consider Mode Has No Due Diligence Questionnaire, So Questions Leak Into the Memo"
lede: "A consider-mode run has nowhere to put questions for management. They end up in the section prose and the exports, and the outline asks for some of them there."
date_authored_initial_draft: 2026-11-16
date_authored_current_draft: 2026-11-16
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-11-16
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-11-16
date_modified: 2026-11-16
tags: [Consider-Mode, Diligence, Questions, Writer, Exports]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
status: Open
---

# Consider Mode Has No Due Diligence Questionnaire, So Questions Leak Into the Memo

## What the operator expects

A `consider` run should produce a Due Diligence Questionnaire (DDQ) as its own artifact. Any agent can add a question for management. The pipeline gathers and de-duplicates them in one place. The questions never appear in the `2-sections/` drafts, `4-final-draft.md`, or any export.

## What happens today

- **No DDQ artifact exists.** The only generated questions come from `scorecard_evaluator.generate_diligence_questions()`, and that runs only when a scorecard runs. It returns at most 7 generic questions, copied from the scorecard's evaluation guidance for any dimension scoring 2 or less. They are not deal-specific, and they land in `5-scorecard/12Ps-scorecard.md`.
- **The outline asks for questions in the body.** In `decile-group-deal-memo-template.yaml`, section 7 (Flags), `mode_specific.consider.consider` requires "Specific diligence items to resolve flags" and "Next steps with timeline". So under a CONSIDER verdict the writer is told to list diligence items in the memo.
- **No collector or stripper.** No agent gathers question-shaped prose, and no step removes it before assembly or export.

## Proposed shape

1. **A question marker**, in the same family as `<needs-source>` and `<insufficient-data>` (AGENTS.md §5). Writers and enrichers emit `<ddq topic="runway">…</ddq>` instead of prose questions.
2. **A collector node before assembly.** It pulls every `<ddq>` marker out of the section files and merges them with the scorecard questions and the deal's own `diligence_questionnaire` file, if the deal JSON names one. It de-duplicates them, groups them by topic, and writes `6-due-diligence-questionnaire.md`, then strips the markers from the sections.
3. **An export guard.** Before rendering, export fails or warns if a `<ddq>` marker or a line asking management a question survives into the final draft.
4. **Outline wording.** Change "Specific diligence items to resolve flags" to "Name the flags; the questions go to the DDQ."
5. **Deal-level seed.** The deal JSON's `diligence_questionnaire` field points to an analyst-curated file. The collector treats it as authoritative and appends model-generated questions under a separate heading.

## First case

`io/humain` New-Silicon (2026-11-16) seeds this with a hand-written `Due-Diligence-Questionnaire.md` and a deal-note editorial rule. That stopgap only works through the writer's prompt; nothing enforces it.

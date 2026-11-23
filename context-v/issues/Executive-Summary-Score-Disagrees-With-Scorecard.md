---
title: "Executive Summary Score Disagrees With the Scorecard"
lede: "The Executive Summary states an overall 12Ps score that the scorecard section, generated afterwards, contradicts: 3.7/5 versus 3.2/5 in the same memo."
date_created: 2026-11-22
date_modified: 2026-11-22
date_authored_initial_draft: 2026-11-22
date_authored_current_draft: 2026-11-22
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Scorecard, Executive-Summary, Assembly]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
---

# Executive Summary Score Disagrees With the Scorecard

## What happens

In `io/humain` Rockland v0.0.2 (2026-11-22), `01-executive-summary.md` says Rockland "scores **3.7/5 overall**, with standout dimensions in Problem (4.5/5), Potential (4.5/5) and People (4.0/5)". The scorecard evaluator then ran and wrote `5-scorecard/12Ps-scorecard.md` and section 8 with **3.2/5**, Problem 5/5 and different group scores. The writer drafts the Executive Summary before the evaluator scores, so it estimates the numbers itself.

## Expected

One score per memo. Either the Executive Summary is written (or its score sentence rewritten) after the scorecard evaluator runs, reading its numbers from `5-scorecard/12Ps-scorecard.json`, or the writer is told not to state scores at all.

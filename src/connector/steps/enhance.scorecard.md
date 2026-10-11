---
id: enhance.scorecard
title: Score the deal
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 100
version: "0"
reads: ["draft.section:*"]
produces:
  kind: enhancement
  checks:
    not_empty: true
    max_chars: 200000
path: "enhancements/enhance.scorecard/deal.md"
source_agent: src/agents/scorecard_agent.py
enabled: true
---
# Score the deal: {{company}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/scorecard_agent.py`.

Score the company on the firm's scorecard dimensions from the drafts in your inputs, with a one-line reason for each score.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.scorecard`, and your work as `content`. Then call `next_step`.

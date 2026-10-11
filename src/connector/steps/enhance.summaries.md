---
id: enhance.summaries
title: Revise the summary sections
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 110
version: "0"
reads: ["draft.section:*"]
produces:
  kind: enhancement
  checks:
    not_empty: true
    max_chars: 200000
path: "enhancements/enhance.summaries/deal.md"
source_agent: src/agents/revise_summary_sections.py
enabled: true
---
# Revise the summary sections: {{company}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/revise_summary_sections.py`.

Rewrite the executive summary and closing assessment so they match what the finished sections now say.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.summaries`, and your work as `content`. Then call `next_step`.

---
id: enhance.one_pager
title: Write the one-pager
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 120
version: "0"
reads: ["draft.section:*"]
produces:
  kind: enhancement
  checks:
    not_empty: true
    max_chars: 200000
path: "enhancements/enhance.one_pager/deal.md"
source_agent: src/agents/one_pager_generator.py
enabled: true
---
# Write the one-pager: {{company}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/one_pager_generator.py`.

Write a one-page cover sheet for the memo from the drafts in your inputs.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.one_pager`, and your work as `content`. Then call `next_step`.

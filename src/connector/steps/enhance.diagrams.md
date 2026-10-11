---
id: enhance.diagrams
title: Add diagrams to the memo
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 70
version: "0"
reads: ["draft.section:*"]
produces:
  kind: enhancement
  checks:
    not_empty: true
    max_chars: 200000
path: "enhancements/enhance.diagrams/deal.md"
source_agent: src/agents/diagram_generator.py
enabled: true
---
# Add diagrams to the memo: {{company}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/diagram_generator.py`.

Read the drafts in your inputs and propose diagrams (as Mermaid) where a picture explains the market or the business better than prose.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.diagrams`, and your work as `content`. Then call `next_step`.

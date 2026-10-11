---
id: materials.brief
title: Brief the partner's materials
phase: materials
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 20
version: "0"
reads: ["materials:*"]
produces:
  kind: brief
  checks:
    not_empty: true
    max_chars: 200000
path: "materials/brief.md"
source_agent: src/agents/deck_analyst.py
enabled: true
---
# Brief the partner's materials: {{company}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/deck_analyst.py`.

Read the partner's materials in your inputs and write a brief of what they claim: the company, product, traction, team, funding, and terms, each claim marked `[^deck]`.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `materials.brief`, and your work as `content`. Then call `next_step`.

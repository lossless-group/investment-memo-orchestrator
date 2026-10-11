---
id: research.sources
title: Consolidate the research sources
phase: research
scope: deal
required: false
runs_on: claude
needs_partner: true
order: 40
version: "0"
reads: ["research.section:*"]
produces:
  kind: sources
  checks:
    not_empty: true
    max_chars: 200000
path: "research/_sources.md"
source_agent: src/agents/source_aggregator.py
enabled: true
---
# Consolidate the research sources: {{company}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/source_aggregator.py`.

Read every section's research in your inputs and list the sources they cite, once each, grouped by publisher, flagging any that look unreliable.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `research.sources`, and your work as `content`. Then call `next_step`.

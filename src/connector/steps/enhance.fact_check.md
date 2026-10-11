---
id: enhance.fact_check
title: Fact-check a section
phase: enhance
scope: section
required: false
runs_on: claude
needs_partner: false
order: 90
version: "0"
reads: ["draft.section:@section", "research.section:@section"]
produces:
  kind: enhancement
  checks:
    not_empty: true
    max_chars: 200000
path: "enhancements/enhance.fact_check/{section}.md"
source_agent: src/agents/fact_checker.py
enabled: true
---
# Fact-check a section: {{company}} / {{section_name}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/fact_checker.py`.

Compare each claim in the section draft with its research and sources, and list any claim that is unsupported or contradicted.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.fact_check`, `section` = `{{section_key}}`, and your work as `content`. Then call `next_step`.

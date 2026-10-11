---
id: enhance.tables
title: Add tables to a section
phase: enhance
scope: section
required: false
runs_on: claude
needs_partner: false
order: 60
version: "0"
reads: ["draft.section:@section"]
produces:
  kind: enhancement
  checks:
    not_empty: true
    max_chars: 200000
path: "enhancements/enhance.tables/{section}.md"
source_agent: src/agents/table_generator.py
enabled: true
---
# Add tables to a section: {{company}} / {{section_name}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/table_generator.py`.

Read the section draft in your inputs and add markdown tables where figures are easier to compare in a table than in prose.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.tables`, `section` = `{{section_key}}`, and your work as `content`. Then call `next_step`.

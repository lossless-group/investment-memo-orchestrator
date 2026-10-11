---
id: enhance.citations
title: Strengthen a section's citations
phase: enhance
scope: section
required: false
runs_on: claude
needs_partner: false
order: 80
version: "0"
reads: ["draft.section:@section", "research.section:@section"]
produces:
  kind: enhancement
  checks:
    not_empty: true
    max_chars: 200000
path: "enhancements/enhance.citations/{section}.md"
source_agent: src/agents/citation_enrichment.py
enabled: true
---
# Strengthen a section's citations: {{company}} / {{section_name}}

> Interim instruction. Plan 5 replaces this with one adapted from
> `src/agents/citation_enrichment.py`.

Check every claim in the section draft has a citation from its research, and add or correct citations where they are missing.

This step is optional. If you can't do it well with what you have, tell the
partner in one line and submit a short note saying why as the `content`.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.citations`, `section` = `{{section_key}}`, and your work as `content`. Then call `next_step`.

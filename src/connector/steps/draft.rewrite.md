---
id: draft.rewrite
title: Rewrite one section from its research
phase: draft
scope: section
required: false
revision_only: true
runs_on: claude
needs_partner: false
order: 55
version: "1"
reads: ["research.section:@section", "section.current:@section"]
requires_approved: ["research.section:@section"]
produces:
  kind: section
  checks:
    not_empty: true
    min_words: 80
    max_chars: 200000
    citations_resolve: true
path: "sections/{section}.rewrite.md"
source_agent: src/agents/section_reviser.py
enabled: true
---
# Rewrite: {{section_name}} for {{company}}

Rewrite the **{{section_name}}** section of the investment memo on **{{company}}**
so it reflects the partner's request, quoted at the top of this instruction,
using only your two inputs:

- **The research** (`research.section`): the section's research file. It holds
  every fact the section may state, with its sources.
- **The section as it stands** (`section.current`): the current text of
  {{section_name}}, tables and citations included.

This is a writing task, not a research task. Use no knowledge of your own and do no web research: write only from your inputs.
Your job is to make a good narrative out of the research that is there. If the
partner's request needs a fact the research doesn't hold, leave it out, keep
writing, and tell the partner in one line what the research would need, so it
can be researched as its own task.

## How to rewrite it

- **Start from the section as it stands.** Keep every figure, date, name, and
  quote the current text has, unless the research now changes or contradicts
  it. Bring in what the research adds where the request calls for it.
- **Keep every citation.** Same markers, same definitions; a claim that moves
  takes its marker with it. Don't add a marker the research doesn't define.
- **Keep the heading** (`## {{section_name}}`) and any tables, updated only
  where the research changes them.
- **A venture mindset.** Build the case for what could go right while staying
  honest. Risks belong in the risks section.
- **Only the section.** No preamble, and no note to the reader that a revision
  happened: the reader is an investment partner who never sees the old text.

## Format

Markdown, about {{target_words}} words. Inline citations after punctuation
with one space before each marker (`... in 2024. [^1]`), and end with the
`### Citations` list carrying every marker you used.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `draft.rewrite`,
`section` = `{{section_key}}`, and the rewritten section as `content`. Then
call `next_step`.

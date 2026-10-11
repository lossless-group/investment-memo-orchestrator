---
id: enhance.tables
title: Add tables to a section
phase: enhance
scope: section
required: false
runs_on: claude
needs_partner: false
order: 60
version: "1"
reads: ["section.current:@section", "research.section:@section"]
produces:
  kind: section
  checks:
    not_empty: true
    min_words: 80
    max_chars: 200000
    citations_resolve: true
path: "enhancements/enhance.tables/{section}.md"
source_agent: src/agents/table_generator.py
enabled: true
---
# Add tables: {{company}} / {{section_name}}

Some figures read better in a table than in a paragraph: a funding history, a
team's credentials, market sizes, traction over time. Find those in the
**{{section_name}}** section of the memo on **{{company}}** and lay them out as
markdown tables, leaving the rest of the section as it is. What you submit
replaces the section in the compiled memo.

## What to read

- **The section** (`section.current`): the latest text of {{section_name}}. This
  is what you edit.
- **The section's research** (`research.section`): use it only to check a figure
  or fill a cell the section already implies. Don't bring in new facts.

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## What to look for

- **Funding rounds**: round, date, amount, valuation, lead investor. Put other
  participants in the last column; if there are more than three, list three and
  name the rest in a sentence below the table.
- **Team**: role, name, prior experience, one notable achievement.
- **Market sizing**: segment (TAM, SAM, SOM or named segments), size, growth,
  source.
- **Traction**: metric, value, period.
- **Any other series or comparison**: a figure tracked over time, or several
  companies compared on the same attributes.

## How to do it

- **Three or more comparable rows, or no table.** Two data points read fine in
  prose. Skip anything too qualitative to tabulate.
- **Don't duplicate an existing table.** If the section already has the table it
  needs, leave it.
- **Change nothing else.** Every sentence, figure, and citation outside the
  tables stays exactly as written. You may shorten a sentence whose figures now
  sit in the table right below it, but never drop a figure from the section.
- **Every figure keeps its citation.** Put the marker in the cell that holds the
  figure (`$12M [^3]`), using the same marker the prose used. Write `—` for a
  cell you have no figure for; never estimate one.
- **Place each table where it belongs**: after the paragraph that discusses those
  figures, not at the end of the section.
- **Bold {{company}}'s row** in a comparison with other companies.
- **Align numbers right** (`---:`) and text left (`:---`).

## Format

The whole section, in markdown:

- Starts with `## {{section_name}}`.
- The section's original prose, with your tables in place.
- Inline citations after punctuation with one space before each marker
  (`... in 2024. [^1]`); in a table cell, after the figure.
- Ends with the `### Citations` block, carrying the definition of every marker
  used in the section, in the form
  `[^1]: 2025, Jan 08. [Title](https://url). Publisher. Published: 2025-01-08 | Updated: N/A`.

It must be at least 80 words, and every `[^n]` must have a definition in the
`### Citations` block, or the submission is rejected.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.tables`,
`section` = `{{section_key}}`, and the whole section as `content`. Then call
`next_step`.

## If you can't do this step

This step is optional. If nothing in the section is tabular, or the section
already has the tables it needs, don't submit filler: call `submit_artifact`
with `deal` = `{{deal}}`, `step_id` = `enhance.tables`, `section` =
`{{section_key}}`, `skip` = `true`, and a one-sentence `reason`. Tell the
partner in one line that you skipped it and why, then call `next_step`.

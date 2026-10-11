---
id: research.sources
title: Consolidate the research sources
phase: research
scope: deal
required: false
runs_on: claude
needs_partner: true
order: 40
version: "1"
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
# Consolidate the sources: {{company}}

The memo should be written from sources the partner approved, not from whatever
the research happened to turn up. Gather every source the sections' research
cites into one deduplicated list, flag the weak ones, and let the partner strike
what they don't trust. Drafting will cite only the sources on the approved list.

## What to read

Your inputs hold the research for each section, each titled with the section's
name and ending in a `### Citations` block. Those blocks are what you
consolidate.

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## How to do it

- **One entry per URL.** The same URL cited by several sections (under different
  marker numbers) is one source. Keep the first complete title, publisher, and
  date you find for it.
- **Group by section**, in the order of the sections. A source cited by several
  sections is listed once, under the first section that cites it, and labelled
  with every section that cites it.
- **Order within a section**: reputable, accessible sources first (filings,
  established publishers, analyst reports), then by how many sections cite them.
  The partner's reorder is what counts; this is a starting point.
- **Keep the company's own materials.** `[^deck]` and similar entries are
  sources too; list them under the first section that uses them.
- **Change nothing in a citation line** except to fill in a missing field you can
  read from the research itself. Never invent a title, date, or URL.

## What to flag

Mark a source **⚠** with a short reason when it:

- uses a placeholder or reserved domain (`example.com`, `/path/to/`, `XXXXX`,
  `{id}`-style template text), or a bare report ID with no title in the path;
- looks dead or unreachable, or you couldn't open it;
- has no date, or is too old for the figure it supports;
- is a vendor's or the company's own marketing used for a market figure;
- is about a different company than {{company}} ({{url}}).

## Format

Markdown:

```
## <Section name>

- [^1]: 2025, Jan 08. [Title](https://url). Publisher. Published: 2025-01-08 | Updated: N/A
  Sections: Market, Traction
- [^2]: ... ⚠ undated; vendor marketing used for TAM
```

Renumber the markers `[^1]`, `[^2]`, ... across the whole list so each source has
one number. End with a line counting the sources and the flagged ones.

## Show the partner, then submit

1. Show the partner the list, with the flagged sources called out, and ask which
   to strike, which to keep despite a flag, and what is missing. Remove what they
   strike. Repeat until they approve it.
2. Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` =
   `research.sources`, the approved list as `content`, `partner_approved` =
   `true` once they approve, and their comments in `partner_notes`. Then call
   `next_step`.

You may submit before approval (with `partner_approved: false`) to save the work.

## If you can't do this step

This step is optional. If the research cites too few sources to be worth
consolidating, don't submit filler: call `submit_artifact` with `deal` =
`{{deal}}`, `step_id` = `research.sources`, `skip` = `true`, and a one-sentence
`reason` (a skip needs no approval). Tell the partner in one line that you
skipped it and why, then call `next_step`.

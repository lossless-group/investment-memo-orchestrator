---
id: enhance.citations
title: Strengthen a section's citations
phase: enhance
scope: section
required: false
runs_on: claude
needs_partner: false
order: 80
version: "1"
reads: ["section.current:@section", "research.section:@section", research.sources]
produces:
  kind: section
  checks:
    not_empty: true
    min_words: 80
    max_chars: 200000
    has_citations: 1
    citations_resolve: true
path: "enhancements/enhance.citations/{section}.md"
source_agent: src/agents/citation_enrichment.py
enabled: true
---
# Strengthen citations: {{company}} / {{section_name}}

A partner should be able to pick up the memo and trace any number in it to the
source that vouches for it. Go through the **{{section_name}}** section of the
memo on **{{company}}** and make sure every factual claim carries a correct
citation drawn from the section's research. You are adding and fixing
citations, not rewriting. What you submit replaces the section in the compiled
memo.

## What to read

- **The section** (`section.current`): the latest text of {{section_name}}. This
  is what you edit.
- **The section's research** (`research.section`): the facts and their sources.
  This is where your citations come from.
- **The approved sources** (`research.sources`), if present: the partner's
  consolidated source list. If it's in your inputs, cite only sources on it.

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## What needs a citation

Market sizes and growth rates; founding date, location, and team facts; funding
amounts, valuations, and investor names; product and technical specifics;
traction metrics and milestones; claims about competitors; any direct quote.

## How to do it

- **Keep every existing citation that is right.** Don't renumber, rename, merge,
  or tidy a marker. `[^deck]` stays `[^deck]`.
- **Add a citation to each uncited factual claim** the research supports. Reuse
  the research's definition for that source. New markers continue from the
  highest number already in the section.
- **Fix wrong citations.** If a marker points to a source that doesn't say what
  the sentence claims, point it at the source that does, or remove the marker.
- **Use only sources in your inputs.** Never invent a source, a title, a date, or
  a URL. No `example.com`, no placeholder paths, no report IDs you haven't seen.
  A claim with no source is better than a claim with a made-up one.
- **Claims nothing supports.** If no source in your inputs backs a claim, soften
  it to what the sources do say, or remove it. Tell the partner in one line which
  claims you softened or removed.
- **Change no prose** except to attach a citation or to soften or remove an
  unsupported claim. Every figure you don't remove stays exactly as written.

## Format

The whole section, in markdown:

- Starts with `## {{section_name}}`.
- Inline citations after punctuation with one space before each marker:
  `The market reached $50B in 2024. [^1]`
- Ends with one complete `### Citations` block: every marker used in the section,
  each defined once, in the form
  `[^1]: 2025, Jan 08. [Title](https://url). Publisher. Published: 2025-01-08 | Updated: N/A`.
  Two-digit days, the title wrapped in its link, both Published and Updated.

It must be at least 80 words, carry at least one citation, and every `[^n]` must
have a definition in the block, or the submission is rejected.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.citations`,
`section` = `{{section_key}}`, and the whole section as `content`. Then call
`next_step`.

## If you can't do this step

This step is optional. If the section's research has no sources to cite from,
don't submit filler: call `submit_artifact` with `deal` = `{{deal}}`, `step_id` =
`enhance.citations`, `section` = `{{section_key}}`, `skip` = `true`, and a
one-sentence `reason`. Tell the partner in one line that you skipped it and why,
then call `next_step`.

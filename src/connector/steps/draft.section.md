---
id: draft.section
title: Draft one section
phase: draft
scope: section
required: true
runs_on: claude
needs_partner: false
order: 50
version: "3"
reads: ["research.section:@section", materials.brief]
requires_approved: ["research.section:@section"]
produces:
  kind: section
  checks:
    not_empty: true
    min_words: 80
    max_chars: 200000
    citations_resolve: true
    hex_keys_match_sources: true
path: "sections/{section}.md"
source_agent: src/agents/writer.py
enabled: true
---
# Draft: {{section_name}} for {{company}}

Write the **{{section_name}}** section of the investment memo on **{{company}}**,
from the partner-approved research in your inputs. You are an investment analyst
at a venture capital firm; the memo goes to the investment committee.

## What the section covers

{{section_description}}

It should answer:

{{guiding_questions}}

Use no knowledge of your own and do no web research: write only from your inputs.
Researching and writing are separate tasks: if the section needs a fact the
research doesn't hold, leave it out and tell the partner in one line what's
missing, so it can be researched first.

## How to write it

- **Use the approved research.** Every fact comes from the research input (and
  the materials brief, if there is one). Don't add facts the partner hasn't
  seen. Keep the research's citations: same hex keys, same definitions. Never
  renumber or rename a key.
- **Specific over vague.** Exact numbers, dates, and names. No superlatives
  without data ("revolutionary", "massive market").
- **A venture mindset.** Build the case for what could go right while staying
  honest. Save risk enumeration for the risks section; don't end this section
  with caveats or "conditions to validate".
- **Scannable.** Short paragraphs, bullets where a list is clearer, acronyms
  spelled out on first use.
- **Only the section.** No preamble, no notes to the reader about how you
  wrote it.

## Format

Markdown, about {{target_words}} words. Start with `## {{section_name}}`. Inline
citations after punctuation with one space before each marker (`... in 2024. [^3vdxyl]`),
and end with the `### Citations` list carrying every marker you used.

## Citation keys

Each source gets a **hex key** made from the source itself, so the same source
has the same key in every section and two sources never share one (the memo
numbers them only when it is rendered):

Copy the keys the research uses. If you cite a source the research keyed
with placeholder letters, keep them. A key is made like this:

1. Take the first `https://`, `http://` or `file://` link in the source's
   citation line, percent-decode it, lowercase it, and drop a trailing `/`.
   A source with no link uses its citation text without the date, with runs of
   whitespace collapsed to one space, lowercased.
2. Hash that with SHA-256, read the digest as one integer, and write it in
   base 36 (`0-9a-z`). The key is the first six characters.

`https://full-url` gives `[^3vdxyl]`. If you can run code, compute each key that
way. If you can't, don't guess one: use short placeholder letters (`[^a]`,
`[^b]`, ...) and the server converts them to hex keys when the memo compiles. A
hex-looking key that doesn't match its source is refused, and the refusal says
which key the source gives.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `draft.section`,
`section` = `{{section_key}}`, and the draft as `content`. Then call
`next_step`.

---
id: enhance.fact_check
title: Fact-check a section
phase: enhance
scope: section
required: false
runs_on: claude
needs_partner: false
order: 90
version: "1"
reads: ["section.current:@section", "research.section:@section"]
produces:
  kind: section
  checks:
    not_empty: true
    min_words: 80
    max_chars: 200000
    citations_resolve: true
path: "enhancements/enhance.fact_check/{section}.md"
source_agent: src/agents/fact_checker.py
enabled: true
---
# Fact-check: {{company}} / {{section_name}}

Check every factual claim in the **{{section_name}}** section of the memo on
**{{company}}** against its research, fix what is wrong, and submit the
corrected section. Two kinds of error matter here: a claim the research doesn't
support, and a true, cited claim about the wrong company. What you submit
replaces the section in the compiled memo.

## What to read

- **The section** (`section.current`): the latest text of {{section_name}}. This
  is what you check and correct.
- **The section's research** (`research.section`): the facts and sources the
  section was written from. This is your reference.

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## What to check

- **Every specific claim**: dollar figures, percentages, growth rates, customer
  and user counts, valuations, round sizes, pricing, runway, team size, dates,
  customer and partner names. Statements that data is unavailable ("not
  disclosed") are not claims; leave them.
- **Is it supported?** Find the claim in the research. The figure, date, or name
  must match what the cited source says, not a rounded or drifted version.
- **Is it cited?** A specific figure with no citation and no support in the
  research is the highest-risk kind of error: it was probably invented.
- **Is it about {{company}}?** A sentence can be true, sourced, and about a
  competitor. If a figure comes from a passage about another company (its round,
  its valuation, its user count), it must not be stated as {{company}}'s. Check
  this hardest in funding and traction claims, and wherever the section discusses
  competitors.
- **Is it the right company?** If the research looks like it describes a
  different company with the same name (a different website than {{url}}),
  stop and tell the partner before correcting anything.

## How to correct

- **Fix the claim to what the source says**, keeping its citation. If the
  research has a better source for the corrected figure, cite that one.
- **Remove a claim** when nothing in the research supports it. Don't hedge it
  into vagueness.
- **Re-attribute a misattributed claim** to the company it is about, or remove
  it if it doesn't belong in this section.
- **Use only sources in the research.** Remove any citation whose source isn't
  in the research, along with its definition. Never invent a source or URL.
- **Change nothing else.** Every sentence, figure, and citation you didn't
  correct stays exactly as written. Don't rephrase, reorganize, or improve.

## Tell the partner

In chat (not in the content), give the partner a short list of what you changed:
each original claim, what you changed it to or that you removed it, and why. If
nothing needed correcting, say so in one line.

## Format

The whole corrected section, in markdown:

- Starts with `## {{section_name}}`.
- Inline citations after punctuation with one space before each marker
  (`... in 2024. [^1]`).
- Ends with the `### Citations` block, carrying the definition of every marker
  still used, in the form
  `[^1]: 2025, Jan 08. [Title](https://url). Publisher. Published: 2025-01-08 | Updated: N/A`.

If nothing needed correcting, submit the section unchanged: that records that the
check ran. It must be at least 80 words, and every `[^n]` must have a definition,
or the submission is rejected.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.fact_check`,
`section` = `{{section_key}}`, and the whole corrected section as `content`.
Then call `next_step`.

## If you can't do this step

This step is optional. If the section has no research to check against, don't
submit filler: call `submit_artifact` with `deal` = `{{deal}}`, `step_id` =
`enhance.fact_check`, `section` = `{{section_key}}`, `skip` = `true`, and a
one-sentence `reason`. Tell the partner in one line that you skipped it and why,
then call `next_step`.

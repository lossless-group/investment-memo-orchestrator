---
id: enhance.summaries
title: Revise the summary sections
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 110
version: "1"
reads: ["section.current:*", enhance.scorecard]
produces:
  kind: summaries
  checks:
    not_empty: true
    min_words: 80
    max_chars: 60000
    citations_resolve: true
path: "enhancements/enhance.summaries/deal.md"
source_agent: src/agents/revise_summary_sections.py
enabled: true
---
# Revise the summaries: {{company}}

The executive summary and the closing assessment were drafted before the rest of
the memo was finished, checked, and corrected. Rewrite them so they match what
the finished sections now say about **{{company}}**. The server replaces those
sections in the compiled memo with what you submit.

## What to read

- **Every section** (`section.current`): the current text of each, titled with
  the section's name. The bookends are usually the first section (the executive
  summary) and the last (a closing assessment or recommendation), if the outline
  has one.
- **The scorecard** (`enhance.scorecard`), if present: use its scores and
  overall verdict in the closing section.

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## The executive summary

- **Reflect the memo, not speculation.** Every claim comes from a section.
- **Lead with the few figures that matter**: the round and terms, traction, and
  market size, exactly as the sections state them.
- **No false hedging.** Don't write "data not available" for anything a section
  states. Don't make excuses; write a confident, accurate summary.
- **About the length of the existing summary**, or about 300 words if there is
  none.

## The closing assessment

- **Synthesise, don't repeat the summary.** Weigh the strengths against the
  risks as the sections actually present them.
- **Give a clear recommendation** with its rationale, and the concrete diligence
  items still open. If there is a scorecard, its verdict and lowest scores belong
  here.
- **If the firm has already invested** (the memo says so), restate why with
  conviction instead: no weighing, no open questions, no "remains unproven".
- **Up to three paragraphs**, around 400 to 600 words.

## Rules for both

- **Figures stay exact.** Every figure you use appears in the sections with the
  same value. Don't round $5.9M to $6M.
- **Only {{company}}'s facts.** A competitor's raise, valuation, or user count
  must never appear as {{company}}'s. This is the error that survives every other
  check: the number is real, cited, and about someone else. If a figure sits in a
  sentence about another company, it isn't {{company}}'s.
- **Cite lightly.** These summarise sections that are already sourced. Cite only
  where a single number carries a lot of weight. Any marker you use must already
  exist in the memo, with its definition copied unchanged.
- **Add nothing new.** No facts, sources, or sections that aren't in the memo.

## Format

Each rewritten section under its heading, exactly as the section's name appears
in your inputs' titles, one after the other:

```
## <Executive summary section name>

...

## <Closing section name>

...

### Citations

[^1]: 2025, Jan 08. [Title](https://url). Publisher. Published: 2025-01-08 | Updated: N/A
```

One `### Citations` block at the end covers both sections; leave it out if you
cited nothing. A heading that matches no section is ignored, so copy the names
exactly. If the outline has no closing section, submit only the executive
summary. The content must be at least 80 words, and every `[^n]` must be defined,
or the submission is rejected.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.summaries`,
and the rewritten sections as `content`. Then call `next_step`.

## If you can't do this step

This step is optional. If the outline has no summary or closing section to
revise, don't submit filler: call `submit_artifact` with `deal` = `{{deal}}`,
`step_id` = `enhance.summaries`, `skip` = `true`, and a one-sentence `reason`.
Tell the partner in one line that you skipped it and why, then call `next_step`.

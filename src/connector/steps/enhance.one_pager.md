---
id: enhance.one_pager
title: Write the one-pager
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 120
version: "1"
reads: ["section.current:*", enhance.scorecard, enhance.summaries]
produces:
  kind: one_pager
  checks:
    not_empty: true
    min_words: 80
    max_chars: 20000
path: "enhancements/enhance.one_pager/deal.md"
source_agent: src/agents/one_pager_generator.py
enabled: true
---
# One-pager: {{company}}

Distil the memo on **{{company}}** into one page a partner can read in two
minutes: what the company does, the deal, the numbers that matter, and the
recommendation. It is saved beside the memo, not inside it; the partner reads it
with `get_artifact`.

## What to read

- **Every section** (`section.current`): the current text of each.
- **The revised summaries** (`enhance.summaries`), if present: the most up-to-date
  framing of the deal.
- **The scorecard** (`enhance.scorecard`), if present: the overall score and
  verdict.

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## How to write it

- **Exact figures from the memo.** Copy numbers, names, and metrics as the memo
  states them. Don't round or paraphrase them.
- **Nothing new.** Every item comes from the memo. If the memo has nothing for a
  slot, leave the slot out; don't write "not available".
- **Only {{company}}'s facts.** No competitor's figures stated as {{company}}'s.
- **The company name exactly as written**: {{company}}. Don't shorten or
  "correct" it.
- **Pick the most compelling points**, the ones that would make an investor read
  the full memo.
- **Under 600 words.** Hard limit.

## Format

Markdown, in this order, leaving out any part the memo has nothing for:

```
# {{company}}

*One-line description of the company, at most 10 words.*

**The hook, in one sentence of at most 20 words.** One or two sentences of
context: market, positioning, timing.

## The deal
- Stage, round size, valuation, lead investor, other participants (up to six)
- Location, team size

## Key metrics
- **Label:** value (three to six)

## Why now
- Three bullets, at most 30 words each, key terms in **bold**

## Market
- Two or three figures, e.g. "TAM projected to reach **$50B by 2030**"

## Team
- Founders and key hires, with the one credential that matters

## Traction
- Three or four milestones, at most 15 words each

## Risks
- The two or three that matter most

## Recommendation
**PASS / CONSIDER / COMMIT.** One or two sentences why.
```

Use the scorecard's verdict if there is one. Citations are not needed here (the
memo carries them). It must be at least 80 words and under 20,000 characters, or
the submission is rejected.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.one_pager`,
and the one-pager as `content`. Then call `next_step`.

## If you can't do this step

This step is optional. If the memo is too incomplete to summarise on one page,
don't submit filler: call `submit_artifact` with `deal` = `{{deal}}`, `step_id` =
`enhance.one_pager`, `skip` = `true`, and a one-sentence `reason`. Tell the
partner in one line that you skipped it and why, then call `next_step`.

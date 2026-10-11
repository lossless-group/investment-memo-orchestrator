---
id: enhance.scorecard
title: Score the deal
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 100
version: "1"
reads: ["section.current:*"]
produces:
  kind: scorecard
  checks:
    not_empty: true
    min_words: 80
    max_chars: 60000
    required_headings: ["## Scorecard"]
path: "enhancements/enhance.scorecard/deal.md"
source_agent: src/agents/scorecard_evaluator.py
enabled: true
---
# Scorecard: {{company}}

Score **{{company}}** on the dimensions the memo is organised around, using only
the evidence in the memo, and list the diligence questions that would move the
lowest scores. The server appends your scorecard to the compiled memo after the
last section.

## What to read

Your inputs hold the current text of every section, each titled with the
section's name. Read all of them before scoring.

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## Choose the dimensions

- **Use the dimensions the memo's sections imply.** Most firms' templates are
  organised around their own framework (for example "Capital Syndicate",
  "Category Leadership", "Capital Efficiency"); score each of those.
- **If the memo is organised by the 12Ps** (Problem, Product, People, Potential,
  and so on), score the 12Ps.
- **Otherwise**, score the standard dimensions of a venture memo: team, market,
  product, traction, business model, competition, and terms. Leave out sections
  that aren't judgements, such as the executive summary or the risks list.

## How to score

Use a 1 to 5 scale:

| Score | Meaning |
|---|---|
| 5 | Exceptional: top 5% of deals at this stage |
| 4 | Above average: top 10 to 25% |
| 3 | Meets the bar: top 50% |
| 2 | Below average |
| 1 | Weak or disqualifying |

- **No score without evidence.** Each score cites what the memo actually says:
  a figure, a name, a fact. If the memo has nothing on a dimension, score it 2 and
  write that the memo has no evidence, rather than guessing.
- **Judge against the stage.** {{company}} is at {{stage}}. Score what is
  reasonable to expect at that stage, not at a later one.
- **Look for red flags as well as strengths**: no clear lead investor, prior
  investors not following on, growth that depends on one customer, a market
  figure that is only the company's own claim.
- **Only {{company}}'s evidence.** A competitor's traction is not evidence for
  {{company}}.

## Format

Markdown, exactly in this order:

1. The heading `## Scorecard`.
2. A table with these columns:

   ```
   | Dimension | Score (1-5) | Evidence |
   |:---|:---:|:---|
   | Capital Syndicate | 4 | Led by ... with ... following on. |
   ```

   One row per dimension; evidence is one or two sentences from the memo.
3. An overall line: `**Overall: 3.4 / 5**` (the average), then one sentence on
   what drives it. Use PASS if any dimension scores 1 or the average is below 2.5;
   COMMIT only if no dimension is below 3, the average is above 3.5, and at least
   two dimensions score 5; otherwise CONSIDER.
4. `### Diligence questions`: three to seven questions, each tagged with the
   dimension it would move (`- [Capital Efficiency] What is monthly burn ...?`),
   starting with the lowest scores.

Citations are optional. If you use any, every `[^n]` must be defined in a
`### Citations` block at the end, copied from the memo. The content must start
with `## Scorecard` and be at least 80 words, or the submission is rejected.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.scorecard`,
and the scorecard as `content`. Then call `next_step`.

## If you can't do this step

This step is optional. If the memo has too few finished sections to score
fairly, don't submit filler: call `submit_artifact` with `deal` = `{{deal}}`,
`step_id` = `enhance.scorecard`, `skip` = `true`, and a one-sentence `reason`.
Tell the partner in one line that you skipped it and why, then call `next_step`.

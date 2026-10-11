---
id: enhance.diagrams
title: Add a market-sizing diagram
phase: enhance
scope: deal
required: false
runs_on: claude
needs_partner: false
order: 70
version: "1"
reads: ["section.current:*"]
produces:
  kind: diagrams
  checks:
    not_empty: true
    max_chars: 20000
    fenced_yaml: [section, tam, sam, som]
path: "enhancements/enhance.diagrams/deal.md"
source_agent: src/agents/diagram_generator.py
enabled: true
---
# Market-sizing diagram: {{company}}

A TAM / SAM / SOM diagram shows the size of {{company}}'s market at a glance:
three circles, each sized to its figure. You don't draw it. You find the three
figures the memo already states, with citations, and submit them as data; the
server draws the diagram and places it in the section you name when it
compiles the memo.

## What to read

Your inputs hold the current text of every section, each titled with the
section's name. Each input's `artifact_id` ends with the section's key after the
colon (for `section.current:02-market`, the key is `02-market`).

If an input says `truncated: true`, call `get_artifact` with `deal` = `{{deal}}`,
its `artifact_id`, and `offset` = its `next_offset` until you have all of it.

## How to do it

- **Find the three figures.** Look for the Total Addressable Market (TAM), the
  Serviceable Addressable Market (SAM), and the Serviceable Obtainable Market
  (SOM), usually in the market section. Each one must be stated in the memo and
  carry a citation there.
- **Never estimate or derive a figure.** If the memo gives a TAM but no SAM,
  don't compute a SAM as a share of the TAM. Missing any of the three means you
  skip this step.
- **TAM ≥ SAM ≥ SOM.** If the memo's figures don't nest that way, they are
  probably from different scopes or years. Skip rather than draw a misleading
  picture, and tell the partner which figures conflict.
- **{{company}}'s market, not a competitor's.** A market figure quoted in a
  competitor's context is not {{company}}'s SAM.
- **Same year where you can.** If the figures refer to different years, use the
  ones that match and say so in the closing line.
- **Growth rates are optional.** Include `tam_growth`, `sam_growth`, or
  `som_growth` only when the memo states one for that figure (e.g. "12% CAGR").
- **Name the section the diagram belongs in**: the section where the figures
  are discussed, by its key.

## Format

Exactly this shape, and nothing else:

````
## Market sizing

```yaml
section: 02-market
tam: "$50B"
sam: "$5B"
som: "$500M"
tam_growth: "12% CAGR"
year: 2025
```

One line on where each figure comes from in the memo.
````

- `section`: the key of the section the diagram belongs in, from the inputs'
  `artifact_id` (after the colon).
- `tam`, `sam`, `som`: the dollar figures as the memo writes them: `$`, then the
  number, then `K`, `M`, `B`, or `T`, or the word `million` or `billion`
  (`"$50B"`, `"$12.5 billion"`). Quote them.
- `tam_growth`, `sam_growth`, `som_growth`: optional, as written in the memo.
- `year`: optional, the year the figures refer to.
- The closing line names, for each figure, the section and the sentence it comes
  from (e.g. "TAM and SAM from Market, paragraph 2; SOM from Traction").

The fenced `yaml` block must contain `section`, `tam`, `sam`, and `som`, or the
submission is rejected.

## Submit

Call `submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.diagrams`,
and the block above as `content`. Then call `next_step`.

## If you can't do this step

This step is optional. If the memo doesn't state all three of TAM, SAM, and SOM
with citations, or the figures don't nest, don't submit filler: call
`submit_artifact` with `deal` = `{{deal}}`, `step_id` = `enhance.diagrams`,
`skip` = `true`, and a one-sentence `reason`. Tell the partner in one line that
you skipped it and why, then call `next_step`.

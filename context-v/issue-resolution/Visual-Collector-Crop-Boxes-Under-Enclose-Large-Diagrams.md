---
title: "Visual Collector Crop Boxes Under-Enclose Large Diagrams"
lede: "The visual collectors reliably find and classify what is on a slide; the bounding boxes they draw around large diagrams and timelines sometimes stop short of the visual's true edges. Deferred — the crop is preserved and reusable either way, and precision can be improved without re-deriving anything else."
date_authored_initial_draft: 2026-08-23
date_authored_current_draft: 2026-08-23
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-08-23
date_modified: 2026-08-23
tags: [Slide-Stenographer, Visual-Collectors, Claude-Vision, Bounding-Boxes, Deferred, Issue-Resolution]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
status: Deferred
severity: Low
---

# Visual Collector Crop Boxes Under-Enclose Large Diagrams

## What happens

`src/agents/slides/visual_collector.py` detects visual elements on a rendered
slide and crops each one out. Detection and classification are reliable.
**Extent is not.** On large composite visuals the reported box sometimes encloses
the dense middle of the diagram and stops before its outer nodes, its
surrounding labels, or the band of text along its base.

Measured against an operator's read of one 38-slide deck, using the eight slides
whose contents were known independently:

| Slide | Operator's read | Collector's result | Crop extent |
|---|---|---|---|
| 04 | fact callout | `fact_callout` ×3 | 6–9% |
| 06 | table | `chart/table` | 22% |
| 09 | chart | `chart/line` | 44% |
| 23 | one large diagram | `framework` | **100%** ✓ |
| 25 | one large diagram | `framework` | 75% — under-encloses |
| 31 | one large diagram | `framework` | **100%** ✓ |
| 33 | timeline | `timeline` | 47% — under-encloses |
| 34 | non-standard chart | `diagram` | 27% — under-encloses, wrong collector |

Five of eight correct, two under-cropped, one both under-cropped and routed to
the wrong collector.

## Why it is deferred

The crop is **preserved and reusable** regardless of how tightly it is drawn.
Everything downstream generation needs already survives:

- the rendered slide image at full extent, beside the crop
- the crop's normalized box, so it can be recomputed at any time without another
  model call
- what the visual depicts, its kind, its role, and its alt text
- for charts, the axis titles, legend, series, and units
- provenance: slide, deck, variant, version, company, and date

A tight box is a presentation improvement, not a data-integrity problem.
Correcting it later re-crops from an image already on disk using a box already
recorded — nothing else has to be re-derived, and no transcription is at risk.

## What has already been tried

Three rounds of increasingly explicit instruction, each verified against the same
eight slides:

1. **Padding.** Charts get 6% of the region's own size added to every edge,
   doubled when the model reports the key falls outside its own box. Helped
   charts; did not help large diagrams, whose boxes are wrong by a third rather
   than by a margin.
2. **A granularity rule.** "Report the largest coherent visual unit, never its
   parts", leading with "is this slide essentially ONE visual?". This fixed the
   opposite failure — slides 23 and 34 had been split into two half-diagrams
   each — and fixed nothing about extent.
3. **An explicit extent instruction.** "Extend every box to the visual's true
   edges… when in doubt, extend outward to the slide's margins. An over-wide
   crop is recoverable; a crop missing a third of the diagram is not." Slides 25,
   33, and 34 were unchanged.

The underlying constraint: **a vision model estimates regions, it does not
measure them.** Prompt engineering has reached its useful limit here, and further
revisions would be guessing.

## Options when this is picked up

1. **Full-slide fallback for solo visuals.** When a slide reports exactly one
   region and that region is classified as a large composite kind
   (`framework`, `diagram`, `roadmap`, `timeline`, `architecture`), crop the
   whole slide instead of the reported box. Cheap, and correct for slides 25 and
   33 — the very cases where the operator's description was "the slide *is* one
   giant diagram". Costs the title bar, which is usually wanted anyway.
2. **Edge detection.** Find the visual's true extent from the pixels — content
   bounding box after thresholding out the background — and use the model's box
   only to choose *which* connected region. No extra model calls.
3. **A manual override.** A `crop_override` field in the slide document, honored
   ahead of the reported box. The deck is the source of truth and sometimes so is
   the analyst; a human who has looked at the slide should be able to say so
   once and have it persist across re-runs.
4. **A verification pass.** Re-show the model its own crop and ask whether
   anything was cut off. Doubles the cost per region and is still an estimate.

Option 1 is the cheapest correct-most-of-the-time fix; option 3 is the one that
makes the other three unnecessary for any slide a person has actually reviewed.

## Related

- `changelog/2026-08-23_02.md` — the stenographer and collectors
- `src/agents/slides/visual_collector.py` — `crop_region()` holds the padding and
  area guards; `_DETECTION_PROMPT` holds the granularity and extent instructions

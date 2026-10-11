---
id: compile.assemble
title: Assemble and export the memo
phase: compile
scope: deal
required: true
runs_on: server
needs_partner: false
order: 200
version: "1"
reads: ["draft.section:*"]
produces:
  kind: compiled
  checks:
    not_empty: true
    max_chars: 200000
path: "compiled/{version}/memo.md"
source_agent: src/agents/citation_assembly.py
enabled: true
---
# Assemble and export the memo

Runs on the server inside `compile`; Claude never receives this step, and
nothing is submitted for it with `submit_artifact`. It is listed so the registry,
the docs, and `compile`'s report can name it.

What it does, in order, with no model (`src/connector/compile/pipeline.py`):

1. **Sections** (required): each section's current text in outline order (the
   latest of its draft and the tables, citations, and fact-check revisions);
   the revised summaries replace their sections by heading; the scorecard is
   added after the last section.
2. **Citations** (required): every section's local citations consolidated into
   one block, numbered 1 to N by first appearance, one number per source.
3. **Spacing**, **table of contents**, **deck images**, **market-sizing diagram**
   (each optional: switched off by `MEMOPOP_DISABLED_STEPS` as `compile.spacing`,
   `compile.toc`, `compile.deck_images`, `compile.diagrams`, or skipped with
   `step_failed` if it raises).
4. **Finalize** (required), then the branded HTML and the PDF.

The memo's markdown is saved as the `compile.assemble` artifact; the HTML and
PDF go to the firm's bucket under `compiled/<deal>/<version>/`.

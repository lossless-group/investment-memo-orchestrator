---
title: "Final Draft Citations Collide Across Sections"
lede: "Each section's research file numbers its sources from 1, but final assembly treats citation keys as global. Every section's [^25] resolves to whichever section defined [^25] first, so most citations in the final draft and exports point to the wrong source."
date_authored_initial_draft: 2026-11-17
date_authored_current_draft: 2026-11-17
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-11-17
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-11-17
date_modified: 2026-11-17
tags: [Citations, Assembly, Codified-Mode, Final-Draft]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
status: Open
---

# Final Draft Citations Collide Across Sections

## What happens

1. In codified mode, `codified_section_researcher` writes `1-research/<NN>-<section>-research.md` with definitions numbered `[^1]..[^N]` from `sources_for_section()`. Each section's numbering is local: Overview's `[^25]` is the Cisco–Acacia release, Flags' `[^25]` is the Openspace rebrand article.
2. The writer cites with those local keys, and `2-sections/*.md` keeps them correctly.
3. `assemble_citations()` calls `renumber_citations()`, which:
   - builds one global `appearance_order` from every section's inline keys, so the same key in two sections becomes one entry;
   - fills `all_definitions` first-come-first-served from section files, then from every `1-research/*.md` in sorted order, so `[^25]` takes Overview's definition for every section.
4. The final draft and every export carry these wrong mappings. The run log shows it: "Found 34 unique citations across 9 sections" for a memo citing about 70 distinct sources.

First case: `io/humain` New-Silicon v0.0.1 (2026-11-17). Flags cited the company pro forma; the final draft linked that claim to an Intel press release.

## Fix

`consolidate_citations()` in the same module already treats each text's keys as local and identifies sources by URL (the connector's compile path uses it). `assemble_citations()` should pass each section with its own research file's definitions through `consolidate_citations()`, not `renumber_citations()`.

Add a test with two sections that share a key but cite different sources.

## Repair used on the first case

A one-off script remapped each section region of the existing final draft: global number → section-local key (inverting the run's own `old_to_new`), local key → that section's research definition, then `consolidate_citations()` across all regions.

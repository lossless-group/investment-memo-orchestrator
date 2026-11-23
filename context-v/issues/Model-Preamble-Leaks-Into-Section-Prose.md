---
title: "Model Preamble Leaks Into Section Prose"
lede: "A link-enrichment pass left its own working note, \"I'll add links to the FIRST mention of each entity using their official .gov websites.\", as a line of the Origins section, and it survived into the final draft."
date_created: 2026-11-22
date_modified: 2026-11-22
date_authored_initial_draft: 2026-11-22
date_authored_current_draft: 2026-11-22
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Enrichment, Links, Assembly, Validation]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
---

# Model Preamble Leaks Into Section Prose

## What happens

In `io/humain` Rockland v0.0.2 (2026-11-22), `2-sections/02-origins.md` line 8 reads:

> I'll add links to the FIRST mention of each entity using their official .gov websites.

That is the model narrating its task, not memo prose. It came from a link-enrichment step that writes the model's whole reply back into the section. It passed validation (9.5/10) and reached `7-Rockland-v0.0.2.md`.

## Expected

Enrichment passes return only the edited section. Anything before the first line of the original section text is dropped, or the pass fails closed.

## Proposed fix

1. In the link enrichers (`src/agents/link_enrichment*.py`, `cli/enrich_links.py`), strip leading lines that describe the task ("I'll", "I will", "Here is", "Here's", "Below is") before writing.
2. A guard in assembly or validation that flags a line in first person future tense addressed to no one.

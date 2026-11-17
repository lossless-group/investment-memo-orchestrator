---
title: "Dataroom Citations Duplicate in the Consolidated Block"
lede: "consolidate_citations() identifies a source by its http(s) URL. Dataroom sources are file:// links, so they fall back to the full definition text, and the same document cited from two sections gets two numbers whenever the sections describe its publisher differently."
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
tags: [Citations, Assembly, Dataroom, Deduplication]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
status: Resolved
---

# Dataroom Citations Duplicate in the Consolidated Block

## What happens

`_source_identity()` in `src/agents/citation_assembly.py` matches only `https?://` URLs. A dataroom citation links to `file:///…/inputs/<dataroom>/…pdf`, so it gets no URL identity and falls back to the whole definition text. Each section's research file writes its own publisher wording for the same document ("New Silicon Corporation", "Company-prepared spreadsheet", "New Silicon Corporation Pte. Ltd."). Those strings differ, so the consolidated block gives one document several numbers.

First case: `io/humain` New-Silicon v0.0.1 (2026-11-17). Twenty-seven documents appeared under more than one citation number, including the company pro forma cap table under three (`[^57]`, `[^90]`, `[^116]`).

## Fix

- Identify a source by any link scheme (`https`, `http`, `file`), percent-decoded, with any trailing slash removed and lowercased. Keep the definition-text fallback only for definitions without a link.
- When two definitions share an identity, keep the first.
- Test: two sections cite the same `file://` document with different publisher text and get one number. An `http` URL and its percent-encoded form also get one number.
- Guard: after consolidation, assert that no two definitions in the block share an identity, so a final output can never carry duplicate reference definitions.

## Resolution (2026-11-17)

- `_source_identity()` now matches `file://` as well as `http(s)://` links, and percent-decodes them.
- New `merge_duplicate_definitions()` is the last step in `assemble_citations()` before the final draft is written. It merges definitions with the same identity and renumbers citations 1..N, so no final draft can carry two definitions for one source, whichever path assembled it.
- Tests: `tests/test_citation_dedupe.py`.
- New-Silicon v0.0.1 rebuilt: 125 definitions became 79 distinct sources, with no duplicates and no missing definitions.

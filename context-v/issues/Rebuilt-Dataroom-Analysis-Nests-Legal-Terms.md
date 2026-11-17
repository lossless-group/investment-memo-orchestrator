---
title: "A Dataroom Analysis Rebuilt From Artifacts Nests the Legal Terms One Level Deep"
lede: "5b-legal-terms.json is written as {documents, reconciled}, but the rebuild reads the whole object into legal_docs, which every consumer expects to be a list. Saving that analysis again nests the file and crashes the legal report."
date_authored_initial_draft: 2026-11-15
date_authored_current_draft: 2026-11-15
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-11-15
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-11-15
date_modified: 2026-11-15
tags: [Dataroom, Reuse, Legal-Extraction, Artifacts]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
status: Resolved
severity: Medium
type: Issues
---

# A Dataroom Analysis Rebuilt From Artifacts Nests the Legal Terms One Level Deep

## What happened

Re-saving a dataroom analysis rebuilt with `_analysis_from_artifacts` (to add a re-extracted cap table) wrote `5b-legal-terms.json` as `{"documents": {"documents": [...], "reconciled": {...}}, "reconciled": ...}`, then crashed in `format_legal_report`:

```
AttributeError: 'str' object has no attribute 'get'
```

## Why

`save_dataroom_analysis_artifacts` writes `5b-legal-terms.json` as `{"documents": legal_docs, "reconciled": legal_summary}`. `_ARTIFACT_KEYS` maps that file straight to `legal_docs`, so the rebuild puts the whole wrapper where a list of per-document records belongs. Any memo run that reuses a rebuilt analysis gets a dict for `legal_docs` and iterates its keys.

## Fix

`_analysis_from_artifacts` unwraps the file: `documents` becomes `legal_docs`, and `reconciled` fills `legal_summary` when `5b-legal-summary.json` is absent.

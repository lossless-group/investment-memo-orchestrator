---
title: "The Cap Table Extractor Crashes When the Model Returns a Null Share Class"
lede: "A shareholder row with share_class or investor_type set to null crashes the whole cap table step, and the dataroom analysis carries on with no cap table at all."
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
tags: [Dataroom, Extraction, Cap-Table, Null-Handling]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
status: Resolved
severity: High
type: Issues
---

# The Cap Table Extractor Crashes When the Model Returns a Null Share Class

## What happened

A dataroom-only run on a second version of a deal's dataroom, which added executed financing documents (subscription agreements, SAFEs, a convertible loan agreement), logged:

```
📊 Extracting cap table data from 5 documents...
   ✗ Error: 'NoneType' object has no attribute 'lower'
```

and wrote no `2-cap-table.json`. The run carried on, so the gap is easy to miss. The first version of the same dataroom extracted 24 shareholders without trouble.

## Why

`_classify_table_type` in `src/agents/dataroom/extractors/cap_table_extractor.py`:

```python
sh.get("share_class", "").lower()
sh.get("investor_type", "").lower()
```

`.get(key, "")` only falls back when the key is absent. The LLM returns the key with a JSON `null` when a document names a holder but not the class, so `.get` returns `None` and `.lower()` raises. The exception is caught a level up in `dataroom_analyzer.py`, which drops the whole cap table.

`synthesizer.py` reads `investor_type` the same way.

## Fix

`(sh.get("share_class") or "").lower()`, and the same for `investor_type`, in both places.

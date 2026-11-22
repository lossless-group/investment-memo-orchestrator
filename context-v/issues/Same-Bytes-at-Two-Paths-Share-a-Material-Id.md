---
title: "Same Bytes at Two Paths Share a Material Id"
lede: "The uploader derives a binary's material_id from its content, so one file stored at two paths in a deal folder gives deal.json two materials with the same id."
date_created: 2026-11-21
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Connector, Upload, Materials]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
---

# Same Bytes at Two Paths Share a Material Id

## What happens

`scripts/upload_firm.py` gives each binary a `material_id` tied to its bytes. When a deal folder holds the same file at two paths (a deck in `inputs/` and again inside a data room copy, say), the deal's `deal.json` gets two material records with one id. Anything that looks a material up by id (`get_artifact` on `material:<id>`, revision `material_ids`, `gather_inputs()`) sees an ambiguous record.

Found 2026-11-21 by the engineer on [[Apply-the-Deal-Folder-Uploader]] (uploader prep). It predates that work.

## Fix

- One material per distinct `sha256` per deal, carrying every local path it was found at (`local_paths: [...]`). The manifest stays keyed by path and points each path at the same `material_id`.
- Test: two paths with the same bytes give one material with both paths, and the manifest has two entries sharing its id.
- Fix before the uploader's `--apply`, or `deal.json` on the server carries the duplicates.

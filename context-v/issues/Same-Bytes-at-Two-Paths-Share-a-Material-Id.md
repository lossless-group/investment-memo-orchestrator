---
title: "Same Bytes at Two Paths Share a Material Id"
lede: "The uploader derives a binary's material_id from its content, so one file stored at two paths in a deal folder gives deal.json two materials with the same id."
date_created: 2026-11-21
date_modified: 2026-11-21
date_resolved: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
at_semantic_version: 0.0.0.1
publish: false
status: Resolved
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

## Resolution

Resolved 2026-11-21 on `connector/uploader-dedupe-materials`, tested as CONN-UPL-04.

- `scripts/upload_firm.py` keeps one material per distinct `sha256` in a deal. The first path found (in sorted order) creates it. Each later path with the same bytes is appended to its `local_paths`, and gets no record, text file or skip of its own. `local_path` stays on the record as the first path.
- The manifest is still keyed by path. Every entry for those bytes carries the material's `material_id`, including entries carried over from an earlier manifest.
- `scripts/check_upload.py` matches manifest entries through `local_paths` (or the old `local_path`), and now also flags a manifest entry whose `material_id` isn't the server material's.
- `scripts/apply_upload.py` doesn't read material records, so it needed no change.

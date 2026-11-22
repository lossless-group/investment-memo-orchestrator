---
title: "Uploaded Binary Materials Have No Text File"
lede: "The uploader records each binary as a ready material but writes no materials/<id>.md, so next_step on an imported deal that isn't finished fails with artifact_not_found when it reaches the materials brief."
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

# Uploaded Binary Materials Have No Text File

## What happens

`scripts/upload_firm.py` (commit `41339e6`) records every binary in a deal folder as a material with status `ready`, but writes no `materials/<material_id>.md`. `gather_inputs()` in `src/connector/flow.py` reads that file for every ready material. On an imported deal that isn't finished, `next_step` reaches `materials.brief`, which reads `materials`, and fails with `artifact_not_found`.

Found 2026-11-21 by the engineer on [[Fix-What-the-First-Partner-Test-Found]], reproduced with a scratch script on the test fixture firm. Finished deals avoid it since that fix, because their brief is written by the uploader instead of handed out.

## Fix

Belongs with [[Apply-the-Deal-Folder-Uploader]], before the uploader is applied:

- A binary uploaded without extracted text is recorded as `queued` (or `skipped` with a reason) so the materials pipeline extracts it on the server, the way `add_materials` does. Or the uploader runs the same extraction locally and writes `materials/<id>.md`.
- `gather_inputs()` treats a ready material with no text file as a notice input ("Material <filename>: no text extracted"), never an error that stops the walk.
- Test: an imported, unfinished deal walks through `materials.brief` without `artifact_not_found`.

## Resolution

Resolved 2026-11-21 on `connector/uploader-prep`, tested as CONN-UPL-03.

- **The uploader extracts the text itself.** `scripts/upload_firm.py` runs each binary through the connector's own reader (`src/connector/materials/extract.py`, the one `add_materials` uses on the server), once per distinct hash, and writes `materials/<material_id>.md`. The material is `ready` with its `chars`. A binary with no text (an image, a scan with no text layer, a format the reader doesn't take) is recorded `skipped` with the reason, plus a `materials.extract` skip with code `material_unreadable`, the same record the server writes for an unreadable upload.
- **Why not `queued`.** Nothing on the server picks a `queued` material up for extraction: jobs exist only in the process that took the upload. The sweep in `src/connector/materials/pipeline.py` would mark every such material `skipped` ("MemoPop restarted while this was being read") at the next start, or lazily 30 minutes after `added_at` on the first `next_step`. Recording them `queued` would have turned every binary into a skip.
- **`gather_inputs()` no longer stops on a missing text file.** In `src/connector/flow.py`, a ready material whose `materials/<id>.md` is missing becomes a notice input ("Material <path>: no text was extracted from it…"), so a deal staged by the old uploader still walks.
- For a finished deal, those extraction skips are marked as already reported, so the partner isn't told about a logo that has no text.

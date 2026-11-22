---
title: "Uploaded Binary Materials Have No Text File"
lede: "The uploader records each binary as a ready material but writes no materials/<id>.md, so next_step on an imported deal that isn't finished fails with artifact_not_found when it reaches the materials brief."
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

# Uploaded Binary Materials Have No Text File

## What happens

`scripts/upload_firm.py` (commit `41339e6`) records every binary in a deal folder as a material with status `ready`, but writes no `materials/<material_id>.md`. `gather_inputs()` in `src/connector/flow.py` reads that file for every ready material. On an imported deal that isn't finished, `next_step` reaches `materials.brief`, which reads `materials`, and fails with `artifact_not_found`.

Found 2026-11-21 by the engineer on [[Fix-What-the-First-Partner-Test-Found]], reproduced with a scratch script on the test fixture firm. Finished deals avoid it since that fix, because their brief is written by the uploader instead of handed out.

## Fix

Belongs with [[Apply-the-Deal-Folder-Uploader]], before the uploader is applied:

- A binary uploaded without extracted text is recorded as `queued` (or `skipped` with a reason) so the materials pipeline extracts it on the server, the way `add_materials` does. Or the uploader runs the same extraction locally and writes `materials/<id>.md`.
- `gather_inputs()` treats a ready material with no text file as a notice input ("Material <filename>: no text extracted"), never an error that stops the walk.
- Test: an imported, unfinished deal walks through `materials.brief` without `artifact_not_found`.

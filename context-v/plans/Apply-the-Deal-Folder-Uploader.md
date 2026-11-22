---
type: Plans
title: "Apply the Deal-Folder Uploader"
lede: "The uploader is written and tested but hasn't run against the server. Run it on the first firm, fold the 901 imported bucket keys into content-addressed blobs, and check that every deal on the server matches the local folder."
publish: true
date_created: 2026-11-21
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5
at_semantic_version: 0.0.0.1
status: In-Progress
spec_reference: context-v/specs/Upload-Deal-Folders-With-a-Binaries-Manifest.md
issue_reference: context-v/issues/First-Partner-Test-of-the-Connector-from-Claude.md
depends_on: []
tags: [Plan, Connector, Upload, Bucket, Materials, Sync]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/uploader-prep
owns_test_ids: [CONN-UPL-01, CONN-UPL-02]
---

# Apply the Deal-Folder Uploader

## Where it stands

Commit `41339e6` (2026-11-20) turned `scripts/import_firm.py` into `scripts/upload_firm.py` plus `scripts/apply_upload.py`, with tests in `tests/test_upload_firm.py`. It stages a firm, puts each binary in the bucket once as `blobs/<sha256>`, records materials and a `binaries-on-server.yaml` per deal folder, and makes the newest finished memo compiled version 1.

None of it has been applied to the server yet. The server still holds the lossy 2026-10-15 import: no compiled memos, sections missing on several deals, nothing after 2026-10-15, and 901 `imported/…` keys that no deal records.

Every step that writes to the server waits for Michael's go-ahead. The uploader backs the firm up first. Still, say what will change before running `--apply`.

## Steps

### 0. Give uploaded binaries their text

- [ ] Fix [[Uploaded-Binary-Materials-Have-No-Text-File]] first: binaries recorded as `ready` with no `materials/<id>.md` break `next_step` on unfinished imported deals.

### 1. Fold the 901 imported keys into blobs, server-side

So the first upload doesn't send the same bytes again. Per the spec's "The 901 keys already imported":

- [ ] A server-side script (beside `apply_upload.py`) hashes every `imported/…` object in place, copies each distinct hash to `blobs/<hash>` once, and writes a hash list.
- [ ] The uploader takes that list (`--known-blobs <file>`) and treats those hashes as already uploaded.
- [ ] Test: a staged upload with a known-blobs list stages no blob that's on it.
- [ ] Don't delete the `imported/…` keys yet (step 5).

### 2. Stage and read the report

- [ ] `uv run python scripts/upload_firm.py io/<firm> --firm <firm-slug> --out <scratch>/upload`
- [ ] Read `report.md`: for each deal, the version picked, sections matched (all of the outline's keys?), compiled v1 label, binaries new vs. known, and what `next_step` would ask for.
- [ ] Any deal with unmatched sections: fix the matching rule or the local filenames before going on. Three deals had zero sections after the October import.
- [ ] Check the outline the server will run is the firm's current local outline (it drifted after October).

### 3. Apply

- [ ] Get the go-ahead, with the report's summary.
- [ ] `--apply`. Confirm the backup, the history change, and that the manifests were copied into the local deal folders.
- [ ] Commit the manifests in the firm's private repo (its own changelog, not this one).

### 4. Check every deal against its local folder

- [ ] A check script compares, per deal: compiled version label against the newest local `7-`/`6-` memo, section count against the outline, materials against the manifest entries.
- [ ] `list_deals` from Claude: each finished deal reads as compiled, at its local version.
- [ ] Re-run the uploader unchanged: nothing staged.

### 5. Remove the old imported keys

- [ ] Only after step 4 passes, with its own go-ahead: delete `imported/…`.

### 6. The two tests from Claude that the issue queued

- [ ] Compile a deal that's ready. Check the HTML and PDF exports and the bucket keys. (Writes files: go-ahead first.)
- [ ] One research step end to end: web research, the partner approves, `submit_artifact`. Checks the write path and the citation checks.

## Not in this plan

Two-way sync (server edits flowing back to `io/<firm>`). The spec leaves it to the next spec. Until then, treat the server as the copy partners edit, and don't re-run the uploader over a deal a partner has changed on the server without diffing first.

## Done when

The spec's "Done when", plus: every finished local memo is the latest compiled version on the server, and the two Claude tests pass.

## Related

- [[Upload-Deal-Folders-With-a-Binaries-Manifest]]
- [[Fix-What-the-First-Partner-Test-Found]], item 5
- [[Serve-Compiled-Memos-to-Firm-Sites]]: needs compiled versions on the server

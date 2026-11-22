---
title: "Upload Leaves macOS Files and an Empty History Entry"
lede: "Applying a staged upload from a Mac unpacks a `._` metadata file beside every real file in the firm's workspace, and the upload's history entry ends up nearly empty, leaving thousands of changed files unrecorded."
date_created: 2026-11-22
date_modified: 2026-11-22
date_authored_initial_draft: 2026-11-22
date_authored_current_draft: 2026-11-22
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Connector, Upload, History, jj]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
---

# Upload Leaves macOS Files and an Empty History Entry

## What happens

Found 2026-11-22 while preparing a second `--apply` for one firm. The first apply ran 2026-11-21. In the firm's workspace on the server, `jj diff --summary -r @` showed 5,657 files changed but not recorded, more than 0.69M lines. Two causes:

1. **macOS metadata files.** `scripts/upload_firm.py` sends the staged folder with `tar -cf - -C <out> .`. On macOS, `tar` writes an AppleDouble `._<name>` entry beside every file that has extended attributes, unless `COPYFILE_DISABLE=1` is set. The server unpacked 3,090 of them into deal folders, e.g. `deals/<deal>/sections/._04-team.md` and `deals/<deal>/research/._sources.md`. Nothing has misread them yet (the site endpoint serves the right memos), but any code that globs `sections/*.md` or `research/*.md` can pick them up.
2. **The upload's history entry is nearly empty.** `apply_upload.py` writes every deal, then calls `ws.history.record("upload: …", touched)`, which runs `jj commit` on those paths. The entry exists in `jj log`, but the deal changes stayed in the working copy until a later jj command recorded them: new `local/` folders, material records in `deal.json`, renamed `imported/` keys, sections, research and compiled memos. `JjHistory._run` has a 60 s timeout, and `record` logs a `HistoryError` rather than raising it. A commit this large probably timed out.

The files on disk are correct, and so is the bucket. Binaries are stored once as `blobs/<sha256>` and referenced from material records, so they're unaffected. The damage is a gap in the workspace history: older versions of those deals' text, and what one upload changed, can't be read back reliably.

## Fix

1. **Pack without metadata.** Set `COPYFILE_DISABLE=1` for the `tar` in `upload_firm.py`, and pass `--exclude='._*'` and `--exclude=.DS_Store`. Test: a staged folder containing a `._x` file sends nothing by that name.
2. **Refuse them on the server.** `apply_upload.py` skips or deletes any `._*` and `.DS_Store` under the staged folder before copying, and reports how many.
3. **Record history that holds.** An upload's commit must contain the paths it touched, or the apply fails loudly:
   - give `record` a longer timeout for uploads, or commit deal by deal;
   - after recording, check that `jj diff -r @` is empty for the touched paths;
   - surface a `HistoryError` from `apply_upload` instead of only logging it.
4. **Clean up the existing workspace,** once, with the operator's go-ahead and a backup first: delete the `._*` files, then record the rest as one entry, "upload 2026-11-21 (recorded late)".

Related: [[Apply-the-Deal-Folder-Uploader]].

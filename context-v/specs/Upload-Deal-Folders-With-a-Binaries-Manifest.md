---
title: "Upload Deal Folders, with a Binaries Manifest"
lede: "The uploader sends a firm's whole local deal folder to the hosted connector: text into the firm's workspace, binaries into its bucket exactly once, each binary recorded in a manifest in the deal folder and as a material on the server."
date_created: 2026-11-20
date_modified: 2026-11-20
date_authored_initial_draft: 2026-11-20
date_authored_current_draft: 2026-11-20
at_semantic_version: 0.0.0.1
publish: false
status: Draft
tags: [Connector, Import, Upload, Bucket, Materials, Sync]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
site_uuid: 2403dabd-9a95-409b-966e-1d0ea995802a
hex_code: 1autan
---

# Upload Deal Folders, with a Binaries Manifest

## Why

`scripts/import_firm.py` made a lossy, one-time copy (see [[First-Partner-Test-of-the-Connector-from-Claude]]). For binaries it did two things wrong:

- **It copied them by path, once per version.** Keys look like `imported/<deal>/<version>/inputs/<file>`, so the same deck or data room file is stored again under every version. The first firm's bucket holds 901 imported keys, 226 of them for one deal.
- **It never recorded them.** The deal's `deal.json` doesn't list them, so no step can find them, and nothing tells a later run what is already uploaded.

The importer becomes an **uploader** that can run again and again: text kept in step, binaries uploaded once.

## Where a binary lives and how it's reached

- **Bucket key: by content, per firm.** `blobs/<sha256>` in the firm's bucket. The same bytes are one object, however many versions or deals use them. A changed file is a new hash and a new object, and the old one stays for history.
- **Reaching it:** the connector already signs links. `signed_url(ws, key)` in `compile/links.py` returns an S3 presigned URL (or the connector's own `/v1/files/<firm>/<key>?expires=…&signature=…` route for a local bucket), valid for 7 days. Nobody gets a bucket key alone.
- **On the server, every binary is a material** in `deal.json`, the same record `add_materials` already writes for a partner's upload (`bucket_key`, `filename`, `bytes`, `kind`, status `ready`, plus extracted text where there is any). The uploader adds `sha256` and the local path it came from. Steps then see these files the way they see anything a partner adds.

## The manifest in the deal folder: `binaries-on-server.yaml`

One file per deal folder, written by the uploader, committed with the deal:

```yaml
firm: <firm>
deal: <deal>            # the server's name, same as memopop_deal in the deal config
files:
  inputs/2026-05-19_Company-Deck.pdf:
    sha256: 3f1c…e9
    bytes: 8412233
    kind: deck            # deck | dataroom | financials | export | image | other
    bucket_key: blobs/3f1c…e9
    material_id: mat_…
    uploaded_at: 2026-11-21T10:02:11Z
  inputs/Dataroom-2026-11-08/Legal/Cap-Table.pdf:
    sha256: 9a07…41
    bytes: 233104
    kind: dataroom
    bucket_key: blobs/9a07…41
    material_id: mat_…
    uploaded_at: 2026-11-21T10:02:15Z
```

Keyed by the path inside the deal folder. Plain YAML, written by a YAML library, never by hand.

## What the uploader does with each binary

| Local file vs manifest | Action |
|---|---|
| In the manifest, same `sha256` | Skip. Nothing is uploaded. |
| In the manifest, different `sha256` (the file changed) | Upload the new bytes to `blobs/<new hash>` unless that key already exists, point the entry at it, and update the material. |
| Not in the manifest, and `blobs/<hash>` already exists (another path or deal has the same bytes) | Record it, with no upload. |
| Not in the manifest, new bytes | Upload, record in the manifest and as a material. |
| In the manifest, gone locally | Leave the object and the material. Mark the entry `local_missing: true`. Deleting is a separate, deliberate act. |

The hash, not the path or the date, decides. That's what keeps a re-run from copying anything twice.

**Binaries** are anything that isn't text by the connector's `TEXT_EXTENSIONS`: PDFs, decks, spreadsheets, images, video, zips. Data rooms should be slimmed first (`slim-file-sizes` skill).

## Text

Everything else in the deal folder is text: the config, research for every version, sections, finished memos, data room analysis, due-diligence notes, `Sources.md`. It goes into the firm's workspace, which jj versions. The latest finished memo becomes compiled version 1, so a site can show it at once. Keeping text in step in both directions is the next spec, not this one.

## The firm's own files

Deals aren't the only content. The firm folder's configuration is uploaded and kept in step the same way, and it matters most:

- `configs/` (brand config and any others)
- `templates/outlines/` (the deal outlines)
- `templates/scorecards/`
- other firm-level text, such as fund notes

Text goes to the same paths in the firm's workspace, and binaries (fonts, logos) go through the manifest like any other binary, with one `binaries-on-server.yaml` at the firm root.

**Outlines will drift first.** Checked 2026-11-20 on the first firm: the brand config and scorecard matched the server, but the main outline had been changed locally after the import, so the server was running the older one. The server also had an outline the local folder doesn't, from the shared templates.

**Partners will edit outlines.** As more partners use the connector, they'll want to add their own insights to an outline: a question to always ask, a source to prefer, a section to reorder. The connector has no tool for that today. That needs:

- a tool to read a firm's outline and one to change it (an `edit_outline` beside Plan 9's `edit_section`), recorded in the firm's history like any other save
- the change reaching the local folder, which makes outlines the first thing the two-way sync must cover
- a decision on whether an outline change applies to deals already under way or only to new ones

## The 901 keys already imported

Don't upload them again. A one-time server-side pass:

1. Hash every `imported/…` object in place, on the server.
2. Copy each distinct hash to `blobs/<hash>` once.
3. Write the materials and return the hash list, so the uploader can fill each local manifest without uploading anything.
4. Remove the old `imported/…` keys only after the manifests and materials check out. This is a separate step with its own go-ahead.

## Done when

- Running the uploader twice on an unchanged deal uploads nothing the second time.
- Every binary in a deal folder has exactly one manifest entry, one bucket object and one material.
- A step for an imported deal lists its deck and data room as inputs.

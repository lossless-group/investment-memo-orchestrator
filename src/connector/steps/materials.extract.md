---
id: materials.extract
title: Extract text from materials
phase: materials
scope: deal
required: true
runs_on: server
needs_partner: false
order: 10
version: "1"
reads: ["materials:*"]
produces:
  kind: material
  checks:
    not_empty: true
    max_chars: 400000
path: "materials/{section}.md"
source_agent: src/agents/dataroom
enabled: true
---
# Extract text from materials

Runs on the server, in the background, for every material `add_materials`
receives (`src/connector/materials/pipeline.py`). Claude never receives this
step.

- **Links** are fetched (Google Drive and Dropbox share links rewritten to
  direct downloads; DocSend refused for v1), with timeouts, a 100 MB cap, and
  no private addresses.
- **Uploads** arrive through the one-time page at `/upload/{token}`.
- **Originals** go to the firm's bucket under `materials/<material_id>/`.
- **Text** is extracted through `src/agents/dataroom/document_text.py`
  (PyMuPDF for PDFs, with its OCR fallback for scans; Word, Excel, CSV,
  PowerPoint, markdown, and plain text) or, for a web page, BeautifulSoup, and
  saved to `deals/<deal>/materials/<material_id>.md`, cut at 400,000 characters.
- **Inline text** is saved as given, at once.

A material that can't be fetched or read becomes a `material_unreadable` skip
on the deal and the memo continues. It is listed so the registry, the docs, and
`compile`'s report can name it; it is never handed out by `next_step`, and
nothing is submitted for it with `submit_artifact`.

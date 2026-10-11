---
type: Plans
title: "MemoPop Connector API, Phase 4: Materials"
lede: "Decks, datarooms, notes, and links reach the server three ways, become text the steps can read, and never block the memo."
publish: true
date_created: 2026-10-10
date_modified: 2026-10-10
date_authored_initial_draft: 2026-10-10
date_authored_current_draft: 2026-10-10
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5 (1M context)
at_semantic_version: 0.0.0.1
status: In Progress
spec_reference: context-v/specs/MemoPop-Connector-API.md
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/plan-4-materials
depends_on: [Phase-1-Foundation]
owns_test_ids: [CONN-MAT-01, CONN-MAT-02, CONN-MAT-03, CONN-MAT-04, CONN-MAT-05, CONN-MAT-06, CONN-MAT-07]
site_uuid: 346a86f3-5ea9-4fea-8313-fdfef31c8d8b
hex_code: gwjpoy
tags:
  - Plan
  - MemoPop
  - Claude-Connector
  - TDD
---

# MemoPop Connector API, Phase 4: Materials

Read the spec (`context-v/specs/MemoPop-Connector-API.md`, §The tools →
`add_materials`, §Storage, §Tests → Materials) and the loop doc first. Phase 1
is merged into `development`; build on its registry, workspace, bucket, and
error catalogue. Runs in parallel with phases 5 and 6: stay inside your files.

## Your files

`src/connector/tools/add_materials.py`, `src/connector/materials/` (fetch,
extract, upload page), the `materials.extract` server step and the
`materials.brief` instruction file, `tests/connector/test_materials*.py`, and
small fixtures (a two-page synthetic PDF; generate it, don't copy a real deck).
Touch shared registry files only to register your items.

## Steps

1. **Failing tests** for the seven owned IDs; ledger shows them RED.
2. **`add_materials`** per the spec: inline text (100,000-character cap →
   `material_too_large`), links, and filename-only items that get a one-time
   upload URL. Returns at once; extraction runs in a background task.
3. **Link fetching** with `httpx`, timeouts, and a size cap. An unreachable or
   unreadable link records a skip (`material_unreadable`) on the deal; it never
   blocks. Google Drive and Dropbox share links: rewrite to their direct
   download form. DocSend is out of scope for v1; record it as unreadable with
   a message saying so.
4. **The upload page**: `GET /upload/{token}` serves a minimal HTML form;
   `POST` accepts the file. Tokens are random, single-use, and expire after an
   hour. No auth beyond the token.
5. **Extraction**: reuse what exists rather than rewrite it. PDF text through
   the orchestrator's PyMuPDF path (`src/agents/dataroom/document_text.py` has
   the OCR fallback); `.docx`, `.xlsx`, `.csv`, `.md`, `.txt` as plain text.
   Originals go to the firm's bucket under `materials/`; extracted text to
   `deals/<deal>/materials/<id>.md`.
6. **`materials.brief`**: a Claude step offered after materials are ready and
   before research; instruction adapted from `src/agents/deck_analyst.py`'s
   prompt, with model calls removed.
7. **Docs** for `add_materials` complete, with examples that execute.

## Rules and done

As in Phase 1: never edit a test to pass, no model calls, `uv add` only, no
`io/`. Done when `scripts/check.sh` passes, the owned IDs are GREEN, the
existing and Phase 1 tests still pass, a changelog entry is written, and the
branch is pushed. Report the ledger output and suite counts.

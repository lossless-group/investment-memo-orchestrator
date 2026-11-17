---
title: "Deals With Successive Datarooms Have No First-Class Support"
lede: "A deal config takes one dataroom path. When a company sends a second version, the earlier one, and what changed between them, are invisible to the pipeline. Separately, dataroom-only runs written outside outputs/ are never reused."
date_authored_initial_draft: 2026-11-16
date_authored_current_draft: 2026-11-16
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-11-16
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-11-16
date_modified: 2026-11-16
tags: [Dataroom, Versioning, Reuse, Diligence]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
status: Open
---

# Deals With Successive Datarooms Have No First-Class Support

## What happens

1. **One path only.** `src/main.py` reads `company_data.get("dataroom")` as a single string. A deal whose company answered diligence with a revised dataroom has two versions. The pipeline sees only the one the config points at.
2. **What changed is the signal, and it is lost.** Between versions a company may drop, replace or re-represent documents. The first case was revised patent counts and four licensed patents removed. Nothing in the pipeline compares versions, so the memo cannot say what changed.
3. **Reuse misses analyses stored outside `outputs/`.** `_reusable_dataroom_analysis()` searches only `outputs/<deal>-*` siblings. An analysis written anywhere else is re-extracted from scratch, which takes about 45 minutes for 150 documents. `run_dataroom.py` writes to `outputs/<deal>-dataroom-<date>/`, which is found. A hand-run analysis under `dataroom-analysis/` is not.

## Workaround used on the first case

- Point `dataroom` at the latest version, and record the earlier one under a `prior_datarooms` list (path, date received, diff report, analysis).
- Copy the latest analysis into `outputs/<deal>-dataroom-<date>/` so reuse finds it.
- Add the superseded documents that carry the change (here, the old IP schedule and summary) to `inputs/Sources.md`, titled `SUPERSEDED`. State the change as a fact in the deal notes.

## Proposed shape

- `dataroom` may be a list of `{path, received}`. The latest is primary; earlier ones are diffed by content hash, not path, because renames and asset normalization both change paths or bytes without changing content.
- A diff node emits `0-dataroom-changes.json`: added, removed, replaced and renamed files, with document types. The writer gets the removed and replaced documents as facts. Any questions raised go to the due diligence questionnaire (see `Consider-Mode-Has-No-Due-Diligence-Questionnaire.md`), not the memo.
- Reuse also checks a declared analysis path, or the `analysis` entry of each dataroom.

The hash diff must use each file's normalized original when one exists (`_zip-originals/oversized/`). Otherwise compressed files read as changed.

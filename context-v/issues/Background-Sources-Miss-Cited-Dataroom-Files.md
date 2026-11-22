---
title: "Background Sources Miss Cited Data-Room Files"
lede: "Assembly decides which sources are cited only by their web links, so a data-room file that claims do cite (a cap table, a board consent) is still listed under Background Sources as if nothing cited it."
date_created: 2026-11-22
date_modified: 2026-11-22
date_authored_initial_draft: 2026-11-22
date_authored_current_draft: 2026-11-22
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Citations, Assembly, Materials]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
---

# Background Sources Miss Cited Data-Room Files

## What happens

Final assembly appends a "Background Sources" list of sources the research gathered but no claim cites. To decide what's cited, it compares http(s) links only. A footnote whose definition links a data-room file (`file://…` or a material path) is never matched, so the file shows up under Background Sources even when claims cite it.

Found 2026-11-22 while checking that a hand-fixed memo re-assembles from its section files. Three data-room files cited in the Fundraising section (cap table, board consent, cap-table overview) were listed as uncited after assembly.

## Fix

Match cited sources by `source_identity()` from `src/citation_keys.py` (the same identity hex keys are built from), which already covers `file://` links, rather than by http URL. Test: a definition linking a `file://` path that a section cites never appears in Background Sources.

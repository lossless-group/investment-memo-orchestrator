---
title: "A Stale Enhancement Outranked a Newer Draft"
lede: "A section's current text was picked by step order, not save order, so an old citations pass would have won over a freshly revised draft."
publish: false
date_created: 2026-10-15
date_modified: 2026-10-15
date_authored_initial_draft: 2026-10-15
date_authored_current_draft: 2026-10-15
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5 (1M context)
at_semantic_version: 0.0.1.0
status: Resolved
site_uuid: 19adb553-32be-4df5-abff-d292472cd895
hex_code: jxrj6s
summary: >-
  flow.current_section_key returned the last section-kind artifact in registry
  order (draft, tables, citations, fact check). That was safe while a deal only
  moved forward. Once a draft can be redone after its enhancements, the old
  enhancement still ranked higher and compile would have used the old text.
  Found while designing revisions, before any deal hit it.
tags:
  - Issue-Resolution
  - MemoPop
  - Claude-Connector
  - Compile
---

# A Stale Enhancement Outranked a Newer Draft

## What happened

`current_section_key` decides which artifact is a section's text for the next
step's inputs and for compile. It walked the section-kind steps in registry
order and kept the last one present. In a forward-only walk the last in order
is also the last saved, so this held.

A revision breaks that: redo `draft.section:02-market`, then skip
`enhance.citations` for it, and the *old* `enhance.citations:02-market` (the
pre-revision draft with citations) still ranks above the new draft. Compile
would have published the old section.

## Resolution

Every artifact save now carries `seq`, a per-deal counter, and the current
text is the one with the highest `seq` (registry order breaks ties, so records
from before `seq` existed behave as before). `cancel_revision` restores each
record's old `seq`, so the pre-revision current text is current again. Commit
`ae903bb`.

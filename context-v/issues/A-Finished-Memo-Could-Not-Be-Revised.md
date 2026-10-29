---
title: "A Finished Memo Could Not Be Revised"
lede: "The hosted connector only moved forward. Once a section was drafted, no tool could reopen it, so a colleague holding the latest PDF couldn't add new research or a new angle."
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
site_uuid: cc972b53-137f-4908-a911-21992a1cd20b
hex_code: 2wtsr0
summary: >-
  submit_artifact refused any step next_step hadn't handed out, and next_step
  never handed out a step that was already done, so a drafted section was
  final. Found while importing a client firm's local memos to memopop.didi.sh,
  where the point of hosting them was that colleagues could iterate. Resolved by
  plan 8: start_revision and cancel_revision.
tags:
  - Issue-Resolution
  - MemoPop
  - Claude-Connector
  - Revisions
type: Issues
---

# A Finished Memo Could Not Be Revised

## What happened

After importing a firm's deals to the hosted connector, a test edit of a done
section came back:

```
step_out_of_order: 'draft.section:01-overview' has not been handed out by next_step.
```

The walk (`flow.walk`) hands out the first step that isn't done, and a done
step is never done again. Nothing let a client reopen one. A colleague could
read, continue, and compile a memo, but not say *"we have new market research;
can it go in?"*

## Why it matters

Hosting the memos was meant to fix exactly this: drafts lived on one laptop,
and nobody else could iterate on a good one.

## Resolution

Plan 8 ([[MemoPop-Connector-API]] §Revisions): `start_revision` reopens
sections with the partner's angle and new materials; `next_step` walks only the
reopened steps; `compile` closes the revision and labels the next version;
`cancel_revision` restores the earlier text. Tests CONN-REV-01 to 10. Commit
`ae903bb`.

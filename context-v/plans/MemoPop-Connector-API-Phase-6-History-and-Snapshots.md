---
type: Plans
title: "MemoPop Connector API, Phase 6: History and Snapshots"
lede: "Every saved artifact becomes a jj change the client never sees, and one save backs the firm's whole workspace up to its bucket."
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
status: Blocked-On-Phase-1
spec_reference: context-v/specs/MemoPop-Connector-API.md
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/plan-6-history-snapshots
depends_on: [Phase-1-Foundation]
owns_test_ids: [CONN-HIST-01, CONN-HIST-02, CONN-HIST-03, CONN-HIST-04, CONN-HIST-05]
site_uuid: 57368519-d8ed-4485-9db7-70cb42e1aaa0
hex_code: q8vti7
tags:
  - Plan
  - MemoPop
  - Claude-Connector
  - Jujutsu
  - TDD
---

# MemoPop Connector API, Phase 6: History and Snapshots

Read the spec (§Storage, §The tools → `save_snapshot`, §Defaults chosen for
v1, §Tests → History) and the decision
[[jj-Versions-Text-and-Saves-Snapshot-to-the-Bucket]] (in
`memopop-ai/context-v/decisions/`). Phase 1 is merged into `development` and
left a no-op `History` hook in `src/connector/workspace.py`. Runs in parallel
with phases 4 and 5.

## Your files

`src/connector/history.py`, `src/connector/tools/save_snapshot.py`,
`tests/connector/test_history*.py`, `test_snapshot*.py`. Edit
`workspace.py` only to wire the hook.

## Steps

1. **Failing tests** for the five owned IDs. Tests need the `jj` binary; skip
   with a clear reason when it's absent locally, but CI installs it, so in CI
   they must run.
2. **One jj repository per firm**, initialised on first write
   (`jj git init` in the firm root, with a `.gitignore` excluding any binary
   material paths). After each saved artifact, record exactly one change with
   a description naming step, deal, and section; identical content records
   nothing. Run jj as a subprocess with a fixed author
   (`MemoPop <noreply@didi.sh>`) and `JJ_CONFIG` pointing at a file you write,
   so the server user's config never leaks in.
3. **`save_snapshot`**: a `.tar.gz` of the firm's workspace (including `.jj`)
   written to the firm's bucket under `snapshots/<timestamp>-<label>.tar.gz`,
   with change counts against the previous snapshot from a small manifest kept
   beside it. Return the fields in the spec.
4. **Isolation** (`CONN-HIST-04`): two firms, separate repositories and bucket
   locations, and no path in either reachable from the other's workspace.
5. **Docs** for `save_snapshot` complete, with executing examples.

## Rules and done

As in Phase 1. Done when `scripts/check.sh` passes, the owned IDs are GREEN,
everything previously green still is, a changelog entry is written, and the
branch is pushed.

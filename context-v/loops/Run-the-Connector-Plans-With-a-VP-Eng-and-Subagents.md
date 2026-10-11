---
type: Loops
title: "Run the Connector Plans with a VP Eng and Subagents"
lede: "One VP Eng holds the spec and the ledger; engineer subagents each take a plan from failing tests to green, changelog, and push."
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
status: Active
spec_reference: context-v/specs/MemoPop-Connector-API.md
site_uuid: f9e07df7-c3ae-441c-8632-ace9aea3f8a8
hex_code: ye4xo0
tags:
  - Loop
  - MemoPop
  - Claude-Connector
  - TDD
  - Subagents
---

# Run the Connector Plans with a VP Eng and Subagents

> `context-v/loops/` is an experimental folder. This loop adopts
> corpora-builder's [[Spec-to-Shipped-With-TDD]] almost whole: test IDs in the
> spec, failing tests first, status derived by the ledger, never written. What
> it adds is a **VP Eng** who farms plans to engineer subagents and verifies
> their work independently before anything counts as done.

## Roles

```
┌─ VP ENG (the main session) ──────────────────────────────────────────┐
│ OWNS     the spec, the plans, the gh issues, merges into development, │
│          this loop's log, and the operator's attention                │
│ DOES     reviews each plan before handing it out; re-runs the ladder  │
│          and the ledger itself after every engineer reports; reads    │
│          every changelog; asks the operator at RED gates              │
│ NEVER    takes an engineer's "it's green" on trust                    │
└──────────────────────────────────────────────────────────────────────┘
                 ⇅  one plan per engineer, one branch per plan
┌─ LEAD ENGINEER (a subagent) ─────────────────────────────────────────┐
│ WRITES   src/connector/, tests/connector/, scripts/, CI, its plan's   │
│          status, its changelog entry                                  │
│ NEVER    edits a test to make it pass · changes the spec's intent ·   │
│          deploys or spends money · pushes to main or master ·         │
│          touches io/                                                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Per plan

1. **VP Eng reviews the plan** against the live code and the spec. Anything the
   plan got wrong is fixed in the plan before it's handed out.
2. **VP Eng opens the gh issue** for the plan, linking the plan file.
3. **Engineer writes the failing tests first**, one per owned ID, each marked
   `@pytest.mark.spec("CONN-…")`. The ledger must show every owned ID RED or
   MISSING-free before implementation starts (the TDD floor).
4. **Engineer implements** in small steps, climbing the ladder
   (`scripts/check.sh`) after each.
5. **Iterate until green.** If a test can't go green against honest code, the
   spec is wrong: the engineer stops and reports it, and the VP Eng amends the
   spec with the operator. The test is never edited to fit.
6. **Engineer writes the changelog entry**, commits, and pushes its branch.
   The entry says plainly what was *not* tested and why.
7. **VP Eng verifies**: merges into `development`, re-runs the full ladder and
   the ledger, reads the changelog against what the code does, and closes the
   gh issue with `Fixes #N`.

## Branches

Each plan runs on `connector/plan-N-<name>`, cut from `development` after the
plans it depends on have merged. Plans 4, 5, and 6 run in parallel in separate
worktrees. Only the VP Eng merges into `development`. `main` is promoted once,
when the spec is done, with the operator's yes.

## Gates the VP Eng takes to the operator

- A test that can't go green honestly (the spec is wrong).
- Anything outward-facing or that costs money: the Railway deploy, DNS for
  `memopop.didi.sh`, deploying id.didi.sh.
- Promoting to `main`.

Everything else runs without asking.

## Done

The ledger reports every `CONN-` ID GREEN except those that need a live
service or credentials (GATED), each of which the VP Eng has run by hand and
recorded in the log below; every plan's gh issue is closed; the operator has
walked the connector in Claude Desktop.

## Log

One entry per plan as it lands: the ledger result, what the VP Eng's own run
found, and anything decided that the plan didn't cover.

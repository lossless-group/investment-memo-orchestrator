---
type: Plans
title: "MemoPop Connector API, Phase 5: Enhancements, Compile, and the Full Flow"
lede: "Every enhancement becomes a step that can skip, compile turns sections into a branded PDF, and a scripted client walks the whole memo."
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
branch: connector/plan-5-enhancements-compile
depends_on: [Phase-1-Foundation]
owns_test_ids: [CONN-ENH-01, CONN-ENH-02, CONN-ENH-03, CONN-CMP-01, CONN-CMP-02, CONN-CMP-03, CONN-CMP-04, CONN-FLOW-01, CONN-FLOW-02]
site_uuid: a3cb4529-95f4-49d2-bf2f-bafe72410b71
hex_code: dd1tmo
tags:
  - Plan
  - MemoPop
  - Claude-Connector
  - TDD
---

# MemoPop Connector API, Phase 5: Enhancements, Compile, and the Full Flow

Read the spec (§The step registry, §First mapping, §Deal state, §The tools →
`compile`, §Errors on `skipped`, §Tests → Enhancements) and the loop doc.
Phase 1 is merged into `development`. Runs in parallel with phases 4 and 6.

## Your files

`src/connector/tools/compile.py`, `src/connector/compile/`, the enhancement
and `compile.assemble` steps and their instruction files,
`tests/connector/test_enhancements*.py`, `test_compile*.py`, `test_flow*.py`.

## Steps

1. **Failing tests** for the nine owned IDs. `CONN-ENH-02` is parametrized over
   every optional step.
2. **Enhancement instructions**: one file per enhancement step in the spec's
   mapping, adapted from its source agent's prompt with every model and API
   call removed, ending with how to submit. Each declares what it reads (the
   saved sections) and produces, with checks.
3. **Skips end to end**: a disabled step (`enabled: false`, settable by env
   `MEMOPOP_DISABLED_STEPS`) and an optional server step that raises both
   record a skip on the deal and the flow continues. `next_step` reports
   `skipped_since_last_call`; `list_deals` shows skips.
4. **`compile`**: assemble the sections in outline order, then the server
   steps from §First mapping (citation consolidation and renumbering, spacing,
   table of contents, deck images if any, finalize). **Reuse the existing
   functions** in `src/agents/citation_assembly.py`, `citation_spacing.py`,
   `toc_generator.py` and the export code in `cli/export_branded.py`; call
   their pure parts, and where one is tangled with `MemoState` or `Path("io")`,
   extract a pure function beside it rather than duplicating it. HTML and PDF
   (WeasyPrint) go to the firm's bucket under `compiled/`; return signed links
   that expire after seven days. Past a time budget (default 200 s, env
   overridable for tests), return a `job_id`.
5. **The scripted client** (`tests/connector/fake_claude.py`): walks
   `fixture-co` from creation to compile using canned artifacts, over MCP
   (`CONN-FLOW-01`) and REST (`CONN-FLOW-02`).
6. **Docs** for `compile` complete, with executing examples.

## Rules and done

As in Phase 1. Done when `scripts/check.sh` passes, the owned IDs are GREEN,
everything previously green still is, a changelog entry is written, and the
branch is pushed. Report the ledger output and suite counts.

---
type: Plans
title: "Edit Tools for Finished Memos"
lede: "Plan 9's routing table needs three tools that don't exist yet (edit_section, edit_final, edit_outline) and a compile that refuses to overwrite untracked edits. Together they let a partner change a finished memo from Claude without losing anything on the next compile."
publish: true
date_created: 2026-11-21
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5
at_semantic_version: 0.0.0.1
status: Ready
spec_reference: context-v/specs/MemoPop-Connector-API.md
depends_on: [Finish-Turning-Agents-into-Connector-Steps, Apply-the-Deal-Folder-Uploader]
tags: [Plan, Connector, Revisions, Plan-9]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
owns_test_ids: [CONN-EDIT-01, CONN-EDIT-02, CONN-EDIT-03, CONN-EDIT-04, CONN-EDIT-05, CONN-EDIT-06]
---

# Edit Tools for Finished Memos

The connector's current scope is iterating memos that are already done (spec, "Where an edit goes (Plan 9)"). Of the three routes in its table, only the first works today: `start_revision` with `start: research`. The other two, and outline changes, need new tools.

**Depends on:**
- [[Finish-Turning-Agents-into-Connector-Steps]] step 1, the rewrite step from `section_reviser.py`, so the research route ends in a clean rewrite. The rule: research file and current draft as the only inputs, no outside knowledge.
- [[Apply-the-Deal-Folder-Uploader]], so there are compiled memos on the server to edit.

Each tool goes in `src/connector/tools/`, over MCP and REST, with docs carrying the routing table, and tests in `tests/connector/`.

## 1. `edit_section`

Narrative or clerical changes: wording, tone, order, emphasis, typos, formatting.

- Inputs: `deal`, `section` (key, name or number), and either `text` (the whole new section) or `edits` (old/new pairs that must each match once).
- Saves a new version of the section's current artifact (`current_section_key`). It doesn't reopen research or enhancements, and doesn't open a revision. Several can stack before one compile.
- Refuses while a revision is open on the same section (`revision_open`).
- Tests: an edit makes a new version and leaves research untouched. An `old` string that doesn't match once returns `validation_failed` naming it. Compile after two edits includes both.
- [ ] Done

## 2. Compile refuses to overwrite untracked edits

Must land before `edit_final`, since `edit_final` is the way out of it.

- Before writing a new final draft, `compile` rebuilds the draft the current sections would produce for the *previous* compiled version and compares it with that version's stored final. Differences are text someone changed outside the sections.
- If any: refuse with `final_has_untracked_edits`, listing each difference with its section, and offer `edit_final` to carry it back. A `discard_untracked: true` input drops them, used only when the partner says so.
- Tests: hand-edit a compiled final, then compile: refused, difference listed. With `discard_untracked`: compiles.
- [ ] Done

## 3. `edit_final`

The partner overrides the process: "just edit the memo I'm looking at."

- Inputs: `deal`, `edits` (old/new pairs against the latest compiled final), optional `facts_changed: bool`.
- Applies them to the final so the partner sees them now (a new compiled version, label bumped), then writes the same change into the section each edit falls in, as a new section version, and records the pairing. When `facts_changed`, the response's `next` tells Claude to update the section's research too, through `start_revision`.
- Locates the section by the assembled draft's section boundaries. If an edit spans sections or can't be placed, it refuses and says which edit.
- Tests: an edit to the final shows up in the section, and the next compile reproduces it without `final_has_untracked_edits`.
- [ ] Done

## 4. `get_outline` and `edit_outline`

The decision (spec, 2026-11-20): an outline change made while working on a memo applies to that memo only. Other memos change only when the partner asks, and then one at a time.

- `get_outline(deal?)`: the outline a deal uses, or the firm's outlines.
- `edit_outline(deal, edits)`: copies the firm's outline into the deal as its own pinned outline (unless it already has one), applies the edits there, and records the change in the firm's history. The deal's `template` then points at the pinned copy. A section that's added or whose questions changed shows in `next_step` as needing work.
- An `apply_to: firm` option changes the firm's outline itself and returns the list of deals using it, without changing them. Claude then works through them one at a time with the partner.
- Tests: editing a deal's outline doesn't change another deal using the same outline. A new section appears in `next_step`.
- [ ] Done

## 5. Docs and routing

- [ ] The agent-facing docs for `start_revision`, `edit_section`, `edit_final`, `edit_outline` and `compile` carry the routing table.
- [ ] The step instructions for research and rewrite repeat the two-task rule (research edits are one task, the rewrite from research plus draft is another).
- [ ] Regenerate the docs. Redeploy.

## Done when

A partner in Claude can do each row of Plan 9's table on a finished memo, plus an outline change for one memo, and the next compile keeps every change.

## Related

- [[MemoPop-Connector-API]], Plan 8 and Plan 9
- [[Serve-the-Method-from-the-Server]]: the skills that tell Claude which tool to use
- [[Serve-Compiled-Memos-to-Firm-Sites]]: where partners see the result

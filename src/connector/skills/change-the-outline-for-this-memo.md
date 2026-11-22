---
name: change-the-outline-for-this-memo
description: The partner wants to add, remove, rename, or reorder sections of one memo's outline; the change applies to this memo only.
---
# Change the outline for this memo

A partner who changes the outline while working on a memo expects the change in **that memo only**. Other memos using the same outline stay as they are. If the partner asks for the change in other memos too, work through them one at a time, confirming each, never all at once. Change the firm's own outline only when the partner says so in as many words.

1. Read the outline the memo uses with `get_outline` and the deal.
2. Call `edit_outline` with the deal and `edits`, each with an `op`:
   - `add_section`: `name`, optionally `after` (a section), `description`, `guiding_questions`.
   - `update_section`: `section`, and any of `name`, `description`, `guiding_questions`.
   - `move_section`: `section`, and `after` (leave it out to put the section first).
   - `remove_section`: `section`. Its text stays in history.
   The deal gets its own copy of the outline; no other memo changes.
3. Call `next_step`. An added section, or one whose description or questions changed, is handed out for research (show it to the partner and wait for approval) and then a draft. When `next_step` says done, compile (see `compile-and-check-the-site`).
4. If the partner wants the firm's outline itself changed, call `edit_outline` with `apply_to: firm`. No memo changes; the reply lists the memos on that outline in `deals_using`. Ask the partner which of them should change, then call `edit_outline` for each, one at a time.

Tell the partner in one line what changed, and that it applies to this memo only.

Call next: `edit_outline`, then `next_step`.

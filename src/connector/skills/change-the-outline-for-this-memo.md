---
name: change-the-outline-for-this-memo
description: The partner wants to add, remove, rename, or reorder sections of one memo's outline; the change applies to this memo only.
---
# Change the outline for this memo

A partner who changes the outline while working on a memo expects the change in **that memo only**. Other memos using the same outline stay as they are. If the partner asks for the change in other memos too, work through them one at a time, confirming each, never all at once. Change the firm's own outline only when the partner says so in as many words.

**Needs `edit_outline`, which is not on the server yet.** Once it is: call `edit_outline` with the deal and the change. An added section then appears in `next_step`, which hands out its research and draft like any other section.

**Until then:**

- Adding or removing a section can't be done through the connector yet. Tell the partner so in one line, and offer to fold the new content into an existing section instead.
- Renaming a section, or moving material from one section to another: call `start_revision` with the sections involved, the partner's request as `angle`, and `start: draft` (or `start: research` when the moved material needs new sources). Follow `next_step` until done, then compile.

Tell the partner in one line what changed, and that it applies to this memo only.

Call next: `edit_outline` (not yet available; until it is, `start_revision` for renames and moves).

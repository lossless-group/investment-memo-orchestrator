---
name: just-edit-the-memo
description: The partner says to just edit the memo they're looking at, overriding the usual process; change the final draft and carry the change back to its section.
---
# Just edit the memo

Use this when the partner overrides the process: "just change it in the memo", "don't redo anything, edit what I'm reading". Do what they ask and don't argue about the process.

A change made only in the final draft would be overwritten the next time anything recompiles, so it is always **carried back**: into the section it falls in, and into that section's research too when a fact or source changed.

**Needs `edit_final`, which is not on the server yet.** Once it is: call `edit_final` with the deal and the exact old and new text. It changes the compiled memo now, writes the same change into the section (and research), and records the pairing, so the next compile reproduces it.

**Until then, use the revision path:**

1. Find the deal with `list_deals`. Work out which section the text is in.
2. Wording only: call `start_revision` with that section, the partner's request as `angle`, and `start: draft`. A fact or source changed: use `start: research` and fix the research first (see `fix-a-source-or-citation`).
3. Call `next_step`, apply exactly the change asked for, submit it with `submit_artifact`, and keep calling `next_step` until it says done.
4. Compile, so the partner sees the change in the memo (see `compile-and-check-the-site`).

Tell the partner in one line that the memo is changed and the change will survive the next compile.

Call next: `edit_final` (not yet available; until it is, `start_revision` with `start: draft`, then `compile`).

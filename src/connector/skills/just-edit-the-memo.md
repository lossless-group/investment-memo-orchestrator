---
name: just-edit-the-memo
description: The partner says to just edit the memo they're looking at, overriding the usual process; change the final draft and carry the change back to its section.
---
# Just edit the memo

Use this when the partner overrides the process: "just change it in the memo", "don't redo anything, edit what I'm reading". Do what they ask and don't argue about the process.

A change made only in the final draft would be overwritten the next time anything recompiles, so `edit_final` always **carries it back**: it changes the compiled memo now (a new version, label bumped, fresh links), writes the same change into the section it falls in, and records the pairing, so the next compile reproduces it.

1. Find the deal with `list_deals`. Read the latest compiled memo with `get_artifact` (`compile.assemble`).
2. Call `edit_final` with the deal and `edits`: each `old` copied exactly from the memo, inside one section's text, matching once. Leave citation numbers out of `old`: they are renumbered in the final, so the section has different ones. Set `facts_changed: true` when the change alters a fact or a source.
3. If it returns `edit_not_placed`, `details.reason` says why (it spans two sections, sits outside every section, or the section words it differently). Make the edit smaller, or make it with `edit_section` on that section and then compile.
4. Give the partner the links. With `facts_changed`, follow `next_hint`: `start_revision` with `start: research` on that section, so its research says what the memo now says (see `fix-a-source-or-citation`).

The same tool carries back changes `compile` reports as `final_has_untracked_edits` (someone edited the final outside MemoPop): for each difference the partner wants kept, make the section say what the final says with `edit_section` (or `edit_final`), then compile again. Drop them with `compile` and `discard_untracked: true` only when the partner says so.

Tell the partner in one line that the memo is changed and which section now carries the change.

Call next: `edit_final`.

---
name: edit-wording
description: The partner wants a narrative or clerical change to a section (wording, tone, order, emphasis, typos, formatting) with no change to the facts or sources.
---
# Edit wording

Use this when the change is narrative or clerical: wording, tone, order, emphasis, typos, formatting. The facts and sources stay as they are, so the research is not touched. The change goes in the **section's draft**, so the next compile keeps it. Don't ask the partner which layer to change; if the change turns out to touch a fact or source, use `fix-a-source-or-citation` instead.

**Needs `edit_section`, which is not on the server yet.** Once it is: call `edit_section` with the deal, the section, and the exact old and new text. Several edits can stack before one compile.

**Until then, use the revision path:**

1. Find the deal with `list_deals` and read the section's draft with `get_artifact` (`draft.section:<section>`).
2. Call `start_revision` with the deal, that section, the partner's request in their words as `angle`, and `start: draft`. Research is not reopened.
3. Call `next_step`. It hands out the section's draft again: apply exactly the change asked for and leave the rest of the text as it was. Submit it with `submit_artifact`.
4. Keep calling `next_step` until it says done, then compile (see `compile-and-check-the-site`).

Tell the partner in one line what changed and where, e.g. "Tightened the opening of the Team section."

Call next: `edit_section` (not yet available; until it is, `start_revision` with `start: draft`).

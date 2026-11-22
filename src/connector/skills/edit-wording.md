---
name: edit-wording
description: The partner wants a narrative or clerical change to a section (wording, tone, order, emphasis, typos, formatting) with no change to the facts or sources.
---
# Edit wording

Use this when the change is narrative or clerical: wording, tone, order, emphasis, typos, formatting. The facts and sources stay as they are, so the research is not touched. The change goes in the **section**, so the next compile keeps it. Don't ask the partner which layer to change; if the change turns out to touch a fact or source, use `fix-a-source-or-citation` instead.

1. Find the deal with `list_deals`. Read the section as it stands with `get_artifact`; `next_step`'s inputs and `edit_section`'s reply name its current artifact (a draft, or the latest enhancement of it).
2. Call `edit_section` with the deal, the section (key, name, or number), and `edits`: each `old` copied exactly from the section, with enough words around it to match once, and its `new`. To replace the whole section, send `text` instead.
3. If it returns `validation_failed`, an `old` didn't match exactly once: copy it again from the section and retry. If it returns `revision_open`, finish or cancel that revision first.
4. Several edits can stack, across sections. When every change the partner asked for is in, compile once (see `compile-and-check-the-site`).

Tell the partner in one line what changed and where, e.g. "Tightened the opening of the Team section."

Call next: `edit_section`, then `compile`.

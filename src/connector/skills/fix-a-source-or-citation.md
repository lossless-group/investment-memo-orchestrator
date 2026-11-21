---
name: fix-a-source-or-citation
description: The partner says a citation is wrong or broken, a source is weak, or information is missing; fix the section's research, then rewrite the section from it.
---
# Fix a source or citation

Use this when the complaint is about the source information: a bad or broken citation, incomplete information, weak research, a missed insight. The fix goes in the section's **research**, not only in the wording, because the memo is rebuilt from research and sections on every compile. Don't ask the partner which layer to change.

1. Find the deal with `list_deals` and the section the partner means. Read its research with `get_artifact` (`research.section:<section>`) and its draft (`draft.section:<section>`).
2. If the partner has new evidence (a link, a file, notes), add it with `add_materials` first and keep the material ids.
3. Call `start_revision` with the deal, that section, the partner's complaint in their words as `angle`, `start: research`, and any `material_ids`.
4. Call `next_step`. It hands out the section's research again. Fix the research file: correct or replace the citation, add what was missing, cut what can't be verified. Research must be verifiable; it doesn't have to read well. Show the partner what changed and submit it with `partner_approved: true` once they agree.
5. Call `next_step` for the draft and rewrite the section from the research. Load `rewrite-a-section-from-its-research` with `get_skill` first: it is a separate task with its own rules.
6. Keep calling `next_step` until it says done, then compile (see `compile-and-check-the-site`).

Tell the partner in one line where the change went, e.g. "Fixed the citation in the market research and rewrote the Market section from it."

Call next: `start_revision` with `start: research`.

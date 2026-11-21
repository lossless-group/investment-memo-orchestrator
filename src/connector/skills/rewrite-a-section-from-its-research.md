---
name: rewrite-a-section-from-its-research
description: Rewrite one section's draft after its research changed, from exactly two inputs (the research file and the current draft), with no outside knowledge.
---
# Rewrite a section from its research

Fixing research and rewriting the section are **two separate tasks**. Do them one after the other, never as one. If you hand the rewrite to a subagent, give it only this playbook and the two inputs.

**Task 1, the research** (done before this playbook): the research file is edited and approved. It must be verifiable; it doesn't have to tell a story.

**Task 2, the rewrite** (this playbook): `next_step` hands out the section's draft step. Write the new draft from exactly two inputs:

- the section's research file, as approved, and
- the section's current draft (among the step's inputs; read it with `get_artifact` if it was cut short).

Rules:

- Use nothing else. No knowledge of your own, no web research on the side, no facts from other sections. If the research doesn't support a claim, the claim goes.
- Keep what still holds in the current draft: its structure, its voice, its citations that still match the research. Change what the research changed.
- Every fact keeps its citation to the research's source.
- The job is only to make a good narrative out of the research that's there.

Keeping the tasks apart stops invented facts, lets the research be checked on its own, and keeps iterations small. When the two were done together, drafts swung widely between versions.

Call next: `submit_artifact` with the new draft, then `next_step`.

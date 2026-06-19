---
title: "Section Citations Orphaned When Definitions Live in 1-research/"
lede: "Writer agents emit `[^N]` references in `2-sections/NN-foo.md` but the actual citation *definitions* live in `1-research/NN-foo-research.md`. The downstream `cli/utils/consolidate_citations.py` only reads `### Citations` blocks inside section files, so every ref whose definition lives in the research file becomes an orphan in the exported memo. On the Panthalassa-Deck-Series-B v0.0.3 export, 17 distinct ref IDs in body but only 8 defs survived — most of the bibliography didn't render. A new `cli/utils/hydrate_section_citations.py` pulls missing defs from 1-research/ into each section file as a pre-step, wired into `recompile_memo.py` so it runs on every assembly."
date_authored_initial_draft: 2026-06-15
date_authored_current_draft: 2026-06-15
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-06-15
at_semantic_version: 0.0.0.1
usage_index: 0
publish: true
augmented_with: Claude Code (Opus 4.7)
category: Issue-Resolution
tags: [Citation-Assembly, Section-Citations, 1-Research, MemoPop, Orchestrator, Pandoc, Export]
authors:
  - Michael Staton
files_changed:
  - apps/memopop-orchestrator/cli/utils/hydrate_section_citations.py
  - apps/memopop-orchestrator/cli/recompile_memo.py
date_created: 2026-06-15
date_modified: 2026-06-15
---

# Section Citations Orphaned When Definitions Live in 1-research/

## The symptom

Export a memo (HTML or PDF) and a large fraction of citation markers in the rendered output show as raw `[^N]` text instead of a clickable footnote, or — worse — get silently collapsed to the wrong source. On the 2026-06-14 Panthalassa-Deck-Series-B v0.0.3 export:

- Body had 17 distinct citation IDs `[^1]` … `[^17]`
- Only 8 unique citation *definitions* made it into the consolidated citation block
- The fix_citations.py post-processor collapsed 173 footnote refs into 8 sources, including merging references from different sections that all happened to use `[^N]` locally

## The root cause

The orchestrator's writer agent emits two artifacts per section:

1. `2-sections/NN-foo.md` — the prose draft. Contains `[^N]` inline references.
2. `1-research/NN-foo-research.md` — the per-section research file. Contains the `[^N]: …` definitions and the foundational source corpus the writer was citing.

This split is documented in the `manage-memo-citations` skill ("foundational citations live in 1-research/, not in section files"). The pipeline relies on it.

The downstream `cli/utils/consolidate_citations.py` only reads `### Citations` blocks *inside* section files. If a section file has refs in the body but no `### Citations` block (because the defs live in `1-research/`), the consolidator never sees the definitions. Two compounding failure modes follow:

1. **Orphan refs.** Refs in the body have no matching def in the final draft. Pandoc renders them as raw text or drops them.
2. **Positional misalignment.** `consolidate_citations.py` assumes `content_sections[i]` references `citation_blocks[i]` — a positional assumption that only holds if *every* section has a `### Citations` block. When a section has refs but no block, the consolidator renumbers its refs against the *next* section's def map, corrupting the bibliography.

This bug affects every memo that follows the documented research-and-section split. Until now it has been masked by per-section `### Citations` blocks that some writer paths happen to emit. The Panthalassa Series B v0.0.3 export made it acute because most sections had no per-section block.

## The fix

A new pre-assembly step: `cli/utils/hydrate_section_citations.py`.

For each `2-sections/NN-foo.md`:

1. Collect every `[^id]` reference in the body.
2. Collect every `[^id]:` definition already in the section file's `### Citations` block (if any).
3. For each reference *not* yet defined locally, look up the same id in `1-research/NN-foo-research.md` and pull the definition into the section file's `### Citations` block (creating the block if absent).
4. Report any refs that have no matching def in either place — these are real orphans (writer-invented IDs, research-file gaps) and the script prints them so the analyst can see them.

The script is idempotent. Section files that already have complete `### Citations` blocks are not modified. Calling it twice in a row is a no-op the second time.

`cli/recompile_memo.py` was updated to invoke `hydrate_section_citations.py` *before* `assemble_sections()` runs. That means every existing pipeline that already calls `recompile_memo.py` (and every future one) gets the fix automatically. No agent prompt changes, no outline YAML changes.

Exit code 2 from the hydrator means "orphans reported" — `recompile_memo.py` treats that as informational, not failure. Exit code 0 means no orphans. Any other exit code is a real bug.

## Effect on the Panthalassa-Deck-Series-B v0.0.3 export

Before:

```
Found 4 '### Citations' blocks
Consolidated to 1 citation block with 9 unique citations
…
Consolidated 173 duplicate footnotes
8 unique sources remain
```

After (with the new hydrator running first):

```
✓ 01-risks: hydrated from 1-research/
✓ 02-diligence: hydrated from 1-research/
✓ 03-capital-syndicate: hydrated from 1-research/
✓ 04-category-leadership: hydrated from 1-research/
✓ 07-colossal-market-size: hydrated from 1-research/
✓ 08-counter-cyclicality: hydrated from 1-research/
✓ 09-cash-on-cash-return-probability: hydrated from 1-research/

7 section(s) hydrated

Orphan references (referenced but never defined — will not resolve in export):
  02-diligence: [^4], [^7], [^8], [^9], [^10], [^11], [^12], [^13], [^17]
  07-colossal-market-size: [^5], [^6], [^7]

Found 10 '### Citations' blocks
Consolidated to 1 citation block with 58 unique citations
…
Consolidated 157 duplicate footnotes
47 unique sources remain
```

Bibliography went from 8 sources to 47. The 12 remaining orphans (in sections 02 and 07) are real — they're refs the writer agent emitted with no matching def in either the section or the research file. They surface in the hydrator's report so the analyst can fix them deliberately.

## What the hydrator does NOT do

- It does not invent definitions. If `[^9]` is in the section body but appears in neither the section's existing block nor `1-research/NN-foo-research.md`, it stays orphan and is reported.
- It does not deduplicate across sections — that's `cli/utils/fix_citations.py`'s job, run later in the export.
- It does not enforce the schema of the citation definitions. Whatever the writer agent emitted is what the hydrator pulls.
- It does not modify `1-research/*-research.md` files. They remain the source of truth.

## Anti-patterns to avoid

- **Don't move section definitions out of `1-research/` to "fix" the symptom.** That breaks the manage-memo-citations skill's foundational invariant. The hydrator is the right fix; it preserves the canonical split.
- **Don't run `consolidate_citations.py` without the hydrator step first.** You'll get the original bug. `recompile_memo.py` now runs both in order — use it.
- **Don't hand-edit `### Citations` blocks the hydrator added.** They get refreshed on every assembly run; your edits will survive but the source of truth is `1-research/`.

## See also

- `context-v/agent-skills/manage-memo-citations/SKILL.md` — the canonical citation discipline (foundational defs in `1-research/`, semantic IDs over numeric, etc.)
- `cli/utils/hydrate_section_citations.py` — the new tool
- `cli/recompile_memo.py` — the assembly pipeline that now invokes the hydrator
- `cli/utils/consolidate_citations.py` — the downstream consolidator the hydrator feeds
- `changelog/2026-05-26_01.md` — the earlier assembler hardening pass; this bug was always present but masked

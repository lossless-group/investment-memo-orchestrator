---
type: Plans
title: "Fix Citation Collisions in Final Assembly"
lede: "The local pipeline's assemble_citations() treats each section's [^N] as global, so most citations in a final draft point at another section's source. Route it through consolidate_citations(), which the connector's compile already uses."
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
status: In-Progress
issue_reference: context-v/issues/Final-Draft-Citations-Collide-Across-Sections.md
depends_on: []
tags: [Plan, Citations, Assembly, Final-Draft]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: fix/citation-collisions
---

# Fix Citation Collisions in Final Assembly

[[Final-Draft-Citations-Collide-Across-Sections]] is still open. Its sibling, [[Dataroom-Citations-Duplicate-In-Consolidated-Block]], was resolved on 2026-11-17 with `merge_duplicate_definitions()`. That guard catches duplicate definitions but not this bug: here the definitions are distinct, they're just attached to the wrong citations.

This matters for the uploader. Finished memos produced by the local pipeline become compiled version 1 on the server, so any memo assembled with this bug goes up with wrong citations.

## Steps

1. **Test first.** In `tests/` beside `test_citation_dedupe.py`: two sections, each with its own research file. Both use `[^25]` for different URLs. After `assemble_citations()`, each section's claim links to its own URL, and the block has two definitions.
   - [ ] Fails on current code.
2. **Fix.** In `src/agents/citation_assembly.py`, make `assemble_citations()` pair each section with its own research file's definitions and pass them through `consolidate_citations()` (keys local per text, sources identified by link). Drop the global first-come `all_definitions` fill from `1-research/*.md`. Keep `merge_duplicate_definitions()` as the final guard.
   - [ ] Test passes, with the rest of the suite.
3. **Guard.** After assembly, for each section, every inline key's definition URL should appear in that section's research file. Log a warning per mismatch, so this class of bug shows up in the run log.
   - [ ] Done
4. **Find the memos it affected.** Any final draft assembled by the local pipeline in codified mode before the fix. List them per firm by checking whether the run log's unique-citation count is far below the distinct sources in the research files.
   - [ ] List written into the issue.
5. **Repair before upload.** Rebuild the affected final drafts with the fixed assembler (or the one-off remap the issue describes), and re-export dark and light HTML and PDF. Do this before [[Apply-the-Deal-Folder-Uploader]] step 3, or re-run the uploader for those deals afterwards.
   - [ ] Done
6. Close the issue with a resolution section.

## Related

- `src/agents/citation_assembly.py`: `assemble_citations`, `renumber_citations`, `consolidate_citations`
- [[Apply-the-Deal-Folder-Uploader]]

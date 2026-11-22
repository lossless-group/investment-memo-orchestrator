---
title: "Appended Research Blocks Reuse Footnote Keys"
lede: "When a run reuses a prior version's research and appends new sources, the appended block numbers its footnotes from 1 again. Assembly keeps only the last definition of each key, so footnotes from the reused block link to sources from the appended one."
date_created: 2026-11-21
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Citations, Research, Assembly]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
---

# Appended Research Blocks Reuse Footnote Keys

## What happens

`src/research_append.py` augments a reused research file by appending a new document under `## Added from N new sources`. That block numbers its footnotes from `[^1]` again, so one research file defines `[^1]`, `[^2]`, … twice, once per block, each time for a different source.

Two things then go wrong:

1. **Assembly mis-links them.** `extract_citation_definitions` in `src/agents/citation_assembly.py` builds a dict, so the last definition of each key wins. A footnote written against the reused block (for example a team bio citing the company website as `[^1]`) is linked to whatever the appended block called `[^1]` (for example a pitch deck). This affects memos assembled today, not only old ones. The 2026-11-21 hex-key fix doesn't cover it, because hex keys are assigned after this lookup.
2. **Repair refuses them.** `src/citation_repair.py` refuses a section whose research file "defines [^N] more than once", so these memos are reported as unrepairable, and the scan reads them as the older collapsed-keys bug, which they are not.

Sections drafted after the append are of two kinds. Some keep the reused text and add a `### Added from …` part, each part using its own block's keys. Others are redrafted in one part from the combined file, mixing keys from both blocks.

Found 2026-11-21 while diagnosing memos the repair tool refused. In one memo, 123 of 406 footnotes link to the wrong source, including every team bio, which links to a literature review instead of the team deck. Firm and deal details are in the firm's own repo.

## Fix

1. **Stop producing it.** When appending, re-key the new block so its keys can't collide with the reused block: continue the numbering, or assign hex keys from `src/citation_keys.py` at append time. Test: an appended file defines each key once, and assembling a section that cites both blocks links each footnote to its own block's source.
2. **Make assembly block-aware** for research files that already exist: split at `## Added from`, and resolve each key in the block that defines it. When two blocks define a key differently, refuse that key rather than silently taking the last.
3. **Make repair block-aware** in the same way (shared helper). Split sections at `### Added from` and match each part to its block. In a one-part section, resolve each key in the block that defines it, and refuse only keys whose definitions conflict, not the whole file. Pair markers on lines whose prose is identical to the section file, so a few edited lines don't block a whole region.
4. **Tell the two apart in the scan.** Report "appended blocks" separately from "collapsed keys".

Related: [[Fix-Citation-Collisions-in-Final-Assembly]], [[Hex-Code-Citations-and-a-Repair-Tool]].

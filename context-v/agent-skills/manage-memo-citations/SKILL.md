---
title: "Manage Memo Citations Durably"
lede: "Foundational citation definitions live in 1-research/, not in section files. The assembler strips defs from section files but treats research files as a durable fallback source — so anything you want to survive multiple assembly runs has to live there."
date_authored_initial_draft: 2026-05-26
at_semantic_version: 0.0.0.1
usage_index: 0
publish: false
category: Reference
tags: [Citations, Assembler, Research-Files, Section-Files, Workflow]
authors:
  - Michael Staton
augmented_with: "Claude Code (Opus 4.7)"
---

# Manage Memo Citations Durably

## The Rule

**Every foundational citation definition belongs in a `1-research/*-research.md` file.**

Section files (`2-sections/*.md`) and the assembled final draft (`7-{Deal}-vX.Y.Z.md`) are downstream artifacts. They churn — every assembler run rewrites their citation IDs and strips local citation definitions from them. Research files, by contrast, are durable: the assembler reads them as a fallback definition source (see `src/agents/citation_assembly.py:281`) and never writes back to them.

If a citation definition lives only in a section file, it will be stripped on the next assembler run and the inline references that point to it will become orphans — Pandoc renders orphan `[^X]` markers as literal text (e.g. `[^12]`), not as superscript footnotes.

## Two assembly paths — and the one that used to break

The orchestrator has two ways to assemble a memo:

1. **Full pipeline** (`src/agents/citation_assembly.py`, invoked end-to-end during `python -m src.main`). This path reads `1-research/` as a fallback definition source per the rule above.
2. **CLI recompile** (`python cli/recompile_memo.py`, used for partial reassembly after section edits). Until 2026-06-15 this path did *not* read `1-research/`. Section refs whose defs lived in research files became orphans, and `cli/utils/consolidate_citations.py`'s positional-renumbering pass corrupted neighboring sections too. See `context-v/issue-resolution/Section-Citations-Orphaned-When-Defs-Live-In-1-Research.md`.

The fix is `cli/utils/hydrate_section_citations.py`, now wired into `recompile_memo.py` as a pre-step. It pulls missing defs from `1-research/*-research.md` into each section file's `### Citations` block before assembly. Idempotent; safe to run repeatedly. The CLI path now matches the full pipeline's behavior.

If you're editing sections by hand and then reassembling, you don't need to think about this — `recompile_memo.py` runs the hydrator for you. If you're invoking `consolidate_citations.py` directly, run `hydrate_section_citations.py` first.

## Why It Matters

The assembler does five things in order ([source](../../src/agents/citation_assembly.py)):

1. Scans every section file for inline `[^X]` markers; builds `appearance_order`.
2. Scans every section file + every research file for `[^X]:` definitions; first definition wins per key.
3. Renumbers inline markers sequentially (1, 2, 3, …) based on `appearance_order`.
4. **Removes all `[^X]:` definitions from section files in place.**
5. Writes a single consolidated `### Citations` block at the bottom of the assembled draft.

Step 4 is the trap. Any definition you added to a section file is gone after one assembly run. The inline reference survives — but it now points to nothing.

Research files are immune to step 4 by design.

## Where to Put a New Citation (by Theme)

| Section the citation supports | Research file to host the `[^name]:` definition |
|---|---|
| Overview / product / market sizing | `1-research/01-overview-research.md` |
| Investment thesis, comps, upside, developer-momentum precedents | `1-research/02-why-invest-research.md` |
| Competitive landscape, performance comparisons, regulatory | `1-research/03-situation-and-market-overview-research.md` |
| Founders, team, governance, board | `1-research/04-team-research.md` |
| Business model, ASP, GTM, exit comps (MongoDB / Elastic / Databricks etc.) | `1-research/05-business-economics-and-ethics-research.md` |
| Round mechanics, cap table, instrument | `1-research/06-fundraising-round-research.md` |
| Risk register, acquisition precedents (Firebase / Red Hat / HashiCorp etc.) | `1-research/07-flags-research.md` |

If a citation is referenced from multiple sections (e.g., the analyst-notes-vault), it can be defined in just one research file — the assembler walks all of them and finds the first match.

## ID Naming: Semantic Over Numeric

**Use descriptive semantic IDs.** Example:

```markdown
[^cursor-2026]: 2026, Apr 17. [Cursor in talks to raise $2B at $50B valuation]…
[^github-2018]: 2018, Jun 04. [Microsoft to acquire GitHub for $7.5 billion]…
[^oracle-fy25]: 2025, Jun 11. [Oracle Announces Fiscal 2025 Fourth Quarter and Fiscal Full Year Financial Results]…
```

Not:

```markdown
[^14]:  ❌  collides with whatever number the assembler renumbers something else to
[^cite-1]:  ❌  not human-meaningful; tells you nothing when you grep
```

**Why semantic wins**:
- Survives re-renumbering. The assembler maps `[^cursor-2026]` → some sequential number at write time, but the source stays semantic.
- Self-documents. `grep cursor-2026` finds every body reference to that source.
- Avoids collisions with the assembler's own numeric output. If you write `[^14]` by hand, the assembler will think you mean the global #14 citation, which may be something completely different.

**The assembler's regex** (post-fix in our session) matches `[a-zA-Z0-9_-]+`, so hyphenated IDs like `cursor-2026` work. Underscores and digits also work. No other punctuation (no slashes, dots, colons).

## The Authoring Loop

```
1. Edit section file (2-sections/*.md) with inline [^semantic-id] markers
2. Make sure [^semantic-id]: definition exists in some 1-research/*.md file
3. Run assembler:
     python -m src.agents.citation_assembly io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z
4. (optional) Run citation-positioning script:
     python scripts/fix_citation_positioning.py path/to/7-{Deal}-vX.Y.Z.md
5. (optional) Insert TOC via src.agents.toc_generator
6. Export:
     python cli/export_branded.py path/to/7-{Deal}-vX.Y.Z.md --brand {firm} --mode dark --pdf -o {exports-dir}
```

**Never edit the assembled `7-{Deal}-vX.Y.Z.md` directly.** It's a build artifact. Any edits you make there are lost the next time you run the assembler.

## Recovery: When Citations Got Lost

If the assembled draft has orphan `[^X]` markers showing as literal text (not superscript), one of three things happened:

1. **A definition was only in a section file** and got stripped by an assembler run. Fix: move the definition into the appropriate `1-research/*-research.md` file, re-assemble.
2. **A semantic ID has no definition anywhere** (you referenced it but never added `[^name]: …`). Fix: add the definition to a research file.
3. **The body has a hand-typed numeric ID that doesn't exist in the consolidated block** (e.g., you wrote `[^14]` in a section file but only 11 citations are defined globally). Fix: change to a semantic ID with a real definition, or remove.

To recover prior definitions:
- Check `7-{Deal}-vX.Y.Z.md` of any earlier version (final drafts are flat, full snapshots).
- Check `1-research/*.md` files (they're durable).
- Check conversation logs / Git history.

## The "Two Sources of Truth" Anti-Pattern

It is tempting to write a citation definition into a section file ("near the prose that uses it"). **Don't.** That makes the section file a temporary source of truth that the assembler will clobber. You end up with the same definition in two places (the section file's local block + the assembled draft's consolidated block), and the two will drift the moment anyone edits one and not the other.

One definition, one place: `1-research/`.

## When You Need to Add a New Citation Quickly

```markdown
# in 1-research/02-why-invest-research.md (or whichever theme fits):
[^my-new-citation]: 2026, May 26. [Title of source](https://url). Publisher. Brief note on what this supports. Published: 2026-05-26 | Updated: N/A
```

```markdown
# in 2-sections/02-why-invest.md (or wherever you need to cite it):
…and the company has crossed $1B in ARR. [^my-new-citation]
```

Run the assembler. Done.

## See Also

- `context-v/reminders/Citation-Reminders.md` — formatting rules for inline citations (spacing, punctuation positioning)
- `context-v/reminders/Extended-Markdown-Citation-System-Syntax.md` — Obsidian-flavored citation syntax conventions
- `scripts/fix_citation_positioning.py` — post-assembly script that enforces "citation after punctuation; consolidate same-ID repeats per paragraph"
- `src/agents/citation_assembly.py` — the assembler itself
- `src/final_draft.py` — naming/path conventions for the final draft file

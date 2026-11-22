---
name: manage-memo-citations
description: "Put memo citation definitions in 1-research/ rather than in section files, so they survive repeated assembly runs. Use whenever adding, moving, renaming, or debugging a citation in a generated memo; whenever a footnote renders as a bare marker, a reference disappears after re-assembly, or a citation ID collides; whenever asked \"why did my citation vanish\" or \"where should this source go\". Encodes the durability rule (the assembler strips definitions from section files but treats research files as a fallback source), the two assembly paths and which one used to drop them, hex-code IDs derived from the source (not numbers, not hand-made names), and where a new citation belongs by theme."
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

## ID Naming: Hex Codes From the Source

**Use the source's hex key.** Lossless Flavored Markdown's rule 2 requires citation keys derived from the source, not sequential numbers, and MemoPop follows it. Make the key with `src/citation_keys.py`:

```bash
.venv/bin/python -c "from src.citation_keys import source_key; print(source_key('2026, Apr 17. [Cursor in talks to raise \$2B](https://example.com/cursor-raise).'))"
```

```markdown
[^k3x9qa]: 2026, Apr 17. [Cursor in talks to raise $2B at $50B valuation](https://…)…
[^7hq2mz]: 2025. [Company Pitch Deck](internal-document). Company Materials.
[^0p4wbc]: 2025. [Cap table](file:///…/dataroom/cap-table.xlsx). Dataroom.
```

Not:

```markdown
[^14]:  ❌  a position in one section's list; another section's [^14] is a different source
[^cursor-2026]:  ❌  readable, but two people name the same source two ways, and nothing checks it
```

**Why hex wins**:
- Same source, same key, in every section and memo. The key is hashed from the source's link (or its text without the date), so sections can't collide when they are stitched together. Numbered keys did, and most finished memos before 2026-11-21 link footnotes to another section's source ([[repair-memo-citations]] repairs them).
- Checkable. A key that doesn't match its definition's source is detectable.
- Readers still see 1, 2, 3: Pandoc and LFM number footnotes at render time.

Deck and dataroom sources take plain keys like any other (no prefixes). If two different sources ever share six characters, `assign_keys()` gives both eight.

**The assembler's regex** matches `[a-zA-Z0-9_-]+`, so hex keys work. Older semantic IDs like `cursor-2026` still assemble; don't add new ones.

## The Authoring Loop

```
1. Edit section file (2-sections/*.md) with inline [^<hex>] markers (source_key())
2. Make sure [^<hex>]: definition exists in some 1-research/*.md file
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
2. **A key has no definition anywhere** (you referenced it but never added `[^name]: …`). Fix: add the definition to a research file.
3. **The body has a hand-typed numeric ID that doesn't exist in the consolidated block** (e.g., you wrote `[^14]` in a section file but only 11 citations are defined globally). Fix: change to the source's hex key with a real definition, or remove.
4. **Footnotes link to the wrong source** (another section's): the memo was assembled before the 2026-11-21 fix. Use [[repair-memo-citations]].

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
[^<hex>]: 2026, May 26. [Title of source](https://url). Publisher. Brief note on what this supports. Published: 2026-05-26 | Updated: N/A
```

```markdown
# in 2-sections/02-why-invest.md (or wherever you need to cite it):
…and the company has crossed $1B in ARR. [^<hex>]
```

`<hex>` is `source_key()` of the definition line (without the `[^…]: ` prefix). Run the assembler. Done.

## See Also

- `context-v/reminders/Citation-Reminders.md` — formatting rules for inline citations (spacing, punctuation positioning)
- `context-v/reminders/Extended-Markdown-Citation-System-Syntax.md` — Obsidian-flavored citation syntax conventions
- `scripts/fix_citation_positioning.py` — post-assembly script that enforces "citation after punctuation; consolidate same-ID repeats per paragraph"
- `src/agents/citation_assembly.py` — the assembler itself
- `src/citation_keys.py` — `source_key()` and `assign_keys()`, the hex keys
- [[repair-memo-citations]] — repair memos whose footnotes link to another section's source
- `src/final_draft.py` — naming/path conventions for the final draft file

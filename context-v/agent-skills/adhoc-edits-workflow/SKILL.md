---
title: "Ad-Hoc Edits Workflow for an Existing Memo"
lede: "When the user asks for a one-off change to a deal memo, follow a strict four-step pipeline: (1) drop facts + citations into research first; (2) integrate into the right section with proper prose; (3) assemble into the final draft; (4) export HTML, then PDF. Never edit the final draft directly, never start with prose before the citation exists."
date_authored_initial_draft: 2026-05-26
at_semantic_version: 0.0.0.1
usage_index: 0
publish: false
category: Workflow
tags: [Workflow, Editing, Assembly, Export, Memo-Pipeline, Discipline]
authors:
  - Michael Staton
augmented_with: "Claude Code (Opus 4.7)"
---

# Ad-Hoc Edits Workflow for an Existing Memo

## When to Use This Skill

You are using this skill when the user asks for a discrete change to an already-assembled deal memo. Examples that trigger it:

- "Add Paramount to the customer list."
- "The seed wasn't priced — it was a SAFE bridge. Fix."
- "Look up Oracle's revenue and add it to the upside paragraph."
- "Insert this chart at the Investment Conviction section."
- "Add a fourth risk to the competitive risks subsection."

Whenever a change is scoped to one or a few specific edits — not a full re-run of the pipeline — this is the discipline to follow.

## The Four-Step Pipeline

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 1. RESEARCH    →   Add facts + citation defs to 1-research/*.md         │
│                    Don't worry about prose. Get the citation right.      │
├──────────────────────────────────────────────────────────────────────────┤
│ 2. SECTIONS    →   Integrate into the proper 2-sections/*.md file       │
│                    Pay attention to prose flow + paragraph structure.    │
├──────────────────────────────────────────────────────────────────────────┤
│ 3. ASSEMBLE    →   python -m src.agents.citation_assembly <output-dir>  │
│                    Renumbers citations + writes the final draft.         │
├──────────────────────────────────────────────────────────────────────────┤
│ 4. EXPORT      →   HTML first, then PDF (in a single pass via            │
│                    cli/export_branded.py with --pdf flag).               │
└──────────────────────────────────────────────────────────────────────────┘
```

Each step has one responsibility. Don't merge them. Don't skip them. Don't reverse them.

## Step 1 — Research First (no prose)

**Goal**: get the facts and the citation into the durable layer before doing anything else.

**Where**: `io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z/1-research/*-research.md` — pick the file whose theme matches the citation (see the theme→file table in `[[manage-memo-citations]]`).

**What to add**: a single `[^semantic-id]: …` line at the end of the file containing:
- the date (ISO or "YYYY, Mon DD" format the project uses)
- the canonical URL
- the publisher
- a one-sentence note on what this source supports
- `Published: YYYY-MM-DD | Updated: YYYY-MM-DD`

**Don't worry about prose at this step.** If you need to make notes for yourself about which sentence will eventually cite this, you can drop them as bullet points inside the research file, but the *only thing that has to be right* is the citation definition itself.

If the user gave you a number ("Oracle did $57.4B last fiscal year"), confirm via WebSearch before writing the citation. Authoritative sources only — investor relations pages, SEC filings, tier-1 financial press. No blog hot-takes.

**Why this step first**: research files are durable across assembler runs. Section files and the final draft are downstream artifacts that get rewritten. If you skip research and put the citation only in a section file, the assembler strips it on the next run and the inline reference becomes an orphan (Pandoc renders orphan `[^X]` as literal text).

## Step 2 — Integrate Into Sections (prose now matters)

**Goal**: weave the new content into the right section with prose that reads naturally inside the surrounding paragraphs.

**Where**: `io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z/2-sections/*.md` — pick the section file that matches the user's request.

**How**:

- Place the new claim at the natural point in the existing prose. Don't bolt a new sentence to the end of a paragraph if it interrupts the flow — find the right spot and weave it in.
- Use the **same semantic citation ID** you defined in Step 1 (`[^cursor-2026]`, `[^oracle-fy25]`, etc.) — never a numeric ID, never a made-up name.
- Follow the citation positioning rules: marker after terminal punctuation, one space before the bracket (Obsidian-compliant: ` [^id]`). If the same citation appears multiple times in one paragraph, collapse to one marker at the end of the paragraph. (See `context-v/reminders/Citation-Reminders.md`.)
- Re-read the whole paragraph after the edit. Does it flow? Does the new sentence belong where you put it? Are you over-citing (same source three times in two sentences)? Tighten if so.
- If the change is a *correction* (not an addition), find every other place in the memo that asserts the same fact and update those too — silent inconsistency is worse than verbose redundancy.

**Don't edit the final draft (`7-{Deal}-vX.Y.Z.md`) at this step.** It is a build artifact; the assembler will rewrite it. Any prose you put there is lost on the next assembly run.

## Step 3 — Assemble

**Goal**: produce a fresh `7-{Deal}-vX.Y.Z.md` from the current state of the section files (which now include your edits).

**Command**:

```bash
.venv/bin/python -m src.agents.citation_assembly \
  io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z
```

**What this does**:
1. Walks `2-sections/*.md` to find every inline `[^X]` marker.
2. Walks `2-sections/*.md` and `1-research/*.md` to collect every `[^X]: …` definition.
3. Renumbers all inline markers sequentially (1, 2, 3, …) based on first appearance.
4. Strips `[^X]:` definitions from section files in place.
5. Writes the assembled final draft `7-{Deal}-vX.Y.Z.md` with a single consolidated `### Citations` block at the end.

**Verify the assembler output**:

- Look for `Renumbered N citations (sequential 1-N)` with **no `missing definitions` count**. If you see `… , K missing definitions`, your edit referenced a `[^semantic-id]` that doesn't have a matching definition anywhere — go back to Step 1.
- Spot-check the consolidated `### Citations` block at the end of the assembled draft. Every new citation you added in Step 1 should be present here with the correct text.

**Optional post-assembly passes** (run if needed):

- `scripts/fix_citation_positioning.py` — enforces "citation after punctuation; consolidate same-ID repeats per paragraph".
- `src.agents.toc_generator` (called directly via Python — see `context-v/skills/manage-memo-citations` for the snippet) — regenerates the clickable Table of Contents.

## Step 4 — Export (HTML First, Then PDF)

**Goal**: produce the deliverable file the user will read.

**Command** (single invocation, handles both formats):

```bash
.venv/bin/python cli/export_branded.py \
  io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z/7-{Deal}-vX.Y.Z.md \
  --brand {firm} \
  --mode dark \
  --pdf \
  -o io/{firm}/deals/{deal}/exports/dark/
```

**Why HTML first, then PDF**: the export script (`cli/export_branded.py`) does this natively. Pandoc converts markdown → HTML (with embedded CSS, fonts, and footnote rendering), and WeasyPrint converts that *same HTML* → PDF. The PDF is a faithful rendering of the HTML, not a separate render path — so what you see in a browser preview is what ships in the PDF.

**Naming**: the script names the output after the input directory's name. If the file already exists, it appends `.1`. Rename to canonical (`{Deal}-vX.Y.Z.{html,pdf}`) after each export.

**Open the PDF** to confirm the user's edit landed as intended. If a footnote shows as literal `[^X]` text instead of a superscript, there's an orphan citation — go back to Step 1.

## Anti-Patterns (Hard Don'ts)

1. **Editing the final draft (`7-{Deal}-vX.Y.Z.md`) directly.** It's a build artifact. The assembler rewrites it. Your edits get clobbered.
2. **Adding prose before the citation exists in research.** Inevitable when the citation gets stripped: the section file has a `[^id]` with no definition anywhere, Pandoc renders it as literal text, the export looks broken.
3. **Mixing concerns in one pass.** "I'll just edit the section file and the final draft and the research at the same time" leads to drift across three sources of truth. Pipe the change through the four steps in order.
4. **Using hand-typed numeric citation IDs in section files** (e.g., `[^14]`). The assembler renumbers numerics on every run; if you write `[^14]` expecting it to mean MongoDB FY26, the next assembly may renumber MongoDB FY26 to `[^7]` and your `[^14]` becomes a dangling reference.
5. **Skipping the assembly step before exporting.** The export reads from `7-{Deal}-vX.Y.Z.md`. If you haven't assembled since your edits, the export reflects the *previous* state, not your changes. This is the #1 way edits "don't show up" in the PDF.
6. **Exporting from the wrong version directory.** If the deal's working version is `vX.Y.11` but you copy-pasted a command pointing at `vX.Y.10`, the export reflects v10 even though you edited v11's section files.

## The Test: "Could the User's Edit Survive a Re-Assembly?"

Before you call any edit done, ask: *if I run the assembler from scratch right now, does the new content survive?*

- ✓ If the citation definition is in `1-research/` → it survives.
- ✓ If the prose is in `2-sections/` → it survives.
- ✗ If the citation definition is only in `2-sections/` → it gets stripped.
- ✗ If the prose is only in `7-{Deal}-vX.Y.Z.md` → it gets overwritten.

If the answer is no, you skipped Step 1 or Step 2. Fix it before exporting.

## Quick-Reference Loop

```bash
# Step 1: edit 1-research/*.md with new [^semantic-id]: definition
# Step 2: edit 2-sections/*.md with new inline [^semantic-id] reference + prose

# Step 3: assemble
.venv/bin/python -m src.agents.citation_assembly \
  io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z

# (optional) tidy citation positioning
.venv/bin/python scripts/fix_citation_positioning.py \
  io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z/7-{Deal}-vX.Y.Z.md

# (optional) refresh TOC
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from src.agents.toc_generator import extract_headers, generate_toc_markdown, insert_toc_after_executive_summary, remove_existing_toc
p = Path('io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z/7-{Deal}-vX.Y.Z.md')
c = p.read_text(); c = remove_existing_toc(c); h = extract_headers(c)
p.write_text(insert_toc_after_executive_summary(c, generate_toc_markdown(h)))
"

# Step 4: export (HTML + PDF)
.venv/bin/python cli/export_branded.py \
  io/{firm}/deals/{deal}/outputs/{Deal}-vX.Y.Z/7-{Deal}-vX.Y.Z.md \
  --brand {firm} --mode dark --pdf \
  -o io/{firm}/deals/{deal}/exports/dark/
```

## See Also

- `context-v/skills/manage-memo-citations/SKILL.md` — the citation discipline this workflow depends on (theme→file table, semantic-ID rules, recovery procedures).
- `context-v/reminders/Citation-Reminders.md` — formatting rules for inline citation markers (spacing, punctuation positioning).
- `context-v/reminders/Ideal-Orchestration-Agent-Workflow.md` — the full pipeline that ran when the memo was first built. This skill is the *ad-hoc* variant for one-off edits *after* that pipeline has run.
- `src/agents/citation_assembly.py` — the assembler implementation (the engine of Step 3).
- `cli/export_branded.py` — the exporter (the engine of Step 4).
- `scripts/fix_citation_positioning.py` — the citation-positioning enforcement script.

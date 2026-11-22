---
name: repair-memo-citations
description: "Find and repair finished memos whose footnotes link to another section's source, rewriting them as source-derived hex keys. Use whenever a partner or reviewer says a citation points at the wrong source, a footnote doesn't support its claim, or the same number means different things in different sections; whenever asked to audit, scan, or fix citations across firms' memos; whenever re-exporting a memo assembled before the 2026-11-21 citation-collision fix; or whenever someone asks why MemoPop uses hex citation keys. Encodes the scan, dry run, write, export sequence, how to read repair-report.json, what the tool refuses and why, and what to tell the partner about refused sections."
title: "Repair Memo Citations That Link to the Wrong Source"
lede: "Memos assembled before the citation-collision fix numbered every section's sources from 1 and then resolved the numbers across the whole memo, so most footnotes link to another section's source. cli/repair_citations.py re-derives each section's footnotes from its own research, writes them as hex keys, and refuses anything it can't prove."
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
date_last_updated: 2026-11-21
at_semantic_version: 0.0.0.1
usage_index: 0
publish: false
category: Reference
tags: [Citations, Hex-Codes, Repair, Final-Draft, Exports, LFM]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5.5"
---

# Repair Memo Citations That Link to the Wrong Source

## Why links went wrong

Each section is researched on its own, and its research file numbers its sources from 1. Overview's `[^25]` and Flags' `[^25]` are different sources. Until 2026-11-21 the final assembler treated those numbers as if they meant the same thing everywhere: every section's `[^25]` linked to whichever section defined `[^25]` first. The prose is right and the section files are right; the finished memo (`7-<Deal>-<version>.md`) and every export made from it link claims to the wrong sources.

The assembler is fixed for new runs ([[Final-Draft-Citations-Collide-Across-Sections]]). Memos already finished stay wrong until they are repaired. A scan on 2026-11-21 found about 40 affected finished versions.

## Why hex codes

A number is a position, not a source: it means something only inside the list that produced it, so any stitching, reordering or copying breaks it. Lossless Flavored Markdown already requires citation keys derived from the source (rule 2 of the `lossless-flavored-markdown` skill): `[^1ucdcd]`, not `[^1]`. `src/citation_keys.py` makes them: six characters of `0-9a-z` hashed from the source's link (or, with no link, its text without the date). The same source gets the same key in every section and every memo, so two sections can no longer collide. Deck and dataroom sources get plain keys too (a deck with no link is identified by its text; a dataroom file by its `file://` link). Keys are assigned once per memo over every definition; if two different sources ever share six characters, both get eight. Pandoc and LFM number the footnotes 1, 2, 3 at render time, so readers still see numbers.

## When to run it

- A partner says a footnote doesn't support its claim, or links to an unrelated article.
- Before re-sending or re-exporting any memo finished before 2026-11-21.
- As a sweep across firms, starting from the scan.

Not for memos assembled after the fix (they come out right), and not to add or change sources: for that, edit research files ([[manage-memo-citations]]) or use the connector's edit tools.

## The sequence

Run from the orchestrator root with its venv.

```bash
# 1. Scan: which finished memos link to another section's source, and how much
.venv/bin/python cli/repair_citations.py --scan io

# 2. Dry run (the default): what would be repaired and refused; writes nothing
.venv/bin/python cli/repair_citations.py io/<firm>/deals/<Deal>/outputs/<Deal>-v0.0.1

# 3. Write in place (keeps 7-<Deal>-v0.0.1.md.bak and writes repair-report.json),
#    then export dark and light HTML and PDF to io/<firm>/deals/<Deal>/exports/<mode>/
.venv/bin/python cli/repair_citations.py <version-dir> --write --export

# Or try it on a copy first
.venv/bin/python cli/repair_citations.py <version-dir> --out /tmp/<Deal>-repaired
```

`--export` runs `cli/export_branded.py --brand <firm> --firm <firm> --mode dark|light --pdf`, taking the firm from the path; pass `--brand` or `--firm` to override. When a version dir holds more than one `7-*.md` (sometimes one named for another version), the tool stops until you name it with `--memo 7-<Deal>-<version>.md`.

Exit codes: 0 repaired, 2 nothing repairable (memo untouched), 1 error or prose changed (nothing written).

Then commit each firm's changes in its own repo (`io/<firm>/` is a separate private repo) with a changelog note, and list what was refused.

### Reading the scan

Each row is `wrong/cited share path`: how many of the memo's section citations link to a source that only another section's research cites. Flags under a row:

- **collapsed keys in N research file(s)**: those sections will be refused (see below).
- **several 7-\*.md here**: pass `--memo`.
- **duplicate of ...**: the same deal and version also sits under another folder (some firms have deals copied from `deals/` to `portfolio/`). Repair the one the firm actually uses and ask before touching the other.

## Reading the report

The dry run prints, and `--write`/`--out` save to `repair-report.json`, one line per section with a research file:

| Status | Meaning |
|---|---|
| `repaired` | Every footnote now links to the source the section's own research gave it |
| `unrepairable` | Left byte-identical, numbered keys and all; `reason` says why |
| `no-citations` | Nothing to do |

Then `unverified`: text with no research file (title, Executive Summary, Closing Assessment, scorecard, anything added after assembly). Its footnotes are converted to hex but keep pointing at the source they point to now, because there is no section research to check them against. They were usually written against the final numbering and are often right, but nobody has proven it.

Also: `kept_numbered_keys` (the keys left in refused sections, still defined in the block), `new_sources`, `notes` (markers with no definition anywhere, a block that defined one key twice), and `prose_unchanged`.

## What it refuses, and why

It repairs a section only when it can prove the mapping. Otherwise it leaves the section exactly as it was:

- **Research file defines a key more than once.** Memos from an older bug, where keys collapsed during renumbering, have research files with five `[^1]:` lines. The local key no longer names one source, so there is nothing to map back to. Guessing would replace one wrong link with another.
- **Marker count differs between memo and section file, or the order doesn't pair one to one.** The section was edited after assembly (a revision pass, a hand edit). The tool never matches by surrounding text: a near-match is exactly how a claim gets the wrong source.
- **Heading missing or found twice.** It can't find the section's span.
- **A cited key has no definition in the research file.**

Refused sections keep their numbered keys, so `grep -E '\[\^[0-9]+\]'` on a repaired memo finds exactly what is still unproven. If prose differs after repair (only markers and the block may change), it writes nothing.

## What to tell the partner

Keep it short and specific, for example:

> We found that some footnotes in the <Deal> memo linked to sources from other sections. We've corrected the Overview, Team, Business and Fundraising sections; every footnote there now links to the source the claim came from. Why Invest, Market and Flags were edited after the memo was assembled, so we can't correct their footnotes automatically. We can regenerate those sections, or check and fix their footnotes by hand. The Executive Summary and Closing footnotes link to the same sources as before; we haven't been able to verify them.

For refused sections, the two honest fixes are: regenerate the section (its research is intact, and new runs cite correctly), or fix it with the connector's edit tools, checking each footnote against the section's research file. Don't hand-renumber.

## See also

- [[manage-memo-citations]]: where definitions live and how to add one
- [[Final-Draft-Citations-Collide-Across-Sections]]: the bug
- [[Hex-Code-Citations-and-a-Repair-Tool]]: the plan, and the `source_key()` contract
- `src/citation_repair.py`: the repair logic, importable for a connector tool

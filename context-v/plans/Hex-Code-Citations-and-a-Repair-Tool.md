---
type: Plans
title: "Hex-Code Citations, and a Tool to Repair Memos Cited by Number"
lede: "Numbered citation keys mean something only inside the section that wrote them, so stitching sections together links claims to the wrong source. Switch drafting to source-derived hex codes, as Lossless Flavored Markdown already requires, and give agents a tool and a skill to repair memos written the old way."
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
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
depends_on: [Fix-Citation-Collisions-in-Final-Assembly]
owns_test_ids: [CONN-HEX-01, CONN-HEX-02, CONN-HEX-03]
tags: [Plan, Citations, Hex-Codes, LFM, Repair, Agent-Skills]
---

# Hex-Code Citations, and a Tool to Repair Memos Cited by Number

## Why

Each section's research numbers its sources from 1. Overview's `[^25]` and Flags' `[^25]` are different sources. Final assembly treated keys as global, so every section's `[^25]` linked to whichever source was defined first ([[Final-Draft-Citations-Collide-Across-Sections]]). The assembler is fixed for new runs, but the cause is the numbering itself: a number is a position, not a source.

The decision already exists in the `lossless-flavored-markdown` skill (rule 2): inline references use hex codes like `[^1ucdcd]`, never `[^1]`, derived from the source where possible. LFM, and Pandoc in our exports, number them at render time. MemoPop never adopted it: the codified researcher, the writer and the connector's `research.section` and `draft.section` steps all still ask for `[^1]`, `[^2]`.

A sampling scan on 2026-11-21 found about 40 finished memo versions across six firm folders with citations linking to another section's source. A proof repair on one memo fixed 62 links with the prose unchanged. Memos from an older bug, where research files define one key several times, can't be repaired from their files.

## The shared function: `src/citation_keys.py`

Both parts use one function. Its contract is fixed here so two branches write the same thing:

```python
def source_key(definition: str) -> str:
    """The hex citation key for a source: same source, same key, everywhere."""
```

- Identity: the first `http(s)://` or `file://` link in the definition, percent-decoded, lowercased, trailing slash removed. With no link, the definition text with its date prefix removed, whitespace collapsed, lowercased.
- Key: `sha256(identity)`, as an integer, written in base 36 (`0-9a-z`), first 6 characters.
- `assign_keys(definitions: dict[str, str]) -> dict[str, str]` maps each old key to its hex key. If two different identities give the same 6 characters, both get 8.
- No prefixes: deck and dataroom sources get plain keys like any other (decided 2026-11-21; a `file://` link can't tell a deck from a dataroom file reliably).
- "First link" is the first bare `http(s)://` or `file://` URL anywhere in the definition, ending at whitespace, `)`, `]` or `>` (the regex in `src/citation_keys.py` on `connector/hex-citations`, commit `9b213ad`, is canonical).
- Keys are assigned once per memo, over every definition in every section, so two sections can't collide with each other.

## Part 1: the repair tool and skill (branch `fix/citation-repair-tool`)

- `cli/repair_citations.py <version-dir> [--memo 7-X.md] [--write | --out <dir>] [--export]`, promoted from the proven scratch script (`repair_memo.py`) with tests. Default is a dry run that reports; `--write` repairs in place and keeps a `.bak`; `--export` re-exports dark and light HTML and PDF.
- Repairs only what it can prove, region by region: the heading appears once, the section's research defines each key once, every cited key has a definition, and the region's markers pair one for one with the section file's. Anything else stays byte-identical and is listed in `repair-report.json` with the reason.
- Output uses hex keys from `source_key()`, so a repaired memo can't collide again. The block is the one list of sources, in first-cited order.
- Checks the prose is unchanged (markers and the block stripped) and refuses to write if not.
- `--scan <io-root>` lists every finished memo with the share of citations that link to another section's source, the way the 2026-11-21 scan did.
- Skill: `context-v/agent-skills/repair-memo-citations/SKILL.md`, beside `manage-memo-citations`. When to use, how to run a scan, dry run, write and export, what it refuses and why, what to tell the partner about refused sections (regenerate, or fix with the connector's edit tools), and why hex codes. Cross-link `manage-memo-citations`, and update that skill's "semantic rather than numeric ID naming" advice to point at hex codes.

## Part 2: hex codes going forward (branch `connector/hex-citations`)

- Local pipeline: the codified section researcher and the writer emit and cite hex keys from `source_key()`. `assemble_citations()` keeps hex keys as they are: the same source in two sections is already one key, so assembly only gathers definitions, removes duplicates and orders the block by first citation. No renumbering in markdown.
- Connector: `research.section` and `draft.section` instructions use `[^<hex>]` keys and tell Claude how to make one (the server computes and checks it). `submit_artifact`'s citation checks accept hex keys and flag a key that doesn't match its source. `compile` keeps hex keys in `memo.md`; the exports number them.
- Exports: confirm `cli/export_branded.py` (Pandoc) numbers hex footnotes in order, and that the site endpoint's markdown works with LFM's hex rendering.
- Old numbered research and sections still assemble: numbered keys are converted to hex at assembly with `assign_keys()`.

- [x] Done 2026-11-21 on `connector/hex-citations`: CONN-HEX-01..03 green, CONN-CMP-04 amended and green, API 1.9.0 ([[2026-11-21_11]]). Not changed: the Perplexity researcher, citation enrichment and the fact corrector still number keys; assembly converts them.

## Decided 2026-11-21 (operator direction: hex in markdown, numbers only at render)

- The compiled `memo.md` keeps hex keys, one per source. Exports (Pandoc) and LFM sites number them. CONN-CMP-04 changes from "consolidated and renumbered" to "consolidated, one key per source; exports number them".
- `consolidate_citations()` and `merge_duplicate_definitions()` dedupe by source and stop renumbering. A test that asserts a literal `[^1]` after consolidation changes to assert one key per source.
- `cli/utils/restore_uncited_footnotes.py` reads only `[^\d+]:` definitions: Part 2 makes it read hex keys too.

## Test IDs

| ID | Given / When / Then |
|---|---|
| `CONN-HEX-01` | Given two sections citing the same URL under different local keys, when a research step's submission is checked and the memo compiles, then both use one hex key from `source_key()`, and the compiled markdown has one definition for it |
| `CONN-HEX-02` | Given a section submitted with numbered keys, then `submit_artifact` accepts it and compile converts its keys to hex; given a hex key that doesn't match its definition's source, the check names it |
| `CONN-HEX-03` | Given the connector's `research.section` and `draft.section` instructions, then they ask for hex keys, never `[^1]` |

The repair tool's tests are pipeline tests (`tests/test_repair_citations.py`), not connector IDs.

## Then (the operator's go-ahead)

Run `--scan`, then `--write --export` on the newest finished version of each affected deal, commit each firm's changes in its own repo with a changelog note, and list the memos and sections that were refused.

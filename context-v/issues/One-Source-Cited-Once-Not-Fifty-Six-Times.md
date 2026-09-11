---
title: "One Source, Cited Once — Not Fifty-Six Times"
lede: "The exported memo lists 101 numbered sources for 17 distinct documents. The pitch deck alone appears 56 times, each as its own entry. And every one of them reads Published: N/A | Updated: N/A while the deck's own PDF metadata carries 2026-09-08."
date_authored_initial_draft: 2026-09-11
date_authored_current_draft: 2026-09-11
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-09-11
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-09-11
date_modified: 2026-09-11
tags: [Citations, Export, Footnotes, Deduplication, Dates, Analyst-Grade, Pandoc]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: ccfae7a8-68bf-4f88-b193-73248ab3c694
hex_code: zjyqnl
status: Open
severity: High
---

# One Source, Cited Once — Not Fifty-Six Times

## What the reader sees

The Citations section of an exported memo, verbatim:

```
Profile Deck. Profile Health. Published: N/A | Updated: N/A  ↩︎
Profile Deck. Profile Health. Published: N/A | Updated: N/A  ↩︎
Profile Deck. Profile Health. Published: N/A | Updated: N/A  ↩︎
Profile Deck. Profile Health. Published: N/A | Updated: N/A  ↩︎
Profile Health - Executive Summary. Profile Health. …         ↩︎
Profile Deck. Profile Health. Published: N/A | Updated: N/A  ↩︎
…
```

Twenty-six entries in the operator's screenshot; **101 in the file**. A partner
opening this counts a hundred sources and finds the same PDF over and over.

That is worse than untidy. A reference list is the one place a reader checks the
*breadth* of the evidence, and this one overstates it by six-fold while making
the real corpus impossible to see. It also makes a specific citation
unfollowable: `[^14]` and `[^51]` and `[^73]` are the same deck, so the number
carries no information and there is nothing to look up.

## The measurements

Against `ProfileHealth-v0.0.4`, 2026-09-11:

| Artifact | Entries | Distinct sources |
|---|---:|---:|
| `7-ProfileHealth-v0.0.4.md` (assembled) | **17** definitions | 17 — correct |
| `exports/dark/…html` | **101** `<li>` entries | **17** |

So the markdown is right and the export is wrong. The inline markers number 173
across the memo; the export turns marker *occurrences* into list entries.

Frequency of the worst offenders in the rendered list:

| Rendered entry | Times |
|---|---:|
| Profile Deck | **56** |
| Profile Health - Executive Summary | **22** |
| Profile Tech Architecture Overview | 6 |
| Genetic Pipeline Overview | 4 |

## Where it happens

`cli/export_branded.py` already knows this is a problem — it prints

```
Found 10 unique sources with duplicates
✓ Consolidated 55 duplicate footnotes
✓ 13 unique sources remain
```

and then emits 101 entries anyway. So there is a consolidation pass, it runs,
it reports success, and the output still carries the duplicates. Either it
consolidates a different representation than the one pandoc renders, or it runs
before the step that re-expands them. That is the first thing to establish —
the fix is not "add deduplication", it is "find out why the deduplication that
is already there does not hold".

Note the assembler is not at fault. `citation_assembly_agent` renumbers to 17
sequential definitions and the markdown proves it. The damage is downstream.

## The second defect: every date is N/A

All 17 definitions in the assembled memo read `Published: N/A | Updated: N/A`.

The deck is not undated. Its own PDF metadata:

```
creationDate: D:20260908121452-05'00'     →  2026-09-08
modDate:      D:20260908121452-05'00'
```

A dataroom document's date is available from, in rough order of trust:

1. PDF/Office metadata (`creationDate`, `modDate`) — present here and unread
2. The date stated inside the document (an executed instrument names its date)
3. The filename, where dated
4. Filesystem mtime — weakest, and wrong after any copy or normalization

None are consulted. For a memo whose whole claim is that a partner can
spot-check every number, a citation that cannot say *when* is a citation doing
half its job. It matters most for exactly the documents that carry the
deal terms: a SAFE with no date is not a citation an analyst can act on.

## The third defect, and the one that matters most

The memo cites **17 distinct documents. Every one is internal.**

```
external citations in the memo:     0
external citations in 1-research:   0
http refs in inputs/Sources.md:     13
```

`Sources.md` is in `mode: codified`, the run reported *"Codified-source mode
active — 29 hand-curated URLs"* and *"Reusing stored content for 16 source(s)"*,
and not one of them produced a citation. The curated corpus was loaded, fetched,
and then contributed nothing.

**This is not hallucination — it is the opposite, and that distinction should be
stated plainly before anyone reads the numbers above and concludes otherwise.**
No fabricated URL appears anywhere. Every claim traces to a document in the
firm's own dataroom: the deck, the executive summary, seven executed SAFEs, the
board consent, the cap table, the tech architecture overview, the genetic
pipeline overview, three competitive analyses. The closed-corpus machinery held.

What failed is corroboration. A memo sourced entirely to the company's own
materials is a memo with no independent check on anything the company says about
its market, its competitors, or its category. That is a real analytical gap and
it reads, in the reference list, as though the pipeline did no research at all.

### And seven of the sixteen paths are malformed

```
cited:   …/apps/memopop-orchestrator/inputs/ProfileHealth-Dataroom/Company Overview/Profile Deck.pdf
actual:  …/apps/memopop-orchestrator/io/humain/deals/ProfileHealth/inputs/ProfileHealth-Dataroom/Company Overview/Profile Deck.pdf
```

The `io/<firm>/deals/<deal>/` segment is missing. The file exists (2.3 MB) at the
correct path. So a reader following the link finds nothing, and anyone auditing
the memo by resolving its citations would conclude the source does not exist —
which is precisely the accusation this pipeline is built to be immune to.

Worth noting the citation formatter emits a `file://` URL at all. For a
dataroom-grounded memo that is defensible per
[[Validation-and-Fact-Checker-not-using-Research]], but an absolute path from one
developer's laptop is not a citation anyone else can follow.

## What "fixed" looks like

1. **One source, one entry, one number.** The rendered list has as many entries
   as there are distinct documents — 17 here, not 101. Every inline marker for
   the same document resolves to the same number.
2. **Identity is the document, not the string.** Two references to the same file
   under different path spellings are one source. This repo has already been bitten
   twice by matching on exact path strings — see
   [[Agent-Sequencing-For-Deals-We-Already-Have-Content-On]] for the deck cache
   and `inject_deck_images` for duplicated slides. Match on a stable key.
3. **Dates come from the document.** Read PDF/Office metadata at ingest and
   carry it on the source record, so the citation formatter has something to
   print. `N/A` should mean "we looked and there is none", not "nobody looked".
4. **A regression test on the export, not just the markdown.** Every check in
   this area tests the assembled markdown, which is why this survived: the
   markdown has been correct the whole time. Assert on the rendered HTML —
   entries equal distinct sources.
5. **Citation paths resolve.** A `file://` citation names a file that exists.
   Assert it at assembly time; a broken path is a broken citation.
6. **The curated corpus reaches the memo.** If `Sources.md` carries 13 approved
   URLs and the exported memo cites zero of them, something between fetch and
   synthesis is dropping them, and the run should say so rather than producing a
   memo that silently cites only the company's own documents.

## Verification

The same run is the regression case. On `ProfileHealth-v0.0.4`, re-exported:

- `exports/dark/*.html` contains **17** `<li id="fn…">` entries, not 101
- No rendered entry text appears more than once
- The deck's entry reads a real date, not `N/A`
- Inline `[^N]` markers still resolve — the count of distinct markers in the
  body equals the count of entries in the list

## Related

- [[Validation-and-Fact-Checker-not-using-Research]] — the other place the memo's
  citation apparatus reports a number that does not mean what it says
- `agent-skills/manage-memo-citations` — where definitions must live to survive
  assembly; the rules there are being honoured, which is why the markdown is fine
- `cli/export_branded.py` — the consolidation pass that reports success without
  achieving it
- `src/agents/citation_assembly.py` — correct; renumbers to 17 and is not the cause

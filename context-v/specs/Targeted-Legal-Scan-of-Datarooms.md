---
title: "Targeted Legal Scan of Datarooms"
lede: "Inventory every legal document. Read only the ones that state terms. A checklist is cheap; a model call is not."
date_created: 2026-08-26
date_modified: 2026-08-26
date_authored_initial_draft: 2026-08-26
date_authored_current_draft: 2026-08-26
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-08-26
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
tags: [Dataroom, Legal-Extraction, Term-Sheet, Cost-Control, Diligence-Checklist, MemoPop]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5 (1M context)"
status: Draft
---

# Targeted Legal Scan of Datarooms

## The problem, measured

The ProfileHealth run classified 158 documents and sent **109 of them** to the
terms extractor, one model call each. What those 109 actually were:

| count | type | states deal terms? |
|---|---|---|
| 76 | `charter_document` | no — incorporation certificates, bylaws, 83(b) elections, EIN letters, good-standing certificates, foreign-qualification statements |
| 15 | `stockholder_consent` | no — board and stockholder approvals |
| 10 | `purchase_agreement` | sometimes — founder restricted stock agreements state price and vesting |
| 6 | `safe_note` | **yes** |
| 1 | `term_sheet` | **yes** |
| 1 | `side_letter` | **yes** |

Eight documents carry the terms of the round. Ninety-one do not, and three of the
76 charter documents are images — a payment-confirmation screenshot and two
photographed 83(b) forms.

Two costs, and the second is worse than the first:

1. **Spend.** Roughly ten times the necessary number of calls.
2. **Noise.** Every one of those 91 is asked for `investment_amount`,
   `valuation_cap`, and `discount_rate`. Whatever they scrape flows into a single
   reconciled term set, so a dollar figure on a wire confirmation can end up
   sitting beside the actual SAFE terms with equal standing.

## The rule

**Inventory everything. Read what states terms.**

Listing a file, reading its name, noting its folder, and recording that it exists
costs nothing and is genuinely useful — a reader wants to know the 83(b)
elections are on file without anyone reading them. Opening a document and asking
a model to pull deal terms out of it is the expensive act, and it should happen
only where deal terms live.

## Tier 1 — the checklist (no model calls)

Every file in the dataroom appears here, whatever its type. For each: filename,
folder, size, extension, classified type, and whether it was readable.

Grouped into the categories a diligence reader expects, and — the part that earns
its keep — **saying which categories are empty**:

```
FORMATION                    ✓ 12 documents
  Certificate of Incorporation ✓        Bylaws ✓        EIN ✓
  Good Standing (DE) ✓                  Foreign Qualification (CA) ✓

FOUNDER EQUITY               ✓ 18 documents
  Restricted Stock Purchase Agreements ✓ 5    83(b) elections ✓ 5
  RSPA amendments ✓ 2

OPTION POOL                  ✓ 14 documents
  Stock Plan ✓        Board consents ✓ 4        Award notices ✓ 6

FINANCING INSTRUMENTS        ✓ 9 documents      ← the only tier-2 group
  SAFEs ✓ 7        Side letter ✓ 1        Board consent (ratification) ✓ 1

INSURANCE                    ✓ 4 documents
  D&O ✓        E&O ✗ not present

MISSING / EXPECTED
  ✗ No IP assignment agreements
  ✗ No employment agreements
  ✗ No board minutes
```

Absence is a finding here and nowhere else. A dataroom without IP assignments is
worth a line in a checklist; it is not an anomaly and it is not a risk paragraph
in the memo.

Written as `0-dataroom-inventory.json` and `.md`, before any extractor runs.

## Tier 2 — the read (model calls)

Only these types are opened for terms:

| type | why |
|---|---|
| `safe_note` | the instrument |
| `convertible_note` | the instrument |
| `term_sheet` | the terms, before papering |
| `side_letter` | modifies an instrument's terms; useless to log the SAFE and miss it |
| `subscription_agreement` | states amount and what is bought |
| `warrant` | states coverage, strike, term |
| `schedule_of_purchasers` | who bought what, at what price |
| `executed_financing_doc` | catch-all for a papered financing |

Explicitly **not** read for terms:

`charter_document` · `stockholder_consent` · `insurance` · `wire_instructions` ·
`investor_questionnaire` · `memo_template` · anything classified non-legal

`purchase_agreement` is the judgment call. A stock purchase agreement in a
financing states terms; a founder restricted stock purchase agreement states
founder vesting. **Route it by folder** — under `SAFEs/`, `Financing/`, or
`Transaction Documents/` it is tier 2; under `Founder docs/` or `Option Pool/` it
is tier 1. Where the folder does not say, leave it in tier 1 and list it in the
checklist as unreviewed rather than guess.

For ProfileHealth this is **9 documents, not 109.**

## Escalation, when the checklist is thin

If tier 2 finds fewer than two documents and the checklist shows a `SAFEs/`,
`Financing/`, or `Transaction Documents/` folder with contents, widen to
`purchase_agreement` and `stockholder_consent` within those folders only, and
record in the run notes that the scan was widened and why. A quiet widening that
nobody can see is how 109 happens again.

## What this does not change

- **Classification still covers every document.** Tier 1 needs a type for
  everything; the saving is in what gets *read for terms*, not in what gets
  classified.
- **Other extractors are unaffected.** Team, financials, traction, and cap table
  keep their own document sets.
- **A tier-1 document is still evidence.** A board consent ratifying the SAFEs
  belongs in the checklist and can be cited in prose. It simply is not a source
  of cap and discount.

## Acceptance

Re-run ProfileHealth:

- tier 2 opens **9 documents**, and the 7 SAFEs plus the term sheet and side
  letter are all among them
- `0-dataroom-inventory.md` lists all 158 documents with a per-category checklist
  and a MISSING section
- no `charter_document` appears in the terms output
- the terms output is **per instrument** — investor, amount, cap, discount, date —
  not one reconciled set

## Related

- `context-v/issue-resolution/Archive-Dating-And-Time-Series-Defect-Hitlist.md` — D8, the collapse of many instruments into one term set
- `context-v/reminders/Every-Step-Writes-Its-Output-To-File.md` — the checklist is written before tier 2 begins
- `context-v/reminders/Round-Closing-Timeline-Nuances.md` — absence of a document is not an anomaly

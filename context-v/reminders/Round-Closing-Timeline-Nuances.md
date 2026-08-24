---
title: "Round-Closing Timeline Nuances"
lede: "Wires arrive before and after the close they belong to, rounds close later than anyone planned, and a fund and its SPV subscribe months apart on identical terms. None of that is an anomaly. Record every date as the document states it, never revise one to make a sequence tidy, and confine anomaly-noticing to the handful of series that are actually real at this stage — money spent, web traffic, signed contracts, billed subscription revenue. Everything else is a claim or a projection, and instinctive concerns about it belong in anomalies.json rather than in the memo or the conversation."
date_created: 2026-08-24
date_modified: 2026-08-24
date_authored_initial_draft: 2026-08-24
date_authored_current_draft: 2026-08-24
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5 (1M context)
at_semantic_version: 0.0.0.1
status: Active
site_uuid: 3352b28e-51c0-457a-8d92-0b9c1dc37c0b
hex_code: 2fc7ka
summary: >-
  Guardrail born from a 2026-08-24 session in which an agent auditing the
  CogSciAI archive reported that a wire dated six days before its signed SAFE
  was evidence of a dating defect. It is not; it is how closings work. The
  operator corrected it, and the correction generalizes: early-stage closing
  mechanics look like anomalies to anyone reasoning from private-equity or
  general-business priors, and an agent applying those priors produces a memo
  that reads like a doomscroll about an investment already made. This reminder
  states which closing patterns are ordinary, forbids revising a document's
  stated date to normalize a sequence, bounds anomaly-noticing to the few
  early-stage series that have an outside referent, and gives instinctive risk
  observations a destination that is not the deliverable.
tags: [Dataroom, Round-Closing, Time-Series, Dates, Provenance, Anomalies, Agent-Discipline, Reminders]
---

# Round-Closing Timeline Nuances

## 1. Ordinary closing mechanics are not anomalies

A round is not an event with a single date. It is a window, and the paperwork,
the money, and the announcement move through that window in whatever order the
parties found convenient.

Treat all of the following as **normal**. Record the dates; say nothing.

- **A wire lands before the instrument is signed.** An investor wires against an
  agreed close and the paper is countersigned afterward. Extremely common.
- **A wire lands well after the close date.** Also common — an LP capital call
  runs slow, an operations team batches transfers, a signature page sits in
  someone's inbox.
- **The round closes later than the documents anticipated.** Term sheets and
  decks name target closes. Targets slip. A December close on an August term
  sheet is a schedule, not a red flag.
- **Rolling and multiple closes.** First close, second close, extension. Each has
  its own date and its own subscribers.
- **A fund and one or more SPVs subscribe separately**, often months apart, often
  on identical terms. CogSciAI is the worked example: Humain Ventures Fund I, LP
  at $200,000 and Humain Ventures CogScAI SPV (a Series of Decile SPV, LLC) at
  $182,000, both at a $120M post-money cap and a 15% discount, roughly four
  months apart. Two vehicles, two subscriptions, one position.
- **Executed and unexecuted copies of the same instrument coexist** in the same
  folder. A blank signature line in one copy says nothing about whether the deal
  closed.
- **A form instrument carries no date at all.** The YC SAFE reads "on or about
  \_\_\_, 2024" and that blank is frequently never filled. The absence of a date
  inside a document is not a finding.

**The folder is the unit of coherence.** If the documents sit in the same deal
folder, assume they belong to the same transaction and that their dates differ
for ordinary reasons. Log what each one says and move on.

This list is not exhaustive, and it is not meant to be. The governing instinct
is: early-stage venture is procedurally messy, and messiness read through a
private-equity, MBA, or general-business-wisdom lens looks like risk when it is
just Tuesday.

## 2. Never revise a document's date to tidy a sequence

**Record the date each document states, from the source it states it in, and
leave it alone.** Do not shift a wire date to match a close date. Do not shift an
instrument date to precede its funding. Do not pick one date and propagate it
across a folder for consistency.

The reason is not fidelity for its own sake. It is that **the correct date depends
on the question, and the question is not known at collection time.**

- **IRR.** For the fund's own return it is technically correct to run from the
  **wire date** — that is when the capital left. For the company's return it is
  technically correct to run from the **close date**. Same position, two
  defensible start dates, materially different numbers over a short holding
  period.
- **Next-round timing.** Estimating the window before the next raise is best
  anchored to the **close date** of the prior round, not to any individual wire.
- **Dilution and conversion.** A SAFE's conversion turns on the equity financing
  event, not on when the money moved or when the PDF was generated.
- **Vintage and cohort.** Which year a position belongs to can follow the close,
  the first wire, or the fund's own accounting convention.

The list of downstream nuances is longer than anyone can enumerate in advance.
That is precisely why collection must not choose. **Carry every date, labelled by
what kind of date it is, and let the analysis pick.** A collection layer that
normalizes has destroyed the information the analysis needed, and it has done so
invisibly — the surviving date looks exactly as authoritative as the one it
replaced.

See `context-v/issue-resolution/Archive-Dating-And-Time-Series-Defect-Hitlist.md`
(D1–D8) for the current gaps between this rule and the code.

## 3. `anomalies.json` — a place to put it, not a job to do

Agents notice things. Gaps in the data, claims they could not verify, numbers
that disagree, a document they expected and did not find. The instinct to report
all of it is strong and, in this domain, wrong.

**Surfacing risk is not the analyst's job.** Left unconstrained, every agent
writes down every concern it can conjure, and the operator receives a memo about
an investment they have already made that reads like a doomscroll. The
information is not valuable in proportion to its volume; it is valuable in
proportion to how surprising it is, and almost none of it is surprising.

So: `anomalies.json` exists as a **pressure valve**, and the rules around it
matter more than the file does.

### Rules

1. **Writing to it is optional and incidental.** No agent's task is "find
   anomalies." No agent should take an extra pass, re-read a document, or make an
   additional model call in order to populate it. If something surfaced while
   doing the actual work, it may be written down. If not, the correct number of
   entries is zero.
2. **Nothing in it reaches the memo.** Not as a caveat, not as a footnote, not as
   a "considerations" section. The assembly step never reads this file.
3. **Nothing in it is raised in conversation.** Do not summarize it, do not lead
   with it, do not append "I also noticed…" to a report. The operator reads it
   when the operator wants it.
4. **Ordinary closing mechanics from §1 are never anomalies.** If §1 names it,
   it does not go in the file.
5. **Absence of data is not an anomaly.** A dataroom without a cap table is a
   dataroom without a cap table. Note it in the extraction record where such
   things already live, not here.
6. **One entry per observation, stated once.** No elaboration, no recommended
   remediation, no severity inflation.

### First: most early-stage data is not real, and that is fine

Startup data is mostly bad. Early-stage venture data is mostly bad. Where it is
not bad it is usually an invented projection, and where it is neither it very
often does not exist at all. **This is the normal condition of the asset class,
not a finding.**

A short list of what tends to be *actually real* at this stage:

- **Money spent.** Burn, payroll, the bank balance. Almost always the most
  trustworthy series in the room, because someone had to move it.
- **Web traffic**, where it comes from an analytics product rather than a slide.
- **Signed customer contracts** — a countersigned document with a value on it.
- **Credit-card-based monthly subscription revenue** — Stripe-style billing
  records, where the number exists because a card was charged.

Everything else — TAM, SAM, SOM, pipeline, ARR built from a handful of LOIs,
headcount plans, the year-three revenue line, market-share estimates, the
competitive matrix — is a claim, a projection, or a marketing artifact. It may be
perfectly reasonable. It is not data, and **it is not a candidate for
`anomalies.json`.** An implausible TAM is not an anomaly; it is a deck.

**So the bounding rule is: notice things in the data that is real.** A discrepancy
in cash spent, in a signed contract value, in billed subscription revenue, or in a
cap table is worth writing down, because those numbers have an outside referent
that could settle the disagreement. A discrepancy between two projections is two
opinions, and nobody needs an agent to file it.

### What actually belongs in it

Within the real-data boundary above, things that would make a careful person go
back and look at the document again:

- Two documents making incompatible claims about the **same** instrument — the
  same SAFE, the same investor, the same vehicle, different numbers.
- An arithmetic identity that does not hold: ownership percentages that do not
  sum, a total that is not the sum of its parts, a schedule that disagrees with
  the ledger it summarizes.
- A number off by a factor consistent with a units or convention error (an 85%
  "Discount Rate" recorded as an 85% discount rather than a 15% one).
- A document whose content contradicts its own filename or metadata in a way that
  changes its meaning — "Signed" in the name, blank signature block in the text.
- A scanned or otherwise unreadable document sitting where its content would
  change one of the real numbers above.

### Shape

One file per analysis run, alongside the numbered artifacts:

```
<output_dir>/anomalies.json
```

```json
{
  "company": "CogSciAI",
  "run_started": "2026-08-24T09:12:03",
  "entries": [
    {
      "recorded_at": "2026-08-24T09:14:41",
      "slug": "cogsciai-safe-humain-fund-i-executed-flag",
      "agent": "legal_extractor",
      "source_path": "io/humain/portfolio/CogSciAI/20241213_CogSciAI_SPV--Seed/20240820_CogSciAI_SAFEHumainVenturesFundInvestment--Signed--Seed.pdf",
      "observation": "filename says executed; the signature block in the text is blank",
      "evidence": "…on or about ___, 2024…",
      "why": "whether this instrument is executed decides whether the $200,000 Fund I position is a closed subscription or an unsigned form; the cap table depends on the answer",
      "kind": "document_contradicts_metadata"
    }
  ]
}
```

**`recorded_at`** — when the entry was written, not when the document is from.
The two are unrelated and conflating them is the mistake this whole reminder is
about.

**`slug`** — a kebab-case identifier for *what the entry is about*. It is expected
to be loose at first and to become canonical over time. Coin one from whatever
you have — company, instrument, vehicle, metric — and do not block on getting it
right; the point is that the same subject observed in a later run, or in another
company's archive, can eventually be reconciled onto one slug. Nothing validates
it at write time. A slug that turns out to be a synonym of an existing one is a
reconciliation job later, not an error now.

**`source_path`** — where the file actually lives, repo-relative, not a basename.
An entry whose document cannot be located is not actionable. If the observation
spans two documents, name the one a reader should open first and cite the other
in `evidence`.

**`why`** — why this might be of concern, or merely worth noting. One sentence,
stated plainly, in terms of what it would change. This field is where the
temptation to editorialize will land, so hold it to the standard: *what decision
or number does this affect?* If the honest answer is "none," the entry does not
belong in the file.

**`evidence`** — a quotation, not a paraphrase. An entry a reader cannot check
against the document is worse than no entry.

**`kind`** — a loose grouping label, not a taxonomy to satisfy. Reasonable values
so far: `conflicting_claims`, `identity_violation`, `unit_or_convention`,
`document_contradicts_metadata`, `unreadable_source`.

Append-only within a run.

## Why this reminder exists

An agent auditing the CogSciAI archive found a wire dated 2024-08-14 and a signed
SAFE dated 2024-08-20, and reported that the money appeared to move six days
before the instrument authorising it — framing ordinary closing mechanics as
evidence of a defect. The operator's correction was immediate and general: *that
happens sometimes, people get the wire in before signing or deadline, that's
normal.*

The dating work in that audit was worth doing. The problem was the register: an
agent reasoning from outside-the-domain priors will keep finding "problems" that
practitioners recognize as routine, and each one costs the operator attention and
credibility with the tool.

The defect that survived the correction was the useful one — not that the dates
were out of order, but that the archive **cannot say what kind of date each one
is**, so a reader cannot distinguish the normal case from a real one. That is the
finding worth keeping, and it is the shape every future one should take: not
"this looks wrong," but "the system cannot tell these apart."

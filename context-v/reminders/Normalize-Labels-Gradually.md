---
title: "Normalize Labels Gradually"
lede: "One company says Total Revenue, another says Gross Revenue, a third says Top Line. One reports monthly, another quarterly, another H1/H2, another only annually. Collection never touches any of it. Normalization is a later, corpus-level act — a cluster of labels that mean the same thing, one chosen default, and an alias map — built by a person from real analysis across real portfolios, never by an agent guessing from what the words sound like."
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
site_uuid: 3561e0be-8f66-4b6d-8da9-27945fb6cb9f
hex_code: l3njpm
summary: >-
  Companion to Round-Closing-Timeline-Nuances. Where that reminder governs dates,
  this one governs labels and grains. A company's choice of metric name and
  reporting period is part of how it represents itself, and an agent that
  "helpfully" renames Top Line Revenue to revenue, or interpolates a quarterly
  figure into three months, has destroyed evidence and made an inference
  indistinguishable from a source's own claim. The canonical vocabulary the
  portfolio eventually needs is real and worth building — but it is built by a
  person from accumulated observation across many portfolios, expressed as an
  alias map over untouched raw labels, and applied as a view rather than a
  rewrite. No agent relabels source data, and no agent edits the registry as a
  side effect of a run: a model is equally confident that Top Line means Revenue
  and that Bookings does, and only one of those is true.
tags: [Time-Series, Metrics, Labels, Normalization, Taxonomy, Collection-Layer, Agent-Discipline, Reminders]
---

# Normalize Labels Gradually

## 1. Carry the label the company used

**A metric is recorded under the name its source gave it. Always. Without
exception at collection time.**

These are all the same idea, and all of them are correct as written:

`Total Revenue` · `Gross Revenue` · `Top Line Revenue` · `Revenue` · `Net Sales` ·
`Total Net Revenue` · `Sales`

An agent that maps them onto a house term has thrown away three things:

1. **Evidence.** Which words a company chooses is a fact about the company. A
   team that reports "Bookings" where its peers report "Revenue" has told you
   something, and the collection layer is where that survives or dies.
2. **Traceability.** A reader who finds `revenue` in a CSV and cannot find that
   word anywhere in the source document has no way to check the number.
3. **The distinction between reading and inferring.** Once a renamed label sits
   in a column, it is indistinguishable from a stated one. This is the same
   failure mode as a normalized date: the substituted value looks exactly as
   authoritative as the thing it replaced.

The company is representing itself. Do not interfere with that.

**This applies within a single company too, not just across them.** In the
Unnatural Products operating model, the `HistIS` sheet says **`Total Revenue`**
and the `Model` sheet says **`Revenue`** — same workbook, same author, same
series, two labels. Both were carried through unchanged, which is correct, and
the divergence is now visible instead of silently smoothed away.

## 2. Carry the grain the company used

The same rule, applied to time.

One company reports monthly. Another reports quarterly. Another reports H1/H2.
Another produces a single annual figure and nothing else. Some produce several at
once — the Unnatural Products model states monthly columns *and* a `Full Year`
column per year, and both were written, to the monthly grid and the annual grid
respectively.

- **Write each figure to the grid matching the periodicity it was stated in.** A
  Q2 2025 number is a Q2 2025 row. It is not three monthly rows.
- **Roll up, never down.** Monthly may be aggregated into quarterly and annual
  and marked `is_rolled_up`. The reverse is forbidden — splitting a quarterly
  figure across three months invents a seasonality the company never reported,
  and once written it is indistinguishable from data.
- **A company that only reports annually gets an annual series.** That is not a
  gap to be filled. It is what they said.

Reporting cadence is also self-representation. A company that moved from annual
to monthly reporting between two decks has told you something about its own
operating maturity, and forcing both onto one grain erases it.

## 3. Normalization is a later act, and a corpus-level one

None of the above says the portfolio should live forever in a hundred dialects.
It says the canonical vocabulary is **downstream**, and is **earned**.

The sequence:

1. **Collect raw.** Every label as stated, every grain as stated. Many companies,
   over time.
2. **Observe the clusters.** After enough archives, the synonyms declare
   themselves. You will not have to guess that `Top Line Revenue` and
   `Total Revenue` are the same thing; you will have seen twelve companies use
   six words for it.
3. **Choose one default** per cluster — the column name analysis reaches for.
4. **Map, do not replace.** The default is a **view over** the raw labels, never
   a rewrite of them. The raw label stays in the row it came from, forever.

Why gradually, and not up front: a taxonomy designed before the evidence will be
wrong in the expensive direction. It will collapse distinctions that turn out to
matter — `Bookings` versus `Revenue`, `ARR` versus `Run-Rate Revenue`, `Gross
Revenue` versus `Net Revenue` after channel fees — and those collapses are
invisible once made. Designing late costs a join. Designing early costs the
distinction itself.

A cluster is allowed to stay unresolved. "We have seen these four labels and have
not decided whether they are one thing" is a legitimate and honest state, and far
better than a premature merge.

### Who does this, and who does not

**The clustering comes from real analysis across real portfolios over time. It
does not come from a model's sense of what words mean.**

That distinction is the whole point of this section, so it gets rules:

1. **No agent relabels source data. Ever.** Not at collection, not at assembly,
   not "just for this join," not when two files refuse to line up. If a rename
   would make the output nicer, the answer is that the output is telling you
   something true.
2. **No agent authors or edits the registry** as a side effect of a run. It is a
   maintained human artifact. A run that quietly added `Bookings` to the
   `total_revenue` cluster would be indistinguishable from one that did not, and
   every analysis afterward would be wrong in a way nobody could see.
3. **An agent may propose; it may not decide.** Surfacing "these six labels
   appeared across these four archives and are not in the registry" is genuinely
   useful. Merging them is not the agent's call.
4. **A model's semantic intuition is the wrong instrument here**, and dangerously
   so, because it is *equally confident on the easy cases and the fatal ones*. It
   will tell you `Top Line Revenue` means `Total Revenue` — correct — in exactly
   the same tone it tells you `Bookings` means `Revenue`, or that `ARR` and
   `Run-Rate Revenue` are interchangeable, or that a `Gross Revenue` net of
   channel fees is the same line as one that is not. Those merges destroy money.
   Fluency about vocabulary is not evidence about accounting.

What counts as evidence for a merge is having watched the same underlying
quantity reported under different names across companies, and having a reason —
a reconciliation, a definition stated in a document, an operator who knows the
firm — to believe they are the same line. Not a plausible-sounding synonym.

## 4. What the cluster looks like

A registry, maintained deliberately by a person as evidence accumulates, living
beside the corpus rather than inside any one company's output. It is edited the
way a schema is edited — on purpose, with a reason recorded — never as a
by-product of processing an archive:

```yaml
- canonical: total_revenue
  aliases:
    - Total Revenue
    - Gross Revenue
    - Top Line Revenue
    - Revenue
    - Net Sales
  notes: >-
    "Net Sales" may be net of returns/allowances. Kept in this cluster
    provisionally; split if a company reports both.
  status: provisional

- canonical: security_class
  aliases:
    - security_class
    - share_class
    - Share Class
  notes: >-
    Our own two names for one thing — the spec says security_class, the
    extraction schema says share_class. Fix the code, keep both as aliases
    for archives already written.
  status: settled
```

Three properties that matter more than the format:

- **`status`** distinguishes a settled cluster from a provisional one. Analysis
  can choose to use only settled clusters.
- **`notes`** carries the reason a cluster is drawn where it is, especially the
  hesitations. A cluster with no recorded doubt is usually a cluster nobody
  thought about.
- **Aliases are additive.** A new archive contributes labels to the registry; it
  never causes a rewrite of what earlier archives recorded.

This is the same discipline as the `slug` field in
`Round-Closing-Timeline-Nuances.md` §3 — coin loosely, converge later, never
block collection on a naming decision.

## 5. What this costs, and where to pay it

Refusing to normalize has a real price, and it should be paid in the right place.

Concretely, from the Unnatural Products run: concatenating the historical and
forecast grids and filtering `metric == 'Revenue'` silently returns **only the
projection half**, because the historical sheet calls it `Total Revenue`. A reader
gets a clean-looking answer that is missing five years of actuals, with no error
and no warning.

That is the correct behaviour of the collection layer and an unacceptable
experience for the reader. The fix belongs in the **read** path, not the write
path:

- The generated `README.md` should list metric names that appear in some files of
  a run and not others — the information is already in hand at write time. Filed
  as **T9** in `context-v/issue-resolution/Archive-Dating-And-Time-Series-Defect-Hitlist.md`.
- Once the registry in §4 exists, an optional `canonical_metric` column can be
  written *alongside* `metric` — derived, never authoritative, and blank where no
  settled cluster covers the label.

Never fix it by renaming at write time.

## Why this reminder exists

The time-series spec already states the rule — *"named as the source names it,
never renamed to a canonical vocabulary — that is an analysis decision"* — and the
first live run confirmed the analyst honours it. This reminder exists because the
rule is counterintuitive under pressure: the moment two files will not join
cleanly, renaming looks like the helpful thing to do, and it is precisely then
that it is most destructive.

It also exists to say the other half out loud. "Never normalize" read alone
becomes an excuse for a corpus nobody can query. The instruction is not *never*.
It is **not yet, not here, and not by overwriting** — the vocabulary is real,
it is worth building, and it gets built from evidence rather than from a
whiteboard.

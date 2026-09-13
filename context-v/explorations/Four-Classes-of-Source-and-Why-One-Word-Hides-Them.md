---
title: "Four Classes of Source, and Why One Word Hides Them"
lede: "A memo that cites the company's own deck forty times and nothing else looks, in the reference list, exactly like a memo with forty sources. Until a source record says whose evidence it is, no gate downstream can tell the difference — and none of ours did."
date_authored_initial_draft: 2026-09-12
date_authored_current_draft: 2026-09-12
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-09-12
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Exploration
date_created: 2026-09-12
date_modified: 2026-09-12
tags: [Sources, Provenance, Independence, Citations, Codified-Mode, Research-Agent, Trust]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: 3f04e39c-f82f-4643-945d-35c5b5b5d6c4
hex_code: 3fk0d3
status: Exploration
---

# Four Classes of Source, and Why One Word Hides Them

## What happened, in one paragraph

ProfileHealth v0.0.4 shipped with seventeen distinct sources. Every one was a
`file://` path into the company's own dataroom — the deck, the executive summary,
the SAFEs, three competitive analyses the company itself authored. Zero external
URLs. The curated source list the researcher was permitted to draw from
contained, on inspection, sixteen entries and not one `http`.

Nothing was fabricated. The closed-corpus machinery worked exactly as designed.
The failure was that **a corpus consisting entirely of the subject's own claims
was indistinguishable, to every part of the system, from a researched one.** The
run printed `Codified-source mode active — 29 hand-curated URLs`, and the word
"sources" carried the deception, because "source" meant only "a thing with a URL
we are allowed to cite."

## The proposal

Four classes, named for whose evidence the source is:

| Class | What it is | Independence |
|---|---|---|
| **DataroomSources** | Materials in the dataroom, about the company, by the company | None. The subject speaking about itself. |
| **ProvidedResearchSources** | Third-party research the company handed us | Partial. Independent author, selected by the subject. |
| **OurResearchSources** | Third-party research our team found and vetted | High. Independent author, independent selection. |
| **AgentResearchSources** | Web search performed by an agent during a run | Unvetted. Independent author, machine selection, no human judgement yet. |

The axis is **independence from the subject** — how far the evidence sits from
the party whose claims it is being used to support. That is the thing an analyst
is actually weighing when they scan a reference list, and it is the thing the
system currently cannot represent.

## Why `origin` is not already this

`curation.source_file.SourceEntry` has:

```python
origin: str = ""    # searxng | perplexity | analyst-paste | pack | inbox
```

That is a real provenance field and it is genuinely useful, but it answers
*which mechanism delivered this to us*. Two sources with `origin: analyst-paste`
can be a Gartner report an analyst found and a PDF the founder emailed over.
Same origin, opposite epistemic weight.

The four classes are orthogonal to `origin`. A DataroomSource can arrive by
`pack` or by `inbox`; an OurResearchSource can arrive by `searxng` or
`analyst-paste`. Keeping `origin` and adding a class is right; overloading
`origin` to mean both would reproduce the problem one field lower.

`sensitivity: citable_externally` is likewise adjacent and different — it governs
whether a source may leave the building, not how much it proves.

## What a class would let the system do that it cannot today

This is the part worth arguing about, because the value is entirely downstream.

**Refuse to ship a monoculture quietly.** A run whose approved corpus is 100%
DataroomSources should say so at the top, in the terms that matter: *"this memo
will contain no independent corroboration."* Today nothing can compute that
sentence, because nothing knows the difference. Whether that is a warning or a
hard halt is a real question — a `justify`-mode memo for an existing portfolio
company may legitimately be dataroom-only, while a `consider`-mode memo probably
should not be.

**Let the fact-checker weight its evidence.** The verification gate currently
treats every source as equally probative. "The company says its TAM is $38B,
sourced to the company's market-size deck" should not verify the same way as the
same number sourced to an analyst report. The class is exactly the signal that
distinction needs.

**Let the scorecard see thin evidence.** A dimension scored 4/5 entirely on
DataroomSources is a different assertion from one scored 4/5 on
OurResearchSources, and the scorecard has no way to know.

**Render citations honestly.** A reference list could group by class, so a reader
sees at a glance that the market section rests on the company's own materials.
That is the cheapest version of this change and possibly the most valuable — it
puts the judgement in the reader's hands without the system having to make it.

**Make `AgentResearchSources` promotable rather than trusted.** The distinction
between what an agent found and what a human approved is the whole content of
the curation halt. Today that lives in `verdict: approved` on a flat list;
making it a class transition — AgentResearchSources becomes OurResearchSources
when a human signs off — states the workflow in the data model rather than in a
convention.

## The tensions worth resolving before building

**Is this a taxonomy or a lattice?** A competitive analysis authored by a third
party, sitting in the dataroom, is simultaneously Dataroom and ProvidedResearch.
ProfileHealth has several. If the classes are exclusive, that document forces a
judgement call at ingest; if they compose, downstream consumers need a rule for
what to do with the union. The exclusive version is simpler and probably right —
"where did we get it" (dataroom) and "who wrote it" (third party) may want to be
two fields rather than one class.

**Who assigns the class, and when?** Dataroom ingest can assign DataroomSources
mechanically. AgentResearchSources is equally mechanical. The two middle classes
require a human to say "the company sent me this" versus "I went and found this"
— and that distinction is invisible by the time a file is on disk. It may need
capturing at the moment of acquisition, which is a workflow change, not a schema
change.

**Does the class survive a re-run?** Everything in this pipeline that was keyed
on a path or a filename has broken at least once. A class needs to live on the
source record, travel with the citation, and be re-derivable if lost.

**What about the memo's own prior versions?** v0.0.3 cited things. Are those
OurResearchSources by virtue of having been vetted once, or do they re-enter
unclassified? The cross-run curation work has a view here worth reconciling with.

## The narrower fix this does not replace

None of the above changes the immediate defect, which is that codified mode and
web research are mutually exclusive and nothing says so. `aggregate_sources`
exists to harvest broad-search URLs and halt for curation; in codified mode the
halt is skipped because the list is treated as final. A `Sources.md` that is
entirely `file://` is therefore a closed corpus that closed before anything got
in.

That is fixable in an afternoon and does not need a taxonomy: warn when the
approved set has no external members, and make the path from "unvetted web
results" to "approved corpus" runnable on an existing deal rather than only at
first generation. The four classes make the warning *precise* — but the warning
is the urgent half.

## Related

- [[One-Source-Cited-Once-Not-Fifty-Six-Times]] — the reference list that
  triggered this, and its 101-entries-for-17-sources rendering
- [[Validation-and-Fact-Checker-not-using-Research]] — the gates that would
  consume the class, and currently cannot tell a dataroom path from a URL
- `context-v/explorations/Curating-only-valid-Sources-across-Runs.md` (parent
  repo) — cross-run source curation, which needs a view on whether a class
  survives promotion
- `src/curation/source_file.py` — `SourceEntry`, where `origin` and
  `sensitivity` already live and where a class would sit beside them
- `AGENTS.md` §2 — closed-corpus citation, which this refines rather than
  replaces: the corpus was closed correctly and was simply empty of everything
  except the subject

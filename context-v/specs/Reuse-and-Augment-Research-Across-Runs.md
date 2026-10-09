---
title: "Reuse and Augment Research Across Runs"
lede: "Running a deal again should cost only what changed: reuse every settled search and synthesis, and research only what is new."
date_created: 2026-10-08
date_modified: 2026-10-08
date_authored_initial_draft: 2026-10-08
date_authored_current_draft: 2026-10-08
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-10-08
at_semantic_version: 0.0.1.0
usage_index: 1
publish: false
category: Specification
tags: [Research-Reuse, Search-Ledger, Change-Detection, Codified-Sources, Thesis-Frame, Pipeline-Cost]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5.5"
site_uuid: 76e17504-f1b4-42eb-86e5-be08b34cb2e4
hex_code: 41a8r8
status: Implementing
summary: >
  Spec of record for how the orchestrator decides, stage by stage, whether to reuse
  prior research or do new work. Defines the deal-level search ledger
  (inputs/research-ledger.json), input fingerprints for the company-research,
  competitive and codified section-research stages, the augment-only rule for
  net-new sources, the per-run reuse report, and the operator overrides. Builds on
  the open issue Agent-Sequencing-For-Deals-We-Already-Have-Content-On; `--from
  <stage>` remains that issue's job and is deferred here.
---

# Reuse and Augment Research Across Runs

## Why care?

The expensive part of a memo is not the writing. It is reading the dataroom, searching
the web, fetching sources and synthesizing them into research. Once that is done for a
deal, it stays true until something new arrives. A new document, a new source, a new
question from the operator, a funding round that moved.

Today the orchestrator forgets that. On 2026-10-08 a thesis-frame run on ImpulseLabs
re-ran six company web searches it had run the day before. It re-synthesized research
for every section, including four the frame had explicitly marked `research: reuse`. In
one of them (Fundraising Round) the regenerated file came back 27% shorter than the one
it replaced. The run did the most expensive work again and lost content doing it.

The rule this spec establishes:

> **Running a deal again reuses everything already settled, and augments it with only
> what is new.**

## What already works, and what does not

| Stage | Behaviour before this spec | Cost |
|---|---|---|
| Dataroom parsing | Reuses the prior version's analysis unless the documents changed (`_reusable_dataroom_analysis`) | heavy |
| Per-source fetch and fact extraction | Reuses content stored in `inputs/sources/` and extracts already on file | heavy |
| Deck analysis | Content-hash cache; orphaned when a deck is only compressed (see the issue) | heavy |
| Company web research (`research_agent_enhanced`) | Re-runs every search and the synthesis call, every run | medium |
| Competitive research and evaluation | Re-runs query generation, searches and evaluation, every run | heavy |
| Codified section research | Re-synthesizes every section, every run, and overwrites | heavy |

The first two already follow the rule. This spec brings the last three into line and gives
web searches the same durable memory that fetched sources already have.

## Design

### 1. The search ledger — `inputs/research-ledger.json`

A deal-level file next to `Sources.md`, version-independent like `inputs/sources/`. Every
web search any agent runs is recorded once:

```json
{
  "entries": [
    {
      "key": "company_research::lambda gpu cloud series e valuation",
      "agent": "company_research",
      "query": "Lambda GPU cloud Series E valuation",
      "provider": "tavily",
      "run": "LambdaLabs-v0.0.1",
      "searched_at": "2026-10-08T14:02:11",
      "ttl_days": 7,
      "results": [{"title": "...", "url": "https://...", "content": "..."}]
    }
  ]
}
```

- **Before any search** an agent looks up `agent::normalized-query`. A hit younger than its
  TTL returns the stored results and makes no API call. A miss runs the search and records it.
- **TTL by topic.** Queries about funding, valuations, rounds, news, announcements or a
  recent year go stale in 7 days. Everything else (founders, technology, market structure,
  science) lasts 90 days. `MEMOPOP_SEARCH_TTL_DAYS` overrides both.
- **New questions run naturally.** A frame's questions or changed deal notes produce new
  query strings, which miss the ledger and execute. That is how a re-run augments.
- **`Research-Ledger.md`** is rendered beside it for humans: one row per search, newest first.

### 2. Input fingerprints, stage by stage

Each stage that does real work records a fingerprint of the inputs that determine its
output. On the next run, the stage compares the current fingerprint with the latest prior
version's. Equal means reuse; different means do only the new part.

| Stage | Fingerprint inputs | Unchanged | Changed |
|---|---|---|---|
| Company research | The query list, and the URLs each query returned (from the ledger) | Copy the prior `1-research.json`; no synthesis call | Synthesize as today, over ledger results |
| Competitive research | Company description, known competitors, search variants, outline | Copy the prior candidate set and query list | Run as today; its searches go through the ledger |
| Competitive evaluation | The candidate set | Copy the prior evaluation | Run as today |
| Section research (codified) | Per section: section filename, plus each usable source's URL and a hash of its stored content | Copy the prior section research file; no synthesis call | See §3 |

The prior version is found with `version_seed.previous_version_dir()`. Fingerprints for
section research live in `1-research/_fingerprints.json`. Stage fingerprints for company
and competitive research are stored inside their own JSON artifacts as `inputs_fingerprint`.

### 3. Augment, do not regenerate

For codified section research, the comparison is by source set:

- **Only additions** (every prior source is still present, and some are new): synthesize
  over the **new sources only**, and append the result to the prior research file under a
  stamped block: `<!-- research-block: augment run=<version> added=<date> sources=<n> -->`.
  Nothing already recorded is rewritten. This reuses the stamping in `research_append.py`.
- **Removals or changed content** (a source was rejected, or its stored text changed):
  re-synthesize the section in full. This is the only path that replaces a research file,
  and the reuse report says so.
- **No prior file**: synthesize as today.

### 4. Frames

- `research: reuse` is a **hard skip**: the prior file is carried forward untouched. The
  section is never re-synthesized, regardless of fingerprints.
- `research: extend` keeps its existing behaviour (frame evidence and questions, appended
  under the frame's stamp).
- `research: refresh` re-synthesizes, as its name says.

### 5. The reuse report — `0-reuse-report.md`

Every gate writes one line to the version directory's `0-reuse-report.md` (and prints it):
the stage, the decision (`reused`, `augmented`, `regenerated`, `ran`), and why. For example:
"`section 06-fundraising-round: reused — 26 sources unchanged since LambdaLabs-v0.0.1`".
The operator reads one file to see what a run actually spent effort on.

### 6. Overrides

| Flag | Effect |
|---|---|
| `--fresh` | Ignore all prior artifacts and the ledger's TTL; regenerate everything (unchanged meaning) |
| `--refresh-searches` | Ignore the ledger's TTL for this run (every search executes and is re-recorded); syntheses still reuse when their inputs come out the same |

## Out of scope here

- **`--from <stage>`**: skipping stages outright rather than letting each gate decide.
  Still wanted; it remains the job of
  [[Agent-Sequencing-For-Deals-We-Already-Have-Content-On]]. With every heavy stage gated,
  an unchanged stage now costs a fingerprint comparison rather than its full work, which
  makes `--from` a convenience rather than a necessity.
- **Deck cache and asset normalization**: described in the same issue; untouched here.
- **Downstream prose agents** (link enrichment, citations, fact correction) editing
  sections a frame marked `prose: unchanged`. A separate defect, observed on the same
  2026-10-08 run.

## Acceptance

1. Re-running a deal with no input changes makes **no** web searches and **no** research
   synthesis calls; every gate reports `reused`.
2. Adding one source to `Sources.md` re-synthesizes **only** the sections it is tagged for,
   and appends to them; every other section reports `reused`.
3. A frame with `research: reuse` on a section leaves that section's research file
   byte-identical to the prior version's.
4. `--fresh` behaves exactly as before this spec.
5. The ledger and the reuse report are human-readable without opening code.

## Implementation (2026-10-08)

| Piece | Where |
|---|---|
| Search ledger, TTLs, `cached_search` | `src/research_ledger.py` |
| Fingerprints, prior-artifact lookup, reuse report | `src/reuse_gate.py` |
| Augment append (`frame=augment` stamp) | `src/research_append.py` → `append_augmentation` |
| Section research gate | `src/agents/codified_section_researcher.py` → `_reuse_or_augment` |
| Company research: ledger + gate | `src/agents/research_enhanced.py` |
| Competitive research and evaluation gates | `src/agents/competitive_landscape_researcher.py`, `competitive_landscape_evaluator.py` |
| `--refresh-searches` | `src/main.py` (sets `MEMOPOP_REFRESH_SEARCHES`; `--fresh` implies it) |
| Tests | `tests/test_reuse_and_ledger.py` |

Versions written before this change carry no fingerprints. Their first re-run
treats a section's sources as covered when the prior research file already cites
them, and augments with the rest. Company and competitive research run once more
to record a fingerprint, then reuse from the following run on.

## Related

- [[Agent-Sequencing-For-Deals-We-Already-Have-Content-On]]: the issue this answers in part
- [[Thesis-Frames-And-The-Re-Angle-Run]]: research directives and the append stamp
- `src/research_append.py`, `src/version_seed.py`, `src/curation/sources_md.py`

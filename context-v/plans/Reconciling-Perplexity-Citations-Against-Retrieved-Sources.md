---
title: "Reconciling Perplexity Citations Against Retrieved Sources"
lede: >-
  Sonar hands us the sources it actually retrieved on every call, and we throw them away — so every URL in every memo is a guess.
date_authored_initial_draft: 2026-08-20
date_authored_current_draft: 2026-08-20
date_authored_final_draft:
date_first_published: 2026-08-20
date_last_updated: 2026-08-20
date_created: 2026-08-20
date_modified: 2026-08-20
at_semantic_version: 0.0.0.2
status: Partially-Shipped
publish: true
category: Plan
tags:
  - Anti-Hallucination
  - Source-Validation
  - Citation-Discipline
  - Perplexity
  - Provenance
  - Retrieval-Augmented-Generation
  - MemoPop
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5
site_uuid: b81bfb98-418e-43e3-b24e-629c4517826b
hex_code: d4d1cb
---

# Reconciling Perplexity Citations Against Retrieved Sources

## Why Care?

Memos come out of this pipeline reading well. The prose is good, the structure
follows the outline, the argument lands. And then the sourcing doesn't survive
contact with a partner who clicks a footnote.

The reason turns out to be small, specific, and entirely fixable: **every Sonar
response already tells us which sources it actually retrieved, and the pipeline
has never once read that field.** Instead, the system prompt asks the model to
*type out* URLs, titles, and publication dates — which is to say, it asks a
language model to recall strings from memory and then presents the result as a
citation. Plausible-looking fabrications are not a surprising outcome of that
design; they are the expected one.

This plan does not touch the prose. Sonar's writing is why we use it, and the
outline adherence is genuinely good. It replaces only the citation *apparatus*,
rebuilding it from retrieved facts instead of generated tokens.

## The finding

Ten call sites across seven files construct a Perplexity client and call
`chat.completions.create(model="sonar-pro", ...)`. Every one of them reads
exactly one thing:

```python
research_content = response.choices[0].message.content
```

A live probe of the API on 2026-08-20 confirms what else is in that response:

```
TOP-LEVEL KEYS: ['choices', 'citations', 'created', 'id', 'model', 'object',
                 'search_results', 'service_tier', 'system_fingerprint', 'usage']
```

- **`citations`** — a flat list of the URLs Perplexity actually retrieved.
- **`search_results`** — per source: `url`, `title`, `date`, `last_updated`,
  `snippet`, `source`.

`search_results` carries precisely the fields the house citation format needs,
already correct, on every single call. A `grep` for `.citations` or
`search_results` across `src/` returns **zero hits**.

Meanwhile `PERPLEXITY_RESEARCH_SYSTEM_PROMPT` instructs:

```
[^1]: YYYY, MMM DD. [Source Title](https://full-url.com). Publisher. Published: YYYY-MM-DD
```

That is an explicit instruction to generate a URL, a title, and a date. Even
when the model gets the URL right, the title and date beside it are invented
independently — so citation metadata drifts even on genuine sources.

### Three secondary holes

1. **403 is whitelisted.** `remove_invalid_sources.py` sets
   `POTENTIALLY_VALID_CODES = {401, 403, 429, 500, 502, 503}` and keeps them.
   A fabricated path on `bloomberg.com` or `gartner.com` returns 403, not 404 —
   so the most authoritative-*looking* fabrications are exactly the ones that
   survive the gate. [[Faked-Sources-from-Perplexity]] logged 18× 403 against
   8× 404 on a single memo.
2. **`preferred_sources` is decorative.** The `perplexity_at_syntax` and
   `domains.include/exclude` blocks sit in all 20 outline sections and never
   reach the API. `research_enhanced.py:44` admits it in a comment. No
   `search_domain_filter`, no `search_recency_filter`, no `web_search_options`
   anywhere in the codebase.
3. **Disambiguation excludes are advisory.** Wrong-entity domains are excluded
   by asking the model "If a search result comes from one of those domains,
   SKIP IT entirely" in prose, rather than via `search_domain_filter`, which
   would exclude at the retrieval layer where it cannot be ignored.

The existing validation gate is genuinely good — hallucination-regex preflight,
live HTTP, body-sniff for soft-404s and paywall stubs, gated-publisher
allowlist. It is a strong net under a leaky pipe. The fix belongs upstream.

## The approach: reconcile, don't regenerate

Prose is left exactly as written. Citation definitions are rebuilt against the
retrieved-source array, per citation:

| Case | Action |
|---|---|
| URL was genuinely retrieved | Keep the URL; overwrite title + dates with ground truth |
| URL was never retrieved | **Substitute** the retrieved source that best supports the claim |
| No retrieved source supports the claim | **Drop** the citation *and* its inline markers |
| `[^deck]`, `[^dataroom]`, `[^internal]` | Protected — never touched |

### The invariant that makes this usable

> **Never orphan an inline marker.**

A `[^7]` in prose with no `[^7]:` definition is the single thing that makes
these memos miserable to hand-edit — the markdown standard is excellent for
export and punishing for manual repair. So a citation is either rewritten,
substituted, or removed *along with every one of its markers*. Prose words are
never rewritten; only marker removal and whitespace tidying touch the body.

This is what makes the fix compatible with a same-day memo run: the output
needs no hand-editing pass to be internally consistent.

## Implementation

### Phase 1 — provenance capture and reconciliation (this plan)

New module `src/agents/perplexity_sources.py`:

- `call_sonar(client, **kwargs) -> SonarResult` — drop-in replacement for
  `client.chat.completions.create(...)`, returning `.content`,
  `.search_results`, `.citations`. Synthesizes minimal records from `citations`
  when `search_results` is absent.
- `reconcile_citations(content, search_results) -> (content, ReconcileReport)`
  — the table above.
- `record_provenance()` / `load_provenance()` — a `.provenance.json` sidecar in
  `1-research/`, so downstream validation can tell a real-but-bot-blocked
  source from a fabricated one.

Substitution matching is deterministic token overlap between the **claim
sentence** and the source's `title` + `snippet` — no extra LLM call, which
keeps it fast and cheap enough to run inline.

Four calibration decisions came out of testing and are worth recording, because
the first three were wrong on the first attempt:

- **Claim context is scoped to the sentence, not a character window.** A 400-char
  window bleeds tokens in from neighbouring claims, which made an unsupportable
  claim look supported by whatever preceded it. Substitution stopped
  discriminating entirely.
- **House citation style puts the marker *after* the terminator**
  (`"Market size is $50B. [^1]"`). A naive backward walk to the last `". "`
  therefore lands *past* the end of the claim and returns empty context — which
  swung the reconciler from too-permissive to dropping everything.
- **Best score wins outright, reused or not.** Preferring not-yet-used sources
  was tried, and it mis-assigned claims to merely-unspent sources. Duplicate
  URLs across two keys are consolidated downstream by `citation_assembly_agent`.
- A substitution requires **both** a ratio floor (`0.20`) and an absolute
  overlap floor (`2` shared meaningful tokens). A high ratio on a one-word
  coincidence is noise, and undiscriminating substitution is *worse* than none:
  it launders a fabricated URL into a confidently-wrong real one and defeats the
  fact-checker downstream.

**Wiring (research stage only, deliberately):** `perplexity_section_researcher`
(both the main and retry calls) and `citation_enrichment`. Citations are *born*
in `1-research/`; everything downstream inherits them. Scope was held here
rather than swept across all ten call sites because this lands the day before a
memo batch — blast radius is the constraint.

### Phase 2 — close the 403 hole

Consult the provenance sidecar in `remove_invalid_sources.py`: a 401/403 URL
counts as potentially-valid only if it appears in the retrieved set. Absent
sidecar ⇒ current behavior, so the change is backward-compatible.

### Phase 3 — enforce source preferences at the API layer

Plumb the already-authored `preferred_sources.domains` into
`search_domain_filter`, add `search_recency_filter` and
`web_search_options.search_context_size`, and move `disambiguation_excludes`
from prose instruction to API-level exclusion.

### Phase 4 — prompt surgery

Strip the `[Source Title](https://full-url.com)` instruction from
`PERPLEXITY_RESEARCH_SYSTEM_PROMPT`. Once reconciliation is authoritative, the
model should emit markers and prose only, and stop being asked to invent
bibliographic metadata at all.

### Phase 5 — surface it to the analyst

The reconcile report (`N verified, N substituted, N dropped`) is the honest
per-section trust signal, and it currently dies in stdout. It belongs in the
MemoPop native UI next to each section — the user-facing half of this problem
is that the pipeline is hard to steer, not just that sources are weak. See
[[Grill-Me-Per-Section-User-Input-Moment]] for the interaction precedent.

## Relationship to prior work

This is a pragmatic slice of direction #1 in the orchestrator's `CLAUDE.md` —
splitting retrieval from generation. The full
[[Separating-Retrieval-from-Generation-in-Agent-Pipelines]] target has a Source
Harvester emitting a validated corpus and a Section Writer that never holds a
search tool. That remains the destination.

Reconciliation gets most of the benefit without the topology change: the writer
still generates URLs, but nothing it generates survives contact with the
retrieved set. It is a **structural** defense rather than a filtering one —
fabricated URLs stop being *possible* rather than being *caught* — which is the
distinction [[Trustworthy-Citations-Source-Harvester-Rollout]] argues has been
missing from every previous attempt.

Related: [[Faked-Sources-from-Perplexity]] (the original symptom log),
[[Preventing-Hallucinations-in-Memo-Generation]],
[[Anti-Hallucination-Source-Validation-and-Removal]],
[[Curating-only-valid-Sources-across-Runs]] (the residue-catching safety net
this reduces the need for).

## Status

- **Phase 1 shipped.** Module written, unit-verified, and wired into
  `perplexity_section_researcher` (main + retry calls) and
  `citation_enrichment`. Metadata correction, substitution,
  drop-with-marker-removal, and protected-key passthrough all behave; the
  no-orphan invariant holds. Full suite green (169 passed, 1 skipped).
- **Live smoke test** on a real Sonar research call (Ramp, Market Context, 20
  retrieved sources): 7 of 7 cited URLs were genuinely retrieved, and **5 of
  those 7 carried wrong titles or publication dates**, all corrected from
  ground truth. Metadata drift is therefore not an edge case — it was affecting
  the majority of otherwise-legitimate citations, silently.
- Phases 2, 3, 4, 5 open — tracked at
  <https://github.com/lossless-group/investment-memo-orchestrator/issues/26>.

## Remaining risk

Substitution can still attach a real source to the wrong claim when several
retrieved sources share vocabulary — observed in testing on two same-company
funding rounds. The downstream fact-checker is the backstop, and the reconcile
report makes the substitution auditable. Worth revisiting if the rate is high
on real memos; an embedding-similarity match would discriminate better than
token overlap at the cost of a model call per citation.

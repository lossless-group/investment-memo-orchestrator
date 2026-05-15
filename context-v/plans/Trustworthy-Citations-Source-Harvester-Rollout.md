---
title: "Trustworthy Citations: Source Harvester Rollout"
lede: "Where we are after the ChromaDB curation post-mortem, why the existing anti-hallucination work hasn't held, and the concrete six-phase plan to make fabricated URLs structurally impossible — starting with cheap fixes that block the bleeding and ending with a Source Harvester / Section Writer split."
date_authored_initial_draft: 2026-05-15
date_authored_current_draft: 2026-05-15
date_authored_revisions:
  - 2026-05-15: "Phase 1 refined — distinguish URL drift, graceful-error stubs, paywalled-but-reputable. Verdict ladder expanded; reporting shape added."
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-05-15
at_semantic_version: 0.0.0.2
status: Draft
augmented_with: Claude Code (Opus 4.7)
category: Plan
tags:
  - Anti-Hallucination
  - Source-Validation
  - Agent-Topology
  - Retrieval-Augmented-Generation
  - Source-Harvester
  - URL-Validation
  - Citation-Discipline
  - MemoPop
authors:
  - Michael Staton
image_prompt: A six-stage assembly line on a workshop bench — first stations are small bolt-on fixes (a wrench tightening a loose pipe labeled "validator:302", a clamp replacing a leaky urllib HEAD-check), middle stations are a new librarian-style harvester desk receiving books and stamping each with a barcode, last stations are a writer typing prose at a desk separated from the librarian by a glass wall, all in deep-violet uplight with hand-drawn blueprint annotations in monospaced font, technical-illustration aesthetic.
date_created: 2026-05-15
date_modified: 2026-05-15
---

# Plan — Trustworthy Citations: Source Harvester Rollout

## Context

On 2026-05-14 we ran cross-version source curation against ChromaDB and got back **159 "unique" URLs that were mostly recycled across sections, with a meaningful fraction returning HTTP 404 / soft-404 / paywall stubs**. The first probe — `https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-knowledge-bases-now-supports-four-new-data-sources/` — returns a clean 404. The pipeline had cataloged it as `HTTP: 200` and the citation enricher had used it.

This is not a new problem. `blueprints/Anti-Hallucination-Source-Validation-and-Removal.md` (2025-12-15) and `issue-resolution/Faked-Sources-from-Perplexity.md` (2025-12-14) already named the symptom and proposed a validation pass. So why are we still here?

Because the existing fix is downstream and structurally porous:

- **`agents/citation_validator.py:302`** has the buggy clause `if extracted_url and len(issues) == 0` — URL accessibility checks are **skipped whenever any other issue exists**. Self-disabling validation.
- **`agents/remove_invalid_sources.py`** uses `urllib.request.Request(url, method='HEAD', ...)`. HEAD requests get different treatment than GET on many CDNs; and it never reads response bodies, so every soft-404 (Gartner / Forrester / IDC / AWS generic landing) slips through.
- **`agents/research_enhanced.py`** doesn't validate at all. Tavily/Perplexity results land directly in `ResearchData.sources`.
- **`agents/citation_enrichment.py`** is *prompted* to invent citations for already-written prose. It's the worst offender — the prompt itself rewards URL fabrication.

The architectural diagnosis — that **one LLM call cannot reliably both retrieve sources and write prose that cites them** — is captured in `../../../../../context-v/explorations/Separating-Retrieval-from-Generation-in-Agent-Pipelines.md` at the parent monorepo level. The downstream-curation post-mortem is at `../../../../../context-v/explorations/Curating-only-valid-Sources-across-Runs.md`. The runtime operating contract for all agents lives in the orchestrator root's [[AGENTS.md]].

This plan turns those into ordered, executable phases. The principle ordering: **fixes that don't require architecture work first** (Phase 1), then the new agent topology (Phases 2–4), then audit and re-validate (Phases 5–6).

## What we have already

- **Pass A curation shipped** in the memopop-native UI. `src/curation/best_sources.py` walks every version's `3-source-catalog/` and emits `exports/best-of-sources/Master-Sources.md` with URL canonicalization and cross-section dedupe. **This is the safety net, not the fix.**
- **`AGENTS.md` operating contract** drafted at orchestrator root. Twelve anchored principles addressable by section number in agent prompts.
- **Two parent-level explorations** capturing the architectural commitment.
- **Pre-existing blueprints and issue-resolution docs** that named the symptom in Dec 2025 — proposed a HEAD-only validator that has since proved insufficient.

## Phase 1 — Block the bleeding (this week, no architecture)

Small fixes that immediately reduce hallucinated URLs without touching agent topology. None requires a state-schema change.

### The crucial verdict distinction

"Dead URL" and "dead source" are not the same thing. A reputable publisher can move an article (URL changes, content lives). A page can return HTTP 200 with a "Sorry, this article is no longer available" body (graceful error, not a 404). A WSJ article behind a paywall is still a valid source — the citation just can't be read by an anonymous fetcher. The validator must distinguish:

| Verdict | Meaning | Disposition |
|---|---|---|
| `verified-accessible` | Fetched cleanly, real content, title matches | Keep, treat as primary citation |
| `verified-gated` | Fetched, returns paywall / login stub, BUT publisher is on the **reputable-gated allow-list** (WSJ, FT, Bloomberg, Reuters, NYT, Economist, HBR, Nature, NEJM, Lancet, Statista, Gartner-with-real-slug, etc.) | **Keep as valid source.** Flag in run report under "Gated Sources" so an analyst with the relevant subscription can verify. |
| `verified-via-republish` | Original URL failed, second-pass search by `title + publisher + author` found a fresh live URL with matching metadata | Update the corpus to the new URL, keep as primary citation, log the recovery |
| `soft-404-graceful` | 200 status with body explicitly saying the content is gone ("this article is no longer available", "page has moved or been removed") AND second-pass search found no replacement | Drop |
| `hard-404` | True HTTP error (404, 410, 5xx) AND second-pass search found no replacement | Drop |
| `hallucinated-pattern` | Preflight regex match (Gartner doc-id-only, Forrester RES-id, IDC containerId, etc.) | Drop without network request |
| `thin` | 200, no soft-404 phrases, but body has < 2KB of extracted text | Flag for human review (could be SPA shell, could be genuine stub) |
| `title-swapped` | 200, real content, but `<title>` fuzzy-match against claimed title is < 0.3 Jaccard | Flag for human review (likely wrong URL for the claim) |

**The reputable-gated allow-list** is a maintained config file (`src/validation/gated_publishers.yaml` or similar). Conservative initial list: WSJ, FT, Bloomberg, Reuters, NYT, The Economist, Harvard Business Review, MIT Tech Review, Nature, Science, NEJM, Lancet, Statista, IDC (with non-fabricated URL shape), Gartner (with non-fabricated URL shape), Forrester (with non-fabricated URL shape), PitchBook, CB Insights, S&P Global, Moody's, Crunchbase Pro. Extensible.

### Steps

1. **Fix `citation_validator.py:302` bypass.** Replace `if extracted_url and len(issues) == 0:` with `if extracted_url:`. URL accessibility should never be skipped because of unrelated issues. One-line change. **Impact: every citation gets fetched, every time.**

2. **Replace urllib HEAD with httpx GET in `remove_invalid_sources.py`.** Async `httpx.AsyncClient`, concurrency 10, follow redirects, real GET with `Range: bytes=0-32768` where supported (fall back to full GET). Take final status. **Impact: real HTTP errors caught; AWS-style clean 404s die at the gate.**

3. **Add body-content sniffer with three-way classification** in the same module. On 200 responses:
   - **Soft-404 phrases** ("this article is no longer available", "page has moved or been removed", "we couldn't find", "this content doesn't exist", "404", "we can't find that page") → verdict `soft-404-graceful`
   - **Paywall / login phrases** ("sign in to continue", "subscribe to read", "start your free trial", "this content is for subscribers", "log in to read", "create an account to continue") → **check publisher against allow-list.** If reputable → `verified-gated`. If not → `paywall-stub` (drop, treat as soft-404).
   - **Otherwise** → check title match and body length, then `verified-accessible` / `thin` / `title-swapped`.

4. **Implement URL-drift recovery (the second-pass search).** When a URL produces `hard-404`, `soft-404-graceful`, or `fetch-failed`, AND the catalog has a `title` and at least one of `publisher` / `author` / `published_date`, run a recovery search:
   - Query: `"<title>" site:<publisher-domain>` or `"<title>" "<author>"`.
   - Use whichever search tool is configured (Tavily, Perplexity research-only mode).
   - For each candidate result: validate via this same pipeline, AND fuzzy-match title (Jaccard ≥ 0.6) against the original claimed title.
   - First match wins. Update the corpus entry to the new URL; log the recovery to `recovery-log.json` with `{original_url, recovered_url, matched_via}`.
   - If no match found within 5 candidates → fall through to the original verdict (drop or flag).
   **Impact: reputable sources that have just been re-slugged stay in the memo. The publisher's editorial decision to move a URL doesn't cost us a citation.**

5. **Extend `HALLUCINATION_PATTERNS`** in `remove_invalid_sources.py` with the URL shapes we've seen the LLM produce:
   - `^https?://(www\.)?gartner\.com/en/documents/\d+/?$` (no canonical slug)
   - `^https?://(www\.)?forrester\.com/report/[^/]+/RES\d+$` (sequential placeholder IDs)
   - `^https?://(www\.)?idc\.com/getdoc\.jsp\?containerId=US\d+$`
   - More as we find them — this is an extensible regex list. Note: the **non-fabricated** shapes from these same publishers (real slugs, real titles, validated URLs) stay on the reputable-gated allow-list. We're flagging the fabrication template, not the publisher.
   **Impact: zero-cost preflight drops the obvious fabrications without a network request.**

6. **Cache validator results** to `output/.url-validation-cache.json`, keyed by canonical URL, with a 30-day TTL. Cache stores the verdict + the body snippet that triggered it. Re-runs hit cache and add ~0s. **Impact: Phase 1 only feels slow once per URL. Recovery searches cached too.**

7. **Surface verdicts in run reports.** The validator's output feeds into the existing source-catalog generator. New report sections per memo:
   - **Verified Sources** — `verified-accessible` + `verified-via-republish` (latter annotated with the URL change)
   - **Gated Sources** — `verified-gated`, with publisher name and access-method note ("WSJ — requires subscription"). These are valid citations; the report lets the analyst know which subset needs subscription access to verify.
   - **Flagged for Review** — `thin`, `title-swapped`. Human decides.
   - **Dropped** — `hard-404`, `soft-404-graceful`, `paywall-stub`, `hallucinated-pattern`. With reason per entry.
   - **Recovered** — list of `(original_url → recovered_url)` pairs with the search query that found the replacement. Demonstrates the recovery loop is working.

### Phase 1 success criterion

Running the existing pipeline against ChromaDB after Phase 1 produces a `3-source-catalog/` where:
- Zero entries return `hard-404` or `soft-404-graceful` on independent re-fetch.
- Zero entries match the hallucination-pattern preflight.
- Gated sources from reputable publishers are present and labeled, not dropped.
- The recovery log shows at least some `original → recovered` pairs (if our test corpus has any drifted URLs) — proves the recovery loop is wired and not just a no-op.

## Phase 2 — Build the Source Harvester

The architectural move. Splits today's `research_enhanced.py` into two agents with bounded responsibilities, per [[Separating-Retrieval-from-Generation-in-Agent-Pipelines]].

8. **Shared validator module: `src/validation/url_validator.py`.** Extract the logic from Phase 1 into a clean reusable module. Single source of truth. Used by the Harvester and by any other agent that handles URLs. Signature: `validate(url: str, *, claimed_title: str | None = None, publisher: str | None = None, author: str | None = None) -> ValidationResult` with the full verdict ladder from Phase 1 (`verified-accessible`, `verified-gated`, `verified-via-republish`, `soft-404-graceful`, `hard-404`, `hallucinated-pattern`, `thin`, `title-swapped`, `paywall-stub`, `fetch-failed`). Internally orchestrates the preflight regex check, the GET with body sniff, the publisher/allow-list lookup, and the second-pass recovery search.

9. **New agent: `src/agents/source_harvester.py`.** Bounded responsibility: tool calls (Tavily, Perplexity-in-research-mode, Firecrawl) + URL validation. Reads section's `preferred_sources` from the outline. Drops anything that fails validation. Assigns stable IDs (`src-001`, `src-002`, ...). Emits `sourced_corpus.json` per section: `[{id, url, canonical_url, title, fetched_at, body_excerpt, summary, retrieval_query, retrieval_tool, verdict, access_note}]`. The `access_note` carries the "requires WSJ subscription" / "recovered from <old-url>" annotation that flows into the run report. **Does no narrative work.**

10. **Update `MemoState` schema** in `src/state.py` to carry `sourced_corpus: dict[str, list[SourceRecord]]` keyed by section name. Wire into the LangGraph state machine before the writer node.

11. **Per-section query construction.** The harvester reads the section's `guiding_questions` and `preferred_sources` from the outline and constructs targeted queries — not one generic search per section. AGENTS.md §10 (tool diversity per section) is the rule. Team sections route to LinkedIn/socials; market sections route to analyst-report domains; etc.

## Phase 3 — Disarm the writer

The complement to Phase 2. The writer can no longer introduce a URL because it has no tool to search with and the post-process won't let untracked URLs through.

12. **Change writer prompt and state contract.** The writer receives `sourced_corpus` as structured data (corpus IDs + titles + summaries, optionally full body excerpts on flag). Prompt explicitly forbids URL generation. Citations are `[src-NNN]` references to corpus IDs. The model has no search tool.

13. **ID-to-citation post-process.** New module (probably in `src/citation/`) that walks the draft, replaces `[src-NNN]` references with `[^N]` markers, assembles the citation list from the corpus by walking referenced IDs in order. Unresolved IDs (writer invented `src-047` when there are only 32 sources) become `<needs-source>` markers — caught loudly, never silent.

14. **Forbid bare URLs in writer output.** Post-process strips any markdown link whose URL doesn't appear in the corpus. Stripped links become `<needs-source>` markers with the original claim text preserved. AGENTS.md §2 (closed-corpus citation) made structural.

## Phase 4 — Demote citation enrichment

Today's `citation_enrichment.py` is the largest single source of hallucinated URLs because the prompt is "add citations to this prose," which is exactly the failure mode we're eliminating.

15. **Narrow to marker-driven mode.** `citation_enrichment.py` runs only against sections with `<needs-source>` markers. For each marker, the claim text is routed to the Harvester (not directly to an LLM) to find supporting sources. Any URLs come back through the validator gate. **Or delete the agent entirely** if Harvester coverage is good enough — decision deferred to after Phase 3 measurement.

16. **Same treatment for `fact_corrector.py`.** Today it rewrites contradicted claims and can introduce new URLs in the process. Same retrieval/generation conflation. Either becomes pure rewrite-against-existing-corpus, or routes new-source requests through the Harvester.

## Phase 5 — Apply AGENTS.md across the graph

17. **Every agent prompt explicitly references AGENTS.md sections.** Writer prompt cites §1, §2, §3, §4, §5, §6, §7, §9; Harvester cites §2, §7, §10, §11; Fact-Checker cites §5, §11; etc. AGENTS.md becomes load-bearing, not aspirational.

18. **Audit every agent for over-reach** per §11. Any agent doing more than one bounded thing gets split or de-scoped. The pattern to break: Researcher over-asserts → Writer amplifies → Fact-Checker tears down → Fact-Corrector rewrites with new hallucinations. The clean split prevents the fight.

## Phase 6 — Re-run, measure, iterate

19. **Re-run pipeline against ChromaDB end-to-end** with the new architecture. Generate v0.0.8 (or whatever the next version is).

20. **Re-curate via the MemoPop native UI button.** Cross-version best-of should now show dramatically fewer URLs (qualitative target: under 50 unique sources for a complete memo, vs. the current 159 across 7 runs). The "Gated Sources" and "Recovered" sub-reports from Phase 1 step 7 should also appear in the curated output.

21. **Define and measure success.** Of N URLs in the final memo:
    - ≥95% return `verified-accessible` OR `verified-gated` (on a reputable publisher) OR `verified-via-republish` on independent fetch
    - 0% match a hallucination-pattern regex
    - 0% are referenced only because the LLM thought they "should" exist (this is unmeasurable but a smell test — spot-check 10 random URLs)

22. **Iterate on the harvester's query construction** based on what's still missing. The structural problem will be solved; the remaining quality problem is "did we look in the right places?" — that's an outline + query-strategy concern, not a topology concern.

## Decision points

These are open and need user input before the corresponding phase ships:

1. **Strict vs hybrid writer (Phase 3, step 14).** Strict = writer's output is post-processed to strip any bare URL not in the corpus. Hybrid = warn but allow. Recommendation: **strict from day one**. Hybrid is the slippery slope back to "the LLM mostly gets it right."
2. **Corpus richness in writer prompt (Phase 3, step 12).** Summaries only (cheap, ~200 tokens per source), or full body excerpts (rich grounding, ~2K tokens per source × 10 sources = 20K-token prompt before the section guidance even starts). Recommendation: **summaries by default, full excerpts on a `<needs-deeper-grounding>` flag the writer can raise per claim.**
3. **Citation enrichment fate (Phase 4, step 15).** Narrow it to marker-resolver, or delete. Recommendation: **narrow first, measure how often the writer surfaces `<needs-source>`, then decide. If marker rate is < 5%, delete; if > 20%, the harvester isn't covering enough and we keep the enricher as a backstop.**
4. **Phase 6 success threshold.** 95% verified is aspirational. What's the floor that ships? Recommendation: **block-ship below 90%, accept above 95%, investigate the gap in between.**
5. **Reputable-gated allow-list scope (Phase 1, verdict ladder).** Which publishers count as "verified-gated"? The initial conservative list is in the verdict table. Should we expand it to include high-quality industry trade press (TechCrunch behind paywall, Information's gated articles, Stratechery), or stay conservative? Recommendation: **stay conservative for v1, expand based on what we see being legitimately cited in real memos.** The allow-list lives in a YAML file precisely so it's cheap to update without touching code.
6. **Recovery-search aggressiveness (Phase 1, step 4).** How many candidates do we evaluate per recovered URL before giving up? More candidates = better recall but more cost (each is a fetch + validation). Recommendation: **5 candidates per recovery, with fuzzy title match ≥ 0.6 Jaccard as the gate.** Tighten if recovery introduces wrong-source matches.

## What this plan does NOT solve

- **Source quality beyond URL validity.** A `verified` URL can still be an SEO blog with no expertise, an aggregator copying a primary source, or an AI-content-farm site. Editorial filtering is a separate layer ([[blueprints/Anti-Hallucination-Fact-Checker-Agent]] partially addresses this).
- **Claim-vs-source mismatch.** A real URL can be cited for a claim the article doesn't actually make. The fact-checker job. The corpus's `body_excerpt` field makes this easier (the data is right there) but doesn't do it automatically.
- **Outline drift across runs.** The fact that ChromaDB had nine differently-named section sets across seven versions is an outline-stability concern. AGENTS.md §1 (outline-as-contract) names the principle; enforcement is a separate phase.

## Cross-references

**Parent-monorepo explorations** (the architectural rationale):
- `[[../../../../../context-v/explorations/Separating-Retrieval-from-Generation-in-Agent-Pipelines]]`
- `[[../../../../../context-v/explorations/Curating-only-valid-Sources-across-Runs]]`

**Orchestrator-local operating contract:**
- `[[../../AGENTS.md]]` — every phase references AGENTS.md principles by section number

**Pre-existing prior art in this same context-v/:**
- `[[../blueprints/Anti-Hallucination-Source-Validation-and-Removal]]` — Dec 2025 thinking, mostly superseded by the harvester architecture but the validation patterns inform Phase 1
- `[[../blueprints/Anti-Hallucination-Fact-Checker-Agent]]` — claim-vs-source verification, the layer above URL validity
- `[[../issue-resolution/Faked-Sources-from-Perplexity]]` — the original symptom record, Dec 2025
- `[[../issue-resolution/Correct-Citation-Pipeline-Accuracy-in-Multi-Agent-Research]]`
- `[[../issue-resolution/Getting-AI-to-Refocus-when-Web-Research-is-empty]]` — related to AGENTS.md §7 (no backfilling from training data)

**Pattern reference:**
- `[[Wire-Memopop-Native-To-The-FastAPI-Sidecar]]` — the plan-doc shape this one follows

## One-sentence version

Block the bleeding with a real URL validator that distinguishes dead URLs from drifted URLs (recoverable via title+publisher search), dead pages from gated-but-reputable pages (paywalled WSJ stays in), and hard 404s from graceful-error stubs (Phase 1), then split `research_enhanced.py` into a Source Harvester (tools + validation only) and a Section Writer (prose + cite-by-ID only) so URL fabrication becomes structurally impossible (Phases 2–4), then enforce AGENTS.md across every agent and re-run against ChromaDB (Phases 5–6).

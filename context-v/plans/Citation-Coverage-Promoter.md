---
title: "Citation Coverage Promoter: Surface the Long Tail of Cited Sources"
lede: "The writer agent reliably composes prose that cites a handful of sources heavily and ignores the rest. ChromaDB v0.0.10 demonstrated the pattern at scale — 33 hand-curated URLs in scope, 7 actually cited, 26 ignored. This plan adds a citation-additive, prose-conservative second pass between draft and assemble: same prose, more sources, more even distribution. Phase 1 is prompt-level fixes; Phase 2 is the new agent; Phase 3 is matching infrastructure; Phase 4 is calibration."
date_authored_initial_draft: 2026-05-22
date_authored_current_draft: 2026-05-22
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-05-22
at_semantic_version: 0.0.0.1
status: Draft
publish: false
augmented_with: Claude Code (Opus 4.7)
category: Plan
tags:
  - Citation-Discipline
  - Source-Coverage
  - Writer-Prompt
  - Agent-Topology
  - Codified-Sources
  - MemoPop
authors:
  - Michael Staton
image_prompt: A wide library reading-room cross-section seen from the side — at left, a writer at a typewriter pulling books from a tall stack of 33 but actually only opening 7 of them, the other 26 untouched on a shelf behind a glass case labeled "UNDERUSED"; at right, a librarian-auditor in a green visor stands next to the typewritten draft holding a stamp marked "[^N]" and quietly pressing it after sentences in the existing prose without changing a single word of the writer's text; a horizontal arrow labeled "additive only" connects the auditor's stamp to the existing prose; deep-violet uplight, blueprint-paper aesthetic, hand-drawn monospaced annotations.
date_created: 2026-05-22
date_modified: 2026-05-22
---

# Plan — Citation Coverage Promoter

## Context

The writer agent has a persistent pattern of citing a small subset of available sources very heavily and ignoring the long tail. ChromaDB v0.0.10 — the first end-to-end demonstration of codified-source mode — surfaced it clearly:

- **33 hand-curated URLs** in `inputs/Sources.md`, fetched and synthesized into per-section research.
- **98 inline `[^N]` references** in the final memo body.
- **7 distinct sources** resolved across those 98 references (post-`citation_assembly` consolidation).
- **26 sources** sat in the corpus and never appeared in the memo.

This isn't a codified-mode problem — it's the writer's behavior on *any* corpus that exceeds a handful of sources, and it has been observed across many prior memos. The codified path just made it legible: we know exactly which sources were available, so we can measure what fraction made it through.

The diagnosis (from `2026-05-22_02.md` "The Analyst Gets the Pencil"):

1. **Token economy.** Integrating 33 sources is cognitively harder than 5. The model gravitates to a manageable subset.
2. **Position / prominence bias in the prompt.** Sources earlier in the system prompt or with longer body excerpts get over-cited.
3. **Topical-fit asymmetry.** Some sources are obviously about the topic; subtler relevance gets ignored.
4. **No diversity pressure.** The current writer prompt does not penalize repeated citations.
5. **Token budget per section.** Within a 500-word section, the writer reaches for the cheapest source that supports each claim and moves on.

The remedy is not to rewrite the writer agent. It's to add a **citation-additive, prose-conservative** second pass that promotes underused sources without rewriting prose. The analyst's curation work is wasted if 80% of the curated set never reaches the final memo.

## What we have already

- The codified-source path writes per-section research files in `1-research/` with `[^N]` citations referencing the curated set (`src/agents/codified_section_researcher.py`).
- The writer (`src/agents/writer.py`) composes per-section drafts in `2-sections/`, drawing from those research files plus the deck and general background research. Citations carry through.
- A standalone `citation_enrichment_agent` (`src/agents/citation_enrichment.py`) runs **upstream of the writer**, not after it (see `workflow.py` — the `cite` node fires after `competitive_evaluator` and before `cleanup_research → aggregate_sources → draft`). It operates on `1-research/` files, calling Perplexity Sonar Pro to ADD NEW citations to research material before the writer composes prose. It is NOT a coverage promoter; it brings in new URLs (often LLM-generated) rather than promoting underused curated ones. The two functions are genuinely distinct and should stay as separate agents — repurposing `citation_enrichment` would conflate "widen the corpus" with "redistribute attention within a fixed corpus."
- No existing agent does the proposed job (promoting underused curated sources by inserting `[^N]` markers into already-written prose). The post-writer agents that touch `2-sections/` are: `inject_deck_images`, `enrich_trademark`, `enrich_socials`, `enrich_links`, `generate_tables`, `generate_diagrams`, `enrich_visualizations`, `revise_summaries`, `cleanup_sections` (subtractive — `remove_invalid_sources_agent`), `assemble_citations`, and `fact_correct` (claim-driven rewrites). None are coverage-driven.
- The codified Sources.md frontmatter gives every source a `rank: N` field already. The current writer doesn't use it.
- The cleanup_sections gate (`remove_invalid_sources_agent`, URL-keyed) validates and trims citations after the writer, so any inserted citations get the verdict-ladder treatment automatically.

## Phase 1 — Prompt-level fixes (cheap, no new agent)

**Separation of concerns.** Two agents touch citations in the prose pipeline, and they should be given fundamentally different prompt regimes:

- **Codified researcher** (`codified_section_researcher.py`) — focused on *ingesting content and drafting narrative from available sources*. Its job is **maximize source diversity**. Don't burden it with paragraph-elegance rules or per-paragraph dedup; that's not its level. Cite every tagged source whose content fits a claim, stack freely, redundancy is fine. The research file is raw material, not finished prose.
- **Writer** (`writer.py`) — focused on *coherent narrative, elegant paragraph structure, and citation balancing*. Its job is to read the research file (which is now coverage-maximizing) and compose investor-ready prose with the three citation-discipline rules below applied to the *output*. The writer inherits the diversity by carrying citations forward from research, and adds the discipline.

This division means Phase 1 has two prompt-edit groups — one per agent — with overlapping but not identical rules.

### Step 1 — Codified researcher prompt: maximize diversity, don't over-discipline

In `codified_section_researcher.py`'s `_synthesize_via_claude`, the synthesis prompt should be amended to make coverage the dominant value:

> **Cite every source that contributes to a claim in this section.** If a source's content supports something you're writing, cite it. If three sources independently support the same fact, cite all three inline: `... happened in Q3 [^1] [^2] [^4].` Redundancy is a feature here, not a flaw — this research file is the writer's source-of-truth, and missing citations at this stage will not be recovered downstream.
>
> Do not omit a source because another already covers the claim. Do not pick "the best one" — the writer will do that selection later. Your job is to ensure every tagged source whose content fits a claim has a citation attached.

Additionally, label each source block with its rank so downstream consumers (writer, coverage promoter) can see analyst priority:

- In `_synthesize_via_claude`, change source block headers from `### Source [^N]: <title>` to `### Source [^N] (rank N): <title>`.

No paragraph-dedup rule, no 40% cap, no laziness clause for the researcher. Those are writer-level concerns.

### Step 2 — Writer prompt: the three citation-discipline rules

In the writer prompt (`src/agents/writer.py`, `WRITER_SYSTEM_PROMPT_BASE` and/or the per-section `user_prompt`), append a new section. These three rules constrain each other and must be stated together:

> **CITATION DISCIPLINE**
>
> **1. Stack supporting sources inline.** When two or more sources in the research file each support the same claim, cite them stacked: `... happened in Q3 [^1] [^2] [^4].` Do not pick "the best one and move on" — if three sources each independently report the same fact, the reader is owed all three. The analyst curated these sources deliberately; carry that work through to the page.
>
> **2. No single source more than once per paragraph.** Within a single paragraph, do not cite the same `[^N]` twice. If a paragraph makes three claims and source `[^4]` supports all three, cite it once — at the most diagnostic sentence, or at the paragraph's terminal claim if it serves as the overall ground. Pick the placement that best signals *what* `[^4]` actually establishes.
>
> **3. Do not be lazy. Do not guess. Do not take shortcuts.** Every `[^N]` you place must reflect content you actually read in that source's block in the research file. Do not stack citations to *look* thorough — stack only when you genuinely have multiple sources backing the same claim. If only one source supports a claim, cite only that one. If a claim has no source in the research file, emit `<needs-source>` rather than guessing which `[^N]` might cover it.

Also add (as a complement to rule 2):

> **Rank awareness.** Rank-1 sources are the analyst's primary picks for this section. When stacking, lead with the highest-rank source: `[^1] [^4] [^7]` (rank 1, 2, 3), not `[^7] [^1] [^4]`. When a claim has only a low-rank source, cite it without apology — the analyst tagged it for a reason.

### Step 3 — Section-level density backstop (writer only)

Append to the writer prompt: *"In each section, no single source should account for more than ~40% of the section's inline citations. The per-paragraph dedup rule (rule 2) should make this hard to violate, but if you find yourself citing the same `[^N]` more than 3 times across the section, you're either composing too narrowly or the source genuinely is the section's spine — in the latter case, that's fine."*

Advisory, not enforced. The cleanup_sections gate doesn't measure density. This is the section-level analog of rule 2.

### Phase 1 success criterion

Re-running v0.0.10 with the researcher prompt + writer prompt + rank-labeling edits should produce:

**Research-side (1-research/):**
- Every section's research file cites ≥80% of the sources tagged for that section in Sources.md. (v0.0.10: section 5 cited 1 of 8; section 7 cited 1 of 3 — these should land at 6-of-8 and 2-of-3 or better.)

**Writer-side (2-sections/ → final memo):**
- ≥20 of the 33 curated sources have at least one inline citation in the final memo (up from 7).
- No single source carries >40% of any section's citations.
- No paragraph cites the same `[^N]` twice.
- Stacked-citation patterns (`[^1] [^2] [^4]`) appear in the prose wherever the research file has redundant coverage for a claim.
- No new code; no new agent; no additional API spend per memo.

If Phase 1 alone closes the gap to ≥20-of-33, Phase 2 (the new agent) is deferred. Measure before building.

## Phase 2 — The Citation Coverage Promoter agent

### Naming note

Originally drafted as "Citation Diversity Enricher." Renamed to **Citation Coverage Promoter** to avoid collision with the existing `citation_enrichment` / `citation_assembly` / `citation_corrector` / `citation_validator` / `citation_spacing` family — "enrichment" is already overloaded in this codebase, and the new agent's job (redistribute attention within a fixed curated corpus) is genuinely distinct from `citation_enrichment`'s job (widen the corpus with new external URLs via Perplexity).

If Phase 1's prompt tweaks land us at, say, 12 of 33, the remaining gap warrants a dedicated audit pass.

### Step 4 — New agent module: `src/agents/citation_coverage_promoter.py`

Function name: `citation_coverage_promoter_agent(state: MemoState) -> Dict[str, Any]` (matches the `*_agent` convention used across the agents directory).

**Target: `1-research/` files, not `2-sections/`.** Today's v0.0.10 inspection showed coverage loss starts at the synthesis stage (section 5 of v0.0.10: 8 sources tagged, 1 cited in the research file). Promoting coverage upstream — in research notes — means the writer inherits it, since the writer is far more likely to carry forward an `[^N]` already present in its input than to introduce one fresh. One intervention, two stages of payoff.

The Phase 1 researcher prompt-edit (Step 1) should reduce this gap substantially. The Coverage Promoter is the structural safety net for whatever the prompt edit doesn't close.

Bounded responsibility: read each research file in `1-research/`, identify sources tagged for that section but not yet cited, fetch their content from the codified researcher's cache, ask Claude to insert `[^N]` references at appropriate sentences without rewriting prose. No new sources outside the curated set, no prose changes.

```python
def citation_coverage_promoter_agent(state: MemoState) -> Dict[str, Any]:
    """
    For each per-section research file in 1-research/, find sources from
    Sources.md that are tagged for the section but not yet cited, and
    insert [^N] references at sentences where they naturally support
    existing claims.

    No-op unless Sources.md is in codified mode — the broad-search path
    has its own per-section research from Perplexity Sonar Pro and there
    is no fixed curated set to promote against.
    """
```

Inside the agent, per research file:

1. Parse the existing research markdown to extract the set of `[^N]` references actually used (call them `cited_in_research`).
2. From `inputs/Sources.md`, get the sources tagged for this section (via `sources_for_section()`).
3. Compute `underused = tagged_for_section - sources_cited_by_url`. Note: the research file's `[^N]` numbers are local per-file IDs assigned by the codified researcher, NOT Sources.md ranks. Map them back via the existing `### Source [^N] (rank N): <title> — <url>` headers in the research file's appendix, then compare by URL.
4. For each underused source, build a per-source content block with the title, URL, and the first ~2KB of fetched markdown (already cached from the codified researcher's Jina fetch in this run's directory).
5. Assign the next local `[^N]` number for each underused source, append it to the research file's source appendix.
6. Call Claude with the strict citation-only prompt below.
7. Write the modified research file back to `1-research/{section_filename}-research.md`.

### Step 5 — The strict citation-only prompt

```
You are auditing one section's research file for citation coverage.

CURRENT RESEARCH FILE:
{research_markdown}

CURRENTLY CITED: [^4], [^7], [^12]

UNDERUSED SOURCES (tagged for this section but absent from current citations):
[^8]: {title} — {url}
  Excerpt (first ~2KB): {fetched_content_excerpt}

[^17]: ...

YOUR JOB: For each UNDERUSED source, find a sentence in the research narrative
where that source naturally supports the existing claim. Insert [^N] inline
after the relevant sentence. Stacking with existing citations is encouraged:
"X happened [^4] [^8]" is exactly the pattern we want.

HARD RULES:
- Do NOT rewrite or rephrase any prose. Only insert [^N] markers.
- Stacking is encouraged: multiple [^N] after one claim is the norm here, not the exception.
- If a source doesn't fit naturally anywhere, leave it uncited — do NOT force.
- Do NOT add new claims, sentences, paragraphs, or transitions.
- Output ONLY the modified research markdown with no other commentary.

QUALITY EXPECTATION: it's better to insert zero citations than to insert
ones that misrepresent what a source actually says. Better to leave a source
underused than to over-cite it incorrectly. This research file is the writer's
source-of-truth — coverage here is high-leverage, but inaccuracy here poisons
the prose downstream.
```

Note: the writer's per-paragraph dedup rule (Phase 1 Step 2, rule 2) does NOT apply at the research-file stage. Research files are raw material; redundant citations there are a feature. The writer will dedup when composing prose.

The "do not rewrite prose" guardrail is what makes this safe to run iteratively without text drift.

### Step 6 — Workflow integration

**Correction to earlier draft:** `cite` (`citation_enrichment_agent`) runs *upstream* of `draft`, not downstream. The current order (per `workflow.py:529-548`) is:

```
... → competitive_evaluator → cite → cleanup_research → aggregate_sources → draft
   → inject_deck_images → enrich_trademark → enrich_socials → enrich_links
   → generate_tables → generate_diagrams → enrich_visualizations
   → revise_summaries → cleanup_sections → assemble_citations → ...
```

The new `citation_coverage_promoter` belongs in the **research band**, between `section_research` (which writes 1-research/ files) and `cite` (which currently runs Perplexity enrichment, but in codified mode should no-op per Decision Point #2). So:

```
... → section_research → citation_coverage_promoter → cite → cleanup_research → aggregate_sources → draft → ...
                        ↑ promotes underused curated sources in 1-research/
                                                                ↑ no-op in codified mode (Decision #2)
                                                                                                              ↑ writer inherits the coverage
```

Rationale for that slot:
- Immediately after `section_research`: the codified researcher has just written 1-research/*.md and the Jina fetches for every curated URL are still warm in this run's directory.
- Before `cite`: in codified mode, `cite` is gated off, so the promoter is the last touch on 1-research/ before validation. In non-codified mode, the promoter is also a no-op (no Sources.md to promote against), so order doesn't matter.
- Before `cleanup_research`: any inserted `[^N]` markers get the verdict-ladder validation for free.
- Before `draft`: the writer inherits the coverage — the highest-leverage outcome.

**Not the post-writer slot.** An earlier draft put the promoter between `enrich_visualizations` and `revise_summaries` (operating on 2-sections/). Today's v0.0.10 inspection (sections 5, 6, 7 cited 1, 4, 1 of 8, 7, 3 tagged) showed the upstream slot is the higher-leverage intervention: fixing coverage in research notes pulls the writer along, while fixing it in section files leaves the synthesis gap unaddressed. The post-writer slot remains a future option if upstream-only coverage isn't enough.

### Step 7 — Configuration constraints

- `max_tokens` per call: 4000 (enough for the full section's prose plus inline `[^N]` markers).
- `temperature`: 0.2 (conservative; we want minimal change, not creative writing).
- `top_p`: default.
- The system prompt should NOT include the deck or general background — only the section text and the underused source excerpts. Constraint by exclusion: if the model can't see other context, it can't be tempted to expand the prose.

## Phase 3 — Topical-match infrastructure

The Phase 2 prompt asks Claude to find a "sentence where this source naturally supports the existing claim." That works, but it relies entirely on the LLM's reasoning. A simple matching pre-pass would help:

### Step 8 — Per-source sentence-match hints

Before calling Claude, run a lightweight matcher between each underused source's body and the section's sentences:

- Tokenize the section into sentences.
- For each underused source, score each sentence by token-set Jaccard or TF-IDF overlap with the source's body (or just its title + first 500 chars).
- Sort sentences by score; pass the top 3 candidates to Claude as hints: *"This source might fit one of these sentences: [...]. Or anywhere else in the section. Or nowhere — your call."*

This is cheap (no external API; just regex + counter) and gives the model a starting place.

### Step 9 — Optional: embedding-based matching

If keyword overlap is too coarse, swap in sentence embeddings (the orchestrator already has Anthropic/OpenAI keys; we'd use a cheap embedding model). Compute cosine similarity between each section sentence and each underused source's title+excerpt. Same downstream prompt; better matches.

Worth it only if Step 8's keyword matching turns out insufficient. Probably defer until measurement shows it's needed.

## Phase 4 — Measurement and calibration

### Step 10 — Track coverage as a per-run metric

In the run summary, add:

```
📊 Citation coverage:
  Curated sources:        33
  Sources cited (draft):  12   (36%)
  Sources cited (after diversity enricher):  18   (55%)
  Sources cited (after cleanup_sections):    18   (55%)

  Per-source distribution:
    [^1] trychroma.com: 21 cites (21%)
    [^4] github/chroma-core: 14 cites (14%)
    [^8] oracle: 8 cites (8%)
    ...
    [^29] mindstudio/hybrid-memory: 1 cite (1%)
    [^31] aix-ventures: 1 cite
    [^32] bloomberg-beta: 0 cites
    [^33] quiet-capital: 1 cite
```

Surface this in the validator's output and in a new top-level summary section of `state.json`.

### Step 11 — Per-source distribution alarm

When the per-source distribution is heavily skewed (single source carries >40% of citations), surface a warning in the validator's report so the analyst knows to look at it. Not a fail; just a flag.

### Step 12 — Track citation density per section

Add to the run summary:

```
Section          Citations  Unique sources  Most-cited  % of section
01-overview      18          5               [^1] 8x     44%   ⚠️ over-concentrated
02-why-invest    14          7               [^4] 4x     29%
03-situation     22          9               [^8] 6x     27%
04-team          11          4               [^31] 4x    36%
...
```

The "⚠️ over-concentrated" flag fires when a single source is >40% of a section's citations.

## Decision points

These are open and need user input before the corresponding phase ships:

1. **Phase 1 vs Phase 2 — measure first?** Recommendation: **ship Phase 1 alone first**, re-run v0.0.10, see if prompt tweaks alone get coverage from 7/33 to 15+/33. If yes, defer Phase 2 — simpler is better. If no, proceed to Phase 2.

2. **`citation_enrichment_agent` boundary.** The existing agent adds new sources for unsourced claims via Perplexity Sonar Pro — and Sonar Pro is exactly the source of LLM URL inventions that triggered the whole Trustworthy-Citations rollout. In codified mode, that behavior is actively harmful (it'll add URLs outside the analyst's approved set). Recommendation: **gate `citation_enrichment_agent` on `is_codified()`** — in codified mode it should be a no-op (or strictly limited to drawing from the codified set, never Perplexity). Out of codified mode it stays as-is.

3. **Diversity-enricher run mode.** Should it run on every codified-mode memo, or be opt-in? Recommendation: **always-on in codified mode**, because the analyst's curation work is the whole point — using only 7/33 is leaving value on the table by default.

4. **Diversity-enricher input scope.** Just the underused sources tagged for THIS section, or all curated sources? Recommendation: **only sources tagged for this section** — the analyst's section-tagging is a strong signal of relevance. If a source isn't tagged for the section, the model probably shouldn't force-cite it there.

5. **Temperature for the enrichment call.** 0.0 vs 0.2 vs 0.4. Recommendation: **0.2** — low enough to discourage prose drift, high enough to allow some judgment about which sentence best fits each source.

6. **Failure handling.** If the enricher's Claude call fails or returns something unparseable (added new claims, rewrote sentences), the safest fallback is to skip enrichment for that section. Recommendation: **diff the original and the returned text on word count and sentence count; if either changed by >5%, reject the enrichment and log the rejection**. We trust the rules but verify.

## What this plan does NOT solve

- **The writer's choice of WHICH claims to make.** If the analyst's curated set covers topic X but the writer never makes a claim about X in this section, no enrichment can insert a citation about X without rewriting prose. That's an outline+writer-prompt concern, not a citation-coverage concern.

- **Source quality.** The diversity enricher promotes underused sources without judging their quality. If a curated source is technically valid (passed the Phase 1 verdict ladder) but is editorially weak (e.g., DataCamp tutorial vs. McKinsey report), it'll still get promoted. The analyst's curation decision is what's trusted.

- **The fact-corrector / fact-verifier behavior.** Those agents may still introduce new URLs in codified mode if they detect unsourced claims. Same fix as Decision Point #2: gate them on `is_codified()` and either no-op or strictly restrict to the codified corpus.

- **Cross-section citation balance.** A source tagged for sections [overview, why-invest, traction] might be cited heavily in overview and not at all in the other two. The per-section diversity enricher catches *within-section* skew, not *across-section* skew. A future cross-section auditor could compute "this source is tagged for 3 sections but only cited in 1" and surface that as a coverage gap.

## Cross-references

**Sibling plans / explorations (this implements / extends them):**

- [[Trustworthy-Citations-Source-Harvester-Rollout]] — the parent plan. Citation diversity sits alongside URL validity in the broader "trustworthy citations" effort.
- `[[../../../../context-v/explorations/Human-Curated-Source-Sets-and-Per-Firm-RAG-for-Memo-Narrative]]` — the exploration. Curation only matters if curated sources actually reach the memo; this plan is what closes that loop.
- `[[../../../../context-v/explorations/Separating-Retrieval-from-Generation-in-Agent-Pipelines]]` — informs the boundary discipline. The diversity enricher is in the *post-write* enrichment band, not the retrieval band.

**Existing artifacts:**

- `[[../changelog/2026-05-22_02|The Analyst Gets the Pencil]]` — names the 7-of-33 problem as a next-iteration item.
- `[[../blueprints/Anti-Hallucination-Source-Validation-and-Removal]]` — the validator pattern; diversity enricher is on the *additive* side, opposite of the validator's *subtractive* role, but both compose into the same `cleanup_sections` gate downstream.

**Code files (anticipated):**

- `src/agents/writer.py` — Phase 1 prompt edits land here.
- `src/agents/codified_section_researcher.py` — Phase 1 step 2 (label sources by rank) edits land here.
- `src/agents/citation_coverage_promoter.py` — NEW, Phase 2.
- `src/agents/citation_enrichment.py` — Decision Point #2 may gate this in codified mode. Note: this agent runs *pre-writer* on `1-research/` files, not post-writer.
- `src/workflow.py` — Phase 2 step 6 wires the new agent in between `enrich_visualizations` and `revise_summaries`.

## One-sentence version

Add a citation-additive, prose-conservative second pass between the writer and the existing citation-enrichment step that promotes analyst-curated sources from "tagged but uncited" to "cited at the right sentence" — without rewriting a word of the writer's prose — so the 26-of-33 unused sources from v0.0.10 become 5-of-33 or fewer on the next run.

---
title: "Generic competitor analysis enhancement, post-hoc and re-runnable"
lede: "Move competitor research/evaluation from a one-shot pipeline step into a re-runnable, configurable enhancement — driven by `.md` + frontmatter schemas, applicable to any version of any memo, surfaced in memopop-native."
date_authored_initial_draft: 2026-05-03
date_authored_current_draft: 2026-05-03
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-05-03
at_semantic_version: 0.0.0.1
status: Draft
augmented_with: Claude Code (Opus 4.7)
category: Plan
tags: [Competitor-Analysis, Investment-Memo, Content-Model, Frontmatter, Refactor, Memopop-Native, Multi-Firm]
authors:
  - Michael Staton
date_created: 2026-05-03
date_modified: 2026-05-03
---

# Plan — Generic competitor analysis enhancement

## Context

Competitor analysis exists in three disconnected places:

1. **Pipeline agents** that run automatically during memo generation:
   - `src/agents/competitive_landscape_researcher.py` — discovers competitors via web research, writes `1-competitive-research.{json,md}`.
   - `src/agents/competitive_landscape_evaluator.py` — scores them, writes `1-competitive-evaluation.{json,md}`.
   - Wired into `src/workflow.py:39-40, 461-462` as `competitive_researcher` → `competitive_evaluator` nodes.
2. **Interactive review** in the Rich terminal app:
   - `cli/terminal_app/py_rich/app.py:549` `flow_integrate_competitive()` walks evaluated competitors across versions for human curation.
3. **Generic section enhancer** that *could* target the competitive section:
   - `cli/improve_section.py "Category Leadership"` — re-runs Perplexity on a single section.

What's missing:

- **No standalone CLI** to re-run the competitive landscape researcher/evaluator on an existing artifact directory. If the original run produced weak results, you have to regenerate the entire memo.
- **No content model** for competitor evaluation criteria. The evaluator's prompt (which dimensions to score on, scoring scale, what counts as a credible competitor) is hardcoded inside the agent — not discoverable, not customizable per firm.
- **No memopop-native surface.** The interactive review only lives in the terminal app. The native UI shows artifacts read-only.

This is the same shape as the scorecard refactor (see `Generic-Scorecard-Generation.md`): a capability exists buried in the pipeline; it needs an extractable content model, a re-runnable script, and a UI affordance.

## Approach

Lift the competitive evaluation criteria into a `.md` + frontmatter content model, build a standalone re-run CLI, then expose it on the deal page in memopop-native.

Architecture decisions:

- **`.md` + frontmatter as the content model.** Mirror the scorecard pattern. Frontmatter declares: scoring dimensions, scoring scale, credibility filters (e.g. "min funding raised", "must have product in market"), output format. Body is human-readable methodology notes.
  - Path: `templates/competitor-frameworks/{name}.md` (firm overrides at `io/{firm}/templates/competitor-frameworks/{name}.md`).
  - Default framework: `default-direct-investment.md`. Alpha Partners gets `alpha-partners-7Cs-competitive.md` aligned with their C2 (Category Leadership) and C5 (Colossal Market) dimensions.
- **Deal JSON declares the framework.** New optional field `competitor_framework: "alpha-partners-7Cs-competitive"`. Resolves the same way as `scorecard` and `outline`.
- **Standalone CLI: `cli/enhance_competitor_analysis.py`.** Mirrors `cli/improve_section.py` UX: takes deal target + version, loads existing artifacts, re-runs `competitive_landscape_researcher` and `competitive_landscape_evaluator` against the latest inputs, overwrites `1-competitive-research.{json,md}` and `1-competitive-evaluation.{json,md}`. Optional `--researcher-only` / `--evaluator-only` flags.
- **Agents stay used by the pipeline.** Refactor them to read framework config from frontmatter (passed in via state or resolved internally) rather than inline-prompted dimensions. Same agent runs in pipeline and in the standalone CLI.
- **Memopop-native surface.** Deal page gets a "Competitive landscape" tab showing current evaluations, with "Re-run research" + "Re-run evaluation" actions and per-competitor curation (keep/drop/edit) — port the terminal-app flow to Svelte.

## Phases

### Phase 1 — Content model

- [ ] Define frontmatter schema for competitor frameworks. Fields:
  - `metadata` (id, name, version, firm, applicable_types)
  - `scoring` (scale, label_map, what each dimension means)
  - `evaluation_dimensions` (e.g. "category_overlap", "funding_stage_match", "geographic_overlap", "product_maturity")
  - `credibility_filters` (min funding, min team size, must-have-product flags)
  - `output_format` (table layout for `1-competitive-evaluation.md`)
  - `discovery_guidance` (search queries template, source preferences)
- [ ] Create `templates/competitor-frameworks/default-direct-investment.md` — captures what the current agent does today, just externalized.
- [ ] Create `templates/competitor-frameworks/default-fund-commitment.md` — fund-specific (peer GPs, comparable funds).
- [ ] Create `io/alpha-partners/templates/competitor-frameworks/alpha-partners-7Cs-competitive.md` — aligned with the 7Cs scorecard's C2/C5 dimensions.
- [ ] Add `templates/competitor-frameworks/competitor-framework-schema.json`.

### Phase 2 — Refactor agents to consume the content model

- **`src/agents/competitive_landscape_researcher.py`:**
  - Resolve framework via new helper (mirrors scorecard resolver from sibling plan).
  - Build search queries from `discovery_guidance.search_queries_template` instead of inline list.
  - Apply `credibility_filters` to drop noise competitors before saving.
- **`src/agents/competitive_landscape_evaluator.py`:**
  - Read `evaluation_dimensions` and `scoring` from framework frontmatter.
  - Build the evaluation prompt from frontmatter (same generic-renderer pattern as the scorecard refactor).
- **`src/state.py`:** add optional `competitor_framework: str | None` to `MemoState`.
- **`src/main.py`:** populate `competitor_framework` from deal JSON; default to `default-{investment_type}` if missing.

### Phase 3 — Standalone CLI

`cli/enhance_competitor_analysis.py`:

- Args mirror `cli/generate_scorecard.py`: `target` (deal name or artifact path), `--version`, plus `--researcher-only` / `--evaluator-only` / `--framework <name>` overrides.
- Loads `state.json` from artifact dir; rebuilds `MemoState`.
- Calls `competitive_landscape_researcher(state)` (unless `--evaluator-only`); persists outputs.
- Calls `competitive_landscape_evaluator(state)` (unless `--researcher-only`); persists outputs.
- Prints competitor count + score distribution summary.
- Cost notes in help text (Perplexity calls, ~$X/run).

Validation:

- [ ] Run against `io/alpha-partners/deals/ChromaDB/outputs/ChromaDB-v0.0.1/` — produces fresh competitor evaluation with the new framework.
- [ ] Run with `--framework default-direct-investment` to compare against the alpha-partners framework — confirms decoupling.
- [ ] Run `--researcher-only` then `--evaluator-only` separately — confirms the steps are independently runnable.

### Phase 4 — Memopop-native surface

Target route: `apps/memopop-native/src/routes/deals/[firm]/[deal]/+page.svelte`.

- **New tab/panel:** `CompetitiveLandscapePanel.svelte` in `src/lib/components/` — alongside `ArtifactBrowser.svelte`. Shows current evaluated competitors as a sortable table (name, score, dimensions, source).
- **Actions:**
  - "Re-run research" button → `POST /memos/{id}/competitors/research`.
  - "Re-run evaluation" button → `POST /memos/{id}/competitors/evaluate`.
  - Per-row keep/drop toggles → write back to `1-competitive-evaluation.json` (curated subset).
- **Sidecar:** new routes in `src/server/` (mirrors the existing `/memos` routes from the FastAPI sidecar work — see `Wire-Memopop-Native-To-The-FastAPI-Sidecar.md`):
  - `POST /memos/{id}/competitors/research`
  - `POST /memos/{id}/competitors/evaluate`
  - `GET /memos/{id}/competitors` (returns curated list)
  - `PATCH /memos/{id}/competitors/{competitor_id}` (curation update)
- **Transport:** add `enhanceCompetitorResearch(jobId)`, `enhanceCompetitorEvaluation(jobId)`, `listCompetitors(jobId)`, `curateCompetitor(jobId, competitorId, patch)` to `src/lib/transport/types.ts` + `local.ts`. Rust dispatcher gets corresponding match arms.
- **Optional Phase 4.5:** port the terminal-app `flow_integrate_competitive()` cross-version comparison view to Svelte (show competitors evaluated across v0.0.1, v0.0.2, etc., side-by-side).

## Open questions

- **Scope of "re-run":** should the researcher always re-run the web search, or check freshness of cached results first? Probably make it a flag: `--force-fresh` vs default-incremental.
- **Curation persistence:** if the user manually drops 3 competitors via the UI, does a subsequent re-run respect that? Suggest storing curation decisions in a separate `1-competitive-curation.json` that the evaluator reads as a hint (not a hard filter).
- **Sequencing with scorecard:** if the C2 (Category Leadership) scorecard rationale references competitors, re-running competitor analysis should probably invalidate the scorecard. Defer cross-cutting invalidation to a future "memo coherence" plan.

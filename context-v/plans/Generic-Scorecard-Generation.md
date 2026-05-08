---
title: "Generic scorecard generation across firms and outlines"
lede: "Refactor the scorecard agent + CLI from hardcoded Hypernova/fund-only to a generic renderer driven by `.md` + frontmatter scorecards, then surface it in memopop-native on the deal page."
date_authored_initial_draft: 2026-05-03
date_authored_current_draft: 2026-05-03
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-05-03
at_semantic_version: 0.0.0.1
status: Draft
augmented_with: Claude Code (Opus 4.7)
category: Plan
tags: [Scorecard, Investment-Memo, Content-Model, Frontmatter, Refactor, Memopop-Native, Multi-Firm]
authors:
  - Michael Staton
date_created: 2026-05-03
date_modified: 2026-05-03
---

# Plan — Generic scorecard generation

## Context

`cli/generate_scorecard.py` and `src/agents/scorecard_agent.py` are hardcoded to Hypernova's emerging-manager fund framework:

- `scorecard_agent.py:13` — template path is literally `templates/scorecards/lp-commits_emerging-managers/hypernova-scorecard.yaml` (which **doesn't exist in the main repo anymore** — it moved into the `io/hypernova` submodule, so the agent is currently broken even for hypernova).
- `scorecard_agent.py:34-39` — `_load_section_snippets()` reads fund-specific section filenames (`02-gp-background--credibility.md`, `03-fund-strategy--thesis.md`, etc.).
- `scorecard_agent.py:106-153` — prompt hardcodes "12 dimensions", "3 horizontal markdown tables", group names ("Empathy / Theory of Market / Ecosystem Imprint / Hustle"), and the 1–5 → percentile mapping.
- `scorecard_agent.py:162-166` and `cli/generate_scorecard.py:96-105` — both gate on `investment_type == "fund"` AND `outline_name == "lpcommit-emerging-manager"`.

Meanwhile Alpha Partners has a fully-formed direct-investment scorecard (7 Cs, 4 groups, 7 dimensions, 1–5 scale, different threshold rules) at `io/alpha-partners/templates/scorecards/direct-growth-7Cs/alpha-partners-7Cs-scorecard.md`. Per-deal JSON (e.g. `deals/Solugen/Solugen.json`) already references it via a `scorecard: "alpha-partners-7Cs"` field. The CLI today would silently exit with a yellow warning.

**Already done in this session (2026-05-03):**
- Folded the standalone `alpha-partners-7Cs-scorecard.yaml` into the frontmatter of `alpha-partners-7Cs-scorecard.md` and deleted the `.yaml`. Verified parses with all 7 dimensions and 4 groups intact.
- Frontmatter is now the canonical structured data; markdown body remains as the human reference (rubrics duplicated for readability — drift is a known cleanup item).

## Approach

Make the scorecard schema self-describing in the `.md` frontmatter, make the agent a generic renderer, and resolve which scorecard to use from the deal JSON's `scorecard` field. No more hardcoded paths or framework-specific gates.

Architecture decisions:

- **Frontmatter is canonical.** Agent reads only the YAML frontmatter block (already in place for 7Cs). Markdown body is for humans (Obsidian-friendly).
- **Discovery by name, not path.** Deal JSON declares `scorecard: "alpha-partners-7Cs"`. A new resolver walks `{firm}/templates/scorecards/**/*.md` (and falls back to repo-root `templates/scorecards/**/*.md`) and matches on frontmatter `metadata.scorecard_id` or filename stem. Same pattern outlines already use.
- **Drop the gates.** Remove `investment_type == "fund"` and `outline_name == "lpcommit-emerging-manager"` checks in both `scorecard_agent.py` and `cli/generate_scorecard.py`. Replace with: "if the deal has a `scorecard` field, generate it."
- **Prompt builder reads frontmatter.** Group count, dimension count, scoring scale, percentile mapping, threshold rules, output format (`output_format.layout`, `output_format.rows`), and per-dimension rubrics all flow from frontmatter into the prompt template — no hardcoded structure.
- **Context sections come from frontmatter too.** Add `context_sections: [...]` (list of `2-sections/*.md` filenames to include for evidence) to each scorecard's frontmatter. Replaces the hardcoded fund-section dict.
- **Hypernova scorecard gets the same treatment.** Migrate `io/hypernova/templates/scorecards/.../hypernova-scorecard.yaml` (wherever it now lives) into `.md` + frontmatter. Same shape as 7Cs. Both frameworks should be interchangeable from the agent's POV.

## Phases

### Phase 1 — Scorecard content model (in progress)

- [x] Fold 7Cs YAML into `.md` frontmatter, delete `.yaml`, verify parse.
- [ ] Migrate Hypernova scorecard the same way (in `io/hypernova` submodule).
- [ ] Add a JSON Schema at `templates/scorecards/scorecard-schema.json` documenting the frontmatter contract (mirroring the existing `templates/outlines/sections-schema.json`).
- [ ] Add `context_sections: [...]` to both 7Cs and Hypernova frontmatter so the agent knows which section files to feed in.

### Phase 2 — Refactor the agent

- **`src/agents/scorecard_agent.py`:**
  - Replace `_load_scorecard_template()` with a generic resolver: `_resolve_scorecard(scorecard_name, firm) → (frontmatter_dict, body_markdown)`. Walks `io/{firm}/templates/scorecards/**/*.md` then repo-root, parses frontmatter.
  - Replace `_load_section_snippets()` with `_load_context_sections(output_dir, frontmatter['context_sections'])` — driven by frontmatter list, not a hardcoded dict.
  - Rewrite `_build_scorecard_prompt()` to template from `frontmatter['scoring']`, `frontmatter['dimension_groups']`, `frontmatter['dimensions']`, `frontmatter['output_format']`. No literal "12 dimensions" or named groups.
  - Drop the `investment_type != "fund"` and `outline_name != "lpcommit-emerging-manager"` early-returns. Replace with: skip if no `scorecard` field on the deal.
- **`cli/generate_scorecard.py`:**
  - Drop matching gates at `:96-105`.
  - Read `scorecard` field from the deal JSON (or via `state["scorecard_name"]`); 404 with a clear message if absent.
  - Add `--scorecard <name>` flag to override the deal's default (useful for trying a different framework on the same memo).
- **`src/state.py`:** add optional `scorecard_name: str | None` to `MemoState`; populate from deal JSON in `main.py` initial state, mirroring how `outline_name` is handled.

### Phase 3 — Apply to any version of any memo

The CLI already takes `target` (company name or path) + `--version`, so once the gates are gone it works against any artifact dir. Validation:

- [ ] Run against `io/alpha-partners/deals/Solugen/outputs/Solugen-v0.0.x/` — generates a 7Cs scorecard.
- [ ] Run against any existing Hypernova fund memo — generates the emerging-manager scorecard from the migrated `.md`.
- [ ] Run against a deal with `scorecard` set to the *other* framework — confirms full decoupling from outline.
- [ ] Add a test (when the test infra from `Wire-Memopop-Native-To-The-FastAPI-Sidecar.md` Phase 0 lands): `tests/test_scorecard_agent.py` — load each scorecard `.md`, assert frontmatter parses + has required keys.

### Phase 4 — Surface in memopop-native

Target file: `apps/memopop-native/src/routes/deals/[firm]/[deal]/+page.svelte` (or its companion `+page.ts`).

- **Where:** the deal detail page, near the existing version selector / `ArtifactBrowser.svelte`. Each version row gets a "Generate scorecard" action (icon button or menu item).
- **Component:** new `ScorecardPanel.svelte` in `apps/memopop-native/src/lib/components/` — shows the rendered `scorecard.md` if it exists, or a "Generate" CTA if it doesn't.
- **Transport:** new sidecar route `POST /memos/{id}/scorecard` that wraps a call to `scorecard_agent(state)` for the selected artifact dir. Returns `{ scorecard_path, markdown }`. SSE optional (it's a single LLM call, ~30s — sync response is fine).
- **Type:** add `ScorecardResult` to `src/lib/transport/types.ts`; `generateScorecard(jobId)` method on the Transport interface (`src/lib/transport/local.ts`); Rust dispatcher gets a new match arm forwarding to the sidecar.
- **Affordance:** in the artifact tree, when `scorecard.md` exists, render it as a tab alongside `4-final-draft.md` so reviewers can see the framework's verdict without leaving the page.

## Open questions

- **Inline vs separate output:** today the agent writes to `output/{deal}/scorecard.md`. Should it also be embeddable into the final memo (per the 7Cs `dimension_groups[].placement` instructions, which specify *where in which section* each group's table should be inserted)? Suggest deferring to Phase 4.5 — generate standalone first, embed second.
- **Schema versioning:** if frontmatter shape evolves (e.g., new `output_format.layout` values), how do we signal compat? Simplest: add `metadata.frontmatter_schema_version` and have the agent check it.
- **Body/frontmatter drift:** rubric tables exist both in frontmatter (canonical) and body (human reference). Either thin the body to a "rubrics defined in frontmatter" pointer, or accept duplication. Pick one in Phase 1 cleanup.

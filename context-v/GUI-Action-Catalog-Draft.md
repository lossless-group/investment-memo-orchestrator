---
title: "GUI Action Catalog — Draft v1"
lede: "Audit of the orchestrator's CLI surface, bucketed by GUI tier. Defines which CLIs become buttons in v1, which wait for v2/v3, and which are excluded entirely. Includes a draft gui_actions.json and a query catalog."
date_authored_initial_draft: 2026-04-26
date_authored_current_draft: 2026-04-26
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-04-26
date_modified: 2026-04-26
tags: [GUI, Tauri, CLI, Audit, Action-Catalog]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.7"
related:
  - context-v/Introducing-a-GUI-Native-Desktop-with-Tauri.md
  - context-v/Transport-Contract-and-API-Conventions.md
---

# GUI Action Catalog — Draft v1

## Method

I walked the entire CLI surface (~25 entry points across `src/`, `cli/`, `tools/`, plus shell scripts) and bucketed each into one of three tiers:

- **Tier 1**: high-frequency, stable signature, clear inputs. **Buttons in v1.**
- **Tier 2**: useful but lower-frequency, or signature still in flux. **Defer to v2.**
- **Tier 3**: one-off / debugging / migration / dev-only. **Exclude from GUI entirely.**

I also identified internal tools (called by other CLIs, never directly) and excluded them from GUI consideration.

The audit also surfaced a few **consolidation opportunities** — multiple CLIs that overlap and should appear as one button with a mode picker. Flagged below.

---

## Important Architectural Note: Firm-Scoped vs Legacy

The orchestrator runs in two modes (auto-detected by `paths.resolve_deal_context()`):

- **Firm-scoped (preferred)**: `io/{firm}/deals/{deal}/` — config, deck, dataroom, outputs all live under the deal directory. Each deal has its own `config.yaml` (or similar) carrying type, mode, outline, scorecard, trademarks.
- **Legacy**: `data/{Company}.json` flat, outputs in `output/{Company}-vX/`.

**For the GUI this matters because**: in firm-scoped mode, most parameters (type, mode, outline, scorecard, deck path) come from the deal config — the user doesn't re-enter them. The action forms reduce to ~3 fields: firm, deal, version.

The GUI should default to firm-scoped: pick "active firm" once in settings, then deal selection is a dropdown of `io/{firm}/deals/`.

---

## Tier 1: v1 Buttons (8 actions)

These ship in the first usable release.

| Action ID            | CLI Source                          | Purpose                                                  | Long-running |
| -------------------- | ----------------------------------- | -------------------------------------------------------- | ------------ |
| `generate-memo`      | `python -m src.main`                | Run the full LangGraph pipeline for a deal               | 10+ min      |
| `improve-section`    | `cli/improve_section.py`            | Rewrite one section with Perplexity Sonar Pro + citations | 1–2 min      |
| `recompile-memo`     | `cli/recompile_memo.py`             | Reassemble final draft after manual section edits         | seconds      |
| `export-branded`     | `cli/export_branded.py`             | Branded HTML/PDF/DOCX export (light/dark)                 | ~30 sec      |
| `generate-scorecard` | `cli/generate_scorecard.py`         | Hypernova emerging-manager scorecard (fund memos)         | 2–3 min      |
| `generate-one-pager` | `cli/generate_one_pager.py`         | Single-page visual investment summary                     | ~10 sec      |
| `generate-diagrams`  | `cli/generate_diagrams.py`          | TAM/SAM/SOM concentric circles into market section        | ~10 sec      |
| `generate-tables`    | `cli/generate_tables.py`            | Funding/team/traction tables into sections                | ~10 sec      |

### Consolidation Decisions for Tier 1

- **`improve-section` absorbs `improve_team_section`**: the team variant is a specialized mode of the same action. Add an optional `flavor: "default" | "team-deep-dive"` parameter. Don't make it a separate button.
- **`export-branded` is the primary export button**: covers HTML, PDF, DOCX with branding. `cli/export_formats.py` is a more generic Pandoc wrapper that's lower priority — defer to Tier 2.

---

## Tier 2: v2 Additions (8–10 actions)

These should land in v2 once the v1 surface has stabilized. Most are lower-frequency; a few have signatures that may still drift.

| Action ID                  | CLI Source                          | Purpose                                                |
| -------------------------- | ----------------------------------- | ------------------------------------------------------ |
| `refocus-section`          | `cli/refocus_section.py`            | Repair sections in `justify` mode (sparse web research) |
| `score-memo`               | `cli/score_memo.py`                 | Score memo against a named scorecard                    |
| `evaluate-memo`            | `cli/evaluate_memo.py`              | Per-section quality evaluation, issues + suggestions    |
| `enrich-section`           | `cli/enrich_links.py`               | Add organization/social hyperlinks (no rewrite)         |
| `rewrite-key-info`         | `cli/rewrite_key_info.py`           | Apply YAML-defined corrections to memo                  |
| `export-formats`           | `cli/export_formats.py`             | Pandoc multi-format export (citation-preserving)        |
| `parse-research-pdf`       | `cli/parse_research_pdf.py`         | Scrape research PDFs into markdown + citations          |
| `resume-from-interruption` | `cli/resume_from_interruption.py`   | Resume pipeline from last checkpoint after a crash      |

### Consolidation Decisions for Tier 2

- **`enrich-section` collapses `enrich_citations.py` and `enrich_links.py`** — they appear to be duplicates / variants. **Open question for you**: which is the canonical one? Pick one, retire the other, GUI exposes the survivor.
- **`refocus-section` and `improve-section` should share a single UI** with a mode picker (`improve` for prospective deals, `refocus` for retrospective). They take nearly identical params. But keep them as **separate action IDs** in the catalog — the backend logic differs enough that the API shouldn't pretend they're one.

---

## Tier 3: Excluded (no button)

These are real and useful, but they don't belong in the GUI either because they're internal glue, dev/admin tools, or one-off migrations.

### Internal glue (called by other actions; never user-facing)

- `cli/assemble_draft.py` — Final draft reassembly. Invoked internally by `improve_section`, `recompile_memo`, the pipeline.
- `cli/sanitize_commentary.py` — Strips LLM meta-commentary; runs as part of polishing flow.

### Dev / admin / one-off

- `cli/migrate_versions.py` — Legacy → firm-scoped migration. Run once, never again.
- `cli/correct_pdf_citations.py` — Research PDF citation correction. Power-user research-prep tool.
- `cli/convert_to_png.py` — Image format conversion utility. Asset prep.
- `cli/describe_all_listed_portfolio_companies.py` — Fund-only, one-shot use.
- `cli/markdown_to_pdf.py` — Subsumed by `export-branded`.
- `cli/md2docx.py` — Subsumed by `export-branded` and `export-formats`.
- `tools/validate_outlines.py` — QA / dev tool.
- `cli/export-all-html.sh`, `cli/export-all-modes.sh` — Batch dev utilities; replaceable by GUI looping.
- `cli/html-to-pdf.sh`, `cli/md-to-pdf.sh` — Wrappers for already-deferred Python tools.

### Already a UI

- `cli/terminal_app/py_rich/app.py` — The memopop interactive CLI. Don't wrap a UI in another UI; the Tauri app supersedes this.

---

## Query Catalog

These are read-only endpoints the UI calls to populate dropdowns, sidebars, and detail panes. Each maps cleanly to a filesystem read.

| Query Path                                                      | Returns                                                  | Used By                              |
| --------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------ |
| `GET /firms`                                                    | List of firm names from `io/`                            | Settings: active firm picker         |
| `GET /firms/{firm}/deals`                                       | List of deals for a firm                                 | Sidebar: deal selector               |
| `GET /firms/{firm}/deals/{deal}`                                | Deal config + summary (type, mode, outline, latest version) | Deal detail pane                  |
| `GET /firms/{firm}/deals/{deal}/versions`                       | Version history with scores                             | Version dropdown / history view      |
| `GET /firms/{firm}/deals/{deal}/versions/{v}/sections`          | List of section files                                    | Improve-section picker               |
| `GET /firms/{firm}/deals/{deal}/versions/{v}/sections/{name}`   | Section markdown content                                 | Section preview pane                 |
| `GET /firms/{firm}/deals/{deal}/versions/{v}/exports`           | List of exported artifacts (HTML/PDF/DOCX paths)         | Export pane                          |
| `GET /firms/{firm}/deals/{deal}/versions/{v}/state`             | `state.json` contents                                    | Debug pane                           |
| `GET /companies` *(legacy)*                                     | List of deals from `data/*.json`                         | Sidebar in legacy mode               |
| `GET /companies/{name}/...` *(legacy)*                          | Same shape, legacy paths                                 | Legacy support                       |
| `GET /outlines`                                                 | Available outlines (default + custom)                    | Settings: outline picker             |
| `GET /brands`                                                   | Available brand configs                                  | Export form: brand selector          |
| `GET /scorecards`                                               | Available scorecard definitions                          | Scorecard action: scorecard picker   |
| `GET /jobs`                                                     | Active + recent jobs                                     | Job history pane (v2)                |
| `GET /jobs/{jobId}`                                             | Job status snapshot                                      | Run status indicator                 |
| `GET /settings`                                                 | App settings (active firm, repo path)                    | Settings screen                      |
| `PUT /settings`                                                 | Update settings                                          | Settings screen                      |

---

## Draft `gui_actions.json` (Tier 1 only)

```json
{
  "$schema": "./gui_actions.schema.json",
  "schemaVersion": 1,
  "actions": [
    {
      "id": "generate-memo",
      "displayName": "Generate Memo",
      "description": "Run the full memo generation pipeline for a deal. Researches, drafts, validates, and finalizes all 10 sections.",
      "category": "generate",
      "icon": "sparkles",
      "longRunning": true,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "fresh", "type": "bool", "label": "Fresh start (ignore prior artifacts)", "required": false, "default": false },
        { "name": "version", "type": "string", "label": "Force version (optional, e.g., v0.1.0)", "required": false }
      ]
    },
    {
      "id": "improve-section",
      "displayName": "Improve Section",
      "description": "Rewrite one section with real-time research and citations via Perplexity Sonar Pro.",
      "category": "improve",
      "icon": "wand",
      "longRunning": true,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "section", "type": "enum", "label": "Section", "required": true, "source": "GET /firms/{firm}/deals/{deal}/versions/latest/sections" },
        { "name": "flavor", "type": "enum", "label": "Mode", "required": false, "default": "default", "enumValues": ["default", "team-deep-dive"] },
        { "name": "version", "type": "string", "label": "Version (optional)", "required": false }
      ]
    },
    {
      "id": "recompile-memo",
      "displayName": "Recompile Memo",
      "description": "Reassemble the final draft from current section files. Use after manual edits.",
      "category": "improve",
      "icon": "refresh",
      "longRunning": false,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "version", "type": "string", "label": "Version (optional)", "required": false }
      ]
    },
    {
      "id": "export-branded",
      "displayName": "Export Branded",
      "description": "Export the memo as styled HTML, PDF, or Word using a brand config.",
      "category": "export",
      "icon": "download",
      "longRunning": false,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "format", "type": "enum", "label": "Format", "required": true, "enumValues": ["html", "pdf", "docx"], "default": "pdf" },
        { "name": "brand", "type": "enum", "label": "Brand", "required": false, "source": "GET /brands" },
        { "name": "mode", "type": "enum", "label": "Color Mode", "required": false, "enumValues": ["light", "dark"], "default": "light" },
        { "name": "version", "type": "string", "label": "Version (optional)", "required": false }
      ]
    },
    {
      "id": "generate-scorecard",
      "displayName": "Generate Scorecard",
      "description": "Score the deal against the firm's scorecard framework. Best for fund memos.",
      "category": "analyze",
      "icon": "chart",
      "longRunning": true,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "version", "type": "string", "label": "Version (optional)", "required": false }
      ]
    },
    {
      "id": "generate-one-pager",
      "displayName": "Generate One-Pager",
      "description": "Render a single-page visual summary of the memo as HTML and PDF.",
      "category": "visualize",
      "icon": "page",
      "longRunning": false,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "mode", "type": "enum", "label": "Color Mode", "required": false, "enumValues": ["light", "dark"], "default": "light" },
        { "name": "version", "type": "string", "label": "Version (optional)", "required": false }
      ]
    },
    {
      "id": "generate-diagrams",
      "displayName": "Generate Diagrams",
      "description": "Extract TAM/SAM/SOM and insert concentric-circle SVG diagrams into the market section.",
      "category": "visualize",
      "icon": "circle",
      "longRunning": false,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "version", "type": "string", "label": "Version (optional)", "required": false },
        { "name": "dryRun", "type": "bool", "label": "Dry run (preview, don't write)", "required": false, "default": false }
      ]
    },
    {
      "id": "generate-tables",
      "displayName": "Generate Tables",
      "description": "Extract structured data (funding, team, traction) and insert markdown tables into sections.",
      "category": "visualize",
      "icon": "table",
      "longRunning": false,
      "parameters": [
        { "name": "firm", "type": "enum", "label": "Firm", "required": true, "source": "GET /firms" },
        { "name": "deal", "type": "enum", "label": "Deal", "required": true, "source": "GET /firms/{firm}/deals" },
        { "name": "version", "type": "string", "label": "Version (optional)", "required": false },
        { "name": "dryRun", "type": "bool", "label": "Dry run (preview, don't write)", "required": false, "default": false }
      ]
    }
  ]
}
```

### Note on Parameter Sources

The `source` field on `enum` parameters is a **query path**. The frontend, when rendering the form, calls that path to populate the dropdown. The path can include other parameter values as placeholders (`{firm}`, `{deal}`) — when the user changes those, dependent dropdowns refresh.

This is why the action catalog and the query catalog are co-designed: the actions' parameter schemas reference queries.

---

## Categories (Sidebar Grouping)

Five top-level categories in the sidebar:

1. **Generate** — `generate-memo`
2. **Improve** — `improve-section`, `recompile-memo` (Tier 2: `refocus-section`, `enrich-section`, `rewrite-key-info`)
3. **Visualize** — `generate-one-pager`, `generate-diagrams`, `generate-tables`
4. **Analyze** — `generate-scorecard` (Tier 2: `score-memo`, `evaluate-memo`)
5. **Export** — `export-branded` (Tier 2: `export-formats`)

Plus **Settings** (firm picker, repo path, API keys) as a separate sidebar item, not a category.

---

## Open Questions for You

1. **`enrich_citations.py` vs `enrich_links.py`** — which is canonical? My instinct says they overlap and one should be retired. Want me to compare them?
2. **`improve_team_section` consolidation** — should it really collapse into `improve-section --flavor team-deep-dive`, or stay separate? Depends on whether the team variant is meaningfully different in UX (different prompts, different research depth) — not just code organization.
3. **Tier 1 size: 8 actions feels right but is it the right 8?** Specifically, are `generate-diagrams` and `generate-tables` daily-use enough to be Tier 1, or should they drop to Tier 2 to keep the v1 sidebar tight? If you only run them once after a memo is drafted, Tier 2 is fine.
4. **Section list source** — the parameter source `GET /firms/{firm}/deals/{deal}/versions/latest/sections` assumes "latest" is a valid version alias. Worth supporting; flag if you'd rather always pin explicit versions.
5. **Version parameter UX** — every action has an optional `version` parameter that defaults to "latest". Is "latest" always what the user wants? Most of the time, yes. But for actions that mutate (improve, recompile), it might be worth defaulting to "latest" but warning if the user picks an older version (could overwrite history they care about).
6. **Firm-scoped vs legacy in the GUI** — should v1 support legacy mode at all, or only firm-scoped? Legacy adds complexity. If you're committed to migrating off `data/*.json` anyway, the GUI could just say "firm-scoped only" and skip the dual-path.

---

## Next Steps After This Doc

1. Resolve the open questions above.
2. Decide Tier 1 final list.
3. Implement `LocalTransport` + Rust `api_dispatch` skeleton (one route handler at a time).
4. Build the Svelte sidebar + form + log pane against the Transport interface.
5. Wire the first action end-to-end (`generate-memo` is most demanding; start there or with `recompile-memo` if you want a faster first win).

The hardest part isn't writing the GUI — it's keeping the catalog declarative and the transport seam clean. Both are now defined; the rest is execution.

<!-- GENERATED FILE — DO NOT EDIT BY HAND.
     Regenerate:  .venv/bin/python scripts/gen_pipeline_reference.py
     Prose that is not derivable from code belongs in
     docs/pipeline-reference.overlay.yaml, which this file merges in. -->

# MemoPop Orchestrator — Pipeline Reference

The single current answer to *what agents run, in what order, and what can I type at a shell*. Generated from `src/workflow.py`, `src/main.py`, and `cli/` by `scripts/gen_pipeline_reference.py`; `tests/test_pipeline_reference.py` fails when it drifts from them.

This file says what the pipeline **does**. `AGENTS.md` says how each agent must **behave** — the §1–§12 contract prepended to agent system prompts. The §-references in the table below point into it.

## The graph — 35 nodes

Entry point: **`dataroom`**. Every node runs on every invocation; see the
`--from` discussion below for why that is a problem and what is planned.

| # | Node | Stage | Module | LLM routing | Purpose | AGENTS.md |
|---|------|-------|--------|-------------|---------|-----------|
| 1 | `dataroom` | dataroom | `src/agents/dataroom/` | routed | Classify and extract every document in the dataroom; skips when no dataroom is anchored. | §7, §11 |
| 2 | `deck_analyst` | deck | `src/agents/deck_analyst.py` | routed | Read the pitch deck via Claude vision, batching page renders; skips when no deck is present. | §7, §11 |
| 3 | `research` | research | `src/agents/research_enhanced.py / src/agents/researcher.py` | routed (via Perplexity/OpenAI, Tavily) | General web research via Tavily. Node function is chosen at build time by `USE_WEB_SEARCH`; the enhanced agent is the default and the plain one is the fallback. | §2, §10, §11 |
| 4 | `section_research` | research | `src/agents/perplexity_section_researcher.py` | other provider (via Perplexity/OpenAI) | Per-section deep research through Perplexity Sonar Pro, keeping the retrieved-source array so citations reconcile. | §2, §10, §11 |
| 5 | `competitive_researcher` | research | `src/agents/competitive_landscape_researcher.py` | other provider (via Perplexity/OpenAI) | Discover competitor candidates across multiple queries. | §2, §10 |
| 6 | `competitive_evaluator` | research | `src/agents/competitive_landscape_evaluator.py` | other provider (via Perplexity/OpenAI) | Classify candidates direct/indirect/adjacent and run gap analysis. | §11 |
| 7 | `cite` | research | `src/agents/citation_enrichment.py` | other provider (via Perplexity/OpenAI) | Add inline citations to the research files, preserving existing ones. | §2, §11 |
| 8 | `cleanup_research` | research | `src/workflow.py` | no model call | GATE 1 — validate every URL in `1-research/` and remove 404s and hallucinations before the writer ever sees them. | §2 |
| 9 | `aggregate_sources` | research | `src/agents/source_aggregator.py` | no model call | Aggregate broad-search URLs into a curated `Sources.md` draft and HALT for analyst curation. In codified mode the curated list is already authoritative and the halt is skipped. This is the seam the closed corpus depends on. | §2 |
| 10 | `draft` | write | `src/agents/writer.py` | routed | Write each section in isolation from the outline and the codified research. The writer has no search tool. | §1, §3, §4, §5, §6, §7, §9 |
| 11 | `inject_deck_images` | write | `src/agents/inject_deck_images.py` | no model call | Place deck screenshots into the section files. | §12 |
| 12 | `enrich_trademark` | write | `src/agents/trademark_enrichment.py` | no model call | Insert the company trademark into the header. | §12 |
| 13 | `enrich_socials` | write | `src/agents/socials_enrichment.py` | other provider (via Tavily) | Attach LinkedIn and professional profile links to named team members. | §12 |
| 14 | `enrich_links` | write | `src/agents/link_enrichment.py` | routed | Hyperlink named organizations, investors, and partners. | §12 |
| 15 | `generate_tables` | write | `src/agents/table_generator.py` | routed | Build markdown tables from structured state data and section prose. | §3, §12 |
| 16 | `generate_diagrams` | write | `src/agents/diagram_generator.py` | no model call | Render diagrams — TAM/SAM/SOM concentric circles, funnels, and similar. | §12 |
| 17 | `enrich_visualizations` | write | `src/agents/visualization_enrichment.py` | routed (via Perplexity/OpenAI) | Find and embed supporting visualizations. Currently disabled. | §12 |
| 18 | `revise_summaries` | write | `src/agents/revise_summary_sections.py` | bypasses (1× `ChatAnthropic()`) | Rewrite the Executive Summary and Closing Assessment against the complete draft, which is the only point either can be accurate. | §3, §6, §9 |
| 19 | `cleanup_sections` | assemble | `src/agents/remove_invalid_sources.py` | no model call | GATE 2 — validate every URL in `2-sections/`, catching anything enrichment or revision introduced. | §2 |
| 20 | `assemble_citations` | assemble | `src/agents/citation_assembly.py` | no model call | Consolidate citations, renumber globally, and create the final draft file. Reads definitions from `1-research/` as a fallback. | §9 |
| 21 | `fix_citation_spacing` | assemble | `src/agents/citation_spacing.py` | no model call | Normalise citation marker spacing in the assembled draft. | §9 |
| 22 | `validate_citations` | assemble | `src/agents/citation_validator.py` | no model call | Check citation accuracy, dates, and duplicates in the assembled draft. | §2, §9 |
| 23 | `fact_check` | assemble | `src/agents/fact_checker.py` | no model call | Mechanical claim extraction. Currently reads `state["research"]` — the legacy blob — rather than the codified corpus the writer actually used; see `context-v/issues/Validation-and-Fact-Checker-not-using-Research.md`. | §2, §11 |
| 24 | `attribution_audit` | assemble | `src/agents/attribution_audit.py` | no model call | Flag claims whose numbers are real but attributed to the wrong company. The gate that actually tests truth. | §7, §11 |
| 25 | `fact_verify` | assemble | `src/agents/fact_verifier.py` | other provider (via Perplexity/OpenAI) | Verify extracted claims against sources via Perplexity. | §2, §11 |
| 26 | `fact_correct` | assemble | `src/agents/fact_corrector.py` | bypasses (1× `Anthropic()`) | Apply verified corrections back to the section files — not to the assembled draft. | §2, §7, §11 |
| 27 | `source_catalog` | assemble | `src/agents/source_cataloger.py` | no model call | Compile the complete per-section source list. | §2 |
| 28 | `validate` | assemble | `src/agents/validator.py` | routed | Score the memo 0-10 against the style guide. Sees only the memo and the style guide — no research, no source catalog — and runs three nodes before the draft is rebuilt, so it critiques an artifact that no longer exists. Both defects tracked in the validation issue. | §1, §11 |
| 29 | `scorecard` | assemble | `src/agents/scorecard_evaluator.py` | routed | Evaluate against the firm's scorecard template. | §11 |
| 30 | `integrate_scorecard` | assemble | `src/workflow.py` | no model call | Insert the scorecard into its section and reassemble the final draft. | §9 |
| 31 | `scorecard_nav` | assemble | `src/agents/scorecard_navigator.py` | no model call | Insert the scorecard overview table into the Executive Summary. | §9 |
| 32 | `toc` | assemble | `src/agents/toc_generator.py` | no model call | Generate the table of contents. The final content step — everything that mutates headings must already have run. | §9 |
| 33 | `one_pager` | export | `src/agents/one_pager_generator.py` | bypasses (2× `Anthropic()`) | Generate the single-page visual cover summary. | §6 |
| 34 | `finalize` | export | `src/workflow.py` | no model call | Verify the final draft and save the state snapshot. Reached when the validator scores 8 or above. | §8 |
| 35 | `human_review` | export | `src/workflow.py` | no model call | Prepare the memo for human review with issues and suggestions. Reached when the validator scores below 8. | §5 |

## Stages

The stage column groups nodes into the resume points the operator actually thinks in. These are the candidate values for the proposed `--from <stage>` flag.

| Stage | Nodes | Artifacts it owns | What entering here means |
|-------|------:|-------------------|--------------------------|
| `dataroom` | 1 | `0-dataroom/`, `_zip-originals/normalized.json` | Full re-extraction of the deal's document set. The most expensive entry point; only correct when documents were added or changed. |
| `deck` | 1 | `.cache/deck-<fingerprint>/` | Re-analyse the pitch deck via Claude vision. Correct when the deck itself was replaced — not when it was merely compressed by asset normalization. |
| `research` | 7 | `1-research/`, `inputs/Sources.md`, `3-source-catalog/` | Re-perform web research only. Additive by contract — net-new sources and the findings drawn from them are appended to the existing research files under a provenance stamp; nothing already recorded is overwritten. Takes a thesis frame as its argument for what to look for. |
| `write` | 9 | `2-sections/` | No web search at all. The prior analysts' paper trail is the input and it is sufficient; the job is re-synthesis of sections, not re-gathering. The frame's per-section directives (rewrite / amend / re-score / unchanged) describe exactly this. |
| `assemble` | 14 | `4-fact-check.json`, `3-validation.md`, `5-scorecard/`, the assembled `7-*.md` | Rebuild the draft from existing sections and re-run the quality gates. No new prose, no new research — citation consolidation, fact gates, scorecard. |
| `export` | 3 | `6-one-pager.md`, `exports/`, state snapshot | Cover sheet and final disposition from a draft that is already complete. |

## Execution order

```
 1. dataroom
 2. deck_analyst
 3. research
 4. section_research
 5. competitive_researcher
 6. competitive_evaluator
 7. cite
 8. cleanup_research
 9. aggregate_sources
10. draft
11. inject_deck_images
12. enrich_trademark
13. enrich_socials
14. enrich_links
15. generate_tables
16. generate_diagrams
17. enrich_visualizations
18. revise_summaries
19. cleanup_sections
20. assemble_citations
21. fix_citation_spacing
22. validate_citations
23. fact_check
24. attribution_audit
25. fact_verify
26. fact_correct
27. source_catalog
28. validate
29. scorecard
30. integrate_scorecard
31. scorecard_nav
32. toc
33. one_pager

    one_pager ──(should_continue)──┬─▶ finalize
                                   └─▶ human_review

    finalize, human_review ──▶ END
```

## LLM routing inventory

`src/llm_provider.py` tries the local Claude Code seat first and falls back to the metered API with a warning. Modules that construct `ChatAnthropic(...)` or `anthropic.Anthropic(...)` themselves bill the API unconditionally and cannot use the seat — the defect tracked in `context-v/issues/Route-Every-Claude-Call-Through-The-CLI-First-Provider.md`. Counts below are live.

| Routing | Nodes | Meaning |
|---------|-------|---------|
| **routed** | 9 | goes through `llm_provider` — can use the seat |
| **bypasses** | 3 | builds an Anthropic client directly — always metered |
| **other provider** | 6 | no Anthropic client; calls Perplexity/Tavily/Firecrawl |
| **no model call** | 17 | no model or retrieval client in the node's own modules |

Across all of `src/`: **9 modules / 10 call sites** construct a client directly; **20 modules** route through `llm_provider`.

| Module | Sites | Constructs |
|--------|------:|------------|
| `src/agents/one_pager_generator.py` | 2 | 2× `Anthropic()` |
| `src/agents/citation_corrector.py` | 1 | 1× `Anthropic()` |
| `src/agents/fact_corrector.py` | 1 | 1× `Anthropic()` |
| `src/agents/key_info_rewrite.py` | 1 | 1× `Anthropic()` |
| `src/agents/portfolio_listing_agent.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/revise_summary_sections.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/scorecard_agent.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/source_extractor.py` | 1 | 1× `ChatAnthropic()` |
| `src/server/brand_fetch.py` | 1 | 1× `Anthropic()` |

<details><summary>Modules already routing through <code>llm_provider</code></summary>

- `src/agents/codified_section_researcher.py`
- `src/agents/dataroom/document_classifier.py`
- `src/agents/dataroom/extractors/cap_table_extractor.py`
- `src/agents/dataroom/extractors/competitive_extractor.py`
- `src/agents/dataroom/extractors/financial_extractor.py`
- `src/agents/dataroom/extractors/legal_extractor.py`
- `src/agents/dataroom/extractors/team_extractor.py`
- `src/agents/dataroom/extractors/traction_extractor.py`
- `src/agents/deck_analyst.py`
- `src/agents/link_enrichment.py`
- `src/agents/perplexity_sources.py`
- `src/agents/research_enhanced.py`
- `src/agents/researcher.py`
- `src/agents/scorecard_evaluator.py`
- `src/agents/slides/slide_stenographer.py`
- `src/agents/slides/visual_collector.py`
- `src/agents/table_generator.py`
- `src/agents/validator.py`
- `src/agents/visualization_enrichment.py`
- `src/agents/writer.py`

</details>

## `python -m src.main` — the main entry point

| Flag | Choices / default | Help |
|------|-------------------|------|
| `company_name` | — | Name of the company to analyze |
| `--type` | direct/fund, default `direct` | Type of investment: 'direct' for startup investments, 'fund' for LP commitments (default: direct) |
| `--mode` | consider/justify, default `consider` | Memo mode: 'consider' for prospective analysis, 'justify' for retrospective justification (default: consider) |
| `--resume` | flag | Resume from last checkpoint if available (skips completed agents) |
| `--version` | — | Force a specific version (e.g., v0.1.0). With --resume, resumes that version. Without --resume, creates a new run at that version. |
| `--fresh` | flag | Start from a clean slate: ignore prior artifacts and research, generate everything from scratch. |
| `--firm` | — | Firm name for firm-scoped IO (e.g., 'hypernova'). Uses io/{firm}/deals/{deal}/ structure. |
| `--deal` | — | Deal name (alternative to positional company_name argument) |
| `--frame` | — | Thesis frame slug under io/{firm}/deals/{deal}/frames/. Reframes both research and writing for the sections the frame declares. Research is additive: `extend` appends to the existing 1-research file and never rewrites it. Omit for today's behaviour. |
| `--list-frames` | flag | List the thesis frames available for this deal and exit. |

## Standalone CLI tools

Every executable under `cli/`, `cli/utils/`, and `src/cli/`. Purpose is each file's own docstring — a tool with a blank cell has no docstring, which is itself the finding.

### `cli/`

| Tool | Flags | Purpose |
|------|-------|---------|
| `cli/_docsend_diag.py` | — | Diag v2 — anti-WAF + form-scoped gate selectors + post-submit DOM dump. |
| `cli/assemble_draft.py` | `target` · `--version` | Assemble Final Draft from Section Files. |
| `cli/capture_docsend.py` | `--url`, `--out`, `--email`, `--passcode`, `--max-pages`, `--keep-pngs` | Capture a DocSend deck to a single PDF. |
| `cli/convert_to_png.py` | `input` · `-o`, `-q`, `-b` | Convert images to PNG with transparency preservation. |
| `cli/correct_pdf_citations.py` | `pdf_path` · `-o`, `--model`, `-v` | CLI tool for scraping research PDFs and correcting citations with LLM. |
| `cli/describe_all_listed_portfolio_companies.py` | `target` · `--version` | Describe all portfolio companies listed in a fund's deck/state artifacts. |
| `cli/enrich_citations.py` | `company_or_path`, `section` · `--version`, `--no-reassemble` | Citation Enrichment CLI Tool. |
| `cli/enrich_links.py` | `company_or_path`, `section` · `--version`, `--no-reassemble`, `--orgs-only`, `--socials-only` | Link Enrichment CLI Tool. |
| `cli/evaluate_memo.py` | `company_or_path` · `--version`, `--output`, `--brief` | Standalone memo evaluation tool. |
| `cli/export-all-html.sh` | — | Export all highest-version memos to HTML with citations |
| `cli/export-all-modes.sh` | — | Export all investment memos in both light and dark modes |
| `cli/export_branded.py` | `input` · `--firm`, `--deal`, `--version`, `-o`, `--brand`, `--pdf`, `--all`, `--mode` | Branded Memo Exporter - Multi-Brand Support |
| `cli/export_formats.py` | `input` · `-o`, `--format` | Multi-format memo exporter that preserves citations. |
| `cli/export_web.py` | `input` · `--brand`, `--firm`, `--mode`, `--output` | Export a memo as a WEBPAGE — distinct from the document/PDF export. |
| `cli/extract_team_roster.py` | `--url`, `--name`, `--description`, `--from-memo`, `--output-dir`, `--refresh`, `--no-enrich`, `--allow-linkedin-photo`, `--dry-run` | Extract a structured TeamRoster from any organization URL. |
| `cli/generate_diagrams.py` | `target` · `--version`, `--firm`, `--tam`, `--sam`, `--som`, `--dry-run` | Diagram Generator CLI Tool. |
| `cli/generate_one_pager.py` | `company_or_path` · `--version`, `--firm`, `--brand`, `--mode`, `--dry-run` | One-Pager Generator CLI Tool. |
| `cli/generate_scorecard.py` | `target` · `--version` |  |
| `cli/generate_tables.py` | `company_or_path` · `--version`, `--firm`, `--dry-run` | Table Generator CLI Tool. |
| `cli/html-to-pdf.sh` | — | HTML to PDF Converter using WeasyPrint |
| `cli/improve_section.py` | `target`, `section` · `--firm`, `--deal`, `--version`, `--message` | Improve or complete a specific section of an investment memo using Perplexity Sonar Pro. |
| `cli/improve_team_section.py` | `target` · `--version` | Improve the Team section using structured, sequential research. |
| `cli/markdown_to_pdf.py` | `input` · `--mode`, `--output` | Markdown to PDF Converter with Hypernova Branding |
| `cli/md-to-pdf.sh` | — | Markdown to PDF Converter with Hypernova Branding |
| `cli/md2docx.py` | `input` · `-o`, `--no-recursive`, `--toc`, `--reference-doc`, `--no-auto-install` | Markdown to Word (.docx) Converter |
| `cli/migrate_versions.py` | `--firm`, `--deals`, `--legacy-file`, `--io-root`, `--dry-run` | Migration script to split legacy versions.json into firm-scoped versions. |
| `cli/parse_research_pdf.py` | `pdf_paths` · `-o`, `--no-tables`, `-v` | CLI tool for scraping research PDFs into markdown with citations. |
| `cli/recompile_memo.py` | `target` · `--firm`, `--deal`, `--version` | Recompile a memo from sections and consolidate citations. |
| `cli/refocus_section.py` | `target`, `section` · `--firm`, `--deal`, `--version` | Refocus or repair a specific memo section when web research is thin or noisy. |
| `cli/resume_from_interruption.py` | `company_name` · `--firm`, `--deal`, `--version` | Resume workflow from last interruption. |
| `cli/rewrite_key_info.py` | `--corrections`, `--preview`, `--output-mode`, `--source-version`, `--source-path` | Correct crucial information in investment memos using YAML correction files. |
| `cli/sanitize_commentary.py` | `company_or_path` · `--firm`, `--deal`, `--version`, `--preview`, `--reassemble`, `--no-reassemble` | Sanitize Commentary CLI |
| `cli/score_memo.py` | `company` · `--firm`, `--deal`, `--version`, `--scorecard`, `--output`, `--model` | CLI tool for scoring an existing memo against a scorecard. |
| `cli/triage_sources.py` | `--firm`, `--deal`, `--version`, `--apply`, `--sources-file`, `--workers` | Triage a deal's curated source set before an analyst reviews it. |

### `cli/utils/`

| Tool | Flags | Purpose |
|------|-------|---------|
| `cli/utils/consolidate_citations.py` | `input` · `-o`, `--dry-run` | Consolidate section-level citations to the bottom of a markdown file. |
| `cli/utils/fix_citations.py` | `input` · `-o`, `--dry-run` | Fix duplicate citations in HTML exports to match Obsidian-style behavior. |
| `cli/utils/fix_markdown_citations.py` | `input` · `-o`, `--dry-run` | Consolidate duplicate citations in Markdown files. |
| `cli/utils/hydrate_section_citations.py` | `input` · `--firm`, `--deal`, `--version`, `--dry-run` | Hydrate per-section ### Citations blocks from 1-research/*-research.md. |
| `cli/utils/restore_uncited_footnotes.py` | `html_file`, `markdown_file` · `--dry-run` | Restore unreferenced footnotes to HTML that Pandoc excluded. |

### `src/cli/`

| Tool | Flags | Purpose |
|------|-------|---------|
| `src/cli/revise_summaries.py` | `company` · `--version`, `--firm`, `--dry-run` | CLI tool to revise Executive Summary and Closing Assessment based on complete memo. |

### Installed console scripts

From `pyproject.toml` `[project.scripts]`:

- `memopop` → `cli.terminal_app.py_rich.app:main`
- `memopop-server` → `src.server.app:run`

## Notes

### The graph has no entry point but the first one

`set_entry_point("dataroom")` is unconditional, and every node runs on every
invocation. The only thing making a re-run cheap is a content-hash cache inside
each agent — and content-hash caching is not a resume mechanism. Ordinary
maintenance (compressing an oversized deck, parking media as transcripts)
changes the bytes without changing the content, the cache orphans itself, and
the pipeline silently redoes settled work. The `stage` column above is the
proposed fix: an explicit, operator-chosen `--from <stage>`, where everything
before the named stage is *not run* rather than *cheaply re-run if a hash
matches*. Tracked in
`context-v/issues/Agent-Sequencing-For-Deals-We-Already-Have-Content-On.md`.

### Two anti-hallucination gates

`cleanup_research` (GATE 1) runs after citation enrichment and before the
writer, so the writer never sees an unverified URL. `cleanup_sections`
(GATE 2) runs after revision and before assembly, catching anything the
enrichment passes introduced. Both are structural, not prompted.

### Where the older references went

`docs/COMMANDS_CHEAT_SHEET.md`, `WARP.md`, and the README's *CLI Tools
Reference* / *Pipeline Agents Reference* tables all predate the firm-scoped IO
system, codified mode, and thesis frames. They are superseded by this file for
anything a machine can verify; the cheat sheet remains useful for its worked
examples.

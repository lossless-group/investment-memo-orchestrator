---
title: "Route Every Claude Call Through the CLI-First Provider"
lede: "A provider layer exists that tries the local Claude Code seat first and falls back to the metered API, printing a warning when it does. Ten files use it. Nineteen do not — they construct ChatAnthropic or an Anthropic client directly and bill the API unconditionally, which is why a run with a zero credit balance died on the deck analyst while the dataroom extractors beside it were routing correctly."
date_authored_initial_draft: 2026-09-10
date_authored_current_draft: 2026-09-10
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-09-10
at_semantic_version: 0.0.1.0
usage_index: 1
publish: false
category: Specification
date_created: 2026-09-10
date_modified: 2026-09-10
tags: [LLM-Provider, Claude-Code-CLI, Anthropic-API, Cost, Refactor, Billing]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: a322e4c6-d869-428f-9a0a-3b8d45344803
hex_code: m1xtyl
status: Resolved
severity: High
---

# Route Every Claude Call Through the CLI-First Provider

## Status — Resolved 2026-09-10

**Zero modules under `src/` construct an Anthropic client.** All 30 that call a
model route through `src/llm_provider.py`. The generated inventory in
`docs/PIPELINE-REFERENCE.md` now reads *"nothing constructs a client directly"*,
and `tests/test_pipeline_reference.py` enforces it absolutely — `KNOWN_BYPASSING`
is empty, with a second test asserting it stays that way, so re-populating the
allowlist cannot quietly re-open the hole.

Landed in seven commits across one day, in the order this issue proposed:

| Step | Modules | Notes |
|---|---|---|
| 1 | `deck_analyst` | 4 sites, the only image path; renders now land on disk because the CLI reads images with its own Read tool |
| 2 | the five single-call agents | surfaced `detect_prose_tables`, which had never produced a table |
| 3 | the writer + three researchers | `complete_with_retry` replaced three retry loops that were about to go dead |
| 4 | the sourcing trio | exposed a six-thread race on the isolated CLI working directory |
| 5 | the two correction agents | one built its client at import time |
| 6 | one-pager, scorecard, portfolio | and `main.py`, which exited 1 without an API key |
| 7 | `server/brand_fetch.py` | tool-use loop replaced; Brandfetch supplies the facts it used to guess |

**The finding that mattered most is not in this issue's original diagnosis.**
`cli_available()` was `shutil.which("claude")`, and the FastAPI sidecar inherits
a Finder-launched app's `PATH`, where `claude` is absent. Every routed call from
the desktop app was still billing the metered API. See
[[The-Sidecar-Cannot-See-The-Claude-CLI-On-PATH]] — without that fix this entire
refactor was inert in the shipped product.

Two guards that silently disabled features rather than failing are worth naming,
because both would have survived a code review: `codified_section_researcher`
downgraded to a raw source dump without an API key, and `fact_corrector`
discarded every computed correction. Neither said anything an operator would
notice in a run that prints hundreds of lines.


## The intended behaviour, which already exists

`src/llm_provider.py:call()` implements it correctly:

```python
# auto: the seat first, credits second, and say so when it falls through.
if cli_available():
    response = _via_cli(prompt, images, model, timeout)
    if response.ok:
        return response
    fallback = _via_api(prompt, images, max_tokens, model)
    print(f"   ⚠️  CLI call failed ({response.error}); billing the API key instead")
    return fallback
```

`MEMOPOP_LLM_PROVIDER` selects `cli`, `api`, or `auto` (default). The fallback is
loud on purpose — an operator should never discover after the fact that a run
was metered.

## What actually happens

**Ten files route through it. Nineteen bypass it**, constructing
`ChatAnthropic(...)` or `anthropic.Anthropic(...)` and calling
`client.messages.create(...)` directly. Those calls always bill the API, cannot
use the seat, and produce a raw provider error rather than a fallback.

### Routing correctly

```
src/agents/dataroom/document_classifier.py
src/agents/dataroom/extractors/{cap_table,competitive,financial,legal,team,traction}_extractor.py
src/agents/perplexity_sources.py
src/agents/slides/{slide_stenographer,visual_collector}.py
```

### Bypassing — 19 call sites across 18 modules (was 23 across 19)

**This table is now generated.** The authoritative, live version is the *LLM
routing inventory* section of `docs/PIPELINE-REFERENCE.md`, produced by
`scripts/gen_pipeline_reference.py` from the AST. Regenerate it rather than
editing the table below; the counts here are a 2026-09-10 snapshot kept so the
issue reads standalone.

| File | Sites | Constructs |
|---|---:|---|
| ~~`src/agents/deck_analyst.py`~~ | ~~4~~ | **routed — done** |
| `src/agents/one_pager_generator.py` | 2 | 2× `Anthropic()` |
| `src/agents/citation_corrector.py` | 1 | 1× `Anthropic()` |
| `src/agents/codified_section_researcher.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/fact_corrector.py` | 1 | 1× `Anthropic()` |
| `src/agents/key_info_rewrite.py` | 1 | 1× `Anthropic()` |
| `src/agents/link_enrichment.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/portfolio_listing_agent.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/research_enhanced.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/researcher.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/revise_summary_sections.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/scorecard_agent.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/scorecard_evaluator.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/source_extractor.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/table_generator.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/validator.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/visualization_enrichment.py` | 1 | 1× `ChatAnthropic()` |
| `src/agents/writer.py` | 1 | 1× `ChatAnthropic()` |
| `src/server/brand_fetch.py` | 1 | 1× `Anthropic()` |

#### Corrections to the original hand-count (2026-09-10)

The headline — **19 files, 24 call sites** — was right. Three rows were not, and
they cancelled out, which is exactly why nobody caught them:

| File | Was | Is | Why |
|---|---:|---:|---|
| `src/agents/socials_enrichment.py` | 1 | **0** | Imports `ChatAnthropic` at line 11 and never instantiates it. The agent is Tavily-only. The import is dead — see [[Dead-ChatAnthropic-Import-In-Socials-Enrichment]]. |
| `src/agents/citation_corrector.py` | 2 | **1** | One `Anthropic()`, in the client factory at line 33. |

So the corrected pre-refactor figure is **23 call sites across 19 modules**, not
24 across 19. `socials_enrichment.py` drops off the work list entirely.

**A third row was briefly recorded here as a correction and was itself wrong.**
`portfolio_listing_agent.py` was reported as having 2 sites; it has 1, at line
169. The first version of the generated scan matched `ChatAnthropic` and
`Anthropic` with a regex over raw source, and line 25 of that file is a docstring
reading `Anthropic (ChatAnthropic), similar to other agents` — a bare `Anthropic`
followed by whitespace and an open paren. The scan now matches `ast.Call` nodes
instead of source text, which cannot see prose. Worth remembering when reading
any inventory: the counting method is part of the claim.

#### Step 1 is done — `deck_analyst.py`

All four sites routed through `llm_provider.complete()`:

| Was | Now |
|---|---|
| `Anthropic()` → `identify_visual_pages` (page classification) | `complete(prompt, images=[...])` |
| `ChatAnthropic()` + `llm.invoke` (deck text analysis) | `complete(prompt, timeout=_TEXT_TIMEOUT)` |
| `Anthropic()` → batched slide vision, 5 per batch | `complete(prompt, images=[...], timeout=_VISION_TIMEOUT)` |
| `ChatAnthropic()` → `create_initial_section_drafts` | parameter removed; helper calls `complete()` |

Three things the refactor forced, which the remaining files will not need:

1. **Images move from bytes to paths.** Both vision paths base64-encoded renders
   straight into an API payload. The CLI cannot be handed bytes — it reads images
   with its own Read tool from a directory granted via `--add-dir` — so renders
   now land on disk via `_render_pages_to_files()` and the API fallback
   re-encodes from the same files. Both providers see identical input.
2. **The `llm` parameter went away rather than being threaded.** A
   `ChatAnthropic` instance was being passed into `create_initial_section_drafts`
   and `create_section_draft_from_deck`. `complete()` is a function, so the
   parameter was deleted; nothing outside the module called either helper.
3. **Vision needs its own timeout.** The CLI costs a Read round-trip per slide on
   top of the completion, so a 5-slide batch at the 300s extractor default would
   time out in a way indistinguishable from a model failure. `_VISION_TIMEOUT`
   is 900s, `_TEXT_TIMEOUT` 240s.

Failure handling changed shape too. A batch that fails now prints the provider
alongside the error and `continue`s, so a run that loses every batch to a billing
error says *billing* rather than `No batches were successfully analyzed`. A
failed section draft returns an `<insufficient-data />` marker rather than
apologetic prose, per `AGENTS.md` §5.

#### The count cannot drift again

`tests/test_pipeline_reference.py` carries `KNOWN_BYPASSING`, a frozen
module→count map. The suite fails when a twentieth module appears, when a listed
module grows a call site, and when a module is fixed but not struck from the
list. The number only moves down, and striking a line is part of finishing each
step of the refactor below.

That is the writer, the researcher, the validator, the scorecard, every
enrichment agent, and the deck analyst — most of the money in a run.

## How it surfaced

ProfileHealth v0.0.4, on an account with a zero credit balance. The dataroom
extractors behaved correctly, degrading with a warning per document:

```
⚠️  CLI call failed (exit 1: ⚠ claude.ai connectors are disabled because
   ANTHROPIC_API_KEY … takes precedence over your claude.ai login);
   billing the API key instead
```

The deck analyst, three lines later, produced a raw 400 and no output:

```
ERROR: Batch 1 failed: Error code: 400 — 'Your credit balance is too low to
access the Anthropic API.'   ×5
Merging 0 batch analyses...
ERROR: No batches were successfully analyzed
```

Same run, same credentials, opposite behaviour — one path routes, the other
does not.

## Already fixed, and worth knowing

`_via_cli` inherited the parent environment, so the CLI saw `ANTHROPIC_API_KEY`,
refused to load claude.ai connectors, exited 1, and **every** routed call fell
through to the API. The seat was never being used even by the ten files that
route. Fixed in `src/llm_provider.py` (`_cli_env`) by stripping
`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`,
`CLAUDE_CODE_USE_BEDROCK` and `CLAUDE_CODE_USE_VERTEX` from the subprocess
environment. Verified against a live call: exit 0, correct output, no warning.

So the routing layer is now genuinely working. The remaining work is getting the
other nineteen files to use it.

## What makes this a real refactor rather than a find-and-replace

1. **`ChatAnthropic` is a LangChain object, not a function call.** Agents build
   it once and invoke it repeatedly, sometimes passing it to helpers
   (`deck_analyst.create_section_draft_from_deck(llm, ...)`,
   `create_initial_section_drafts(deck_analysis, state, llm)`). Replacing it
   means changing signatures, not just call sites.
2. **Images.** The deck analyst sends PDF page renders. `llm_provider.call()`
   takes `images` and the two paths differ — the CLI reads them from disk and
   needs `--add-dir`, the API base64-encodes them. Already implemented; needs
   testing at deck volume (24 slides in 5 batches).
3. **Structured output.** Several agents rely on the model returning JSON and
   parse it themselves. `llm_provider` returns an `LLMResponse` with `.text` and
   `.ok`; the JSON-shaped prompting and parsing has to move with the call.
4. **Timeouts.** `_via_cli` takes a timeout and abandons the call; `ChatAnthropic`
   has its own retry semantics. Long single calls (a full memo section) may need
   a longer timeout than the extractor default.
5. **`src/server/brand_fetch.py`** runs inside the FastAPI sidecar, not the
   graph. Confirm the CLI is reachable in that context before switching it.

## Suggested order

1. **`deck_analyst.py` first** — 4 sites, the one that failed, and the only image
   path. Proves the hardest case.
2. **The single-call agents** — validator, scorecard, table generator,
   enrichments. Mechanical once the pattern is set.
3. **The writer and researchers** — highest volume, most JSON parsing, most care.
4. **`brand_fetch.py`** last, after confirming the sidecar can reach the CLI.

Add a regression test asserting no `ChatAnthropic(` or `anthropic.Anthropic(`
outside `llm_provider.py`, so the fix does not erode.

## Related

- [[Agent-Sequencing-For-Deals-We-Already-Have-Content-On]] — the other half of
  why the v0.0.4 run died. The deck analyst should not have been running at all;
  a stale cache made it run, and this issue made it fail.
- [[Thesis-Frames-And-The-Re-Angle-Run]] — `context-v/specs/`. Blocked behind both.
- `src/llm_provider.py` — the provider layer, its docstring, and `_cli_env`.
- `AGENTS.md` — the runtime contract for pipeline agents.

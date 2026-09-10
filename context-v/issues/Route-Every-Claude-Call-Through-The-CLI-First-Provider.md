---
title: "Route Every Claude Call Through the CLI-First Provider"
lede: "A provider layer exists that tries the local Claude Code seat first and falls back to the metered API, printing a warning when it does. Ten files use it. Nineteen do not — they construct ChatAnthropic or an Anthropic client directly and bill the API unconditionally, which is why a run with a zero credit balance died on the deck analyst while the dataroom extractors beside it were routing correctly."
date_authored_initial_draft: 2026-09-10
date_authored_current_draft: 2026-09-10
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
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
status: Open
severity: High
---

# Route Every Claude Call Through the CLI-First Provider

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

### Bypassing — 24 call sites across 19 files

| File | Sites |
|---|---:|
| `src/agents/deck_analyst.py` | 4 |
| `src/agents/citation_corrector.py` | 2 |
| `src/agents/one_pager_generator.py` | 2 |
| `src/agents/writer.py` | 1 |
| `src/agents/researcher.py` | 1 |
| `src/agents/research_enhanced.py` | 1 |
| `src/agents/codified_section_researcher.py` | 1 |
| `src/agents/validator.py` | 1 |
| `src/agents/scorecard_agent.py` | 1 |
| `src/agents/scorecard_evaluator.py` | 1 |
| `src/agents/table_generator.py` | 1 |
| `src/agents/link_enrichment.py` | 1 |
| `src/agents/socials_enrichment.py` | 1 |
| `src/agents/source_extractor.py` | 1 |
| `src/agents/fact_corrector.py` | 1 |
| `src/agents/key_info_rewrite.py` | 1 |
| `src/agents/revise_summary_sections.py` | 1 |
| `src/agents/visualization_enrichment.py` | 1 |
| `src/agents/portfolio_listing_agent.py` | 1 |
| `src/server/brand_fetch.py` | 1 |

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

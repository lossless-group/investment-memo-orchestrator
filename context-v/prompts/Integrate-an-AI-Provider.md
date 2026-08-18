---
site_uuid: 262cb70c-2497-43c4-b722-d81abdb61190
hex_code: oyjnml
title: Integrate an AI Provider
lede: >-
  There is no provider abstraction here — 36 client constructions across 29 agent files — so "add Gemini" first means building the seam.
summary: "Reusable operator prompt for adding a new LLM/search provider to memopop-orchestrator. Invoked as \"Add <provider>\" and runs to completion — integration plus a passing live smoke test — without stopping for confirmation at each step. Encodes the current (absent) provider architecture, the exact call-site inventory an integration must cover, the per-provider smoke-test convention set by tools/test_anthropic.py and tools/test_perplexity.py, and the definition of done. Seeded 2026-08-17 during the context-v frontmatter sweep."
status: Draft
publish: false
date_created: 2026-05-08
date_modified: 2026-08-17
date_authored_initial_draft: 2026-08-17
date_authored_current_draft: 2026-08-17
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5 (1M context)
at_semantic_version: 0.0.1.0
tags:
  - Prompt
  - Reusable-Prompt
  - MemoPop
  - Providers
  - LLM-Integration
---

# Integrate an AI Provider

**Invocation:** *"Add Gemini"* — or any provider name.

**Contract:** run the whole procedure. Do not stop to confirm between steps. Do
not report success until a smoke test has passed **against the live API**, not
against a mock.

---

## Read this first — there is no provider layer

This is the single fact that determines how much work "add a provider" is.
Verified 2026-08-17:

| Construction | Sites | Where |
|---|---|---|
| `ChatAnthropic(...)` | 17 | LangChain path — writer, validator, table_generator, scorecard_agent, scorecard_evaluator, link_enrichment, codified_section_researcher |
| `Anthropic(...)` | 12 | raw SDK path — fact_corrector, citation_corrector, one_pager_generator |
| `OpenAI(...)` | 7 | **pointed at Perplexity**, not OpenAI — perplexity_section_researcher, competitive_landscape_{researcher,evaluator}, citation_enrichment |

**36 client constructions across 29 files.** There is no `providers/` module, no
factory, no registry. Model ids are string literals at the call site
(`claude-sonnet-4-5-20250929`, `claude-haiku-4-5-20251001`, `sonar-pro`).

Note the third row: the OpenAI SDK is already used as a *transport* for a
non-OpenAI provider via `base_url`. Many providers (including Gemini) expose an
OpenAI-compatible endpoint, and that is usually the cheapest integration path.

### Step 0 — decide the shape, then say which you chose

Before touching code, pick one and state it:

- **(a) Narrow** — wire the provider into the specific agents that need it.
  Correct when the provider is for one job (e.g. a search provider used by two
  researchers). Touches few files.
- **(b) Seam-first** — introduce the provider abstraction that should exist, then
  add the provider through it. Correct when the provider is a general-purpose LLM
  meant to be swappable with Anthropic. **Much larger diff, and it is a refactor
  of 29 files — say so explicitly and get a yes before proceeding.**

Do not silently do (b) when asked for (a). Do not do a half-(b) that leaves two
competing patterns.

---

## Procedure

1. **Read the provider's current docs.** Do not integrate from memory — SDK names
   and model ids change. For Gemini: <https://ai.google.dev/gemini-api/docs/libraries>.
   Establish: package name, client construction, auth env var, current model ids,
   and whether an OpenAI-compatible endpoint exists.

2. **Add the dependency** with `uv` (this repo is `uv`, not bare `pip`), and pin
   it in the same style as its neighbours in `pyproject.toml`.

3. **Add the API key** as `<PROVIDER>_API_KEY`, matching the existing convention
   (`ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `TAVILY_API_KEY`, `JINA_API_KEY`).
   Add it to `.env.example` **and** tell the operator to put the real value in
   `.env` — never write a real key into a tracked file.

4. **Implement per the shape chosen in Step 0.** Match the surrounding idiom: if
   the call site uses LangChain, use the LangChain integration; if it constructs
   a raw SDK client, do that.

5. **Write `tools/test_<provider>.py`.** This is an established convention —
   `tools/test_anthropic.py` and `tools/test_perplexity.py` are the models to
   copy. It must make a **real API call** and print enough to confirm the
   response is genuine, not a stub.

6. **Run it.** Iterate until it passes. A failing smoke test is not a finding to
   report — it is the work, keep going.

7. **Run the existing suite** (`pytest`, configured in `pyproject.toml`) and
   confirm nothing regressed. Note that `tests/` covers sources, membership, and
   emitters — not provider calls — so a green suite is necessary, not sufficient.

8. **Write a changelog entry** per the `changelog-conventions` skill.

## Definition of done

All four, or it isn't done:

- [ ] `tools/test_<provider>.py` exists and **passes against the live API**
- [ ] `pytest` is green
- [ ] The key is in `.env.example`, and no real key is in any tracked file
- [ ] A changelog entry is written

## Do not stop for

- Confirmation between steps
- A failing smoke test on the first attempt
- Deciding which model id to default to — pick the provider's current
  general-purpose model and say which you picked

## Do stop for

- **Step 0 resolving to (b).** A 29-file refactor needs an explicit yes.
- A missing API key with no way to obtain one — report and halt.
- The provider requiring a paid tier the operator has not signed up for.

## Related

- [[Reorder-and-Edit-Direct-Outline]] — the other memopop feature seed
- `tools/test_anthropic.py`, `tools/test_perplexity.py` — the smoke-test pattern
- `tools/test-perplexity-curl.sh` — the shell-level variant, useful for isolating
  whether a failure is auth or SDK

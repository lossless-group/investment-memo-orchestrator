---
title: "Dead ChatAnthropic Import in Socials Enrichment"
lede: "The socials enrichment agent imports ChatAnthropic and never instantiates it — it is a Tavily-only agent. The import is inert at runtime but it is not harmless: it put the file on the CLI-first-provider refactor's work list, where it would have cost a reader the time to open it and discover there was nothing to route. Deleting one line closes it."
date_authored_initial_draft: 2026-09-10
date_authored_current_draft: 2026-09-10
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-09-10
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-09-10
date_modified: 2026-09-10
tags: [Dead-Code, LLM-Provider, Socials-Enrichment, Inventory-Hygiene, Quick-Fix]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: 4f86c19b-6daa-484b-8495-def2dccc9cb8
hex_code: l1xh2n
status: Open
severity: Low
---

# Dead ChatAnthropic Import in Socials Enrichment

## The finding

`src/agents/socials_enrichment.py:11`:

```python
from langchain_anthropic import ChatAnthropic
```

The name is never used. The agent's only network client is Tavily:

```python
client = TavilyClient(api_key=tavily_api_key)   # :37
response = client.search(...)                    # :40
```

There is no `ChatAnthropic(` anywhere in the file, so nothing is constructed and
nothing is billed. At runtime the line costs an import that `langchain_anthropic`
was going to be paid for anyway, elsewhere in the process.

## Why it is worth a line in the issues directory

Because a dead import is indistinguishable from a live one when you are counting
by eye, and somebody did.

`socials_enrichment.py` appeared on the bypassing-modules table in
[[Route-Every-Claude-Call-Through-The-CLI-First-Provider]] with one call site.
It has zero. Anyone working that list in order would have opened the file
expecting to route a model call, found a Tavily search, and spent the time
working out whether they were in the wrong file or the inventory was wrong.

That is the actual cost: not runtime, but a false entry on a work list that
nineteen other modules are also on.

## Fix

Delete line 11. Nothing else in the file references it.

## Verification

```bash
.venv/bin/python scripts/gen_pipeline_reference.py
.venv/bin/python -m pytest tests/test_pipeline_reference.py -q --no-cov
```

`src/agents/socials_enrichment.py` already does not appear in the *LLM routing
inventory* of `docs/PIPELINE-REFERENCE.md` — the generator counts constructions,
not imports, which is how the discrepancy surfaced. So the doc will not change,
and the test will stay green. The point of the fix is the file, not the count.

While in there: confirm nothing else in the module is dead. The import survived
because nobody read the file after the agent's model call was removed, which
suggests the removal left other residue.

## A cheap guard, if this recurs

`ruff` is already a dev dependency (`pyproject.toml`, `[project.optional-dependencies].dev`)
and its `F401` rule is exactly "imported but unused". If unused imports turn out
to be widespread, enabling `F401` in the ruff config catches the whole class
rather than this one instance. Worth a look before hand-fixing a second one.

## Related

- [[Route-Every-Claude-Call-Through-The-CLI-First-Provider]] — the inventory this
  row was wrong on, and the corrections section that records why.
- `docs/PIPELINE-REFERENCE.md` — the generated inventory, and the reason the
  hand-count could be checked at all.
- `tests/test_pipeline_reference.py` — `KNOWN_BYPASSING`, which does not list
  this module, because it never constructed a client.

---
type: Plans
title: "Fix What the First Partner Test Found"
lede: "Five fixes from the first partner's session in Claude: a lean list_deals, a sentence for deals with no URL, trading names, a whoami tool, and steps on imported deals that actually get their inputs."
publish: true
date_created: 2026-11-21
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5
at_semantic_version: 0.0.0.1
status: In-Progress
spec_reference: context-v/specs/MemoPop-Connector-API.md
issue_reference: context-v/issues/First-Partner-Test-of-the-Connector-from-Claude.md
depends_on: []
tags: [Plan, Connector, Partner-Test, Claude]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/fix-partner-test
owns_test_ids: [CONN-PT-01, CONN-PT-02, CONN-PT-03, CONN-PT-04, CONN-PT-05, CONN-PT-06]
---

# Fix What the First Partner Test Found

The five items under "What needs fixing before other partners use it" in [[First-Partner-Test-of-the-Connector-from-Claude]]. Each one is small and has its own test. Work them in order, run the connector suite (`uv run pytest tests/connector`) after each, and check it off here.

## 1. A lean `list_deals`

**Now:** `summarise()` in `src/connector/tools/list_deals.py` returns every entry in `state["skips"]`. An imported deal has 26–36 of them, all with the same "Already applied in the local pipeline run…" reason.

**Change:**
- Return `skips_count` and `skips_by_reason` (each distinct reason once, with its count) by default.
- Add an input `include_skips: bool = False` that returns the full list as now.
- Update the tool's docs and examples (`_examples.py`, `docs_build.py` output) and regenerate the docs.

**Test** (`tests/connector/test_deals.py`): a deal with 30 identical skips lists one reason with count 30. With `include_skips=True` the full list comes back.

- [ ] Done

## 2. A sentence for a deal with no URL

**Now:** `render_instruction()` in `src/connector/flow.py` substitutes `"the company's website (not given)"` for `{{url}}`. Four step files (`research.section`, `research.sources`, `materials.brief`, `enhance.fact_check`) then read "The only correct company is at the company's website (not given)."

**Change:**
- When `url` is missing, lead the instruction with a fixed notice: "This deal has no company website on record. Before researching, ask the partner for the company's URL, and don't research until you have it. A company with a similar name is a common wrong match." Use the same lead-in mechanism as the existing tell-the-partner notice.
- Replace `{{url}}` with `"its website (ask the partner)"` so the sentences stay readable.
- Better still: the step returns `needs_partner` with the question, so Claude can't skip it. Use that if the flow already supports `needs_partner` on research steps. Otherwise do the notice now and note the follow-up.

**Test** (`tests/connector/test_flow.py`): render `research.section` for a deal without a URL. The output has no "(not given)" and starts with the ask-for-the-URL notice.

- [ ] Done

## 3. The deal's name is the trading name

**Now:** `scripts/upload_firm.py` (line ~323) sets `company = cfg.get("legal_name") or cfg.get("name")`. A company that has been renamed shows its former legal name, while its slug comes from the current domain.

**Change:**
- Deal configs get an optional `trading_name`. The uploader sets `company` to `trading_name`, then `name`, then `legal_name`, and keeps `legal_name` as its own field in `deal.json`.
- `list_deals` returns both `company` and `legal_name` (when they differ), so a search by either name finds the deal.
- Fix the one known config in the first firm's folder, and look for others where `legal_name` differs from `name` or the domain.

**Test** (`tests/test_upload_firm.py`): a config with `legal_name` and `trading_name` stages a deal whose `company` is the trading name.

- [ ] Done

## 4. A `whoami` tool

**Change:** a read-only tool, `whoami`, over MCP and REST (`GET /v1/whoami`). It returns the signed-in account (name, email), the firm in use and its display name, every firm the account can use, and the connector version. Register it with the other tools and docs, and mention it in the server instructions ("If the partner works with more than one firm, call whoami first").

**Test** (`tests/connector/test_auth.py`): a token for an account on two firms returns both, with the active one marked. A static key returns the firm it's bound to.

- [ ] Done

## 5. Steps on imported deals get their inputs

**Cause, found 2026-11-21:** two things together.
- The uploader records `materials.brief` as skipped ("Already applied…"), but `research.section` reads only `[materials.brief]`. So the research step for an imported deal resolves no inputs, beyond its own earlier submission when that exists under the same key.
- Imported binaries weren't recorded as materials, so `reads: materials` found nothing. [[Apply-the-Deal-Folder-Uploader]] fixes this part.

**Change:**
- When the uploader skips `materials.brief` on a finished deal, it writes a brief instead: a short text listing the deal's materials, its finished memo version and the local run it came from, saved as the `materials.brief` artifact. Steps that read the brief then get something real.
- `gather_inputs()` in `flow.py`: when a step read resolves to nothing because the step was skipped, add an input that says so ("The materials brief was skipped: <reason>"). An empty `inputs` list should never reach Claude silently.
- Check that each imported deal's research artifacts land under the keys `research.section` looks up, so "Your previous submission for this step" appears when a revision reopens research.

**Test** (`tests/connector/test_flow.py` and `tests/test_upload_firm.py`): an imported, finished deal's `research.section` step has at least the brief and its previous research among its inputs.

- [ ] Done

## Done when

- All five are checked off, with tests passing, and the connector is redeployed.
- A partner repeats the first test in Claude: `list_deals` fits in a few hundred tokens per deal, `whoami` answers, and a research step on an imported deal lists inputs.
- The issue's five items are marked fixed in [[First-Partner-Test-of-the-Connector-from-Claude]].

## Related

- [[Apply-the-Deal-Folder-Uploader]]: the other half of item 5
- [[MemoPop-Connector-API]]

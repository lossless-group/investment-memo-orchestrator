---
type: Plans
title: "Finish Turning the Agents into Connector Steps"
lede: "13 of the orchestrator's roughly 40 agents are steps the connector can hand Claude. The rest, starting with the revision and correction agents that editing finished memos depends on, still need converting."
publish: true
date_created: 2026-11-20
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-20
date_authored_current_draft: 2026-11-20
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5
at_semantic_version: 0.0.0.1
status: In-Progress
spec_reference: context-v/specs/MemoPop-Connector-API.md
depends_on: [Phase-7-Plugin-and-Real-Claude]
site_uuid: 79ea9a93-45f0-48f9-9984-74c88ce1f56b
hex_code: 38ng9b
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/rewrite-step
owns_test_ids: [CONN-STEP-11, CONN-STEP-12]
---

# Finish Turning the Agents into Connector Steps

## Where it stands

The method is decided ([[The-Server-Hands-Claude-the-Method-One-Step-at-a-Time]]): each agent in `src/agents/` becomes a step file in `src/connector/steps/`, and `next_step` hands it to Claude in the partner's chat. Until the orchestrator runs on the server with its own keys, Claude (or a subagent it delegates to) does every step.

13 steps exist, each naming its `source_agent`: `materials.brief`, `materials.extract`, `research.section`, `research.sources`, `draft.section`, the seven `enhance.*` steps, and `compile.assemble`. They cover generating a memo. The connector's current scope is the opposite: iterating memos that are already done and shared (Plan 9 in the spec).

## What to convert, in order

1. **Revision**, which Plan 9 runs on:
   - [x] `section_reviser.py`, revising a section's prose without losing what it said. It becomes the rewrite step: inputs are the research file and the current section draft only, with no outside knowledge and no web research. *Done 2026-11-21: `draft.rewrite`, handed out only when a revision reopens it (CONN-STEP-11). Nothing reopens it yet: both of `start_revision`'s paths reopen `draft.section` (CONN-REV-01, CONN-REV-03), so its caller is the light edit path (`edit_section`).*
   - [x] Also give `draft.section` the current draft as an input when it runs as part of a revision, and add the same no-outside-knowledge line to its instructions. *Done 2026-11-21: it reads `section.current:@section`, which resolves only once the section has text (CONN-STEP-12).*
2. **Correction**, for "this citation is wrong" and "this fact is off": `fact_verifier`, `fact_corrector`, `citation_validator`, `citation_corrector`, `remove_invalid_sources`, `attribution_audit`.
3. **Rewrites and enrichment**: `key_info_rewrite`, `competitive_landscape_researcher`, `competitive_landscape_evaluator`, `link_enrichment`, `socials_enrichment`, `inject_deck_images` (if `enhance.*` doesn't already cover it).
4. **Clean-up passes**, which may be server-side code rather than Claude steps: `citation_spacing`, `internal_comments_sanitizer`, `anomalies`.
5. **Check for overlap and retire**: `researcher`, `research_enhanced`, `codified_section_researcher`, `perplexity_sources`, `source_cataloger`, `source_extractor`, `scorecard_agent`, `scorecard_navigator`. Several look superseded by existing steps. Confirm which before converting any.
6. **Not memo steps**: `portfolio_listing_agent`, `slides/`, `one_pager_generator` beyond `enhance.one_pager`. Decide separately.

## For each agent

- Read the agent's prompt and its node in the LangGraph workflow.
- Write `src/connector/steps/<phase>.<name>.md` in the shape of the existing steps: `reads`, `requires_approved`, `source_agent`, the instruction, and what a finished artifact must look like.
- Add the step to the registry's flow (or to a revision path, for steps that only run on request), with tests beside the existing step tests.
- Note in the agent file that the step now exists.

## Done when

- A partner can ask Claude for each kind of change in Plan 9's routing table, and `next_step` hands Claude a step for it.
- Every agent in `src/agents/` is a step, folded into one, or marked retired.

## Related

- [[MemoPop-Connector-API]], Plan 9: where an edit goes
- [[Upload-Deal-Folders-With-a-Binaries-Manifest]]: steps for imported deals need their materials recorded
- [[First-Partner-Test-of-the-Connector-from-Claude]]

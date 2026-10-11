---
type: Plans
title: "MemoPop Connector API, Phase 7: The Plugin and Real Claude"
lede: "A thin skill that keeps Claude on the method, packaged with the connector, and a test where real Claude writes the fixture memo."
publish: true
date_created: 2026-10-10
date_modified: 2026-10-10
date_authored_initial_draft: 2026-10-10
date_authored_current_draft: 2026-10-10
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5 (1M context)
at_semantic_version: 0.0.0.1
status: Gated-On-Deploy
spec_reference: context-v/specs/MemoPop-Connector-API.md
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/plan-7-plugin
depends_on: [Phase-5-Enhancements-Compile-and-Flow]
owns_test_ids: [CONN-PLUG-01, CONN-PLUG-02]
site_uuid: 4c820f47-5848-40ee-87d8-5c4dd42abe57
hex_code: xdvrun
tags:
  - Plan
  - MemoPop
  - Claude-Plugin
  - Agent-Skills
  - TDD
---

# MemoPop Connector API, Phase 7: The Plugin and Real Claude

Read the spec (§Docs that aren't generated, §The test suite, layer 11) and
[[The-Server-Hands-Claude-the-Method-One-Step-at-a-Time]].

## Steps

1. **Check current Claude plugin documentation** before packaging: the plugin
   manifest format, how a plugin declares a remote MCP connector, and which
   surfaces load skills. Record the sources in the changelog.
2. **Failing tests** for both owned IDs. `CONN-PLUG-02` is gated on
   `ANTHROPIC_API_KEY` and a reachable server URL.
3. **`plugin/`**: the plugin manifest, the connector entry pointing at
   `https://memopop.didi.sh/mcp`, and `skills/memopop/SKILL.md`. The skill is
   thin and states the rules: this is a multi-step pipeline with an artifact
   trail; start with `list_deals`; always call `next_step` and do only what it
   says; show the partner every research file and wait for approval before
   submitting it with `partner_approved: true`; on `skipped`, say so in one
   line and continue; on `down`, stop and tell the partner. `CONN-PLUG-01`
   checks each rule is present.
4. **The real-Claude test** (`tests/connector/test_real_claude.py`): the Claude
   API's MCP connector support pointed at a server running `fixture-co`, with
   the skill as the system prompt and a scripted partner that approves
   research. Assert from the server's step log: tools in order, research shown
   before drafting, one forced skip handled in a line, one forced `down`
   stopping cleanly. Use a current Claude model, and keep the fixture small so
   a run costs little.
5. **`docs/operator/connect-claude.md`**: adding the connector in Claude
   Desktop and installing the plugin.
6. Changelog, commit, push. Report the cost and duration of one real run.

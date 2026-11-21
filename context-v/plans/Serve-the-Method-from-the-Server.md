---
type: Plans
title: "Serve the Method from the Server"
lede: "Partners who add the connector by URL get no skill, and Claude only finds MemoPop's deferred tools when the request names MemoPop. Serve small skills and MCP prompts from the server, the way event-hog does, and lead the server instructions with editing memos."
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
tags: [Plan, Connector, Skills, MCP-Prompts, Claude]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/serve-the-method
owns_test_ids: [CONN-SKL-01, CONN-SKL-02, CONN-SKL-03, CONN-SKL-04]
---

# Serve the Method from the Server

The decision is in the spec ("How partners get the method", 2026-11-20): no skill uploads, everything on the server. The reference implementation is event-hog, `self-host-stack/hubs/event-hog-mcp/src/skills.ts`. Read it before starting.

Steps 1 and 2 can ship now. Some skills in step 3 describe tools from [[Edit-Tools-for-Finished-Memos]], so write those once the tools exist.

## 1. Server instructions lead with editing

- [ ] Rewrite the instructions string in `src/connector/mcp_app.py` (and the copy in `docs_build.py`): lead with "MemoPop holds this firm's finished investment memos. Partners use it to change them: fix a citation, rewrite a section, change wording." Then the method lines as now. Then "Call list_skills to see the playbooks."
- [ ] Mention `whoami` for partners on more than one firm (from [[Fix-What-the-First-Partner-Test-Found]]).
- [ ] Test (`tests/connector/test_docs.py`): the instructions start with the editing sentence.

## 2. `list_skills` and `get_skill`

- [ ] Skills are markdown files in `src/connector/skills/<name>.md` with `name` and `description` frontmatter, in git.
- [ ] `list_skills`: names and one-line descriptions. `get_skill(name)`: the playbook. Both read-only, MCP and REST, registered and documented.
- [ ] Tests: every file is listed, an unknown name returns `not_found` with the list.

## 3. The first set of skills

Each short, each ending with which tool to call. Following Plan 9:

- [ ] `fix-a-source-or-citation`: research route, `start_revision` with `start: research`, rewrite, compile.
- [ ] `rewrite-a-section-from-its-research`: the two-task rule.
- [ ] `edit-wording`: `edit_section`.
- [ ] `just-edit-the-memo`: `edit_final`, and what gets carried back.
- [ ] `change-the-outline-for-this-memo`: `edit_outline`, this memo only, others one at a time on request.
- [ ] `compile-and-check-the-site`: compile, then the page link (from [[Serve-Compiled-Memos-to-Firm-Sites]]).

## 4. MCP prompts as entry points

- [ ] Register prompts (`prompts/list`): "Edit a memo", "Fix a citation", "Change the outline for this memo", "Check the memo on the site". Each names MemoPop and tells Claude to load its tools and the matching skill, which gets past the deferred-tool problem.
- [ ] Test: `prompts/list` returns the four, and each prompt's text names a skill that exists.

## 5. A getting-started prompt for partners

- [ ] A short paste-once message, sent with the connector link: load MemoPop, call `list_skills`, say what you can do. Keep it in `docs/` and in the partner onboarding email.

## 6. Retest from Claude

- [ ] A partner, in a fresh chat, says "fix the citation in the market section of the X memo" without naming MemoPop, after pasting the getting-started prompt once. Claude finds the tools and the skill.
- [ ] Record the result in the partner-test issue.

## Related

- [[First-Partner-Test-of-the-Connector-from-Claude]], "How the method reaches Claude without the plugin"
- [[MemoPop-Connector-API-Phase-7-Plugin-and-Real-Claude]]: the plugin skill this replaces for URL-added connectors

---
type: Plans
title: "Serve Compiled Memos to Firm Sites"
lede: "A read endpoint that returns a deal's latest compiled memo to the firm's own site, behind a per-firm site key, so a partner who edits a memo in Claude sees it on the LP page after a refresh."
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
spec_reference: astro-knots/context-v/specs/Firm-Sites-Show-the-Latest-Memo-from-MemoPop.md
depends_on: [Apply-the-Deal-Folder-Uploader]
tags: [Plan, Connector, Sites, Compile]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/site-memo-endpoint
owns_test_ids: [CONN-SITE-01, CONN-SITE-02, CONN-SITE-03, CONN-SITE-04]
---

# Serve Compiled Memos to Firm Sites

The orchestrator's half of the firm-site specs: the general one in `astro-knots/context-v/specs/Firm-Sites-Show-the-Latest-Memo-from-MemoPop.md` and the first firm's build in `astro-knots/sites/humain-web/context-v/specs/Show-Partners-the-Latest-Memo-from-MemoPop.md` (phase 1 there). The site-side work stays in that site's repo.

## Steps

1. **Endpoint.** `GET /site/v1/firms/{firm}/deals/{deal}/memo` in `rest_app.py`. Returns the latest compiled `memo.md`, its version label, compile time, and signed links to the HTML and PDF exports (`compile/links.py`). `404` when the deal has no compiled version.
   - [ ] Done
2. **Site keys.** `MEMOPOP_SITE_KEYS` (`firm=key,…`) read in `config.py`. A request needs `Authorization: Bearer <key>` matching the firm in the path. A key for one firm can't read another's. Separate from partner auth, read-only, and logged.
   - [ ] Done
3. **Images.** Answer the open question first: do compiled memos reference images, and how? If they're bucket keys or workspace paths, rewrite them in the response to signed URLs, or return an `images` map the site can proxy through its gated route. Pick one with the site's needs in mind and record the choice in both specs.
   - [ ] Decided and built
4. **The compile reply links to the page.** `firm.json` gets `site_memo_url` (a pattern with `{slug}`) and a deal-to-slug map. A finished `compile` includes `site_url` in its response, and the `compile-and-check-the-site` skill tells Claude to give it to the partner.
   - [ ] Done
5. **Tests** (`tests/connector/`): right key gets the memo, wrong firm's key gets `403`, no key `401`, uncompiled deal `404`, and an image rewrite case.
   - [ ] Done
6. **Deploy and hand off.** Deploy to the `connector` service, set the firm's site key in Railway and the password manager (never in a repo), then mark the site spec's phase 1 done so phase 2 can start in the site repo.
   - [ ] Done

## Done when

The site spec's phase 3 loop works: change one sentence in Claude, compile, refresh the LP page, and the sentence and the version have changed.

## Related

- [[Apply-the-Deal-Folder-Uploader]]: without it there are no compiled versions to serve
- [[Edit-Tools-for-Finished-Memos]]

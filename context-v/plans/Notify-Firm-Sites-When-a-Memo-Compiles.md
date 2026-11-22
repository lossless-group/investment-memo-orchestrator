---
type: Plans
title: "Notify Firm Sites When a Memo Compiles"
lede: "When a new compiled version is saved, MemoPop sends the firm's site a signed memo.compiled event naming the deal, so the site can cache memos and still show a fresh compile after a refresh."
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
spec_reference: context-v/specs/Notify-Firm-Sites-When-a-Memo-Compiles.md
depends_on: [Serve-Compiled-Memos-to-Firm-Sites]
tags: [Plan, Connector, Sites, Compile, Webhooks]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/site-hook
owns_test_ids: [CONN-HOOK-01, CONN-HOOK-02, CONN-HOOK-03, CONN-HOOK-04, CONN-HOOK-05, CONN-HOOK-06]
---

# Notify Firm Sites When a Memo Compiles

The server side of [[Notify-Firm-Sites-When-a-Memo-Compiles]]. The site's hook endpoint and cache are built in each site's own repo.

## Steps

1. **Failing tests first.** `tests/connector/test_site_hook.py`, CONN-HOOK-01 to 06, against a fake site endpoint (`httpx.MockTransport`) with the backoff wait recorded, never slept.
   - [x] Done. Watched 12 of 15 fail against a stub module; the three that passed were the "sends nothing" cases, which a stub satisfies trivially.
2. **The sender.** `src/connector/site_hook.py`: build the body (event, firm, deal, version, label, compiled_at; no memo, no links), sign `"<timestamp>.<raw body>"` with HMAC-SHA256 and the firm's key from `MEMOPOP_SITE_KEYS`, POST with a 5 s timeout, retry a connection error, timeout or 5xx after 1 s, 5 s and 25 s, never retry a 4xx. Log firm, deal, attempt, status and duration only.
   - [x] Done. Uses `httpx`, already a dependency. Each send runs on a daemon thread, tracked so a one-shot script can wait for it (`wait_for_senders`). `transport`, `sleep` and `clock` are module attributes the tests replace. A `site_hook_url` that isn't `http(s)` is skipped and logged.
3. **Call it after a compile.** In `tools/compile.py`, after the compiled record, the memo and the history entry are saved.
   - [x] Done. Sent when the compile made a new version or new exports (a PDF added to an unchanged version changes the site's `pdf_url`). A compile that changes nothing sends nothing. A compile detached past its budget notifies when its worker finishes. A failed or refused compile never reaches the call.
4. **Call it from the uploader's apply step.** `scripts/apply_upload.py`, for each deal whose compiled version or sha256 differs from the server's before the upload (or that had none).
   - [x] Done. Split into `replace_deals` (returns the changed deals) and `notify_site`, called after the firm's history records the upload. The script then waits up to 90 s for the sends, since its daemon threads die with it.
5. **Docs.** `site_hook_url` beside `site_memo_url` in the connector spec's §Site read endpoint; the HOOK table in its §Tests.
   - [x] Done.
6. **Deploy and hand off.** Deploy to the `connector` service; set `site_hook_url` in a firm's `firm.json` once its site's hook endpoint is live.
   - [ ] Done

## Decisions made here

- **Retries.** The spec says both "up to 3 attempts, about 1 s, 5 s and 25 s apart" and (CONN-HOOK-03) "retried up to 3 times". Built as one send plus up to three retries, waiting 1 s, 5 s and 25 s, so all three waits are used. One constant (`RETRY_DELAYS`) to change if three sends in all was meant.
- **No client-visible change.** The compile reply gains no field, so no `SERVER_VERSION` bump and no API changelog entry.

## Done when

A partner compiles in Claude, the firm's site receives one signed `memo.compiled` event within seconds, and a refresh shows the new version from the site's freshly fetched copy.

## Related

- [[Serve-Compiled-Memos-to-Firm-Sites]]
- [[Apply-the-Deal-Folder-Uploader]]

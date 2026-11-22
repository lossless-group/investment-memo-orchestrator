---
title: "Notify Firm Sites When a Memo Compiles"
lede: "When a new compiled version of a memo is saved, MemoPop tells the firm's site which deal changed. The site drops its cached copy of that memo, so pages stay fast and a refresh after compiling still shows the change."
date_created: 2026-11-21
date_modified: 2026-11-21
date_authored_initial_draft: 2026-11-21
date_authored_current_draft: 2026-11-21
at_semantic_version: 0.0.0.1
status: Draft
publish: true
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
tags: [Connector, Firm-Sites, Webhooks, Caching]
---

# Notify Firm Sites When a Memo Compiles

## Why

A firm's site reads each memo from `GET /site/v1/firms/{firm}/deals/{deal}/memo` on every page view, with no cache, so a partner who compiles in Claude and refreshes sees the change. That costs a round trip per view: about 0.2–0.45 s for a 109 KB memo, measured 2026-11-21. Caching the memo on the site makes views instant, but a cache alone would show the old memo after a compile until it expired.

So MemoPop notifies the site when a memo changes, and the site caches until told otherwise.

## Decisions

1. **Notify, don't push.** MemoPop sends which deal changed, never the memo. The site fetches the new version with the site key it already has. Trust runs one way: the site doesn't give MemoPop write access, and a lost notification only means the cache lives until it expires.
2. **Sign with the firm's existing site key.** The notification is signed with HMAC-SHA256 using the firm's key from `MEMOPOP_SITE_KEYS`, which the site already holds as `MEMOPOP_SITE_KEY`. No new secret to issue or rotate.
3. **Cache the memo data, not the page.** Firm memo pages sit behind an investor sign-in. Caching the rendered page at the edge risks serving it without the sign-in check, so the site caches only the fetched memo, per deal. The sign-in check still runs on every view.
4. **Expire the cache within 3 days anyway.** Image links in the memo are signed for 7 days, and a missed notification must not leave a page with dead images.

## The notification

### When MemoPop sends it

Only after a new compiled version is durably saved: its markdown, the record of the compile, and its exports. That happens in two places:

- a compile job (the `compile` tool) finishing successfully;
- the uploader's apply step, for each deal whose compiled version it changes.

It never sends on a failed or cancelled compile, or on edits that don't produce a compiled version (`edit_section`, `edit_final`, drafting steps).

### Where it goes

The firm's `firm.json` on the server gains `site_hook_url`, beside the existing `site_memo_url` and `site_memo_slugs`:

```json
{ "site_hook_url": "https://www.example-firm.com/api/memopop/revalidate" }
```

No `site_hook_url` means no notification. A firm without a site key in `MEMOPOP_SITE_KEYS` gets none either, since there is nothing to sign with. Either case is logged once per compile and never fails it.

### The request

```
POST {site_hook_url}
Content-Type: application/json
X-MemoPop-Timestamp: 1763776800
X-MemoPop-Signature: sha256=<hex HMAC-SHA256(site key, "<timestamp>.<raw body>")>

{ "event": "memo.compiled", "firm": "<firm>", "deal": "<deal>",
  "version": 3, "label": "v0.0.4", "compiled_at": "2026-11-21T16:29:44Z" }
```

- The body carries no memo text and no links.
- The timestamp is Unix seconds at sending. The signature covers the timestamp and the exact body bytes.

### Delivery

- Sent after the compile finishes, never blocking the tool's reply and never failing it.
- Timeout 5 s. Up to 3 attempts, about 1 s, 5 s and 25 s apart, on a connection error, a timeout or a 5xx. A 4xx is not retried.
- Each attempt is logged with firm, deal, status and duration, never the signature or key.
- No delivery queue that survives a restart. A notification lost to a restart is covered by the site's cache expiry.

## The site's side

### The hook endpoint

`POST /api/memopop/revalidate`, rendered on demand.

1. Reject with 401 if the signature doesn't match: HMAC-SHA256 with `MEMOPOP_SITE_KEY` over `"<timestamp>.<raw body>"`, compared in constant time. Also reject if the timestamp is more than 5 minutes from now.
2. Reject with 400 if the body isn't the event above, or if `firm` isn't this site's firm.
3. Expire the cached memo for `deal`. Answer 204 whether or not the deal is mapped to a page or cached, so the endpoint doesn't reveal which deals the site shows.

### The cache

- Key the cached memo by deal, tagged `memopop:<deal>`, so the hook can expire one deal.
- Keep each entry for at most 3 days.
- Cache only successful fetches. A failed fetch still falls back to the bundled copy and caches nothing.
- The memo page's own response stays `Cache-Control: private, no-store`.

On Vercel, use the Runtime Cache (`getCache()` from `@vercel/functions`, with tags) or the nearest supported equivalent; check Vercel's current docs before choosing. An in-memory cache per function instance isn't enough, because the hook can't reach other instances.

## Tests

### MemoPop (connector)

| ID | Checks |
|---|---|
| CONN-HOOK-01 | A successful compile sends one signed `memo.compiled` request to the firm's `site_hook_url`: the right body, a timestamp, and a signature verifiable with the firm's site key. |
| CONN-HOOK-02 | No request when the firm has no `site_hook_url` or no site key, and the compile still succeeds. |
| CONN-HOOK-03 | A hook that times out or returns 5xx is retried up to 3 times and never fails or delays the compile reply. A 4xx is not retried. |
| CONN-HOOK-04 | A failed compile sends nothing. |
| CONN-HOOK-05 | The uploader's apply step sends one notification per deal whose compiled version it changed, and none for unchanged deals. |
| CONN-HOOK-06 | The request body contains no memo text, no links, and no key; logs contain neither the signature nor the key. |

### Site

- A correctly signed request expires that deal's cache and returns 204. A wrong signature, a stale timestamp, or the wrong firm is refused.
- A cached memo is served without calling MemoPop. After the hook fires, the next view fetches the new version.
- Entries expire within 3 days. A failed fetch isn't cached.

## Related

- `context-v/specs/MemoPop-Connector-API.md` §Site read endpoint
- astro-knots: `context-v/specs/Firm-Sites-Show-the-Latest-Memo-from-MemoPop.md`
- Each firm site's own spec, in that site's repo

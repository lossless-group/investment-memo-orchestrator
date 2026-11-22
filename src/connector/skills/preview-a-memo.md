---
name: preview-a-memo
description: The partner wants to see a section, research, or the whole memo as it will look; render it on the server with preview, never yourself.
---
# Preview a memo

Use this whenever the partner wants to see something as it will look: a section just rewritten, a draft, research, or the whole memo, before or after compile.

**Never render the markdown yourself, and never invent citation numbers.** The memo's citations are hex keys (`[^1ucdcd]`); the server numbers them in the order they are first cited, the way the firm's site does, and wraps the page in the firm's branding. A memo you render yourself won't match the site, and its numbers will be wrong.

1. Find the deal with `list_deals`.
2. Call `preview` with the deal and `artifact`:
   - a section's key, name, or number, for its current text (a rewritten section shows before anything is compiled);
   - `memo`, for the whole memo assembled from the current sections, as compile would make it (no version is saved; every section needs a draft, else `drafts_incomplete`);
   - an artifact id, for that artifact: research (`research.section:<key>`), a draft, or `compile.assemble` for the last compiled memo.
3. Give the partner `html_url` (a signed link that lasts seven days). If your client shows HTML as a work artifact, you may show the returned `html` as it is; don't rewrite or restyle it.
4. If it returns `service_unavailable`, rendering is down on the server: tell the partner the preview isn't available right now, and give them the text from `get_artifact` instead of a page you made.

A preview saves nothing. To publish the change as the memo's next version, compile (see `compile-and-check-the-site`).

Call next: `preview`.

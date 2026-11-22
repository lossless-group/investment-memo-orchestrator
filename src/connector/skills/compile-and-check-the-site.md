---
name: compile-and-check-the-site
description: After changes are worked through, compile the memo into its next version and give the partner the links to check it.
---
# Compile and check the site

Compile once all the partner's changes are worked through, not after each one.

1. Call `compile` with the deal. It refuses with `revision_incomplete` while a revision still has steps to do: call `next_step` and finish them first.
2. It returns the memo's new version `label` and signed `html_url` and `pdf_url` links that last seven days. If compiling takes long, it returns a `job_id` instead: call `list_deals` until that deal's compile shows done, and take the links from there.
3. Give the partner the version label and the links, and ask them to check the change they asked for.

To show the partner the memo before compiling, call `preview` with `artifact: memo` (see `preview-a-memo`). Never render the memo's markdown yourself or number its citations: the exports and `preview` do that.

**The page on the firm's site needs the compile→site link, which is not on the server yet.** Once it is, `compile` also returns `site_url`, the memo's page on the firm's site: give the partner that link first. Until then, give the HTML and PDF links, and don't promise when the site shows the new version.

Call next: `compile`.

---
title: "First Partner Test of the Connector from Claude"
lede: "Sign-in, list_deals and next_step all work from a regular Claude chat. Five things need fixing before other partners use it, and the deals on the server are an incomplete copy of the firm's local work."
date_created: 2026-11-20
date_modified: 2026-11-20
date_authored_initial_draft: 2026-11-20
date_authored_current_draft: 2026-11-20
at_semantic_version: 0.0.0.1
publish: false
status: Open
tags: [Connector, Claude, Partner-Test, Import, Sync]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
site_uuid: 0a894cfb-cd64-411d-bf5e-394ac2e935d0
hex_code: 7hiq8d
---

# First Partner Test of the Connector from Claude

On 2026-11-20 a partner of the first firm on the hosted connector added `https://memopop.didi.sh/mcp` to Claude and used it from a regular chat. Claude's own report is the source for most of this.

## What worked

- Sign-in through id.didi.sh, choosing the firm.
- `list_deals` returned the firm's 12 deals.
- `next_step` returned a full, well-formed step. The step instructions are clear, the citation format and checks are spelled out, and the approve-before-submit rule is easy to follow.
- No data changed, except that `next_step` marked one step as handed out.

## What needs fixing before other partners use it

1. **`list_deals` returns far too much.** Every imported deal carries 26–36 nearly identical "Already applied in the local pipeline run…" skip entries, thousands of tokens for 12 deals. Return a skip count by default and the full list only when asked.
2. **A bad sentence when a deal has no URL.** The step reads "(the company's website (not given))" and "The only correct company is at the company's website (not given)." That case needs its own sentence, telling Claude to ask the partner for the URL. Without one, Claude can easily research a different company with a similar name.
3. **A deal's name doesn't match its slug.** One deal is labeled with the company's former name while its slug comes from the current domain (the company trades under a different name). Anyone searching by name will be confused. The display name should follow the deal config, and the config should carry the trading name.
4. **No way to see who you're signed in as.** No tool reports the firm and account in use. With a firm parameter on every call, people on more than one firm will need one, e.g. a `whoami` tool.
5. **A step gets no inputs.** A research step on an imported deal had an empty inputs list, even though the deal came from the local pipeline with earlier research and a materials brief. Imported material isn't reaching the steps.

## The bigger problem: the server's deals are an incomplete copy

Checked the same day against the firm's local folder:

- **Locally, every deal has a finished memo** (14 of 14). **On the server, none is compiled.** The 2026-10-15 import stored each finished memo as reference material, not as a compiled version.
- **Sections are missing.** Some deals have all 10, some 7, and three have 0, because the import matched section files by name and the outline's names had drifted from the local ones.
- **Deals changed or added after 2026-10-15 never arrived.** Nothing has synced since the one-time import.
- **Binaries were copied to the bucket but not recorded.** Inputs and exports went to `imported/<deal>/…` in the firm's bucket, but the deal doesn't list them as assets, so no step can find them. This is likely the cause of item 5.

So the partner's status read ("ready to compile", "in research", "waiting on materials") reflects the import's gaps, not the real state of the work.

## Direction

Upload the whole deal folder. Text (configs, research, sections, finished memos, analyses) goes into the firm's workspace. Data rooms, decks and other binaries go to the firm's bucket, and each one is recorded in the deal as an asset (bucket key, file name, kind, size, checksum) so steps and people can find it. The latest finished memo becomes the first compiled version. After that, keep the two sides in sync instead of importing once.

## Next tests from Claude

- Compile a deal that is ready, which checks the HTML and PDF exports and the bucket. It writes files, so it waits for a go-ahead.
- Finish one research step end to end: web research, the partner approves, `submit_artifact`. This checks the write path and the citation checks.

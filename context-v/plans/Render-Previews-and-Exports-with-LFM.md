---
type: Plans
title: "Render Previews and Exports with LFM"
lede: "Exports go through Pandoc and WeasyPrint, firm sites through Lossless Flavored Markdown, and agents in Claude or ChatGPT have no way to show a memo as it will look. Render once, on the server, with LFM, and tell every agent to use that instead of rendering itself."
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
at_semantic_version: 0.0.1.0
status: In-Progress
spec_reference: context-v/specs/MemoPop-Connector-API.md
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
depends_on: [Hex-Code-Citations-and-a-Repair-Tool]
owns_test_ids: [CONN-LFM-01, CONN-LFM-02, CONN-LFM-03, CONN-LFM-04, CONN-LFM-05, CONN-LFM-06]
tags: [Plan, LFM, Exports, Previews, Connector, Agents]
---

# Render Previews and Exports with LFM

## Why

Three renderers show the same memo three ways:

- **Local exports:** Pandoc (`cli/export_branded.py`), then WeasyPrint for PDF.
- **Connector exports:** `render_branded_html` and WeasyPrint (`src/connector/compile/pipeline.py`).
- **Firm sites:** LFM (`@lossless-group/lfm`), with hex-code citations numbered at render, hover popovers, callouts.

With hex-code citations ([[Hex-Code-Citations-and-a-Repair-Tool]]), Pandoc still numbers footnotes correctly, but the PDF a partner downloads won't match the memo on the firm's site.

Agents can't close the gap themselves. Partners now work through Claude and, later, ChatGPT and Claude Code. They will want to see a draft as it will look. LFM is published to JSR (npm-compat: `@jsr/lossless-group__lfm`). A Claude artifact can load scripts only from cdnjs, jsDelivr (npm) and unpkg, which don't serve JSR packages, and ChatGPT's canvas is more restricted still. If each agent rendered markdown its own way, every preview would differ.

## Decision (2026-11-21)

Render on the server, once, with LFM. Agents never render a memo themselves.

The open questions below, resolved by the VP Eng before the build:

- **LFM runs outside Astro.** `@lossless-group/lfm@0.11.0` is on npm with a Node-free `/browser` entry, and the root entry works in Node. The renderer pins 0.11.0 exactly (and `unified`, `remark-rehype`, `rehype-stringify` exactly) in `src/connector/render/package.json` and its lockfile. It imports `/browser`, which has no Open Graph fetching, so a render makes no network calls.
- **Exports keep the firm's brand CSS** from `brand-<firm>-config.yaml`, as `render_branded_html` does today. LFM makes the HTML body; the branded page and its CSS around it are unchanged, plus a few rules for what LFM adds (callouts, the sources list).
- **The site endpoint keeps returning markdown.** The firm's site renders it with LFM itself. No HTML is added there.
- **Two steps, never one chain.** `parseMarkdown`, then `remark-rehype` and `rehype-stringify`. Chaining `remarkLfm` and `remarkRehype` in one processor silently skips callouts and citations (a known LFM issue). Citations are numbered from the hex keys in first-cited order, and the sources list is rendered from `tree.data.citations.ordered`.
- **Behind a setting until checked.** `MEMOPOP_EXPORT_RENDERER` (`pandoc` by default, or `lfm`) chooses compile's renderer; `cli/export_branded.py --renderer lfm` does the same locally. `preview` always uses LFM.

## Steps

1. **An LFM renderer on the connector.** A small Node script in the container (`@lossless-group/lfm` with `unified`, `remark-parse`, `remark-rehype`, `rehype-stringify`) that takes markdown and the firm's theme and returns HTML. Called from Python as a subprocess, the way Pandoc is now. Citations number from hex keys in first-cited order, with the definitions as the reference list. Callouts and other directives render as plain HTML, with no Astro components.
2. **Exports use it.** `compile`'s HTML export, and the PDF made from that HTML by WeasyPrint, go through the LFM renderer with the firm's brand CSS. `cli/export_branded.py` gets an `--renderer lfm` option, made the default once the output matches the brand's look.
3. **A preview for agents.** A read-only tool, `preview` (`GET /v1/deals/{deal}/preview?artifact=…`), renders the current text of a section, the compiled memo, or a submitted artifact, and returns a signed link and the HTML. It works before compile, so a partner can see a rewritten section before publishing it.
4. **Agent instructions.** The server instructions and the skills say: to show the partner a memo or section, call `preview` and give them the link, or show the returned HTML as a work artifact if the client supports one. Never render the markdown yourself, and never invent citation numbers. Add a `preview-a-memo` playbook.
5. **Optional: publish LFM to npm too.** Then jsDelivr serves it as ESM (`cdn.jsdelivr.net/npm/@lossless-group/lfm@x/+esm`), and Claude can build live-preview artifacts in the chat. That depends on the core plugin running in a browser, with no Node-only imports. Check before committing to it.

## Open questions

Resolved in the Decision above (2026-11-21):

- ~~Does `@lossless-group/lfm`'s core run outside Astro with plain `unified`?~~ Yes, from npm, two steps.
- ~~Which brand CSS applies to LFM's HTML?~~ The firm's `brand-<firm>-config.yaml` CSS, as today.
- ~~Does the site endpoint keep returning markdown?~~ Yes.

Still open:

- When does `MEMOPOP_EXPORT_RENDERER` default to `lfm`? Once a partner has compared an LFM export with the pandoc one for each firm brand.
- Firms whose brand config names a `theme` (`cli/themed_export.py`) render locally with pandoc only; `--renderer lfm` falls back to the brand CSS for them.

## Related

- [[Hex-Code-Citations-and-a-Repair-Tool]]
- [[Serve-Compiled-Memos-to-Firm-Sites]]
- [[Serve-the-Method-from-the-Server]]
- `lossless-flavored-markdown` skill, `references/package-and-setup.md`

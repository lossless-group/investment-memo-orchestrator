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
at_semantic_version: 0.0.0.1
status: Draft
spec_reference: context-v/specs/MemoPop-Connector-API.md
depends_on: [Hex-Code-Citations-and-a-Repair-Tool]
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

## Decision (proposed 2026-11-21)

Render on the server, once, with LFM. Agents never render a memo themselves.

## Steps

1. **An LFM renderer on the connector.** A small Node script in the container (`@lossless-group/lfm` with `unified`, `remark-parse`, `remark-rehype`, `rehype-stringify`) that takes markdown and the firm's theme and returns HTML. Called from Python as a subprocess, the way Pandoc is now. Citations number from hex keys in first-cited order, with the definitions as the reference list. Callouts and other directives render as plain HTML, with no Astro components.
2. **Exports use it.** `compile`'s HTML export, and the PDF made from that HTML by WeasyPrint, go through the LFM renderer with the firm's brand CSS. `cli/export_branded.py` gets an `--renderer lfm` option, made the default once the output matches the brand's look.
3. **A preview for agents.** A read-only tool, `preview` (`GET /v1/deals/{deal}/preview?artifact=…`), renders the current text of a section, the compiled memo, or a submitted artifact, and returns a signed link and the HTML. It works before compile, so a partner can see a rewritten section before publishing it.
4. **Agent instructions.** The server instructions and the skills say: to show the partner a memo or section, call `preview` and give them the link, or show the returned HTML as a work artifact if the client supports one. Never render the markdown yourself, and never invent citation numbers. Add a `preview-a-memo` playbook.
5. **Optional: publish LFM to npm too.** Then jsDelivr serves it as ESM (`cdn.jsdelivr.net/npm/@lossless-group/lfm@x/+esm`), and Claude can build live-preview artifacts in the chat. That depends on the core plugin running in a browser, with no Node-only imports. Check before committing to it.

## Open questions

- Does `@lossless-group/lfm`'s core run outside Astro with plain `unified`? The LFM skill says non-Astro consumers use it with their own pipeline, but check the trigger map and the components it expects.
- Which brand CSS applies to LFM's HTML: the firm's `brand-<firm>-config.yaml` CSS as today, or the firm site's theme tokens?
- Does the site endpoint keep returning markdown (the site renders it) or add rendered HTML?

## Related

- [[Hex-Code-Citations-and-a-Repair-Tool]]
- [[Serve-Compiled-Memos-to-Firm-Sites]]
- [[Serve-the-Method-from-the-Server]]
- `lossless-flavored-markdown` skill, `references/package-and-setup.md`

---
title: "Diagram SVGs Made Every Recompile a New Version"
lede: "compile versions a memo by its content, and the market-sizing diagram rendered to different bytes every time, so an unchanged memo with a diagram never compiled as unchanged."
publish: false
date_created: 2026-10-15
date_modified: 2026-10-15
date_authored_initial_draft: 2026-10-15
date_authored_current_draft: 2026-10-15
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5 (1M context)
at_semantic_version: 0.0.1.0
status: Resolved
site_uuid: c120a3c9-d5eb-4b41-a923-8feb9e5f7dfd
hex_code: ndkgr2
summary: >-
  matplotlib writes a random element-id salt and a Date into every SVG.
  diagram_generator embeds the SVG in the memo, so two compiles of the same
  sections hashed differently and compile minted a new version (and now a new
  label) each time. The existing CONN-CMP test for an unchanged recompile
  passed only because its deal had no diagram. Found by CONN-REV-09.
tags:
  - Issue-Resolution
  - MemoPop
  - Compile
  - Diagrams
  - Matplotlib
---

# Diagram SVGs Made Every Recompile a New Version

## What happened

CONN-REV-09 compiled a fully enhanced fixture deal twice and expected the same
label. The second compile came back `v0.0.2`, version 2. The only difference
between the two `memo.md` files was the base64 SVG of the TAM/SAM/SOM diagram.

matplotlib's SVG backend salts element ids with a random value and writes the
render time into the file's metadata.

## Why it matters

compile decides "nothing changed" by hashing the memo. With a diagram in it,
every compile was a new version: version numbers and labels climbed with no
change, and a partner sharing "v0.0.3" couldn't trust it named a distinct memo.

## Resolution

`src/agents/diagram_generator.py` renders the SVG under
`rc_context({"svg.hashsalt": "memopop"})` with `metadata={"Date": None}`, so
the same figure is the same bytes. Commit `e52f37b`.

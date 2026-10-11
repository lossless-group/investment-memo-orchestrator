---
id: compile.assemble
title: Assemble and export the memo
phase: compile
scope: deal
required: true
runs_on: server
needs_partner: false
order: 200
version: "0"
reads: ["draft.section:*"]
produces:
  kind: compiled
  checks:
    not_empty: true
    max_chars: 200000
path: "compiled/{section}.md"
source_agent: src/agents/citation_assembly.py
enabled: true
---
# Assemble and export the memo

Runs on the server inside compile: joins the sections, consolidates and renumbers citations, adds the table of contents, and exports HTML and PDF. Claude never receives this step.

It is listed so the registry, the docs, and `compile`'s report can name it;
it is never handed out by `next_step`, and nothing is submitted for it with
`submit_artifact`.

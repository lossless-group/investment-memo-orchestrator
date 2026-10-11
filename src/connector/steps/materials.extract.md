---
id: materials.extract
title: Extract text from materials
phase: materials
scope: deal
required: true
runs_on: server
needs_partner: false
order: 10
version: "0"
reads: ["materials:*"]
produces:
  kind: material
  checks:
    not_empty: true
    max_chars: 200000
path: "materials/{section}.md"
source_agent: src/agents/dataroom
enabled: true
---
# Extract text from materials

Runs on the server inside add_materials: extracts each material's text to the workspace and keeps the original in the firm's bucket. Claude never receives this step.

It is listed so the registry, the docs, and `compile`'s report can name it;
it is never handed out by `next_step`, and nothing is submitted for it with
`submit_artifact`.

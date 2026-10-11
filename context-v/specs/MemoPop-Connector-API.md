---
type: Specs
title: "MemoPop Connector API"
lede: "Eight tools, one step registry, and the docs and tests that ship with each. What we build so a partner's Claude can write a MemoPop memo."
publish: true
date_created: 2026-10-10
date_modified: 2026-10-10
date_authored_initial_draft: 2026-10-10
date_authored_current_draft: 2026-10-10
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5 (1M context)
at_semantic_version: 0.0.0.4
status: Draft
category: Specification
site_uuid: f32ada52-1cdb-4348-9170-42eebdbc9bd3
hex_code: 2blght
summary: >-
  Spec of record for v1 of the MemoPop connector: a remote MCP server (and
  matching versioned REST API) at memopop.didi.sh that hands a client's Claude
  the memo method one step at a time and keeps every artifact. Defines the
  concepts, the step registry and how today's LangGraph nodes map onto it, the
  eight tools with inputs, outputs, and errors, the error envelope, versioning,
  auth, storage layout, the agent-facing documentation set (with a worked
  example entry and the generation targets), and the full test suite from
  registry lint to the live health check. Built on the eight decisions in
  context-v/decisions/. Ends with the plan split and the questions that are
  still open. Read before writing any plan or code for the connector.
tags:
  - MemoPop
  - Claude-Connector
  - Model-Context-Protocol
  - Hosted-API
  - API-Docs-For-Agents
  - Testing
  - Specification
---

# MemoPop Connector API

## Why care?

A partner should be able to open Claude on their laptop or phone, say *start a
memo on Acme*, and end up with a MemoPop-quality memo: researched section by
section, shaped by their own comments, compiled to a branded PDF. The
partner's Claude does the thinking. This API is what lets it follow our method,
keep every artifact, and never lose the partner's work.

It is also **our first API**. Whatever habits it sets for docs, tests, errors,
and versioning, every later API in the tree will copy.

## Built on these decisions

| Decision | What it fixes for this spec |
|---|---|
| [[The-Clients-Claude-Does-the-Work]] | v1 makes no model calls of its own |
| [[The-Server-Hands-Claude-the-Method-One-Step-at-a-Time]] | The step registry and the eight tools |
| [[One-Workspace-Per-Firm-With-a-Private-Bucket]] | Tenancy and storage layout |
| [[jj-Versions-Text-and-Saves-Snapshot-to-the-Bucket]] | History and `save_snapshot` |
| [[Host-the-Connector-on-Railway-at-memopop-didi-sh]] | Where it runs and its URLs |
| [[Sign-In-Through-didi-sh-OAuth]] | Auth |
| [[No-Tool-Ships-Without-Its-Docs-and-Tests]] | The definition of done |
| [[Three-Kinds-of-Error-and-Optional-Steps-Never-Block]] | The error model |

The reasoning behind each lives in those records and in
[[MemoPop-as-a-Claude-Connector]]. This spec says only what to build.

## Scope

**In v1:** the eight tools over MCP and REST, the step registry, per-firm
workspaces on a Railway volume, jj history, snapshots to a per-firm bucket,
compile to HTML and PDF, didi.sh sign-in, the docs set, and the test suite
including the live health check.

**Not in v1:** server-side model calls or research APIs, a full-pipeline job,
any web UI beyond the upload page and the docs, billing, per-deal access
inside a firm, and migrating the eleven existing firms (its own plan, last).

## Concepts

| Term | Meaning |
|---|---|
| **Firm** | A client organisation; a didi.sh entity. Owns one workspace and one bucket |
| **Deal** | One company being evaluated, inside a firm. Has a memo template (an outline) and a state |
| **Material** | Anything the partner provides: deck, dataroom, financials, notes, a link. Original in the bucket, extracted text on the volume |
| **Step** | One unit of the method: an instruction for Claude, the artifacts it reads, and the artifact it must produce |
| **Artifact** | A text file a step produces: a research file, a section draft, an enhancement. Versioned by jj |
| **Skip** | A record that an optional step didn't run, and why. Can be re-run later |
| **Snapshot** | A partner-requested backup of the firm's workspace, written to the firm's bucket |

## Where the code lives

All server code lives in **`memopop-orchestrator`**, beside the existing
FastAPI app in `src/server/`, not in `memopop-ai`. New package:

```
src/connector/
  registry/        # step definitions and tool definitions, the single source
  tools/           # one module per tool; pure functions over a Workspace
  steps/           # instruction text per step (markdown), loaded by the registry
  workspace.py     # firm/deal paths under MEMO_IO_ROOT, jj, bucket client
  errors.py        # the error envelope and codes
  auth.py          # token verification, firm resolution
  mcp_app.py       # MCP server built from the registry
  rest_app.py      # /v1 REST routes built from the registry
  docs_build.py    # llms.txt, /docs, OpenAPI enrichment, all from the registry
```

- **MCP** uses the official MCP Python SDK over Streamable HTTP, mounted on the
  existing FastAPI app at `/mcp`.
- **REST** routes are generated from the same registry under `/v1/`.
- **Tool functions are transport-free.** A tool takes typed input and a
  `Workspace`, returns typed output or raises a typed error. MCP and REST are
  thin adapters, so both behave identically and tests can call tools directly.
- **The existing 22 routes stay** for the Tauri app. The connector doesn't
  depend on them.

## The step registry

Every step is declared once:

| Field | Meaning |
|---|---|
| `id` | Stable name, e.g. `research.section`, `draft.section`, `enhance.tables` |
| `phase` | `materials`, `research`, `draft`, `enhance`, `compile` |
| `scope` | `deal` (runs once) or `section` (runs once per outline section) |
| `required` | Required steps may block; optional steps skip ([[Three-Kinds-of-Error-and-Optional-Steps-Never-Block]]) |
| `runs_on` | `claude` (handed out by `next_step`) or `server` (runs inside `compile` or `add_materials`, no model) |
| `instruction` | Path to the step's markdown instruction, written for Claude |
| `reads` | Which artifacts and materials the step receives |
| `produces` | The artifact kind it must submit, with checks (required headings, citation format, length range) |
| `needs_partner` | The step ends only when the partner has approved the artifact |
| `source_agent` | The agent in `src/agents/` the instruction was adapted from |
| `enabled` | Ops switch. A disabled optional step is skipped with `step_disabled` |

### First mapping from today's workflow

A first cut, to be confirmed in plan 1. Nodes that only rearrange files or
citations become **server steps** with no model; nodes that need judgment
become **Claude steps**; nodes that depend on our research APIs wait for v2.

| Step | Phase / scope | Runs on | Required | From today's nodes |
|---|---|---|---|---|
| `materials.extract` | materials / deal | server | yes, if materials exist | text extraction half of `dataroom`, `deck_analyst` |
| `materials.brief` | materials / deal | claude | no | judgment half of `deck_analyst`, `dataroom` |
| `research.section` | research / section | claude, `needs_partner` | yes | `section_research`, `research`, `competitive_researcher` (competition section) |
| `research.sources` | research / deal | claude, `needs_partner` | no | `aggregate_sources` |
| `draft.section` | draft / section | claude | yes | `draft` (`writer`) |
| `enhance.tables` | enhance / section | claude | no | `generate_tables` |
| `enhance.diagrams` | enhance / deal | claude | no | `generate_diagrams`, `enrich_visualizations` |
| `enhance.citations` | enhance / section | claude | no | `cite`, `validate_citations` |
| `enhance.fact_check` | enhance / section | claude | no | `fact_check`, `attribution_audit`, `fact_correct` |
| `enhance.scorecard` | enhance / deal | claude | no | `scorecard`, `integrate_scorecard`, `scorecard_nav` |
| `enhance.summaries` | enhance / deal | claude | no | `revise_summaries` |
| `enhance.one_pager` | enhance / deal | claude | no | `one_pager` |
| `compile.assemble` | compile / deal | server | yes | `cleanup_sections`, `assemble_citations`, `fix_citation_spacing`, `toc`, `inject_deck_images`, `finalize`, export |
| *(v2)* | — | — | — | `fact_verify` (Perplexity), `enrich_trademark`, `enrich_socials`, `enrich_links`, `competitive_evaluator` |

Each Claude step's instruction is adapted from its source agent's prompt, with
everything about calling models and APIs removed and an explicit "submit with
`submit_artifact`" ending. The outline (`templates/outlines/*.yaml`) supplies
the section list and each section's guidance.

### Deal state

The server is the only source of truth for where a deal stands. `next_step`
returns the first step that is not done, in this order: materials, then each
section's research (approved), then each section's draft, then enhancements,
then compile. Rules:

- A section can't be drafted until its research is partner-approved.
- Enhancements run only when every section has a draft.
- `compile` is always allowed once every section has a draft; it reports any
  enhancement that hasn't run or was skipped.
- Submitting an artifact again replaces it as a new jj change. Earlier versions
  stay in history. Resubmitting identical content changes nothing, except that
  it may record the partner's approval (research is often saved first and
  approved later, unchanged); that does not bump the version.
- `research.sources` runs after every section's research and before the first
  draft, since drafting cites the approved sources.
- Claude can't decline an optional step on its own; an optional Claude step it
  can't do is skipped through `submit_artifact` with `skip: true` and a reason
  (added in plan 5).

## The tools

All eight, over both MCP and REST. `RO` is `readOnlyHint`, `D` is
`destructiveHint`; Claude requires both on every tool.

| Tool | REST | RO | D | Blocks? |
|---|---|---|---|---|
| `list_deals` | `GET /v1/deals` | yes | no | no |
| `create_new_deal` | `POST /v1/deals` | no | no | yes (required) |
| `add_materials` | `POST /v1/deals/{deal}/materials` | no | no | no |
| `next_step` | `POST /v1/deals/{deal}/next-step` | no* | no | no |
| `submit_artifact` | `POST /v1/deals/{deal}/artifacts` | no | no | yes, for required steps |
| `get_artifact` | `GET /v1/deals/{deal}/artifacts/{id}` | yes | no | no |
| `save_snapshot` | `POST /v1/snapshots` | no | no | no |
| `compile` | `POST /v1/deals/{deal}/compile` | no | no | yes (required) |

\* `next_step` records skips and marks the step handed out, so it isn't
read-only even though it changes no artifacts.

No v1 tool deletes anything, so none is destructive. Overwriting an artifact
keeps the old version in jj.

### Inputs and outputs

**`list_deals`** `{ cursor?, limit? (default 20, max 100) }` →
`{ deals: [{ deal, company, stage, template, phase, next_step_hint,
materials_pending, skips: [...] , updated_at }], next_cursor? }`

**`create_new_deal`** `{ company, url?, stage?, template? }` → `{ deal,
created: bool, template, sections: [...] }`. The deal slug is derived from the
company's domain when `url` is given, otherwise from the name. A second call
for the same company returns the existing deal with `created: false`.
`template` defaults to the firm's default outline; an unknown template is
`invalid`.

**`add_materials`** `{ deal, items: [{ kind: deck | dataroom | financials |
notes | other, link? , text?, filename? }] }` → `{ accepted: [{ material_id,
status: queued | ready }], upload_url?, upload_expires_at? }`. A `link` is
fetched by the server; `text` (up to 100,000 characters) is stored directly;
an item with only `filename` gets a one-time upload page at `upload_url`.
Returns immediately; extraction runs in the background and `list_deals` shows
`materials_pending` until it's done.

**`next_step`** `{ deal }` → `{ step_id, phase, section?, instruction,
inputs: [{ artifact_id, title, text }], produces: { kind, checks },
needs_partner, skipped_since_last_call: [...] , progress: { done, total } }`.
When the deal is finished: `{ step_id: null, done: true, compile_ready: true }`.

**`submit_artifact`** `{ deal, step_id, section?, content, partner_approved?,
partner_notes? }` → `{ artifact_id, version, checks: [{ name, passed, detail }],
advanced: bool, next_hint }`. Failed checks return `invalid` with each failure
listed, and nothing is saved. Submitting identical content twice is a no-op
that returns the same `version`.

**`get_artifact`** `{ deal, artifact_id | material_id, version?, offset? }` →
`{ title, kind, version, text, next_offset? }`. Text is paged at 100,000
characters to stay under Claude's 150,000-character result limit.

**`save_snapshot`** `{ label? }` → `{ snapshot_id, label, created_at, bytes,
files_added, files_changed, files_removed }`. Snapshots the whole firm
workspace; the change counts are against the previous snapshot.

**`compile`** `{ deal, formats?: [html, pdf] }` → `{ html_url, pdf_url,
version, report: { sections, enhancements_run, skipped: [...] } }`. The links
are signed and expire after seven days. If compiling would exceed 240 seconds,
it returns `{ job_id, status: running }` and `list_deals` reports completion.

## Errors

Every failure, on both transports, uses one envelope:

```json
{
  "ok": false,
  "error": {
    "kind": "down | invalid | skipped",
    "code": "deal_not_found",
    "message": "No deal called 'acme' in this workspace.",
    "next": "Call list_deals to see this firm's deals, or create_new_deal to start one.",
    "retry_after_seconds": null,
    "details": {}
  },
  "api_version": "1"
}
```

- **MCP:** a tool result with `isError: true` and the envelope as structured
  content, plus `message` and `next` as text so any client reads them.
- **REST:** `down` → 503 (with `Retry-After`) or 504; `invalid` → 400, 401,
  403, 404, 409, or 422 as fits; `skipped` → 200, because the call succeeded.
- **`skipped` is reported, not raised.** `next_step` returns the next runnable
  step and lists anything it skipped in `skipped_since_last_call`; `compile`
  lists skips in its report.

Starting codes (each must have a docs entry):

| Kind | Codes |
|---|---|
| `down` | `service_unavailable`, `storage_unavailable`, `timeout`, `internal_error` |
| `invalid` | `unauthenticated`, `forbidden_firm`, `deal_not_found`, `artifact_not_found`, `template_not_found`, `validation_failed`, `checks_failed`, `step_out_of_order`, `research_not_approved`, `material_too_large`, `link_unreachable`, `unsupported_version`, `not_implemented` |
| `skipped` | `step_disabled`, `step_failed`, `material_unreadable` |

## Versioning

- REST lives under `/v1/`; MCP advertises server version `1.x` and every
  response carries `api_version`.
- **Additive changes** (new optional input, new output field, new tool, new
  error code) stay in v1 and land in the API changelog.
- **Breaking changes** (removing or renaming anything, a new required input,
  changing a meaning) need `/v2/` and a new MCP server version, with v1 kept
  running until no firm uses it.
- **Step instructions are content, not API.** They can improve freely, which
  is the point of keeping the method on the server. Each handed-out step
  records the instruction's version on the artifact it produces.

## Auth

Per [[Sign-In-Through-didi-sh-OAuth]]:

- **The connector URL partners enter is `https://memopop.didi.sh/mcp`.**
  Claude requires the protected-resource document's `resource` to equal that
  URL exactly, path included (Claude's *Authentication for connectors*,
  checked 2026-10-10). So MemoPop serves the document at
  `https://memopop.didi.sh/.well-known/oauth-protected-resource/mcp` (and the
  same document at `/.well-known/oauth-protected-resource`), with `resource`
  `https://memopop.didi.sh/mcp` and `authorization_servers`
  `["https://id.didi.sh"]`.
- A request without a valid token gets **401** (Claude ignores
  `WWW-Authenticate` on a 200) with `WWW-Authenticate: Bearer
  resource_metadata="https://memopop.didi.sh/.well-known/oauth-protected-resource/mcp"`.
- Tokens are verified against `https://id.didi.sh/.well-known/jwks.json`
  (EdDSA, header `typ: at+jwt`). id.didi.sh resolves any resource at or below
  a registered one to the registered URI, so the audience is
  `https://memopop.didi.sh` whichever form Claude sends; MemoPop accepts that
  audience and also `https://memopop.didi.sh/mcp`. The firm comes from the
  `entity` claim, `{ "id": …, "slug": … }`. A person with more than one firm
  passes `firm` explicitly.
- **Until didi.sh OAuth ships,** a per-firm static key in a header works for
  Claude Code and the health check only. It is never given to a client and is
  removed from the code path the day OAuth works.

## Storage

On the Railway volume, `MEMO_IO_ROOT=/data/firms`:

```
/data/firms/<firm>/            # one jj repository per firm
  deals/<deal>/
    deal.json                  # template, state, step log, skips
    materials/<id>.md          # extracted text (originals in the bucket)
    research/<section>.md
    sections/<section>.md
    enhancements/<step>/...
    compiled/<version>/        # HTML and PDF also copied to the bucket
```

- After every saved artifact, the server makes one jj commit with a message
  naming the step, deal, and section.
- Originals of materials, compiled PDFs, and snapshots live in the firm's
  bucket under `materials/`, `compiled/`, and `snapshots/`.
- Writes to `deal.json` are serialized per deal (the existing unlocked
  `versions.json` pattern is not reused).
- Code that hardcodes `Path("io")` is not called by the connector; anything
  reused is first fixed to honour `MEMO_IO_ROOT`.

## Docs

Per [[No-Tool-Ships-Without-Its-Docs-and-Tests]]. The docs are part of the
registry, not a separate site to keep in sync.

### Each tool's docs entry

Structured fields on the tool definition:

| Field | Rule |
|---|---|
| `summary` | One sentence starting with what it does. Shown first in the MCP description |
| `when_to_use` | The situations, in the partner's words where possible |
| `when_not_to_use` | The nearest wrong choice and what to call instead |
| `inputs` | Each input: meaning, type, required or not, an example |
| `returns` | Each output field in a sentence |
| `changes` | What it changes on the server, or "nothing" |
| `duration` | Typical and worst case |
| `errors` | Every code it can return, with its `next` text |
| `next` | What to call afterwards |
| `examples` | At least one full request and response, which the tests execute |

### A worked example: `create_new_deal`

> **create_new_deal** — Start a new deal for a company this firm has no record
> of yet.
>
> **Use when** the partner names a company to write a memo on and
> `list_deals` doesn't show it. **Don't use** to continue an existing deal:
> call `next_step` with its slug instead. Calling this twice for the same
> company is safe; it returns the existing deal.
>
> **Inputs.** `company` (required): the company's name, e.g. `"Acme Robotics"`.
> `url`: its website, e.g. `"https://acme.ai"`; strongly preferred, because it
> makes the deal slug unambiguous. `stage`: e.g. `"Seed"`, `"Series A"`.
> `template`: the memo outline to use; omit for the firm's default.
>
> **Returns** the deal slug, whether it was newly created, the template, and
> the list of sections the memo will have.
>
> **Changes** creates the deal folder and its first history entry.
> **Takes** under a second.
>
> **Errors.** `template_not_found`: the template name is wrong; call again
> without `template`. `validation_failed`: `company` is empty. `down` kinds:
> tell the partner and try later.
>
> **Next:** ask the partner for their materials and call `add_materials`, or
> call `next_step` to begin research without them.

### What gets generated from the registry

| Output | For | Where |
|---|---|---|
| MCP tool descriptions and input schemas | Claude, at call time | `/mcp` |
| OpenAPI 3.1 with the docs fields in `description` | Any HTTP client, codegen | `/v1/openapi.json` |
| `llms.txt` | Agents finding their way: what MemoPop is, the flow, every tool with a one-line summary and a link | `/llms.txt` |
| `llms-full.txt` | The complete docs in one file | `/llms-full.txt` |
| A readable docs page | Partners and developers | `/docs` |
| The error reference | Everyone; one entry per code | `/docs/errors` |
| The API changelog | Anyone integrating | `/docs/changelog` |

### Docs that aren't generated

- **The plugin's skill.** A thin `SKILL.md` that tells Claude: this is a
  multi-step pipeline with an artifact trail; always call `next_step` and do
  only what it says; show the partner every research file and wait for their
  approval; on `skipped`, say so in one line and continue; on `down`, stop and
  tell the partner. Its text is reviewed like code, because it governs every
  run.
- **Step instructions** (`src/connector/steps/*.md`), written for Claude: the
  goal, what good output looks like, the format, and how to submit.
- **A short operator guide**: provisioning a firm, its bucket, and its sign-in;
  disabling a broken step; reading the health check.

### Writing style for agent-facing docs

Second person, imperative, plain words. The first sentence says what the tool
does; the second says when to call it. Every error tells the caller what to do
next. No marketing. A description that makes Claude call the wrong tool is a
bug, and is filed and tested like one.

## The test suite

Per [[No-Tool-Ships-Without-Its-Docs-and-Tests]]. pytest, as today. **The
orchestrator has no test workflow yet** (its only workflow deploys Pages), so
plan 1 adds one. It must check out with `submodules: false`, because the
`io/<firm>` repos are private, so **no test may read `io/`**. Every fixture is
synthetic and lives in `tests/connector/fixtures/`.

### Fixtures

- **`test-firm`**: a firm with no client data, the default template, and a
  local fake bucket (a temp directory behind the same bucket interface).
- **`fixture-co`**: a deal with a three-section template, a two-page synthetic
  deck PDF, a short notes file, and canned artifacts for every step.
- **A fake Claude**: a script that walks the flow by calling tools and
  submitting the canned artifacts. No model is called anywhere in CI.

### The suite

| Layer | What it proves | Runs |
|---|---|---|
| **1. Registry lint** | Every tool has every docs field filled; every error code it lists exists and is documented; `readOnlyHint` and `destructiveHint` are set; every step has an instruction file, `reads`, `produces`, and a source agent; summaries stay short | Every CI run |
| **2. Docs examples execute** | Each docs example is sent to the tool and its response matches; generated OpenAPI validates; `llms.txt` lists every tool | Every CI run |
| **3. Tool contracts** | For each tool, on both MCP and REST: the normal case; bad input; unknown deal; no token; the wrong firm's token (must be `forbidden_firm`, and must reveal nothing about the other firm); repeat-safe calls; paging | Every CI run |
| **4. Transport parity** | The same call returns the same body over MCP and REST | Every CI run |
| **5. Flow** | The fake Claude takes `fixture-co` from creation to compile; order is enforced (drafting before approval is `research_not_approved`); identical resubmission is a no-op; a fresh "conversation" resumes from `next_step` | Every CI run |
| **6. Error kinds** | Disabling each optional step in turn yields a skip and a finished memo; a failing required step blocks with the right code; the storage fake raising yields `down` with nothing saved | Every CI run |
| **7. Storage** | Each saved artifact is one jj commit; `save_snapshot` writes to the bucket with correct change counts; two firms can't see each other's paths, artifacts, or bucket keys | Every CI run |
| **8. Limits** | No result exceeds 150,000 characters (`get_artifact` pages); `add_materials` returns within 5 seconds with a large fixture; `compile` falls back to a job past its time budget | Every CI run |
| **9. Auth against a real didi.sh** | Sign-in, token audience, refresh, rejection of a token minted for another audience | Once OAuth ships; against id.didi.sh's staging |
| **10. Live health check** | Signed in as `test-firm` on `memopop.didi.sh`: create a uniquely named deal, add the small deck, one research step, one draft, compile, then archive the deal. Records each call's time | Scheduled, every 30 minutes |
| **11. Real Claude** | Claude, through the Claude API's MCP connector support, runs `fixture-co` with the real skill and checks that it called tools in order, showed research before drafting, and handled a forced skip and a forced `down` correctly | Before each release, and on demand |

Layers 1–8 gate merges. Layer 10 alerts on any failed step or a call slower
than its documented worst case. Layer 11 is the only one that costs model
tokens, so it doesn't run per commit.

### Coverage rule

A new tool, step, or error code without its lint entry, a contract test, and a
docs example fails layer 1, so the rule enforces itself rather than relying on
review.

## Plans

Each is a file in `context-v/plans/`, owns the test IDs listed in §Tests, and
runs under [[Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents]].

1. **Foundation.** The registry, the error envelope, auth (static key and token
   verification), storage, `list_deals`, `create_new_deal`, `next_step`,
   `submit_artifact`, `get_artifact`, the docs generators, the ledger, and the
   CI workflow. Everything else builds on it.
2. **Deploy.** Dockerfile with the system tools, Railway service and volume,
   `memopop.didi.sh`, `test-firm`, and the scheduled live health check.
3. **didi.sh OAuth.** The authorization server on id.didi.sh, in that repo
   and under its own tests ([[Claude-Connectors-Need-didi-sh-to-Be-an-OAuth-Server]]).
   Runs in parallel with plan 1.
4. **Materials.** `add_materials`, the upload page, link fetching, extraction.
5. **Enhancements, compile, and the full flow.** The remaining step
   instructions, `compile`, skip handling, and the scripted end-to-end walks.
6. **History and snapshots.** jj per firm and `save_snapshot`.
7. **The plugin and real Claude.** The skill, packaging, and the real-Claude
   run.

Plans 4, 5, and 6 run in parallel once plan 1 lands. Migrating the eleven
existing firms is out of scope for this loop.

## Defaults chosen for v1

These were open in the exploration. Each is a judgment call made so the first
loop can run; the operator can override any of them, and each is cheap to
change later.

- **Materials arrive all three ways:** links, the one-time upload page, and
  inline text, as `add_materials` already specifies.
- **Section research is required**, not skippable.
- **Snapshots are a compressed archive** of the firm's workspace, written to
  the firm's bucket under `snapshots/`. Kopia can replace it later behind the
  same tool.
- **Buckets are S3-compatible** (Railway buckets in production, a local
  directory in tests), one per firm, reached through one bucket interface.
- **Health-check alerts** go through GitHub Actions: the check runs as a
  scheduled workflow, and a failed run notifies by GitHub's own email.
- **Compiled links expire after seven days; snapshots are kept** until a
  retention policy is decided.

## Tests

Every promise this spec makes, as an ID. IDs are stable forever: never
renumber; retire one by striking it through. Status is derived by
`scripts/spec_status.py`, never written here. Each plan owns a subset.

### Registry and docs (Plan 1)

| ID | Given / When / Then |
|---|---|
| `CONN-REG-01` | Given the registry, when it loads, then exactly the eight tools in §The tools are registered under those names |
| `CONN-REG-02` | Given any tool, then every docs field in §Each tool's docs entry is filled, and its summary is at most 200 characters |
| `CONN-REG-03` | Given any tool, then every error code it lists exists in the error catalogue and has a docs entry |
| `CONN-REG-04` | Given any tool, then it declares both `readOnlyHint` and `destructiveHint`, matching §The tools |
| `CONN-REG-05` | Given any step with `runs_on: claude`, then it has an instruction file that exists, `reads`, `produces`, and a `source_agent` that exists in `src/agents/` |
| `CONN-DOCS-01` | Given any tool's docs examples, when each request is sent to the tool, then the response matches the documented response |
| `CONN-DOCS-02` | When `/v1/openapi.json` is fetched, then it validates as OpenAPI 3.1 and has an operation for every tool, carrying its docs |
| `CONN-DOCS-03` | When `/llms.txt` and `/llms-full.txt` are fetched, then the first lists every tool with its summary and the second contains every docs entry |
| `CONN-DOCS-04` | When `/docs` and `/docs/errors` are fetched, then they render every tool and every error code |
| `CONN-DOCS-05` | When an MCP client lists tools, then each has a description built from its docs fields and an input schema |

### Errors, versioning, and auth (Plan 1)

| ID | Given / When / Then |
|---|---|
| `CONN-ERR-01` | Given any failing MCP call, then the result has `isError: true` and structured content with `kind`, `code`, `message`, `next`, and `api_version` |
| `CONN-ERR-02` | Given a failing REST call, then `invalid` maps to a 4xx status and `down` to 503 with `Retry-After` |
| `CONN-ERR-03` | Given the storage layer failing mid-call, then the caller gets `down` / `storage_unavailable` and nothing was saved |
| `CONN-ERR-04` | Given any response, success or failure, then it carries `api_version: "1"` |
| `CONN-AUTH-01` | Given a request with no credential, then it gets 401 with `WWW-Authenticate` pointing at the protected-resource document |
| `CONN-AUTH-02` | When `/.well-known/oauth-protected-resource/mcp` or `/.well-known/oauth-protected-resource` is fetched, even through a proxy that forwards plain http, then it names `https://id.didi.sh` first in `authorization_servers`, its `resource` is exactly `https://memopop.didi.sh/mcp`, and every URL in it is `https://` |
| `CONN-AUTH-03` | Given a credential for firm A, when it asks for firm B's deal, then it gets `invalid` with nothing revealed about firm B |
| `CONN-AUTH-04` | Given a token signed by a key in the configured JWKS, with audience `https://memopop.didi.sh` and an entity claim, then the request is served in that entity's workspace |
| `CONN-AUTH-05` | Given a token for another audience, an expired token, or one signed by an unknown key, then it gets 401 |

### Deals and steps (Plan 1)

| ID | Given / When / Then |
|---|---|
| `CONN-DEAL-01` | When `create_new_deal` runs with a company and a template, then the deal exists with that template's sections |
| `CONN-DEAL-02` | Given an existing deal, when `create_new_deal` runs again for the same company, then it returns that deal with `created: false` and makes no second one |
| `CONN-DEAL-03` | Given an unknown template, then `create_new_deal` returns `invalid` / `template_not_found` |
| `CONN-DEAL-04` | Given more deals than `limit`, then `list_deals` pages them with `next_cursor`, and `limit` above 100 is capped |
| `CONN-DEAL-05` | Given a deal with pending materials and a recorded skip, then `list_deals` shows its phase, `materials_pending`, and the skip |
| `CONN-STEP-01` | Given a new deal without materials, then `next_step` returns `research.section` for the first section |
| `CONN-STEP-02` | Given a section whose research isn't partner-approved, when its draft is submitted, then it returns `invalid` / `research_not_approved` |
| `CONN-STEP-03` | Given an artifact that fails its checks, then `submit_artifact` returns `invalid` / `checks_failed` listing each failure, and nothing is saved |
| `CONN-STEP-04` | Given an artifact already saved, when identical content is submitted again, then the same version is returned and nothing changes |
| `CONN-STEP-05` | When a step's artifact is accepted, then `next_step` returns the following step |
| `CONN-STEP-06` | Given a deal part-way through, when a new client session calls `next_step`, then it gets the same step the previous session would have |
| `CONN-STEP-07` | Given an artifact longer than 100,000 characters, then `get_artifact` pages it, and no tool result exceeds 150,000 characters |
| `CONN-STEP-08` | Given the same call over MCP and over REST, then both return the same body |
| `CONN-STEP-09` | Given a step that hasn't been handed out, when an artifact is submitted for it, then it returns `invalid` / `step_out_of_order` |

### Materials (Plan 4)

| ID | Given / When / Then |
|---|---|
| `CONN-MAT-01` | When `add_materials` receives inline text, then it is stored and `ready` |
| `CONN-MAT-02` | When `add_materials` receives a reachable link, then it is fetched and becomes `ready`; given an unreachable link, then the material is recorded as a skip with `material_unreadable` and the deal can continue |
| `CONN-MAT-03` | Given an item with only a filename, then an upload URL is returned; an upload through it succeeds once, and a second use or an expired link is refused |
| `CONN-MAT-04` | Given a large file, then `add_materials` returns within 5 seconds and extraction finishes in the background |
| `CONN-MAT-05` | Given a PDF deck, then its text is extracted to the workspace and the original is in the firm's bucket under `materials/` |
| `CONN-MAT-06` | Given inline text over 100,000 characters, then it returns `invalid` / `material_too_large` |
| `CONN-MAT-07` | Given materials that are `ready`, then `next_step` offers `materials.brief` before research |

### Enhancements, compile, and the full flow (Plan 5)

| ID | Given / When / Then |
|---|---|
| `CONN-ENH-01` | Given every section drafted, then `next_step` hands out the enhancement steps in registry order |
| `CONN-ENH-02` | Given any one optional step disabled, then it is skipped with `step_disabled`, the flow continues, and compile succeeds |
| `CONN-ENH-03` | Given an optional server step that raises, then it is skipped with `step_failed` and the flow continues |
| `CONN-CMP-01` | Given every section drafted, when `compile` runs, then it returns working HTML and PDF links and a report of sections, enhancements run, and skips |
| `CONN-CMP-02` | Given a section without a draft, then `compile` returns `invalid` |
| `CONN-CMP-03` | Given a compile that would exceed its time budget, then it returns a `job_id` and `list_deals` reports when it finishes |
| `CONN-CMP-04` | Given section drafts with citations, then the compiled memo has its citations consolidated and renumbered |
| `CONN-FLOW-01` | Given the fixture deal, when the scripted client walks it from creation to compile over MCP, then every step succeeds and the compiled memo contains every section |
| `CONN-FLOW-02` | The same walk over REST succeeds identically |

### History and snapshots (Plan 6)

| ID | Given / When / Then |
|---|---|
| `CONN-HIST-01` | When an artifact is saved, then exactly one jj change is recorded, its description naming the step, deal, and section |
| `CONN-HIST-02` | When identical content is resubmitted, then no jj change is recorded |
| `CONN-HIST-03` | When `save_snapshot` runs, then an archive is written to the firm's bucket under `snapshots/`, with change counts against the previous snapshot |
| `CONN-HIST-04` | Given two firms, then their jj repositories and bucket locations are separate and neither can reach the other's |
| `CONN-HIST-05` | Given binary materials, then none is inside the jj working copy |

### Deploy and live health (Plan 2)

| ID | Given / When / Then |
|---|---|
| `CONN-LIVE-01` | Given a base URL and a key, when the health-check script runs against a local server, then it walks the short flow and exits 0; given a failing or slow step, it exits non-zero naming it |
| `CONN-LIVE-02` | Given the deployed service, then `https://memopop.didi.sh/healthz`, `/llms.txt`, and the protected-resource document answer over https |

### The plugin and real Claude (Plan 7)

| ID | Given / When / Then |
|---|---|
| `CONN-PLUG-01` | Given the plugin's skill, then it states each rule in §Docs that aren't generated: always call `next_step`, show research and wait for approval, one line on `skipped`, stop on `down` |
| `CONN-PLUG-02` | Given an API key, when Claude runs the fixture deal through the connector, then it calls tools in order, shows research before drafting, and handles a forced skip and a forced `down` correctly |

## Done when

1. A partner at a test firm adds the connector in Claude Desktop, signs in with
   didi.sh, and produces a compiled memo on a new deal with research shown and
   approved section by section.
2. Turning off any enhancement still produces a memo, with the skip in its
   report.
3. Every tool has a complete docs entry, and `/llms.txt`, `/docs`, and
   `/v1/openapi.json` are live.
4. Layers 1–8 pass in CI, and the live health check has run green for a week.

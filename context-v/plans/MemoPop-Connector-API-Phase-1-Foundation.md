---
type: Plans
title: "MemoPop Connector API, Phase 1: Foundation"
lede: "The registry, errors, auth, storage, five tools, the docs generators, the ledger, and CI. Every later phase builds on this one."
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
at_semantic_version: 0.0.0.1
status: Ready
spec_reference: context-v/specs/MemoPop-Connector-API.md
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/plan-1-foundation
owns_test_ids: [CONN-REG-01, CONN-REG-02, CONN-REG-03, CONN-REG-04, CONN-REG-05, CONN-DOCS-01, CONN-DOCS-02, CONN-DOCS-03, CONN-DOCS-04, CONN-DOCS-05, CONN-ERR-01, CONN-ERR-02, CONN-ERR-03, CONN-ERR-04, CONN-AUTH-01, CONN-AUTH-02, CONN-AUTH-03, CONN-AUTH-04, CONN-AUTH-05, CONN-DEAL-01, CONN-DEAL-02, CONN-DEAL-03, CONN-DEAL-04, CONN-DEAL-05, CONN-STEP-01, CONN-STEP-02, CONN-STEP-03, CONN-STEP-04, CONN-STEP-05, CONN-STEP-06, CONN-STEP-07, CONN-STEP-08, CONN-STEP-09]
site_uuid: 6689b1dc-617e-48ba-a04e-375e7397802c
hex_code: 75v8ck
tags:
  - Plan
  - MemoPop
  - Claude-Connector
  - Model-Context-Protocol
  - TDD
---

# MemoPop Connector API, Phase 1: Foundation

Read the spec first: `context-v/specs/MemoPop-Connector-API.md`. It is the
contract; this plan is the order of work. Then read the loop:
`context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md`.

## What this phase delivers

A running FastAPI app that serves the connector over MCP at `/mcp` and REST at
`/v1/`, with five working tools (`list_deals`, `create_new_deal`,
`next_step`, `submit_artifact`, `get_artifact`), all eight tools declared in
the registry (the other three registered with full docs but returning
`invalid` / `not_implemented` until their phases land, which keeps
`CONN-REG-01` honest from day one), generated docs, auth, the ledger, and a CI
workflow that runs it all.

**Phases 4, 5, and 6 will run in parallel on top of this.** Lay the code out so
each of them touches mostly its own files: one module per tool under
`src/connector/tools/`, one instruction file per step under
`src/connector/steps/`, and tool and step registration that adds a line per
item rather than editing shared logic.

## Step 0: the ledger and the ladder (do first)

Copy corpora-builder's ledger, knots-style (copy, never import across repos):

- `../../../corpora-builder/src/ledger.py` → `src/ledger.py`
- `../../../corpora-builder/scripts/spec_status.py` → `scripts/spec_status.py`
- The spec-marker and results hooks from
  `../../../corpora-builder/tests/conftest.py` → `tests/conftest.py`

Adapt:

- **The Tests section ends only at a level-2 heading.** This spec groups its
  IDs under `###` subheadings; corpora-builder's parser stops at any heading.
- Drop the frontend (`app/`) merging.
- Specs without a `## Tests` table are ignored (the orchestrator has many).
- Add `.spec-results.json` to `.gitignore`.
- Add `--plan <file>` (or `--ids`), so a plan's owned IDs can be checked alone.

Add `scripts/check.sh`, the ladder: `ruff check src/connector tests/connector`,
`black --check src/connector tests/connector`, `pytest`, then the ledger.
Scope lint to the new code; don't reformat the rest of the repo.

Add `.github/workflows/connector-tests.yml`: on push and pull request to
`development` and `main`, check out with **`submodules: false`**, install with
`uv`, install `jj` and `pandoc`, run `scripts/check.sh`. Then run the whole
existing suite in a fresh clone without `io/`; if existing tests fail there,
don't edit them. Make CI run the connector tests and the ledger as blocking and
report the rest, and say so in the changelog.

## Step 1: failing tests (the TDD floor)

Write `tests/connector/` with one test per owned ID, each marked
`@pytest.mark.spec("CONN-…")`. Fixtures in `tests/connector/fixtures/`: the
`test-firm` workspace under `tmp_path`, `fixture-co` with a three-section
outline, a local-directory bucket, and canned artifacts. Nothing reads `io/`.

Run `scripts/spec_status.py --plan` on this plan. Every owned ID must be RED,
none MISSING, before any implementation.

## Step 2: implement, in this order

1. **`errors.py`**: the envelope and the full code catalogue from the spec,
   each with its kind and docs text. `api_version` on every response.
2. **`workspace.py`**: firm and deal paths under `MEMO_IO_ROOT`, `deal.json`
   with a per-deal lock, artifact read and write, and a `Bucket` interface with
   a local-directory implementation and an S3 implementation (endpoint, key,
   and bucket from env; boto3 is fine). jj and snapshots are phase 6: leave a
   `History` hook that phase 6 fills (a no-op here).
3. **`registry/`**: tool and step definitions as dataclasses, matching the
   spec's field tables. Register all eight tools with complete docs, and the
   steps from §First mapping. Write the instruction files for
   `research.section` and `draft.section` now, adapted from
   `src/agents/perplexity_section_researcher.py` and `src/agents/writer.py`
   (strip every model and API call; end with how to submit). Other Claude
   steps get a stub instruction that phase 5 replaces, but must still satisfy
   `CONN-REG-05`.
4. **The five tools**, as transport-free functions over a `Workspace`. Deal
   state and ordering per §Deal state. Templates come from
   `templates/outlines/*.yaml`; the firm default is
   `direct-early-stage-12Ps` unless the firm config says otherwise.
5. **`auth.py`**: static per-firm keys from env (`MEMOPOP_STATIC_KEYS`, for
   Claude Code and the health check only), and JWT verification against a
   JWKS URL (`MEMOPOP_JWKS_URL`, default `https://id.didi.sh/.well-known/jwks.json`)
   with audience `https://memopop.didi.sh` and the firm from the entity claim.
   Tests use a locally generated EdDSA keypair and a served JWKS; nothing calls
   id.didi.sh. Serve `/.well-known/oauth-protected-resource`, building URLs
   from a configured public base URL, never from the request scheme
   (`CONN-AUTH-02`).
6. **`mcp_app.py` and `rest_app.py`**: both generated from the registry. Use
   the official MCP Python SDK (`mcp`) over Streamable HTTP, mounted at `/mcp`
   on the existing app in `src/server/app.py`. Set `readOnlyHint` and
   `destructiveHint` on every tool. MCP and REST must return the same body
   (`CONN-STEP-08`).
7. **`docs_build.py`**: `/v1/openapi.json`, `/llms.txt`, `/llms-full.txt`,
   `/docs`, `/docs/errors`, `/docs/changelog`, all from the registry. Plain
   server-rendered HTML for `/docs`; no frontend build.

Re-read `context-v/Transport-Contract-and-API-Conventions.md` before naming
anything; follow it where it doesn't conflict with the spec.

## Rules

- Never edit a test to make it pass. If a test can't pass against honest code,
  stop and report it.
- No model calls anywhere in the connector, and no new `anthropic` client
  (`tests/test_pipeline_reference.py` enforces the latter).
- The existing 22 routes and their tests keep working.
- Add dependencies with `uv add`; never `pip`.
- Don't touch `io/`, `main`, or `master`.

## Done when

- `scripts/check.sh` passes and the ledger shows every owned ID GREEN.
- The existing suite still passes locally (554 passed, 2 skipped at the start).
- CI is green on the branch.
- A changelog entry in `changelog/` (per `changelog-conventions`; see the
  repo's recent entries for shape) says what landed and what was *not* tested.
- The branch is pushed. Report back: the ledger output, the suite counts, the
  CI run URL, and anything in the spec you think is wrong.

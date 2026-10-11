---
type: Plans
title: "MemoPop Connector API, Phase 2: Deploy"
lede: "A container with every system tool the memo needs, running on Railway at memopop.didi.sh, watched by a health check every 30 minutes."
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
status: Built-Awaiting-Deploy
spec_reference: context-v/specs/MemoPop-Connector-API.md
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/plan-2-deploy
depends_on: [Phase-1-Foundation, Phase-4-Materials, Phase-5-Enhancements-Compile-and-Flow, Phase-6-History-and-Snapshots]
owns_test_ids: [CONN-LIVE-01, CONN-LIVE-02]
site_uuid: 32281f37-a9d6-457d-81ca-544b899d48b7
hex_code: la8s8g
tags:
  - Plan
  - MemoPop
  - Railway
  - Deployment
  - Monitoring
---

# MemoPop Connector API, Phase 2: Deploy

Numbered 2 in the spec, run after 4, 5, and 6 so the first deploy carries the
whole API. Read the spec (§Storage, §Auth, §The test suite, layer 10) and
[[Host-the-Connector-on-Railway-at-memopop-didi-sh]].

## Split of work

The **engineer** builds and tests everything that runs locally. The **VP Eng**
does everything outward-facing, with the operator's yes: creating the Railway
service, volume, and bucket, setting variables, DNS for `memopop.didi.sh`, and
the first deploy.

## Engineer steps

1. **Failing test** for `CONN-LIVE-01`: the health-check script run against a
   local server (uvicorn in a fixture) passes; with a step forced to fail or
   to be slow, it exits non-zero naming the step.
2. **`scripts/health_check.py`**: given a base URL and a key, create a uniquely
   named deal in `test-firm`, add a small inline material, take one research
   step and one draft step with canned artifacts, compile, then mark the deal
   archived. Time each call against its documented worst case.
3. **`Dockerfile`**: Python 3.11 slim; `uv` install; pandoc, WeasyPrint's
   libraries, poppler, tesseract, ghostscript, ImageMagick, and the `jj`
   binary. Runs `uvicorn` on `$PORT`, honouring `X-Forwarded-*` from Railway's
   proxy. `MEMO_IO_ROOT=/data/firms`. Build it locally and run the health
   check against the container.
4. **`.github/workflows/live-health.yml`**: every 30 minutes and on manual
   dispatch, runs the script against `https://memopop.didi.sh` with the key
   from repository secrets. `CONN-LIVE-02` is a gated test that runs only when
   `MEMOPOP_LIVE_URL` is set.
5. **`docs/operator/deploy.md`**: the variables, the volume, the bucket per
   firm, provisioning a firm, disabling a step.
6. Changelog, commit, push. Report what the VP Eng needs to provision.

## VP Eng steps (operator approval first)

Railway project and service from the repo's `development` branch, a volume
at `/data`, a bucket for `test-firm`, the variables, a custom domain
`memopop.didi.sh` (DNS record where didi.sh's DNS lives), the first deploy,
then `CONN-LIVE-02` and one manual health-check run.

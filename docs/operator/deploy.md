# Deploying and operating the MemoPop connector

The connector runs on Railway at `https://memopop.didi.sh`, from this repo's
`Dockerfile`. Partners connect Claude to `https://memopop.didi.sh/mcp`. This
guide covers the service, its variables, its volume, a firm's bucket,
provisioning a firm, switching a step off, and reading the health check.

Spec of record: `context-v/specs/MemoPop-Connector-API.md`. Plan:
`context-v/plans/MemoPop-Connector-API-Phase-2-Deploy.md`.

## What runs

- **Image:** `Dockerfile` (Python 3.13 slim, uv, pandoc, WeasyPrint's
  libraries, poppler-utils, tesseract, ghostscript, ImageMagick, jj 0.46.0).
  About 400 MB compressed.
- **Process:** `uvicorn --factory src.connector.serve:create_app` on `$PORT`,
  one process, as the unprivileged user `memopop`, honouring `X-Forwarded-*`.
  Every URL MemoPop publishes comes from `MEMOPOP_PUBLIC_BASE_URL`, never from
  the request.
- **Not** `src.server.app`. That app also carries the Tauri sidecar's routes
  (`/memos`, `/firms/...`, the sources API), which have no authentication and
  read and write firm data. Never deploy it publicly.
- **Railway config:** `railway.json`: Dockerfile builder, one replica,
  health check `GET /healthz`, restart on failure.
- **One replica only.** Background jobs (link fetches, extraction, long
  compiles) run inside the process, and per-deal locks are file locks on the
  volume. Don't scale out.

## Variables

Set these on the Railway service. **Secret** means: mark it sealed, keep the
canonical copy in the password manager, never commit it.

| Variable | Production value | Secret? |
|---|---|---|
| `MEMO_IO_ROOT` | `/data/firms` (the image's default) | no |
| `MEMOPOP_PUBLIC_BASE_URL` | `https://memopop.didi.sh` | no |
| `MEMOPOP_AUTH_ISSUER` | `https://id.didi.sh` (default) | no |
| `MEMOPOP_JWKS_URL` | `https://id.didi.sh/.well-known/jwks.json` (default) | no |
| `MEMOPOP_TOKEN_AUDIENCE` | `https://memopop.didi.sh` (default) | no |
| `MEMOPOP_STATIC_KEYS` | `test-firm=<key>` (comma-separated `firm=key` pairs; Claude Code and the health check only, never given to a client) | **yes** |
| `MEMOPOP_LINK_SECRET` | 64 random hex characters (`openssl rand -hex 32`). Without it, signed links to compiled memos stop working at every restart | **yes** |
| `MEMOPOP_COMPILE_BUDGET_SECONDS` | leave unset (`200`): compile returns a job past this | no |
| `MEMOPOP_DISABLED_STEPS` | empty; see "Switching a step off" | no |
| `MEMOPOP_BUCKET_BACKEND` | `s3` | no |
| `MEMOPOP_S3_FIRM_<FIRM>_BUCKET` | the firm's bucket name, from its Credentials tab | no |
| `MEMOPOP_S3_FIRM_<FIRM>_ACCESS_KEY_ID` | the firm's bucket key | **yes** |
| `MEMOPOP_S3_FIRM_<FIRM>_SECRET_ACCESS_KEY` | the firm's bucket secret | **yes** |
| `MEMOPOP_S3_FIRM_<FIRM>_ENDPOINT` | the bucket's endpoint (e.g. `https://t3.storageapi.dev`) | no |
| `MEMOPOP_S3_FIRM_<FIRM>_REGION` | the bucket's region, if its Credentials tab gives one | no |
| `MEMOPOP_S3_ENDPOINT`, `MEMOPOP_S3_ACCESS_KEY_ID`, `MEMOPOP_S3_SECRET_ACCESS_KEY`, `MEMOPOP_S3_REGION` | global fallbacks for any per-firm field left unset; may stay unset when every firm has its own | keys: **yes** |
| `MEMOPOP_S3_BUCKET_TEMPLATE` | fallback bucket name, `{firm}` replaced (`memopop-{firm}`); only used for a firm without `..._BUCKET` | no |
| `MEMOPOP_S3_ADDRESSING_STYLE` | `virtual` (default; Railway buckets). Use `path` only if a bucket's Credentials tab says so | no |
| `MEMOPOP_BUCKET_LOCAL_ROOT` | unset in production (only for the `local` backend) | no |
| `MEMOPOP_JJ_BIN` | unset (`jj` is on `PATH` in the image) | no |
| `PORT` | set by Railway | no |

`<FIRM>` is the firm's slug upper-cased with `_` for `-`: `test-firm` becomes
`MEMOPOP_S3_FIRM_TEST_FIRM_BUCKET`. A misspelt field name stops the server at
startup instead of sending a firm to the wrong bucket.

The connector reads no model or search API keys: v1 makes no model calls.

## The volume

- One Railway volume mounted at **`/data`**. Firms live in `/data/firms/<firm>/`
  (one jj repository each). With the `s3` backend nothing else goes there.
- The entrypoint creates `/data/firms` and gives it to the `memopop` user on
  every boot (it re-walks ownership only when something is wrong).
- The upload tokens live in `/data/firms/.uploads/` (hashed; no usable token is
  ever on disk).
- Back it up with `save_snapshot` per firm (to the firm's bucket), and with
  Railway's volume backups.

## A bucket per firm

Each firm gets its own Railway bucket; firms never share one.

1. In the Railway project, create a bucket named after the firm (e.g.
   `memopop-test-firm`).
2. From its **Credentials** tab, set on the service:
   `MEMOPOP_S3_FIRM_<FIRM>_BUCKET`, `..._ACCESS_KEY_ID`, `..._SECRET_ACCESS_KEY`,
   `..._ENDPOINT` (and `..._REGION` if shown). Railway variable references
   (`${{bucket.ACCESS_KEY_ID}}` style) are better than pasted values.
3. Redeploy so the service picks them up.

The bucket holds `materials/` (originals), `compiled/` (HTML and PDF; links
are presigned for seven days), and `snapshots/`.

## Provisioning a firm

A firm is a didi.sh entity. Its slug in MemoPop **must equal the entity's
slug**, because tokens carry `entity: {id, slug}` and MemoPop maps the slug to
`/data/firms/<slug>/`. Record the entity id too, so a token that carries only
the id still resolves.

```bash
railway ssh -- /opt/venv/bin/python /app/scripts/provision_firm.py <slug> \
  --entity-id <didi entity id> --default-template direct-early-stage-12Ps
```

This creates `/data/firms/<slug>/deals/` and `firm.json`
(`{"default_template": ..., "entity_id": ...}`). Re-running is safe: deals are
kept and `firm.json` is merged. Then create the firm's bucket (above).

**test-firm**, the health check's firm, also needs the one-section
`health-check` outline and a static key:

```bash
railway ssh -- /opt/venv/bin/python /app/scripts/provision_firm.py test-firm --health-check --new-key
```

`--new-key` prints a fresh key once (it is never written to disk). Put
`test-firm=<key>` in `MEMOPOP_STATIC_KEYS`, put the same key in the GitHub
repository secret `MEMOPOP_HEALTH_KEY`, and store it in the password manager.

A static key for a real firm is for Claude Code only, never for a client;
clients sign in through didi.sh.

## Switching a step off

If an optional step misbehaves (an enhancement producing bad output, say), set

```
MEMOPOP_DISABLED_STEPS=enhance.diagrams,enhance.scorecard
```

and redeploy. Disabled steps are skipped with `step_disabled`; the memo still
compiles and lists the skip in its report. Required steps (`research.section`,
`draft.section`, `compile.assemble`, materials extraction) can't be switched
off. Remove the variable to turn them back on.

## Reading the health check

`.github/workflows/live-health.yml` runs every 30 minutes (at :07 and :37) and
on manual dispatch (Actions, "Live health check", Run workflow; it takes an
optional origin). It needs the repository secret **`MEMOPOP_HEALTH_KEY`**
(test-firm's static key); without it, every run passes with the notice
"Live health check skipped".

Each run:

1. `scripts/health_check.py` walks test-firm through a new deal named
   `Health Check <UTC stamp> <random>`: `/healthz`, `list_deals`,
   `create_new_deal`, one inline note, `next_step` and `submit_artifact` until
   the deal is done (one partner-approved research step, one draft, canned
   enhancements, and a skip where canned text can't meet a step's checks),
   `compile`, and downloads of the signed HTML and PDF.
2. CONN-LIVE-02 (`tests/connector/test_live_deployed.py`) checks `/healthz`,
   `/llms.txt`, both protected-resource documents, and the 401 on `/mcp`,
   over https.

The run's summary has a table of every call: seconds taken, budget, result.
The budget is the call's documented worst case (each tool's `duration`) plus
2 seconds for the network. A failure ends with one line naming the step:

```
FAIL submit_artifact draft.section [01-health-check]: HTTP 503: storage_unavailable: ...
FAIL next_step: slow: 4.12s against a budget of 3.00s
FAIL healthz: unreachable: ConnectError: ...
```

GitHub emails the failure to whoever is watching the repository's Actions.
The JSON timings are kept as a run artifact for 7 days.

To run it by hand:

```bash
MEMOPOP_HEALTH_KEY=<test-firm key> uv run --no-project --with httpx \
  python scripts/health_check.py --base-url https://memopop.didi.sh
MEMOPOP_LIVE_URL=https://memopop.didi.sh uv run pytest -q --no-cov \
  tests/connector/test_live_deployed.py
```

`/healthz` alone answers `{"ok": true, "storage": "ok", "history": "jj"}`; it
is 503 when `/data/firms` isn't writable, and `"history": "off"` means jj is
missing and artifact history isn't being kept.

### Health-check deals accumulate

No v1 tool deletes anything, so each run leaves its deal in test-firm (about
48 a day). They are marked: slug `health-check-...`, stage `health-check`.
`create_new_deal` scans the firm's deals, so prune them now and then:

```bash
railway ssh -- sh -c 'find /data/firms/test-firm/deals -maxdepth 1 -name "health-check-*" -mtime +7 -exec rm -rf {} +'
```

Only ever in `test-firm`, and only `health-check-*`.

## First deploy, in order

1. Create the service from this repo's `development` branch (Dockerfile
   builder; `railway.json` is picked up).
2. Add a volume mounted at `/data`.
3. Create the `test-firm` bucket and set its `MEMOPOP_S3_FIRM_TEST_FIRM_*`
   variables, plus `MEMOPOP_BUCKET_BACKEND=s3`, `MEMOPOP_LINK_SECRET`, and
   `MEMOPOP_PUBLIC_BASE_URL`.
4. Deploy once, then provision test-firm (above) and set
   `MEMOPOP_STATIC_KEYS`; redeploy.
5. Add the custom domain `memopop.didi.sh`; create the CNAME Railway shows at
   didi.sh's DNS host; wait for the certificate.
6. Set `MEMOPOP_HEALTH_KEY` in the GitHub repository secrets, dispatch the
   workflow once, and check it passes.

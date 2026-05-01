---
title: "Wire memopop-native to the FastAPI sidecar"
lede: "End-to-end plan for closing the loop from Tauri click to live log stream — Rust dispatcher forwards JSON, browser EventSource handles SSE, sidecar spawns lazily."
date_authored_initial_draft: 2026-05-01
date_authored_current_draft: 2026-05-01
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-05-01
at_semantic_version: 0.0.0.1
status: Draft
augmented_with: Claude Code (Opus 4.7)
category: Plan
tags: [Tauri-Framework, FastAPI, Sidecar-Process, Rust, SSE, Server-Sent-Events, Integration, Memopop-Native]
authors:
  - Michael Staton
image_prompt: A blueprint-style cutaway of a desktop application connecting to a Python sidecar — translucent native window on the left, Rust dispatcher node in the middle routing JSON, a glowing localhost wire splitting into one path through the dispatcher and another path direct to a Server-Sent-Events stream, soft violet uplight, technical annotations in monospaced font.
date_created: 2026-05-01
date_modified: 2026-05-01
---

# Plan — Wire memopop-native to the FastAPI sidecar

## Context

We just shipped a FastAPI sidecar inside `investment-memo-orchestrator/src/server/` that wraps `generate_memo()` over HTTP (changelog: `2026-04-30_01.md`). It boots, all 7 routes register, error paths return correct codes — but no real `POST /memos` has been driven end-to-end through the orchestrator (would take 15–45 min and burn API credits).

memopop-native (the Tauri app at `memopop-ai/apps/memopop-native/`) currently stops at a "Ready to generate" placeholder panel inside `DealCreationModal.svelte` — when the user clicks Generate, nothing happens. The journey from "click an outline" to "see a memo run" has a missing middle.

Standing question was: *should we set up a testing framework, or wire up Tauri to drive the sidecar?* The orchestrator has no formal test suite today (pytest is in dev-deps but unused; the only `.github/workflows` runs GH Pages doc deploy). Standing up one for one new module is overkill. The high-leverage next step is closing the loop: **Tauri → Rust dispatcher → FastAPI sidecar → orchestrator → live log stream → artifacts**. That's the moment the entire onboarding journey actually pays off.

## Approach

**Wire Tauri to the sidecar end-to-end, with a small targeted unit-test subphase along the way for the security/tricky bits.**

Architecture decisions:

- **JSON requests go through the Rust dispatcher.** `POST /memos`, `GET /memos/{id}`, `GET /memos/{id}/artifacts*` get new match arms in `src-tauri/src/api/router.rs` that forward to the sidecar via `reqwest`. The Transport seam from session 02 stays unchanged.
- **SSE goes direct from webview to localhost:8765.** `EventSource` is browser-native; the FastAPI CORS allowlist already covers Tauri origins (`tauri://localhost`, `http://tauri.localhost`). No Rust streaming proxy needed. New `subscribeEvents()` method on the Transport interface.
- **Lazy sidecar spawn on first `/memos` call.** First `POST /memos` from Rust checks if sidecar is running; if not, spawns `{repoPath}/.venv/bin/python -m src.server` with `cwd={repoPath}`, polls `/healthz` until ready, then forwards. Stored as `Mutex<Option<CommandChild>>` in Tauri state. Killed on `WindowEvent::Destroyed`.
- **`running_job` flow stage** holds the live state (job_id, status, log buffer). Lives in `flow.svelte.ts` alongside the existing `create_deal` / `ready_to_run` stages.
- **JobLogViewer component** renders status pill + virtualized log tail. New file.

Why direct EventSource (not Rust-proxied): FastAPI already streams SSE correctly; webview natively consumes it; bypassing Rust avoids reimplementing chunked HTTP forwarding in the dispatcher. If CORS blocks (unlikely given the allowlist), fall back to `tauri::Emitter` events as a Rust-driven proxy — but cross that bridge only if we hit it.

## Phases

### Phase 0 — Targeted unit tests in the orchestrator (~30 min)

Lock down the tricky/security bits before they get exercised by Tauri. Not a framework — just a `tests/` directory with 5 tests.

- **`investment-memo-orchestrator/tests/__init__.py`** (empty).
- **`investment-memo-orchestrator/tests/test_server.py`** — five tests:
  1. `test_create_memo_request_rejects_empty_body` — Pydantic validation, expects 422.
  2. `test_log_sink_splits_on_newlines` — write `"a\nb\nc"`, expect 3 events; partial line buffered until flush.
  3. `test_event_bus_replays_backlog_to_late_subscribers` — publish 5 events, then subscribe, expect all 5 + live tail.
  4. `test_artifact_path_traversal_rejected` — `GET /memos/{id}/artifacts/../../etc/passwd` → 400.
  5. `test_get_unknown_job_returns_404`.
- **`pyproject.toml`** — add `[tool.pytest.ini_options]` block: `testpaths = ["tests"]`.
- **Run:** `.venv/bin/python -m pytest tests/ -v`.

Uses FastAPI's `TestClient` (no real `generate_memo()` calls — those tests would cost \$5+ each). Total time: minutes to write, milliseconds to run.

### Phase 1 — Tauri Rust: sidecar process + dispatcher forwarder (~2 hours)

Files in `memopop-ai/apps/memopop-native/`:

- **`src-tauri/Cargo.toml`** — add:
  ```toml
  reqwest = { version = "0.12", default-features = false, features = ["json", "rustls-tls"] }
  tokio = { version = "1", features = ["process", "time", "sync"] }
  ```
- **`src-tauri/src/api/sidecar.rs`** (new):
  - `pub struct SidecarManager { child: Mutex<Option<CommandChild>>, port: u16 }`
  - `async fn ensure_running(&self, repo_path: &Path) -> Result<(), ApiError>` — checks `child`; if none, spawns `{repo_path}/.venv/bin/python -m src.server --port 8765` with `cwd=repo_path`, polls `GET /healthz` for up to 10 seconds, stores child handle.
  - `async fn forward(&self, method: &str, path: &str, body: Option<Value>) -> Result<Value, ApiError>` — uses `reqwest::Client` to call `http://127.0.0.1:8765{path}`, maps reqwest errors to `ApiError`.
  - `pub fn shutdown(&self)` — kills child via stored handle.
- **`src-tauri/src/api/mod.rs`** — declare `pub mod sidecar;`.
- **`src-tauri/src/api/router.rs`** — add four match arms after the existing routes:
  ```rust
  ("POST", "/memos") | ("GET", "/memos") => {
      let repo_path = require_string(&body, "repoPath")?;
      let manager = state.sidecar();
      manager.ensure_running(Path::new(repo_path)).await?;
      manager.forward(&method, &path, body).await
  }
  ("GET", p) if p.starts_with("/memos/") && !p.ends_with("/events") => {
      // same as above for status + artifact endpoints
  }
  ```
  (SSE endpoint `/memos/{id}/events` deliberately *not* routed through Rust — JS opens EventSource directly.)
- **`src-tauri/src/lib.rs`** — register `SidecarManager` in `app.manage(...)`, add `.on_window_event` handler that calls `manager.shutdown()` on `WindowEvent::Destroyed`.

### Phase 2 — Frontend: transport SSE + flow stage + UI (~1.5 hours)

Files in `memopop-ai/apps/memopop-native/src/`:

- **`lib/transport/types.ts`** — extend `Transport`:
  ```ts
  export type JobEvent = { type: 'log' | 'status' | 'complete' | 'error'; ts: string; [k: string]: any };
  export interface Transport {
    request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T>;
    subscribeEvents(jobId: string, onEvent: (ev: JobEvent) => void): () => void;
  }
  ```
- **`lib/transport/local.ts`** — implement `subscribeEvents`:
  ```ts
  subscribeEvents(jobId, onEvent) {
    const es = new EventSource(`http://127.0.0.1:8765/memos/${jobId}/events`);
    es.onmessage = (e) => onEvent(JSON.parse(e.data));
    return () => es.close();
  }
  ```
- **`lib/stores/flow.svelte.ts`** — add stage:
  ```ts
  | { kind: 'running_job'; outline: Outline; jobId: string; status: 'queued'|'running'|'completed'|'failed'; events: JobEvent[]; outputDir?: string }
  ```
  Methods: `markRunning(outline, jobId)`, `appendEvent(event)`, `markFinished(status, outputDir)`.
- **`lib/components/DealCreationModal.svelte`** — replace `submit()` body with:
  ```ts
  const result = await getTransport().request<{job_id: string}>('POST', '/memos', {
    repoPath: settings.repoPath,
    company_name: companyName.trim() || companyUrl.trim(),
    company_url: companyUrl.trim() || undefined,
    investment_type: outline.outline_type === 'fund_commitment' ? 'fund' : 'direct',
    memo_mode: mode,
    firm: settings.activeFirm,
    deck_path: deckPath,
    outline_name: outline.id,
  });
  flow.markRunning(outline, result.job_id);
  ```
- **`lib/components/JobLogViewer.svelte`** (new) — modal-shaped component, takes `jobId` as prop:
  - On mount: `getTransport().subscribeEvents(jobId, flow.appendEvent)`.
  - Renders status pill (queued / running / completed / failed) at top.
  - Scrollable log pane below, auto-scrolls on new events, tail is reverse-chronological-friendly.
  - On `complete` event: shows "View artifacts →" CTA that opens the output directory in Finder via `tauri-plugin-shell`'s `open` (or just lists files via `GET /memos/{id}/artifacts`).
  - "Close" returns to gallery.
- **`routes/+page.svelte`** — add `{:else if flow.stage.kind === 'running_job'} <JobLogViewer ... />`.
- **`lib/components/JourneyBreadcrumbs.svelte`** — recognize `running_job` kind, set "Generate" step to active (currently this step lights up only for `ready_to_run`; needs extension).

### Phase 3 — End-to-end smoke test (~10 min, but 15–45 min wall time for a full run)

1. Boot the app: `cd memopop-ai/apps/memopop-native && bun run tauri dev`.
2. If repo path not yet anchored, pick `investment-memo-orchestrator/`.
3. Click an outline (Standard Direct Investment).
4. Click "Try this on a company →".
5. Enter a company name and URL (if no firm set, create one — `alpha-partners` already exists per the user).
6. Click Generate.
7. Watch: sidecar spawns (~2 sec), POST /memos returns job_id, SSE stream opens, log lines stream in.
8. **Partial validation**: confirm log streaming, status transitions, sidecar process visible in `ps` for 30–60 seconds, then close the modal (kills the run via close → idle → orphans the worker thread, which is fine for testing).
9. **Optional full validation**: let it run end-to-end, see "completed" status, click "View artifacts," verify files exist on disk.

## Critical files

**Orchestrator (`investment-memo-orchestrator/`):**
- `tests/test_server.py` (new) — Phase 0
- `pyproject.toml` — add pytest config

**Tauri Rust (`memopop-ai/apps/memopop-native/src-tauri/`):**
- `Cargo.toml` — add reqwest, tokio
- `src/api/sidecar.rs` (new) — process manager + forwarder
- `src/api/mod.rs` — declare new module
- `src/api/router.rs` — add `/memos*` match arms; reuse existing `require_string` and `ApiError`
- `src/lib.rs` — register state, wire shutdown hook

**Frontend (`memopop-ai/apps/memopop-native/src/`):**
- `lib/transport/types.ts` — add `subscribeEvents` to Transport interface
- `lib/transport/local.ts` — implement via `EventSource`
- `lib/stores/flow.svelte.ts` — add `running_job` stage and methods
- `lib/components/DealCreationModal.svelte` — real `POST /memos` submit
- `lib/components/JobLogViewer.svelte` (new) — live log + status panel
- `lib/components/JourneyBreadcrumbs.svelte` — recognize new stage
- `routes/+page.svelte` — render JobLogViewer for `running_job` stage

## Reused, not reinvented

- `ApiError` shape and `require_string` helper in `src-tauri/src/api/mod.rs` and `router.rs` — same patterns as `/firms`, `/outlines`, `/actions/create-firm`.
- `JobEventBus` 2000-event backlog (already in orchestrator's `events.py`) — late SSE subscribers automatically replay.
- `flow.svelte.ts` discriminated-union pattern — `running_job` slots in alongside existing stages.
- `Transport` singleton seam — `subscribeEvents` is the second method on the interface; everything else stays.

## Verification

**Phase 0 verification:**
```bash
cd investment-memo-orchestrator
.venv/bin/python -m pytest tests/ -v
# expect: 5 passed
```

**Phase 1 verification (Rust side compiles + dispatches):**
```bash
cd memopop-ai/apps/memopop-native
cargo check --manifest-path src-tauri/Cargo.toml
# manual: stub a sidecar manager test that calls forward() against a running server
```

**Phase 2 verification (frontend types + builds):**
```bash
cd memopop-ai/apps/memopop-native
bun run check          # svelte-check, types clean
bun run build          # vite build, no errors
```

**Phase 3 verification (the real one):**
- Sidecar process appears in `ps aux | grep 'src.server'` after first POST.
- `curl http://127.0.0.1:8765/healthz` returns 200 from outside the app.
- Log lines visible streaming in the JobLogViewer within 5 seconds of submit.
- Status pill transitions queued → running.
- App quit cleanly stops the sidecar process (no orphan in `ps` after exit).

## Out of scope (deliberately deferred)

- **PyInstaller-bundled sidecar.** Today's plan assumes the user has Python + venv set up in the orchestrator. Standalone-binary distribution is its own multi-day platform-by-platform effort.
- **Multiple concurrent jobs.** `max_workers=1` stays. Multi-job is a `JobRegistry` change later.
- **Persistent job history across restarts.** Process memory is the store; the artifact tree on disk is the durable record.
- **Auth, hosted deployment, multi-tenant.** Those are option 3 from the exploration doc, not this work.
- **Comprehensive test framework + CI.** A future effort. Phase 0's five tests are a seed, not a framework.

## Estimated effort

~4 hours total: 30 min Phase 0, 2 hours Phase 1, 1.5 hours Phase 2, 10 min smoke test (15–45 min if running a full memo). Most likely sequence to take longer: the Rust sidecar manager (`spawn` + `healthz` polling + lifecycle) is the part with the most platform-specific moving parts.

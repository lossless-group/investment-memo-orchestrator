---
title: "Transport Contract and API Conventions"
lede: "Defines the API shape the Tauri GUI talks to. Same contract today (local IPC dispatch) as tomorrow (remote HTTP server). Designed so the v1→v3 switch is a transport swap, not a rewrite."
date_authored_initial_draft: 2026-04-26
date_authored_current_draft: 2026-04-26
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-04-26
date_modified: 2026-04-26
tags: [GUI, Tauri, API, Architecture, Transport]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.7"
related:
  - context-v/Introducing-a-GUI-Native-Desktop-with-Tauri.md
  - context-v/GUI-Action-Catalog-Draft.md
---

# Transport Contract and API Conventions

## Why This Document Exists

The Tauri GUI calls into the Python orchestrator. **Today** that call is a local subprocess spawn through Tauri's shell plugin. **Eventually** it'll be an HTTP request to a Python server you host somewhere.

If the frontend talks to those two worlds via different code paths, you'll rewrite the UI when the time comes. If it talks to both via the **same interface** with two implementations, the switch is hours, not weeks.

This doc defines that interface — what it looks like, what guarantees it provides, and how each implementation satisfies it.

---

## Two Halves: Actions vs Queries

Every API call is one of two kinds:

| Kind        | What it does                                | Examples                                        | HTTP analog          |
| ----------- | ------------------------------------------- | ----------------------------------------------- | -------------------- |
| **Action**  | Triggers work. Returns a `jobId`. Streams logs/status. | Generate memo, improve section, export PDF      | `POST /actions/...`  |
| **Query**   | Reads state. Returns data synchronously.    | List firms, list deal versions, read a section  | `GET /...`           |

**Buttons trigger Actions. Sidebars and dropdowns are populated by Queries.** Don't conflate them; the streaming-vs-not distinction is what makes the abstraction work cleanly.

---

## Path Naming Conventions

REST-shaped, predictable, no clever shortcuts:

### Actions

```
POST /actions/{action_id}
```

Body is a JSON object whose shape comes from the action's parameter schema (see `gui_actions.json`). Returns:

```json
{ "jobId": "j_8f2a1c", "accepted": true }
```

If the request body fails validation, returns `400` with an error shape (see Errors below).

### Queries

Hierarchical, resource-shaped:

```
GET /firms                                                     # list firms
GET /firms/{firm}/deals                                        # list deals
GET /firms/{firm}/deals/{deal}                                 # deal config + summary
GET /firms/{firm}/deals/{deal}/versions                        # version history
GET /firms/{firm}/deals/{deal}/versions/{v}                    # version metadata + state
GET /firms/{firm}/deals/{deal}/versions/{v}/sections           # list of section files
GET /firms/{firm}/deals/{deal}/versions/{v}/sections/{name}    # section content
GET /firms/{firm}/deals/{deal}/versions/{v}/exports            # exported artifacts

GET /outlines                                                   # available outlines (default + custom)
GET /brands                                                     # available brand configs
GET /scorecards                                                 # available scorecard definitions

GET /jobs                                                       # active + recent jobs
GET /jobs/{jobId}                                               # job status
POST /jobs/{jobId}/cancel                                       # cancel a running job

GET /settings                                                   # app settings (active firm, repo path, etc.)
PUT /settings                                                   # update settings
```

### Legacy Companies (Pre-Firm-Scope)

For deals still living under `data/{Company}.json` instead of `io/{firm}/deals/`:

```
GET /companies                            # legacy flat list
GET /companies/{name}/versions
GET /companies/{name}/versions/{v}/...    # mirrors firm-scoped paths
```

The orchestrator already detects which mode a deal is in (`paths.resolve_deal_context()`); the API surfaces both.

### Path Rules

- **Lowercase + hyphens** for action IDs (`generate-memo`, not `generateMemo` or `generate_memo`). Yes, even though Python uses underscores — the API is the contract, not the implementation.
- **No verbs in query paths.** `GET /firms/{firm}/deals` not `GET /firms/{firm}/listDeals`.
- **Plural for collections, singular for items.** `/deals` and `/deals/{deal}`.
- **No trailing slash.** Ever.

---

## Request and Response Shapes

### Action Request

```typescript
// POST /actions/improve-section
{
  "firm": "hypernova",
  "deal": "Avalanche",
  "section": "Team",
  "version": "v0.0.3"   // optional; defaults to latest
}
```

### Action Response

```typescript
{
  "jobId": "j_8f2a1c",
  "accepted": true
}
```

That's it. The work happens asynchronously; logs come over the stream.

### Query Response

Plain JSON. No envelope. Examples:

```typescript
// GET /firms
{ "firms": ["hypernova", "humain", "alpha-partners"] }

// GET /firms/hypernova/deals/avalanche
{
  "firm": "hypernova",
  "deal": "Avalanche",
  "type": "direct",
  "mode": "consider",
  "outline": "hypernova-direct",
  "stage": "Series A",
  "deck": "deck.pdf",
  "trademark_light": "...",
  "trademark_dark": "...",
  "latestVersion": "v0.0.3"
}
```

If a resource doesn't exist, `404` with the error shape.

### Job Status Shape

```typescript
// GET /jobs/{jobId}
{
  "jobId": "j_8f2a1c",
  "action": "improve-section",
  "status": "running",       // queued | running | succeeded | failed | cancelled
  "startedAt": "2026-04-26T14:32:11Z",
  "finishedAt": null,
  "exitCode": null,
  "params": { ... },          // the original request body
  "artifacts": []             // populated as files are produced
}
```

---

## Streaming: Job Events

Long-running actions (memo generation, section improvement) need live output. The transport exposes a stream of events keyed by `jobId`:

```typescript
type JobEvent =
  | { type: 'log';    jobId: string; level: 'info' | 'warn' | 'error'; line: string; ts: number }
  | { type: 'status'; jobId: string; status: 'running' | 'succeeded' | 'failed' | 'cancelled'; exitCode?: number }
  | { type: 'artifact'; jobId: string; path: string; kind: 'section' | 'export' | 'state' | 'other' };
```

- **`log`** events carry one line at a time; the UI appends them to the log pane.
- **`status`** events fire on lifecycle transitions; the UI updates the run indicator.
- **`artifact`** events fire when a new output file appears (e.g., a section is saved, a PDF is written); the UI can offer "open" buttons in real time.

**Ordering guarantee**: events for a given `jobId` arrive in the order the server emitted them. No ordering guarantee across different `jobId`s.

---

## The Transport Interface

This is the abstraction the frontend codes against:

```typescript
// src/lib/transport.ts

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';

export interface ApiError {
  status: number;
  code: string;       // machine-readable: "validation_failed", "not_found", "internal_error"
  message: string;    // human-readable
  details?: unknown;
}

export interface Transport {
  /**
   * Make a single request. Resolves with the parsed JSON response.
   * Rejects with ApiError on non-2xx responses or transport-level failures.
   */
  request<T = unknown>(
    method: HttpMethod,
    path: string,
    body?: unknown
  ): Promise<T>;

  /**
   * Subscribe to events for a job. Returns an unsubscribe function.
   * The handler receives every event for that jobId until unsubscribed
   * or until the job emits a terminal status (succeeded/failed/cancelled).
   */
  stream(
    jobId: string,
    handler: (event: JobEvent) => void
  ): () => void;
}
```

**Frontend code uses only this interface.** It never imports `@tauri-apps/plugin-shell` or `fetch` directly.

A single factory picks the implementation:

```typescript
// src/lib/transport/index.ts
import { LocalTransport } from './local';
import { HttpTransport } from './http';
import { settings } from '../settings';

export function makeTransport(): Transport {
  return settings.serverUrl
    ? new HttpTransport(settings.serverUrl, settings.authToken)
    : new LocalTransport();
}
```

---

## LocalTransport (v1 — Today)

Backed by Tauri IPC. There is **one** Tauri command, `api_dispatch`, that routes by `(method, path)`:

```typescript
// src/lib/transport/local.ts
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

export class LocalTransport implements Transport {
  async request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    return await invoke<T>('api_dispatch', { method, path, body });
  }

  stream(jobId: string, handler: (event: JobEvent) => void): () => void {
    const promise = listen<JobEvent>(`job:${jobId}`, (e) => handler(e.payload));
    return () => { promise.then(unsub => unsub()); };
  }
}
```

Rust side (sketch — `src-tauri/src/api/mod.rs`):

```rust
#[tauri::command]
pub async fn api_dispatch(
    app: tauri::AppHandle,
    method: String,
    path: String,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, ApiError> {
    match (method.as_str(), path.as_str()) {
        // Actions: spawn a process, return jobId
        ("POST", p) if p.starts_with("/actions/") => {
            let action_id = &p["/actions/".len()..];
            actions::spawn(&app, action_id, body).await
        }

        // Queries: read state, return JSON
        ("GET", "/firms")            => queries::list_firms().await,
        ("GET", p) if p.starts_with("/firms/") => queries::firms_route(p).await,
        ("GET", "/outlines")         => queries::list_outlines().await,
        ("GET", "/brands")           => queries::list_brands().await,
        ("GET", "/scorecards")       => queries::list_scorecards().await,
        ("GET", "/jobs")             => queries::list_jobs().await,
        ("GET", p) if p.starts_with("/jobs/") => queries::jobs_route(p).await,

        // Job control
        ("POST", p) if p.ends_with("/cancel") => actions::cancel(p).await,

        _ => Err(ApiError::not_found(&path)),
    }
}
```

Process spawning emits Tauri events:

```rust
// In actions::spawn, after kicking off the subprocess:
app.emit(&format!("job:{}", job_id), JobEvent::Log {
    job_id: job_id.clone(),
    level: "info".into(),
    line: line_from_stdout,
    ts: now_unix_ms(),
})?;
```

**Why a single dispatcher Rust command instead of one command per route?**

- Frontend code is identical to the HTTP world (one `request()` call, path-shaped).
- Adding a new route only touches Rust dispatcher + Python — no new Tauri command registration ceremony.
- The dispatcher is the natural seam where you'd later swap to actual HTTP if you wanted to host the server externally.

---

## HttpTransport (v3 — When You're Ready)

Same interface, different innards:

```typescript
// src/lib/transport/http.ts
export class HttpTransport implements Transport {
  constructor(private baseUrl: string, private authToken?: string) {}

  async request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(this.authToken ? { 'Authorization': `Bearer ${this.authToken}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: res.statusText }));
      throw { status: res.status, ...err } as ApiError;
    }

    return res.json();
  }

  stream(jobId: string, handler: (event: JobEvent) => void): () => void {
    const es = new EventSource(`${this.baseUrl}/jobs/${jobId}/events`);
    es.onmessage = (msg) => handler(JSON.parse(msg.data));
    return () => es.close();
  }
}
```

The Python server (FastAPI is the natural fit) implements the same paths:

```python
@app.post("/actions/improve-section")
async def improve_section(req: ImproveSectionRequest) -> JobAck:
    job_id = job_manager.create("improve-section", req.dict())
    asyncio.create_task(run_improve_section(job_id, req))
    return JobAck(jobId=job_id, accepted=True)

@app.get("/jobs/{job_id}/events")
async def stream_events(job_id: str):
    return StreamingResponse(
        job_manager.event_stream(job_id),
        media_type="text/event-stream",
    )
```

The orchestrator's actual logic — `improve_section()`, `generate_memo()`, etc. — doesn't change. Only the entry shell does.

---

## Errors

One shape, used by both transports:

```typescript
interface ApiError {
  status: number;       // HTTP status (also used by LocalTransport for parity)
  code: string;         // "validation_failed" | "not_found" | "conflict" | "internal_error" | ...
  message: string;
  details?: unknown;    // structured info (e.g., per-field validation errors)
}
```

Status codes follow HTTP conventions even in local mode:
- `400` — invalid request body
- `404` — unknown route or missing resource
- `409` — conflict (e.g., job already running on that deal in single-task mode)
- `500` — internal error (Python crashed, etc.)

---

## Migration Path: What Changes When You Flip the Switch

When you stand up the Python server and switch the `transport` factory:

| Component                       | Changes? | Notes                                              |
| ------------------------------- | -------- | -------------------------------------------------- |
| Frontend Svelte components      | No       | Use `Transport` interface only                     |
| Action catalog (`gui_actions.json`) | No   | Same actions, same parameters                      |
| `LocalTransport`                | No       | Stays available as offline / dev-mode fallback     |
| `HttpTransport`                 | New      | ~80 lines of code. Already designed.               |
| Settings UI                     | Tiny     | Add "Server URL" + "Auth token" fields             |
| Python orchestrator             | No       | Same functions. New FastAPI shim wraps them.       |
| FastAPI server                  | New      | The real work — endpoint per action, job manager, SSE |
| Auth                            | New      | Out of scope here; bearer token is the placeholder |

Realistic estimate: **1–2 days of frontend work** + however long the FastAPI server itself takes.

---

## Things Deliberately Deferred

- **Auth.** Local mode has no auth. HTTP mode uses bearer tokens; OAuth/SSO is later.
- **Multi-window job management.** v1 assumes one window; if a job is running and the user opens a second window, behavior is undefined. Fix when needed.
- **API versioning.** When the contract breaks compatibly, prefix paths with `/v2/`. Not before.
- **Pagination.** Queries return full lists for now; add `?limit=&cursor=` when collections grow past ~100.
- **Webhooks / push from server.** SSE is enough for v3.

---

## How to Use This Doc

When designing a new feature:

1. Decide: **Action or Query?** Streaming required?
2. Pick a path that fits the conventions above.
3. Define the request body and response shape (TypeScript types).
4. Add it to `gui_actions.json` (if action) or to the query catalog.
5. Implement once on `LocalTransport` (Rust dispatcher route + Python entry).
6. When v3 lands, the same path implementation moves to FastAPI; frontend is unchanged.

If you're tempted to bypass the transport interface — to call `invoke()` or `fetch()` directly from a component — stop. That's how the abstraction rots.

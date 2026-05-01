---
title: "Introducing a GUI Native Desktop with Tauri"
lede: "Specification for a Tauri control panel app that wraps the existing memo orchestration CLIs and agents. Mac-first build, written to keep cross-platform porting cheap."
date_authored_initial_draft: 2025-11-28
date_authored_current_draft: 2026-04-26
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.4
usage_index: 1
publish: false
category: Specification
date_created: 2025-11-28
date_modified: 2026-04-26
tags: [GUI, Tauri, Svelte, macOS, Desktop-App, Control-Panel]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.7"
---

# Introducing a GUI Native Desktop with Tauri

## Goal

Create a **cross-platform desktop application** that acts as a **control panel** over the existing memo orchestration CLIs and agents, optimized for:

- People who are **terminal-averse** but work on a MacBook Pro (primary), with Windows/Linux ports possible later.
- Reducing cognitive load around "which command/agent does what and with which flags".
- Keeping the **brains** in the existing Python orchestrator, while the GUI focuses on: discovery, parameter collection, execution, and live logs.
- A mind toward eventual mobile and web variants (Tauri 2 supports mobile targets; the Svelte frontend is reusable for a hosted web build).

This document assumes **familiarity with Svelte/HTML/CSS** and **no prior experience** building a Tauri app. Rust knowledge is helpful but not required — the Rust side stays small and recipe-driven.

---

## High-Level Architecture

A Tauri app is a **Rust shell** hosting a **web frontend** in the OS's native webview (WKWebView on macOS, WebView2 on Windows, WebKitGTK on Linux). There is no embedded Chromium — bundles are small (a few MB) and the system handles updates to the web engine.

Three layers, from outside in:

1. **Frontend (Svelte + Vite)** — the UI: sidebar of actions, parameter form, log pane. Pure web tech. Talks to Rust via `invoke()` calls and listens for `event` streams.
2. **Rust backend (`src-tauri/`)** — exposes a small set of `#[tauri::command]` functions: load action catalog, spawn a child process, stream its stdout/stderr back to the frontend as events. Uses Tauri's [shell plugin](https://v2.tauri.app/plugin/shell/) for process spawning so we don't write platform-specific code.
3. **Python orchestrator (existing repo)** — unchanged. The GUI invokes the same CLI entry points (e.g., `python -m src.main`, `python improve-section.py`) the user runs today.

The app:

- Reads a **declarative catalog of actions** from the repo (`config/gui_actions.json`).
- Renders a **sidebar** of actions grouped by category.
- Renders a **form** for the selected action's parameters.
- On "Run", invokes a Rust command that spawns the corresponding **CLI process**.
- Streams **stdout/stderr** into a log view via Tauri events.

All memo/agent logic stays in the existing orchestrator. The GUI is intentionally thin.

### Cross-platform discipline (Mac-first, port-friendly)

To keep porting cheap later:

- **No direct system calls.** Use Tauri plugins (`shell`, `dialog`, `fs`, `store`) instead of platform-specific Rust crates.
- **Path handling** through `std::path::PathBuf` and `tauri::path::PathResolver` — no hardcoded `/Users/...` or `~/Library/...`.
- **Config and persisted state** via `@tauri-apps/plugin-store` (writes to the OS-correct app data dir on each platform).
- **No AppleScript, no `NSOpenPanel`, no `defaults` calls.** All file pickers go through the dialog plugin.

If you find yourself reaching for a Mac-specific API, stop and check whether a Tauri plugin covers it — it almost always does.

---

## v0 Scope (Good Enough to Be Useful)

- **Platforms**: macOS only for v0 (you're the user). Code written to compile cross-platform.
- **Features**:
  - Sidebar list of **3–5 high-leverage actions**:
    - Generate new memo from a brief.
    - Refocus / repair a specific section. Sub-features:
      - Refocus
      - Reduce redundancy
      - Fact check
      - Align to content preferences
      - Gather more research (Perplexity / browserless search)
    - Export branded HTML/PDF.
  - For each action:
    - Title and 1–2 line description.
    - Minimal parameters (paths, IDs, toggles) defined in a schema file.
    - `Run` button with icon.
    - Action/command search bar (VS Code-style command palette would be ideal; v0 can ship plain text filter).
  - Rich user and org settings:
    - Preferred outline for memo content.
    - Grab a public outline.
    - Alternate outlines.
  - Org admin dashboard (stub for v0 — single-user store; design the schema so it can grow).
  - **Log pane** showing live process output and final status.
  - **Native filesystem "Vault"** for storing memos and related files according to current application state.
- **Out of scope for v0**:
  - Job history, retry, queues.
  - Multi-user / auth.
  - Bundled Python (see Distribution Strategy — v0 assumes `uv sync` worked).
  - Code signing / notarization.

The goal is a **daily-driver helper**, not a boxed product.

---

## Distribution Strategy (Three Tiers)

This is the most important strategic decision because it determines who can use the app.

### v0 — "Developer mode" (you, now)

- User clones the repo, runs `uv sync` per the existing README.
- Tauri app launches Python via `uv run python -m src.main ...` through the shell plugin.
- The app needs to know the repo path (set on first launch via folder picker, persisted via `plugin-store`).
- **Pros**: Ships in days. No bundling complexity. Python deps update naturally with `uv sync`.
- **Cons**: User must have `uv` installed and run two commands first. Useless for non-technical VCs.

### v0.5 — "One-command install"

- A shell script (`curl https://yourdomain/install.sh | sh`) that:
  1. Installs `uv` if missing.
  2. Clones or updates the orchestrator repo to a known location (e.g., `~/.memo-orchestrator/`).
  3. Runs `uv sync`.
  4. Downloads and installs the Tauri `.app`.
- This is the `npx create-astro@latest` parallel you mentioned. Realistic mid-step.
- **Pros**: Single command, no manual git knowledge required.
- **Cons**: Still terminal. VCs who don't know what a terminal is can't use it.

### v1 — True one-click install

- Use **PyInstaller** (or **Briefcase**) to bundle the Python orchestrator + all deps into a single binary.
- Ship that binary as a **Tauri sidecar** (`src-tauri/binaries/orchestrator-aarch64-apple-darwin`).
- User downloads `.dmg`, drags to Applications, launches. No Python install. No terminal.
- **Pros**: Real consumer experience.
- **Cons**:
  - PyInstaller-bundling LangChain is non-trivial (lots of dynamic imports — needs `--collect-all` flags for `langchain`, `langgraph`, `anthropic`, etc.).
  - Mac requires **code signing** (Apple Developer account, $99/yr) and **notarization** to avoid Gatekeeper warnings.
  - **API keys can't be bundled.** First-launch flow must collect `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `PERPLEXITY_API_KEY` and store them via OS keychain (`@tauri-apps/plugin-stronghold` or platform-native keyring).
  - Bundle size jumps to 200MB+ once Python + LangChain are inside.
- **When to do it**: Only if there's real demand. Don't pre-build for users who don't exist.

**v0 ships the developer-mode path.** v0.5 and v1 are tracked as upgrade paths, not blockers.

---

## Step 1: Define the Action Catalog in the Repo

Before touching Tauri, define a machine-readable list of actions the GUI can present. This is framework-agnostic and stays useful even if you swap UIs later.

Create `config/gui_actions.json`. For each action:

- `id`: stable identifier (e.g., `refocus_section`).
- `display_name`: human-readable label.
- `description`: short paragraph.
- `category`: for sidebar grouping (e.g., `generate`, `improve`, `export`).
- `command`: the CLI entry. Two forms:
  - String: `"uv run python -m src.main"` (v0 dev mode).
  - Object: `{ "sidecar": "orchestrator", "subcommand": "generate" }` (v1 sidecar mode).
- `working_directory`: relative to a configured repo root, if needed.
- `parameters`: list of:
  - `name`
  - `type` (`string`, `path`, `enum`, `bool`, `int`)
  - `label`
  - `help_text`
  - `required` / optional
  - `default` (optional)
  - `enum_values` (when type is `enum`)
  - `flag` (CLI flag form, e.g., `--firm` — if absent, value is positional)

Keeping the catalog declarative means new agents/CLIs become available to the GUI by editing the config + Python, never the Tauri code.

---

## Step 2: Scaffold the Tauri + Svelte Project

Tauri 2 has a project generator. From your projects directory:

```bash
bun create tauri-app
```

Answer the prompts:

- Project name: `memo-control-panel`
- Identifier: `com.yourname.memocontrolpanel` (used for app bundle ID)
- Frontend language: **TypeScript**
- UI template: **Svelte**
- UI flavor: **TypeScript**

This produces:

```
memo-control-panel/
├── src/                    # Svelte frontend
│   ├── routes/             # (or App.svelte for vanilla Svelte)
│   ├── lib/
│   └── main.ts
├── src-tauri/              # Rust backend
│   ├── src/
│   │   ├── main.rs
│   │   └── lib.rs
│   ├── Cargo.toml
│   ├── tauri.conf.json     # window size, permissions, bundle config
│   └── capabilities/       # permissions per window
└── package.json
```

Then:

```bash
cd memo-control-panel
bun install
bun run tauri dev
```

A native window opens with the Svelte default page. Confirm it works before going further.

---

## Step 3: Add the Plugins You'll Need

Tauri 2 is plugin-based — add only what you use. For this app:

```bash
# Spawn child processes (Python CLI)
bun run tauri add shell

# File pickers (browse for repo root, output paths)
bun run tauri add dialog

# Persistent settings (repo path, last-used parameters)
bun run tauri add store

# Filesystem access (read action catalog, output dirs)
bun run tauri add fs
```

Each plugin adds:
- A Rust crate to `src-tauri/Cargo.toml`.
- A JS package to `package.json`.
- A capability entry in `src-tauri/capabilities/default.json` (permissions are explicit in Tauri 2 — you opt in to `shell:allow-execute`, `dialog:allow-open`, etc.).

Edit `capabilities/default.json` to allow what you need. Keep this list **minimal** — every permission you grant is attack surface.

---

## Step 4: Model the Action Catalog (Frontend Types)

Define TypeScript types in `src/lib/actions.ts` mirroring the JSON schema:

```typescript
export type ParameterType = 'string' | 'path' | 'enum' | 'bool' | 'int';

export interface GuiParameter {
  name: string;
  type: ParameterType;
  label: string;
  help_text?: string;
  required: boolean;
  default?: string | boolean | number;
  enum_values?: string[];
  flag?: string;
}

export interface GuiAction {
  id: string;
  display_name: string;
  description: string;
  category: string;
  command: string;
  working_directory?: string;
  parameters: GuiParameter[];
}

export interface GuiActionCatalog {
  actions: GuiAction[];
}
```

At app startup, load `gui_actions.json` from the configured repo root via the `fs` plugin and parse it into the type above. For v0, hardcode the path or prompt the user once via the `dialog` plugin and persist it via `store`.

You don't need matching Rust structs unless Rust needs to introspect the catalog (it doesn't — Rust just receives a fully-built command string from the frontend).

---

## Step 5: Build the Basic Layout

Three-region layout, all in Svelte components:

```
┌──────────┬─────────────────────────────┐
│ Sidebar  │ Detail (parameter form)     │
│          │                             │
│ - Action │   [form fields...]          │
│ - Action │                             │
│ - Action │   [Run button]              │
│          ├─────────────────────────────┤
│          │ Log pane (live output)      │
└──────────┴─────────────────────────────┘
```

- **`<Sidebar>`** — receives `actions: GuiAction[]`, emits `select` event with the chosen action.
- **`<ParameterForm>`** — receives the selected `GuiAction`, renders one control per parameter, emits `submit` with the collected values.
- **`<LogPane>`** — subscribes to a Svelte store of log lines.

Keep it data-driven from the action catalog. No per-action hardcoded UI.

For styling: vanilla CSS or Tailwind both work. Tauri has no opinion. Use what you're fast in.

---

## Step 6: Wire Up Process Execution

This is the heart of the app. The flow:

1. User clicks `Run`.
2. Frontend builds an argument array from the form values + the action's `command`.
3. Frontend calls `invoke('run_action', { ... })` — a Rust command.
4. Rust spawns the child process via the shell plugin and streams stdout/stderr back as Tauri events.
5. Frontend listens for those events, appends each line to the log store.

### Frontend side

```typescript
import { Command } from '@tauri-apps/plugin-shell';
import { listen } from '@tauri-apps/api/event';

// Build the command from form values
const command = Command.create('uv', [
  'run', 'python', '-m', 'src.main',
  companyName,
  '--firm', firm,
  '--mode', mode,
]);

command.stdout.on('data', (line) => logStore.append(line));
command.stderr.on('data', (line) => logStore.append(line, 'error'));
command.on('close', ({ code }) => {
  status.set(code === 0 ? 'succeeded' : 'failed');
});

const child = await command.spawn();
// Save child to allow terminate() if user clicks Stop
```

The shell plugin's `Command.create()` is allow-listed in `capabilities/default.json` — only commands you explicitly permit can run. For v0, allow `uv` and `python`.

### Rust side

For most v0 needs you don't write any Rust — the `@tauri-apps/plugin-shell` JS API is sufficient. Only drop into Rust when you need:

- Streaming log lines from a sidecar binary (v1 PyInstaller path).
- Custom logic the frontend shouldn't see (API key handling, keychain access).

A Rust command looks like:

```rust
#[tauri::command]
async fn run_action(
    app: tauri::AppHandle,
    args: Vec<String>,
) -> Result<String, String> {
    // ...
}
```

Register it in `src-tauri/src/lib.rs` via `.invoke_handler(tauri::generate_handler![run_action])`.

### Cancellation

Keep a reference to the spawned child. Frontend `Stop` button calls `child.kill()`. v0 supports one running task at a time.

---

## Step 7: Parameter Forms From Schema

Render controls dynamically from each `GuiParameter`:

| Parameter type | Control                                       |
| -------------- | --------------------------------------------- |
| `string`       | `<input type="text">`                         |
| `path`         | `<input>` + "Browse" button → `dialog.open()` |
| `bool`         | `<input type="checkbox">`                     |
| `enum`         | `<select>`                                    |
| `int`          | `<input type="number">`                       |

Use a single `<ParameterControl>` Svelte component that switches on `parameter.type`. Bind values to a reactive object keyed by parameter name.

On `Run`:

1. Validate required fields (show inline error if missing).
2. Walk the parameters, build CLI args:
   - If `flag` is set: push `[flag, value]`.
   - Else: push `[value]` as positional.
   - Booleans: push `flag` only if true (or `--no-flag` if false — depends on the CLI's convention).

---

## Step 8: Repo Root and Configuration

The Tauri app needs to know where the orchestrator lives.

v0 implementation:

- **First-launch flow**: if no repo path is stored, show a dialog prompting the user to select the orchestrator directory. Use `dialog.open({ directory: true })`.
- **Persist** via `@tauri-apps/plugin-store` — writes to the OS-correct app data dir (`~/Library/Application Support/com.yourname.memocontrolpanel/` on Mac).
- **Settings screen**: a simple page exposing the path with an "Edit" button. Same dialog.

All paths (`gui_actions.json`, working directories, output) are resolved relative to that root.

---

## Step 9: Polishing v0

Once the basics work, small QoL improvements:

- **Persist last parameter values** per action. (`plugin-store`, keyed by action ID.)
- **Inline validation** for required params.
- **Status indicators**:
  - Idle (none).
  - Running (spinner).
  - Success (green check).
  - Error (red icon + last stderr line).
- **Open output folder** button after a run completes (use `shell.open()` to reveal in Finder).
- **Clear log** button.

Resist the urge to over-design. This is an internal companion, not a boxed product.

---

## Possible v1+ Enhancements

If v0 lands well:

- **PyInstaller sidecar** + signed/notarized .dmg (see Distribution Strategy).
- **Keychain integration** for API keys via `@tauri-apps/plugin-stronghold`.
- **Job history** with timestamps, parameters, outcomes (small SQLite via `plugin-sql`).
- **Queue** for long-running tasks.
- **Structured log display** — collapse sections, link to artifact files.
- **Auto-update** via Tauri's updater plugin.
- **Windows + Linux ports** — `bun run tauri build` already targets all three; main work is testing and platform-specific bundle config.
- **Mobile companion** — Tauri 2 supports iOS/Android targets; the Svelte UI is reusable.

---

## Key Files Reference

```
memo-control-panel/
├── src/
│   ├── App.svelte                  # Root component, layout
│   ├── lib/
│   │   ├── actions.ts              # GuiAction, GuiParameter types + loader
│   │   ├── runner.ts               # spawn + log stream wrapper
│   │   ├── store.ts                # Svelte stores (logs, status, settings)
│   │   └── components/
│   │       ├── Sidebar.svelte
│   │       ├── ParameterForm.svelte
│   │       ├── ParameterControl.svelte
│   │       └── LogPane.svelte
│   └── main.ts
├── src-tauri/
│   ├── src/lib.rs                  # invoke_handler registration (mostly empty for v0)
│   ├── tauri.conf.json             # window size, bundle ID, plugins
│   ├── capabilities/default.json   # permission allowlist
│   └── Cargo.toml
└── ../config/gui_actions.json      # in the orchestrator repo, loaded at runtime
```

---

## Risks and Open Questions

- **PyInstaller + LangChain compatibility (v1)**: LangChain uses dynamic imports heavily; PyInstaller often misses some. Plan to spike this before committing to v1 — a single failed import can break the whole bundle.
- **API key UX (v1)**: First-launch onboarding is a real design problem. Don't underestimate it.
- **Action catalog evolution**: As you add agents, the JSON schema may need versioning. Add a `schema_version` field from day one.
- **Long-running processes**: Memo generation can take 10+ minutes. Make sure the log pane handles thousands of lines without slowing the UI (virtualize if needed; v0 can defer).
- **Concurrent runs**: v0 says one at a time. If you add queuing later, decide whether logs are per-run or merged.

# Introducing a GUI Native Desktop with Swift

## Goal

Create a **macOS SwiftUI app** that acts as a **control panel** over the existing memo orchestration CLIs and agents, optimized for:

- People who are **terminal‑averse** but work on a MacBook Pro.
- Reducing cognitive load around "which command/agent does what and with which flags".
- Keeping the **brains** in the existing Python/Rust tools, while the GUI focuses on: discovery, parameter collection, and execution + logs.

This document assumes **no prior experience** building a macOS app with SwiftUI.

---

## High‑Level Architecture

- **SwiftUI macOS app** (single target in Xcode).
- The app:
  - Reads a **declarative catalog of actions** from the repo (JSON/TOML/YAML).
  - Renders a **sidebar** of actions grouped by category.
  - Renders a **form** for the selected action's parameters.
  - On "Run", spawns the corresponding **CLI process** via macOS `Process` API.
  - Streams **stdout/stderr** into a log view.
- All memo/agent logic remains in the existing orchestrator; the SwiftUI app is intentionally thin.

---

## v0 Scope (Good Enough to Be Useful)

- **Platforms**: macOS only (SwiftUI on Mac; no iOS/iPadOS).
- **Features**:
  - Sidebar list of **3–5 high‑leverage actions**, e.g.:
    - Generate new memo from a brief.
    - Refocus/repair a specific section.
    - Export branded HTML/PDF.
  - For each action:
    - Title and 1–2 line description.
    - Minimal parameters (paths, IDs, toggles) defined in a schema file.
    - `Run` button.
  - **Log pane** showing live process output and completion status.
- **Out of scope for v0**:
  - Job history, retry, queues.
  - Multi‑user / auth.
  - Fancy window management or deep macOS integrations.

The goal is a **daily‑driver helper**, not a fully productized app.

---

## Step 1: Define the Action Catalog in the Repo

Before touching Swift, define a machine‑readable list of actions the GUI can present.

- Create a file like `config/gui_actions.json` (or `.toml`, `.yaml`).
- For each action, include fields like:
  - `id`: stable identifier (e.g. `refocus_section`).
  - `display_name`: human‑readable label.
  - `description`: short paragraph.
  - `command`: the CLI entry (e.g. `python -m cli.refocus_section`).
  - `working_directory`: relative path from repo root, if needed.
  - `parameters`: list of
    - name
    - type (`string`, `path`, `enum`, `bool`, `int`)
    - label
    - help_text
    - required / optional
    - default (optional)

This catalog:

- Keeps the GUI **decoupled** from implementation details.
- Lets you change workflows by editing the config + CLIs, not the Swift code.

---

## Step 2: Create a New SwiftUI macOS Project

1. Open **Xcode**.
2. Choose **File → New → Project…**.
3. Select **App** under macOS, and choose **SwiftUI** as the interface.
4. Name it something like `MemoControlPanel`.
5. Choose **Swift** as the language.

This gives you:

- An `@main` `App` struct.
- A root `ContentView` with SwiftUI boilerplate.

For now, you can run it and confirm you see the default "Hello, world" window.

---

## Step 3: Model the Action Catalog in Swift

Define Swift structs that mirror your `gui_actions` schema.

- Example types (conceptually):
  - `GuiActionCatalog` with `[GuiAction]`.
  - `GuiAction` with id, displayName, description, command, parameters.
  - `GuiParameter` with name, type, label, required, etc.

Then:

- Load `gui_actions.json` at app startup.
- For v0, hard‑code the path to your repo root (or prompt the user once and persist it).

This gives you a strongly typed model the UI can render.

---

## Step 4: Build the Basic SwiftUI Layout

Aim for a **three‑region layout**:

1. **Sidebar** (left): list of actions grouped by category.
2. **Main panel** (center): details and parameter form for the selected action.
3. **Log panel** (bottom or right): text view showing process output.

In SwiftUI:

- Use `NavigationSplitView` (or `NavigationView` with a sidebar style) for a classic macOS layout.
- The sidebar lists `GuiAction`s with `List`.
- The detail area uses a `Form` or `VStack` with dynamic controls based on `GuiParameter.type`.
- The log area is a `ScrollView` + `Text` for now.

The key is to keep all controls **data‑driven** from the action catalog.

---

## Step 5: Wire Up Process Execution

Use the macOS `Process` API to run your CLIs:

- Build the **argument list** from:
  - `command` in the catalog.
  - Parameter values from the SwiftUI form.
- Set `Process.currentDirectoryURL` to the repo root or the configured working directory.
- Capture:
  - `standardOutput` via `Pipe`.
  - `standardError` via `Pipe`.

As the process runs:

- Read bytes from the pipes on a background queue.
- Append decoded lines to a `@Published` log string.
- Update status (`running`, `succeeded`, `failed`), reflected in the UI.

For v0:

- One running task at a time is fine.
- A simple "Stop" can call `process.terminate()`.

---

## Step 6: Parameter Forms From Schema

To avoid hand‑coding a form per action:

- Iterate over each `GuiParameter` for the selected action.
- For each parameter type, render a control:
  - `string` → `TextField`.
  - `path` → `TextField` with a "Browse" button (hook up to `NSOpenPanel` later).
  - `bool` → `Toggle`.
  - `enum` → `Picker`.

Bind each control to state inside a `ViewModel` for that action.

On `Run`:

- Validate required fields.
- Construct CLI arguments using a simple mapping function from parameter values.

---

## Step 7: Repo Root and Configuration

The SwiftUI app needs to know where the **repo lives** on disk.

v0 options:

- A simple **Preferences** screen with a single field:
  - "Path to memo orchestrator repo".
- On first launch, if unset:
  - Prompt with `NSOpenPanel` limited to directories.
  - Persist the selection in `UserDefaults` (or a small config file).

All paths (like `gui_actions.json` and CLI working directories) are then relative to that root.

---

## Step 8: Polishing v0

Once the basics work, add small quality‑of‑life improvements:

- **Persist last parameter values** for each action per machine (e.g., last memo path).
- Show **inline validation messages** if required parameters are missing.
- Add **visual status indicators**:
  - Running (spinner).
  - Success (green check).
  - Error (red icon + last error line from stderr).

Still keep the scope small—this is an internal companion, not a boxed product.

---

## Possible v1+ Enhancements

If v0 lands well, future steps could include:

- **Job history** with timestamps and outcomes.
- A simple **queue** for long‑running tasks.
- Better file pickers and templates for common input paths.
- More structured log display (sections, collapsible groups, links back to artifacts).
- Optional **integration with a small local HTTP API** instead of spawning CLIs directly, if that simplifies orchestration.

But v0 should already significantly reduce friction by making the memo tools 
more discoverable and less dependent on remembering exact command lines.

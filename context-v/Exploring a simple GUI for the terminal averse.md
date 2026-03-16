---
title: "Exploring a Simple GUI for the Terminal Averse"
lede: "Evaluation of GUI stack options for building a lightweight control panel over the existing memo orchestration CLIs and agents."
date_authored_initial_draft: 2025-11-28
date_authored_current_draft: 2025-11-28
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2025-11-28
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2025-11-28
date_modified: 2025-11-28
tags: [GUI, Desktop-App, UX, CLI, Control-Panel]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.6"
---

# Exploring a simple GUI for the terminal‑averse

## What problem are we actually solving?

This system now has **too many CLIs and agents** for anyone (including me) to remember:

- **Many entrypoints** (e.g. `cli/refocus_section.py`, `cli/export_branded.py`, etc.).
- Each has its own **arguments, modes, and gotchas**.
- The mental model is scattered across: code, changelogs, doc files, and my head.

What’s actually needed:

- **A small, opinionated control panel** over the existing tools.
- Discoverable list of **agents / commands** with:
  - human‑readable names
  - short, high‑signal descriptions
- Simple **forms** for the required inputs (paths, memo IDs, sections, profile selection, etc.).
- **Run / Stop** controls.
- **Status + logs view** to see what the tool is doing.

This is conceptually 1–3 main screens, not a whole new product.

The hard part is not the memo logic; it’s choosing a GUI stack that isn’t a bloated science project.

---

## High‑level options for a native desktop GUI

Constraints:

- Avoid **Electron / Flutter / webview bloat**.
- Prefer **native‑ish**, single‑binary or simple install.
- Keep most **orchestration logic in the existing CLIs / Python**, not re‑implement everything in the UI layer.

### Option A: Rust + `wgpu` directly

This is the tempting “do it right” path that is actually a trap here.

`wgpu` is a **low‑level GPU abstraction**. Using it directly means:

- You are effectively building your own **UI toolkit**:
  - Layout engine (rows, columns, padding, scrolling).
  - Text rendering (fonts, shaping, cursor, selection).
  - Widgets (buttons, lists, scroll views, text inputs, dropdowns).
  - Input handling (mouse, keyboard focus, shortcuts).
- You also have to deal with:
  - Windowing and event loop integration.
  - Accessibility (if you care at all).
  - DPI / scaling / platform nuances.

This is **more complicated than the product logic itself**. It’s “build a small game engine / UI library” work.

For the problem “give me a panel with buttons that run CLIs and show logs”, **raw `wgpu` is unreasonably hard and overkill**.

### Option B: Rust + a higher‑level GUI over `wgpu` (e.g. `egui`, `iced`)

This is the realistic Rust path.

Use a GUI library that already knows how to:

- Create windows.
- Handle events.
- Layout widgets.
- Render text.

Examples:

- **`egui`** (with `eframe`): immediate‑mode GUI, battery‑included app framework.
- **`iced`**: Elm‑style architecture, more “retained‑mode” feeling.

These typically use `wgpu` or similar under the hood, but you never touch it directly.

For this project, a minimal **`egui` + `eframe`** app could:

- Show a left panel of **categories**:
  - Memo generation
  - Refocus / repair
  - Export / brand
  - Diagnostics / utilities
- For the selected action, show:
  - Description (pulled from a config file the repo maintains).
  - Inputs: text fields, file pickers, toggles.
  - A **Run** button.
- At the bottom / right: a **log console** streaming stdout/stderr from the underlying CLI process.

Rough effort levels:

- **Prototype** (list of commands, parameters for a couple of them, Run, and a log window):
  - 1–2 days of focused work if we limit scope and piggyback on existing CLIs.
- **More polished tool** (categories, job history, persistent config, cancelation, etc.):
  - 1–2 weeks.

Pros:

- **Non‑bloated**: single Rust binary, no browser, no Node runtime.
- Cross‑platform (macOS, Linux, Windows) if needed.
- Keeps core orchestration in the existing stack; the GUI is mostly a thin RPC/CLI shell.

Cons:

- Desktop niceties (system theming, menus, file dialogs, etc.) may require manual wiring / extensions.
- You still own: process management, streaming logs, some amount of concurrency / state.

### Option C: macOS‑only SwiftUI front‑end over the CLIs

If macOS‑only is acceptable, **SwiftUI** is arguably the easiest way to get a really nice UX fast.

Conceptual architecture:

- **SwiftUI app** as a front‑end.
- It either:
  - calls the existing **Python/Rust CLIs** using `Process` and pipes stdout/stderr, or
  - talks to a small **local HTTP or Unix‑socket API** exposed by the orchestrator.

UI layout sketch:

- **Sidebar**: groups of actions / agents:
  - *Memos*
  - *Sections / Refocus*
  - *Exports & Branded Outputs*
  - *Maintenance / Debug*
- **Main content**:
  - Title + description for the selected action.
  - Parameter form (memo path, company handle, section name, flags, etc.).
  - Run / Cancel.
- **Bottom panel**:
  - Log output (live streaming from the underlying process).

Effort levels (assuming you’re new to SwiftUI but comfortable with modern languages):

- **Usable v0 over a subset of commands**: a weekend.
- **Comfortable daily driver**: 1–2 weeks to smooth edges and wire more agents.

Pros:

- Very **native macOS feel** (windows, menus, dark mode, system behaviors) “for free”.
- No extra runtime besides what macOS already has.
- Great fit for a **personal control center** for complex CLIs.

Cons:

- **mac‑only**. If teammates need Windows/Linux, you’ll need another UI or ask them to stick with the terminal.
- You’ll write it in **Swift**, which may be a context‑switch from your current stack.

---

## Architectural principle: keep the brains in the existing tools

Regardless of GUI choice, a key design decision is:

> The GUI should be a **thin orchestration and parameter‑collection layer**, not the place where the actual memo/agent logic lives.

Concretely:

- The existing CLIs and/or a small internal API remain the **source of truth** for workflows.
- The GUI:
  - Loads a **declarative catalog** of actions (e.g. JSON/TOML in the repo that lists agents, their descriptions, and their parameters).
  - Presents forms based on that schema.
  - Invokes the underlying command / endpoint and streams back logs and status.

Benefits:

- You don’t fork logic between “CLI” and “GUI” worlds.
- You can continue to iterate on agents in Python/Rust, test them via CLI, and only adjust a thin schema/config for the GUI.
- If this GUI is later replaced (e.g. by a web app or a different native client), the core behavior doesn’t have to move.

---

## Answering: "How hard is this, really?"

Framed against the actual need (a control panel, not a design‑tool‑grade UI):

- **Raw `wgpu`**
  - Technically possible.
  - Practically: takes you deep into graphics/UI‑toolkit territory.
  - For this project, it’s **overkill and high risk** for little benefit.

- **Rust + `egui` / `iced`**
  - Sensible for a **lean, cross‑platform, non‑web GUI**.
  - Effort: days for a basic prototype, weeks for a refined daily tool.
  - Good tradeoff if you want to stay in Rust and avoid platform‑specific stacks.

- **SwiftUI (mac‑only)**
  - Probably the **fastest path to a comfortable, native app** if mac is your primary environment.
  - Effort: a weekend to get something that meaningfully reduces your cognitive load, then incremental polish.

So: building "a GUI" for this use case is not inherently hard, but it becomes hard **if** you insist on doing low‑level graphics (`wgpu` directly) or if you try to move all orchestration logic into the GUI.

---

## A plausible v0 scope

To keep this realistic, a good v0 might:

- **Support only a few high‑leverage actions**, e.g.:
  - Generate a new memo from a seed brief.
  - Refocus/repair a specific section of an existing memo.
  - Export a branded HTML/PDF artifact.
- Provide:
  - Clear descriptions of what each action does.
  - Minimal parameters (paths, IDs, toggles).
  - One log panel.
- Defer "nice to haves" like job history, advanced configuration, multi‑user support, etc.

That alone would already:

- Reduce cognitive overhead (“what’s the command for X again?”).
- Make the system approachable for non‑terminal people.
- Give you a place to hang more capabilities as the project evolves.

---

## If/when we implement this

Implementation sketch, irrespective of GUI tech:

1. **Define a catalog of actions** in the repo
   - A single JSON/TOML/YAML file listing:
     - id
     - display_name
     - description
     - underlying command / endpoint
     - parameter schema (name, type, default, required, help text)
2. **Build a thin adapter layer**
   - For each action, translate GUI input → CLI args or API payload.
3. **Implement the GUI shell**
   - Sidebar of actions.
   - Parameter form auto‑generated from the schema.
   - Run / Cancel.
   - Log streaming.
4. Iterate on the catalog + small UI tweaks as workflows evolve.

The main point: the UI client is **replaceable**; the action catalog and core agents are not.

## Where does a Python GUI fit?

An obvious question: since so much of the system is Python, why not also do the GUI in Python and stay in one language?

### Python GUI options

Common ways people build “native” desktop GUIs in Python:

- **Tkinter**
  - Bundled with CPython.
  - Very simple and widely documented.
  - Looks dated and basic; fine for internal tools, not great for polished UX.

- **PyQt / PySide (Qt)**
  - Mature, feature‑rich, cross‑platform GUI framework.
  - “Native‑feeling”, but not literally using AppKit/Cocoa widgets.
  - PyQt licensing (GPL/commercial) vs PySide (LGPL) is a consideration.

- **wxPython**
  - Wrapper over native toolkits (e.g. Cocoa on macOS).
  - Closer to true “native” look/feel than Qt in some cases.
  - Smaller ecosystem and a bit more old‑school.

- **Kivy / pyglet and friends**
  - More custom UI / app framework territory.
  - Often aimed at touch/mobile or special UIs, less ideal for a conventional desktop control panel.

- **PyObjC + Cocoa (macOS)**
  - Direct bridge to Cocoa APIs from Python.
  - You’re essentially writing a mac app using Objective‑C/Swift APIs from Python.
  - Powerful, but you inherit the complexity of native APIs *plus* Python runtime overhead.

### The real issue: packaging and runtime “bloat”

Where Python desktop apps get hairy is less about coding and more about **shipping**:

- You must bundle **Python + all dependencies** with your app:
  - Tools like `pyinstaller`, `briefcase`, `cx_Freeze`, etc. can do this.
  - Resulting bundles are often **large** and occasionally finicky.
- Startup time and memory use are typically higher than a small compiled binary.
- Even if you avoid Electron, you’re still shipping a **heavier runtime story** than Rust/Swift.

So while it is absolutely possible to:

- Build a Qt/wx/Tkinter front‑end.
- Have it either shell out to the existing CLIs or import the same Python modules directly.

…the experience is still not as “tight” as a small native binary, especially for a long‑lived tool.

### Comparing Python GUI vs Rust/Swift for this project

Given the explicit constraint of “avoid bloated frameworks like Electron or Flutter,” the comparison looks roughly like this:

- **Python GUI (Qt / wx / Tkinter / PyObjC)**
  - **Pros**:
    - Stays in Python if you wire directly into your orchestrator code.
    - Fast to prototype if you are already comfortable with Python.
  - **Cons**:
    - Packaging is non‑trivial (bundle interpreters, native libs, etc.).
    - App size and startup overhead are noticeably larger.
    - Cross‑platform “native‑feeling” is good but not perfect, and you still ship a heavy runtime.

- **Rust + `egui` / `iced`**
  - **Pros**:
    - Produces a **single compiled binary**, typically small and fast to start.
    - No embedded Python interpreter or web engine.
    - Good cross‑platform story.
  - **Cons**:
    - Different language from most of the existing code.
    - Some learning curve and plumbing for process management / IPC.

- **SwiftUI (mac‑only)**
  - **Pros**:
    - True **native macOS experience**.
    - No extra runtime beyond what macOS ships.
    - Very productive for building a control‑panel‑style app.
  - **Cons**:
    - mac‑only.
    - Requires working in Swift and Xcode.

For this specific memo/agent orchestration system, where the GUI is conceptually “a thin control surface over many CLIs,” the Python GUI route is viable but:

- Still somewhat “bloated” compared to Rust/Swift from a runtime and packaging perspective.
- Doesn’t substantially reduce architectural complexity, since you’d still want a clean boundary between GUI and orchestration logic.

That’s why the default recommendation remains:

- Prefer **Rust+egui** if you want a lean, cross‑platform GUI without a web stack.
- Prefer **SwiftUI** if mac‑only is OK and you want the fastest route to something that feels really good to use.

Python remains best used where it already excels in this project: **the core orchestration and agent logic**, not necessarily the graphical shell wrapped around it.

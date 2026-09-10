---
title: "The Sidecar Cannot See the Claude CLI on PATH"
lede: "A Tauri app launched from Finder gets the macOS GUI PATH — /usr/bin:/bin:/usr/sbin:/sbin — and the FastAPI sidecar inherits it. shutil.which('claude') returns None there, so every memo generated from the desktop app billed the metered API no matter how many agents route through the provider. `bun run dev:native` inherits the terminal's PATH, so it never reproduces in development."
date_authored_initial_draft: 2026-09-10
date_authored_current_draft: 2026-09-10
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-09-10
at_semantic_version: 0.0.0.2
usage_index: 1
publish: false
category: Specification
date_created: 2026-09-10
date_modified: 2026-09-10
tags: [LLM-Provider, Claude-Code-CLI, PATH, Tauri, Sidecar, Cost, Dev-Prod-Divergence]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: 07b556d4-b99d-4eaa-9277-763e1ff1a253
hex_code: 3uo0o6
status: Resolved
severity: High
---

# The Sidecar Cannot See the Claude CLI on PATH

## Status

**Resolved** in `src/llm_provider.py` (`claude_binary()`), 2026-09-10, with nine
tests in `tests/test_claude_resolution.py`. Written up because the *class* of bug
outlives the fix, and because the way it hid is worth remembering.

## What was wrong

`cli_available()` was `shutil.which("claude") is not None`.

`shutil.which` searches `PATH`. A macOS application launched from Finder or the
Dock does not inherit a login shell's `PATH` — it gets the system default:

```
/usr/bin:/bin:/usr/sbin:/sbin
```

`claude` is not there. On this machine it is at `/opt/homebrew/bin/claude`;
elsewhere it is `~/.local/bin`, `~/.bun/bin`, or `~/.claude/local`. None of those
are on the GUI default.

`apps/memopop-native/src-tauri/src/api/sidecar.rs` spawns the sidecar through
`tauri-plugin-shell` with no environment manipulation — verified, there is no
`.env()` or `.env_clear()` call — so the Python process inherits the app's
`PATH` exactly.

Measured:

```
$ env PATH=/usr/bin:/bin:/usr/sbin:/sbin python -c \
    "import shutil; print(shutil.which('claude'))"
None
```

`cli_available()` → False → `complete()` takes the API branch → **every model
call from the desktop app was metered**, on a machine with a working, logged-in
seat.

## Why nobody noticed

`bun run dev:native` starts Tauri from a terminal. The terminal's `PATH` has
`/opt/homebrew/bin` on it. The Tauri process inherits that, the sidecar inherits
it from Tauri, and `shutil.which("claude")` resolves.

**The bug is invisible in development and present in every shipped build.** No
amount of running the app locally would have surfaced it.

It also survived the entire provider refactor. Twenty-nine modules were moved
onto `llm_provider` across a single day; every one of them was inert in the
desktop app the whole time, because the layer they were routed *to* could not
find the binary.

## The fix

`claude_binary()` resolves in three steps and caches the result:

1. `MEMOPOP_CLAUDE_BIN`, if set — an explicit operator override.
2. `shutil.which("claude")` — correct whenever `PATH` is sane.
3. A sweep of known install locations: `/opt/homebrew/bin`, `/usr/local/bin`,
   `~/.local/bin`, `~/.claude/local`, `~/.bun/bin`, `~/.npm-global/bin`,
   `/usr/bin`.

`_via_cli` now invokes the **resolved absolute path** rather than the bare name,
because `PATH` is precisely what is missing in the case this exists for.
`describe_provider()` names the binary it found, so a run header answers "which
one?" and not merely "is there one?".

An override pointing at nothing resolves to `None` rather than silently falling
through to `PATH` — an operator who sets it and gets it wrong should not be
quietly handed a different binary, which is how you bill an account you were
trying to avoid.

## Verification

The realistic simulation is **full user session, GUI `PATH`** — not `env -i`,
which strips the session and produces a different failure (`Not logged in ·
Please run /login`) that misled the first diagnosis. A Finder-launched app has a
real session; it just has a short `PATH`.

```
$ env PATH=/usr/bin:/bin:/usr/sbin:/sbin ANTHROPIC_API_KEY= python probe.py
LLM provider: Claude Code CLI (subscription seat) at /opt/homebrew/bin/claude
binary: /opt/homebrew/bin/claude
elapsed=2.9s  ok=True  provider=cli  text='SIDECAR-OK'
```

A live completion, on the seat, under the GUI `PATH`, with **no API key set at
all**.

## What this does not cover

- **Windows.** The sidecar path there is `.venv/Scripts/python.exe`, and
  `claude` installs elsewhere again. The fallback list is macOS/Linux-shaped.
  Untested; `MEMOPOP_CLAUDE_BIN` is the escape hatch.
- **A packaged CLI-less machine.** If the operator has no CLI, the API fallback
  is correct and unchanged — this only stops a *present* CLI from being missed.
- **The Rust side.** Passing an augmented `PATH` from `sidecar.rs` would also
  work and would fix it for any child process, not just this one. It was not
  done: provider resolution belongs in the module that owns the provider, and a
  Python-side fix is testable in the Python suite.

## The general lesson

The check was correct when it was written. `shutil.which` is the right way to
find a binary — in a process that has a normal `PATH`. What changed was the
*context the code runs in*, not the code.

That is the same shape as every other find in this refactor: guards written when
an API key was the only way to reach a model, none revisited when that stopped
being true. Here the unstated assumption was an inherited shell environment.

**Any capability probe should be evaluated in the environment that will actually
run it.** For this repo that means: the sidecar, not the terminal.

## Related

- [[Route-Every-Claude-Call-Through-The-CLI-First-Provider]] — the refactor this
  was silently defeating
- `src/llm_provider.py` — `claude_binary()`, `_CLAUDE_FALLBACK_DIRS`
- `tests/test_claude_resolution.py` — nine tests, including that `_via_cli`
  invokes the resolved path rather than the bare name
- `apps/memopop-native/src-tauri/src/api/sidecar.rs` — the spawn site

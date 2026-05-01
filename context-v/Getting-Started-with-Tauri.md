


  Tauri Setup Plan (6 Phases)

  ┌───────┬───────────────────────────────────────────────────┬────────┐
  │ Phase │                       What                        │  Time  │
  ├───────┼───────────────────────────────────────────────────┼────────┤
  │ 1     │ Verify prerequisites (Xcode CLI, Rust, Bun)       │ 5 min  │
  ├───────┼───────────────────────────────────────────────────┼────────┤
  │ 2     │ Pick project location                             │ quick  │
  ├───────┼───────────────────────────────────────────────────┼────────┤
  │ 3     │ Scaffold project (bun create tauri-app)           │ 5 min  │
  ├───────┼───────────────────────────────────────────────────┼────────┤
  │ 4     │ First run — confirm a native window opens         │ 2 min  │
  ├───────┼───────────────────────────────────────────────────┼────────┤
  │ 5     │ Add the four plugins (shell, dialog, store, fs)   │ 5 min  │
  ├───────┼───────────────────────────────────────────────────┼────────┤
  │ 6     │ Smoke-test that plugins work from the Svelte side │ 10 min │
  └───────┴───────────────────────────────────────────────────┴────────┘

  How we'll do this: I give you the commands and explain what to expect. You run them and paste the
  output back. We don't move to the next step until the current one is green. If something errors, I
  diagnose before you try the next thing.

```bash
┣[ ~/code/lossless-monorepo/ai-labs/memopop-ai/apps]┣[ 0.041s][ RAM: 26/48GB][ 84]
└─> bun create tauri-app
✔ Project name · memopop-native
✔ Identifier · ai.memopop.native
✔ Choose which language to use for your frontend · TypeScript / JavaScript - (pnpm, yarn, npm, deno, bun)
✔ Choose your package manager · bun
✔ Choose your UI template · Svelte - (https://svelte.dev/)
✔ Choose your UI flavor · TypeScript

Template created! To get started run:
  cd memopop-native
  bun install
  bun run tauri android init
  bun run tauri ios init

For Desktop development, run:
  bun run tauri dev

For Android development, run:
  bun run tauri android dev

For iOS development, run:
  bun run tauri ios dev
```

```bash
bun update svelte svelte-check @sveltejs/kit
bun add -d vite@latest @sveltejs/vite-plugin-svelte@latest typescript@latest
bun install
```

This explicitly pins new majors in package.json (not just bun.lock), so the upgrade is durable.

  What to watch for

  The two real risk surfaces:

  1. vite.config.ts — the scaffold's config might use a key that Vite 7 or 8 deprecated. If dev fails
   to start with a "config option X removed" error, that's where to look. Usually a one-line fix.
  2. TypeScript 6 — stricter checks could surface in svelte-check. If your dev mode runs but bun run
  check complains, we'll address case-by-case.

  Test again
```bash
bun run tauri dev
```



  Each tauri add command does three things automatically:
  1. Adds the Rust crate to src-tauri/Cargo.toml
  2. Adds the JS package to package.json
  3. Adds the plugin's default permissions to src-tauri/capabilities/default.json

  Run them in sequence:

```bash
  bun run tauri add shell
  bun run tauri add dialog
  bun run tauri add store
  bun run tauri add fs
```

  Each one takes a few seconds — it fetches the Rust crate and updates the config files. You'll see
  green ✓ messages or similar.

  What each plugin will do for us later

  ┌────────┬────────────────────────────────────────────────────────────────────────┐
  │ Plugin │                                Used for                                │
  ├────────┼────────────────────────────────────────────────────────────────────────┤
  │ shell  │ Spawning the Python orchestrator processes (the core action mechanism) │
  ├────────┼────────────────────────────────────────────────────────────────────────┤
  │ dialog │ "Browse for repo path" / "Choose deal directory" file pickers          │
  ├────────┼────────────────────────────────────────────────────────────────────────┤
  │ store  │ Persisting active firm, repo path, last-used parameters                │
  ├────────┼────────────────────────────────────────────────────────────────────────┤
  │ fs     │ Reading the action catalog, listing deals/versions/sections            │
  └────────┴────────────────────────────────────────────────────────────────────────┘

  After all four, smoke test


```bash
  bun run tauri dev
```
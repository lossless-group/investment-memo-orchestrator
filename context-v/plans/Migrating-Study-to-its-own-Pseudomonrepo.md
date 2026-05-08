---
title: Migrate `studies/open-specs-and-standards/` into its own pseudo-monorepo
status: proposed
date: 2026-05-02
authors:
  - Michael Staton
  - Claude (Opus 4.7)
target_repo_to_create: lossless-group/study-open-specs-and-standards
visibility: public
---

# Context

`studies/open-specs-and-standards/` started as a quick reading list and is now
ten upstream submodules plus a README and an inquiry note. Continuing to keep
each upstream registered as a *direct* submodule of `ai-labs` makes ai-labs's
`.gitmodules` noisy and forces ai-labs to own change-pointers for ten unrelated
spec repos. Promoting the directory into its own repo
(`lossless-group/study-open-specs-and-standards`) gives the study its own
history, lets us add study-specific tooling (trees, parsers, scripts, README
sections) without touching ai-labs, and reduces ai-labs's `.gitmodules` to a
single entry for the study.

The 10 nested submodules are currently **staged but never committed** in
ai-labs, which is the easiest possible starting point — there is no historical
ai-labs commit that pins their SHAs, so we can detach them losslessly.

# Outcome

After this migration:

- A new public repo `https://github.com/lossless-group/study-open-specs-and-standards`
  exists, with its own `.gitmodules` containing the 10 upstream submodules
  (absolute URLs), a `README.md`, and a `context-v/` directory.
- `ai-labs/.gitmodules` no longer lists the 10 upstream specs. Instead it has a
  single new entry: `studies/open-specs-and-standards` →
  `https://github.com/lossless-group/study-open-specs-and-standards.git`.
- ai-labs is left with its `studies/open-specs-and-standards` submodule
  *staged but uncommitted* on the `development` branch, for the user to review
  before committing.

# Non-goals (do not touch)

- `.claude/settings.local.json` (currently staged add — leave alone)
- `investment-memo-orchestrator` submodule pointer (currently modified — leave alone)
- `memopop-ai` submodule pointer (currently modified — leave alone)
- The four pre-existing ai-labs submodules: `packages/mermaid-js-ai-agent`,
  `packages/Perplexica`, `investment-memo-orchestrator`, `memopop-ai`.

# Phase 1 — Detach the 10 study submodules from ai-labs

**Working directory:** `/Users/mpstaton/code/lossless-monorepo/ai-labs`

The submodules are staged-adds, never committed. The canonical primitive for
this state is `git rm --cached`, which removes the gitlink from the index *and*
auto-stages the corresponding `.gitmodules` deletion in one shot. Do **not**
use `git restore --staged` (would diverge index and `.gitmodules`) or
`git submodule deinit` (only valid for *committed* submodules; these aren't).

1. Save the work that should travel with the new repo:
   ```bash
   mkdir -p /tmp/study-migration
   cp studies/open-specs-and-standards/README.md /tmp/study-migration/README.md
   cp -r studies/open-specs-and-standards/context-v /tmp/study-migration/context-v
   ```

2. Remove each of the 10 staged submodule gitlinks from the index:
   ```bash
   for name in 12-factor-agents agent-2-agent agents-md ai-skills design-md \
               frictionless-specs llms-txt modelcontextprotocol open-spec spec-kit; do
     git rm --cached -f "studies/open-specs-and-standards/$name"
   done
   ```

3. Verify `.gitmodules` no longer has those 10 entries (only the four
   unrelated entries remain) and that `git diff --cached .gitmodules` shows
   the deletions are staged:
   ```bash
   cat .gitmodules
   git diff --cached .gitmodules | head -60
   ```

4. Remove the working-tree directory and the modules cache:
   ```bash
   rm -rf studies/open-specs-and-standards
   rm -rf .git/modules/studies/open-specs-and-standards
   ```

5. Sanity-check that `.git/config` has no leftover `submodule.studies.*` keys
   (there shouldn't be any since the adds were never committed, but verify):
   ```bash
   git config --get-regexp '^submodule\.studies\.' || echo "clean"
   ```

# Phase 2 — Build the new study repo locally

**Working directory:** `/Users/mpstaton/code/lossless-monorepo/ai-labs/studies/open-specs-and-standards`

1. Re-create the directory and initialize:
   ```bash
   mkdir -p studies/open-specs-and-standards
   cd studies/open-specs-and-standards
   git init -b main
   ```

2. Restore the user content:
   ```bash
   cp /tmp/study-migration/README.md ./README.md
   cp -r /tmp/study-migration/context-v ./context-v
   ```

3. Add a minimal `.gitignore` (covering OS cruft and the typical study-time
   junk; mirroring the spirit of ai-labs's `.gitignore`):
   ```
   .DS_Store
   node_modules
   .venv
   venv
   __pycache__
   .env
   ```

4. Add the 10 upstream submodules (absolute URLs — the Plan agent confirmed
   `../` relative paths would resolve to the wrong org for these external
   repos):
   ```bash
   git submodule add https://github.com/humanlayer/12-factor-agents.git 12-factor-agents
   git submodule add https://github.com/a2aproject/A2A.git agent-2-agent
   git submodule add https://github.com/agentsmd/agents.md.git agents-md
   git submodule add https://github.com/anthropics/skills.git ai-skills
   git submodule add https://github.com/google-labs-code/design.md.git design-md
   git submodule add https://github.com/frictionlessdata/specs.git frictionless-specs
   git submodule add https://github.com/AnswerDotAI/llms-txt.git llms-txt
   git submodule add https://github.com/modelcontextprotocol/modelcontextprotocol.git modelcontextprotocol
   git submodule add https://github.com/Fission-AI/OpenSpec.git open-spec
   git submodule add https://github.com/github/spec-kit.git spec-kit
   ```

5. Stage and commit (explicit paths only — never `git add -A`):
   ```bash
   git add .gitignore README.md context-v .gitmodules \
           12-factor-agents agent-2-agent agents-md ai-skills design-md \
           frictionless-specs llms-txt modelcontextprotocol open-spec spec-kit
   git commit -m "study(open-specs-and-standards): seed study repo with 10 upstream specs and inquiry"
   ```

# Phase 3 — Create remote and push

Still inside `studies/open-specs-and-standards/`:

```bash
gh repo create lossless-group/study-open-specs-and-standards \
  --public \
  --description "A study of open specs and standards for human+agent file-based cooperation." \
  --source . \
  --remote origin \
  --push
```

Verify:
```bash
gh repo view lossless-group/study-open-specs-and-standards --json url,visibility,defaultBranchRef
```

# Phase 4 — Re-attach as a single submodule of ai-labs

**Working directory:** `/Users/mpstaton/code/lossless-monorepo/ai-labs`

The newly-pushed repo is now the source of truth. We need ai-labs to track it
as a fresh submodule. The cleanest path is to remove the local working dir
(its `.git` is bound to itself, not ai-labs) and let `git submodule add`
re-clone it.

1. ```bash
   cd /Users/mpstaton/code/lossless-monorepo/ai-labs
   rm -rf studies/open-specs-and-standards
   ```

2. ```bash
   git submodule add https://github.com/lossless-group/study-open-specs-and-standards.git \
     studies/open-specs-and-standards
   ```

3. Initialize the nested submodules in the freshly-cloned study (so the
   working tree is fully populated locally):
   ```bash
   git submodule update --init --recursive studies/open-specs-and-standards
   ```

4. Verify ai-labs's `.gitmodules` now has the four pre-existing entries plus
   one new entry for `studies/open-specs-and-standards`, and **zero** entries
   for the 10 individual specs:
   ```bash
   grep -c '^\[submodule' .gitmodules   # expect 5
   grep 'studies/open-specs-and-standards' .gitmodules
   ```

5. Inspect what's staged for the eventual ai-labs commit (do **not** commit;
   the user wants to review):
   ```bash
   git status --short
   git diff --cached .gitmodules
   ```

# Phase 5 — Verification

End-to-end checks before handing back:

- [ ] `gh repo view lossless-group/study-open-specs-and-standards` returns the
      repo as public with a default branch `main`.
- [ ] Cloning the new repo into a scratch dir works and `--recurse-submodules`
      pulls all 10 nested specs:
      ```bash
      mkdir -p /tmp/study-roundtrip && cd /tmp/study-roundtrip
      git clone --recurse-submodules \
        https://github.com/lossless-group/study-open-specs-and-standards.git
      ls study-open-specs-and-standards/12-factor-agents | head -5
      ```
- [ ] In ai-labs, `studies/open-specs-and-standards/.git` is a *file* whose
      gitdir points into `.git/modules/studies/open-specs-and-standards/`
      (confirms it is correctly registered as a submodule of ai-labs).
- [ ] In ai-labs, the four unrelated changes from before this migration are
      still present and unmodified:
      `.claude/settings.local.json` (A), `investment-memo-orchestrator` (MM),
      `memopop-ai` (MM).
- [ ] `git status` in ai-labs shows the new submodule entry staged but
      uncommitted.

# Critical files

- `ai-labs/.gitmodules` — edited indirectly via `git rm --cached` and
  `git submodule add`
- `ai-labs/.git/modules/studies/open-specs-and-standards/` — directory to
  delete in Phase 1
- `ai-labs/studies/open-specs-and-standards/README.md` — preserve through
  migration (already contains the curated study description)
- `ai-labs/studies/open-specs-and-standards/context-v/inquiry/Filesystem-Naming-Conventions.md`
  — preserve through migration

# Rollback

If anything goes wrong before Phase 3's `gh repo create`, recovery is local:

- The 10 submodule directories can be re-cloned by re-running the original
  `git submodule add ...` commands in ai-labs (the URLs are documented in
  Phase 2).
- The README and `context-v/` are backed up at `/tmp/study-migration/`.

If something goes wrong *after* the GitHub repo is created, options:

- `gh repo delete lossless-group/study-open-specs-and-standards --yes` and
  start over (only safe if no one else has cloned it yet).
- Or fix forward: amend commits and `git push --force` on the new repo's
  `main` (only if no collaborators have pulled).

# Notes for downstream users of ai-labs

After this migration, anyone cloning ai-labs needs:
```bash
git clone --recurse-submodules https://github.com/lossless-group/lossless-ai-labs.git
# or, post-clone:
git submodule update --init --recursive
```
This was already true (because ai-labs has had submodules), but the
double-nesting now makes the `--recursive` flag mandatory if they want to
pull all the way through to the study's nested specs. Worth a one-line note
in ai-labs's top-level README.

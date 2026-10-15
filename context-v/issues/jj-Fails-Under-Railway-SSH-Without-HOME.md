---
title: "jj Fails Under railway ssh Without HOME"
lede: "An operator script that drops from root to the memopop user over railway ssh can't start a firm's jj history, because HOME still points at /root."
publish: false
date_created: 2026-10-15
date_modified: 2026-10-15
date_authored_initial_draft: 2026-10-15
date_authored_current_draft: 2026-10-15
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5 (1M context)
at_semantic_version: 0.0.1.0
status: Open
site_uuid: 2ac8816f-b24a-436d-9ee5-00b991b19041
hex_code: awsuw9
summary: >-
  railway ssh runs as root. A script that setuid's to memopop to keep file
  ownership right still inherits HOME=/root, and jj git init then fails reading
  /root/.config/git/config. Hit while unpacking an imported firm onto the
  volume. Worked around by setting HOME; the operator guide doesn't say so yet.
tags:
  - Issue-Resolution
  - MemoPop
  - Railway
  - Jujutsu
  - Operator
---

# jj Fails Under railway ssh Without HOME

## What happened

Unpacking an imported firm's workspace onto `/data/firms/` over `railway ssh`,
the script extracted and chowned the files, switched to the `memopop` user
with `os.setgid`/`os.setuid`, and called `JjHistory.ensure_repo()`:

```
jj git init: Error: Failed to access the repository
Caused by:
3: The configuration file at "/root/.config/git/config" could not be read
4: Permission denied (os error 13)
```

`JjHistory._env` drops inherited `JJ_*` and `GIT_*` variables but keeps
`HOME`, and jj's git backend reads the user's git config from `$HOME`.

## Workaround

Set `HOME` to the user's home (and drop `XDG_CONFIG_HOME`) after switching
users, before any jj call. The firm's history then initialized normally.

## To resolve

- Add the rule to `docs/operator/deploy.md` next to the `railway ssh` commands.
- Or make `JjHistory._env` set `HOME` from the effective user (`pwd.getpwuid(os.geteuid())`),
  so every caller is safe.
- `scripts/import_firm.py` should grow its server-side half (unpack, chown,
  first commit) as a committed script, instead of an inline one.

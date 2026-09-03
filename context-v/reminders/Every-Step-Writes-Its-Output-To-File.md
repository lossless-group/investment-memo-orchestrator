---
title: "Every Step Writes Its Output To File"
lede: "A run's destination folder is decided before the first step, and every step writes its result there as it finishes. Nothing lives only in memory."
date_created: 2026-08-26
date_modified: 2026-08-26
date_authored_initial_draft: 2026-08-26
date_authored_current_draft: 2026-08-26
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5 (1M context)
at_semantic_version: 0.0.0.1
status: Active
site_uuid: 624acfd6-b316-42ab-8b12-69bf95318cde
hex_code: yzdk1t
summary: >-
  Guardrail written after a 2026-08-26 ProfileHealth dataroom run was killed
  roughly twenty minutes in and produced nothing at all. Scanning, classification
  of 158 documents, and five completed extractors were held in memory and would
  have been written only by a single save call at the end. The work was not slow
  to redo — it was unrecoverable, and there was nothing to resume from. Long runs
  get killed: by the operator, by a timeout, by a crash in step nine. A run that
  only writes at the end treats every interruption as total loss, which is also
  why the versioning system exists and why no run output ever belongs in a
  scratch or temp directory.
tags: [Orchestrator, Artifacts, Versioning, Resumability, Run-Discipline, Reminders]
---

# Every Step Writes Its Output To File

## The rule

1. **Every run has a destination outputs folder, resolved before the first step
   does any work.** `output/<Company>-v0.0.x/` for a legacy run,
   `io/<firm>/deals/<Deal>/outputs/<Deal>-v0.0.x/` for a firm-scoped one. The
   version manager picks it; nothing else invents a path.
2. **Every step writes its own output to that folder the moment it completes.**
   Not at the end of the phase, not when the graph finishes. When the step is
   done, the file exists.
3. **Nothing of value lives only in memory or only in `state`.** State is how
   steps talk to each other. It is not where results are kept.
4. **Never write run output to a scratch, temp, or session directory.** Not for
   a test, not for a trial, not "just to look at it first." If it is worth
   producing it is worth producing where it belongs.

## Why

Long runs get killed. By the operator, by a timeout, by an API failure in step
nine, by a laptop lid. That is normal and must be survivable.

A run that writes only at the end converts every interruption into total loss.
Worse, it converts a *recoverable* interruption into total loss: the expensive
work was done, the answers existed in memory, and they evaporated because nobody
had written them down.

**The concrete failure this came from.** `analyze_dataroom` on the ProfileHealth
dataroom:

```
line  81   extraction_results = _run_extractors(...)     # 8 extractors, ~30 min
                                                         # competitive, cap table,
                                                         # financial, traction, team…
line 140   save_dataroom_analysis_artifacts(...)         # the first and only write
```

The run was stopped during the legal pass at line 81. Scanning had completed.
Classification of 158 documents had completed — a 194-second model pass.
Five extractors had completed and found real data, including a cap table with
fifteen shareholders and seven SAFEs. **None of it reached disk.** The output
directory contained one empty folder.

Everything above had to be paid for twice.

## What this looks like in practice

- An extractor finishes → its `.json` and `.md` are written before the next
  extractor starts. `0-dataroom-inventory` should exist while `1-competitive`
  is still running.
- A section is drafted → `2-sections/03-market-context.md` is on disk before the
  writer moves to section four. (The section-by-section writer already does this;
  it is the model to copy, not the exception.)
- A step that produces nothing still records that it ran and found nothing.
  "No cap table data extracted" is a result, and a rerun should not have to
  rediscover it.
- Killing a run at any moment leaves a directory that says how far it got.

## Resumability is the point, not a bonus

Because each step's output is a file, a rerun can look at the folder and skip
what is already there. That is what `--resume` means, and it only works if the
files exist. A run that keeps its results in memory cannot be resumed even in
principle — there is nothing to resume *from*.

This is also what the version directory is for. `<Deal>-v0.0.1` is not just a
label on a finished memo; it is the workspace the run fills in as it goes, and
the reason a killed run can be restarted rather than rerun.

## When a step legitimately holds state

Passing a value between two adjacent steps in memory is fine — that is what
`MemoState` is for. The rule is about **results**, not about plumbing. The test:
*if the process died right now, would anything of value be lost?* If yes, it
should already have been written.

## See also

- `context-v/reminders/Round-Closing-Timeline-Nuances.md` — `anomalies.json`, which is written incidentally during a run and follows the same discipline
- `src/versioning.py` — the version manager that resolves the destination folder
- `src/artifacts.py` — the artifact writers each step should be calling

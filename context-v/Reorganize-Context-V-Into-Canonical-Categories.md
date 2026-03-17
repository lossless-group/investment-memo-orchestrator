---
title: "Reorganize Context-V Into Canonical Categories"
lede: "Step-by-step prompt for reclassifying all context-v files into the four canonical categories: Specification, Reminder, Prompt, Blueprint."
date_authored_initial_draft: 2026-03-17
date_authored_current_draft: 2026-03-17
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Prompt
date_created: 2026-03-17
date_modified: 2026-03-17
tags: [Context-V, Reorganization, Categories, Frontmatter, Migration]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.6"
---

# Reorganize Context-V Into Canonical Categories

## Context

Read `context-v/Context-V-System-Blueprint.md` first. It defines the four document types:

- **Specification**: Design doc for a feature, agent, system, or fix
- **Reminder**: Short convention/preference doc for context window feeding
- **Prompt**: Step-by-step implementation guide
- **Blueprint**: System-level architecture spanning multiple features

Currently, files use inconsistent categories (Architecture, Infrastructure, Agent Documentation, Reference, etc.). These all need to map to one of the four canonical types.

## Step 1: Update `category` field in frontmatter

For each file listed below, open it and change the `category:` frontmatter field to the recommended value. **Do not move files between directories** — only change the frontmatter.

### Files that should become `Blueprint`

These describe system-level patterns or cross-cutting architecture:

| Current Category | File | Rationale |
|---|---|---|
| Architecture | `Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` | Core pipeline architecture used by all agents |
| Architecture | `Format-Memo-According-to-Template-Input.md` | Outline system used across writer, research, citation agents |
| Architecture | `Dataroom-Analyzer-Agent.md` | System-level plan for multi-doc processing subsystem |
| Architecture | `Model-Scorecard-Agent-and-Template-System.md` | Scoring framework referenced by validator and other agents |
| Architecture | `Introducing-a-Diagram-Generator-Agent.md` | Diagramming system with reusable patterns |
| Infrastructure | `Git-Submodules-for-Private-Data-and-Exports.md` | Repo-wide file organization pattern |
| Blueprint (keep) | `12Ps-Integration-Plan.md` | Cross-cutting framework touching outlines + scoring + writer |
| Blueprint (keep) | `Anti-Hallucination-Fact-Checker-Agent.md` | Premium sources integration across research + citation agents |
| Blueprint (keep) | `Firm-and-Deal-based-File-Organization-System.md` | File org pattern used across all agents |
| (missing) | `Portfolio-Listing-Agent-and-Current-Portfolio-Section.md` | Portfolio listing pattern across firm scoping |
| Specification | `Vision-for-Production-Grade-Memopop-Monorepo.md` | Production architecture vision spanning all subsystems |

### Files that should become `Specification` (most already are)

These are single-feature/agent/fix designs. Most are already correctly categorized. Confirm these:

| Current Category | File | Notes |
|---|---|---|
| Agent Documentation | `Deck-Analyzer-Agent.md` | Agent spec, not a separate category |
| (missing) | `PDF-Parser-Agent-Spec.md` | Missing category entirely, should be Specification |
| Reference | `Citation-Reminders.md` | Actually a spec for CSS citation fixes, not a reminder |
| Reference | `Export-Style-Templates.md` | Spec for dark/light mode export support |
| Reference | `Document-Examples.md` | Short reference pointer — could be Reminder, but keep as Specification since it's about where example data lives |
| Blueprint | `issue-resolution/Premium-Data-Sources-Integration-Plan.md` | Bug fix / integration, scoped to one subsystem → Specification |

All `issue-resolution/*.md` files are already `Specification` — leave them as-is.

All `Introducing-a-*.md` files are already `Specification` — leave them as-is.

All other `Specification` files — leave them as-is.

### Files that should become `Prompt`

| Current Category | File | Rationale |
|---|---|---|
| Prompts (rename) | `Generate-Investment-Memo-for-Portfolio-Company.md` | Step-by-step usage guide |
| Prompts (rename) | `Improving-Memo-Output.md` | Sequential improvement workflow |

### Files that should become `Reminder`

| Current Category | File | Rationale |
|---|---|---|
| Reminder (keep) | `reminders/Frontmatter-Standards-for-Context-Files.md` | Already correct |
| Reminder (keep) | `reminders/Extended-Markdown-Citation-System-Syntax.md` | Already correct |

**Consider moving to `reminders/`** (optional, discussed in Step 3):
- `Citation-Reminders.md` — if the CSS spacing info is better treated as a convention reminder than a spec
- `Document-Examples.md` — if it's just a pointer to example files

### Files with no category (fix these)

| File | Recommended Category |
|---|---|
| `Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` | Blueprint |
| `PDF-Parser-Agent-Spec.md` | Specification |
| `Portfolio-Listing-Agent-and-Current-Portfolio-Section.md` | Blueprint |

## Step 2: Normalize the `category` values

After updating, run this to verify all files use one of the four canonical categories:

```bash
for f in context-v/*.md context-v/issue-resolution/*.md context-v/reminders/*.md; do
  cat=$(grep '^category:' "$f" | head -1 | sed 's/^category: *//')
  case "$cat" in
    Specification|Reminder|Prompt|Blueprint) ;;
    *) echo "INVALID: $cat → $(basename $f)" ;;
  esac
done
```

This should produce no output. If it does, fix the remaining files.

## Step 3: Optional directory reorganization

The current structure keeps most files at the root with `issue-resolution/` and `reminders/` as subdirectories. This works fine. **Do not create `specs/`, `blueprints/`, or `prompts/` subdirectories** — the flat structure with category-in-frontmatter is simpler and avoids arguments about where a borderline file goes.

The only organizational move to consider:

- If `Document-Examples.md` is just a pointer (5 lines), it could move to `reminders/` or be deleted if the path is already in CLAUDE.md
- `Citation-Reminders.md` could move to `reminders/` if you want all convention docs in one place

Both are optional and low-priority.

## Step 4: Update the README table

After changing categories, update the README's "Design Documents (context-v)" section to reflect the new category values. The table structure can stay the same — just change the Category column values.

## Step 5: Commit

```bash
git add context-v/ README.md
git commit -m "docs(context-v): normalize all files to four canonical categories (Specification, Reminder, Prompt, Blueprint)

Reclassify Architecture, Infrastructure, Agent Documentation, Reference,
and Prompts categories into the four canonical types defined in
Context-V-System-Blueprint.md. Fix 3 files with missing categories.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

## Summary of Changes

| Change | Count |
|---|---|
| Architecture → Blueprint | 5 files |
| Infrastructure → Blueprint | 1 file |
| Specification → Blueprint | 1 file (Vision-for-Production-Grade) |
| Agent Documentation → Specification | 1 file (Deck-Analyzer) |
| Reference → Specification | 3 files |
| Blueprint → Specification | 1 file (Premium-Data-Sources in issue-resolution/) |
| Prompts → Prompt | 2 files |
| Missing → assigned | 3 files |
| Already correct | 34 files |
| **Total** | **51 files** |

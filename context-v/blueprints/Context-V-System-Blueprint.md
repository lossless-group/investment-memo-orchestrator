---
title: "Context-V System Blueprint"
lede: "Blueprint for the context-v documentation system: a structured approach to maintaining project context, design decisions, and institutional knowledge across AI-assisted development sessions."
date_authored_initial_draft: 2026-03-17
date_authored_current_draft: 2026-03-17
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Blueprint
date_created: 2026-03-17
date_modified: 2026-03-17
tags: [Context-V, Documentation, System-Design, Knowledge-Management, AI-Development]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.6"
---

# Context-V System Blueprint

**Status**: Active
**Date**: 2026-03-17

---

❯ I think I want `journeys` to be the higher level layer, and `implementation` and
`issue-resolutions` to be the subsidiary layer.

  The relationship isn't parent-child. It's temporal:

      PLAN                  ENCOUNTER REALITY              LEARN
   ┌──────────┐                                       ┌──────────┐
   │ Blueprint │─┐                                 ┌──│ (updated) │
   │ Spec      │ │   ┌─────────────────────────┐   │  │ Reminder  │
   │ Prompt    │ ├──>│   Issue-Resolution       │───┤  │ Spec      │
   │ Reminder  │ │   │                          │   │  │ Prompt    │
   │           │─┘   │   "Here's what happened  │   └──│ Blueprint │
   └──────────┘      │    and why we changed    │      └──────────┘
                     │    course."              │
                     └─────────────────────────┘

I like the diagrams you made that show the "narrative" "the journey"

what we can do is have journeys be a fifth bucket, implementation and issue-resolution be two types
of journeys.  These new diagrams are cool, let's codify those by updating the doc

## Purpose

`context-v/` is the project's institutional memory. It exists because AI-assisted development happens across many sessions, each with a fresh context window. Without a structured documentation system, design decisions get lost, mistakes get repeated, and the project drifts.

The name `context-v` is short for "context vigilance" — the practice of actively maintaining awareness of what has been decided, what went wrong, what patterns work, and what the team prefers. 

> [!ASIDE] Context Vigilance 
> Context Vigilance (context-v) is a more disciplined, comprehensive, and even neurotic extension of Context Engineering, emphasizing the new, nearly bombastic need for systematic, proactive, and persistent documentation to feed AI assisted workflows. 
>
> The term was coined by us, The Lossless Group, as we sought to address shortcomings, and their resulting frustrations, while tinkering with practices commonly touted by developer influencers. The broader developer community quicly went from Vibe Coding to Prompt Engineering to Context Engineering within the span of a few months, demonstrating how quicky everyone had identified that collaborating with AI Agents necessitated a more structured approach to documentation. We felt like our approach was more systematic and comprehensive, and unique enough to give it a name and tell the world about it.

***

**Naming convention**: `{Descriptive-Title}.md` using Title-Case-With-Hyphens. Prefix with `Introducing-a-` for new agent/feature proposals. This is because we often use files with libraries that struggle with spaces in filenames. Underscores may be used but as a separator between phrases of meaning, the most common being dates, version numbers, author name, or category to help organize files.  {Prefix_Descriptive-Title_Suffix}.md

***

## How the Four Types Relate

The four document types form two pairs, connected by two axes: **depth** and **direction**.

### The Depth Axis: Exhaustive vs. Bite-Sized

Blueprints and Specifications are the **deep documents** — exhaustive, explanatory, conceptual. They describe *what* a system is and *why* it works that way. They are meant to be read, studied, and referenced.

Reminders and Prompts are their **bite-sized counterparts** — short, actionable, designed for execution rather than understanding. They distill the deep documents into things you can *do* without re-reading the full rationale.

```
        EXHAUSTIVE / CONCEPTUAL              BITE-SIZED / ACTIONABLE
     ┌──────────────────────────┐          ┌──────────────────────────┐
     │                          │          │                          │
     │       BLUEPRINT          │ -------> │        REMINDER          │
     │                          │ distills │                          │
     │  System-level patterns,  │   into   │  "Do it this way."       │
     │  architecture, cross-    │          │  Conventions, defaults,  │
     │  cutting concerns        │          │  stack preferences       │
     │                          │          │                          │
     ├──────────────────────────┤          ├──────────────────────────┤
     │                          │          │                          │
     │     SPECIFICATION        │ -------> │         PROMPT           │
     │                          │ distills │                          │
     │  Feature design, agent   │   into   │  "Do these steps."       │
     │  specs, problem/solution │          │  Sequential actions,     │
     │  rationale               │          │  CLI commands, handoffs  │
     │                          │          │                          │
     └──────────────────────────┘          └──────────────────────────┘
```

### The Reference Axis: What Points to What

Documents reference each other in predictable directions:

- **Specifications reference Blueprints** — A spec for a new agent cites the pipeline architecture blueprint to explain where the agent fits. The blueprint is the map; the spec is one location on it.
- **Prompts reference Reminders** — A step-by-step implementation prompt says "follow the citation syntax in `reminders/Extended-Markdown-Citation-System-Syntax.md`" rather than restating the convention inline.
- **Blueprints generate Reminders** — When a blueprint establishes a system-wide pattern, the conventions that enforce it day-to-day become reminders.
- **Specifications generate Prompts** — When a spec is ready for implementation, the steps to build it become a prompt.

```
                    references
     SPECIFICATION ─────────────> BLUEPRINT
          │                           │
          │ generates                  │ generates
          │                           │
          v           references      v
        PROMPT ───────────────> REMINDER
```

### The Full Picture

```
     ┌─────────────────────────────────────────────────────────┐
     │                                                         │
     │              BLUEPRINTS  ◄──── referenced by ── SPECS   │
     │              (the map)                    (the locations)│
     │                 │                            │          │
     │                 │ distill into               │ distill  │
     │                 │                            │ into     │
     │                 v                            v          │
     │              REMINDERS ◄── referenced by ── PROMPTS     │
     │              (the habits)              (the steps)      │
     │                                                         │
     │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
     │  Left side: SYSTEM-WIDE       Right side: SCOPED        │
     │  Top row:   DEEP              Bottom row: ACTIONABLE    │
     └─────────────────────────────────────────────────────────┘
```

Think of it as a 2x2:

|  | System-Wide | Feature-Scoped |
|---|---|---|
| **Deep / Conceptual** | Blueprint | Specification |
| **Actionable / Bite-Sized** | Reminder | Prompt |

A Blueprint says *"this is how our pipeline works."*
A Specification says *"this is how the KPI Extractor agent works within that pipeline."*
A Reminder says *"always use Obsidian-style footnotes, not inline links."*
A Prompt says *"run these 5 steps to add frontmatter to all context-v files."*

---

## The Four Document Types

Every document in `context-v/` is one of exactly four types. The `category` field in frontmatter must be one of these values.

### 1. Specification (`category: Specification`)

**What it is**: A design document for a specific feature, agent, system, or fix — either implemented, in progress, or planned.

**Characteristics**:
- Describes a bounded idea, a coherent piece of work, or an interrelated feature set.
- May have a clear problem statement and proposed solution, or may add context and rationale to an idea or set of ideas.
- May include code examples, schemas, pipeline diagrams
- Can be at any status: Planning, In Progress, Implemented, Abandoned
- Ranges from a single feature, to a set of features, to a full agent design doc

**When to write one**: When you're designing something new, overhauling project architecture, or proposing a substantial change to existing behavior.

**Examples**:
- Agent specs (KPI Extractor, Table Generator, Diagram Generator)
- Feature designs (Content Density Mode, Legal Doc Comparator)
- Large scale bug fixes (Fix Firm-Scoped Output Paths, Deck Data Flow Gap)
- Issue resolutions (Preventing Hallucinations, Citation Pipeline Accuracy)
- Deployment plans (Papermark Self-Hosted Dataroom)

### 2. Reminder (`category: Reminder`)

**What it is**: A short, convention-focused document that gets fed into context windows to enforce consistency on mundane but important details.

**Characteristics**:
- Short (sometimes under 100 lines)
- Prescriptive, not exploratory — states "do it this way"
- Covers preferences and conventions that are not standard, 
  - Code Assistant models often intuitively are likely to do it some other way
  - Given context windows, models forget or get it wrong, repeatedly... thus need reminding.
- Not about system design, but about how the team works or how to do things
- Should be stable — updated rarely, referenced often

**When to write one**: When you find yourself correcting the same mistake in multiple sessions, or when a convention exists in someone's head but not on paper.

**Examples**:
- Stack preferences and default project conventions 
- Frontmatter field standards for context files
- Citation syntax preferences (Obsidian/GitHub flavored markdown)
- File naming conventions
- Code cmmenting conventions
- Import ordering preferences
- Commit message format

**Naming convention**: `{Convention-Topic}.md`. Lives in `context-v/reminders/` subdirectory.
**Stack preferences**: (i.e. use this library or package manager, not another. `This is Astro and Svelte, not React and Next.js.  Therefore....`)

  **Note**: It's helpful to have a frontmatter property called `use_index: [n]` where n is the count of use. This way we can focus and build out reminder systems that are most used first. 
  **Note**: These are not "rules" but "preferences" - they are guidelines to follow unless there is a compelling reason not to.

### 3. Prompt (`category: Prompt`)

**What it is**: A step-by-step implementation guide, usually sequential and action-oriented. Designed to be handed to a developer or AI assistant as executable instructions. Rather than it reading as a single prompt, each step is written and used as a prompt.

**Characteristics**:
- Numbered steps or a clear sequence
- Specific file paths, commands, and expected outcomes
- Smaller scope than a spec — focuses on "how to do X" not "what X should be"
- Often references specs for the design rationale
- Can be used as input to a new Claude Code session

**When to write one**: When you need to hand off implementation work to a future session (yours or someone else's), and the steps are specific enough to follow mechanically.

**Examples**:
- "Generate an investment memo for [Company]" (step-by-step CLI usage)
- "Improve memo output quality" (section-by-section improvement workflow)
- "Reorganize context-v files into canonical categories" (migration steps)

**Naming convention**: `{Action-Oriented-Title}.md` — should read as an imperative or task description.

### 4. Blueprint (`category: Blueprint`)

**What it is**: A system-level architecture document describing patterns, structures, or frameworks that span multiple features and recur across the codebase.

**Characteristics**:
- Describes *how the system works* at a conceptual or structural level, not a single feature
- Documents patterns that show up in multiple places
- Covers cross-cutting concerns: file organization, state management, pipeline architecture, component design patterns
- More durable than specs — a spec might implement part of a blueprint, a blueprint might be used as a reference document across many specs and prompts.
- Often referenced by multiple specs

**When to write one**: When you realize you're describing the same architecture in multiple specs, or when a system-level decision affects many features at once.

**Examples**:
- Multi-agent pipeline architecture and state flow
- Firm and deal-based file organization system
- Outline-based content structure (YAML outlines → agents → sections)
- Brand configuration and multi-tenant export system
- The context-v system itself (this document)
- Integration plans that touch many subsystems (12Ps, Premium Sources)

**Naming convention**: `{System-or-Pattern-Name}.md`. Should describe a system, not an action.

---

## Directory Structure

```
context-v/
├── Context-V-System-Blueprint.md          # This document
├── {Specification-files}.md               # Specs live at root level
├── {Blueprint-files}.md                   # Blueprints live at root level
├── {Prompt-files}.md                      # Prompts live at root level
├── issue-resolution/                      # Subset of specs focused on debugging
│   └── {Issue-Name}.md                    #   (category is still Specification)
└── reminders/                             # All reminders in their own subdirectory
    └── {Convention-Name}.md
```

### Why `issue-resolution/` is a subdirectory, not a category

Issue resolution docs are **Specifications** — they have a problem statement, root cause analysis, and a proposed/implemented fix. The subdirectory is purely organizational, keeping debugging-focused specs separate from feature/agent specs. The `category` field in frontmatter remains `Specification`.

### Why `reminders/` is a subdirectory

Reminders are reference material meant to be pulled into context windows. Keeping them in their own directory makes it easy to glob them (`context-v/reminders/*.md`) for bulk injection into agent prompts or session preambles.

---

## Frontmatter Standard

Every file in `context-v/` must have YAML frontmatter. The canonical fields:

```yaml
---
title: "Human-Readable Title"
lede: "One-sentence description for search and browsing, enticing the reader to open the file."
date_authored_initial_draft: YYYY-MM-DD
date_authored_current_draft: YYYY-MM-DD
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification    # One of: Specification, Reminder, Prompt, Blueprint
date_created: YYYY-MM-DD
date_modified: YYYY-MM-DD
tags: [Relevant, Hyphenated-Tags]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.6"
---
```

See `reminders/Frontmatter-Standards-for-Context-Files.md` for the complete field reference.

---

## Category Decision Tree

When creating a new document, use this:

```
Is this about how the team works or formatting conventions?
  → YES → Reminder (put in reminders/)

Is this step-by-step instructions someone could follow mechanically?
  → YES → Prompt

Does this describe a system-level pattern used across multiple features?
  → YES → Blueprint

Everything else (feature design, agent spec, bug fix, deployment plan):
  → Specification (put in issue-resolution/ if it's a bug/debugging doc)
```

---

## How Context-V Integrates with Development

### Starting a new Claude Code session
1. CLAUDE.md provides the project overview and commands
2. Relevant `context-v/` specs provide design context for the specific task
3. `context-v/reminders/` docs enforce conventions

### During development
- When a design decision is made that isn't obvious from code, write a spec
- When a system bug or constraint is diagnosed, write an issue-resolution spec with root cause
- When you find yourself repeating a correction, write a reminder
- When you see a pattern spanning multiple features, write a blueprint

### After development
- Update the spec's `status` field and `date_last_updated`
- Increment `at_semantic_version` if the document content changed substantially
- Increment `usage_index` each time the document is referenced in a session

---

## Relationship to Other Documentation

| Location | Purpose | Audience |
|---|---|---|
| `CLAUDE.md` | Project overview, commands, architecture summary | AI assistants |
| `context-v/` | Design decisions, conventions, institutional memory | AI assistants + developers |
| `README.md` | User-facing project documentation | External users + new developers |
| `changelog/` | Version-by-version change history | All audiences |
| Code comments | Implementation-level notes | Developers reading code |

`context-v/` is the bridge between high-level README docs and in-code comments. It captures the *why* behind design decisions that are too detailed for the README but too important to live only in code comments.

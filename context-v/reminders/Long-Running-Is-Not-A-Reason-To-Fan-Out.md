---
title: "Long-Running Is Not a Reason to Fan Out"
lede: "Duration is not the variable that decides whether work should be split across agents. Continuity is. Ask before parallelizing anything whose quality depends on what came before it."
date_created: 2026-08-23
date_modified: 2026-08-23
date_authored_initial_draft: 2026-08-23
date_authored_current_draft: 2026-08-23
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5 (1M context)
at_semantic_version: 0.0.0.1
status: Active
site_uuid: 6f04e711-5b31-4ca6-b5d8-d4a16fcdd4d6
hex_code: x7q2mv
summary: >-
  Guardrail born from a 2026-08-23 session in which an agent offered to
  parallelize a 14-minute slide-transcription run, framing the choice as speed
  versus patience. The operator declined in order to protect context continuity.
  The framing was the error: the agent had conflated concurrent API calls with
  agent delegation, and had not noticed that the task carried no continuity to
  protect — which was itself the defect worth fixing. Duration is not the
  variable. Continuity is, and only the operator can price it.
tags:
  - Reminder
  - Tree-Wide
  - Agent-Orchestration
  - Context-Window
  - Delegation
  - Operator-Preference
publish: true
---

# Long-Running Is Not a Reason to Fan Out

**Rule.** A task taking a long time is **not**, on its own, a reason to split it
across subagents or parallel workers. Before proposing any fan-out, establish
whether the work carries **continuity** — whether step N is better for having
seen step N−1. If it does, sequential is not the slow option, it is the correct
one. When continuity is present or arguable, **discuss it with the operator
rather than optimizing for wall-clock on their behalf.**

## Why

On 2026-08-23 an agent was transcribing a 38-slide deck, one model call per
slide, roughly 22 seconds each — about 14 minutes. It volunteered that the run
could be parallelized to finish in two, and framed the choice as speed versus
patience.

The operator declined: *"I think the context-window is important so I'd rather
wait than have it fan out to subagents."*

Two things were wrong, and they pointed in opposite directions.

**The agent's framing was wrong.** Parallelizing that loop would not have
involved subagents at all. It was a Python `for` loop issuing independent HTTP
requests to the Messages API — concurrency inside one process, no delegation, no
second context, nothing spawned. By offering "parallel" without saying what it
meant mechanically, the agent invited a reasonable operator to defend against a
risk that was not on the table.

**The operator's instinct was right about something the agent had missed.** Each
slide was being transcribed in total isolation — one image, one prompt, no memory
of the preceding slides. So there was no continuity to lose by parallelizing,
*because the design had none*. And that absence was a real defect:

- **Animation-build detection is inherently a comparison between adjacent
  pages.** Asking "is this page one frame of a build?" while showing the model a
  single frame is asking it to guess. Six such groups were pending in that very
  deck.
- Cross-slide references (*"Our Solution | …"* on slide 8 continuing slide 7)
  could not be resolved.
- Contradictions between slides could not be noticed.
- The company's vocabulary was re-derived 38 times.

The operator was protecting a property the system did not yet have. The right
response was not "you're mistaken, it's safe to parallelize" — it was to notice
that the property was worth *adding*, which then makes sequential execution
permanent and correct for a real reason.

## The general failure

Agents reach for fan-out when they see a big number — pages, files, records,
minutes — and treat parallelism as the obvious win. The number is the wrong
input. The questions that actually decide it:

1. **Does step N depend on the output of step N−1?** If yes, it cannot be
   parallelized, whatever it costs.
2. **Would step N be *better* for having seen step N−1, even if it does not
   strictly depend on it?** This is the case that gets missed. Build detection,
   tone consistency, deduplication, running totals, "have I already said this" —
   all degrade under independence without failing outright.
3. **Is the operator's judgment or review in the loop?** A run they are watching
   and steering is worth more than a run that finishes sooner without them.
4. **Is "concurrent" being confused with "delegated"?** Concurrent HTTP calls,
   background processes, subagents, and worktrees are four different things with
   four different risk profiles. Name which one is meant.

## How to apply

- **Never offer "I can parallelize this" without saying what the mechanism is.**
  "Six concurrent API calls from this process" and "six subagents with their own
  contexts" are different proposals and deserve different answers.
- **Before proposing fan-out, state whether the work carries continuity** and
  what would be lost. If nothing would be lost, say so — and then ask whether
  continuity is something the task *should* have.
- **Treat a long-running task as normal.** Run it in the background so it is not
  killed by a foreground timeout, report progress, and wait. Duration is not a
  problem to be engineered away.
- **Make long tasks resumable instead of fast.** Write each unit of work as it
  completes and skip completed units on re-run. This removes most of the reason
  anyone wanted parallelism — the fear of losing an expensive interrupted run.
- **When the operator states a preference like this, take it as standing.** It
  is a judgment about their work, not a constraint to be negotiated down the next
  time a big number appears.

## The tell

If the sentence forming is *"this will take N minutes, I could split it up"* —
stop. Replace it with *"this will take N minutes; here is what each step would
lose by not seeing the one before it."* If the answer is "nothing", that is worth
saying out loud, because it is usually a finding about the design rather than a
green light.

## Related

- [[Check-The-Substrate-Before-Reasoning-On-Top-Of-It]] — the sibling failure:
  reasoning confidently on top of something never verified
- `context-v/agent-skills/pseudomonorepos/SKILL.md` — search-first discipline,
  the other place where doing less work first is the faster route

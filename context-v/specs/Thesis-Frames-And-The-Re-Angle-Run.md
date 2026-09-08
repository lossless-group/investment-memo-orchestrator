---
title: "Thesis Frames and the Re-Angle Run"
lede: "A memo's angle is currently implicit — it emerges from the deal config, the outline, and whatever research landed, and it can only be changed by editing sections one at a time until they disagree with each other. This makes the frame a first-class object the pipeline holds, and adds a run mode that regenerates only the sections the frame touches, with the frame in every writer call so the sections agree. Grill-me at memo scope rather than section scope."
date_authored_initial_draft: 2026-09-08
date_authored_current_draft: 2026-09-08
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-09-08
date_modified: 2026-09-08
tags: [Thesis-Frame, Re-Angle, Writer-Agent, Grill-Me, Outline-Contract, Memo-Revision]
authors:
  - Michael Staton
augmented_with: "Claude Code on Claude Opus 5"
site_uuid: 132ba434-030f-4acf-831b-9ecb6c91bb73
hex_code: biqllo
status: Proposed
severity: Medium
---

# Thesis Frames and the Re-Angle Run

## The problem

Two operations look alike from the operator's chair and are not alike at all.

**"Improve this section"** is local. One file, more evidence, tighter prose. The machinery exists —
`improve-section.py`, and the four-step discipline in the `adhoc-edits-workflow` skill. What is
missing is only a surface to drive it from.

**"Change the angle"** is global. When the thesis of a deal changes, the change lands in most of the
memo at once. The live example: ProfileHealth is being approached by Prudential Long-Term Care to
serve LTC carriers in a B2B2C model. The v0.0.3 memo is written throughout as though private-pay
clinicians are the only customer. Under the new frame the changes land in Executive Summary, Opening
(the market becomes a closed block of 5.8M policies, not 350K physicians), Offering (the clinician
product becomes delivery rather than go-to-market), Opportunity (TAM and GTM inverted), Risks (new:
single champion, proposed-not-contracted, the genetic-privacy perimeter), the 12Ps scorecard, and
Closing. Seven of ten sections.

Done as seven separate "improve this section" passes, you get seven independently re-angled sections
that do not agree with each other. **No editor and no chat window fixes that.** The frame has to be
an object the pipeline holds, not an instruction repeated seven times.

## Relationship to grill-me

This is [[Grill-Me-Per-Section-User-Input-Moment]] generalised from section scope to memo scope. That
exploration already establishes the mechanism — pause, brief the user, take a structured decision,
inject it into the writer's context — and scopes it to one section's *synthesis frame*. A thesis
frame is the same object one level up: the decision that governs how every affected section is
synthesised. Build the frame object first; grill-me at both scopes then shares one pause/resume path
rather than needing two.

## Research is additive; prose is a synthesis

The single most important property of this design, and the one that makes framed runs safe to
repeat:

> **`1-research/` accumulates. `2-sections/` is regenerated from it.**

A research file is not a per-run artifact. It is the deal's evidence base, and a new thesis is
almost always *new evidence about the same company* rather than a replacement for what was already
gathered. The clinician research on ProfileHealth — 62.8 KB across ten files, every claim tied to a
dataroom document — does not become false because a carrier channel appeared. It becomes **half the
picture**. A run that regenerates research wholesale throws away the half that is still true and
re-pays for it, which is both wasteful and lossy: the second gathering will not reproduce the first
exactly, so facts silently disappear between versions.

So research directives are additive by default, and they are a **separate axis** from what happens
to the prose:

| Research directive | Meaning |
|---|---|
| `extend` | Research the frame's new questions and **append** findings and citations to the existing file. Nothing already present is removed or rewritten. |
| `refresh` | `extend`, plus re-verify claims already in the file and mark any that the new evidence contradicts. Use when the frame calls existing findings into question rather than merely adding to them. |
| `reuse` | Carry the file forward untouched. No research call at all. |

| Prose directive | Meaning |
|---|---|
| `rewrite` | Regenerate the section from the (now larger) research base under the frame. Prior prose is not shown to the writer. |
| `amend` | Show the writer the existing prose and ask for the minimum change that makes it consistent with the frame. Preserves good sentences and their citations. |
| `re-score` | Rerun the scorecard evaluator with the frame in context. |
| `unchanged` | Not regenerated, not shown, not touched. Protects hand-authored work. |

The pairing is what does the work. `research: extend` + `prose: rewrite` is the common case: grow the
evidence, then re-synthesise the whole section over the union so it reads as one argument rather than
an old section with a new paragraph stapled on.

### Provenance on appended research

Every appended block is stamped with the frame that produced it:

```markdown
<!-- research-block: frame=ltc-carrier-b2b2c run=v0.0.4 appended=2026-09-08 -->
```

This is not bookkeeping for its own sake. It is what lets a later reader — or the fact-checker, per
`context-v/issues/Validation-and-Fact-Checker-not-using-Research.md` — tell clinician-era evidence
from carrier-era evidence, and it is what makes a frame reversible: dropping a thesis means dropping
its blocks, not re-deriving the file.

## The frame object

A frame lives at `io/<firm>/deals/<Deal>/frames/<name>.yaml`. It is deal-scoped, not firm-scoped —
the same firm will hold different theses about different companies.

```yaml
name: "LTC carrier B2B2C"
slug: ltc-carrier-b2b2c
stance: re-sequencing        # re-sequencing | replacement | dual-thesis
premise: >
  The long-term care carrier becomes the lead customer and the clinician product
  becomes the delivery mechanism rather than the go-to-market. This is a
  re-sequencing of the same product, not a pivot away from the existing one.

evidence:
  - path: inputs/Prudential-Partnership-Proposal.md
    note: "Source document; every quote in it is on the record."

caveats:                      # travel with the frame into EVERY research and writer call
  - "Phases 1-2 are proposed and under executive review. Not contracted."
  - "The $9,800 deferral figure is a Profile Health illustration, not an actuarial estimate."

questions:                    # merged with the outline's guiding_questions, never replacing them
  06-opportunity.md:
    - "How large is the closed standalone LTC block, and what share is reachable
       through the top ten carrier relationships?"
    - "What participation rate does the carrier's own outreach experience support?"

affects:                      # keys are outline `filename` values; two axes per section
  01-executive-summary.md:  { research: extend,  prose: rewrite }
  03-opening.md:            { research: extend,  prose: rewrite }
  05-offering.md:           { research: extend,  prose: amend }
  06-opportunity.md:        { research: extend,  prose: rewrite }
  07-risks.md:              { research: extend,  prose: amend }
  08-scorecard-summary.md:  { research: reuse,   prose: re-score }
  10-closing-assessment.md: { research: reuse,   prose: rewrite }
  02-origins.md:            { research: reuse,   prose: unchanged }
  04-organization.md:       { research: reuse,   prose: unchanged }
  09-funding-terms.md:      { research: reuse,   prose: unchanged }
```

### Field semantics

| Field | Meaning |
|---|---|
| `stance` | How the new thesis relates to the old one. Governs default prose posture. |
| `premise` | The one paragraph every affected section must be consistent with. |
| `evidence` | Source documents, ingested into the corpus before any section is researched. |
| `caveats` | Non-negotiable qualifications, injected verbatim into every research and writer call. |
| `questions` | Per-section research questions **merged with** the outline's, never replacing them. |
| `affects` | Per-section `{research, prose}` pair. Sections absent default to `{reuse, unchanged}`. |

### Why `caveats` is the load-bearing field

A frame introduced by a chat agent one section at a time launders proposals into facts. The
ProfileHealth case has claims that are true only with their qualification attached — the revenue is
proposed, the ROI figure is illustrative, the regulatory protection is contractual rather than
statutory. Carrying them on the frame means every section inherits the qualification, rather than
depending on whichever agent happened to write that paragraph. Because they inject into the
*research* call too, the qualification lands in the durable layer rather than only in prose that the
next assembly can strip.

## Where it injects — two points, not one

The first draft of this spec injected the frame into the writer only. That is wrong, and the
correction is the most important thing in this document.

**A frame changes what gets researched, not only how it gets written.** Under the LTC frame the
question behind Opportunity is no longer "what is the TAM across 350K physicians" but "how large is
the closed standalone LTC block and what share is reachable through ten carrier relationships."
Prudential is also *new evidence that is not in the dataroom at all*. A writer handed the old
research and a new frame will re-angle prose over facts that were gathered to answer different
questions — which produces confident writing on a stale evidence base, the worst possible outcome.

So the frame injects in both places:

### 1. The researcher — `src/agents/codified_section_researcher.py:434`

`synthesize()` builds its `user_prompt` from the section name plus the outline's
`guiding_questions` (line 383-384) and the curated source block. The frame contributes:

- **Frame-derived questions**, merged with the outline's. The outline still owns the section
  taxonomy; the frame adds what this thesis needs answered inside it.
- **The evidence documents**, so frame sources are in the corpus the researcher may cite.
- **The caveats**, so a qualification lands in the research file where it is durable, not only in
  the prose where the next assembly can strip it.

### 2. The writer — `src/agents/writer.py:616`

`write_single_section` composes `user_prompt` out of outline-derived blocks — `dataroom_facts`,
`mode_guidance`, `section_def.description`, `questions_text`, `vocab_text`, `target_length`. The
frame contributes one more block, built the same way and placed beside `mode_guidance`:

```
ACTIVE THESIS FRAME: {frame.name}  ({frame.stance})

{frame.premise}

THIS SECTION'S DIRECTIVE: {affects[section]}
{directive_notes[section]}

NON-NEGOTIABLE QUALIFICATIONS — carry these wherever the underlying claim appears:
- {caveat}
```

No new agent, no new graph node, no change to the outline contract. The outline owns the section
taxonomy (per `CLAUDE.md` §"Architectural direction" #3); the frame owns the angle. A frame that
renames or reorders sections is out of contract.

## How to run the agents

### The frame is a variable, never a hardcode

`--frame` is a run variable of exactly the same kind as `--mode`, `--fresh` and `--firm`. It is
parsed in `src/main.py` (alongside the existing flags at lines 42-85), placed on `MemoState`, and
read by the two agents above. **No agent imports a frame file, and no prompt contains frame text as
a literal.** The rules this enforces:

- A frame is data on disk under `io/<firm>/deals/<Deal>/frames/`. Adding a thesis is authoring a
  YAML file, never editing Python.
- Running with no `--frame` behaves exactly as today. The feature is invisible until asked for.
- The state field is the single source: `state["frame"]`. An agent that wants frame context reads
  state, the same way it reads `memo_mode`.
- Two frames over one deal are two files and two runs. Neither is privileged in code.

```python
# src/state.py — MemoState gains one optional field
frame: Optional[ThesisFrame]      # None => today's behaviour, unchanged

# src/main.py — parsed like every other run variable
parser.add_argument(
    "--frame",
    type=str,
    help="Thesis frame slug under io/{firm}/deals/{deal}/frames/. "
         "Reframes research and writing for the sections the frame declares.",
)
```

### One code path, not two

The first draft proposed a separate `src/reangle.py`. That was a mistake for the same reason the
single injection point was: if research must be regenerated for most sections, a "re-angle" is not a
different operation from a run — **it is a run with a frame variable set.**

So there is no second program. There is one pipeline, and `affects` acts as a *scoping filter* on it:

```bash
# Full run under a frame — research AND writing regenerated for every section.
# This is the default and the one to reach for when the thesis really moved.
python -m src.main "ProfileHealth" --firm humain \
    --frame ltc-carrier-b2b2c --version v0.0.4

# Same frame, but only regenerate the sections the frame declares as
# rewrite/amend/re-score. `unchanged` sections are copied from the prior version.
python -m src.main "ProfileHealth" --firm humain \
    --frame ltc-carrier-b2b2c --version v0.0.4 --scope-to-frame

# No frame — today's behaviour, byte for byte.
python -m src.main "ProfileHealth" --firm humain
```

### What is and isn't at risk in a framed run

Because research is additive, a framed run **cannot lose evidence**. `extend` only appends;
`reuse` doesn't touch the file. The evidence base only ever grows, across every version and every
frame. That removes the main reason the first draft of this spec wanted a separate, narrowly-scoped
program.

What *is* at risk is **hand-authored prose**, and only prose. ProfileHealth v0.0.3 §9 (Funding &
Terms) was written by hand through `adhoc-edits-workflow` — the per-instrument SAFE transcription,
the conversion table, the cap-table contradiction. Nothing regenerates that. It is protected by
`09-funding-terms.md: { research: reuse, prose: unchanged }`, and `prose: unchanged` is the only
mechanism that protects it.

So the guidance is simple:

- **Run the full pipeline under the frame.** Research grows, sections are synthesised over the union,
  and they agree with each other because one thesis was in context for all of them.
- **Use `prose: unchanged` deliberately** for any section carrying analyst work an agent should not
  overwrite. Audit that list before every framed run; it is the only thing standing between a good
  hand-edit and a confident regeneration.
- `--scope-to-frame` remains available to skip regenerating `unchanged` sections entirely, but it is
  now an optimisation rather than a safety mechanism.

### The run, step by step

1. **Resolve** the frame from `--frame`. Fail loudly if any `affects` key is not a section
   `filename` in the active outline. (The v0.0.3 directory has `07-risks--what-could-go-wrong.md`
   while the outline declares `07-risks.md`; the loader resolves that drift, the frame never
   encodes it.)
2. **Ingest evidence.** Each `evidence[].path` is read into the corpus the codified researcher may
   cite, and registered so its citations resolve. This must happen before any section is researched.
3. **Fork the version.** A framed run always writes a new version directory and never edits in
   place, so the two theses can be read side by side.
4. **Research** the in-scope sections with the frame's questions and caveats in context.
5. **Write** them with the frame block and the per-section directive.
6. **Assemble and export** through the existing path, unchanged.

### Verifying a framed run

- Every caveat appears in the research layer, not only in prose — `grep` the `1-research/` files.
- No `unchanged` section differs from the prior version.
- The scorecard moved on dimensions the frame touches and not elsewhere.
- The assembled memo states no proposed revenue as booked.

## What this does not do

- It does not decide the frame. That is the operator's judgment, which is the entire premise.
- It does not touch the outline. Section taxonomy stays the outline's contract.
- It does not resolve conflicts between two frames. Dual-thesis memos are a `stance` value here and a
  synthesis problem that is out of scope for the first cut.

## Build order

1. **Frame schema + loader**, with `affects` validated against the active outline.
2. **`--frame` on `src/main.py`** and `frame` on `MemoState` — the variable, wired end to end.
3. **Frame block in the writer** (`writer.py:616`), `rewrite` directive only.
4. **Frame block in the researcher** (`codified_section_researcher.py:434`) + evidence ingestion.
   Steps 3 and 4 together are the first honest framed run.
5. **`--scope-to-frame`**, plus the `amend` and `re-score` directives.
6. **MemoPop Native fast-follow** — see below.

Steps 1-4 produce a readable v0.0.4 and need no UI.

## Fast-follow — MemoPop Native

The artifact browser today lists every file in a version with its size, and that is all it does.
There is no way to open a file, no way to tell an editable artifact from a build output, and no
action available on any row. A framed run makes that gap acute: the whole point is to read what the
research grew into and what the prose became, and neither is reachable from the app.

Development on the native app has been stalled; this is the work that unstalls it, and none of it
depends on the frame work landing first.

### 1. Make a file openable

Clicking a row opens it in a viewer pane, typed by extension:

| Type | View |
|---|---|
| `.md` | Rendered markdown, with a source toggle |
| `.json` / `.yaml` | Folded, syntax-highlighted tree |
| `.csv` | Table |
| `.png` / `.svg` | Image preview |
| `.pdf` | Embedded viewer |

### 2. Tier the tree — editable vs. build output

This is the durable-layer rule made visible, and it matters more than it looks. In September 2026 a
re-assembly destroyed citation definitions that existed only inside an assembled draft, because
nothing had written them back to `1-research/`. An editor that opens `7-<Deal>-vX.Y.Z.md` as a text
buffer manufactures that bug on demand.

| Tier | Paths | Affordance |
|---|---|---|
| **Evidence** | `1-research/`, `inputs/`, `frames/` | Editable |
| **Prose** | `2-sections/` | Editable |
| **Build output** | `7-*.md`, `exports/`, `0-deck-*`, `3-source-catalog/` | Read-only, with a lock affordance and a one-line explanation |

An "Assemble" action sits on the build-output tier instead of a cursor, so the durability loop —
edit research, edit section, assemble, export — is a visible sequence rather than tribal knowledge.

### 3. Row actions

A kebab per row, contextual to tier and type: Open · Reveal in Finder · Copy path · Diff against
previous version · (evidence/prose tiers) Edit · (build tier) Assemble, Export.

### 4. Frame affordances

- A **frame picker** beside the version dropdown, listing `frames/*.yaml` plus "No frame".
- A **directive review** before a framed run: the `affects` table rendered as a checklist, so the
  operator confirms the `{research, prose}` pair per section — and in particular sees which sections
  are `prose: unchanged` — before anything is spent. This is the natural place for grill-me at memo
  scope to surface later.
- A **version diff**, since a framed run forks the version and the whole question is what changed.

### 5. Then the editor and the chat rail

Port flave's editor (`ai-labs/flave-ai/apps/editor` — CodeMirror 6 + `@lossless-group/lfm` +
`FlaveMarkdown.svelte`) over the tiered tree. flave already carries `railView: 'files' | 'chat'`
scaffolded for exactly this.

When the chat rail lands, the agent gets **tools, not a filesystem** —
`add_research_fact(section, claim, citation)` and `edit_section(section, patch)` — so the four-step
discipline is enforced by the tool surface rather than by an agent remembering a skill. It rides the
existing two-method transport: POST via `request()`, stream via `subscribeEvents()`. No third method.

## The first frame

`io/humain/deals/ProfileHealth/frames/ltc-carrier-b2b2c.yaml`, stance `re-sequencing` — the reading
the source document itself argues: *"Long-term care is the proving ground. Virtual care is the
market,"* with Profile today built for the clinician and the Prudential engagement forcing the
consumer half. Framing it as a pivot away from clinicians would overstate a partnership that is
still under executive review, and would misplace the real change, which lands harder in Risks and
Opportunity than in Offering.

## See also

- [[Grill-Me-Per-Section-User-Input-Moment]] — the same mechanism at section scope (in the parent `memopop-ai` repo)
- `context-v/issues/Validation-and-Fact-Checker-not-using-Research.md` — why frame caveats must reach the gates too
- `agent-skills/adhoc-edits-workflow` — the four-step discipline a re-angle run must not bypass
- `src/agents/writer.py:545` — `write_single_section`, the injection point
- `src/outline_loader.py` — outline resolution the frame validates against

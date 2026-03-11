---
title: Introducing a Content Density Mode System
lede: A system-level content mode toggle (redundant vs concise) that alters the behavior of the writer, table generator, and quality agents to match different firm preferences for information density and repetition.
date_authored_initial_draft: 2026-03-10
date_authored_current_draft: 2026-03-10
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-10
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Content-Strategy, Configuration, Writer-Agent, Redundancy, Firm-Preferences]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A toggle switch between two document layouts—one dense and compact with tables replacing prose, the other expansive with repeated key metrics highlighted across multiple sections.
date_created: 2026-03-10
date_modified: 2026-03-10
---

# Introducing a Content Density Mode System

**Status**: Draft
**Date**: 2026-03-10
**Last Updated**: 2026-03-10
**Author**: AI Labs Team
**Related**: Introducing-a-Table-Generator-Agent.md, Post-Generation-Quality-Agents.md, Format-Memo-According-to-Template-Input.md

---

## Executive Summary

Different firms have fundamentally different philosophies about memo density and repetition. Some assume readers skim — they want key data points repeated across sections so a reader landing on any section gets context without reading the whole document. Others read front-to-back and find repetition tedious and unprofessional.

This specification introduces a `content_mode` setting (`"redundant"` or `"concise"`) that propagates across multiple agents, altering how they handle information repetition, table/prose relationships, and cross-section references.

---

## The Two Philosophies

### Redundant Mode (Default)

**Assumption**: Readers skim. Partners flip to the section they care about.

**Behavior**:
- Key metrics (funding, ARR, team size) appear in multiple sections where relevant
- Tables supplement prose — the same data appears in both formats
- Executive Summary contains substantial detail, not just references
- Cross-section references are rare; each section is semi-self-contained
- Longer overall memo length is acceptable

**Who wants this**: Firms with large partnerships where different partners read different sections. Firms producing memos for LPs who will skim. Firms where memos serve as reference documents.

### Concise Mode

**Assumption**: Readers read front-to-back. Repetition wastes their time.

**Behavior**:
- Each data point appears once, in its most relevant section
- Tables replace inline enumerations (prose is trimmed to narrative analysis only)
- Cross-section anchor links connect related information: "The team (see [Organization](#organization)) brings..."
- Executive Summary is tight — references body sections for detail
- Shorter overall memo length

**Who wants this**: Firms with small teams who read memos thoroughly. Firms where memos are decision documents, not reference documents. Users who reported current output is "too long" or "too repetitive."

---

## Configuration

### In Outline YAML (Preferred)

```yaml
# templates/outlines/direct-investment.yaml
metadata:
  name: "Direct Investment Memo"
  content_mode: "redundant"  # or "concise"
```

### In Company JSON (Per-Deal Override)

```json
{
  "type": "direct",
  "content_mode": "concise"
}
```

### Resolution Order

1. Company JSON `content_mode` (per-deal override) → highest priority
2. Outline YAML `content_mode` (firm default)
3. System default: `"redundant"`

---

## Agent Behavior by Mode

### Writer Agent

| Behavior | Redundant | Concise |
|----------|-----------|---------|
| Key metric repetition across sections | Yes, repeat in context | No, state once in primary section |
| Funding amount in Exec Summary | Full detail | Brief reference with anchor link |
| Team names in Business Overview | Mention key team members | Reference Organization section |
| Market size in Investment Thesis | Restate TAM/SAM figures | "The $X TAM (see [Market Context](#market-context))" |
| Section self-containment | Each section readable standalone | Sections build on each other |
| Target word count per section | Upper end of outline range | Lower end of outline range |

**Implementation**: The writer's system prompt includes a content mode directive:

```
CONTENT MODE: {content_mode}

If REDUNDANT:
- Each section should be readable on its own. A partner flipping to "Team"
  should get enough context without reading prior sections.
- Repeat key metrics where they add context (funding in both Exec Summary
  and Funding & Terms, team highlights in both Business Overview and Team).
- Err on the side of completeness per section.

If CONCISE:
- State each data point once, in its most relevant section.
- Use anchor links to connect related information across sections.
- Keep prose analytical, not enumerative. Let tables handle data display.
- Target the lower end of word count ranges.
```

### Table Generator Agent

| Behavior | Redundant | Concise |
|----------|-----------|---------|
| Table + prose relationship | Additive (both exist) | Tables replace inline enumerations |
| Prose trimming | Never | Trim enumeration prose, keep analysis |
| Table placement | After relevant prose | Replaces relevant prose block |

**Example — Concise mode transformation**:

Before (prose):
```markdown
Key competitors include Calm, which has raised $218M and serves 4M subscribers,
Headspace with $215M raised and 2.5M subscribers, and Noom at $540M raised
with 1M subscribers. The competitive landscape is intensifying as consumer
wellness spending grows.
```

After (concise mode with table):
```markdown
The competitive landscape is intensifying as consumer wellness spending grows.

| Competitor | Funding | Subscribers |
|------------|---------|-------------|
| Calm       | $218M   | 4M          |
| Headspace  | $215M   | 2.5M        |
| Noom       | $540M   | 1M          |
```

After (redundant mode with table):
```markdown
Key competitors include Calm ($218M raised, 4M subscribers),
Headspace ($215M, 2.5M subscribers), and Noom ($540M, 1M subscribers).
The competitive landscape is intensifying as consumer wellness spending grows.

| Competitor | Funding | Subscribers |
|------------|---------|-------------|
| Calm       | $218M   | 4M          |
| Headspace  | $215M   | 2.5M        |
| Noom       | $540M   | 1M          |
```

### Redundancy Reducer Agent

| Behavior | Redundant | Concise |
|----------|-----------|---------|
| Runs? | Light pass only | Full pass |
| What it removes | Only verbatim repeated paragraphs | All duplicate data points |
| Anchor links added | Rarely | Frequently |
| Executive Summary exemption | Yes (summary naturally repeats) | Partial (summary is tighter but still summarizes) |

### Revise Summary Sections Agent

| Behavior | Redundant | Concise |
|----------|-----------|---------|
| Exec Summary detail level | High — includes key metrics, team names, funding details | Moderate — key thesis and 3-4 headline metrics only |
| Closing Assessment length | Full analysis with repeated evidence | Synthesis only, references body sections |
| Target word count | Upper range (~400 words for Exec Summary) | Lower range (~250 words for Exec Summary) |

---

## State Propagation

The content mode is set once and flows through the entire pipeline via state:

```python
# In MemoState (src/state.py)
class MemoState(TypedDict):
    # ... existing fields ...
    content_mode: str  # "redundant" or "concise"
```

Set during initialization in `src/main.py`:
```python
content_mode = company_data.get("content_mode") or outline.get("metadata", {}).get("content_mode", "redundant")
state["content_mode"] = content_mode
```

Each agent reads `state["content_mode"]` and adjusts behavior accordingly.

---

## Implementation Priority

This is a **lower priority** than the competitive landscape system and table generator. The content mode system is a refinement that improves output quality for different firm preferences, but the core agents work without it (defaulting to redundant mode, which is current behavior).

**Suggested order**:
1. Add `content_mode` field to state and config loading (small change)
2. Wire into writer agent prompt (moderate change)
3. Wire into table generator (moderate change)
4. Wire into redundancy reducer (when that agent is implemented)
5. Wire into revise summary sections (small change)

---

## Open Questions

1. **Should there be a "balanced" middle option?** Or is the binary toggle sufficient? (Recommendation: start binary, add a middle option later only if needed.)

2. **Per-section content mode?** Some firms might want the Executive Summary to be redundant (self-contained) but the body sections to be concise. This adds complexity — defer unless specifically requested.

3. **How does this interact with the outline's word count ranges?** Currently each section has `min_words` and `max_words` in the outline. Concise mode would target `min_words`, redundant targets `max_words`. Should we add explicit `concise_target_words` and `redundant_target_words`?

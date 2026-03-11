---
title: Introducing an Augment Research Writer Agent
lede: A two-phase post-hoc enrichment system that first enhances research files with authoritative third-party citations via Perplexity Sonar Pro, then runs an augmentation writer that weaves those new citations into existing section prose without rewriting content.
date_authored_initial_draft: 2026-03-10
date_authored_current_draft: 2026-03-10
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-10
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Agent-Design, Citations, Research, Perplexity, Augmentation, Post-Hoc-Enrichment]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A split-panel diagram showing research documents on the left gaining new citation markers, and memo section documents on the right receiving those citations woven into existing prose, with arrows flowing left to right to represent the augmentation pipeline.
date_created: 2026-03-10
date_modified: 2026-03-10
---

# Introducing an Augment Research Writer Agent

**Status**: Draft (v0.1.0)
**Date**: 2026-03-10
**Last Updated**: 2026-03-10
**Author**: AI Labs Team
**Related**: `src/agents/citation_enrichment.py`, `src/agents/perplexity_section_researcher.py`, `src/agents/writer.py`, `cli/enrich_citations.py`

---

## Problem Statement

After the full memo pipeline completes, the final output often has too few third-party authoritative citations. This happens for several reasons:

1. **Citation enrichment runs on research files, not sections.** The `citation_enrichment_agent` enriches `1-research/` files before the writer runs. But the writer may not carry all citations through to the final section prose.
2. **The writer prioritizes narrative over attribution.** The writer agent synthesizes research into prose and may drop citations that feel redundant to the narrative flow.
3. **No post-hoc citation path exists.** Once sections are written, there is no reliable way to add authoritative citations without rewriting content. The `improve_section.py` CLI rewrites prose entirely. The `enrich_citations.py` CLI imports a function (`enrich_section_with_citations`) that no longer exists.
4. **Direct section enrichment is fragile.** Asking Perplexity to add citations directly to section prose often produces hallucinated URLs or misattributions because the model lacks the research context that produced the original claims.

The result: memos go out with 3-5 citations when they should have 30-80 from authoritative third-party sources (Crunchbase, PitchBook, SEC filings, TechCrunch, Nature, PubMed, etc.).

---

## Proposed Solution: Two-Phase Augmentation

Instead of enriching sections directly, follow the existing data flow pattern: **research is the source of truth, sections are derived from research.**

### Phase 1: Enrich Research

Run `enrich_research_with_citations()` (already implemented in `src/agents/citation_enrichment.py`) on each `1-research/*.md` file. This:

- Uses Perplexity Sonar Pro to find authoritative sources for uncited claims
- Preserves all existing content and citations
- Adds new citations starting from the highest existing citation number + 1
- Appends new citation definitions to the research file's `### Citations` section

This phase already works. The function handles citation key collisions, validates that existing citations aren't removed, and falls back to original content if Perplexity mangles the output.

### Phase 2: Augment Writer

A new lightweight agent that reads enriched research alongside existing section content and weaves citations into the prose. This is fundamentally different from the full writer agent:

| Aspect | Full Writer | Augment Writer |
|--------|-------------|----------------|
| **Input** | Research files + outline | Enriched research + existing section |
| **Output** | New section from scratch | Same section with citations added |
| **Prose changes** | Generates all prose | No prose changes (or minimal bridging) |
| **When it runs** | During pipeline | Post-hoc, on demand |
| **Risk** | N/A (generating fresh) | Must not alter existing narrative |

---

## Augment Writer: Detailed Design

### Core Principle

The augment writer is a **citation insertion agent**, not a content writer. Its job is to match factual claims in section prose to citations found in the enriched research, and insert `[^N]` markers at the correct locations.

### Input

For each section, the augment writer receives:

1. **Existing section content** from `2-sections/{NN}-{section-name}.md` — the prose to augment
2. **Enriched research content** from `1-research/{NN}-{section-name}-research.md` — the source of new citations
3. **Company name** — for disambiguation context
4. **Section name** — for contextual relevance

### Processing Steps

1. **Extract new citations from research.** Compare the research file's citation definitions against what's already inline in the section. Any citation in the research that doesn't appear in the section is a candidate.

2. **Match claims to citations.** For each candidate citation, identify the factual claim it supports in the research file, then find the corresponding claim (or closely paraphrased version) in the section prose.

3. **Insert citation markers.** Place `[^N]` after the matching claim in the section, following the existing citation format conventions:
   - After punctuation with a space: `"text. [^N]"`
   - Multiple citations comma-separated: `"text. [^1], [^2]"`

4. **Append citation definitions.** Add the new citation definitions to the section's citation block (or create one if none exists).

5. **Validate preservation.** Confirm that all existing content and citations in the section are intact. If the augment writer removed or altered existing content, fall back to the original.

### LLM Prompt Strategy

The augment writer uses a constrained prompt that emphasizes preservation:

```
You are a citation insertion specialist. Your ONLY job is to add citation markers
to existing text. You must NOT:
- Rewrite, rephrase, or modify ANY existing text
- Remove or relocate ANY existing citations
- Add narrative commentary or transitions
- Change formatting, headers, or structure

You MUST:
- Insert [^N] markers after factual claims that match citations from the research
- Place citations after punctuation: "claim text. [^N]"
- Only cite claims that have a clear match in the provided research citations
- Skip claims where the match is ambiguous or uncertain
```

The prompt includes both the section content and the enriched research content, with the new citations clearly labeled.

### Output

- Updated section file with new inline citation markers
- Updated citation definitions appended to the section
- A count of citations added vs. candidates found (for transparency)

### Section-to-Research File Matching

The augment writer needs to pair each section file with its corresponding research file. The current naming conventions are:

| Section File | Research File |
|-------------|---------------|
| `2-sections/01-executive-summary.md` | `1-research/01-executive-summary-research.md` |
| `2-sections/03-opening.md` | `1-research/03-opening-research.md` |
| `2-sections/04-organization.md` | `1-research/04-organization-research.md` |

Matching strategy:
1. Extract the numeric prefix and section slug from both filenames
2. Match by numeric prefix first (most reliable)
3. Fall back to fuzzy slug matching if prefixes don't align
4. Skip sections with no matching research file (e.g., `08-12ps-scorecard-summary.md` has no research counterpart)

---

## Pipeline Position

This system is designed primarily for **post-hoc standalone use** via CLI, not as a mandatory pipeline step. The full pipeline already has citation enrichment in its flow.

### Full Pipeline (existing, unchanged)

```
section_research → cite (on 1-research/) → cleanup_research → writer →
    enrichment agents → toc → revise_summaries → cleanup_sections →
    assemble_citations → validate → scorecard
```

### Standalone Post-Hoc Flow (new)

```
CLI invocation
    → Phase 1: enrich_research_with_citations() on 1-research/*.md
    → Phase 2: augment_writer() on each 2-sections/*.md
    → Reassemble final draft via assemble_final_draft()
    → Done
```

### Optional: Pipeline Integration

If desired, the augment writer could be added as an optional pipeline step after `revise_summaries` and before `cleanup_sections`:

```
revise_summaries → AUGMENT_WRITER → cleanup_sections → assemble_citations
```

This would catch any citations that the writer dropped during initial section generation. However, this adds API cost and latency, so it should be opt-in via a flag like `--enrich-citations` or a config setting.

---

## CLI Interface

### Primary Command

```bash
# Enrich all sections for a deal
python cli/enrich_citations.py io/humain/deals/Metabologic/outputs/Metabologic-v0.2.1 --all

# Enrich by company name (auto-resolves latest version)
python cli/enrich_citations.py "Metabolic" --all --firm humain

# Enrich a specific section only
python cli/enrich_citations.py "Metabolic" "Opening" --firm humain

# Dry run: show what citations would be added without writing
python cli/enrich_citations.py "Metabolic" --all --dry-run

# Skip reassembly (useful if you want to review sections before rebuilding)
python cli/enrich_citations.py "Metabolic" --all --no-reassemble
```

### Output

```
╭──────────────────────────────────────────────────────────╮
│ Citation Augmentation                                     │
│ Company: Metabologic                                      │
│ Path: io/humain/deals/Metabologic/outputs/Metabologic-v0.2.1 │
╰──────────────────────────────────────────────────────────╯

Phase 1: Enriching Research
  03-opening-research.md:     8 existing → 14 citations (+6)
  04-organization-research.md: 5 existing → 11 citations (+6)
  05-offering-research.md:    3 existing → 9 citations (+6)
  ...
  Total: +42 new citations across 8 research files

Phase 2: Augmenting Sections
  03-opening.md:              2 existing → 10 citations (+8 inserted)
  04-organization.md:         0 existing → 7 citations (+7 inserted)
  05-offering.md:             1 existing → 6 citations (+5 inserted)
  ...
  Total: +38 citations inserted across 8 sections

Reassembling final draft...
  Final draft: 6-Metabologic-v0.2.1.md (9,450 words, 41 citations)

Done.
```

---

## Section Name Mapping

The current `enrich_citations.py` CLI has a hardcoded `SECTION_MAP` that only covers the default direct investment and fund commitment templates. The 12Ps outline (used by Humain) produces different section names like `03-opening.md`, `04-organization.md`, `05-offering.md`.

### Solution: Dynamic Section Discovery

Instead of maintaining a static mapping, the augment system should:

1. **Scan `2-sections/` directory** for all `*.md` files
2. **Scan `1-research/` directory** for all `*-research.md` files
3. **Match by numeric prefix** (e.g., `03-` matches `03-`)
4. **Accept section names from the command line as fuzzy matches** against the actual filenames found on disk

This makes the CLI work with any outline, including custom firm-specific outlines, without code changes.

```python
def match_section_to_research(sections_dir: Path, research_dir: Path) -> list[tuple[Path, Path]]:
    """Match section files to their research counterparts by numeric prefix."""
    pairs = []
    for section_file in sorted(sections_dir.glob("*.md")):
        prefix = section_file.name.split("-")[0]  # e.g., "03"
        research_matches = list(research_dir.glob(f"{prefix}-*-research.md"))
        if research_matches:
            pairs.append((section_file, research_matches[0]))
    return pairs
```

---

## Anti-Hallucination Safeguards

Citation augmentation is a high-risk operation for hallucination. The following safeguards apply:

### Phase 1 Safeguards (Research Enrichment)

- **Perplexity Sonar Pro** is used specifically because it returns citations from its search index, not hallucinated URLs
- **Existing citation preservation**: If Perplexity removes any existing citations, the entire enrichment is rejected and original content is kept
- **Sequential numbering**: New citations start from `highest_existing + 1` to avoid key collisions

### Phase 2 Safeguards (Section Augmentation)

- **No prose modification**: The augment writer can only INSERT citation markers, not change text
- **Match-or-skip**: If a claim in the section doesn't clearly match a citation from the research, skip it. False negatives (missing a valid citation) are acceptable; false positives (misattributing a citation) are not.
- **Content preservation validation**: After augmentation, compare the prose-only content (with citation markers stripped for comparison purposes only) to confirm the underlying text wasn't altered. The actual output retains all citations — both existing and new.
- **Citation URL validation**: All new citation URLs can optionally be validated via HTTP HEAD before insertion (same as `cleanup_research` gate)

### Citation Numbering Strategy

The augment writer does NOT strip or renumber existing citations. It preserves them exactly where they are and adds new ones using numbers that don't collide:

1. **Scan the section** for the highest existing citation number (e.g., if `[^3]` is the highest, new citations start at `[^4]`)
2. **Insert new markers** at contextually appropriate locations in the prose, using sequential numbers from the starting point
3. **Append new definitions** to the section's citation block
4. **Defer global renumbering** to `assemble_final_draft()`, which already handles cross-section citation consolidation and sequential renumbering

This means individual sections may have non-sequential citation numbers (e.g., `[^1], [^3], [^4], [^7]`) after augmentation — that's fine because the assembly step renumbers everything globally.

### Preservation Validation

To verify the augment writer didn't alter prose, the validation step temporarily strips citation markers from both the original and augmented versions and compares the underlying text. This is a comparison technique only — the actual output retains all citations.

```python
def validate_preservation(original: str, augmented: str) -> bool:
    """
    Verify that augmentation only added citations, not changed content.

    This strips citation markers for COMPARISON ONLY. The actual output
    retains all citations (existing + new). This check ensures the
    augment writer didn't rewrite, remove, or rearrange any prose.
    """
    # Strip citation markers for comparison
    clean_original = re.sub(r'\[\^\d+\]', '', original)
    clean_augmented = re.sub(r'\[\^\d+\]', '', augmented)
    # Remove citation definition blocks for comparison
    clean_original = re.split(r'\n---\n\n### Citations', clean_original)[0].strip()
    clean_augmented = re.split(r'\n---\n\n### Citations', clean_augmented)[0].strip()
    return clean_original == clean_augmented
```

---

## Cost and Performance

### API Costs (per memo, estimated)

| Phase | Calls | Model | Est. Cost |
|-------|-------|-------|-----------|
| Phase 1: Research enrichment | 8-10 (one per research file) | Perplexity Sonar Pro | ~$4-6 |
| Phase 2: Section augmentation | 8-10 (one per section) | Claude Sonnet | ~$2-3 |
| **Total** | **16-20 calls** | | **~$6-9** |

### Why Different Models for Each Phase?

- **Phase 1 (Perplexity Sonar Pro)**: Perplexity has a live search index and returns real URLs from its retrieval system. This is the right tool for finding authoritative sources.
- **Phase 2 (Claude Sonnet)**: The augment writer doesn't need web search — it needs precise text matching and careful insertion. Claude is better at following strict preservation constraints than Perplexity.

### Performance

- Phase 1: ~60-90 seconds (8-10 parallel Perplexity calls)
- Phase 2: ~60-90 seconds (8-10 sequential Claude calls — sequential to avoid citation key collisions)
- Reassembly: ~2 seconds
- **Total: ~2-3 minutes per memo**

---

## Relationship to Existing Components

### What This Replaces

- **`cli/enrich_citations.py`**: The current CLI is broken (imports a deleted function). This spec supersedes it with a working two-phase approach.
- **Direct section enrichment via Perplexity**: The previous approach of asking Perplexity to add citations directly to section prose was fragile and produced low-quality results.

### What This Builds On

- **`enrich_research_with_citations()`** in `src/agents/citation_enrichment.py`: Phase 1 reuses this function directly. It already handles citation preservation, key collision avoidance, and fallback on failure.
- **`assemble_final_draft()`** in `cli/assemble_draft.py`: The reassembly step at the end reuses the existing canonical assembly function, which handles citation renumbering, TOC generation, and header inclusion.

### What This Does NOT Change

- **The full pipeline**: No changes to `src/workflow.py` or the existing agent sequence. The augment writer is a standalone post-hoc tool.
- **Research files as source of truth**: Research files remain the canonical source. Sections are always derived from research.
- **Citation format**: Same Obsidian-style `[^N]` format with the standard definition format: `[^N]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: N/A`

---

## Implementation Plan

### Step 1: Fix the Existing Research Enrichment CLI Path

The `enrich_research_with_citations()` function exists and works. Wire it into the CLI with `--all` support and firm-scoped path resolution.

### Step 2: Build the Augment Writer Function

Create `src/agents/augment_writer.py` with:
- `augment_section_with_citations(section_content, research_content, company_name, section_name) -> str`
- Uses Claude Sonnet for precise citation insertion
- Validates content preservation before returning

### Step 3: Update the CLI

Rewrite `cli/enrich_citations.py` to:
- Support `--all` flag for all sections
- Support firm-scoped path resolution (`--firm`, `--deal`)
- Use dynamic section discovery (no hardcoded section map)
- Run Phase 1 then Phase 2 then reassemble
- Support `--dry-run` for preview

### Step 4: Optional Pipeline Integration

Add an optional `augment_citations` node to `src/workflow.py` that can be enabled via config. This is lower priority than the CLI path.

---

## Open Questions

1. **Should Phase 2 run in parallel or sequential?** Parallel is faster but risks citation key collisions across sections. Sequential is safer. Current recommendation: sequential, since reassembly handles global renumbering anyway — but each section's local numbering must be internally consistent.

2. **Should the augment writer also add citations to tables?** Tables generated by the table generator may contain factual claims (market sizes, funding amounts) that deserve citations. The augment writer could handle table cells as well, but this adds complexity. Recommendation: defer to a future iteration.

3. **Minimum citation threshold?** Should there be a target citation count (e.g., "at least 5 citations per section") that triggers automatic augmentation in the pipeline? This could be a quality gate after the writer runs.

# Anti-Hallucination: Source Validation and Removal

## Problem Statement

Perplexity Sonar Pro, despite being a premium research API with `@source` syntax for targeting authoritative sources, **hallucinates citations**. These hallucinations take several forms:

1. **Fabricated URLs**: Real domains with fake paths (e.g., `mckinsey.com/industries/healthcare/fake-report-2024`)
2. **Placeholder text**: `XXXXX`, `example.com`, `placeholder`
3. **Non-existent pages**: URLs that return 404/410 errors
4. **Future dates**: Citations claiming to be from dates that haven't occurred yet

When these hallucinated sources propagate through the pipeline, they:
- Distort the draft narrative with false "facts"
- Persist in `1-research/` and `2-sections/` even after final draft cleanup
- Mislead human reviewers who trust cited sources
- Undermine the credibility of the entire memo

## Two Agents, Different Purposes

We have two agents that deal with citation quality. They were created separately for good reasons, but their relationship needs clarification.

### citation_validator (`src/agents/citation_validator.py`)

**Purpose**: Comprehensive citation quality assessment

**Scope** (too broad?):
- Validate citation FORMAT (date accuracy, proper `[^N]:` structure)
- Check for duplicate URLs across citations
- Verify citations are properly numbered (no gaps, no duplicates)
- Check URL accessibility
- Validate date consistency (published date matches claim)
- Detect missing citations (inline refs without definitions)
- Generate quality report with issues and suggestions

**Output**: Validation report with scores and issues list

**Problem**: This agent has **too much scope**. It tries to:
1. Assess format quality
2. Check dates
3. Validate URLs
4. Find duplicates
5. Report on everything

Because it's trying to do everything, it often **fails to actually remove** invalid sources. It reports issues but doesn't fix them. The cognitive load on the LLM is high, leading to inconsistent results.

### remove_invalid_sources (`src/agents/remove_invalid_sources.py`)

**Purpose**: Focused URL validation and removal

**Scope** (narrow and actionable):
- HTTP HEAD requests to validate URL accessibility
- Remove citations with 404/410 status codes
- Detect hallucination patterns via regex:
  - `example\.com`
  - `XXXXX`
  - `placeholder`
  - `/path/to/`
  - `\{[^}]+\}` (template variables)
- Actually MODIFY files to remove bad citations
- Clean`1-research/` directories
- Audit `2-sections/` directories (which should not have any invalid citations)

**Output**: Modified files with invalid citations removed

**Why it was created**: The citation_validator wasn't reliably removing hallucinated sources. We needed a focused agent that:
1. Does ONE thing well (validate URLs)
2. Takes ACTION (removes bad citations)
3. Has no competing priorities (no format checking, no date validation)

## The Core Distinction

| Aspect | citation_validator | remove_invalid_sources |
|--------|-------------------|----------------------|
| Primary role | **Assess** quality | **Fix** problems |
| Scope | Broad (format, dates, URLs, duplicates) | Narrow (URL validity only) |
| Output | Report with issues | Modified files |
| Action taken | Reports problems | Removes bad citations |
| LLM cognitive load | High (many tasks) | Low (one task) |
| Reliability | Inconsistent | More reliable |

## Why Two Agents Exist

### Historical Context

1. **citation_validator came first** - Created to ensure citation quality before finalization
2. **It wasn't removing invalid sources** - Despite having URL checking logic, it was reporting issues but not fixing them
3. **AI completion bias** - When asked to "validate citations", the model focused on producing a nice report rather than taking the uncomfortable action of deleting content
4. **remove_invalid_sources was created** - A focused agent that ONLY validates URLs and removes bad ones, with no other distractions

### The "Too Much Scope" Problem

When you ask an LLM to:
- Check format AND
- Validate dates AND
- Find duplicates AND
- Test URLs AND
- Generate a report

It will optimize for the easiest tasks (format checking, report generation) and skimp on the hard tasks (actually testing URLs, removing content).

By creating `remove_invalid_sources`, we gave the LLM a single, clear mission: **test URLs, remove failures**. No report to write, no format to check, no dates to validate. Just test and remove.

## Proposed Architecture

These agents should work together, but at the RIGHT time in the pipeline.

### Current (Wrong) Architecture

```
section_research → writer → ... many agents ... → remove_invalid_sources → citation_validator
                                                          ↑
                                                    Too late!
                                                    Hallucinations already
                                                    propagated everywhere
```

### Proposed (Correct) Architecture

```
section_research
       ↓
[VALIDATE GATE]  ← Run BEFORE writer can proceed
  │
  ├─→ remove_invalid_sources (on 1-research/)
  │      - HTTP HEAD validation
  │      - Remove 404s/410s
  │      - Detect hallucination patterns
  │      - Remove in-text references/citations to any removed sources       
  │      - Call a reorder_citations agent on `1-research/` files
  │
  └─→ citation_validator (on 1-research/)
         - Format validation
         - Date consistency
         - Duplicate detection (duplicates are allowed and encouraged even in the text content, but not in the sources section at the bottom of the document)
         - Quality report
       ↓
writer (receives ONLY clean, validated research)
       ↓
... enrichment agents ...
       ↓
citation_assembly (consolidate and renumber)
```

### Execution Order Within the Gate

1. **remove_invalid_sources FIRST**
   - Removes obviously bad citations (404s, hallucination patterns)
   - Reduces noise for the validator

2. **reorder_citations SECOND** (called by remove_invalid_sources)
   - Renumbers citations to eliminate gaps
   - See detailed sequence below

3. **citation_validator THIRD**
   - Validates remaining citations (they should all be accessible)
   - Checks format, dates, duplicates
   - Generates quality report
   - If issues found, can block progression or flag for human review

### Detailed Removal and Renumbering Sequence

**Critical**: Removal and renumbering must be SEPARATE operations to avoid race conditions.

**Why separate?** If you try to renumber DURING removal:
- Remove `[^3]` definition
- Try to renumber `[^4]` → `[^3]`
- But you haven't removed `[^4]` inline refs yet
- Now `[^3]` appears twice with different meanings
- Chaos ensues

**Correct sequence within remove_invalid_sources:**

```
STEP 1: Identify invalid citations
  - HTTP HEAD validation on all URLs
  - Detect hallucination patterns (example.com, XXXXX, etc.)
  - Build list of citation numbers to remove (e.g., [^3], [^7])

STEP 2: Remove inline references
  - For each invalid citation number, remove ALL ` [^N]` in body text
  - This prevents orphaned references pointing to nothing

STEP 3: Remove citation definitions
  - Remove the `[^N]: ...` lines at bottom of document
  - File now has GAPS in numbering ([^1], [^2], [^4], [^5], [^6], [^8]...)

STEP 4: EXIT remove_invalid_sources
  - Do NOT renumber here - removal is complete
       ↓
STEP 5: Call reorder_citations (separate function)
  - Read file with gaps
  - Build renumbering map: [^4]→[^3], [^5]→[^4], [^6]→[^5], [^8]→[^6]...
  - Update ALL inline refs with new numbers (descending order to avoid conflicts)
  - Update ALL definitions with new numbers
  - File now SEQUENTIAL ([^1], [^2], [^3], [^4], [^5], [^6]...)
```

### reorder_citations vs citation_assembly

These are different tools for different purposes:

| Aspect | reorder_citations | citation_assembly |
|--------|------------------|-------------------|
| Scope | Single file | All sections |
| Purpose | Fix gaps after removal | Consolidate for final draft |
| Output | Same file, renumbered | Assembled final draft |
| When | After remove_invalid_sources | After all enrichment |
| Citations stay | In same file | Moved to ONE block at end |

**reorder_citations** (utility function):
- Works on ONE file at a time
- Keeps citations within that file
- Just renumbers to eliminate gaps
- Called by remove_invalid_sources after removal

**citation_assembly** (workflow agent):
- Works across ALL section files
- Consolidates ALL citations into ONE block
- Creates the final assembled draft
- Runs near end of pipeline

## Should One Agent Call the Other?

**Yes, but carefully.**

Option A: **citation_validator calls remove_invalid_sources internally**
- Pros: Single agent to invoke in workflow
- Cons: Brings back the "too much scope" problem

Option B: **Separate workflow nodes, sequential execution**
- Pros: Each agent stays focused
- Cons: Two nodes to manage in workflow

Option C: **Create a "research_validation_gate" composite agent**
- Calls remove_invalid_sources
- Then calls citation_validator
- Acts as a single gate in the workflow
- Each sub-agent stays focused on its task

**Recommendation: Option C** - A composite gate agent that orchestrates both, keeping each sub-agent focused while presenting a single interface to the workflow.

## CLI Usage

Both agents should be callable independently for human-triggered cleanup:

```bash
# Remove invalid sources from a specific output directory
python -m src.agents.remove_invalid_sources io/dark-matter/deals/ProfileHealth/outputs/ProfileHealth-v0.0.3

# Validate citations in a specific output directory
python -m src.agents.citation_validator io/dark-matter/deals/ProfileHealth/outputs/ProfileHealth-v0.0.3
```

This allows humans to:
1. Run cleanup on existing memos without regenerating
2. Validate research before manually editing
3. Fix citation issues discovered during review

## Key Principles

### 1. Validate at the Source
Don't let hallucinations propagate. Clean `1-research/` BEFORE the writer sees it.

### 2. Single Responsibility
Each agent does ONE thing well:
- `remove_invalid_sources`: Test URLs, remove failures
- `citation_validator`: Assess quality, report issues

### 3. Action Over Reporting
An agent that removes bad citations is more valuable than one that reports they exist.

### 4. Avoid Completion Bias
Don't run cleanup at the end of a long pipeline where the model feels pressure to "succeed". Run it early as a gate/checkpoint.

### 5. Human-Triggerable
Both agents should be callable from CLI for manual cleanup of existing content.

## Related Documents

- `context-vigilance/Faked-Sources-from-Perplexity.md` - Documents the hallucination problem
- `context-vigilance/An-Agent-should-Reorder-and-Organize-Citations-on-Assembly.md` - Citation assembly requirements
- `src/agents/remove_invalid_sources.py` - URL validation and removal agent
- `src/agents/citation_validator.py` - Citation quality assessment agent

## Implementation Status

- [x] `remove_invalid_sources` agent created
- [x] `citation_validator` agent exists (needs scope reduction?)
- [x] `citation_assembly` agent created (for final draft consolidation)
- [x] **Update `remove_invalid_sources` to remove inline refs when removing definitions**
- [x] **Create `reorder_citations_in_file()` utility function** (single-file renumbering)
- [x] **Create `reorder_directory_citations()` utility function** (directory-level renumbering)
- [x] **Have `remove_invalid_sources` call `reorder_*` after removal (two-pass approach)**
- [x] **Add CLI entry point for `remove_invalid_sources`**: `python -m src.agents.remove_invalid_sources <output_dir>`
- [x] **Move validation gate to BEFORE writer agent** - Added `cleanup_research` node in workflow.py
- [x] **Two-gate architecture implemented**:
  - GATE 1 (`cleanup_research`): After section_research, BEFORE writer - cleans 1-research/
  - GATE 2 (`cleanup_sections`): After revise_summaries, BEFORE assembly - cleans 2-sections/
- [ ] Add CLI entry point for `citation_validator`
- [ ] Create composite `research_validation_gate` agent (optional - may not be needed now)

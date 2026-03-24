# Ideal Information Hierarchy Applied to Markdown Headings

## Purpose

This document defines the heading hierarchy for all generated investment memos. The system supports 6 levels of headings (`#` through `######`), and each level has a specific role in the document structure. Agents must respect this hierarchy when writing, enriching, and assembling content.

## Heading Levels and Their Roles

| Level | Markdown | Role | Example |
|-------|----------|------|---------|
| h1 | `#` | Document title and top-level bookend sections | `# Solugen`, `# Executive Summary`, `# Closing Assessment` |
| h2 | `##` | Numbered content sections from the outline | `## 1. Capital Syndicate`, `## 5. Colossal Market Size` |
| h3 | `###` | Subsections within a content section | `### Lead Investors`, `### Competitive Differentiation` |
| h4 | `####` | Sub-subsections or detail groups | `#### Bull Case: Platform Scaling (25% probability)` |
| h5 | `#####` | Fine-grained detail points (rare) | `##### Key Metric Breakdown` |
| h6 | `######` | Lowest-level annotations (rare) | `###### Source Note` |

## Document Structure

```
# {Company Name}                          ← h1: document title (from header.md)
  **Investment Memo** | Prospective Analysis
  **Prepared by:** {firm}
  **Date:** {date}

  ---

# Executive Summary                       ← h1: bookend section (not numbered)
  [Prose summarizing the full memo]
  ### Scorecard Overview                   ← h3: scorecard nav table with anchor links
    [Table with scores and jump links]

## Table of Contents                       ← h2: navigation aid
  [Generated anchor links to all sections]

  ---

## 1. Capital Syndicate                    ← h2: numbered content section
  [Opening paragraph]
  ### Lead Investors                       ← h3: subsection
    [Detail]
  ### Institutional Depth                  ← h3: subsection
    [Detail]

## 2. Category Leadership                  ← h2: numbered content section
  ### Competitive Differentiation          ← h3: subsection
    #### Cell-Free vs. Fermentation        ← h4: sub-subsection
  ### Defensibility                        ← h3: subsection

...

## 7. Cash on Cash Return Probability      ← h2: numbered content section
  ### Return Scenarios                     ← h3: subsection
    #### Bull Case (25%)                   ← h4: scenario detail
    #### Base Case (50%)                   ← h4: scenario detail
    #### Bear Case (25%)                   ← h4: scenario detail
  ### Exit Landscape                       ← h3: subsection

## 8. Scorecard Evaluation                 ← h2: integrated scorecard
  ### Scorecard Summary                    ← h3: summary table
  ### 1. Capital Quality                   ← h3: dimension group
    #### Capital Syndicate -- 5/5          ← h4: individual dimension score
    #### Capital Efficiency -- 2/5         ← h4: individual dimension score
  ### Key Findings                         ← h3: strengths, concerns, diligence Qs

# Closing Assessment                       ← h1: bookend section (not numbered)
  [Synthesized recommendation]

[^1]: Citation 1...                        ← footnotes at end
[^2]: Citation 2...
```

## Rules for Each Agent

### Writer Agent (`src/agents/writer.py`)
- Writes section body content only -- no section header (added by `save_section_artifact`)
- Subsection headings should use `###` (h3) or lower
- If the LLM outputs `#` or `##` headings, they will be automatically demoted to `###` by `save_section_artifact`

### `save_section_artifact` (`src/artifacts.py`)
- Prepends the canonical `## {number}. {section_name}` header (h2)
- Strips any leading LLM heading that duplicates the section name
- Demotes all `#` and `##` headings in the body content to `###` to maintain hierarchy

### Revise Summary Sections (`src/agents/revise_summary_sections.py`)
- Writes `# Executive Summary` (h1) -- a bookend section, not a numbered content section
- Writes `# Closing Assessment` (h1) -- same treatment
- These are h1 because they frame the entire document, sitting at the same level as the document title

### Scorecard Navigator (`src/agents/scorecard_navigator.py`)
- Inserts `### Scorecard Overview` (h3) inside the Executive Summary
- The table lives within the h1 Executive Summary, so h3 is the correct subsection level

### TOC Generator (`src/agents/toc_generator.py`)
- Extracts h1, h2, and h3 headers for the table of contents
- Generates anchor links matching pandoc's slug algorithm
- Runs as the **final content step** in the workflow -- after all other agents have finished modifying content
- Only one TOC should exist in the final draft

### Scorecard Evaluator (`src/agents/scorecard_evaluator.py`)
- Output uses `#` for scorecard title, `##` for groups, `###` for dimensions
- When integrated into the memo (as section 8), the headings are demoted:
  - `#` title becomes the `## 8.` section header
  - `##` groups become `###`
  - `###` dimensions become `####`

### Citation Assembly (`src/agents/citation_assembly.py`)
- Assembles sections in file-sort order (`00-`, `01-`, `02-`, ... )
- Preserves heading levels as written in section files
- Does not modify heading hierarchy

## Why This Matters

1. **Export fidelity**: HTML and PDF exports rely on heading levels for styling, page breaks, and navigation. Incorrect levels produce flat, unreadable documents.
2. **TOC accuracy**: The TOC generator builds its tree from heading levels. If subsections are `##` instead of `###`, they appear as siblings of their parent section.
3. **Scorecard discoverability**: Investors need to find the scorecard quickly. Placing the overview table inside the Executive Summary at h3 ensures it appears in the TOC nested under the summary, not floating as a standalone section.
4. **Anchor link reliability**: Each heading generates an anchor slug. Duplicate heading text at the same level creates ambiguous anchors. Proper hierarchy avoids collisions.

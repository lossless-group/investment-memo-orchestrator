# Improving Memo Output: Section Improvement & Key Information Rewrite

**Status**: Implementation Plan
**Date**: 2025-11-20
**Author**: AI Labs Team
**Related**: Multi-Agent-Orchestration-for-Investment-Memo-Generation.md

---

## Executive Summary

This document specifies two complementary features for improving memo quality without regenerating entire memos:

1. **Section Improvement**: Enhance individual sections with better research and citations using Perplexity Sonar Pro
2. **Key Information Rewrite**: Correct crucial facts that appear across multiple sections (e.g., fund size, dates, names)

Both features leverage the section-by-section architecture introduced in the 2025-11-20 refactor, allowing targeted improvements while preserving the artifact trail.

---

## Problem Statement

### Current Limitations

**Issue #1: No Targeted Section Improvements**
- When one section is weak, users must regenerate the entire memo
- Full regeneration is expensive (10 LLM calls + research)
- Good sections may degrade during regeneration
- No way to iteratively improve specific sections

**Issue #2: No Global Fact Correction**
- Factual errors often appear in multiple sections
- Example: Avalanche memo states "$50M fund" in 7 different sections, but actual size is "$10M"
- Manually editing each section is error-prone
- Citations may reference the wrong information

### Requirements

**Feature #1 Requirements**:
- Improve a single section without touching others
- Use Perplexity Sonar Pro for real-time research
- Add citations automatically during improvement
- Preserve existing artifact structure
- Allow reassembly of final draft

**Feature #2 Requirements**:
- Identify all sections affected by a correction
- Apply corrections consistently across sections
- Preserve citations and formatting
- Update research data if needed
- Reassemble final draft automatically

---

## Feature #1: Section Improvement with Sonar Pro

### Current Implementation Review

**Existing File**: `improve-section.py` (created 2025-11-18)

**Current Behavior**:
- Loads artifacts (state, research, other sections)
- Uses Claude to improve section content
- Saves to `2-sections/` directory
- **Missing**: Citations must be added separately

**What Exists**:
```python
def improve_section_with_agent(
    section_name: str,
    artifacts: dict,
    artifact_dir: Path,
    console: Console
) -> str:
    """Use agents to improve or create a specific section."""
    # Uses ChatAnthropic (Claude)
    # Does NOT add citations
    # Requires separate citation enrichment step
```

**What's Needed**:
- Replace Claude with Perplexity Sonar Pro
- Citations added during improvement (not after)
- One-step process instead of two-step

---

### Target Architecture

**Improved Function**:
```python
def improve_section_with_sonar_pro(
    section_name: str,
    artifacts: dict,
    artifact_dir: Path,
    console: Console
) -> str:
    """Use Perplexity Sonar Pro to improve section with citations."""
    from openai import OpenAI

    # Initialize Perplexity client
    perplexity_client = OpenAI(
        api_key=os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai"
    )

    # Build comprehensive improvement prompt
    prompt = build_improvement_prompt(
        section_name=section_name,
        existing_content=artifacts["sections"].get(section_file, ""),
        company_name=artifacts["state"]["company_name"],
        research_data=artifacts["research"],
        other_sections=artifacts["sections"],
        investment_type=artifacts["state"]["investment_type"],
        memo_mode=artifacts["state"]["memo_mode"]
    )

    # Call Sonar Pro with improvement + citation instructions
    response = perplexity_client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": prompt}]
    )

    improved_content = response.choices[0].message.content

    # Save improved section
    save_section_artifact(artifact_dir, section_num, section_name, improved_content)

    return improved_content
```

---

### Prompt Design

**Sonar Pro Improvement Prompt Structure**:

```markdown
You are improving the '{section_name}' section for an investment memo about {company_name}.

INVESTMENT TYPE: {investment_type.upper()}
MEMO MODE: {memo_mode.upper()} ({'retrospective justification' if justify else 'prospective analysis'})

CURRENT SECTION CONTENT:
{existing_content}

RESEARCH DATA AVAILABLE:
{research_data_json}

CONTEXT FROM OTHER SECTIONS:
{other_sections_summary}

TASK: Significantly improve this section by:
1. Adding specific metrics and data from authoritative sources
2. Removing vague or speculative language ("could potentially", "might be", etc.)
3. Strengthening analysis with concrete evidence
4. Adding inline citations [^1], [^2], [^3] for ALL factual claims
5. Including a comprehensive Citations section at the end

REQUIREMENTS:
- Use Obsidian-style citations: [^1], [^2], etc.
- Place citations AFTER punctuation: "text. [^1]" not "text[^1]."
- Always include ONE SPACE before each citation: "text. [^1] [^2]"
- Use quality sources:
  * Company websites, blogs, press releases
  * TechCrunch, The Information, Sifted, Protocol, Axios
  * Crunchbase, PitchBook (for funding data)
  * SEC filings, investor letters
  * Industry analyst reports (Gartner, CB Insights, McKinsey)
  * Bloomberg, Reuters, WSJ, FT (for news)
- Match the analytical tone of professional VC memos
- Be specific, not promotional or dismissive
- For {memo_mode} mode: {'justify the investment decision' if justify else 'objectively assess'}

CITATION FORMAT:
[^1]: YYYY, MMM DD. [Source Title](https://full-url-here.com). Publisher Name. Published: YYYY-MM-DD | Updated: YYYY-MM-DD

IMPROVED SECTION CONTENT:
```

**Key Differences from Citation Enrichment Agent**:
- **Citation Enrichment**: Preserves narrative, only adds citations
- **Section Improvement**: Rewrites for quality AND adds citations
- Both use same citation format (Obsidian-style)

---

### CLI Interface

**Usage**:
```bash
# Activate venv first (recommended)
source .venv/bin/activate

# Basic usage: improve section
python improve-section.py "Avalanche" "Team"

# Specify version
python improve-section.py "Avalanche" "Team" --version v0.0.1

# With final draft reassembly
python improve-section.py "Avalanche" "Team" --rebuild-final

# Direct path to artifact directory
python improve-section.py output/Avalanche-v0.0.1 "Market Context"
```

**New Flags**:
- `--rebuild-final`: Reassemble `4-final-draft.md` after improvement
- `--preview`: Show before/after comparison without saving

**Output**:
```
✓ Loading artifacts from: output/Avalanche-v0.0.1/
✓ Loaded state.json
✓ Loaded research data
✓ Loaded 10 existing sections

🔧 Improving section: Team
  Using Perplexity Sonar Pro for real-time research...

✓ Section improved with 8 new citations added
✓ Saved to: output/Avalanche-v0.0.1/2-sections/04-team.md

📊 Changes Summary:
  - Original length: 850 words
  - Improved length: 1,200 words
  - Citations added: 8
  - Vague claims removed: 5
  - Specific metrics added: 12

✓ Reassembled final draft: 4-final-draft.md

Next steps:
  1. Review improved section in: output/Avalanche-v0.0.1/2-sections/
  2. Export to HTML: python export-branded.py output/Avalanche-v0.0.1/4-final-draft.md
```

---

### Implementation Steps

#### Step 1: Update `improve-section.py` for Sonar Pro

**Files Modified**:
- `improve-section.py`

**Changes**:
1. Replace `improve_section_with_agent()` with `improve_section_with_sonar_pro()`
2. Import OpenAI client for Perplexity
3. Update prompt to include citation instructions
4. Test with PERPLEXITY_API_KEY

**Testing**:
```bash
# Test on weak section
python improve-section.py "Avalanche" "Team" --version v0.0.1

# Verify:
# - Section has inline citations [^1], [^2]
# - Citations section at end with URLs
# - Content quality improved
# - Vague language removed
```

#### Step 2: Add Reassembly Feature

**Changes**:
1. Add `--rebuild-final` flag
2. Implement `reassemble_final_draft()` function:
   - Load header.md if exists
   - Load all sections from 2-sections/ in order
   - Concatenate with proper spacing
   - Save as 4-final-draft.md

**Code**:
```python
def reassemble_final_draft(artifact_dir: Path, console: Console):
    """Reassemble 4-final-draft.md from section files."""
    console.print("\n[bold]Reassembling final draft...[/bold]")

    # Load header if exists
    header_file = artifact_dir / "header.md"
    if header_file.exists():
        with open(header_file) as f:
            content = f.read() + "\n"
    else:
        content = ""

    # Load sections in order
    sections_dir = artifact_dir / "2-sections"
    section_files = sorted(sections_dir.glob("*.md"))

    for section_file in section_files:
        with open(section_file) as f:
            content += f.read() + "\n\n"

    # Save final draft
    final_draft = artifact_dir / "4-final-draft.md"
    with open(final_draft, "w") as f:
        f.write(content.strip())

    console.print(f"[green]✓ Final draft reassembled:[/green] {final_draft}")
```

#### Step 3: Add Before/After Comparison

**Changes**:
1. Add `--preview` flag
2. Show diff before saving
3. Require confirmation

**Output Example**:
```
📊 Section Improvement Preview:

BEFORE (850 words):
  "The team has extensive experience in the industry..."

AFTER (1,200 words):
  "The founding team brings 40+ years of combined experience. [^1]

   CEO Jane Doe previously scaled Acme Corp from $5M to $150M ARR
   over 6 years (2015-2021). [^2] CTO John Smith led engineering at..."

Changes:
  ✓ Removed 5 vague claims
  ✓ Added 12 specific metrics
  ✓ Added 8 citations
  ✓ Increased depth by 41%

Save improved section? [y/N]:
```

#### Step 4: Error Handling & Edge Cases

**Handle**:
- Missing PERPLEXITY_API_KEY
- Invalid section names
- Missing artifact directories
- Network errors during API calls
- Malformed citations in response

**Code**:
```python
def validate_environment():
    """Check required environment variables."""
    if not os.getenv("PERPLEXITY_API_KEY"):
        console.print("[red]Error: PERPLEXITY_API_KEY not set[/red]")
        console.print("[yellow]Set it in .env file or export it[/yellow]")
        sys.exit(1)

def validate_section_name(section_name: str) -> bool:
    """Validate section name against known sections."""
    if section_name not in SECTION_MAP:
        console.print(f"[red]Error: Unknown section '{section_name}'[/red]")
        console.print("\n[yellow]Available sections:[/yellow]")
        for name in sorted(SECTION_MAP.keys()):
            console.print(f"  • {name}")
        return False
    return True
```

#### Step 5: Documentation & Testing

**Update Files**:
- `CLAUDE.md`: Add Section Improvement section
- `README.md`: Add to "Remaining Enhancements" → "Completed"
- Create examples in `docs/EXAMPLES.md`

**Test Cases**:
1. ✅ Improve existing weak section
2. ✅ Create missing section from scratch
3. ✅ Handle section with existing citations (preserve them)
4. ✅ Error: Invalid section name
5. ✅ Error: Missing artifacts
6. ✅ Reassemble final draft after improvement

---

## Feature #2: Key Information Rewrite Agent

### Use Cases

**Scenario 1: Fund Size Correction**
- **Error**: Memo states "$50M fund" in 7 sections
- **Correction**: Actual size is "$10M"
- **Impact**: Affects deployment strategy, check sizes, portfolio construction, economics

**Scenario 2: Person Title Correction**
- **Error**: "Katelyn Donnelly, Partner at Avalanche"
- **Correction**: "Katelyn Donnelly, Managing Partner and Founder at Avalanche"
- **Impact**: Affects GP Background, Track Record, decision-making authority

**Scenario 3: Date Correction**
- **Error**: "Company founded in 2020"
- **Correction**: "Company founded in 2019"
- **Impact**: Affects traction timeline, milestones, growth metrics

**Scenario 4: Investment Stage Correction**
- **Error**: "Series B company"
- **Correction**: "Series A company"
- **Impact**: Affects valuation expectations, metrics benchmarks, competitive positioning

---

### Architecture Design

**New Agent**: `src/agents/key_info_rewrite.py`

**Agent Function**:
```python
def key_information_rewrite_agent(state: MemoState) -> dict:
    """
    Correct crucial information that affects multiple sections.

    Args:
        state: Must contain:
            - correction_instruction: str
              Example: "The fund size is $10M, not $50M"
            - company_name: str
            - latest_output_dir: Path (optional, auto-detected if not provided)

    Process:
        1. Load final draft from latest version
        2. Analyze correction to identify affected sections
        3. For each affected section:
            a. Load section file from 2-sections/
            b. Apply correction via LLM
            c. Preserve citations and formatting
            d. Save corrected section
        4. Reassemble final draft
        5. Update metadata

    Returns:
        {
            "sections_corrected": int,
            "instances_found": int,
            "files_updated": List[str],
            "messages": List[str]
        }
    """
```

---

### Correction Analysis Algorithm

**Phase 1: Parse Correction Instruction**

```python
def analyze_correction(instruction: str, company_name: str) -> CorrectionAnalysis:
    """
    Use LLM to understand correction and identify search terms.

    Returns:
        CorrectionAnalysis:
            - incorrect_info: str ("$50M")
            - correct_info: str ("$10M")
            - semantic_variations: List[str] (["fifty million", "Fund II size", "10M fund"])
            - affected_section_types: List[str] (["Fund Strategy", "Economics", "Portfolio"])
    """

    analysis_prompt = f"""Analyze this correction instruction for {company_name}:

INSTRUCTION: {instruction}

TASK: Extract structured information:
1. What information is INCORRECT?
2. What is the CORRECT information?
3. What semantic variations might appear? (paraphrases, related concepts)
4. Which section types are likely affected?

Return JSON:
{{
    "incorrect_info": "exact text",
    "correct_info": "exact text",
    "semantic_variations": ["variant1", "variant2"],
    "affected_section_types": ["section name 1", "section name 2"]
}}
"""

    # Call Claude for analysis
    response = anthropic_client.invoke(analysis_prompt)
    return CorrectionAnalysis.parse(response.content)
```

**Phase 2: Identify Affected Sections**

```python
def identify_affected_sections(
    correction_analysis: CorrectionAnalysis,
    artifact_dir: Path
) -> List[SectionInfo]:
    """
    Scan all section files to find which ones contain the error.

    Returns:
        List of SectionInfo:
            - section_name: str
            - section_file: Path
            - instances_found: int
            - sample_text: str (preview of error)
    """

    affected_sections = []
    sections_dir = artifact_dir / "2-sections"

    for section_file in sections_dir.glob("*.md"):
        with open(section_file) as f:
            content = f.read()

        # Check for exact match
        exact_count = content.count(correction_analysis.incorrect_info)

        # Check for semantic variations
        variation_count = 0
        for variation in correction_analysis.semantic_variations:
            variation_count += content.lower().count(variation.lower())

        total_instances = exact_count + variation_count

        if total_instances > 0:
            affected_sections.append(SectionInfo(
                section_name=extract_section_name(section_file),
                section_file=section_file,
                instances_found=total_instances,
                sample_text=extract_sample(content, correction_analysis.incorrect_info)
            ))

    return affected_sections
```

**Phase 3: Apply Correction to Each Section**

```python
def correct_section(
    section_file: Path,
    correction_analysis: CorrectionAnalysis,
    other_sections_context: str,
    company_name: str
) -> str:
    """
    Use LLM to apply correction while preserving formatting and citations.
    """

    with open(section_file) as f:
        original_content = f.read()

    correction_prompt = f"""You are correcting a factual error in an investment memo section.

COMPANY: {company_name}

CORRECTION REQUIRED:
  Incorrect: {correction_analysis.incorrect_info}
  Correct: {correction_analysis.correct_info}

CONTEXT FROM OTHER SECTIONS:
{other_sections_context}

CURRENT SECTION CONTENT:
{original_content}

TASK:
1. Find ALL instances of the incorrect information (including paraphrases)
2. Replace with the correct information
3. Ensure consistency throughout the section
4. Update any dependent claims (e.g., if fund size changes, check sizes may change)
5. Preserve ALL citations - do not remove or modify them
6. Preserve all formatting (headers, lists, emphasis)
7. Do NOT change other content unrelated to the correction

CRITICAL:
- If a claim becomes unsupported after correction, flag it with [NEEDS CITATION]
- Maintain the analytical tone and depth
- Return ONLY the corrected section content

CORRECTED SECTION:
"""

    # Call Claude
    response = anthropic_client.invoke(correction_prompt)
    corrected_content = response.content

    # Save corrected section
    with open(section_file, "w") as f:
        f.write(corrected_content)

    return corrected_content
```

**Phase 4: Reassemble Final Draft**

```python
def reassemble_after_correction(artifact_dir: Path) -> Path:
    """Reassemble 4-final-draft.md after corrections."""

    # Same logic as Feature #1 reassembly
    content = ""

    # Load header
    header_file = artifact_dir / "header.md"
    if header_file.exists():
        with open(header_file) as f:
            content = f.read() + "\n"

    # Load all sections in order
    sections_dir = artifact_dir / "2-sections"
    for section_file in sorted(sections_dir.glob("*.md")):
        with open(section_file) as f:
            content += f.read() + "\n\n"

    # Save final draft
    final_draft = artifact_dir / "4-final-draft.md"
    with open(final_draft, "w") as f:
        f.write(content.strip())

    return final_draft
```

---

### CLI Interface

**Standalone Script**: `rewrite-key-info.py`

**Usage**:
```bash
# Activate venv first
source .venv/bin/activate

# Basic correction
python rewrite-key-info.py "Avalanche" \
  --correction "The fund size is $10M, not $50M"

# Specify version
python rewrite-key-info.py "Avalanche" \
  --correction "Katelyn Donnelly is Managing Partner, not Partner" \
  --version v0.0.1

# Direct path
python rewrite-key-info.py output/Avalanche-v0.0.1 \
  --correction "Company founded in 2019, not 2020"

# Preview mode (don't save)
python rewrite-key-info.py "Avalanche" \
  --correction "Series A, not Series B" \
  --preview

# Update research data too (deep mode)
python rewrite-key-info.py "Avalanche" \
  --correction "Fund size is $10M" \
  --update-research
```

**Output Example**:
```
🔍 Analyzing correction...
  Incorrect: "$50M"
  Correct: "$10M"
  Semantic variations: "fifty million", "Fund II target", "target size"

🔎 Scanning sections...
  ✓ Found errors in 7/10 sections:
    • Fund Strategy & Thesis (3 instances)
    • Portfolio Construction (2 instances)
    • Fee Structure & Economics (4 instances)
    • Value Add & Differentiation (1 instance)
    • Track Record Analysis (2 instances)
    • Risks & Mitigations (1 instance)
    • Executive Summary (2 instances)

📝 Applying corrections...
  ✓ Corrected: Fund Strategy & Thesis
  ✓ Corrected: Portfolio Construction
  ✓ Corrected: Fee Structure & Economics
  ✓ Corrected: Value Add & Differentiation
  ✓ Corrected: Track Record Analysis
  ✓ Corrected: Risks & Mitigations
  ✓ Corrected: Executive Summary

✅ Reassembled final draft

📊 Correction Summary:
  Sections modified: 7/10
  Total instances corrected: 15
  Files updated:
    • 2-sections/03-fund-strategy--thesis.md
    • 2-sections/04-portfolio-construction.md
    • 2-sections/07-fee-structure--economics.md
    • 2-sections/05-value-add--differentiation.md
    • 2-sections/06-track-record-analysis.md
    • 2-sections/08-risks--mitigations.md
    • 2-sections/01-executive-summary.md
    • 4-final-draft.md

Next steps:
  1. Review corrections in: output/Avalanche-v0.0.1/
  2. Export to HTML: python export-branded.py output/Avalanche-v0.0.1/4-final-draft.md
  3. Create new version: python -m src.main "Avalanche" --version-only
```

---

### Implementation Steps

#### Step 1: Create Agent Core

**New File**: `src/agents/key_info_rewrite.py`

**Implement**:
1. `analyze_correction()` - Parse correction instruction
2. `identify_affected_sections()` - Scan for errors
3. `correct_section()` - Apply correction
4. `reassemble_after_correction()` - Rebuild final draft
5. `key_information_rewrite_agent()` - Main agent function

**Testing**:
```python
# Unit test
def test_analyze_correction():
    result = analyze_correction(
        "Fund size is $10M, not $50M",
        "Avalanche"
    )
    assert result.incorrect_info == "$50M"
    assert result.correct_info == "$10M"
    assert "fifty million" in result.semantic_variations
```

#### Step 2: Create CLI Script

**New File**: `rewrite-key-info.py`

**Structure**:
```python
#!/usr/bin/env python3
"""
Correct crucial information that affects multiple memo sections.

USAGE:
    python rewrite-key-info.py "Company" --correction "Fund size is $10M, not $50M"
"""

import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from src.agents.key_info_rewrite import key_information_rewrite_agent
from src.utils import get_latest_output_dir

def main():
    parser = argparse.ArgumentParser(description="Correct key information across memo")
    parser.add_argument("target", help="Company name or path to artifact directory")
    parser.add_argument("--correction", required=True, help="Correction instruction")
    parser.add_argument("--version", help="Specific version (default: latest)")
    parser.add_argument("--preview", action="store_true", help="Preview without saving")
    parser.add_argument("--update-research", action="store_true", help="Update research data too")

    args = parser.parse_args()

    # ... implementation ...
```

#### Step 3: State Schema Updates

**Update**: `src/state.py`

**Add Field**:
```python
class MemoState(TypedDict):
    # ... existing fields ...

    # NEW: For key information corrections
    correction_instruction: NotRequired[str]
    correction_metadata: NotRequired[Dict[str, Any]]  # Track what was corrected
```

#### Step 4: Workflow Integration (Optional)

**Update**: `src/workflow.py`

**Add Conditional Node**:
```python
def build_workflow():
    workflow = StateGraph(MemoState)

    # ... existing nodes ...

    # NEW: Optional correction node
    workflow.add_node("correct_key_info", key_information_rewrite_agent)

    # Conditional routing
    def should_correct(state: MemoState) -> str:
        if state.get("correction_instruction"):
            return "correct_key_info"
        return "continue"

    workflow.add_conditional_edges(
        "validate",
        should_correct,
        {
            "correct_key_info": "finalize",
            "continue": "finalize"
        }
    )
```

**CLI Support**:
```bash
# Run memo generation with correction
python -m src.main "Avalanche" --correct "Fund size is $10M, not $50M"
```

#### Step 5: Handle Edge Cases

**Scenarios**:
1. **No instances found**: Warn user, don't modify anything
2. **Conflicting citations**: Flag sections that need manual review
3. **Dependent claims**: Identify claims that may be affected
4. **Research data conflicts**: Warn if correction contradicts research

**Code**:
```python
def validate_correction_safety(
    correction_analysis: CorrectionAnalysis,
    affected_sections: List[SectionInfo],
    research_data: dict
) -> List[str]:
    """Check for potential issues before applying correction."""

    warnings = []

    # No instances found
    if not affected_sections:
        warnings.append("⚠️  No instances of incorrect information found")

    # Check research data conflicts
    research_text = str(research_data)
    if correction_analysis.incorrect_info in research_text:
        warnings.append(
            "⚠️  Research data contains the incorrect information. "
            "Consider using --update-research flag."
        )

    # Check for many instances (may indicate systemic issue)
    total_instances = sum(s.instances_found for s in affected_sections)
    if total_instances > 20:
        warnings.append(
            f"⚠️  Found {total_instances} instances across {len(affected_sections)} sections. "
            "This may indicate a deeper issue. Review carefully after correction."
        )

    return warnings
```

#### Step 6: Research Data Updates (--update-research)

**If Flag Set**:
```python
def update_research_data(
    artifact_dir: Path,
    correction_analysis: CorrectionAnalysis
) -> None:
    """Update research.json with corrected information."""

    research_file = artifact_dir / "1-research.json"
    if not research_file.exists():
        return

    with open(research_file) as f:
        research_data = json.load(f)

    # Apply correction to research data fields
    research_json = json.dumps(research_data)
    corrected_json = research_json.replace(
        correction_analysis.incorrect_info,
        correction_analysis.correct_info
    )
    research_data = json.loads(corrected_json)

    # Save updated research
    with open(research_file, "w") as f:
        json.dump(research_data, f, indent=2)

    # Also update 1-research.md
    research_md = artifact_dir / "1-research.md"
    if research_md.exists():
        with open(research_md) as f:
            content = f.read()

        corrected_content = content.replace(
            correction_analysis.incorrect_info,
            correction_analysis.correct_info
        )

        with open(research_md, "w") as f:
            f.write(corrected_content)
```

#### Step 7: Testing & Validation

**Test Suite**:
1. ✅ Simple correction (fund size)
2. ✅ Complex correction (person title + role)
3. ✅ Date correction with timeline impact
4. ✅ Multiple semantic variations
5. ✅ Correction with citation conflicts
6. ✅ No instances found (error case)
7. ✅ Preview mode
8. ✅ Research data update

**Manual Testing Checklist**:
- [ ] Run on Avalanche $50M → $10M
- [ ] Verify all 7 sections corrected
- [ ] Check citations preserved
- [ ] Verify formatting maintained
- [ ] Review reassembled final draft
- [ ] Export to HTML and verify
- [ ] Test with --update-research flag
- [ ] Test with --preview flag

#### Step 8: Documentation

**Update Files**:
1. `CLAUDE.md`: Add Key Information Rewrite section
2. `README.md`: Move to "Completed" ✅
3. Create `docs/CORRECTIONS.md`: Guide with examples
4. Add examples to `docs/EXAMPLES.md`

**Documentation Structure**:
```markdown
# Key Information Rewrite Guide

## When to Use

Use key information rewrite when:
- A crucial fact appears in multiple sections
- The error affects related claims (e.g., fund size affects check sizes)
- Manual editing would be error-prone

Do NOT use when:
- Error is in only one section (use improve-section.py instead)
- You want to rephrase content (use improve-section.py)
- You need to add new information (use improve-section.py or regenerate)

## Common Scenarios

### Fund Size Correction
...

### Person Title/Role Correction
...

### Date/Timeline Correction
...

### Investment Stage Correction
...
```

---

## Implementation Roadmap

### Step 1: Feature #1 - Sonar Pro Integration

**Objective**: Update improve-section.py to use Perplexity Sonar Pro for one-step improvements with citations

**Tasks**:
- [ ] Replace Claude with Sonar Pro in improve_section_with_agent()
- [ ] Update prompt to include citation instructions
- [ ] Test on Avalanche Team section
- [ ] Verify citations properly formatted
- [ ] Compare quality to Claude-only approach

**Deliverables**:
- Updated `improve-section.py`
- Test results document
- Before/after comparison

---

### Step 2: Feature #1 - Reassembly

**Objective**: Add ability to reassemble final draft after section improvement

**Tasks**:
- [ ] Implement reassemble_final_draft() function
- [ ] Add --rebuild-final flag
- [ ] Test reassembly on improved sections
- [ ] Verify formatting preserved

**Deliverables**:
- Working reassembly feature
- Updated CLI help text

---

### Step 3: Feature #1 - Before/After Preview

**Objective**: Show improvements before applying

**Tasks**:
- [ ] Add --preview flag
- [ ] Implement diff display
- [ ] Add confirmation prompt
- [ ] Show metrics (word count, citations, etc.)

**Deliverables**:
- Preview mode implementation
- User-friendly diff output

---

### Step 4: Feature #1 - Documentation & Testing

**Objective**: Document Feature #1 and complete testing

**Tasks**:
- [ ] Test on 5 different sections from different memos
- [ ] Handle edge cases (missing API key, invalid sections)
- [ ] Update CLAUDE.md with examples
- [ ] Update README.md
- [ ] Mark as complete ✅

**Deliverables**:
- Test results for 5 memos
- Updated documentation
- Feature marked complete

---

### Step 5: Feature #2 - Agent Core

**Objective**: Create key_info_rewrite agent with correction logic

**Tasks**:
- [ ] Create src/agents/key_info_rewrite.py
- [ ] Implement analyze_correction()
- [ ] Implement identify_affected_sections()
- [ ] Implement correct_section()
- [ ] Write unit tests

**Deliverables**:
- Working agent module
- Unit tests passing

---

### Step 6: Feature #2 - CLI Script

**Objective**: Create standalone CLI for key information corrections

**Tasks**:
- [ ] Create rewrite-key-info.py
- [ ] Implement argument parsing
- [ ] Add preview mode
- [ ] Implement reassembly
- [ ] Add rich console output

**Deliverables**:
- Working CLI script
- Help documentation

---

### Step 7: Feature #2 - Research Data Updates

**Objective**: Add deep mode to update research artifacts

**Tasks**:
- [ ] Implement --update-research flag
- [ ] Update 1-research.json
- [ ] Update 1-research.md
- [ ] Test with research data conflicts

**Deliverables**:
- Research update feature
- Conflict detection warnings

---

### Step 8: Feature #2 - Testing & Validation

**Objective**: Comprehensive testing of correction feature

**Tasks**:
- [ ] Test on Avalanche $50M → $10M
- [ ] Test person title correction
- [ ] Test date correction
- [ ] Test with semantic variations
- [ ] Test preview mode
- [ ] Test research updates
- [ ] Handle edge cases

**Deliverables**:
- Test results for all scenarios
- Edge case handling
- Bug fixes

---

### Step 9: Feature #2 - Workflow Integration (Optional)

**Objective**: Allow corrections during memo generation workflow

**Tasks**:
- [ ] Update MemoState schema
- [ ] Add conditional routing in workflow
- [ ] Add --correct flag to main CLI
- [ ] Test integrated workflow

**Deliverables**:
- Workflow integration
- Updated CLI interface

---

### Step 10: Documentation & Examples

**Objective**: Complete documentation for both features

**Tasks**:
- [ ] Create docs/CORRECTIONS.md guide
- [ ] Add examples to docs/EXAMPLES.md
- [ ] Update CLAUDE.md comprehensively
- [ ] Update README.md
- [ ] Mark both features complete ✅

**Deliverables**:
- Complete documentation
- Usage examples
- Features marked complete in README

---

## Success Criteria

### Feature #1: Section Improvement

**Must Have**:
- ✅ Uses Perplexity Sonar Pro (not Claude)
- ✅ Citations added during improvement (not after)
- ✅ Obsidian-style citation format
- ✅ Preserves artifact structure
- ✅ Can reassemble final draft
- ✅ Error handling for missing API keys

**Nice to Have**:
- ✅ Before/after preview mode
- ✅ Word count and quality metrics
- ✅ Comparison with original section

### Feature #2: Key Information Rewrite

**Must Have**:
- ✅ Identifies all affected sections
- ✅ Applies corrections consistently
- ✅ Preserves citations and formatting
- ✅ Reassembles final draft automatically
- ✅ Shows summary of changes

**Nice to Have**:
- ✅ Updates research data (--update-research)
- ✅ Preview mode before applying
- ✅ Semantic variation detection
- ✅ Workflow integration

---

## Technical Considerations

### API Costs

**Feature #1 (Sonar Pro per section)**:
- Cost: ~$0.50-1.00 per section improvement
- Context: ~5k chars in, ~7k chars out
- Model: sonar-pro

**Feature #2 (Corrections)**:
- Analysis: 1 Claude call (~$0.01)
- Per section: 1 Claude call (~$0.05)
- Total for 7 sections: ~$0.36
- Model: claude-sonnet-4-5

**Comparison to Full Regeneration**:
- Full regeneration: 10 sections × $1.00 = $10.00
- Section improvement: 1 section × $0.75 = $0.75 (13× cheaper)
- Key correction: 7 sections × $0.05 = $0.35 (29× cheaper)

### Performance

**Feature #1**:
- Time: ~30-60 seconds per section (Sonar Pro call)
- Parallel: Not applicable (one section at a time)

**Feature #2**:
- Analysis: ~5 seconds
- Section scanning: ~1 second
- Correction per section: ~10-15 seconds
- Total for 7 sections: ~90 seconds (vs. 10+ minutes for full regeneration)

### Rate Limits

**Perplexity Sonar Pro**:
- Rate limit: 50 requests/minute
- Constraint: None (processing one section at a time)

**Anthropic Claude**:
- Rate limit: 50 requests/minute
- Constraint: None for corrections (max ~10 sections)

---

## Monitoring & Quality Assurance

### Metrics to Track

**Feature #1**:
- Sections improved per week
- Average quality improvement (word count, citations added)
- User satisfaction (manual review scores)
- Time saved vs. full regeneration

**Feature #2**:
- Corrections performed per week
- Average sections affected per correction
- Accuracy (manual review of corrections)
- Time saved vs. manual editing

### Quality Checks

**Pre-Deployment**:
- [ ] Test both features on 5 real memos
- [ ] Manual review of outputs
- [ ] Verify citations preserved
- [ ] Check formatting maintained

**Post-Deployment**:
- [ ] Monitor error rates
- [ ] Collect user feedback
- [ ] Review edge cases
- [ ] Iterate on prompts

---

## Future Enhancements

### Feature #1 Extensions

**Batch Improvements**:
```bash
# Improve multiple sections at once
python improve-section.py "Avalanche" --sections "Team,Market Context,Technology"
```

**Comparative Mode**:
```bash
# Compare section across versions
python improve-section.py "Avalanche" --compare v0.0.1 v0.0.2 --section "Team"
```

**Auto-Improve**:
```bash
# Automatically improve sections scoring < 7/10
python improve-section.py "Avalanche" --auto-improve --threshold 7
```

### Feature #2 Extensions

**Multiple Corrections**:
```bash
# Apply multiple corrections at once
python rewrite-key-info.py "Avalanche" \
  --corrections corrections.json
```

**Validation Mode**:
```bash
# Validate consistency across sections
python rewrite-key-info.py "Avalanche" --validate
```

**Rollback Support**:
```bash
# Undo last correction
python rewrite-key-info.py "Avalanche" --rollback
```

---

## Related Documentation

- `Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` - Main architecture
- `changelog/2025-11-20_01.md` - Section-by-section processing refactor
- `CLAUDE.md` - Developer guide
- `README.md` - User guide

---

## Changelog

**2025-11-20**: Document created with comprehensive implementation plan for both features

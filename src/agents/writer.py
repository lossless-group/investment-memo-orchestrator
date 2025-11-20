"""
Writer Agent - Drafts investment memo sections following Hypernova format.

This agent is responsible for transforming research data into well-written
memo sections that follow the Hypernova style guide and template structure.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import os
from pathlib import Path
from typing import Dict, Any

from ..state import MemoState, SectionDraft
from ..artifacts import sanitize_filename, save_section_artifact
from ..versioning import VersionManager
import re


def load_template(investment_type: str = "direct") -> str:
    """
    Load the appropriate memo template based on investment type.

    Args:
        investment_type: "direct" for startup investments, "fund" for LP commitments

    Returns:
        Template markdown content
    """
    templates_dir = Path(__file__).parent.parent.parent / "templates"

    if investment_type == "fund":
        template_path = templates_dir / "memo-template-fund.md"
    else:
        template_path = templates_dir / "memo-template-direct.md"

    # Fallback to original template if specific one doesn't exist
    if not template_path.exists():
        template_path = templates_dir / "memo-template.md"

    with open(template_path, "r") as f:
        return f.read()


def load_style_guide() -> str:
    """Load the style guide from file."""
    style_guide_path = Path(__file__).parent.parent.parent / "templates" / "style-guide.md"
    with open(style_guide_path, "r") as f:
        return f.read()


def parse_memo_sections(memo_content: str) -> Dict[str, str]:
    """
    Parse memo into individual sections.

    Args:
        memo_content: Full memo markdown content

    Returns:
        Dictionary mapping section names to content
    """
    sections = {}

    # Define the 10 expected sections with their markdown headers
    section_patterns = [
        (1, r"##\s*1\.\s*Executive Summary", "Executive Summary"),
        (2, r"##\s*2\.\s*Business Overview", "Business Overview"),
        (3, r"##\s*3\.\s*Market Context", "Market Context"),
        (4, r"##\s*4\.\s*Technology & Product", "Technology & Product"),
        (5, r"##\s*5\.\s*Traction & Milestones", "Traction & Milestones"),
        (6, r"##\s*6\.\s*Team", "Team"),
        (7, r"##\s*7\.\s*Funding & Terms", "Funding & Terms"),
        (8, r"##\s*8\.\s*Risks & Mitigations", "Risks & Mitigations"),
        (9, r"##\s*9\.\s*Investment Thesis", "Investment Thesis"),
        (10, r"##\s*10\.\s*Recommendation", "Recommendation"),
    ]

    # Split content by section headers
    for i, (num, pattern, name) in enumerate(section_patterns):
        # Find start of this section
        match = re.search(pattern, memo_content, re.IGNORECASE)
        if not match:
            continue

        start_pos = match.end()

        # Find start of next section (or end of document)
        if i + 1 < len(section_patterns):
            next_pattern = section_patterns[i + 1][1]
            next_match = re.search(next_pattern, memo_content[start_pos:], re.IGNORECASE)
            if next_match:
                end_pos = start_pos + next_match.start()
            else:
                end_pos = len(memo_content)
        else:
            end_pos = len(memo_content)

        # Extract section content
        section_content = memo_content[start_pos:end_pos].strip()
        sections[name] = section_content

    return sections


# System prompt for Writer Agent (template/style guide will be appended at runtime)
WRITER_SYSTEM_PROMPT_BASE = """You are an investment analyst writing memos for Hypernova Capital.

Your task is to transform research data into a complete, well-structured investment memo
that follows Hypernova's format and style guidelines.

KEY WRITING PRINCIPLES:
1. Analytical, not promotional tone
2. Specific metrics over vague claims (use exact numbers, dates, names)
3. Balanced perspective (acknowledge risks alongside opportunities)
4. Source attribution for market claims
5. Follow the exact 10-section structure from the template

SECTION REQUIREMENTS:
- Each section should be complete and self-contained
- Use bullet points for scannability
- Include specific numbers, dates, and names
- Cite sources for market data
- Match the word count targets in the style guide
- Spell out acronyms on first use

AVOID:
- Superlatives without data ("revolutionary", "game-changing")
- Vague growth claims ("massive market", "rapidly growing")
- Promotional language
- Missing risk acknowledgment
- Generalizations instead of specifics

OUTPUT FORMAT:
Return a complete markdown memo following the template structure exactly.
Replace all template placeholders with actual data from the research.
"""


def augment_section_draft(
    section_name: str,
    existing_draft: str,
    research: Dict[str, Any],
    deck_data: Dict[str, Any],
    model: ChatAnthropic
) -> str:
    """
    Augment existing section draft with research findings.

    Args:
        section_name: Name of the section being augmented
        existing_draft: Existing draft from deck analysis
        research: Research data
        deck_data: Deck analysis data (for context)
        model: Language model for augmentation

    Returns:
        Augmented section content
    """
    import json

    prompt = f"""You have an initial section draft from deck analysis. Augment it with web research findings.

EXISTING DRAFT (from pitch deck):
{existing_draft}

RESEARCH FINDINGS:
{json.dumps(research, indent=2)}

TASK:
1. Keep all good information from the existing draft
2. Add new findings from research (with appropriate context)
3. Fill in gaps noted in original draft
4. Maintain analytical tone
5. Ensure no contradictions (note if deck claims differ from research)
6. Integrate the information smoothly - don't just append

Output the AUGMENTED section (300-500 words) in markdown format.
Return ONLY the section content, no preamble.
"""

    response = model.invoke(prompt)
    return response.content


def write_single_section(
    section_num: int,
    section_name: str,
    research: Dict[str, Any],
    company_name: str,
    investment_type: str,
    memo_mode: str,
    template: str,
    style_guide: str,
    model: ChatAnthropic,
    current_date: str
) -> str:
    """
    Write a single section of the memo.

    Args:
        section_num: Section number (1-10)
        section_name: Section name
        research: Research data
        company_name: Company name
        investment_type: Investment type
        memo_mode: Memo mode
        template: Template content
        style_guide: Style guide content
        model: LLM model
        current_date: Current date string

    Returns:
        Section content as markdown
    """
    import json

    research_json = json.dumps(research, indent=2)[:3000]  # Limit research to 3k chars

    # Add memo mode guidance
    mode_guidance = ""
    if memo_mode == "justify":
        mode_guidance = """
IMPORTANT - MEMO MODE: JUSTIFY (Retrospective Justification)
This memo is justifying an EXISTING investment we have already made. Your recommendation MUST be "COMMIT"
since the investment has already occurred. Focus on explaining WHY we made this investment and what
strengths/thesis justified the commitment.
"""
    else:  # consider mode
        mode_guidance = """
IMPORTANT - MEMO MODE: CONSIDER (Prospective Analysis)
This memo is evaluating a POTENTIAL investment we have not yet made. Your recommendation should be
PASS, CONSIDER, or COMMIT based on the objective analysis of strengths vs. risks.
"""

    user_prompt = f"""Write ONLY the "{section_name}" section for an investment memo about {company_name}.

CURRENT DATE: {current_date}
INVESTMENT TYPE: {investment_type.upper()}
{mode_guidance}

RESEARCH DATA (summary):
{research_json}

TEMPLATE GUIDANCE (for this section):
{template}

STYLE GUIDE:
{style_guide}

Write ONLY this section's content (no section header, it will be added automatically).
Be specific, analytical, use metrics from research.
Target: 300-500 words.

SECTION CONTENT:
"""

    response = model.invoke(user_prompt)
    return response.content.strip()


def writer_agent(state: MemoState) -> Dict[str, Any]:
    """
    Writer Agent implementation - ITERATIVE SECTION-BY-SECTION.

    Writes memo one section at a time, saving and stitching progressively.

    Args:
        state: Current memo state containing research data

    Returns:
        Updated state with draft_sections populated
    """
    research = state.get("research")
    if not research:
        raise ValueError("No research data available. Research agent must run first.")

    company_name = state["company_name"]
    investment_type = state.get("investment_type", "direct")
    memo_mode = state.get("memo_mode", "consider")

    # Load appropriate template and style guide
    template = load_template(investment_type)
    style_guide = load_style_guide()

    # Initialize Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0.7,
        max_tokens=4000  # Smaller context per section
    )

    # Get current date
    from datetime import datetime
    current_date = datetime.now().strftime("%B %Y")

    # Define section order
    section_mapping = [
        (1, "Executive Summary"),
        (2, "Business Overview"),
        (3, "Market Context"),
        (4, "Team"),
        (5, "Technology & Product"),
        (6, "Traction & Milestones"),
        (7, "Funding & Terms"),
        (8, "Risks & Mitigations"),
        (9, "Investment Thesis"),
        (10, "Recommendation"),
    ]

    # Get version manager and output directory
    version_mgr = VersionManager(Path("output"))
    safe_name = sanitize_filename(company_name)
    version = version_mgr.get_next_version(safe_name)
    output_dir = Path("output") / f"{safe_name}-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📝 Writing memo section-by-section...")

    # Write each section iteratively
    total_words = 0

    for section_num, section_name in section_mapping:
        print(f"  Writing section {section_num}/10: {section_name}...")

        # Write individual section
        section_content = write_single_section(
            section_num=section_num,
            section_name=section_name,
            research=research,
            company_name=company_name,
            investment_type=investment_type,
            memo_mode=memo_mode,
            template=template,
            style_guide=style_guide,
            model=model,
            current_date=current_date
        )

        # Save individual section
        save_section_artifact(output_dir, section_num, section_name, section_content)
        total_words += len(section_content.split())

        print(f"  ✓ Section {section_num} saved to file")

    # Sections saved - enrichment agents will process files directly
    print(f"✓ All 10 sections written and saved to {output_dir}/2-sections/")
    print(f"✓ Enrichment agents will process sections individually")
    print(f"✓ Final assembly will happen after citations are added")

    # Return minimal state (enrichment agents load from files)
    return {
        "draft_sections": {},  # Enrichment agents load from files, not state
        "messages": [f"Draft sections completed for {company_name} ({total_words} words total)"]
    }

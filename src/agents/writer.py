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


def writer_agent(state: MemoState) -> Dict[str, Any]:
    """
    Writer Agent implementation.

    Drafts a complete investment memo based on research data.

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
        temperature=0.7,  # Higher temperature for creative writing
    )

    # Create writing prompt
    import json
    from datetime import datetime
    research_json = json.dumps(research, indent=2)

    # Get current date
    current_date = datetime.now().strftime("%B %Y")  # e.g., "November 2024"

    # Customize instructions based on memo mode
    mode_instruction = ""
    if memo_mode == "justify":
        mode_instruction = """
IMPORTANT - MEMO MODE: JUSTIFY (Retrospective)
This investment has already been made. The recommendation section should be "COMMIT" with a rationale explaining why this was a good investment decision based on the analysis."""
    else:
        mode_instruction = """
IMPORTANT - MEMO MODE: CONSIDER (Prospective)
This is a prospective analysis. The recommendation section should objectively recommend "PASS", "CONSIDER", or "COMMIT" based on the strength of the opportunity and risks identified."""

    # Customize based on investment type
    type_instruction = ""
    if investment_type == "fund":
        type_instruction = "This is an LP commitment into a venture fund. Focus on GP track record, fund strategy, portfolio construction, and fee structure."
    else:
        type_instruction = "This is a direct investment into a startup company. Focus on product, market, team, traction, and technology."

    user_prompt = f"""Write a complete investment memo for {company_name} using the following research data:

CURRENT DATE: {current_date}
IMPORTANT: Use "{current_date}" as the memo date. Do NOT use any other date.

INVESTMENT TYPE: {investment_type.upper()}
{type_instruction}

{mode_instruction}

RESEARCH DATA:
{research_json}

Create a professional, analytical investment memo that:
1. Follows the template structure exactly (all 10 sections)
2. Adheres to the style guide principles
3. Uses specific metrics and data from the research
4. Maintains analytical tone (not promotional)
5. Includes balanced risk assessment
6. Cites sources for market claims
7. Provides appropriate recommendation based on memo mode
8. Uses the current date "{current_date}" for the memo date field

Write the complete memo as markdown following the template format."""

    # Build the system prompt with template and style guide
    system_prompt = (
        f"{WRITER_SYSTEM_PROMPT_BASE}\n\n"
        f"TEMPLATE:\n{template}\n\n"
        f"STYLE GUIDE:\n{style_guide}"
    )

    # Call Claude for writing
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]

    response = model.invoke(messages)
    memo_content = response.content

    # Parse into sections (simplified for POC - just store the full memo)
    # In production, we'd parse each section separately for granular validation
    draft_sections = {
        "full_memo": SectionDraft(
            section_name="full_memo",
            content=memo_content,
            word_count=len(memo_content.split()),
            citations=[]  # Would extract these in production
        )
    }

    # Save section artifacts
    try:
        # Get version manager
        version_mgr = VersionManager(Path("output"))
        safe_name = sanitize_filename(company_name)
        version = version_mgr.get_next_version(safe_name)

        # Get artifact directory (should already exist from research phase)
        output_dir = Path("output") / f"{safe_name}-{version}"

        # Parse memo into individual sections
        sections = parse_memo_sections(memo_content)

        # Save each section
        section_mapping = [
            (1, "Executive Summary"),
            (2, "Business Overview"),
            (3, "Market Context"),
            (4, "Technology & Product"),
            (5, "Traction & Milestones"),
            (6, "Team"),
            (7, "Funding & Terms"),
            (8, "Risks & Mitigations"),
            (9, "Investment Thesis"),
            (10, "Recommendation"),
        ]

        for num, name in section_mapping:
            if name in sections:
                save_section_artifact(output_dir, num, name, sections[name])

        print(f"Section artifacts saved to: {output_dir / '2-sections'}")
    except Exception as e:
        print(f"Warning: Could not save section artifacts: {e}")

    # Update state
    return {
        "draft_sections": draft_sections,
        "messages": [f"Draft memo completed for {company_name} ({len(memo_content.split())} words)"]
    }

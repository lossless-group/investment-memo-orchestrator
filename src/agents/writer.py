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
        investment_type: "direct" for startup investment, "fund" for LP commitment

    Returns:
        Template content as string
    """
    template_name = f"memo-template-{investment_type}.md"
    template_path = Path(__file__).parent.parent.parent / "templates" / template_name
    with open(template_path, "r") as f:
        return f.read()


def load_style_guide() -> str:
    """Load the style guide from file."""
    style_guide_path = Path(__file__).parent.parent.parent / "templates" / "style-guide.md"
    with open(style_guide_path, "r") as f:
        return f.read()


def parse_memo_sections(memo_content: str, investment_type: str = "direct") -> Dict[str, str]:
    """
    Parse memo into individual sections.

    Args:
        memo_content: Full memo markdown content
        investment_type: "direct" for startup investment, "fund" for LP commitment

    Returns:
        Dictionary mapping section names to content
    """
    sections = {}

    # Define the 10 expected sections based on investment type
    # Pattern now specifically matches ## N. format that the agents produce
    # Using .* to capture full header including & symbols
    if investment_type == "fund":
        section_patterns = [
            (1, r"##\s*1\.\s*Executive Summary.*", "Executive Summary"),
            (2, r"##\s*2\.\s*GP Background.*", "GP Background & Track Record"),
            (3, r"##\s*3\.\s*Fund Strategy.*", "Fund Strategy & Thesis"),
            (4, r"##\s*4\.\s*Portfolio Construction.*", "Portfolio Construction"),
            (5, r"##\s*5\.\s*Value Add.*", "Value Add & Differentiation"),
            (6, r"##\s*6\.\s*Track Record.*", "Track Record Analysis"),
            (7, r"##\s*7\.\s*Fee Structure.*", "Fee Structure & Economics"),
            (8, r"##\s*8\.\s*LP Base.*", "LP Base & References"),
            (9, r"##\s*9\.\s*Risks.*", "Risks & Mitigations"),
            (10, r"##\s*10\.\s*Recommendation.*", "Recommendation"),
        ]
    else:  # direct
        section_patterns = [
            (1, r"##\s*1\.\s*Executive Summary.*", "Executive Summary"),
            (2, r"##\s*2\.\s*Business Overview.*", "Business Overview"),
            (3, r"##\s*3\.\s*Market Context.*", "Market Context"),
            (4, r"##\s*4\.\s*Team.*", "Team"),
            (5, r"##\s*5\.\s*(?:Technology|Product).*", "Technology & Product"),
            (6, r"##\s*6\.\s*(?:Traction|Milestones).*", "Traction & Milestones"),
            (7, r"##\s*7\.\s*(?:Funding|Terms).*", "Funding & Terms"),
            (8, r"##\s*8\.\s*Risks.*", "Risks & Mitigations"),
            (9, r"##\s*9\.\s*Investment Thesis.*", "Investment Thesis"),
            (10, r"##\s*10\.\s*Recommendation.*", "Recommendation"),
        ]

    # Split content by section headers
    for i, (num, pattern, name) in enumerate(section_patterns):
        # Find start of this section
        match = re.search(pattern, memo_content, re.IGNORECASE)
        if not match:
            # Try alternate pattern without number for backwards compatibility
            alt_pattern = pattern.replace(r"##\s*\d+\.\s*", r"#{1,2}\s*")
            match = re.search(alt_pattern, memo_content, re.IGNORECASE)
            if not match:
                continue

        start_pos = match.end()

        # Find start of next section (or end of document)
        # Look for any ## N. pattern to mark the end
        next_section_pattern = r"\n##\s*\d+\.\s*"
        next_match = re.search(next_section_pattern, memo_content[start_pos:])
        if next_match:
            end_pos = start_pos + next_match.start()
        else:
            # Check for Citations section as potential end marker
            citations_match = re.search(r"\n###\s*Citations", memo_content[start_pos:], re.IGNORECASE)
            if citations_match:
                end_pos = start_pos + citations_match.start()
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
- Apologetic language about missing data ("Data not available", "Not disclosed", "Information limited")
- Explanations about what you couldn't find - just write what you know

OUTPUT FORMAT:
Return a complete markdown memo following the template structure exactly.
Replace all template placeholders with actual data from the research.
"""


def writer_agent(state: MemoState) -> Dict[str, Any]:
    """
    Writer Agent implementation.

    Drafts a complete investment memo based on research data.
    If draft_sections already exist (from deck analyzer), enhances them.
    Otherwise, creates sections from scratch.

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
    deck_analysis = state.get("deck_analysis")  # Get deck analysis if available
    existing_drafts = state.get("draft_sections", {})  # Check for existing section drafts

    # Load template and style guide
    print(f"Loading template for investment_type: {investment_type}")
    template = load_template(investment_type)
    style_guide = load_style_guide()
    print(f"Template loaded: memo-template-{investment_type}.md")

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

    # Get current date for the memo
    current_date = datetime.now().strftime("%B %d, %Y")

    # Prepare existing drafts section if available
    existing_drafts_section = ""
    if existing_drafts and existing_drafts.get("full_memo"):
        existing_content = existing_drafts["full_memo"].get("content", "")
        existing_drafts_section = f"""
EXISTING DRAFT CONTENT (FROM DECK ANALYZER):
{existing_content}

CRITICAL INSTRUCTIONS FOR ENHANCEMENT:
- The content above is from the pitch deck - this is your PRIMARY SOURCE
- PRESERVE all deck content exactly - do not remove or replace any information from the deck
- ONLY ADD web research to fill gaps where deck is silent
- If deck has info on a topic, keep that content and optionally supplement it
- DO NOT add apologetic text like "Data not available", "Not disclosed", "Information limited"
- If you don't have info for a section, write what you can from the deck and move on
- NO explanations about what's missing - just write what you know
- Your job is to SUPPLEMENT the deck content, not rewrite it
"""
    else:
        existing_drafts_section = "(No existing draft content - creating memo from scratch)"

    # Adjust prompt based on memo mode
    if memo_mode == "justify":
        mode_instruction = """
IMPORTANT - RETROSPECTIVE MODE:
This is a JUSTIFICATION memo for an investment we have ALREADY MADE.
- Write in past/present tense about why this was a good decision
- The Recommendation section should be "COMMIT" with rationale explaining our investment decision
- Focus on validating the investment thesis and highlighting strengths
- Acknowledge risks but frame them in context of our risk mitigation strategies
- Use language like "We invested because..." and "This decision was driven by..."
"""
        entity_type = "fund" if investment_type == "fund" else "company"
    else:
        mode_instruction = """
IMPORTANT - PROSPECTIVE MODE:
This is a CONSIDERATION memo for a potential investment opportunity.
- Write in present/future tense analyzing whether this is a good opportunity
- The Recommendation section should be PASS / CONSIDER / COMMIT based on objective analysis
- Provide balanced perspective on opportunities and risks
- Use language like "We should consider..." and "The opportunity presents..."
"""
        entity_type = "fund" if investment_type == "fund" else "company"

    user_prompt = f"""{'ENHANCE the existing draft' if existing_drafts else 'Write a complete investment memo'} for {company_name} using the following data sources:

{existing_drafts_section}

WEB RESEARCH DATA:
{research_json}

{mode_instruction}

IMPORTANT: Today's date is {current_date}. Use this date when filling in the {{DATE}} placeholder in the template.

Create a professional, analytical investment memo that:
1. Follows the template structure exactly (all 10 sections)
2. {'BUILDS ON the existing draft content, enhancing it with research data' if existing_drafts else 'Uses specific metrics and data from the research'}
3. Adheres to the style guide principles
4. Maintains analytical tone (not promotional)
5. Includes balanced risk assessment
6. Cites sources for market claims
7. {'Justifies our investment decision' if memo_mode == 'justify' else 'Provides objective analysis for decision-making'}
8. Uses the current date ({current_date}) for the memo date field

Write the complete {'enhanced' if existing_drafts else ''} memo as markdown following the template format."""

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
        sections = parse_memo_sections(memo_content, investment_type)

        # Save each section (mapping based on investment type)
        if investment_type == "fund":
            section_mapping = [
                (1, "Executive Summary"),
                (2, "GP Background & Track Record"),
                (3, "Fund Strategy & Thesis"),
                (4, "Portfolio Construction"),
                (5, "Value Add & Differentiation"),
                (6, "Track Record Analysis"),
                (7, "Fee Structure & Economics"),
                (8, "LP Base & References"),
                (9, "Risks & Mitigations"),
                (10, "Recommendation"),
            ]
        else:
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

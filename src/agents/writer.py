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


def load_template() -> str:
    """Load the memo template from file."""
    template_path = Path(__file__).parent.parent.parent / "templates" / "memo-template.md"
    with open(template_path, "r") as f:
        return f.read()


def load_style_guide() -> str:
    """Load the style guide from file."""
    style_guide_path = Path(__file__).parent.parent.parent / "templates" / "style-guide.md"
    with open(style_guide_path, "r") as f:
        return f.read()


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

    # Load template and style guide
    template = load_template()
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
    research_json = json.dumps(research, indent=2)

    user_prompt = f"""Write a complete investment memo for {company_name} using the following research data:

RESEARCH DATA:
{research_json}

Create a professional, analytical investment memo that:
1. Follows the template structure exactly (all 10 sections)
2. Adheres to the style guide principles
3. Uses specific metrics and data from the research
4. Maintains analytical tone (not promotional)
5. Includes balanced risk assessment
6. Cites sources for market claims

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

    # Update state
    return {
        "draft_sections": draft_sections,
        "messages": [f"Draft memo completed for {company_name} ({len(memo_content.split())} words)"]
    }

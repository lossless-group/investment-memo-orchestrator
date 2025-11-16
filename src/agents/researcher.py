"""
Research Agent - Gathers comprehensive company and market data.

This agent is responsible for collecting all necessary information to write
an investment memo, including company fundamentals, market sizing, competitive
landscape, team backgrounds, and traction metrics.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import json
import os
from typing import Dict, Any

from ..state import MemoState, ResearchData


# System prompt for Research Agent
RESEARCH_SYSTEM_PROMPT = """You are an investment research specialist gathering data for venture capital memos.

Your task is to collect comprehensive information about a target company for investment analysis.

REQUIRED DATA TO GATHER:
1. Company fundamentals (stage, HQ location, founding team with backgrounds)
2. Market sizing with sources (TAM, growth projections, market dynamics)
3. Competitive landscape (direct competitors, alternatives, positioning)
4. Funding history (rounds, investors, amounts, valuations if available)
5. Traction metrics (revenue, customers, partnerships, key milestones)
6. Technology overview (technical approach, product status, roadmap)
7. Team assessment (founders' prior companies, exits, relevant expertise)

OUTPUT FORMAT: Return structured JSON matching this schema:
{
  "company": {
    "name": "...",
    "stage": "...",
    "hq_location": "...",
    "website": "...",
    "founders": [{"name": "...", "title": "...", "background": "..."}]
  },
  "market": {
    "tam": "...",
    "growth_rate": "...",
    "sources": ["..."],
    "dynamics": ["..."]
  },
  "technology": {
    "description": "...",
    "product_status": "...",
    "roadmap": ["..."]
  },
  "team": {
    "founders": ["..."],
    "key_hires": ["..."],
    "assessment": "..."
  },
  "traction": {
    "revenue": "...",
    "customers": "...",
    "partnerships": ["..."],
    "milestones": ["..."]
  },
  "funding": {
    "current_round": "...",
    "amount_raising": "...",
    "valuation": "...",
    "prior_rounds": ["..."],
    "notable_investors": ["..."]
  },
  "sources": ["..."]
}

QUALITY STANDARDS:
- Prioritize recent data (last 12 months preferred)
- Include source URLs or references for all market sizing
- Note data gaps explicitly (don't fabricate information)
- Flag conflicting information between sources
- Use specific numbers and dates wherever possible

If you cannot find certain information, explicitly note "Data not available" for that field
rather than making assumptions or using placeholder data.
"""


def research_agent(state: MemoState) -> Dict[str, Any]:
    """
    Research Agent implementation.

    Gathers comprehensive company and market data needed for the memo.
    For the POC, this uses Claude to simulate research. In production,
    this would integrate with MCP servers for Crunchbase, PitchBook, etc.

    Args:
        state: Current memo state containing company_name

    Returns:
        Updated state with research data populated
    """
    company_name = state["company_name"]

    # Initialize Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0.3,  # Lower temperature for factual research
    )

    # Create research prompt
    user_prompt = f"""Research the company "{company_name}" and gather comprehensive information for an investment memo.

Since this is a POC and we may not have real-time access to all databases, please:
1. If you have knowledge about this company, provide accurate, specific information
2. If this is a real company but you lack recent data, note what information would need to be gathered from sources like Crunchbase, PitchBook, company website, etc.
3. If this is a hypothetical/sample company, create realistic sample data that demonstrates the structure and level of detail required

Focus on providing the type and quality of information that would be needed for a real investment memo, with proper structure and specificity.

Return your research as valid JSON matching the schema provided in your system prompt."""

    # Call Claude for research
    messages = [
        SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt)
    ]

    response = model.invoke(messages)

    # Parse response as JSON
    try:
        research_data = json.loads(response.content)
    except json.JSONDecodeError:
        # If response isn't valid JSON, try to extract JSON from markdown code block
        content = response.content
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            research_data = json.loads(json_str)
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            research_data = json.loads(json_str)
        else:
            raise ValueError(f"Could not parse research data as JSON: {content[:200]}...")

    # Update state
    return {
        "research": ResearchData(**research_data),
        "messages": [f"Research completed for {company_name}"]
    }

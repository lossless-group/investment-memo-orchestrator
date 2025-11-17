"""
Link Enrichment Agent - Adds hyperlinks to organizations, investors, and entities.

This agent enriches memo sections by adding markdown links to:
- Investor firms and individual investors
- Government bodies (FDA, NRC, SEC, etc.)
- Partner organizations
- Competitor companies
- Universities and research institutions
- Industry organizations

Links are added in-place without changing the narrative flow.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import os
from typing import Dict, Any
from ..state import MemoState


LINK_ENRICHMENT_SYSTEM_PROMPT = """You are a link enrichment specialist for investment memos.

Your task is to add markdown hyperlinks to organizations, companies, investors, and institutions mentioned in memo sections.

ENTITIES TO LINK:
1. **Investor firms**: VC firms, PE firms, family offices, institutional investors
2. **Government bodies**: FDA, NRC, SEC, DOE, EPA, FCC, NASA, etc.
3. **Partner organizations**: Strategic partners, suppliers, distributors
4. **Competitor companies**: Direct and indirect competitors
5. **Universities**: Research institutions, academic partners
6. **Industry organizations**: Trade groups, standards bodies

LINK FORMAT:
Use markdown syntax: [Entity Name](https://website.com)

RULES:
1. DO NOT change the text or narrative - only add links
2. ONLY link the FIRST mention of each entity in each section
3. Use the entity's primary website (not Wikipedia, LinkedIn, Crunchbase)
4. If you're not confident about the correct website, DO NOT add a link
5. Keep existing links unchanged
6. Preserve all formatting, bullet points, and structure
7. For investor websites, use their main firm website
8. For government bodies, use official .gov websites
9. For universities, use the main university domain (.edu)

EXAMPLES:
Before: "The company partnered with Idaho National Laboratory"
After: "The company partnered with [Idaho National Laboratory](https://inl.gov)"

Before: "Series B led by Valor Equity Partners"
After: "Series B led by [Valor Equity Partners](https://valorep.com)"

Before: "Approved by the FDA in 2024"
After: "Approved by the [FDA](https://www.fda.gov) in 2024"

OUTPUT:
Return the COMPLETE section with links added. Do not summarize or truncate.
"""


def link_enrichment_agent(state: MemoState) -> Dict[str, Any]:
    """
    Link Enrichment Agent implementation.

    Adds markdown links to organizations and entities mentioned in memo sections.

    Args:
        state: Current memo state with draft sections

    Returns:
        Updated state with link-enriched sections
    """
    draft_sections = state.get("draft_sections", {})
    if not draft_sections:
        return {
            "messages": ["No draft sections available for link enrichment"]
        }

    company_name = state["company_name"]

    # Get the full memo content
    full_memo = draft_sections.get("full_memo", {})
    memo_content = full_memo.get("content", "")

    if not memo_content:
        return {
            "messages": ["No memo content available for link enrichment"]
        }

    # Initialize Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0,  # Deterministic for link addition
    )

    # Create enrichment prompt
    user_prompt = f"""Add hyperlinks to organizations and entities in this investment memo for {company_name}.

MEMO CONTENT:
{memo_content}

INSTRUCTIONS:
1. Identify all investors, government bodies, partners, competitors, universities, and industry organizations
2. Add markdown links [Entity Name](https://website.com) to the FIRST mention of each entity
3. Use official websites (firm sites, .gov, .edu domains)
4. DO NOT change any text - only add links
5. If unsure about the correct website, skip that entity
6. Return the COMPLETE memo with links added

Output the full memo with links enriched."""

    # Call Claude for link enrichment
    messages = [
        SystemMessage(content=LINK_ENRICHMENT_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt)
    ]

    print("Enriching memo with organization links...")
    response = model.invoke(messages)
    enriched_content = response.content

    # Count links added
    original_link_count = memo_content.count("](http")
    enriched_link_count = enriched_content.count("](http")
    links_added = enriched_link_count - original_link_count

    print(f"Link enrichment completed: {links_added} links added")

    # Update draft sections with enriched content
    enriched_sections = {
        "full_memo": {
            "section_name": "full_memo",
            "content": enriched_content,
            "word_count": len(enriched_content.split()),
            "citations": full_memo.get("citations", [])
        }
    }

    return {
        "draft_sections": enriched_sections,
        "messages": [f"Links added to memo for {company_name} ({links_added} organization links)"]
    }

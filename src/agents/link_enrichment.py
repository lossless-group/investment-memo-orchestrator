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
    Link Enrichment Agent implementation - SECTION-BY-SECTION.

    Adds markdown links to organizations and entities mentioned in each memo section.

    Args:
        state: Current memo state

    Returns:
        Updated state message
    """
    from pathlib import Path
    from ..utils import get_latest_output_dir

    company_name = state["company_name"]

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name)
        sections_dir = output_dir / "2-sections"
    except FileNotFoundError:
        print("⊘ Link enrichment skipped - no output directory found")
        return {"messages": ["Link enrichment skipped - no output directory"]}

    if not sections_dir.exists():
        print("⊘ Link enrichment skipped - no sections directory found")
        return {"messages": ["Link enrichment skipped - no sections found"]}

    # Initialize Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0,  # Deterministic for link addition
    )

    print(f"\n🔗 Enriching links section-by-section...")

    # Load all section files
    section_files = sorted(sections_dir.glob("*.md"))
    total_links_added = 0

    for section_file in section_files:
        section_name = section_file.stem.split("-", 1)[1].replace("--", " & ").replace("-", " ").title()

        # Read section
        with open(section_file) as f:
            section_content = f.read()

        # Skip if section is very short (likely minimal content)
        if len(section_content) < 100:
            continue

        print(f"  Enriching links: {section_name}...")

        # Create enrichment prompt
        user_prompt = f"""Add hyperlinks to organizations and entities in this {section_name} section for {company_name}.

SECTION CONTENT:
{section_content}

INSTRUCTIONS:
1. Identify all investors, government bodies, partners, competitors, universities, and industry organizations
2. Add markdown links [Entity Name](https://website.com) to the FIRST mention of each entity
3. Use official websites (firm sites, .gov, .edu domains)
4. DO NOT change any text - only add links
5. If unsure about the correct website, skip that entity
6. Return the COMPLETE section with links added

Output the full section with links enriched."""

        # Call Claude for link enrichment
        messages = [
            SystemMessage(content=LINK_ENRICHMENT_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]

        try:
            response = model.invoke(messages)
            enriched_content = response.content

            # Count links added
            original_link_count = section_content.count("](http")
            enriched_link_count = enriched_content.count("](http")
            links_added = enriched_link_count - original_link_count

            # Save enriched section back
            with open(section_file, "w") as f:
                f.write(enriched_content)

            total_links_added += links_added
            print(f"  ✓ {section_name}: {links_added} links added")

        except Exception as e:
            print(f"  Warning: Link enrichment failed for {section_name}: {e}")
            continue

    print(f"✓ Link enrichment complete: {total_links_added} total links added")

    return {
        "messages": [f"Links added to memo for {company_name} ({total_links_added} organization links)"]
    }

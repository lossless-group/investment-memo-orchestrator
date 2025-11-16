"""
Citation-Enrichment Agent - Adds inline academic citations to memo sections.

This agent takes well-written content from the Writer agent and enriches it with
properly formatted inline citations [^1], [^2], etc. using Perplexity's research
capabilities, without rewriting or altering the narrative.
"""

from langchain_core.messages import HumanMessage, SystemMessage
import os
from typing import Dict, Any
import re

from ..state import MemoState


CITATION_ENRICHMENT_SYSTEM_PROMPT = """You are a citation specialist for investment memos.

Your ONLY job is to add inline citations to existing content.

CRITICAL RULES:
1. DO NOT rewrite or change the narrative
2. DO NOT alter the author's voice or phrasing
3. DO NOT add new information or change existing claims
4. ONLY insert [^1], [^2], [^3], etc. citations to support existing factual claims
5. Find authoritative sources for each factual claim from quality industry sources:
   - Company websites, blogs, and press releases
   - TechCrunch, The Information, Sifted, Protocol, Axios
   - Medium articles from credible authors
   - Crunchbase, PitchBook (for funding data)
   - SEC filings, S-1s, investor letters
   - Industry analyst reports (Gartner, CB Insights, McKinsey, etc.)
   - News outlets (Bloomberg, Reuters, WSJ, FT)
   - Academic papers only when relevant for technical claims
6. Generate a comprehensive citation list at the end in this exact format:

### Citations

[^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD

[^2]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD

IMPORTANT: DD must ALWAYS be two digits with zero-padding (e.g., "Jan 08" not "Jan 8", "Mar 03" not "Mar 3")

WHAT TO CITE:
- Funding amounts and rounds (cite Crunchbase, PitchBook, press releases)
- Company founding date, location, team info (cite company website, LinkedIn, Crunchbase)
- Market sizing and TAM figures (cite industry reports, analyst firms)
- Technical specifications and product details (cite company announcements, technical docs)
- Traction metrics and milestones (cite company blog, press releases, news articles)
- Investor names and details (cite funding announcements, Crunchbase)
- Competitive landscape claims (cite company websites, industry analysis)

CITATION PLACEMENT:
- Place citation immediately after the claim, before punctuation: "raised $136M[^1]"
- Multiple facts in one sentence can have multiple citations: "founded in 2023[^1] and raised $136M[^2]"
- For lists, cite each item if sources differ

OUTPUT FORMAT:
Return the content with inline citations added, followed by:

### Citations

[citation list in the format above]

Remember: Your goal is to add scholarly rigor WITHOUT changing what was written."""


def citation_enrichment_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation-Enrichment Agent implementation.

    Takes drafted memo sections and adds inline citations using Perplexity,
    without rewriting the content.

    Args:
        state: Current memo state containing draft_sections

    Returns:
        Updated state with citation-enriched sections
    """
    draft_sections = state.get("draft_sections", {})
    if not draft_sections:
        raise ValueError("No draft available. Writer agent must run first.")

    company_name = state["company_name"]
    memo_content = draft_sections.get("full_memo", {}).get("content", "")

    if not memo_content:
        raise ValueError("Draft memo content is empty.")

    # Check if Perplexity is configured
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        print("Warning: PERPLEXITY_API_KEY not set, skipping citation enrichment")
        return {
            "messages": ["Citation enrichment skipped - no Perplexity API key configured"]
        }

    # Initialize Perplexity client
    try:
        from openai import OpenAI
        perplexity_client = OpenAI(
            api_key=perplexity_key,
            base_url="https://api.perplexity.ai"
        )
    except ImportError:
        print("Warning: openai package not installed, skipping citation enrichment")
        return {
            "messages": ["Citation enrichment skipped - openai package not installed"]
        }

    # Create citation enrichment prompt
    user_prompt = f"""Add inline academic citations to this investment memo for {company_name}.

IMPORTANT: Do NOT rewrite the content. Only add [^1], [^2], etc. citations and generate the citation list.

MEMO CONTENT:
{memo_content}

Return the same content with citations added, followed by the citation list in the format specified in your system prompt."""

    print(f"Enriching memo with citations using Perplexity...")

    try:
        # Call Perplexity for citation enrichment
        response = perplexity_client.chat.completions.create(
            model="sonar-pro",  # Perplexity Sonar Pro for advanced research with citations
            messages=[
                {"role": "system", "content": CITATION_ENRICHMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
        )

        enriched_content = response.choices[0].message.content

        # Update draft sections with enriched content
        from ..state import SectionDraft

        enriched_sections = {
            "full_memo": SectionDraft(
                section_name="full_memo",
                content=enriched_content,
                word_count=len(enriched_content.split()),
                citations=extract_citation_count(enriched_content)
            )
        }

        print(f"Citation enrichment completed: {len(extract_citation_count(enriched_content))} citations added")

        return {
            "draft_sections": enriched_sections,
            "messages": [f"Citations added to memo for {company_name}"]
        }

    except Exception as e:
        print(f"Warning: Citation enrichment failed: {e}")
        # If citation enrichment fails, return original content
        return {
            "messages": [f"Citation enrichment failed: {str(e)}. Proceeding with original content."]
        }


def extract_citation_count(content: str) -> list:
    """
    Extract list of citations from content.

    Args:
        content: Markdown content with citations

    Returns:
        List of citation markers found (e.g., ["[^1]", "[^2]"])
    """
    # Find all citation markers like [^1], [^2], etc.
    citations = re.findall(r'\[\^\w+\]', content)
    return list(set(citations))  # Return unique citations

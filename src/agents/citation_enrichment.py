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
6. EVERY citation MUST include the full URL in the reference list
7. Generate a comprehensive citation list at the end in this exact format:

### Citations

[^1]: YYYY, MMM DD. Source Title - Source Name. Published: YYYY-MM-DD | Updated: YYYY-MM-DD | URL: https://full-url-here.com

[^2]: YYYY, MMM DD. Source Title - Source Name. Published: YYYY-MM-DD | Updated: N/A | URL: https://full-url-here.com

IMPORTANT FORMATTING:
- DD must ALWAYS be two digits with zero-padding (e.g., "Jan 08" not "Jan 8", "Mar 03" not "Mar 3")
- ALWAYS include "Updated:" field - use "Updated: N/A" if source has no update date
- ALWAYS include "Published:" field with actual date
- ALWAYS include "URL: https://..." at the end of each citation
- The format MUST be: YYYY, MMM DD. Title. Published: YYYY-MM-DD | Updated: YYYY-MM-DD or N/A | URL: https://...
- No space before colon in "[^1]:"
- Exactly one space after colon before text begins
- All THREE fields (Published, Updated, URL) are REQUIRED in every citation

WHAT TO CITE:
- Funding amounts and rounds (cite Crunchbase, PitchBook, press releases)
- Company founding date, location, team info (cite company website, LinkedIn, Crunchbase)
- Market sizing and TAM figures (cite industry reports, analyst firms)
- Technical specifications and product details (cite company announcements, technical docs)
- Traction metrics and milestones (cite company blog, press releases, news articles)
- Investor names and details (cite funding announcements, Crunchbase)
- Competitive landscape claims (cite company websites, industry analysis)

CITATION PLACEMENT (OBSIDIAN MARKDOWN FORMAT):
- Place citation AFTER punctuation when punctuation exists: "raised $136M. [^1]" NOT "raised $136M[^1]."
- Always include exactly ONE SPACE before each citation marker: "claim. [^1] [^2]" NOT "claim.[^1][^2]"
- Multiple citations: "text. [^1] [^2] [^3]" with one space before each
- In bullet points without ending punctuation: "- Bullet item [^1]" (one space before citation)
- Examples:
  CORRECT: "The company raised $136M. [^1]"
  CORRECT: "Founded in 2023 by Jane Doe. [^1] [^2]"
  CORRECT: "- Strategic partnership with Acme Corp [^3]"
  WRONG: "The company raised $136M[^1]."
  WRONG: "Founded in 2023.[^1][^2]"

OUTPUT FORMAT:
Return the content with inline citations added, followed by:

### Citations

[citation list in the format above with URLs]

Remember: Your goal is to add scholarly rigor WITHOUT changing what was written. ALWAYS include URLs in the citation list."""


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

CRITICAL REQUIREMENTS:
1. Do NOT rewrite the content - only add [^1], [^2], etc. citations
2. Place citations AFTER punctuation with a space: "text. [^1]" not "text[^1]."
3. EVERY citation in the reference list MUST include the full URL
4. Format: [^1]: YYYY, MMM DD. Title - Source. Published: YYYY-MM-DD | Updated: YYYY-MM-DD or N/A | URL: https://...
5. ALL THREE FIELDS REQUIRED: Published, Updated (or "N/A"), and URL

MEMO CONTENT:
{memo_content}

Return the same content with citations added (space before each citation marker), followed by the citation list with URLs."""

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

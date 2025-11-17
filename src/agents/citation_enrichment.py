"""
Citation-Enrichment Agent - Enriches memo with citations, links, and visual content.

This agent takes well-written content from the Writer agent and enriches it with:
- Inline citations [^1], [^2], etc. with full source attribution
- LinkedIn profile links for founders and team members
- Website links for organizations (investors, partners, government bodies)
- Relevant images, charts, and graphs using markdown image syntax

All enrichment preserves the Writer's narrative without rewriting or altering content.
Uses Perplexity's research capabilities for finding URLs and visual content.
"""

from langchain_core.messages import HumanMessage, SystemMessage
import os
from typing import Dict, Any
import re

from ..state import MemoState


CITATION_ENRICHMENT_SYSTEM_PROMPT = """You are an enrichment specialist for investment memos.

Your job is to enrich existing content with citations, links, and visual content.

CRITICAL RULES:
1. DO NOT rewrite or change the narrative
2. DO NOT alter the author's voice or phrasing
3. DO NOT add new information or change existing claims
4. ONLY add enrichments (citations, links, images) to support and enhance existing content

YOUR ENRICHMENT TASKS:

TASK 1: ADD INLINE CITATIONS
- Insert [^1], [^2], [^3], etc. citations to support existing factual claims
- Find authoritative sources for each factual claim from quality industry sources:
  - Company websites, blogs, and press releases
  - TechCrunch, The Information, Sifted, Protocol, Axios
  - Medium articles from credible authors
  - Crunchbase, PitchBook (for funding data)
  - SEC filings, S-1s, investor letters
  - Industry analyst reports (Gartner, CB Insights, McKinsey, etc.)
  - News outlets (Bloomberg, Reuters, WSJ, FT)
  - Academic papers only when relevant for technical claims
- Generate a comprehensive citation list at the end in this exact format:

### Citations

[^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD

[^2]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD

IMPORTANT: DD must ALWAYS be two digits with zero-padding (e.g., "Jan 08" not "Jan 8", "Mar 03" not "Mar 3")

TASK 2: ADD LINKEDIN PROFILE LINKS
- When mentioning founders, co-founders, CEO, CTO, or key team members by name, add LinkedIn profile link
- Format: **Name** ([LinkedIn](https://linkedin.com/in/profile-url))
- Example: **Matt Loszak** ([LinkedIn](https://linkedin.com/in/matt-loszak)) - CEO, previously...
- Search for accurate LinkedIn profile URLs for each person mentioned
- Only add if you can find the actual LinkedIn profile URL
- If uncertain about the correct profile, skip the link rather than guessing

TASK 3: ADD ORGANIZATION WEBSITE LINKS
- When mentioning organizations (investors, companies, government bodies, partners), add website link
- Format: **Organization Name** ([website](https://example.com))
- Examples:
  - **Valor Equity Partners** ([website](https://valorep.com)) led the Series B...
  - **Idaho National Laboratory** ([INL](https://inl.gov)) partnership...
  - **NuScale Power** ([website](https://nuscalepower.com)) competitor...
- Search for official website URLs for each organization
- Only add if you can find the official website URL
- If uncertain, skip the link rather than guessing

TASK 4: INSERT RELEVANT IMAGES AND CHARTS
- Find and insert relevant images, charts, graphs, and diagrams that enhance understanding
- Use markdown image syntax: ![Description](https://imageurl.to/image.png)
- Priority image types:
  - Company logos (use in header if available)
  - Product images or renderings
  - Technology diagrams or schematics
  - Market size charts or TAM visualizations
  - Organizational charts or team photos
  - Facility or manufacturing images
  - Charts from company presentations or press releases
- Good placement locations:
  - After company name in header: Logo
  - Business Overview section: Product images
  - Technology section: Technical diagrams, product renderings
  - Market Context section: TAM charts, market size graphs
  - Team section: Team photos (if available)
- Image descriptions should be clear and informative
- Examples:
  - ![Aalo Pod 50 MWe Modular Reactor](https://www.aalo.com/images/reactor-rendering.png)
  - ![Global Small Modular Reactor Market Size 2022-2030](https://example.com/smr-market-chart.png)
  - ![Aalo Atomics Pilot Factory in Austin, Texas](https://www.aalo.com/images/facility.jpg)
- Only insert images if you can find actual, working URLs
- Do not fabricate or guess image URLs
- If you cannot find relevant images, that's okay - skip this task

WHAT TO CITE:
- Funding amounts and rounds (cite Crunchbase, PitchBook, press releases)
- Company founding date, location, team info (cite company website, LinkedIn, Crunchbase)
- Market sizing and TAM figures (cite industry reports, analyst firms)
- Technical specifications and product details (cite company announcements, technical docs)
- Traction metrics and milestones (cite company blog, press releases, news articles)
- Investor names and details (cite funding announcements, Crunchbase)
- Competitive landscape claims (cite company websites, industry analysis)

CITATION PLACEMENT (INLINE):
- CRITICAL: Always include a space before the citation bracket for Markdown compatibility
- Place citation after the claim with a space: "raised $136M [^1]"
- After punctuation, add space then citation: "raised $136M. [^1]"
- Multiple facts in one sentence can have multiple citations: "founded in 2023 [^1] and raised $136M [^2]"
- For lists, cite each item if sources differ
- INCORRECT: "text[^1]" or "text.[^1]"
- CORRECT: "text [^1]" or "text. [^1]"

CITATION REFERENCE LIST (BOTTOM OF PAGE):
- CRITICAL: NO space before the bracket, colon and space after closing bracket
- Format: [^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD
- INCORRECT: [^1] : citation text or [^1]:citation text
- CORRECT: [^1]: citation text

OUTPUT FORMAT:
Return the enriched content with:
1. LinkedIn profile links added to team member names
2. Website links added to organization names
3. Relevant images inserted in appropriate sections (if found)
4. Inline citations [^1], [^2], etc. added throughout
5. Citation list at the end in the format specified above

### Citations

[citation list in the format above]

Remember: Your goal is to ENRICH the content (citations, links, images) WITHOUT changing the narrative, voice, or claims."""


def citation_enrichment_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation-Enrichment Agent implementation.

    Takes drafted memo sections and enriches with citations, links, and images
    using Perplexity Sonar Pro, without rewriting the content.

    Enrichments added:
    - Inline citations [^1], [^2] with full source attribution
    - LinkedIn profile links for founders and team members
    - Website links for organizations (investors, partners, government bodies)
    - Relevant images, charts, and graphs using markdown syntax

    Args:
        state: Current memo state containing draft_sections

    Returns:
        Updated state with fully enriched sections
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
        print("Warning: PERPLEXITY_API_KEY not set, skipping enrichment")
        return {
            "messages": ["Enrichment skipped - no Perplexity API key configured (citations, links, images will be missing)"]
        }

    # Initialize Perplexity client
    try:
        from openai import OpenAI
        perplexity_client = OpenAI(
            api_key=perplexity_key,
            base_url="https://api.perplexity.ai"
        )
    except ImportError:
        print("Warning: openai package not installed, skipping enrichment")
        return {
            "messages": ["Enrichment skipped - openai package not installed (citations, links, images will be missing)"]
        }

    # Create enrichment prompt
    user_prompt = f"""Enrich this investment memo for {company_name} with citations, links, and images.

CRITICAL: Do NOT rewrite the narrative. Only add enrichments (citations, links, images).

YOUR TASKS:
1. Add LinkedIn profile links for all founders and team members mentioned by name
2. Add website links for all organizations (investors, partners, government bodies, competitors)
3. Find and insert relevant images, charts, graphs (product images, TAM charts, team photos, etc.)
4. Add inline citations [^1], [^2], etc. to support factual claims
5. Generate comprehensive citation list at the end

MEMO CONTENT:
{memo_content}

Return the enriched content with all four types of enrichments added, followed by the citation list in the format specified in your system prompt."""

    print(f"Enriching memo with citations, links, and images using Perplexity...")

    try:
        # Call Perplexity for full content enrichment
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

        # Count enrichments
        citation_count = len(extract_citation_count(enriched_content))
        linkedin_count = enriched_content.count("([LinkedIn](")
        org_link_count = enriched_content.count("([website](") + enriched_content.count("([INL](")
        image_count = enriched_content.count("![")

        print(f"Enrichment completed: {citation_count} citations, {linkedin_count} LinkedIn links, {org_link_count} org links, {image_count} images")

        return {
            "draft_sections": enriched_sections,
            "messages": [f"Enriched memo for {company_name}: {citation_count} citations, {linkedin_count} LinkedIn links, {org_link_count} org links, {image_count} images"]
        }

    except Exception as e:
        print(f"Warning: Enrichment failed: {e}")
        # If enrichment fails, return original content
        return {
            "messages": [f"Enrichment failed: {str(e)}. Proceeding with original content (citations, links, images missing)."]
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

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


def enrich_section_with_citations(
    section_content: str,
    section_name: str,
    company_name: str,
    perplexity_client
) -> str:
    """
    Enrich a single section with citations.

    Args:
        section_content: Section content to enrich
        section_name: Name of the section
        company_name: Company name
        perplexity_client: Perplexity API client

    Returns:
        Section content with citations added
    """
    user_prompt = f"""Add inline citations to this {section_name} section for {company_name}.

CRITICAL:
1. Do NOT rewrite - only add [^1], [^2] citations
2. Place citations AFTER punctuation with space: "text. [^1]"
3. EVERY citation MUST have URL
4. Format: [^1]: YYYY, MMM DD. Title. Published: YYYY-MM-DD | Updated: N/A | URL: https://...

SECTION:
{section_content}

Return same content with citations added, plus citation list at end."""

    try:
        response = perplexity_client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {"role": "system", "content": CITATION_ENRICHMENT_SYSTEM_PROMPT[:2000]},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=6000,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  Warning: Citation enrichment failed for {section_name}: {e}")
        return section_content  # Return original if enrichment fails


def citation_enrichment_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation-Enrichment Agent - SECTION-BY-SECTION.

    Enriches each section independently with citations.

    Args:
        state: Current memo state containing draft_sections

    Returns:
        Updated state with citation-enriched sections
    """
    draft_sections = state.get("draft_sections", {})
    if not draft_sections:
        raise ValueError("No draft available. Writer agent must run first.")

    company_name = state["company_name"]

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
        from pathlib import Path
        from ..artifacts import sanitize_filename
        from ..versioning import VersionManager

        perplexity_client = OpenAI(
            api_key=perplexity_key,
            base_url="https://api.perplexity.ai"
        )
    except ImportError:
        print("Warning: openai package not installed, skipping citation enrichment")
        return {
            "messages": ["Citation enrichment skipped - openai package not installed"]
        }

    # Get output directory
    version_mgr = VersionManager(Path("output"))
    safe_name = sanitize_filename(company_name)
    version = version_mgr.get_latest_version(safe_name)
    output_dir = Path("output") / f"{safe_name}-{version}"
    sections_dir = output_dir / "2-sections"

    if not sections_dir.exists():
        print("Warning: No sections directory found, skipping citation enrichment")
        return {"messages": ["Citation enrichment skipped - no sections found"]}

    print(f"\n📚 Enriching citations section-by-section...")

    # Load all section files
    section_files = sorted(sections_dir.glob("*.md"))
    sections_data = []  # Store (section_num, section_name, enriched_content)
    total_citations_before_renumber = 0

    for section_file in section_files:
        section_name = section_file.stem.split("-", 1)[1].replace("--", " & ").replace("-", " ").title()
        print(f"  Enriching citations: {section_name}...")

        # Read section
        with open(section_file) as f:
            section_content = f.read()

        # Enrich with citations
        enriched_section = enrich_section_with_citations(
            section_content=section_content,
            section_name=section_name,
            company_name=company_name,
            perplexity_client=perplexity_client
        )

        # Save enriched section back
        with open(section_file, "w") as f:
            f.write(enriched_section)

        # Store for global renumbering
        section_num = section_file.stem.split("-")[0]
        sections_data.append((section_num, section_name, enriched_section))

        # Count citations (before renumbering)
        section_cites = len(re.findall(r'\[\^[0-9]+\]', enriched_section))
        total_citations_before_renumber += section_cites
        print(f"  ✓ {section_name}: {section_cites} citations added")

    # Renumber citations globally across all sections
    print(f"\n🔢 Renumbering citations globally across all sections...")
    enriched_content = f"# Investment Memo: {company_name}\n\n"
    enriched_content += renumber_citations_globally(sections_data)

    # Save enriched final draft with globally renumbered citations
    with open(output_dir / "4-final-draft.md", "w") as f:
        f.write(enriched_content)

    # Count unique citations after renumbering
    total_citations_after = len(set(re.findall(r'\[\^(\d+)\]', enriched_content)))
    print(f"✓ Citation renumbering complete: {total_citations_after} unique citations (from {total_citations_before_renumber} section citations)")

    # Update state
    from ..state import SectionDraft
    enriched_sections = {
        "full_memo": SectionDraft(
            section_name="full_memo",
            content=enriched_content,
            word_count=len(enriched_content.split()),
            citations=extract_citation_count(enriched_content)
        )
    }

    return {
        "draft_sections": enriched_sections,
        "messages": [f"Citations added to memo for {company_name}: {total_citations_after} unique citations"]
    }


def renumber_citations_globally(sections_data: list) -> str:
    """
    Renumber citations globally across all sections.

    Each section comes with its own [^1], [^2], etc. This function
    renumbers them sequentially across the entire memo so each unique
    source gets a globally unique citation number.

    Args:
        sections_data: List of tuples (section_num, section_name, section_content)

    Returns:
        Combined content with globally renumbered citations
    """
    combined_content = ""
    citation_counter = 1
    citation_map = {}  # Maps (section_idx, old_num) -> new_num

    # First pass: Renumber inline citations and build mapping
    for idx, (section_num, section_name, section_content) in enumerate(sections_data):
        # Split content from citations
        parts = section_content.split("### Citations")
        main_content = parts[0] if parts else section_content
        citations_section = parts[1] if len(parts) > 1 else ""

        # Find all citation numbers in this section
        old_citations = set(re.findall(r'\[\^(\d+)\]', section_content))

        # Create mapping for this section
        section_map = {}
        for old_num in sorted(old_citations, key=int):
            section_map[old_num] = citation_counter
            citation_map[(idx, old_num)] = citation_counter
            citation_counter += 1

        # Renumber inline citations in main content
        for old_num, new_num in section_map.items():
            # Replace inline citations [^X] with [^NEW]
            main_content = re.sub(
                rf'\[\^{old_num}\]',
                f'[^{new_num}]',
                main_content
            )

        # Renumber citations in the reference list
        if citations_section:
            for old_num, new_num in section_map.items():
                # Replace citation definitions [^X]: with [^NEW]:
                citations_section = re.sub(
                    rf'\[\^{old_num}\]:',
                    f'[^{new_num}]:',
                    citations_section
                )

        # Reconstruct section with renumbered citations
        if citations_section:
            section_content = main_content + "### Citations" + citations_section
        else:
            section_content = main_content

        # Add to combined content
        combined_content += f"## {section_num}. {section_name}\n\n{section_content}\n\n"

    return combined_content


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

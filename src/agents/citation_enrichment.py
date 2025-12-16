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
6. EVERY citation MUST include the full URL wrapped as a markdown link in the title
7. Generate a comprehensive citation list at the end in this exact format:

### Citations

[^1]: YYYY, MMM DD. Author Name. [Source Title](https://full-url-here.com). Publisher or Outlet Name.Published: YYYY-MM-DD | Updated: YYYY-MM-DD

[^2]: YYYY, MMM DD. Author Name. [Source Title](https://full-url-here.com). Publisher or Outlet Name. Published: YYYY-MM-DD | Updated: N/A

IMPORTANT FORMATTING:
- DD must ALWAYS be two digits with zero-padding (e.g., "Jan 08" not "Jan 8", "Mar 03" not "Mar 3")
- ALWAYS wrap the title in a markdown link: [Title](URL) - this makes the source clickable
- Publisher or Outlet Name should be included after the title, if available.
- Author Name is mostly relevant for articles or blog posts, not press releases or company websites. So, use judgement call when including it.
- ALWAYS include "Updated:" field - use "Updated: N/A" if source has no update date
- ALWAYS include "Published:" field with actual date
- The format MUST be: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD or N/A
- DO NOT add "URL: https://..." at the end - the URL goes inside the markdown link
- No space before colon in "[^1]:"
- Exactly one space after colon before text begins

WHAT TO CITE:
- Funding amounts and rounds (cite Crunchbase, PitchBook, press releases)
- Company founding date, location, team info (cite company website, LinkedIn, Crunchbase, early media coverage)
- Market sizing and TAM figures (cite industry reports, analyst firms, gold standard journalism sources like Wall Street Journal, Financial Times, etc)
- Technical specifications and product details (cite company announcements, technical docs)
- Traction metrics and milestones (cite company blog, press releases, news articles, included RAG materials)
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
3. Multiple citations separated by space: "text. [^1] [^2]"
4. EVERY citation MUST have URL wrapped in markdown link
5. Format: [^1]: YYYY, MMM DD. [Title](https://url.com). Published: YYYY-MM-DD | Updated: N/A

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

    Enriches each section independently with citations by loading from section files.

    Args:
        state: Current memo state

    Returns:
        Updated state with citation-enriched sections
    """
    company_name = state["company_name"]
    firm = state.get("firm")

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
        from ..utils import get_output_dir_from_state

        # Use default_headers to set User-Agent (bypasses Cloudflare)
        perplexity_client = OpenAI(
            api_key=perplexity_key,
            base_url="https://api.perplexity.ai",
            default_headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
    except ImportError:
        print("Warning: openai package not installed, skipping citation enrichment")
        return {
            "messages": ["Citation enrichment skipped - openai package not installed"]
        }

    # Get output directory (respects state["output_dir"] for resume, falls back to auto-detect)
    try:
        output_dir = get_output_dir_from_state(state)
        sections_dir = output_dir / "2-sections"
    except FileNotFoundError:
        print("Warning: No output directory found, skipping citation enrichment")
        return {"messages": ["Citation enrichment skipped - no output directory"]}

    if not sections_dir.exists():
        print("Warning: No sections directory found, skipping citation enrichment")
        return {"messages": ["Citation enrichment skipped - no sections found"]}

    print(f"\n📚 Enriching citations section-by-section...")

    # Load all section files
    section_files = sorted(sections_dir.glob("*.md"))
    sections_data = []  # Store (section_num, section_name, enriched_content)
    total_citations_before_renumber = 0

    # Check if using 12Ps outline (scorecard section will be generated separately)
    outline_name = state.get("outline_name", "")
    is_12ps_outline = "12Ps" in outline_name or "12ps" in outline_name

    for section_file in section_files:
        section_name = section_file.stem.split("-", 1)[1].replace("--", " & ").replace("-", " ").title()

        # Skip scorecard section for 12Ps outlines - it will be replaced by scorecard agent
        if is_12ps_outline and ("scorecard" in section_file.stem.lower() or section_file.stem.startswith("08-")):
            print(f"  ⏭️  Skipping {section_name} (will be replaced by scorecard agent)")
            # Still include in sections_data for final assembly
            with open(section_file) as f:
                section_content = f.read()
            section_num = section_file.stem.split("-")[0]
            sections_data.append((section_num, section_name, section_content))
            continue

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

    # Check if header.md exists (created by trademark enrichment agent)
    header_file = output_dir / "header.md"
    if header_file.exists():
        with open(header_file) as f:
            header_content = f.read()
        enriched_content = header_content + "\n"
    else:
        enriched_content = f"# Investment Memo: {company_name}\n\n"

    enriched_content += renumber_citations_globally(sections_data)

    # Save enriched final draft with globally renumbered citations
    from ..final_draft import write_final_draft
    final_draft_path = write_final_draft(output_dir, enriched_content)

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
    Renumber citations globally across all sections and consolidate into ONE citation block.

    Each section comes with its own citations (both numeric like [^1] and
    alphanumeric like [^deck], [^ehrtime]). This function:
    1. Renumbers ALL citations sequentially across the entire memo
    2. Strips citation blocks from individual sections
    3. Consolidates all citations into ONE block at the end

    Special handling for canonical citations like [^deck]:
    - Same key across sections maps to ONE citation number
    - Only the FIRST definition encountered is kept (no duplicates)

    Args:
        sections_data: List of tuples (section_num, section_name, section_content)

    Returns:
        Combined content with globally renumbered citations and ONE citation block
    """
    combined_content = ""
    citation_definitions = {}  # Map citation number -> definition (keeps first only)
    citation_counter = 1
    global_citation_map = {}  # Track citation key -> number across sections

    # Process each section
    for idx, (section_num, section_name, section_content) in enumerate(sections_data):
        # Split content from citations
        parts = section_content.split("### Citations")
        main_content = parts[0].strip() if parts else section_content.strip()
        citations_section = parts[1].strip() if len(parts) > 1 else ""

        # Strip leading # header from section content (we add our own numbered header)
        # Matches: "# Section Name" or "# Section Name\n" at the start
        main_content = re.sub(r'^#\s+[^\n]+\n*', '', main_content, count=1).strip()

        # Demote subsection headers: ## -> ### (since we add ## for main section header)
        # This ensures proper hierarchy: ## Section Name > ### Subsection
        main_content = re.sub(r'^## ', '### ', main_content, flags=re.MULTILINE)

        # Find ALL citation keys in this section's content (both numeric and alphanumeric)
        # Matches: [^1], [^deck], [^ehrtime], [^3b], etc.
        old_citations = set(re.findall(r'\[\^([a-zA-Z0-9_]+)\]', main_content))

        # Create mapping for this section's citations
        section_map = {}
        # Sort: numeric first (by value), then alphanumeric (alphabetically)
        def sort_key(x):
            try:
                return (0, int(x), '')
            except ValueError:
                return (1, 0, x)

        for old_key in sorted(old_citations, key=sort_key):
            # Check if we've already assigned a number to this citation key globally
            if old_key not in global_citation_map:
                global_citation_map[old_key] = citation_counter
                citation_counter += 1
            section_map[old_key] = global_citation_map[old_key]

        # Renumber inline citations in main content
        # Process longer keys first to avoid partial replacements (e.g., [^3b] before [^3])
        for old_key in sorted(section_map.keys(), key=len, reverse=True):
            new_num = section_map[old_key]
            # Replace inline citations [^key] with [^NEW]
            main_content = re.sub(
                rf'\[\^{re.escape(old_key)}\]',
                f'[^{new_num}]',
                main_content
            )

        # Collect citation definitions (keep FIRST definition per citation number)
        if citations_section:
            for old_key, new_num in section_map.items():
                # Skip if we already have a definition for this citation number
                # This handles canonical citations like [^deck] that appear in multiple sections
                if new_num in citation_definitions:
                    continue

                # Find citation definition lines (handles multi-line definitions)
                citation_pattern = rf'\[\^{re.escape(old_key)}\]:.*?(?=\n\[\^|\Z)'
                matches = re.findall(citation_pattern, citations_section, re.DOTALL)
                if matches:
                    # Renumber the citation definition
                    renumbered = re.sub(
                        rf'\[\^{re.escape(old_key)}\]:',
                        f'[^{new_num}]:',
                        matches[0].strip()
                    )
                    citation_definitions[new_num] = renumbered

        # Add section to combined content (WITHOUT citations block)
        combined_content += f"## {section_num}. {section_name}\n\n{main_content}\n\n---\n\n"

    # Sort citations by number and build final list
    all_citations = [citation_definitions[num] for num in sorted(citation_definitions.keys())]

    # Add ONE consolidated citation block at the end
    if all_citations:
        combined_content += "### Citations\n\n"
        combined_content += "\n\n".join(all_citations)
        combined_content += "\n"

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

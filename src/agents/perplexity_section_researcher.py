"""
Perplexity Section Researcher Agent

Generates section-specific research WITH citations using Perplexity Sonar Pro.
This agent runs BEFORE the writer agent, creating research files that the writer
will polish while preserving all citations.

This is the integrated version of the POC approach.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI

from ..state import MemoState
from ..outline_loader import load_outline_for_state
from ..utils import get_latest_output_dir
from ..artifacts import sanitize_filename
from ..versioning import VersionManager


# Perplexity Research System Prompt
PERPLEXITY_RESEARCH_SYSTEM_PROMPT = """You are an investment research specialist conducting in-depth analysis for investment memos.

Your task is to research and write comprehensive content for a specific section with citations.

CRITICAL REQUIREMENTS:
1. Use ONLY current, verifiable information from authoritative sources
2. Add inline citations [^1], [^2], [^3] for EVERY factual claim
3. MINIMUM 5-10 DIVERSE SOURCES (mix of analyst reports, news, company sources)
4. Focus on specific data: numbers, growth rates, names, recent events with dates
5. Prioritize quality sources:
   - Industry analyst reports (Gartner, CB Insights, McKinsey, IDC, Forrester)
   - Financial news (Bloomberg, WSJ, Reuters, FT)
   - Tech journalism (TechCrunch, The Information, Protocol, Axios)
   - Company filings and press releases
6. Include dates with all data (e.g., "TAM of $50B in 2024")

CITATION FORMAT (Obsidian-style) - FOLLOW EXACTLY:
- Place citations AFTER punctuation: "Market size is $50B. [^1]" NOT "size is $50B[^1]."
- Always include ONE SPACE before each citation marker
- Multiple citations: "Growing at 20% CAGR. [^1] [^2]" (space before each)
- Examples:
  CORRECT: "The market reached $50B. [^1]"
  CORRECT: "TAM is $100B. [^1] [^2]"
  WRONG: "The market reached $50B[^1]."
  WRONG: "TAM is $100B.[^1][^2]"

CITATION LIST FORMAT (at end):
### Citations

[^1]: YYYY, MMM DD. [Source Title](https://full-url.com). Publisher. Published: YYYY-MM-DD | Updated: N/A

[^2]: YYYY, MMM DD. Author Name. [Source Title](https://url.com). Publisher. Published: YYYY-MM-DD | Updated: YYYY-MM-DD

IMPORTANT:
- ALWAYS use two-digit day format: "Jan 08" not "Jan 8", "Mar 03" not "Mar 3"
- ALWAYS wrap title in markdown link: [Title](URL)
- ALWAYS include Published and Updated fields
- Use "Updated: N/A" if no update date available
- NO SPACE before colon in "[^1]:" in citation list

OUTPUT: Research content with inline citations (with space before bracket, after punctuation), followed by complete Citations section with 5-10 sources."""


def build_section_research_query(
    section_def: Any,
    company_name: str,
    company_description: str,
    general_research: Dict[str, Any],
    memo_mode: str
) -> str:
    """
    Build section-specific research query using outline guidance.

    Args:
        section_def: Section definition from outline
        company_name: Company name
        company_description: Brief description
        general_research: General research data from Tavily
        memo_mode: "consider" or "justify"

    Returns:
        Research query for Perplexity
    """
    # Extract guiding questions from outline
    questions_text = "\n".join(f"- {q}" for q in section_def.guiding_questions[:10])

    # Extract relevant research context based on section
    section_context = ""
    if "Market" in section_def.name:
        market_data = general_research.get("market", {})
        if market_data:
            section_context = f"\nPRELIMINARY DATA (verify with current sources):\n{market_data}"
    elif "Team" in section_def.name:
        team_data = general_research.get("team", {})
        if team_data:
            section_context = f"\nPRELIMINARY DATA (verify with current sources):\n{team_data}"
    elif "Funding" in section_def.name or "Terms" in section_def.name:
        funding_data = general_research.get("funding", {})
        if funding_data:
            section_context = f"\nPRELIMINARY DATA (verify with current sources):\n{funding_data}"

    query = f"""Research and write comprehensive content for the "{section_def.name}" section of an investment memo about {company_name}.

COMPANY OVERVIEW:
{company_description}
{section_context}

SECTION GUIDANCE - Address these questions with specific data and citations:
{questions_text}

RESEARCH REQUIREMENTS:
- Cite EVERY number, growth rate, claim, and market fact with [^1] [^2] etc.
- Use current data (2024-2025 preferred, nothing older than 2022 unless historical context)
- Name specific companies, people, products - not "several players" or "industry leaders"
- Include dates with all statistics: "TAM of $X in 2024" not just "$X TAM"
- Prioritize analyst reports and financial journalism sources
- MINIMUM 5-10 diverse sources required

MEMO MODE: {"This is justifying an EXISTING investment (retrospective)" if memo_mode == "justify" else "This is evaluating a POTENTIAL investment (prospective)"}

Write {section_def.target_length.ideal_words}-{section_def.target_length.max_words} words with comprehensive inline citations.

Include complete citation list at the end in the specified format."""

    return query


def perplexity_section_researcher_agent(state: MemoState) -> Dict[str, Any]:
    """
    Generate section-specific research with citations using Perplexity Sonar Pro.

    This agent runs BEFORE the writer agent, creating research files for each section
    that include inline citations and citation lists. The writer will then polish
    these research files while preserving all citations.

    Args:
        state: Current memo state

    Returns:
        Updated state with section research completed
    """
    company_name = state["company_name"]
    company_description = state.get("company_description", "")
    general_research = state.get("research", {})
    memo_mode = state.get("memo_mode", "consider")

    # Load outline to get section definitions
    outline = load_outline_for_state(state)

    # Check for Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        print("⚠️  PERPLEXITY_API_KEY not set - skipping section research")
        return {
            "messages": ["Skipped section research - no Perplexity API key"]
        }

    # Initialize Perplexity client
    client = OpenAI(
        api_key=perplexity_key,
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    )

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name)
    except FileNotFoundError:
        # Create new version if no existing output
        version_mgr = VersionManager(Path("output"))
        safe_name = sanitize_filename(company_name)
        version = version_mgr.get_next_version(safe_name)
        output_dir = Path("output") / f"{safe_name}-{version}"
        output_dir.mkdir(parents=True, exist_ok=True)

    # Create research directory
    research_dir = output_dir / "1-research"
    research_dir.mkdir(exist_ok=True)

    print(f"\n{'='*70}")
    print(f"🔍 PERPLEXITY SECTION RESEARCH")
    print(f"{'='*70}")
    print(f"Company: {company_name}")
    print(f"Sections: {len(outline.sections)}")
    print(f"Output: {research_dir}")
    print(f"{'='*70}\n")

    # Research each section
    total_citations = 0
    sections_completed = 0

    for section_def in outline.sections:
        section_num = section_def.number
        section_name = section_def.name
        section_filename = section_def.filename.replace(".md", "-research.md")

        print(f"  [{section_num}/10] {section_name}")
        print(f"      Target: {section_def.target_length.ideal_words} words | Questions: {len(section_def.guiding_questions)}")

        # Build query
        query = build_section_research_query(
            section_def=section_def,
            company_name=company_name,
            company_description=company_description,
            general_research=general_research,
            memo_mode=memo_mode
        )

        print(f"      Calling Perplexity Sonar Pro...")

        try:
            # Call Perplexity Sonar Pro
            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": PERPLEXITY_RESEARCH_SYSTEM_PROMPT},
                    {"role": "user", "content": query}
                ],
                temperature=0.2,
                max_tokens=4000
            )

            research_content = response.choices[0].message.content

            # Count citations
            citations = re.findall(r'\[\^(\d+)\]', research_content)
            citation_count = len(set(citations))

            # Validate minimum citations
            MIN_CITATIONS = 5
            if citation_count < MIN_CITATIONS:
                print(f"      ⚠️  WARNING: Only {citation_count} citations (minimum: {MIN_CITATIONS})")
                print(f"      Proceeding but quality may be lower than expected")

            # Save research file
            research_file = research_dir / section_filename
            research_file.write_text(research_content)

            print(f"      ✓ Complete: {citation_count} citations, {len(research_content.split())} words")
            print(f"      Saved: {section_filename}")

            total_citations += citation_count
            sections_completed += 1

        except Exception as e:
            print(f"      ❌ Error: {e}")
            print(f"      Skipping section - writer will work without section research")
            continue

    print(f"\n{'='*70}")
    print(f"✅ SECTION RESEARCH COMPLETE")
    print(f"{'='*70}")
    print(f"Sections researched: {sections_completed}/10")
    print(f"Total citations: {total_citations}")
    print(f"Average per section: {total_citations/sections_completed:.1f}" if sections_completed > 0 else "N/A")
    print(f"Research files: {research_dir}")
    print(f"{'='*70}\n")

    return {
        "messages": [f"Section research complete: {sections_completed}/10 sections, {total_citations} citations"]
    }

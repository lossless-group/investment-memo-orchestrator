#!/usr/bin/env python3
"""
Proof of Concept: Perplexity Section-Specific Research

Tests the new architecture:
1. Perplexity Sonar Pro generates section-specific research WITH citations
2. Claude polishes that research into final section

Focus: Market Context section (most research-dependent)
"""

import os
import sys
from pathlib import Path
from openai import OpenAI
from langchain_anthropic import ChatAnthropic
from datetime import datetime
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from outline_loader import load_outline
from artifacts import sanitize_filename
from versioning import VersionManager


# Perplexity Research System Prompt
PERPLEXITY_RESEARCH_SYSTEM_PROMPT = """You are an investment research specialist conducting in-depth market analysis.

Your task is to research and write a comprehensive Market Context section for an investment memo.

CRITICAL REQUIREMENTS:
1. Use ONLY current, verifiable information from authoritative sources
2. Add inline citations [^1], [^2], [^3] for EVERY factual claim
3. MINIMUM 5-10 DIVERSE SOURCES (mix of analyst reports, news, company sources)
4. Focus on specific data: market size numbers, growth rates, competitor names, recent events
5. Prioritize quality sources:
   - Industry analyst reports (Gartner, CB Insights, McKinsey, IDC)
   - Financial news (Bloomberg, WSJ, Reuters, FT)
   - Tech journalism (TechCrunch, The Information, Protocol)
   - Company filings and press releases
6. Include dates with all market data (e.g., "TAM of $50B in 2024")

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


# Claude Polishing System Prompt
CLAUDE_POLISHING_SYSTEM_PROMPT = """You are an investment analyst polishing research into a professional memo section.

Your task is to rewrite Perplexity research into a polished "Market Context" section.

CRITICAL RULES:
1. PRESERVE all citations [^1], [^2], [^3] EXACTLY as they appear (including spacing)
2. PRESERVE citation format: space before bracket, after punctuation (". [^1]" not ".[^1]")
3. PRESERVE the entire "### Citations" section at the end - DO NOT REMOVE IT
4. DO NOT remove or alter citation numbers
5. DO NOT add new factual claims without citations
6. Improve flow, coherence, and structure
7. Match Hypernova style: analytical, specific, balanced
8. Use bullet points for scannability
9. Organize into logical subsections

WHAT YOU CAN CHANGE:
- Sentence structure and phrasing
- Organization and flow
- Transitions between paragraphs
- Headers and subsections (e.g., "Market Size & Growth", "Competitive Landscape")
- Formatting (bullets, emphasis)

WHAT YOU CANNOT CHANGE:
- Citation markers [^1] [^2] - keep spacing and position
- The "### Citations" section at the end - MUST be included in output
- Citation format: ". [^1]" (space before bracket, after punctuation)
- Specific numbers or dates
- Source attribution
- Core factual claims

CRITICAL: Your output MUST include:
1. Polished section content with preserved citations
2. The complete "### Citations" section from the input

OUTPUT FORMAT:
<polished content with citations>

### Citations

<complete citation list from input>"""


def build_market_context_query(
    company_name: str,
    company_description: str,
    general_research: dict,
    section_def: dict
) -> str:
    """
    Build a comprehensive research query for Market Context section.

    Args:
        company_name: Company name
        company_description: Brief company description
        general_research: General research data from Tavily
        section_def: Section definition from outline (guiding questions)

    Returns:
        Research query for Perplexity
    """
    # Extract guiding questions from section definition
    questions = section_def.get("guiding_questions", [])
    questions_text = "\n".join(f"- {q}" for q in questions[:8])  # Top 8 questions

    # Extract market context from general research (if available)
    market_data = general_research.get("market", {})
    market_context = json.dumps(market_data, indent=2) if market_data else "No preliminary data"

    query = f"""Research the market context for {company_name} ({company_description}) and write a comprehensive Market Context section with citations.

COMPANY OVERVIEW:
{company_description}

PRELIMINARY RESEARCH (may be outdated - verify with current sources):
{market_context}

SECTION GUIDANCE - Address these questions with specific data and citations:
{questions_text}

RESEARCH REQUIREMENTS:
1. Current market size (TAM, SAM, SOM) with specific dollar figures and dates
2. Market growth rate (CAGR) with timeframe
3. Key market drivers and trends (with dates)
4. Competitive landscape (name specific companies and market share if available)
5. Market dynamics (regulatory changes, technological shifts, consumer behavior)
6. Recent industry events or inflection points (last 12-24 months)

CRITICAL:
- Cite EVERY number, growth rate, and market claim with [^1] [^2] etc.
- Use current data (2024-2025 preferred, nothing older than 2022 unless historical context)
- Name specific competitors, not just "several players"
- Include dates with all statistics: "TAM of $X in 2024" not just "$X TAM"
- Prioritize analyst reports and financial journalism sources

Write 400-600 words with comprehensive inline citations. Format with subsections for readability.

Include citation list at the end in the specified format."""

    return query


def perplexity_section_research(
    company_name: str,
    company_description: str,
    general_research: dict,
    section_def: dict,
    output_dir: Path
) -> str:
    """
    Generate section-specific research using Perplexity Sonar Pro.

    Args:
        company_name: Company name
        company_description: Brief description
        general_research: General research data
        section_def: Section definition from outline
        output_dir: Output directory for artifacts

    Returns:
        Research content with citations
    """
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        raise ValueError("PERPLEXITY_API_KEY not set")

    # Initialize Perplexity client with User-Agent header
    client = OpenAI(
        api_key=perplexity_key,
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    )

    # Build research query
    query = build_market_context_query(
        company_name=company_name,
        company_description=company_description,
        general_research=general_research,
        section_def=section_def
    )

    print(f"\n{'='*70}")
    print(f"🔍 PERPLEXITY SECTION RESEARCH: Market Context")
    print(f"{'='*70}")
    print(f"Company: {company_name}")
    print(f"Query length: {len(query)} chars")
    print(f"\nCalling Perplexity Sonar Pro...")

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
    import re
    citations = re.findall(r'\[\^(\d+)\]', research_content)
    citation_count = len(set(citations))

    # VALIDATION: Check minimum citation requirement
    MIN_CITATIONS = 5
    if citation_count < MIN_CITATIONS:
        print(f"⚠️  WARNING: Only {citation_count} citations found (minimum: {MIN_CITATIONS})")
        print(f"❌ VALIDATION FAILED: Insufficient sources for quality research")
        print(f"\nThis would trigger:")
        print(f"  1. Validation agent rejects the research")
        print(f"  2. System calls improve-section.py to enhance citations")
        print(f"  3. OR retry with more specific queries")
        raise ValueError(
            f"Research quality insufficient: Only {citation_count} sources found (minimum: {MIN_CITATIONS}). "
            f"Need diverse sources from analyst reports, news, company data."
        )

    print(f"✓ Research complete")
    print(f"  Content length: {len(research_content)} chars")
    print(f"  Word count: {len(research_content.split())} words")
    print(f"  Citations found: {citation_count} ✓ (minimum: {MIN_CITATIONS})")

    # Save research artifact
    research_dir = output_dir / "1-research"
    research_dir.mkdir(parents=True, exist_ok=True)

    research_file = research_dir / "03-market-context-research.md"
    research_file.write_text(research_content)

    print(f"✓ Saved: {research_file}")
    print(f"{'='*70}\n")

    return research_content


def polish_research_with_claude(
    research_content: str,
    section_def: dict,
    company_name: str,
    output_dir: Path
) -> str:
    """
    Polish Perplexity research into final section using Claude.

    Args:
        research_content: Raw research with citations from Perplexity
        section_def: Section definition from outline
        company_name: Company name
        output_dir: Output directory

    Returns:
        Polished section content
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    model = ChatAnthropic(
        model="claude-sonnet-4-5-20250929",
        api_key=api_key,
        temperature=0.5,
        max_tokens=4000
    )

    target_words = section_def.get("target_length", {}).get("ideal_words", 500)

    # Count citations in research to inform prompt
    import re
    citations_before = len(set(re.findall(r'\[\^(\d+)\]', research_content)))

    polish_prompt = f"""Rewrite the following Perplexity research into a polished "Market Context" section for {company_name}.

PERPLEXITY RESEARCH (with citations):
{research_content}

SECTION REQUIREMENTS:
- Target length: {target_words} words
- Analytical tone (not promotional)
- Organized with clear subsections
- Scannable (use bullets where appropriate)

CITATION PRESERVATION (CRITICAL - WILL BE VALIDATED):
- PRESERVE ALL {citations_before} CITATIONS EXACTLY - DO NOT REMOVE ANY
- Keep citation format: ". [^1]" (space before bracket, after punctuation)
- Keep ALL citation numbers [^1] through [^{citations_before}]
- DO NOT consolidate or remove "redundant" citations
- DO NOT renumber citations
- If a sentence has multiple citations [^1] [^2], keep ALL of them
- INCLUDE the complete "### Citations" section at the end

STRUCTURE SUGGESTIONS:
- Market Size & Growth
- Key Market Drivers
- Competitive Landscape
- Market Dynamics & Trends

WHAT YOU CAN DO:
- Reorder sentences and paragraphs
- Improve transitions and flow
- Add subsection headers
- Use bullet points for readability
- Rephrase for clarity

WHAT YOU CANNOT DO:
- Remove or change citation markers [^N]
- Remove the "### Citations" section
- Change citation format or spacing
- Add new factual claims without citations
- Change specific numbers or dates
- Consolidate multiple citations into one

VALIDATION: Your output will be checked to ensure ALL {citations_before} citations are preserved. If any are missing, the output will be rejected.

Output the polished section content (no section header "## 3. Market Context") followed by the complete "### Citations" section.
"""

    print(f"\n{'='*70}")
    print(f"✍️  CLAUDE POLISHING: Market Context")
    print(f"{'='*70}")
    print(f"Input length: {len(research_content)} chars")
    print(f"Target: {target_words} words")
    print(f"\nPolishing with Claude Sonnet 4.5...")

    response = model.invoke(polish_prompt)
    polished_content = response.content.strip()

    # Count citations before/after
    import re
    citations_before = len(set(re.findall(r'\[\^(\d+)\]', research_content)))
    citations_after = len(set(re.findall(r'\[\^(\d+)\]', polished_content)))

    # VALIDATION 1: Check citations preserved
    if citations_before != citations_after:
        print(f"⚠️  WARNING: Citation count mismatch!")
        print(f"   Before: {citations_before}, After: {citations_after}")
        print(f"❌ VALIDATION FAILED: Claude removed citations during polishing")
        raise ValueError(
            f"Citation preservation failed: {citations_before} citations in research, "
            f"but only {citations_after} in polished output. ALL citations must be preserved."
        )

    # VALIDATION 2: Check citation list section exists
    if "### Citations" not in polished_content:
        print(f"⚠️  WARNING: Citation list section missing!")
        print(f"❌ VALIDATION FAILED: Claude removed '### Citations' section")
        raise ValueError(
            "Citation list missing: Polished output must include the complete '### Citations' section "
            "from the research input."
        )

    # VALIDATION 3: Check citation format (spot check)
    bad_format = re.findall(r'[^\.]\s?\[\^', polished_content)
    if bad_format:
        print(f"⚠️  WARNING: Possible citation format issues detected")
        print(f"   Found patterns that may not follow '. [^N]' format")

    print(f"✓ Polishing complete")
    print(f"  Output length: {len(polished_content)} chars")
    print(f"  Word count: {len(polished_content.split())} words")
    print(f"  Citations: {citations_before} → {citations_after} ✓ (preserved)")
    print(f"  Citation list: ✓ (present)")

    # Save polished section
    sections_dir = output_dir / "2-sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    section_file = sections_dir / "03-market-context.md"
    section_file.write_text(polished_content)

    print(f"✓ Saved: {section_file}")
    print(f"{'='*70}\n")

    return polished_content


def main():
    """Run POC for Market Context section."""

    # Configuration
    company_name = "Avalanche"  # Test company
    company_description = "Enterprise data infrastructure platform for real-time analytics"

    # Simulate general research data (would come from Tavily in real workflow)
    general_research = {
        "market": {
            "tam": "Data infrastructure market",
            "growth_rate": "Growing rapidly",
            "dynamics": ["Cloud adoption", "Real-time analytics demand"]
        }
    }

    # Load outline to get Market Context section definition
    outline = load_outline("direct")
    market_context_section = next(
        s for s in outline.sections if s.name == "Market Context"
    )

    # Convert to dict for easier access
    section_def = {
        "name": market_context_section.name,
        "guiding_questions": market_context_section.guiding_questions,
        "target_length": {
            "ideal_words": market_context_section.target_length.ideal_words
        }
    }

    # Setup output directory
    version_mgr = VersionManager(Path("output"))
    safe_name = sanitize_filename(company_name)
    version = version_mgr.get_next_version(safe_name)
    output_dir = Path("output") / f"{safe_name}-{version}-POC"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'#'*70}")
    print(f"# POC: Perplexity Section Research → Claude Polishing")
    print(f"# Company: {company_name}")
    print(f"# Section: Market Context")
    print(f"# Output: {output_dir}")
    print(f"{'#'*70}\n")

    try:
        # STEP 1: Perplexity generates research with citations
        research_content = perplexity_section_research(
            company_name=company_name,
            company_description=company_description,
            general_research=general_research,
            section_def=section_def,
            output_dir=output_dir
        )

        # STEP 2: Claude polishes research into final section
        polished_content = polish_research_with_claude(
            research_content=research_content,
            section_def=section_def,
            company_name=company_name,
            output_dir=output_dir
        )

        # Summary
        print(f"\n{'='*70}")
        print(f"✅ POC COMPLETE")
        print(f"{'='*70}")
        print(f"\nArtifacts saved:")
        print(f"  Research: {output_dir / '1-research' / '03-market-context-research.md'}")
        print(f"  Polished: {output_dir / '2-sections' / '03-market-context.md'}")
        print(f"\nNext steps:")
        print(f"  1. Review research quality and citation accuracy")
        print(f"  2. Verify Claude preserved all citations")
        print(f"  3. Compare cost/quality vs current approach")
        print(f"  4. If successful, expand to all 10 sections")
        print(f"{'='*70}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

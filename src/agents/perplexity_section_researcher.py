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
from typing import Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

from ..state import MemoState
from ..outline_loader import load_outline_for_state
from ..utils import get_latest_output_dir
from ..artifacts import sanitize_filename
from ..versioning import VersionManager


# Perplexity Research System Prompt
PERPLEXITY_RESEARCH_SYSTEM_PROMPT = """You are an investment research specialist gathering facts for investment memos.

Your task is to research and compile factual content for a specific section with citations.

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

DECK ANALYSIS HANDLING:
- If DECK ANALYSIS content is provided, it contains claims from the company's pitch deck
- Cite deck claims using [^deck] and verify them with external sources where possible
- If external verification contradicts the deck, note the discrepancy explicitly
- If a deck claim cannot be verified externally, include it with "[^deck]" and note "per company deck"
- Deck is a PRIMARY source for company-specific claims (team, product, funding terms)

CITATION FORMAT (Obsidian-style) - FOLLOW EXACTLY:
- Place citations AFTER punctuation: "Market size is $50B. [^1]" NOT "size is $50B[^1]."
- Always include ONE SPACE before each citation marker
- Multiple citations: "Growing at 20% CAGR. [^1] [^2]" (space before each)
- Examples:
  CORRECT: "The market reached $50B. [^1]"
  CORRECT: "TAM is $100B. [^1] [^2]"
  CORRECT: "The team includes 6 engineers. [^deck]"
  WRONG: "The market reached $50B[^1]."
  WRONG: "TAM is $100B.[^1][^2]"

CITATION LIST FORMAT (at end):
### Citations

[^deck]: 2025. [Company Pitch Deck](internal-document). Company Materials. Published: 2025 | Updated: N/A

[^1]: YYYY, MMM DD. [Source Title](https://full-url.com). Publisher. Published: YYYY-MM-DD | Updated: N/A

[^2]: YYYY, MMM DD. Author Name. [Source Title](https://url.com). Publisher. Published: YYYY-MM-DD | Updated: YYYY-MM-DD

IMPORTANT:
- ALWAYS use two-digit day format: "Jan 08" not "Jan 8", "Mar 03" not "Mar 3"
- ALWAYS wrap title in markdown link: [Title](URL)
- ALWAYS include Published and Updated fields
- Use "Updated: N/A" if no update date available
- NO SPACE before colon in "[^1]:" in citation list
- Include [^deck] citation if deck content was used

VENTURE CAPITAL MINDSET (not Private Equity):
VCs look for reasons to INVEST, not reasons to PASS. Frame the narrative around opportunity.

- Lead with potential and upside - "What could go RIGHT?"
- Draw observations and conclusions - but frame as opportunity, not skepticism
- Acknowledge risks exist, but save detailed risk analysis for Section 8 (Risks & Mitigations)
- Do NOT end sections with skeptical wrap-ups ("However, the investment thesis depends on...")
- Do NOT add "Assessment" subsections that enumerate concerns or conditions to validate
- Do NOT frame the narrative around "what could go wrong" - that's PE thinking

OUTPUT: Research content with inline citations (with space before bracket, after punctuation), followed by complete Citations section with 5-10 sources (plus [^deck] if applicable)."""


def build_section_research_query(
    section_def: Any,
    company_name: str,
    company_description: str,
    general_research: Dict[str, Any],
    memo_mode: str,
    deck_draft_content: str = "",
    company_url: str = "",
    research_notes: str = "",
    disambiguation_excludes: list = None
) -> str:
    """
    Build section-specific research query using outline guidance.

    Args:
        section_def: Section definition from outline
        company_name: Company name
        company_description: Brief description
        general_research: General research data from Tavily
        memo_mode: "consider" or "justify"
        deck_draft_content: Optional draft content from deck analysis to verify/expand
        company_url: Company website URL for disambiguation
        research_notes: Additional research notes (may contain disambiguation hints)

    Returns:
        Research query for Perplexity
    """
    # Extract guiding questions from outline - prefer dimension-grouped if available
    questions_text = ""
    if hasattr(section_def, 'questions_by_dimension') and section_def.questions_by_dimension:
        # Use dimension-grouped format for richer context
        for dim_key, dim_q in section_def.questions_by_dimension.items():
            label = dim_q.dimension_label or dim_key.title()
            questions_text += f"\n### {label}\n"
            for q in dim_q.questions:
                questions_text += f"- {q}\n"
    else:
        # Fallback to flat list
        questions_text = "\n".join(f"- {q}" for q in section_def.guiding_questions[:10])

    # Extract section description and context from outline (CRITICAL for non-standard section names)
    section_description = ""
    if hasattr(section_def, 'description') and section_def.description:
        section_description = f"\nSECTION PURPOSE:\n{section_def.description.strip()}\n"

    # Extract group question if available (high-level framing)
    group_question = ""
    if hasattr(section_def, 'group_question') and section_def.group_question:
        group_question = f"\nCORE QUESTION THIS SECTION ANSWERS: {section_def.group_question}\n"

    # Extract dimensions being evaluated
    dimensions_text = ""
    if hasattr(section_def, 'dimensions') and section_def.dimensions:
        dims = ", ".join(section_def.dimensions)
        dimensions_text = f"\nDIMENSIONS TO EVALUATE: {dims}\n"

    # Extract required elements if available
    required_elements = ""
    structure_template = ""
    if hasattr(section_def, 'section_vocabulary') and section_def.section_vocabulary:
        vocab = section_def.section_vocabulary
        if hasattr(vocab, 'required_elements') and vocab.required_elements:
            elements = "\n".join(f"- {e}" for e in vocab.required_elements[:8])
            required_elements = f"\nREQUIRED ELEMENTS (must include):\n{elements}\n"
        # Extract structure template - this shows the expected subsection organization
        if hasattr(vocab, 'structure_template') and vocab.structure_template:
            template_lines = "\n".join(vocab.structure_template)
            structure_template = f"\nEXPECTED SECTION STRUCTURE:\n{template_lines}\n"

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

    # Include deck draft as citable source if available
    deck_context = ""
    if deck_draft_content:
        deck_context = f"""
DECK ANALYSIS (cite as "[^deck]: Company Pitch Deck" for claims from this source):
The following was extracted from the company's pitch deck. Use this as primary source material,
but verify claims with external sources where possible. If a claim cannot be externally verified,
cite it as "[^deck]" with note "per company pitch deck, unverified externally".

---
{deck_draft_content}
---
"""

    # Build disambiguation block if we have identifying info
    disambiguation_block = ""
    if company_url or research_notes or disambiguation_excludes:
        disambiguation_block = f"""
CRITICAL - ENTITY DISAMBIGUATION:
There may be multiple companies named "{company_name}". You MUST research the CORRECT company:
- Company website: {company_url or 'See description'}
- Description: {company_description}
"""
        if research_notes:
            disambiguation_block += f"- Research notes: {research_notes}\n"

        # Add explicit exclusion list for wrong entities
        if disambiguation_excludes and len(disambiguation_excludes) > 0:
            disambiguation_block += "\nEXCLUDED DOMAINS (WRONG COMPANIES - DO NOT USE):\n"
            for domain in disambiguation_excludes:
                disambiguation_block += f"- {domain} (WRONG company, different entity)\n"

        disambiguation_block += """
DISAMBIGUATION RULES:
1. ONLY use sources that reference THIS specific company
2. If you find funding/revenue data for a DIFFERENT company with the same name, DISCARD IT
3. Cross-reference company website to verify you have the correct entity
4. If a source is from an EXCLUDED DOMAIN listed above, ignore it completely
5. If unsure, state "Data not verified for this entity" rather than include wrong data
"""

    query = f"""Research and write comprehensive content for the "{section_def.name}" section of an investment memo about {company_name}.
{disambiguation_block}
COMPANY OVERVIEW:
{company_description}
{section_description}{group_question}{dimensions_text}{structure_template}{required_elements}{section_context}
{deck_context}

SECTION GUIDANCE - Address these questions with specific data and citations:
{questions_text}

RESEARCH REQUIREMENTS:
- Cite EVERY number, growth rate, claim, and market fact with [^1] [^2] etc.
- Use current data (2024-2025 preferred, nothing older than 2022 unless historical context)
- Name specific companies, people, products - not "several players" or "industry leaders"
- Include dates with all statistics: "TAM of $X in 2024" not just "$X TAM"
- Prioritize analyst reports and financial journalism sources
- MINIMUM 5-10 diverse sources required
- If deck analysis is provided above, incorporate and cite that information using [^deck]

MEMO MODE: {"This is justifying an EXISTING investment (retrospective)" if memo_mode == "justify" else "This is evaluating a POTENTIAL investment (prospective)"}

Write {section_def.target_length.ideal_words}-{section_def.target_length.max_words} words with comprehensive inline citations.

Include complete citation list at the end in the specified format."""

    return query


def _research_single_section(
    client: OpenAI,
    section_def: Any,
    company_name: str,
    company_description: str,
    company_url: str,
    research_notes: str,
    disambiguation_excludes: list,
    general_research: Dict[str, Any],
    memo_mode: str,
    deck_drafts: Dict[str, str],
    deck_drafts_by_topic: Dict[str, str],
    section_to_deck_topics: Dict[str, list],
    research_dir: Path
) -> Tuple[int, int, str, Optional[str]]:
    """
    Research a single section using Perplexity Sonar Pro.

    Returns:
        Tuple of (section_num, citation_count, section_name, error_message_or_None)
    """
    section_num = section_def.number
    section_name = section_def.name
    section_filename = section_def.filename.replace(".md", "-research.md")

    # Get deck draft for this section if available
    section_num_padded = f"{section_num:02d}"
    deck_draft_content = deck_drafts.get(section_num_padded, "")

    # If no numbered draft, try to find relevant topic-based drafts
    if not deck_draft_content and deck_drafts_by_topic:
        section_name_lower = section_name.lower()
        relevant_topics = []

        for keyword, topics in section_to_deck_topics.items():
            if keyword in section_name_lower:
                relevant_topics.extend(topics)

        matched_drafts = []
        for topic in set(relevant_topics):
            if topic in deck_drafts_by_topic:
                matched_drafts.append(f"### From Pitch Deck ({topic.title()})\n\n{deck_drafts_by_topic[topic]}")

        if matched_drafts:
            deck_draft_content = "\n\n---\n\n".join(matched_drafts)

    # Build query
    query = build_section_research_query(
        section_def=section_def,
        company_name=company_name,
        company_description=company_description,
        general_research=general_research,
        memo_mode=memo_mode,
        deck_draft_content=deck_draft_content,
        company_url=company_url,
        research_notes=research_notes,
        disambiguation_excludes=disambiguation_excludes
    )

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

        # Validate response is not garbage/meta-commentary
        GARBAGE_PATTERNS = [
            "I notice that you",
            "you haven't provided",
            "Let me fetch",
            "I need:",
            "please provide",
            "Which Stratosphere company",
            "Once you provide",
            "To help you properly",
            "contains only a header",
            "There are no organizations",
            "If you have the actual content",
        ]

        is_garbage = False
        word_count = len(research_content.split())

        if word_count < 200:
            is_garbage = True

        for pattern in GARBAGE_PATTERNS:
            if pattern.lower() in research_content.lower():
                is_garbage = True
                break

        # If garbage detected, retry with more explicit context
        if is_garbage:
            enhanced_query = f"""IMPORTANT: You must write actual research content, NOT ask clarifying questions.

The company is: {company_name}
{f'Company website: {company_url}' if company_url else ''}
Description: {company_description}

DO NOT say "I need more information" or "Let me fetch" - you have all the information you need.
DO NOT ask which company - the company is {company_name} as described above.

Write the ACTUAL CONTENT for the "{section_def.name}" section now.

{query}"""

            retry_response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": PERPLEXITY_RESEARCH_SYSTEM_PROMPT + "\n\nCRITICAL: Always write actual content. Never ask for clarification or say you need more info."},
                    {"role": "user", "content": enhanced_query}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            research_content = retry_response.choices[0].message.content

        # Count citations
        citations = re.findall(r'\[\^(\d+)\]', research_content)
        citation_count = len(set(citations))

        # Save research file
        research_file = research_dir / section_filename
        research_file.write_text(research_content)

        return (section_num, citation_count, section_name, None)

    except Exception as e:
        return (section_num, 0, section_name, str(e))


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
    firm = state.get("firm")
    company_description = state.get("company_description", "")
    company_url = state.get("company_url", "")
    research_notes = state.get("research_notes", "")
    disambiguation_excludes = state.get("disambiguation_excludes", [])
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

    # Get output directory (respects state["output_dir"] for resume, falls back to auto-detect or create)
    from ..utils import get_output_dir_from_state
    existing_output_dir = state.get("output_dir")
    if existing_output_dir:
        output_dir = Path(existing_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        try:
            output_dir = get_latest_output_dir(company_name, firm=firm)
        except FileNotFoundError:
            # Create new version if no existing output - firm-aware
            from ..paths import resolve_deal_context
            from ..artifacts import create_artifact_directory

            safe_name = sanitize_filename(company_name)

            if firm:
                ctx = resolve_deal_context(company_name, firm=firm)
                version_mgr = VersionManager(ctx.outputs_dir.parent if ctx.outputs_dir else Path("output"), firm=firm)
                version = version_mgr.get_next_version(safe_name)
                output_dir = create_artifact_directory(company_name, str(version), firm=firm)
            else:
                version_mgr = VersionManager(Path("output"))
                version = version_mgr.get_next_version(safe_name)
                output_dir = Path("output") / f"{safe_name}-{version}"
                output_dir.mkdir(parents=True, exist_ok=True)

    # Create research directory
    research_dir = output_dir / "1-research"
    research_dir.mkdir(exist_ok=True)

    # Load deck section drafts if available (from 0-deck-sections/)
    # New format: deck-{topic}.md (e.g., deck-team.md, deck-funding.md)
    # Old format: {num}-{section}.md (e.g., 09-funding-terms.md)
    deck_sections_dir = output_dir / "0-deck-sections"
    deck_drafts = {}
    deck_drafts_by_topic = {}  # Map topic keywords to content

    if deck_sections_dir.exists():
        for deck_file in deck_sections_dir.glob("*.md"):
            content = deck_file.read_text()
            filename = deck_file.stem

            # New format: deck-{topic}.md
            if filename.startswith("deck-"):
                topic = filename.replace("deck-", "")  # e.g., "team", "funding", "market"
                deck_drafts_by_topic[topic] = content
            else:
                # Old format: {num}-{section}.md - extract section number
                section_num_str = filename.split("-")[0]
                if section_num_str.isdigit():
                    deck_drafts[section_num_str] = content

        total_drafts = len(deck_drafts) + len(deck_drafts_by_topic)
        if total_drafts:
            print(f"📄 Loaded {total_drafts} deck section drafts:")
            for topic in deck_drafts_by_topic:
                print(f"    • deck-{topic}.md")

    # Map outline section concepts to deck draft topics
    SECTION_TO_DECK_TOPICS = {
        "executive": ["problem", "solution", "funding"],
        "summary": ["problem", "solution", "funding"],
        "origins": ["problem", "solution"],
        "opening": ["business-model", "product", "solution"],
        "organization": ["team"],
        "team": ["team"],
        "offering": ["product", "solution"],
        "product": ["product", "solution"],
        "technology": ["product", "solution"],
        "opportunity": ["market", "competitive"],
        "market": ["market", "competitive"],
        "traction": ["traction"],
        "milestones": ["traction"],
        "funding": ["funding"],
        "terms": ["funding"],
        "risks": ["competitive"],
        "scorecard": ["traction", "team", "market"],
        "closing": ["funding", "traction"],
        "assessment": ["funding", "traction"],
        "gtm": ["gtm"],
        "strategy": ["gtm", "competitive"],
    }

    # Parallel execution config
    # Using 5 workers to respect Perplexity rate limits while maximizing throughput
    MAX_WORKERS = 5

    print(f"\n{'='*70}")
    print(f"🔍 PERPLEXITY SECTION RESEARCH (PARALLEL)")
    print(f"{'='*70}")
    print(f"Company: {company_name}")
    print(f"Sections: {len(outline.sections)}")
    print(f"Deck drafts: {len(deck_drafts)} available")
    print(f"Max parallel workers: {MAX_WORKERS}")
    print(f"Output: {research_dir}")
    print(f"{'='*70}\n")

    # Research each section in parallel
    total_citations = 0
    sections_completed = 0
    results = {}  # Store results by section number for ordered output

    print(f"  Launching {len(outline.sections)} section research tasks in parallel...")
    print(f"  (Results will appear as they complete)\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all section research tasks
        future_to_section = {
            executor.submit(
                _research_single_section,
                client=client,
                section_def=section_def,
                company_name=company_name,
                company_description=company_description,
                company_url=company_url,
                research_notes=research_notes,
                disambiguation_excludes=disambiguation_excludes,
                general_research=general_research,
                memo_mode=memo_mode,
                deck_drafts=deck_drafts,
                deck_drafts_by_topic=deck_drafts_by_topic,
                section_to_deck_topics=SECTION_TO_DECK_TOPICS,
                research_dir=research_dir
            ): section_def
            for section_def in outline.sections
        }

        # Collect results as they complete
        for future in as_completed(future_to_section):
            section_def = future_to_section[future]
            try:
                section_num, citation_count, section_name, error = future.result()

                if error:
                    print(f"  ❌ [{section_num:02d}] {section_name}: {error}")
                else:
                    print(f"  ✓ [{section_num:02d}] {section_name}: {citation_count} citations")
                    total_citations += citation_count
                    sections_completed += 1
                    results[section_num] = citation_count

            except Exception as e:
                print(f"  ❌ [{section_def.number:02d}] {section_def.name}: Unexpected error: {e}")

    print(f"\n{'='*70}")
    print(f"✅ SECTION RESEARCH COMPLETE (PARALLEL)")
    print(f"{'='*70}")
    print(f"Sections researched: {sections_completed}/{len(outline.sections)}")
    print(f"Total citations: {total_citations}")
    print(f"Average per section: {total_citations/sections_completed:.1f}" if sections_completed > 0 else "N/A")
    print(f"Research files: {research_dir}")
    print(f"{'='*70}\n")

    return {
        "messages": [f"Section research complete: {sections_completed}/10 sections, {total_citations} citations"]
    }

"""
Deck Analyst Agent - Extracts key information from pitch decks.

This agent runs FIRST if a deck is available, creating initial section drafts
that subsequent agents can build upon.
"""

from pathlib import Path
from typing import Dict, List
from langchain_anthropic import ChatAnthropic
from pypdf import PdfReader
import json

from ..state import MemoState, DeckAnalysisData, SectionDraft


def deck_analyst_agent(state: Dict) -> Dict:
    """
    Analyzes pitch deck and extracts key information.

    CRITICAL: Only handles PDF decks for now. Image decks cause bottlenecks.
    Future: Add image deck support with optimization (resizing, compression).

    Args:
        state: Current memo state

    Returns:
        Updated state with deck_analysis and initial section drafts
    """
    deck_path = state.get("deck_path")

    if not deck_path or not Path(deck_path).exists():
        return {
            "deck_analysis": None,
            "messages": ["No deck available, skipping deck analysis"]
        }

    deck_file = Path(deck_path)

    # STEP 1: Extract text from PDF (pypdf)
    if deck_file.suffix.lower() == ".pdf":
        print(f"Extracting text from PDF deck ({deck_file.name})...")
        deck_content = extract_text_from_pdf(deck_path)
        print(f"Extracted {len(deck_content)} characters from deck")
    else:
        # For now, skip image decks to avoid bottleneck
        return {
            "deck_analysis": None,
            "messages": [f"Deck format {deck_file.suffix} not yet supported (images cause bottleneck)"]
        }

    # STEP 2: Analyze with Claude
    print("Analyzing deck content with Claude Sonnet 4.5...")
    llm = ChatAnthropic(
        model="claude-sonnet-4-5-20250929",
        temperature=0
    )

    analysis_prompt = f"""You are a venture capital investment analyst reviewing a pitch deck.

PITCH DECK CONTENT:
{deck_content}

Extract the following information in JSON format:
{{
  "company_name": "...",
  "tagline": "...",
  "problem_statement": "...",
  "solution_description": "...",
  "product_description": "...",
  "business_model": "...",
  "market_size": {{"TAM": "...", "SAM": "...", "SOM": "..."}},
  "traction_metrics": [{{"metric": "...", "value": "..."}}, ...],
  "team_members": [{{"name": "...", "role": "...", "background": "..."}}, ...],
  "funding_ask": "...",
  "use_of_funds": ["...", "..."],
  "competitive_landscape": "...",
  "go_to_market": "...",
  "milestones": ["...", "..."],
  "extraction_notes": ["List what info was found vs. missing"]
}}

IMPORTANT:
- Only include information explicitly stated in the deck
- Use "Not mentioned" if information is absent
- Capture specific numbers (revenue, users, growth rates)
- Note the deck's strengths and weaknesses in extraction_notes
- Return ONLY valid JSON, no other text
"""

    response = llm.invoke(analysis_prompt)
    print("Deck analysis complete, parsing results...")

    # Parse JSON from response
    try:
        deck_analysis = json.loads(response.content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        print("Extracting JSON from markdown code block...")
        content = response.content
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            content = content[json_start:json_end].strip()
        deck_analysis = json.loads(content)

    deck_analysis["deck_page_count"] = len(PdfReader(deck_path).pages)
    print(f"Extracted data from {deck_analysis['deck_page_count']}-page deck")

    # STEP 3: Create initial section drafts where relevant info exists
    print("Creating initial section drafts from deck data...")
    section_drafts = create_initial_section_drafts(deck_analysis, state, llm)
    print(f"Created {len(section_drafts)} initial section drafts")

    # STEP 4: Save artifacts
    from ..artifacts import save_deck_analysis_artifacts
    print("Saving deck analysis artifacts...")
    # Extract just the content strings for artifact saving
    section_drafts_for_disk = {k: v["content"] for k, v in section_drafts.items()}
    save_deck_analysis_artifacts(
        state["company_name"],
        deck_analysis,
        section_drafts_for_disk
    )

    return {
        "deck_analysis": deck_analysis,
        "draft_sections": section_drafts,  # Partial sections
        "messages": [f"Deck analysis complete: {deck_analysis['deck_page_count']} pages analyzed"]
    }


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using pypdf."""
    reader = PdfReader(pdf_path)
    text_content = []

    for page_num, page in enumerate(reader.pages, 1):
        page_text = page.extract_text()
        text_content.append(f"--- PAGE {page_num} ---\n{page_text}\n")

    return "\n".join(text_content)


def create_initial_section_drafts(deck_analysis: Dict, state: Dict, llm: ChatAnthropic) -> Dict[str, SectionDraft]:
    """
    Create draft sections based on deck content.
    Only creates sections where substantial info exists.

    Args:
        deck_analysis: Extracted deck data
        state: Current memo state
        llm: Language model for generating drafts

    Returns:
        Dictionary mapping section filenames to SectionDraft objects
    """
    drafts = {}

    # Map deck data to sections
    section_mapping = {
        "02-business-overview": ["problem_statement", "solution_description", "product_description"],
        "03-market-context": ["market_size", "competitive_landscape"],
        "04-technology-product": ["product_description", "solution_description"],
        "05-traction-milestones": ["traction_metrics", "milestones"],
        "06-team": ["team_members"],
        "07-funding-terms": ["funding_ask", "use_of_funds"],
        "09-investment-thesis": ["go_to_market", "competitive_landscape"]
    }

    for section_key, relevant_fields in section_mapping.items():
        # Check if deck has substantial info for this section
        has_info = any(
            deck_analysis.get(field) and
            deck_analysis[field] != "Not mentioned" and
            deck_analysis[field] != "" and
            deck_analysis[field] != [] and
            deck_analysis[field] != {}
            for field in relevant_fields
        )

        if has_info:
            section_name = section_key.replace("-", " ").title()
            content = create_section_draft_from_deck(
                llm,
                section_name,
                deck_analysis,
                relevant_fields
            )

            # Create proper SectionDraft object
            drafts[section_key] = SectionDraft(
                section_name=section_name,
                content=content,
                word_count=len(content.split()),
                citations=[]  # Citations will be added by citation enrichment agent
            )

    return drafts


def create_section_draft_from_deck(llm: ChatAnthropic, section_name: str, deck_data: Dict, fields: List[str]) -> str:
    """
    Generate a section draft from deck data.

    Args:
        llm: Language model for generating drafts
        section_name: Name of the section being drafted
        deck_data: Extracted deck data
        fields: Relevant fields for this section

    Returns:
        Draft section content in markdown
    """
    relevant_data = {k: deck_data.get(k) for k in fields if deck_data.get(k)}

    prompt = f"""Draft the "{section_name}" section for an investment memo based on this pitch deck data:

{json.dumps(relevant_data, indent=2)}

Write a concise, analytical section (200-400 words) that:
- Uses specific numbers and metrics from the deck
- Maintains analytical (not promotional) tone
- Notes data gaps explicitly (e.g., "Team backgrounds not disclosed in deck")
- Formats for readability (bullet points where appropriate)

This is an INITIAL DRAFT. The Research and Writer agents will augment with external data.

Return ONLY the section content in markdown format, no preamble.
"""

    response = llm.invoke(prompt)
    return response.content

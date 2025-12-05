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
import base64
import os
from anthropic import Anthropic
import fitz  # PyMuPDF
from io import BytesIO
from PIL import Image
from pptx import Presentation  # For PowerPoint files

from ..state import MemoState, DeckAnalysisData, SectionDraft
from ..outline_loader import load_outline_for_state


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

    # STEP 1: Extract text from deck (PDF or PowerPoint)
    deck_suffix = deck_file.suffix.lower()

    if deck_suffix == ".pdf":
        print(f"Extracting text from PDF deck ({deck_file.name})...", flush=True)
        deck_content = extract_text_from_pdf(deck_path)
        print(f"Extracted {len(deck_content)} characters from deck", flush=True)

        # If minimal text extracted, it's an image-based PDF - use Claude's PDF vision
        # Threshold of 1000 chars accounts for page headers (22 pages × ~17 chars = ~374 chars)
        # A text-based deck would have substantially more content
        if len(deck_content.strip()) < 1000:
            print("⚠️  Minimal text extracted - PDF appears to be image-based", flush=True)
            print("Using Claude's PDF vision to analyze deck...", flush=True)
            return analyze_pdf_with_vision(deck_path, state)

    elif deck_suffix in [".pptx", ".ppt"]:
        print(f"Extracting text from PowerPoint deck ({deck_file.name})...", flush=True)
        try:
            deck_content = extract_text_from_pptx(deck_path)
            print(f"Extracted {len(deck_content)} characters from {len(deck_content.split('--- SLIDE'))-1} slides", flush=True)

            if len(deck_content.strip()) < 500:
                print("⚠️  Minimal text extracted - PowerPoint may be mostly images", flush=True)
                print("Note: Image-only PowerPoint analysis not yet supported", flush=True)
                # Continue with what we have
        except Exception as e:
            return {
                "deck_analysis": None,
                "messages": [f"Error reading PowerPoint: {e}"]
            }
    else:
        # Unsupported format
        return {
            "deck_analysis": None,
            "messages": [f"Deck format {deck_suffix} not supported. Supported: .pdf, .pptx"]
        }

    # STEP 2: Analyze extracted text with Claude
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

    # Get page/slide count based on file type
    if deck_suffix == ".pdf":
        deck_analysis["deck_page_count"] = len(PdfReader(deck_path).pages)
    elif deck_suffix in [".pptx", ".ppt"]:
        deck_analysis["deck_page_count"] = len(Presentation(deck_path).slides)
    else:
        deck_analysis["deck_page_count"] = 0

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
    # Pass firm from state for firm-scoped output paths
    firm = state.get("firm")
    save_deck_analysis_artifacts(
        state["company_name"],
        deck_analysis,
        section_drafts_for_disk,
        firm=firm
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


def extract_text_from_pptx(pptx_path: str) -> str:
    """
    Extract text from PowerPoint file.

    Extracts text from all slides, including:
    - Slide titles
    - Text boxes and shapes
    - Tables
    - Notes

    Args:
        pptx_path: Path to .pptx file

    Returns:
        Extracted text with slide markers
    """
    prs = Presentation(pptx_path)
    text_content = []

    for slide_num, slide in enumerate(prs.slides, 1):
        slide_text = []
        slide_text.append(f"--- SLIDE {slide_num} ---")

        # Extract from all shapes
        for shape in slide.shapes:
            # Handle text frames (most common)
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    para_text = "".join([run.text for run in paragraph.runs])
                    if para_text.strip():
                        slide_text.append(para_text.strip())

            # Handle tables
            if shape.has_table:
                table = shape.table
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        if cell.text.strip():
                            row_text.append(cell.text.strip())
                    if row_text:
                        slide_text.append(" | ".join(row_text))

        # Extract slide notes if present
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                slide_text.append(f"[Notes: {notes}]")

        text_content.append("\n".join(slide_text))

    return "\n\n".join(text_content)


def analyze_pdf_with_vision(pdf_path: str, state: Dict) -> Dict:
    """
    Analyze image-based PDF by extracting images and sending to Claude's vision API.

    Args:
        pdf_path: Path to PDF file
        state: Current memo state

    Returns:
        Updated state with deck analysis
    """
    # Extract images from PDF using PyMuPDF
    print(f"Extracting images from PDF...", flush=True)
    doc = fitz.open(pdf_path)
    page_count = len(doc)

    # Process in batches of 5 to avoid API payload limits
    batch_size = 5
    all_deck_analyses = []

    # Use Anthropic client directly for vision
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    for batch_start in range(0, page_count, batch_size):
        batch_end = min(batch_start + batch_size, page_count)
        batch_num = (batch_start // batch_size) + 1
        total_batches = (page_count + batch_size - 1) // batch_size

        print(f"Processing slides {batch_start + 1}-{batch_end} (batch {batch_num}/{total_batches})...", flush=True)

        # Convert batch pages to images
        image_contents = []
        for page_num in range(batch_start, batch_end):
            page = doc[page_num]
            # Render at 0.5x scale to reduce payload size (still readable)
            mat = fitz.Matrix(0.5, 0.5)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image to compress as JPEG
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img_buffer = BytesIO()
            img.save(img_buffer, format="JPEG", quality=85, optimize=True)
            img_bytes = img_buffer.getvalue()
            img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": img_b64
                }
            })

        print(f"Sending batch {batch_num} ({len(image_contents)} slides) to Claude...", flush=True)

        analysis_prompt = f"""You are a venture capital investment analyst reviewing slides {batch_start + 1}-{batch_end} of a pitch deck.

Extract the following information from these slides in JSON format (use "Not mentioned" for information not present in THIS batch):
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
- Capture specific numbers (revenue, users, growth rates, funding amounts)
- Note the deck's strengths and weaknesses in extraction_notes
- Return ONLY valid JSON, no other text"""

        try:
            # Build content blocks: all images followed by the prompt
            content_blocks = image_contents + [{"type": "text", "text": analysis_prompt}]

            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": content_blocks
                }]
            )

            print(f"✓ Batch {batch_num} complete, parsing results...", flush=True)

            # Extract JSON from response
            content = response.content[0].text

            try:
                batch_analysis = json.loads(content)
                print(f"✓ Batch {batch_num}: Parsed JSON directly", flush=True)
            except json.JSONDecodeError as e:
                # Try to extract JSON from markdown code block
                print(f"Batch {batch_num}: Direct JSON parse failed, extracting from code block...", flush=True)
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                else:
                    json_str = content

                try:
                    batch_analysis = json.loads(json_str)
                    print(f"✓ Batch {batch_num}: Parsed JSON from code block", flush=True)
                except json.JSONDecodeError as e2:
                    print(f"ERROR: Batch {batch_num} failed to parse JSON: {e2}", flush=True)
                    print(f"First 500 chars of response: {content[:500]}", flush=True)
                    # Continue with next batch instead of failing completely
                    continue

            all_deck_analyses.append(batch_analysis)
            print(f"✓ Batch {batch_num}: Found {len(batch_analysis.get('team_members', []))} team members, "
                  f"{len(batch_analysis.get('traction_metrics', []))} traction metrics", flush=True)

        except Exception as e:
            print(f"ERROR: Batch {batch_num} failed: {e}", flush=True)
            # Continue with next batch instead of failing completely
            continue

    # Close the PDF document
    doc.close()

    # Merge all batch analyses into a single comprehensive analysis
    print(f"\nMerging {len(all_deck_analyses)} batch analyses...", flush=True)

    if not all_deck_analyses:
        print("ERROR: No batches were successfully analyzed", flush=True)
        return {
            "deck_analysis": None,
            "messages": ["Deck analysis failed (vision mode): No batches succeeded"]
        }

    # Start with the first batch as base
    deck_analysis = all_deck_analyses[0].copy()
    deck_analysis["deck_page_count"] = page_count

    # Merge data from subsequent batches
    for batch_data in all_deck_analyses[1:]:
        # For string fields: use first non-"Not mentioned" value
        for field in ["company_name", "tagline", "problem_statement", "solution_description",
                      "product_description", "business_model", "funding_ask", "competitive_landscape", "go_to_market"]:
            if batch_data.get(field) and batch_data[field] != "Not mentioned":
                if deck_analysis.get(field) == "Not mentioned" or not deck_analysis.get(field):
                    deck_analysis[field] = batch_data[field]

        # For dict fields (market_size): merge non-"Not mentioned" values
        if batch_data.get("market_size"):
            if not deck_analysis.get("market_size"):
                deck_analysis["market_size"] = {}
            for key, value in batch_data["market_size"].items():
                if value and value != "Not mentioned":
                    if not deck_analysis["market_size"].get(key) or deck_analysis["market_size"][key] == "Not mentioned":
                        deck_analysis["market_size"][key] = value

        # For list fields: append unique items
        for field in ["traction_metrics", "team_members", "use_of_funds", "milestones", "extraction_notes"]:
            if batch_data.get(field) and isinstance(batch_data[field], list):
                if not deck_analysis.get(field):
                    deck_analysis[field] = []
                # Append items that aren't already present
                for item in batch_data[field]:
                    if item not in deck_analysis[field] and item != "Not mentioned":
                        deck_analysis[field].append(item)

    print(f"✓ Merged analysis complete: {deck_analysis.get('deck_page_count', 'unknown')} pages analyzed", flush=True)
    print(f"✓ Final totals: {len(deck_analysis.get('team_members', []))} team members, "
          f"{len(deck_analysis.get('traction_metrics', []))} traction metrics", flush=True)

    # Continue with the same flow as text-based analysis
    try:
        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            temperature=0
        )

        print("Creating initial section drafts from deck data...", flush=True)
        section_drafts = create_initial_section_drafts(deck_analysis, state, llm)
        print(f"Created {len(section_drafts)} initial section drafts", flush=True)

        # Save artifacts (same as text-based path)
        from ..artifacts import save_deck_analysis_artifacts
        print("Saving deck analysis artifacts...", flush=True)
        # Extract just the content strings for artifact saving
        section_drafts_for_disk = {k: v["content"] for k, v in section_drafts.items()}
        # Pass firm from state for firm-scoped output paths
        firm = state.get("firm")
        save_deck_analysis_artifacts(
            state["company_name"],
            deck_analysis,
            section_drafts_for_disk,
            firm=firm
        )

        return {
            "deck_analysis": deck_analysis,
            "draft_sections": section_drafts,
            "messages": [f"Deck analysis complete (vision mode): {deck_analysis.get('deck_page_count', 'unknown')} pages analyzed"]
        }

    except Exception as e:
        print(f"Error analyzing PDF with vision: {e}", flush=True)
        return {
            "deck_analysis": None,
            "messages": [f"Deck analysis failed (vision mode): {str(e)}"]
        }


def create_initial_section_drafts(deck_analysis: Dict, state: Dict, llm: ChatAnthropic) -> Dict[str, SectionDraft]:
    """
    Create draft sections for ALL extracted deck data fields.

    This creates a draft for EVERY field that has substantial data, regardless of
    outline section names. Downstream agents (researcher, writer) can then use
    these drafts as authoritative source material.

    Args:
        deck_analysis: Extracted deck data
        state: Current memo state
        llm: Language model for generating drafts

    Returns:
        Dictionary mapping section filenames to SectionDraft objects
    """
    drafts = {}

    # Map deck fields to filenames - outline agnostic
    # Create a draft for EVERY field with data, let downstream agents use them
    DECK_FIELD_CONFIG = {
        "problem_statement": {
            "filename": "deck-problem.md",
            "display_name": "Problem Statement",
            "related_fields": ["problem_statement"]
        },
        "solution_description": {
            "filename": "deck-solution.md",
            "display_name": "Solution",
            "related_fields": ["solution_description"]
        },
        "product_description": {
            "filename": "deck-product.md",
            "display_name": "Product",
            "related_fields": ["product_description"]
        },
        "business_model": {
            "filename": "deck-business-model.md",
            "display_name": "Business Model",
            "related_fields": ["business_model"]
        },
        "market_size": {
            "filename": "deck-market.md",
            "display_name": "Market Size",
            "related_fields": ["market_size"]
        },
        "competitive_landscape": {
            "filename": "deck-competitive.md",
            "display_name": "Competitive Landscape",
            "related_fields": ["competitive_landscape"]
        },
        "traction_metrics": {
            "filename": "deck-traction.md",
            "display_name": "Traction & Metrics",
            "related_fields": ["traction_metrics", "milestones"]
        },
        "team_members": {
            "filename": "deck-team.md",
            "display_name": "Team",
            "related_fields": ["team_members"]
        },
        "funding_ask": {
            "filename": "deck-funding.md",
            "display_name": "Funding & Terms",
            "related_fields": ["funding_ask", "use_of_funds"]
        },
        "go_to_market": {
            "filename": "deck-gtm.md",
            "display_name": "Go-to-Market Strategy",
            "related_fields": ["go_to_market"]
        },
    }

    def has_substantial_data(field_value) -> bool:
        """Check if field has real data (not empty or placeholder)."""
        if not field_value:
            return False
        if field_value == "Not mentioned":
            return False
        if field_value == "":
            return False
        if field_value == []:
            return False
        if field_value == {}:
            return False
        # For dicts, check if all values are "Not mentioned"
        if isinstance(field_value, dict):
            return any(v and v != "Not mentioned" for v in field_value.values())
        return True

    # Create a draft for each field with substantial data
    for primary_field, config in DECK_FIELD_CONFIG.items():
        # Check if any of the related fields have data
        related_fields = config["related_fields"]
        fields_with_data = [
            f for f in related_fields
            if has_substantial_data(deck_analysis.get(f))
        ]

        if not fields_with_data:
            continue

        # Generate draft content
        content = create_section_draft_from_deck(
            llm,
            config["display_name"],
            deck_analysis,
            fields_with_data
        )

        # Create SectionDraft object
        drafts[config["filename"]] = SectionDraft(
            section_name=config["display_name"],
            content=content,
            word_count=len(content.split()),
            citations=[]  # Citations added by citation enrichment agent
        )

        print(f"    ✓ Created deck draft: {config['filename']} ({len(content.split())} words)")

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

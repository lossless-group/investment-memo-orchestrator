"""
Team Extractor

Extracts team data from various document types:
- Team bios and org charts
- Pitch decks (team slides)
- LinkedIn profiles
- About pages and company overviews
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from anthropic import Anthropic

from ..dataroom_state import (
    TeamData,
    FounderProfile,
)


def extract_team_data(
    documents: List[Dict[str, Any]],
    use_llm: bool = True
) -> Optional[TeamData]:
    """
    Extract team data from classified documents.

    Args:
        documents: List of DocumentInventoryItem dicts classified as team-related
        use_llm: Whether to use LLM for extraction

    Returns:
        TeamData with extracted team information, or None if extraction fails
    """
    if not documents:
        return None

    # Process each document
    extractions = []
    for doc in documents:
        file_path = Path(doc["file_path"])
        doc_type = doc.get("document_type", "unknown")

        extraction = None
        if file_path.suffix.lower() == ".pdf":
            extraction = extract_from_pdf(file_path, doc_type, use_llm=use_llm)
        elif file_path.suffix.lower() in [".csv", ".xlsx", ".xls"]:
            extraction = extract_from_spreadsheet(file_path, use_llm=use_llm)
        elif file_path.suffix.lower() in [".md", ".txt"]:
            extraction = extract_from_text(file_path, use_llm=use_llm)

        if extraction:
            extraction["source_file"] = doc["filename"]
            extraction["doc_type"] = doc_type
            extractions.append(extraction)

    if not extractions:
        return None

    # Merge extractions from multiple documents
    return _merge_team_extractions(extractions)


def extract_from_pdf(
    file_path: Path,
    doc_type: str,
    use_llm: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Extract team data from a PDF document.

    Args:
        file_path: Path to the PDF file
        doc_type: Document type classification
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted team data, or None if extraction fails
    """
    if pdfplumber is None:
        print("   ⚠️ pdfplumber not installed, skipping PDF extraction")
        return None

    try:
        with pdfplumber.open(file_path) as pdf:
            all_text = []
            all_tables = []

            for page in pdf.pages:
                # Extract text
                text = page.extract_text() or ""
                all_text.append(text)

                # Extract tables
                tables = page.extract_tables() or []
                all_tables.extend(tables)

            full_text = "\n".join(all_text)
            filename = file_path.name

            # Try rule-based extraction first
            rule_result = _extract_team_rules(full_text, all_tables, filename)

            # If LLM is enabled and we need more data, use LLM
            if use_llm and _needs_llm_enhancement(rule_result):
                llm_result = _extract_team_with_llm(filename, full_text, all_tables, doc_type)
                if llm_result:
                    # Merge LLM results with rule-based results
                    return _merge_single_extraction(rule_result, llm_result)

            return rule_result if rule_result.get("founders") or rule_result.get("leadership") else None

    except Exception as e:
        print(f"   ⚠️ Error extracting team from PDF: {e}")
        return None


def extract_from_spreadsheet(
    file_path: Path,
    use_llm: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Extract team data from a spreadsheet (CSV/Excel).

    Args:
        file_path: Path to the spreadsheet file
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted team data, or None if extraction fails
    """
    try:
        import pandas as pd
    except ImportError:
        print("   ⚠️ pandas not installed, skipping spreadsheet extraction")
        return None

    try:
        # Read the file
        if file_path.suffix.lower() == ".csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Look for team-related columns
        team_columns = [col for col in df.columns if any(
            keyword in col.lower()
            for keyword in ["name", "title", "role", "department", "email", "linkedin", "bio"]
        )]

        if not team_columns:
            return None

        # Convert to text for LLM processing
        content = df.to_string()
        filename = file_path.name

        if use_llm:
            return _extract_team_with_llm(filename, content, [], "team_bios")

        return None

    except Exception as e:
        print(f"   ⚠️ Error extracting team from spreadsheet: {e}")
        return None


def extract_from_text(
    file_path: Path,
    use_llm: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Extract team data from a text file.

    Args:
        file_path: Path to the text file
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted team data, or None if extraction fails
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        filename = file_path.name

        # Try rule-based extraction first
        rule_result = _extract_team_rules(content, [], filename)

        if use_llm and _needs_llm_enhancement(rule_result):
            llm_result = _extract_team_with_llm(filename, content, [], "team_bios")
            if llm_result:
                return _merge_single_extraction(rule_result, llm_result)

        return rule_result if rule_result.get("founders") or rule_result.get("leadership") else None

    except Exception as e:
        print(f"   ⚠️ Error extracting team from text file: {e}")
        return None


def _needs_llm_enhancement(rule_result: Dict[str, Any]) -> bool:
    """Check if rule-based result needs LLM enhancement."""
    founders = rule_result.get("founders", [])
    leadership = rule_result.get("leadership", [])

    # Need LLM if we have names but no details
    for person in founders + leadership:
        if person.get("name") and not person.get("previous_companies"):
            return True

    # Need LLM if we found very few people
    if len(founders) + len(leadership) < 2:
        return True

    return False


def _extract_team_rules(
    text: str,
    tables: List[List],
    filename: str
) -> Dict[str, Any]:
    """
    Rule-based extraction for team data.

    Args:
        text: Document text content
        tables: Extracted tables from PDF
        filename: Source filename

    Returns:
        Dict with extracted team data
    """
    result = {
        "founders": [],
        "leadership": [],
        "total_headcount": None,
        "headcount_by_department": {},
        "advisors": [],
        "board_members": [],
        "extraction_notes": [],
    }

    # Extract headcount
    headcount_patterns = [
        r"(\d+)\s*(?:total\s*)?(?:employees?|team members?|FTEs?|headcount)",
        r"(?:team of|team size[:\s]+)(\d+)",
        r"(\d+)\s*people",
    ]

    for pattern in headcount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                result["total_headcount"] = int(match.group(1))
                break
            except ValueError:
                pass

    # Extract names with titles (common patterns in pitch decks)
    # Pattern: Name, Title or Name - Title or Name (Title)
    name_title_patterns = [
        # "John Smith, CEO" or "John Smith - CEO"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)[,\s-]+(?:the\s+)?(CEO|CTO|CFO|COO|CPO|CMO|VP|President|Founder|Co-Founder|Chief\s+\w+\s+Officer|Head\s+of\s+\w+)",
        # "CEO: John Smith"
        r"(CEO|CTO|CFO|COO|CPO|CMO|Founder|Co-Founder)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    ]

    found_people = set()
    for pattern in name_title_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if len(match) == 2:
                # Could be (name, title) or (title, name)
                if re.match(r"(CEO|CTO|CFO|COO|CPO|CMO|VP|President|Founder|Co-Founder|Chief|Head)", match[0], re.IGNORECASE):
                    title, name = match
                else:
                    name, title = match

                # Clean up the name
                name = name.strip()
                title = title.strip()

                if name and name not in found_people:
                    found_people.add(name)

                    # Determine if founder or leadership
                    is_founder = any(kw in title.lower() for kw in ["founder", "ceo", "cto"])

                    person = {
                        "name": name,
                        "title": title,
                        "linkedin_url": None,
                        "email": None,
                        "previous_companies": [],
                        "previous_roles": [],
                        "education": [],
                        "notable_achievements": [],
                        "domain_expertise": [],
                        "years_experience": None,
                    }

                    if is_founder:
                        result["founders"].append(person)
                    else:
                        result["leadership"].append(person)

    # Extract LinkedIn URLs
    linkedin_pattern = r"linkedin\.com/in/([a-zA-Z0-9\-]+)"
    linkedin_matches = re.findall(linkedin_pattern, text, re.IGNORECASE)
    if linkedin_matches:
        result["extraction_notes"].append(f"Found {len(linkedin_matches)} LinkedIn profiles")

    # Extract email patterns (might find team emails)
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails = re.findall(email_pattern, text)
    if emails:
        result["extraction_notes"].append(f"Found {len(emails)} email addresses")

    # Look for advisor/board mentions
    advisor_section = re.search(r"advisor[s]?[:\s]+(.*?)(?:\n\n|\Z)", text, re.IGNORECASE | re.DOTALL)
    if advisor_section:
        # Try to extract names from advisor section
        advisor_text = advisor_section.group(1)
        advisor_names = re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", advisor_text)
        result["advisors"] = advisor_names[:5]  # Limit to first 5

    board_section = re.search(r"board[:\s]+(.*?)(?:\n\n|\Z)", text, re.IGNORECASE | re.DOTALL)
    if board_section:
        board_text = board_section.group(1)
        board_names = re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", board_text)
        result["board_members"] = board_names[:5]

    return result


def _extract_team_with_llm(
    filename: str,
    content: str,
    tables: List[List],
    doc_type: str
) -> Optional[Dict[str, Any]]:
    """
    Use LLM to extract structured team data.

    Args:
        filename: Source filename
        content: Document text content
        tables: Extracted tables
        doc_type: Document type classification

    Returns:
        Dict with LLM-extracted team data, or None if extraction fails
    """
    client = Anthropic()

    # Prepare tables as text if present
    tables_text = ""
    if tables:
        tables_text = "\n\nTABLES FOUND:\n"
        for i, table in enumerate(tables[:5]):  # Limit tables
            tables_text += f"\nTable {i+1}:\n"
            for row in table[:20]:  # Limit rows
                tables_text += " | ".join(str(cell or "") for cell in row) + "\n"

    # Truncate content if too long
    max_content_length = 15000
    if len(content) > max_content_length:
        content = content[:max_content_length] + "\n...[TRUNCATED]..."

    prompt = f"""Extract team and leadership information from this {doc_type} document.

DOCUMENT: {filename}

CONTENT:
{content}
{tables_text}

Extract the following information and return as JSON:

{{
    "founders": [
        {{
            "name": "Full name",
            "title": "Title/Role",
            "linkedin_url": "LinkedIn URL if found",
            "email": "Email if found",
            "previous_companies": ["Company 1", "Company 2"],
            "previous_roles": ["Role at Company 1", "Role at Company 2"],
            "education": ["Degree from University"],
            "notable_achievements": ["Achievement 1", "Achievement 2"],
            "domain_expertise": ["Expertise area 1", "Expertise area 2"],
            "years_experience": 15
        }}
    ],
    "leadership": [
        // Same structure as founders, for non-founder executives
    ],
    "total_headcount": 50,
    "headcount_by_department": {{
        "engineering": 20,
        "sales": 10,
        "operations": 5
    }},
    "advisors": ["Advisor Name 1", "Advisor Name 2"],
    "board_members": ["Board Member 1", "Board Member 2"],
    "extraction_notes": ["Note about extraction"]
}}

IMPORTANT:
- Founders typically include CEO, CTO, and anyone labeled as "Founder" or "Co-Founder"
- Leadership includes VP, C-suite executives, and department heads who are NOT founders
- Extract as much detail as available about backgrounds, education, and achievements
- Include LinkedIn URLs if mentioned
- Note previous companies (Google, Microsoft, etc.) and notable roles
- If headcount by department isn't explicit, estimate from context if possible
- Return ONLY valid JSON, no explanations"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Try to extract JSON from response
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            return json.loads(json_match.group())

        return None

    except Exception as e:
        print(f"   ⚠️ LLM extraction error: {e}")
        return None


def _merge_single_extraction(
    rule_result: Dict[str, Any],
    llm_result: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge rule-based and LLM extraction results."""
    merged = rule_result.copy()

    # LLM results take precedence for structured data
    if llm_result.get("founders"):
        merged["founders"] = llm_result["founders"]
    if llm_result.get("leadership"):
        merged["leadership"] = llm_result["leadership"]
    if llm_result.get("total_headcount"):
        merged["total_headcount"] = llm_result["total_headcount"]
    if llm_result.get("headcount_by_department"):
        merged["headcount_by_department"] = llm_result["headcount_by_department"]
    if llm_result.get("advisors"):
        merged["advisors"] = llm_result["advisors"]
    if llm_result.get("board_members"):
        merged["board_members"] = llm_result["board_members"]

    # Merge extraction notes
    llm_notes = llm_result.get("extraction_notes", [])
    if llm_notes:
        merged["extraction_notes"].extend(llm_notes)

    return merged


def _merge_team_extractions(extractions: List[Dict[str, Any]]) -> TeamData:
    """
    Merge team extractions from multiple documents.

    Args:
        extractions: List of extraction results from individual documents

    Returns:
        Merged TeamData
    """
    merged: TeamData = {
        "document_source": ", ".join(e.get("source_file", "") for e in extractions if e.get("source_file")),
        "founders": [],
        "leadership": [],
        "total_headcount": None,
        "headcount_by_department": {},
        "advisors": [],
        "board_members": [],
        "extraction_notes": [],
    }

    # Track unique people by name
    founder_names = set()
    leadership_names = set()

    for extraction in extractions:
        # Merge founders (dedupe by name)
        for founder in extraction.get("founders", []):
            name = founder.get("name", "")
            if name and name not in founder_names:
                founder_names.add(name)
                merged["founders"].append(founder)
            elif name in founder_names:
                # Update existing founder with more details
                for existing in merged["founders"]:
                    if existing.get("name") == name:
                        _update_person_details(existing, founder)
                        break

        # Merge leadership (dedupe by name)
        for leader in extraction.get("leadership", []):
            name = leader.get("name", "")
            if name and name not in leadership_names and name not in founder_names:
                leadership_names.add(name)
                merged["leadership"].append(leader)
            elif name in leadership_names:
                # Update existing leader with more details
                for existing in merged["leadership"]:
                    if existing.get("name") == name:
                        _update_person_details(existing, leader)
                        break

        # Take the highest headcount
        if extraction.get("total_headcount"):
            if not merged["total_headcount"] or extraction["total_headcount"] > merged["total_headcount"]:
                merged["total_headcount"] = extraction["total_headcount"]

        # Merge headcount by department
        for dept, count in extraction.get("headcount_by_department", {}).items():
            if dept not in merged["headcount_by_department"]:
                merged["headcount_by_department"][dept] = count
            else:
                # Take the higher count
                merged["headcount_by_department"][dept] = max(
                    merged["headcount_by_department"][dept],
                    count
                )

        # Merge advisors (dedupe)
        for advisor in extraction.get("advisors", []):
            if advisor and advisor not in merged["advisors"]:
                merged["advisors"].append(advisor)

        # Merge board members (dedupe)
        for board in extraction.get("board_members", []):
            if board and board not in merged["board_members"]:
                merged["board_members"].append(board)

        # Collect extraction notes
        source = extraction.get("source_file", "Unknown")
        merged["extraction_notes"].append(f"Source: {source}")
        for note in extraction.get("extraction_notes", []):
            if note not in merged["extraction_notes"]:
                merged["extraction_notes"].append(note)

    return merged


def _update_person_details(existing: Dict[str, Any], new: Dict[str, Any]) -> None:
    """Update existing person details with new information."""
    # Update fields if new has more data
    if new.get("linkedin_url") and not existing.get("linkedin_url"):
        existing["linkedin_url"] = new["linkedin_url"]
    if new.get("email") and not existing.get("email"):
        existing["email"] = new["email"]

    # Merge lists
    for field in ["previous_companies", "previous_roles", "education", "notable_achievements", "domain_expertise"]:
        existing_list = existing.get(field, [])
        new_list = new.get(field, [])
        for item in new_list:
            if item and item not in existing_list:
                existing_list.append(item)
        existing[field] = existing_list

    # Take years_experience if not set
    if new.get("years_experience") and not existing.get("years_experience"):
        existing["years_experience"] = new["years_experience"]

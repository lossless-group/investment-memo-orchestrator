"""
Cap Table Extractor

Extracts cap table data from PDF documents.
Parses ownership structure, shareholders, option pools, and SAFEs.
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
    CapTableData,
    ShareholderEntry,
    SAFEEntry,
    ConvertibleNoteEntry,
)


def extract_cap_table_data(
    documents: List[Dict[str, Any]],
    use_llm: bool = True
) -> Optional[CapTableData]:
    """
    Extract cap table data from classified documents.

    Args:
        documents: List of DocumentInventoryItem dicts classified as cap_table
        use_llm: Whether to use LLM for extraction

    Returns:
        CapTableData with extracted ownership information, or None if extraction fails
    """
    if not documents:
        return None

    # Process each cap table document
    extractions = []
    for doc in documents:
        file_path = Path(doc["file_path"])

        if file_path.suffix.lower() == ".pdf":
            extraction = extract_from_pdf(file_path, use_llm=use_llm)
            if extraction:
                extraction["source_file"] = doc["filename"]
                extractions.append(extraction)
        elif file_path.suffix.lower() in [".csv", ".xlsx", ".xls"]:
            extraction = extract_from_spreadsheet(file_path, use_llm=use_llm)
            if extraction:
                extraction["source_file"] = doc["filename"]
                extractions.append(extraction)

    if not extractions:
        return None

    # If multiple cap tables, use the most recent or most complete
    if len(extractions) == 1:
        return _build_cap_table_data(extractions[0])
    else:
        # Merge/select best extraction
        return _merge_cap_table_extractions(extractions)


def extract_from_pdf(file_path: Path, use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """
    Extract cap table data from a PDF document.

    Args:
        file_path: Path to the PDF file
        use_llm: Whether to use LLM for complex parsing

    Returns:
        Dict with extracted cap table data, or None if extraction fails
    """
    if pdfplumber is None:
        print("   ⚠️ pdfplumber not installed, skipping PDF extraction")
        return None

    try:
        with pdfplumber.open(file_path) as pdf:
            # Extract tables and text from all pages
            all_tables = []
            all_text = []

            for page in pdf.pages:
                tables = page.extract_tables()
                all_tables.extend(tables)

                text = page.extract_text()
                if text:
                    all_text.append(text)

            full_text = "\n".join(all_text)

            # Try rule-based extraction first
            extraction = _extract_cap_table_rules(all_tables, full_text, file_path.name)

            # If rule-based extraction is incomplete and LLM is enabled, use LLM
            if use_llm and _needs_llm_extraction(extraction):
                llm_extraction = _extract_cap_table_with_llm(
                    file_path.name,
                    full_text,
                    all_tables
                )
                if llm_extraction:
                    # Merge LLM extraction with rule-based
                    extraction = _merge_extractions(extraction, llm_extraction)

            return extraction

    except Exception as e:
        print(f"   ⚠️ Error extracting cap table from {file_path.name}: {e}")
        return None


def extract_from_spreadsheet(file_path: Path, use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """
    Extract cap table data from a spreadsheet (CSV/Excel).

    Args:
        file_path: Path to the spreadsheet file
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted cap table data, or None if extraction fails
    """
    try:
        import pandas as pd

        if file_path.suffix.lower() == ".csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Convert to text representation for LLM
        text_repr = df.to_string()

        if use_llm:
            return _extract_cap_table_with_llm(file_path.name, text_repr, [])
        else:
            return _extract_cap_table_from_dataframe(df)

    except Exception as e:
        print(f"   ⚠️ Error extracting cap table from {file_path.name}: {e}")
        return None


def _extract_cap_table_rules(
    tables: List[List[List[str]]],
    text: str,
    filename: str
) -> Dict[str, Any]:
    """
    Rule-based extraction of cap table data.

    Args:
        tables: List of tables extracted from PDF
        text: Full text content of PDF
        filename: Source filename

    Returns:
        Dict with extracted data
    """
    extraction = {
        "shareholders": [],
        "total_shares_outstanding": None,
        "fully_diluted_shares": None,
        "option_pool_size": None,
        "option_pool_percentage": None,
        "options_granted": None,
        "options_available": None,
        "safes": [],
        "convertible_notes": [],
        "as_of_date": None,
        "share_prices": {},
        "notes": [],
    }

    # Extract date from filename or text
    date_patterns = [
        r"as of (\w+ \d+, \d{4})",
        r"(\w+ \d+, \d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extraction["as_of_date"] = match.group(1)
            break

    # Also check filename for date
    if not extraction["as_of_date"]:
        filename_match = re.search(r"(\w+ \d+, \d{4})", filename)
        if filename_match:
            extraction["as_of_date"] = filename_match.group(1)

    # Extract total shares
    total_patterns = [
        r"Total (?:Authorized|Outstanding)[:\s]+([0-9,]+)",
        r"([0-9,]+)\s+Total\s+Shares",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                shares = int(match.group(1).replace(",", ""))
                if "authorized" in pattern.lower():
                    extraction["notes"].append(f"Total Authorized: {shares:,}")
                else:
                    extraction["total_shares_outstanding"] = shares
            except ValueError:
                pass

    # Extract share prices
    price_patterns = [
        r"(Seed[-\s]*\d*|Series [A-Z])\s+Price[:\s]+\$([0-9.]+)",
        r"Price per share[:\s]+\$([0-9.]+)",
    ]
    for pattern in price_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                round_name, price = match
                extraction["share_prices"][round_name.strip()] = float(price)
            else:
                extraction["share_prices"]["common"] = float(match)

    # Process tables for shareholder data
    for table in tables:
        if not table or len(table) < 2:
            continue

        # Look for ownership table by checking headers
        header_row = None
        for i, row in enumerate(table[:3]):  # Check first 3 rows for headers
            row_text = " ".join(str(cell or "").lower() for cell in row)
            if any(keyword in row_text for keyword in ["shares", "ownership", "%", "capital"]):
                header_row = i
                break

        if header_row is not None:
            headers = [str(cell or "").lower().strip() for cell in table[header_row]]

            # Find relevant column indices
            name_col = _find_column(headers, ["name", "shareholder", "investor", ""])
            shares_col = _find_column(headers, ["shares", "total shares", "common"])
            pct_col = _find_column(headers, ["%", "ownership", "% ownership", "percentage"])
            class_col = _find_column(headers, ["class", "share class", "type"])

            # Process data rows
            for row in table[header_row + 1:]:
                if not row or not any(row):
                    continue

                # Skip empty rows or header-like rows
                first_cell = str(row[0] or "").strip()
                if not first_cell or first_cell.lower() in ["total", "totals", ""]:
                    continue

                shareholder = _parse_shareholder_row(
                    row, name_col, shares_col, pct_col, class_col, headers
                )
                if shareholder:
                    extraction["shareholders"].append(shareholder)

    # Extract option pool info from text
    option_patterns = [
        r"(?:Employee )?Option Pool[:\s]+([0-9,]+)\s+(?:shares)?",
        r"Issued Options[:\s]+([0-9,]+)",
        r"Unissued Options[:\s]+([0-9,]+)",
        r"Options?\s+(?:Pool|Available)[:\s]+([0-9,.]+)%?",
    ]
    for pattern in option_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", "")
            if "%" in pattern or float(value) < 100:
                extraction["option_pool_percentage"] = float(value)
            elif "issued" in pattern.lower():
                extraction["options_granted"] = int(float(value))
            elif "unissued" in pattern.lower() or "available" in pattern.lower():
                extraction["options_available"] = int(float(value))
            else:
                extraction["option_pool_size"] = int(float(value))

    return extraction


def _find_column(headers: List[str], keywords: List[str]) -> Optional[int]:
    """Find column index matching any of the keywords."""
    for i, header in enumerate(headers):
        for keyword in keywords:
            if keyword and keyword in header:
                return i
    # Return first non-empty column if no match (for name column)
    if "" in keywords:
        for i, header in enumerate(headers):
            if header and header not in ["", "none"]:
                return i
    return None


def _parse_shareholder_row(
    row: List[Any],
    name_col: Optional[int],
    shares_col: Optional[int],
    pct_col: Optional[int],
    class_col: Optional[int],
    headers: List[str]
) -> Optional[Dict[str, Any]]:
    """Parse a single shareholder row into structured data."""
    # Get name - try first column if name_col not found
    name = None
    if name_col is not None and name_col < len(row):
        name = str(row[name_col] or "").strip()
    elif row:
        name = str(row[0] or "").strip()

    if not name or name.lower() in ["total", "totals", "none", ""]:
        return None

    # Skip section headers
    if name.lower() in ["founders", "investors", "employee option pool", "seed", "series"]:
        return None

    shareholder = {
        "name": name,
        "shares": 0,
        "ownership_percentage": 0.0,
        "share_class": "Common",
        "investor_type": _infer_investor_type(name),
    }

    # Get shares
    if shares_col is not None and shares_col < len(row):
        shares_str = str(row[shares_col] or "").replace(",", "").replace("$", "").strip()
        try:
            shareholder["shares"] = int(float(shares_str)) if shares_str else 0
        except ValueError:
            pass

    # Get ownership percentage
    if pct_col is not None and pct_col < len(row):
        pct_str = str(row[pct_col] or "").replace("%", "").strip()
        try:
            shareholder["ownership_percentage"] = float(pct_str) if pct_str else 0.0
        except ValueError:
            pass

    # Get share class
    if class_col is not None and class_col < len(row):
        share_class = str(row[class_col] or "").strip()
        if share_class:
            shareholder["share_class"] = share_class

    # Only return if we have meaningful data
    if shareholder["shares"] > 0 or shareholder["ownership_percentage"] > 0:
        return shareholder
    return None


def _infer_investor_type(name: str) -> str:
    """Infer investor type from name."""
    name_lower = name.lower()

    if any(term in name_lower for term in ["founder", "ceo", "cto", "coo", "cfo"]):
        return "Founder"
    elif any(term in name_lower for term in ["option", "pool", "esop", "employee"]):
        return "Option Pool"
    elif any(term in name_lower for term in ["ventures", "capital", "partners", "fund", "vc"]):
        return "VC"
    elif any(term in name_lower for term in ["angel", "seed"]):
        return "Angel"
    else:
        return "Investor"


def _needs_llm_extraction(extraction: Dict[str, Any]) -> bool:
    """Check if extraction needs LLM enhancement."""
    # Need LLM if we have few shareholders or missing key data
    shareholders = extraction.get("shareholders", [])
    if len(shareholders) < 2:
        return True
    if not extraction.get("total_shares_outstanding"):
        return True
    return False


def _extract_cap_table_with_llm(
    filename: str,
    text: str,
    tables: List[List[List[str]]]
) -> Optional[Dict[str, Any]]:
    """
    Use LLM to extract cap table data from text and tables.

    Args:
        filename: Source filename
        text: Text content from document
        tables: Tables extracted from document

    Returns:
        Dict with extracted data, or None if extraction fails
    """
    client = Anthropic()

    # Format tables for prompt
    tables_text = ""
    for i, table in enumerate(tables[:3]):  # Limit to first 3 tables
        if table:
            tables_text += f"\n--- Table {i+1} ---\n"
            for row in table[:30]:  # Limit rows
                tables_text += " | ".join(str(cell or "") for cell in row) + "\n"

    prompt = f"""Extract cap table data from this document. Return a JSON object with the following structure:

{{
    "as_of_date": "date string or null",
    "total_shares_outstanding": number or null,
    "fully_diluted_shares": number or null,
    "shareholders": [
        {{
            "name": "shareholder name",
            "shares": number,
            "ownership_percentage": number (0-100),
            "share_class": "Common" or "Seed" or "Series A" etc,
            "investor_type": "Founder" or "VC" or "Angel" or "Employee" or "Option Pool"
        }}
    ],
    "option_pool_size": total option pool shares or null,
    "option_pool_percentage": percentage (0-100) or null,
    "options_granted": issued options or null,
    "options_available": unissued/available options or null,
    "share_prices": {{"round_name": price_per_share}},
    "total_capital_raised": total investment amount or null,
    "notes": ["any important notes about the cap table"]
}}

IMPORTANT:
- Extract ALL shareholders you can identify
- Include founders, investors, and option pool as separate entries
- Ownership percentages should sum to ~100%
- Share prices should be extracted if visible (e.g., "Seed-1 Price: $1.1224")
- If data is unclear, use null rather than guessing

Document: {filename}

Text Content:
{text[:4000]}

Tables:
{tables_text}

Return ONLY the JSON object, no other text."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Clean up response - remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

        return json.loads(response_text)

    except Exception as e:
        print(f"   ⚠️ LLM extraction error: {e}")
        return None


def _extract_cap_table_from_dataframe(df) -> Optional[Dict[str, Any]]:
    """Extract cap table data from a pandas DataFrame without LLM."""
    # Basic extraction - would need more sophisticated logic for real-world use
    extraction = {
        "shareholders": [],
        "notes": ["Extracted from spreadsheet without LLM"],
    }

    # Look for common column patterns
    columns_lower = [c.lower() for c in df.columns]

    name_col = None
    shares_col = None
    pct_col = None

    for i, col in enumerate(columns_lower):
        if "name" in col or "shareholder" in col:
            name_col = df.columns[i]
        elif "share" in col and "%" not in col:
            shares_col = df.columns[i]
        elif "%" in col or "ownership" in col or "percent" in col:
            pct_col = df.columns[i]

    if name_col:
        for _, row in df.iterrows():
            name = str(row.get(name_col, "")).strip()
            if name and name.lower() not in ["total", "totals", ""]:
                shareholder = {
                    "name": name,
                    "shares": int(row.get(shares_col, 0)) if shares_col else 0,
                    "ownership_percentage": float(row.get(pct_col, 0)) if pct_col else 0,
                    "share_class": "Unknown",
                    "investor_type": _infer_investor_type(name),
                }
                extraction["shareholders"].append(shareholder)

    return extraction if extraction["shareholders"] else None


def _merge_extractions(
    rule_based: Dict[str, Any],
    llm_based: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge rule-based and LLM-based extractions."""
    merged = rule_based.copy()

    # Prefer LLM values for missing fields
    for key in ["as_of_date", "total_shares_outstanding", "fully_diluted_shares",
                "option_pool_size", "option_pool_percentage", "options_granted",
                "options_available", "total_capital_raised"]:
        if not merged.get(key) and llm_based.get(key):
            merged[key] = llm_based[key]

    # Merge shareholders - prefer LLM if rule-based has fewer
    if len(llm_based.get("shareholders", [])) > len(merged.get("shareholders", [])):
        merged["shareholders"] = llm_based["shareholders"]

    # Merge share prices
    merged_prices = merged.get("share_prices", {})
    merged_prices.update(llm_based.get("share_prices", {}))
    merged["share_prices"] = merged_prices

    # Merge notes
    merged_notes = merged.get("notes", [])
    merged_notes.extend(llm_based.get("notes", []))
    merged["notes"] = merged_notes

    return merged


def _merge_cap_table_extractions(extractions: List[Dict[str, Any]]) -> CapTableData:
    """Merge multiple cap table extractions, preferring most recent/complete."""
    # Sort by completeness (more shareholders = more complete)
    extractions.sort(key=lambda x: len(x.get("shareholders", [])), reverse=True)

    # Use the most complete extraction as base
    best = extractions[0]

    # Add notes about other sources
    source_files = [e.get("source_file", "unknown") for e in extractions]
    best["notes"] = best.get("notes", [])
    best["notes"].append(f"Merged from {len(extractions)} sources: {', '.join(source_files)}")

    return _build_cap_table_data(best)


def _build_cap_table_data(extraction: Dict[str, Any]) -> CapTableData:
    """Build CapTableData TypedDict from extraction dict."""
    # Convert shareholders to ShareholderEntry format
    shareholders: List[ShareholderEntry] = []
    for sh in extraction.get("shareholders", []):
        entry: ShareholderEntry = {
            "name": sh.get("name", "Unknown"),
            "shares": sh.get("shares", 0),
            "ownership_percentage": sh.get("ownership_percentage", 0.0),
            "share_class": sh.get("share_class", "Common"),
            "investor_type": sh.get("investor_type", "Unknown"),
        }
        shareholders.append(entry)

    # Build extraction notes
    notes = extraction.get("notes", [])
    if extraction.get("share_prices"):
        prices_str = ", ".join(f"{k}: ${v}" for k, v in extraction["share_prices"].items())
        notes.append(f"Share prices: {prices_str}")
    if extraction.get("total_capital_raised"):
        notes.append(f"Total capital raised: ${extraction['total_capital_raised']:,.0f}")

    cap_table_data: CapTableData = {
        "document_source": extraction.get("source_file", "unknown"),
        "as_of_date": extraction.get("as_of_date"),

        # Ownership Summary
        "total_shares_outstanding": extraction.get("total_shares_outstanding"),
        "fully_diluted_shares": extraction.get("fully_diluted_shares"),

        # Shareholders
        "shareholders": shareholders,

        # Options Pool
        "option_pool_size": extraction.get("option_pool_size"),
        "option_pool_percentage": extraction.get("option_pool_percentage"),
        "options_granted": extraction.get("options_granted"),
        "options_available": extraction.get("options_available"),

        # SAFEs and Convertibles (extracted separately if present)
        "safes": extraction.get("safes", []),
        "convertible_notes": extraction.get("convertible_notes", []),

        # Valuation Context
        "last_priced_round_valuation": extraction.get("last_priced_round_valuation"),
        "last_priced_round_date": extraction.get("last_priced_round_date"),

        "extraction_notes": notes,
    }

    return cap_table_data

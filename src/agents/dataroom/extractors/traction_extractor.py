"""
Traction Extractor

Extracts traction data from various document types:
- Customer lists and case studies
- Pitch decks (traction slides)
- Marketing materials (customer logos, testimonials)
- Pipeline and sales reports
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

try:
    import pandas as pd
except ImportError:
    pd = None

from anthropic import Anthropic

from ..dataroom_state import (
    TractionData,
    CustomerEntry,
    PartnershipEntry,
)


def extract_traction_data(
    documents: List[Dict[str, Any]],
    use_llm: bool = True
) -> Optional[TractionData]:
    """
    Extract traction data from classified documents.

    Args:
        documents: List of DocumentInventoryItem dicts classified as traction-related
        use_llm: Whether to use LLM for extraction

    Returns:
        TractionData with extracted traction information, or None if extraction fails
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

        if extraction:
            extraction["source_file"] = doc["filename"]
            extraction["doc_type"] = doc_type
            extractions.append(extraction)

    if not extractions:
        return None

    # Merge extractions from multiple documents
    return _merge_traction_extractions(extractions)


def extract_from_pdf(
    file_path: Path,
    doc_type: str,
    use_llm: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Extract traction data from a PDF document.

    Args:
        file_path: Path to the PDF file
        doc_type: Document type classification
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted traction data, or None if extraction fails
    """
    if pdfplumber is None:
        print("   ⚠️ pdfplumber not installed, skipping PDF extraction")
        return None

    try:
        with pdfplumber.open(file_path) as pdf:
            all_text = []
            all_tables = []

            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text)

                tables = page.extract_tables()
                all_tables.extend(tables)

            full_text = "\n".join(all_text)

            # Try rule-based extraction first
            extraction = _extract_traction_rules(full_text, all_tables, file_path.name)

            # Use LLM for enhanced extraction
            if use_llm:
                llm_extraction = _extract_traction_with_llm(
                    file_path.name,
                    full_text,
                    all_tables,
                    doc_type
                )
                if llm_extraction:
                    extraction = _merge_single_extractions(extraction, llm_extraction)

            return extraction

    except Exception as e:
        print(f"   ⚠️ Error extracting traction from {file_path.name}: {e}")
        return None


def extract_from_spreadsheet(
    file_path: Path,
    use_llm: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Extract traction data from a spreadsheet (CSV/Excel).

    Args:
        file_path: Path to the spreadsheet file
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted traction data, or None if extraction fails
    """
    if pd is None:
        print("   ⚠️ pandas not installed, skipping spreadsheet extraction")
        return None

    try:
        if file_path.suffix.lower() == ".csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        text_repr = df.to_string()

        if use_llm:
            return _extract_traction_with_llm(file_path.name, text_repr, [], "spreadsheet")
        else:
            return _extract_traction_from_dataframe(df)

    except Exception as e:
        print(f"   ⚠️ Error extracting traction from {file_path.name}: {e}")
        return None


def _extract_traction_rules(
    text: str,
    tables: List[List[List[str]]],
    filename: str
) -> Dict[str, Any]:
    """
    Rule-based extraction of traction data.

    Args:
        text: Full text content
        tables: Tables extracted from document
        filename: Source filename

    Returns:
        Dict with extracted traction data
    """
    extraction = {
        "customers": [],
        "total_customers": None,
        "arr": None,
        "mrr": None,
        "growth_rate": None,
        "retention_rate": None,
        "churn_rate": None,
        "nps_score": None,
        "pipeline_value": None,
        "average_deal_size": None,
        "partnerships": [],
        "notes": [],
    }

    # Extract customer count
    customer_patterns = [
        r"(\d+)\+?\s*(?:enterprise\s+)?customers?",
        r"customers?[:\s]+(\d+)",
        r"(\d+)\s+(?:paying\s+)?(?:customers?|clients?|accounts?)",
    ]
    for pattern in customer_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                extraction["total_customers"] = int(match.group(1))
                break
            except ValueError:
                pass

    # Extract ARR/MRR
    arr_patterns = [
        r"ARR[:\s]+\$?([0-9,.]+)\s*([KMB])?",
        r"\$?([0-9,.]+)\s*([KMB])?\s*ARR",
        r"Annual\s+Recurring\s+Revenue[:\s]+\$?([0-9,.]+)\s*([KMB])?",
    ]
    for pattern in arr_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1).replace(",", ""))
                multiplier = match.group(2)
                if multiplier:
                    if multiplier.upper() == "K":
                        value *= 1000
                    elif multiplier.upper() == "M":
                        value *= 1000000
                    elif multiplier.upper() == "B":
                        value *= 1000000000
                extraction["arr"] = value
                break
            except ValueError:
                pass

    mrr_patterns = [
        r"MRR[:\s]+\$?([0-9,.]+)\s*([KMB])?",
        r"\$?([0-9,.]+)\s*([KMB])?\s*MRR",
    ]
    for pattern in mrr_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1).replace(",", ""))
                multiplier = match.group(2)
                if multiplier:
                    if multiplier.upper() == "K":
                        value *= 1000
                    elif multiplier.upper() == "M":
                        value *= 1000000
                extraction["mrr"] = value
                break
            except ValueError:
                pass

    # Extract growth rate
    growth_patterns = [
        r"(\d+(?:\.\d+)?)\s*%\s*(?:YoY|year.over.year|annual)?\s*growth",
        r"growth[:\s]+(\d+(?:\.\d+)?)\s*%",
        r"growing\s+(?:at\s+)?(\d+(?:\.\d+)?)\s*%",
    ]
    for pattern in growth_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                extraction["growth_rate"] = float(match.group(1))
                break
            except ValueError:
                pass

    # Extract retention/churn
    retention_patterns = [
        r"(?:net\s+)?retention[:\s]+(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:net\s+)?retention",
        r"NRR[:\s]+(\d+(?:\.\d+)?)\s*%",
    ]
    for pattern in retention_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                extraction["retention_rate"] = float(match.group(1))
                break
            except ValueError:
                pass

    churn_patterns = [
        r"churn[:\s]+(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*churn",
    ]
    for pattern in churn_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                extraction["churn_rate"] = float(match.group(1))
                break
            except ValueError:
                pass

    # Extract NPS
    nps_patterns = [
        r"NPS[:\s]+(\d+)",
        r"Net\s+Promoter\s+Score[:\s]+(\d+)",
    ]
    for pattern in nps_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                extraction["nps_score"] = int(match.group(1))
                break
            except ValueError:
                pass

    # Extract pipeline value
    pipeline_patterns = [
        r"pipeline[:\s]+\$?([0-9,.]+)\s*([KMB])?",
        r"\$?([0-9,.]+)\s*([KMB])?\s*pipeline",
    ]
    for pattern in pipeline_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1).replace(",", ""))
                multiplier = match.group(2)
                if multiplier:
                    if multiplier.upper() == "K":
                        value *= 1000
                    elif multiplier.upper() == "M":
                        value *= 1000000
                extraction["pipeline_value"] = value
                break
            except ValueError:
                pass

    # Extract average deal size / ACV
    acv_patterns = [
        r"(?:ACV|average\s+(?:deal\s+size|contract\s+value))[:\s]+\$?([0-9,.]+)\s*([KMB])?",
        r"\$?([0-9,.]+)\s*([KMB])?\s*(?:ACV|average\s+deal)",
    ]
    for pattern in acv_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1).replace(",", ""))
                multiplier = match.group(2)
                if multiplier:
                    if multiplier.upper() == "K":
                        value *= 1000
                    elif multiplier.upper() == "M":
                        value *= 1000000
                extraction["average_deal_size"] = value
                break
            except ValueError:
                pass

    # Extract customer names from common patterns
    # Look for "customers include" or customer logo sections
    customer_section = re.search(
        r"(?:customers?\s+include|notable\s+customers?|customer\s+logos?)[:\s]*(.*?)(?:\n\n|\Z)",
        text,
        re.IGNORECASE | re.DOTALL
    )
    if customer_section:
        customer_text = customer_section.group(1)
        # Split by common delimiters
        potential_customers = re.split(r"[,;•\n]", customer_text)
        for name in potential_customers:
            name = name.strip()
            # Filter out noise
            if name and len(name) > 2 and len(name) < 50 and not name.lower().startswith(("and", "the", "our")):
                extraction["customers"].append({
                    "name": name,
                    "contract_value": None,
                    "contract_type": "Unknown",
                    "use_case": None,
                })

    return extraction


def _extract_traction_with_llm(
    filename: str,
    content: str,
    tables: List[List[List[str]]],
    doc_type: str
) -> Optional[Dict[str, Any]]:
    """
    Use LLM to extract traction data.

    Args:
        filename: Source filename
        content: Text content
        tables: Tables extracted from document
        doc_type: Document type classification

    Returns:
        Dict with extracted traction data
    """
    client = Anthropic()

    # Format tables for prompt
    tables_text = ""
    for i, table in enumerate(tables[:5]):
        if table:
            tables_text += f"\n--- Table {i+1} ---\n"
            for row in table[:20]:
                tables_text += " | ".join(str(cell or "") for cell in row) + "\n"

    # Truncate content if too long
    content_truncated = content[:6000] if len(content) > 6000 else content

    prompt = f"""Extract traction and customer data from this document. Return a JSON object with the following structure:

{{
    "total_customers": number or null,
    "customers_by_segment": {{"enterprise": 10, "mid_market": 20, "smb": 50}} or null,
    "notable_customers": [
        {{
            "name": "Customer Name",
            "contract_value": 100000 or null,
            "contract_type": "Annual" or "Multi-year" or "Pilot" or "POC",
            "use_case": "brief description" or null,
            "logo_permission": true/false or null
        }}
    ],

    "arr": annual recurring revenue in dollars or null,
    "mrr": monthly recurring revenue in dollars or null,
    "revenue_growth_rate": percentage (e.g., 150 for 150% YoY) or null,

    "retention_rate": net revenue retention percentage or null,
    "churn_rate": percentage or null,
    "nps_score": number or null,

    "pipeline_value": total pipeline in dollars or null,
    "pipeline_stages": {{"qualified": 500000, "proposal": 300000, "negotiation": 200000}} or null,
    "average_deal_size": ACV in dollars or null,
    "sales_cycle_days": number or null,

    "partnerships": [
        {{
            "partner_name": "Partner Name",
            "partnership_type": "Technology" or "Channel" or "Strategic" or "Integration",
            "description": "brief description" or null
        }}
    ],

    "milestones": [
        "Key milestone or achievement"
    ],

    "notes": ["any important context about the traction data"]
}}

IMPORTANT:
- Extract ALL customer names you can identify (from logos, case studies, quotes, etc.)
- All monetary values should be in dollars (not thousands or millions)
- Convert K to *1000, M to *1000000
- If a metric is not present, omit it entirely (don't use null)
- Look for customer logos, case study mentions, testimonials
- Partnerships include technology integrations, channel partners, strategic alliances

Document type: {doc_type}
Document: {filename}

Content:
{content_truncated}

{tables_text}

Return ONLY the JSON object, no other text."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Clean up response
        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

        return json.loads(response_text)

    except Exception as e:
        print(f"   ⚠️ LLM extraction error: {e}")
        return None


def _extract_traction_from_dataframe(df) -> Optional[Dict[str, Any]]:
    """Extract traction data from a pandas DataFrame without LLM."""
    extraction = {
        "customers": [],
        "notes": ["Extracted from spreadsheet without LLM"],
    }

    # Look for customer-related columns
    columns_lower = [c.lower() for c in df.columns]

    name_col = None
    value_col = None

    for i, col in enumerate(columns_lower):
        if "customer" in col or "client" in col or "account" in col or "name" in col:
            name_col = df.columns[i]
        elif "value" in col or "amount" in col or "revenue" in col or "arr" in col:
            value_col = df.columns[i]

    if name_col:
        for _, row in df.iterrows():
            name = str(row.get(name_col, "")).strip()
            if name and name.lower() not in ["total", "totals", "", "nan"]:
                customer = {
                    "name": name,
                    "contract_value": float(row.get(value_col, 0)) if value_col else None,
                    "contract_type": "Unknown",
                    "use_case": None,
                }
                extraction["customers"].append(customer)

    return extraction if extraction["customers"] else None


def _merge_single_extractions(
    rule_based: Dict[str, Any],
    llm_based: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge rule-based and LLM-based extractions."""
    merged = rule_based.copy()

    # Prefer LLM values for numeric fields
    for key in ["total_customers", "arr", "mrr", "growth_rate", "retention_rate",
                "churn_rate", "nps_score", "pipeline_value", "average_deal_size",
                "sales_cycle_days"]:
        if llm_based.get(key) and not merged.get(key):
            merged[key] = llm_based[key]

    # Merge customer lists (prefer LLM if more complete)
    llm_customers = llm_based.get("notable_customers", [])
    rule_customers = merged.get("customers", [])

    if len(llm_customers) > len(rule_customers):
        merged["customers"] = llm_customers
    elif llm_customers:
        # Add any new customers from LLM
        existing_names = {c.get("name", "").lower() for c in rule_customers}
        for customer in llm_customers:
            if customer.get("name", "").lower() not in existing_names:
                rule_customers.append(customer)
        merged["customers"] = rule_customers

    # Merge partnerships
    merged["partnerships"] = llm_based.get("partnerships", [])

    # Merge pipeline stages
    if llm_based.get("pipeline_stages"):
        merged["pipeline_stages"] = llm_based["pipeline_stages"]

    # Merge customers by segment
    if llm_based.get("customers_by_segment"):
        merged["customers_by_segment"] = llm_based["customers_by_segment"]

    # Merge milestones
    merged["milestones"] = llm_based.get("milestones", [])

    # Merge notes
    merged_notes = merged.get("notes", [])
    merged_notes.extend(llm_based.get("notes", []))
    merged["notes"] = merged_notes

    return merged


def _merge_traction_extractions(extractions: List[Dict[str, Any]]) -> TractionData:
    """
    Merge traction extractions from multiple documents.

    Args:
        extractions: List of extraction dicts from different documents

    Returns:
        Merged TractionData
    """
    # Start with empty aggregation
    merged = {
        "customers": [],
        "total_customers": None,
        "arr": None,
        "mrr": None,
        "growth_rate": None,
        "retention_rate": None,
        "churn_rate": None,
        "nps_score": None,
        "pipeline_value": None,
        "pipeline_stages": None,
        "average_deal_size": None,
        "sales_cycle_days": None,
        "customers_by_segment": None,
        "partnerships": [],
        "milestones": [],
        "notes": [],
    }

    seen_customers = set()
    seen_partners = set()

    for ext in extractions:
        source = ext.get("source_file", "unknown")
        merged["notes"].append(f"Source: {source}")

        # Take first non-null value for numeric fields
        for key in ["total_customers", "arr", "mrr", "growth_rate", "retention_rate",
                    "churn_rate", "nps_score", "pipeline_value", "average_deal_size",
                    "sales_cycle_days"]:
            if ext.get(key) and not merged.get(key):
                merged[key] = ext[key]

        # Merge customers (deduplicate by name)
        for customer in ext.get("customers", []) + ext.get("notable_customers", []):
            name = customer.get("name", "").lower()
            if name and name not in seen_customers:
                seen_customers.add(name)
                merged["customers"].append(customer)

        # Merge partnerships (deduplicate by name)
        for partner in ext.get("partnerships", []):
            name = partner.get("partner_name", "").lower()
            if name and name not in seen_partners:
                seen_partners.add(name)
                merged["partnerships"].append(partner)

        # Merge milestones
        merged["milestones"].extend(ext.get("milestones", []))

        # Take pipeline stages if present
        if ext.get("pipeline_stages") and not merged.get("pipeline_stages"):
            merged["pipeline_stages"] = ext["pipeline_stages"]

        # Take customers by segment if present
        if ext.get("customers_by_segment") and not merged.get("customers_by_segment"):
            merged["customers_by_segment"] = ext["customers_by_segment"]

    # Build TractionData
    notable_customers: List[CustomerEntry] = []
    for c in merged["customers"]:
        entry: CustomerEntry = {
            "name": c.get("name", "Unknown"),
            "contract_value": c.get("contract_value"),
            "contract_type": c.get("contract_type", "Unknown"),
            "use_case": c.get("use_case"),
            "logo_permission": c.get("logo_permission"),
        }
        notable_customers.append(entry)

    partnerships: List[PartnershipEntry] = []
    for p in merged["partnerships"]:
        entry: PartnershipEntry = {
            "partner_name": p.get("partner_name", "Unknown"),
            "partnership_type": p.get("partnership_type", "Unknown"),
            "description": p.get("description"),
        }
        partnerships.append(entry)

    # Add milestones to notes
    if merged["milestones"]:
        merged["notes"].append("Milestones: " + "; ".join(merged["milestones"][:5]))

    traction_data: TractionData = {
        "document_source": ", ".join(e.get("source_file", "unknown") for e in extractions),
        "data_as_of": None,  # Could be extracted from docs

        # Customer Metrics
        "total_customers": merged.get("total_customers"),
        "customers_by_segment": merged.get("customers_by_segment"),
        "notable_customers": notable_customers,

        # Revenue Metrics
        "arr": merged.get("arr"),
        "mrr": merged.get("mrr"),
        "revenue_growth_rate": merged.get("growth_rate"),

        # Engagement Metrics
        "dau": None,
        "mau": None,
        "retention_rate": merged.get("retention_rate"),
        "churn_rate": merged.get("churn_rate"),
        "nps_score": merged.get("nps_score"),

        # Sales Pipeline
        "pipeline_value": merged.get("pipeline_value"),
        "pipeline_stages": merged.get("pipeline_stages"),
        "average_deal_size": merged.get("average_deal_size"),
        "sales_cycle_days": merged.get("sales_cycle_days"),

        # Partnerships
        "partnerships": partnerships,

        "extraction_notes": merged["notes"],
    }

    return traction_data

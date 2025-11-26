"""
Financial Extractor

Extracts financial data from CSV, Excel, and PDF documents.
Parses revenue, projections, operating expenses, and key metrics.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from anthropic import Anthropic

from ..dataroom_state import FinancialData


def extract_financial_data(
    documents: List[Dict[str, Any]],
    use_llm: bool = True
) -> Optional[FinancialData]:
    """
    Extract financial data from classified documents.

    Args:
        documents: List of DocumentInventoryItem dicts classified as financial_*
        use_llm: Whether to use LLM for extraction

    Returns:
        FinancialData with extracted financial information, or None if extraction fails
    """
    if not documents:
        return None

    # Process each financial document
    extractions = []
    for doc in documents:
        file_path = Path(doc["file_path"])
        doc_type = doc.get("document_type", "financial_statements")

        extraction = None
        if file_path.suffix.lower() == ".csv":
            extraction = extract_from_csv(file_path, use_llm=use_llm)
        elif file_path.suffix.lower() in [".xlsx", ".xls"]:
            extraction = extract_from_excel(file_path, use_llm=use_llm)
        elif file_path.suffix.lower() == ".pdf":
            extraction = extract_from_pdf(file_path, use_llm=use_llm)

        if extraction:
            extraction["source_file"] = doc["filename"]
            extraction["doc_type"] = doc_type
            extractions.append(extraction)

    if not extractions:
        return None

    # Merge extractions (projections + actuals if both present)
    return _merge_financial_extractions(extractions)


def extract_from_csv(file_path: Path, use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """
    Extract financial data from a CSV file.

    Args:
        file_path: Path to the CSV file
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted financial data, or None if extraction fails
    """
    if pd is None:
        print("   ⚠️ pandas not installed, skipping CSV extraction")
        return None

    try:
        # Read CSV with flexible parsing
        df = pd.read_csv(file_path, header=None)

        # Try to identify the structure
        extraction = _extract_from_dataframe(df, file_path.name, use_llm=use_llm)
        return extraction

    except Exception as e:
        print(f"   ⚠️ Error extracting financials from {file_path.name}: {e}")
        return None


def extract_from_excel(file_path: Path, use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """
    Extract financial data from an Excel file.

    Args:
        file_path: Path to the Excel file
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted financial data, or None if extraction fails
    """
    if pd is None:
        print("   ⚠️ pandas not installed, skipping Excel extraction")
        return None

    try:
        # Try to read the first sheet or summary sheet
        xlsx = pd.ExcelFile(file_path)
        sheet_names = xlsx.sheet_names

        # Look for summary sheet
        summary_sheet = None
        for name in sheet_names:
            if any(keyword in name.lower() for keyword in ["summary", "overview", "p&l", "income"]):
                summary_sheet = name
                break

        if summary_sheet:
            df = pd.read_excel(file_path, sheet_name=summary_sheet, header=None)
        else:
            df = pd.read_excel(file_path, sheet_name=0, header=None)

        extraction = _extract_from_dataframe(df, file_path.name, use_llm=use_llm)
        return extraction

    except Exception as e:
        print(f"   ⚠️ Error extracting financials from {file_path.name}: {e}")
        return None


def extract_from_pdf(file_path: Path, use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """
    Extract financial data from a PDF file.

    Args:
        file_path: Path to the PDF file
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted financial data, or None if extraction fails
    """
    if pdfplumber is None:
        print("   ⚠️ pdfplumber not installed, skipping PDF extraction")
        return None

    try:
        with pdfplumber.open(file_path) as pdf:
            all_tables = []
            all_text = []

            for page in pdf.pages:
                tables = page.extract_tables()
                all_tables.extend(tables)

                text = page.extract_text()
                if text:
                    all_text.append(text)

            full_text = "\n".join(all_text)

            if use_llm:
                return _extract_financials_with_llm(file_path.name, full_text, all_tables)
            else:
                return _extract_financials_rules(all_tables, full_text)

    except Exception as e:
        print(f"   ⚠️ Error extracting financials from {file_path.name}: {e}")
        return None


def _extract_from_dataframe(
    df: "pd.DataFrame",
    filename: str,
    use_llm: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Extract financial data from a pandas DataFrame.

    Args:
        df: DataFrame with financial data
        filename: Source filename
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extracted financial data
    """
    # Convert DataFrame to a more parseable format
    # First, try to identify header rows and data structure

    extraction = {
        "revenue": {},
        "arr": {},
        "bookings": {},
        "gross_profit": {},
        "gross_margin": {},
        "operating_expenses": {},
        "ebitda": {},
        "headcount": {},
        "projections": {},
        "notes": [],
    }

    # Find row labels and time periods
    # Typically first column has row labels, subsequent columns have periods

    # Convert to string for pattern matching
    df_str = df.to_string()

    # Extract time periods (columns)
    periods = _extract_time_periods(df)

    if use_llm:
        # Use LLM for more accurate extraction
        return _extract_financials_with_llm(filename, df_str, [])

    # Rule-based extraction
    for idx, row in df.iterrows():
        if row.empty:
            continue

        # Get row label (first non-null value)
        row_label = None
        for val in row:
            if pd.notna(val) and str(val).strip():
                row_label = str(val).strip().lower()
                break

        if not row_label:
            continue

        # Match row labels to financial metrics
        values = _extract_row_values(row, periods)

        if "revenue" in row_label or "total revenue" in row_label:
            extraction["revenue"] = values
        elif "arr" in row_label or "annual recurring" in row_label:
            extraction["arr"] = values
        elif "booking" in row_label:
            extraction["bookings"] = values
        elif "gross profit" in row_label:
            extraction["gross_profit"] = values
        elif "gross margin" in row_label or "margin %" in row_label:
            extraction["gross_margin"] = values
        elif "operating expense" in row_label or "total opex" in row_label:
            extraction["operating_expenses"] = values
        elif "ebitda" in row_label:
            extraction["ebitda"] = values
        elif "headcount" in row_label or "employee" in row_label:
            extraction["headcount"] = values

    return extraction


def _extract_time_periods(df: "pd.DataFrame") -> List[str]:
    """Extract time period labels from DataFrame."""
    periods = []

    # Look for date patterns in first few rows
    for idx in range(min(10, len(df))):
        row = df.iloc[idx]
        for val in row:
            if pd.isna(val):
                continue
            val_str = str(val).strip()

            # Match various date formats
            if re.match(r"^\d{4}$", val_str):  # Year only
                periods.append(val_str)
            elif re.match(r"^[A-Z][a-z]{2}-\d{2}$", val_str):  # Mon-YY
                periods.append(val_str)
            elif re.match(r"^\d{1,2}Q\d{2}$", val_str):  # 1Q25
                periods.append(val_str)
            elif re.match(r"^Q\d \d{4}$", val_str):  # Q1 2025
                periods.append(val_str)

    return list(dict.fromkeys(periods))  # Remove duplicates, preserve order


def _extract_row_values(row: "pd.Series", periods: List[str]) -> Dict[str, float]:
    """Extract numeric values from a row, mapped to periods."""
    values = {}

    numeric_values = []
    for val in row:
        if pd.isna(val):
            continue
        val_str = str(val).strip()

        # Clean and parse numeric values
        cleaned = val_str.replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
        cleaned = cleaned.replace("K", "000").replace("M", "000000")

        try:
            num = float(cleaned)
            numeric_values.append(num)
        except ValueError:
            continue

    # Map to periods if we have them
    if periods and len(numeric_values) >= len(periods):
        for i, period in enumerate(periods):
            if i < len(numeric_values):
                values[period] = numeric_values[i]
    else:
        # Use index as key
        for i, val in enumerate(numeric_values):
            values[f"col_{i}"] = val

    return values


def _extract_financials_rules(
    tables: List[List[List[str]]],
    text: str
) -> Dict[str, Any]:
    """Rule-based extraction of financial data from text and tables."""
    extraction = {
        "revenue": {},
        "arr": {},
        "gross_margin": {},
        "operating_expenses": {},
        "ebitda": {},
        "notes": [],
    }

    # Extract key metrics from text using patterns
    patterns = {
        "revenue": r"(?:total )?revenue[:\s]+\$?([0-9,.]+)(?:K|M)?",
        "arr": r"ARR[:\s]+\$?([0-9,.]+)(?:K|M)?",
        "gross_margin": r"gross margin[:\s]+([0-9.]+)%?",
        "burn_rate": r"burn(?: rate)?[:\s]+\$?([0-9,.]+)(?:K|M)?",
        "runway": r"runway[:\s]+([0-9.]+)\s*months?",
    }

    for metric, pattern in patterns.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            extraction["notes"].append(f"Found {metric}: {matches[0]}")

    return extraction


def _extract_financials_with_llm(
    filename: str,
    content: str,
    tables: List[List[List[str]]]
) -> Optional[Dict[str, Any]]:
    """
    Use LLM to extract financial data.

    Args:
        filename: Source filename
        content: Text content or DataFrame string representation
        tables: Tables extracted from document

    Returns:
        Dict with extracted financial data
    """
    client = Anthropic()

    # Format tables if present
    tables_text = ""
    for i, table in enumerate(tables[:3]):
        if table:
            tables_text += f"\n--- Table {i+1} ---\n"
            for row in table[:30]:
                tables_text += " | ".join(str(cell or "") for cell in row) + "\n"

    # Truncate content if too long
    content_truncated = content[:8000] if len(content) > 8000 else content

    prompt = f"""Extract financial data from this document. Return a JSON object with the following structure:

{{
    "currency": "USD",
    "time_unit": "annual" or "monthly" or "quarterly",
    "is_projection": true/false,

    "revenue": {{"2024": 1000000, "2025": 2000000}},
    "arr": {{"2024": 500000, "2025": 1000000}},
    "mrr": {{"Jan-25": 50000, "Feb-25": 55000}},
    "bookings": {{"2024": 600000, "2025": 1200000}},

    "gross_profit": {{"2024": 700000, "2025": 1400000}},
    "gross_margin_pct": {{"2024": 70, "2025": 70}},

    "operating_expenses": {{"2024": 1500000, "2025": 2000000}},
    "rd_expenses": {{"2024": 500000, "2025": 600000}},
    "sales_marketing_expenses": {{"2024": 400000, "2025": 600000}},
    "ga_expenses": {{"2024": 200000, "2025": 250000}},

    "ebitda": {{"2024": -800000, "2025": -600000}},
    "net_income": {{"2024": -900000, "2025": -700000}},

    "cash_position": 2000000,
    "burn_rate_monthly": 100000,
    "runway_months": 20,

    "headcount": {{"2024": 25, "2025": 40}},
    "headcount_by_dept": {{"engineering": 15, "sales": 10, "g&a": 5}},

    "key_metrics": {{
        "customers": 50,
        "avg_deal_size": 50000,
        "retention_rate": 95
    }},

    "notes": ["any important notes or caveats"]
}}

IMPORTANT:
- All monetary values should be in dollars (not thousands or millions)
- Convert K to *1000, M to *1000000
- Use negative numbers for losses/expenses
- If a metric is not present, omit it entirely (don't use null)
- Time periods can be years (2024, 2025) or months (Jan-25, Feb-25) or quarters (Q1-25)
- Extract as much data as you can find

Document: {filename}

Content:
{content_truncated}

{tables_text}

Return ONLY the JSON object, no other text."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
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


def _merge_financial_extractions(extractions: List[Dict[str, Any]]) -> FinancialData:
    """
    Merge multiple financial extractions into a single FinancialData.

    Args:
        extractions: List of extraction dicts from different documents

    Returns:
        Merged FinancialData
    """
    # Separate projections from actuals
    projections = [e for e in extractions if e.get("is_projection", False) or
                   "projection" in e.get("source_file", "").lower() or
                   "model" in e.get("source_file", "").lower()]
    actuals = [e for e in extractions if e not in projections]

    # Use actuals as base, add projections
    base = actuals[0] if actuals else projections[0] if projections else {}

    notes = []

    # Merge all sources
    for ext in extractions:
        source = ext.get("source_file", "unknown")
        notes.append(f"Source: {source}")

    # Build projection data separately
    projection_data = {}
    for proj in projections:
        for key in ["revenue", "arr", "ebitda", "headcount"]:
            if key in proj and proj[key]:
                if key not in projection_data:
                    projection_data[key] = {}
                projection_data[key].update(proj[key])

    # Convert to FinancialData structure
    financial_data: FinancialData = {
        "document_source": ", ".join(e.get("source_file", "unknown") for e in extractions),
        "extraction_date": datetime.now().isoformat(),

        # Income Statement
        "revenue": base.get("revenue"),
        "arr": base.get("arr"),
        "mrr": base.get("mrr"),
        "gross_margin": base.get("gross_margin_pct"),
        "operating_expenses": base.get("operating_expenses"),
        "net_income": base.get("net_income"),
        "ebitda": base.get("ebitda"),

        # Balance Sheet
        "cash": base.get("cash_position"),
        "total_assets": base.get("total_assets"),
        "total_liabilities": base.get("total_liabilities"),

        # Key Metrics
        "burn_rate": base.get("burn_rate_monthly"),
        "runway_months": base.get("runway_months"),
        "ltv": base.get("key_metrics", {}).get("ltv"),
        "cac": base.get("key_metrics", {}).get("cac"),
        "ltv_cac_ratio": base.get("key_metrics", {}).get("ltv_cac_ratio"),

        # Projections
        "projections": projection_data if projection_data else None,
        "projection_assumptions": base.get("assumptions", []),

        # Headcount
        "headcount": base.get("headcount"),
        "headcount_by_department": base.get("headcount_by_dept"),

        # Metadata
        "fiscal_year_end": base.get("fiscal_year_end"),
        "currency": base.get("currency", "USD"),
        "extraction_notes": notes + base.get("notes", []),
    }

    return financial_data

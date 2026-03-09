"""
Cap Table Extractor

Extracts cap table data from PDF and spreadsheet documents.
Parses ownership structure, shareholders, option pools, SAFEs, and convertible notes.

Handles multi-sheet Carta-style exports with separate Certificate and Convertible ledgers.
Classifies tables as pre-round or post-round and computes estimated post-conversion ownership.
"""

import json
import math
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_cap_table_data(
    documents: List[Dict[str, Any]],
    use_llm: bool = True,
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

    extractions = []
    for doc in documents:
        file_path = Path(doc["file_path"])
        extraction = None

        if file_path.suffix.lower() == ".pdf":
            extraction = extract_from_pdf(file_path, use_llm=use_llm)
        elif file_path.suffix.lower() in [".csv", ".xlsx", ".xls"]:
            extraction = extract_from_spreadsheet(file_path, use_llm=use_llm)

        if extraction:
            extraction["source_file"] = doc["filename"]
            extractions.append(extraction)

    if not extractions:
        return None

    if len(extractions) == 1:
        return _build_cap_table_data(extractions[0])
    else:
        return _merge_cap_table_extractions(extractions)


# ---------------------------------------------------------------------------
# Standalone extraction (can also be run directly on a file path)
# ---------------------------------------------------------------------------

def extract_from_file(file_path: str | Path, use_llm: bool = True) -> Optional[CapTableData]:
    """Convenience: extract directly from a file path."""
    fp = Path(file_path)
    docs = [{"file_path": str(fp), "filename": fp.name}]
    return extract_cap_table_data(docs, use_llm=use_llm)


# ---------------------------------------------------------------------------
# PDF Extraction
# ---------------------------------------------------------------------------

def extract_from_pdf(file_path: Path, use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """Extract cap table data from a PDF document."""
    if pdfplumber is None:
        print("   ⚠️ pdfplumber not installed, skipping PDF extraction")
        return None

    try:
        with pdfplumber.open(file_path) as pdf:
            all_tables: list = []
            all_text: list = []

            for page in pdf.pages:
                tables = page.extract_tables()
                all_tables.extend(tables)
                text = page.extract_text()
                if text:
                    all_text.append(text)

            full_text = "\n".join(all_text)

            extraction = _extract_cap_table_rules(all_tables, full_text, file_path.name)

            if use_llm and _needs_llm_extraction(extraction):
                llm_extraction = _extract_cap_table_with_llm(
                    file_path.name, full_text, all_tables
                )
                if llm_extraction:
                    extraction = _merge_extractions(extraction, llm_extraction)

            return extraction

    except Exception as e:
        print(f"   ⚠️ Error extracting cap table from {file_path.name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Spreadsheet Extraction (CSV / XLSX / XLS)
# ---------------------------------------------------------------------------

def extract_from_spreadsheet(file_path: Path, use_llm: bool = True) -> Optional[Dict[str, Any]]:
    """
    Extract cap table data from a spreadsheet.

    Handles multi-sheet Carta-style exports:
    - "CS Certificate Ledger" or similar → equity shareholders
    - "Convertible Ledger" or similar → SAFEs and convertible notes
    """
    try:
        import pandas as pd
    except ImportError:
        print("   ⚠️ pandas not installed, skipping spreadsheet extraction")
        return None

    try:
        if file_path.suffix.lower() == ".csv":
            df = pd.read_csv(file_path)
            return _extract_single_sheet(df, file_path.name, use_llm)

        # Multi-sheet Excel
        xls = pd.ExcelFile(file_path)
        sheet_names = xls.sheet_names
        print(f"   📊 Found {len(sheet_names)} sheet(s): {', '.join(sheet_names)}")

        extraction: Dict[str, Any] = {
            "shareholders": [],
            "safes": [],
            "convertible_notes": [],
            "total_shares_outstanding": None,
            "fully_diluted_shares": None,
            "option_pool_size": None,
            "option_pool_percentage": None,
            "options_granted": None,
            "options_available": None,
            "as_of_date": None,
            "share_prices": {},
            "total_capital_raised": None,
            "notes": [],
        }

        for sheet in sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            sheet_lower = sheet.lower()

            if any(kw in sheet_lower for kw in ["certificate", "equity", "cs ", "common", "preferred", "share"]):
                _extract_equity_ledger(df, extraction)
            elif any(kw in sheet_lower for kw in ["convertible", "safe", "note"]):
                _extract_convertible_ledger(df, extraction)
            else:
                # Try to detect from content
                text_repr = df.to_string().lower()
                if "safe" in text_repr or "convertible" in text_repr or "valuation cap" in text_repr:
                    _extract_convertible_ledger(df, extraction)
                elif "shares" in text_repr or "outstanding" in text_repr:
                    _extract_equity_ledger(df, extraction)
                else:
                    extraction["notes"].append(f"Sheet '{sheet}' not classified, skipped")

        if not extraction["shareholders"] and not extraction["safes"]:
            # Fallback: send everything to LLM
            if use_llm:
                combined_text = ""
                for sheet in sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet)
                    combined_text += f"\n=== Sheet: {sheet} ===\n{df.to_string()}\n"
                return _extract_cap_table_with_llm(file_path.name, combined_text, [])
            return None

        return extraction

    except Exception as e:
        print(f"   ⚠️ Error extracting cap table from {file_path.name}: {e}")
        return None


def _extract_single_sheet(df, filename: str, use_llm: bool) -> Optional[Dict[str, Any]]:
    """Handle a single-sheet CSV or simple Excel."""
    if use_llm:
        return _extract_cap_table_with_llm(filename, df.to_string(), [])
    return _extract_cap_table_from_dataframe(df)


# ---------------------------------------------------------------------------
# Carta-style equity ledger parsing
# ---------------------------------------------------------------------------

def _find_header_row(df) -> Optional[int]:
    """Find the row that contains column headers in a Carta export."""
    import pandas as pd
    equity_keywords = ["stakeholder", "shareholder", "name", "quantity", "shares", "share class"]
    for idx, row in df.iterrows():
        row_text = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        if sum(1 for kw in equity_keywords if kw in row_text) >= 2:
            return idx
    return None


def _extract_equity_ledger(df, extraction: Dict[str, Any]) -> None:
    """Parse a Carta-style CS Certificate Ledger sheet into extraction dict."""
    import pandas as pd

    # Find "as of" date from early rows
    for idx in range(min(5, len(df))):
        row_text = " ".join(str(v) for v in df.iloc[idx].values if pd.notna(v))
        date_match = re.search(r"[Aa]s of (\d{1,2}/\d{1,2}/\d{4})", row_text)
        if date_match:
            extraction["as_of_date"] = date_match.group(1)
            break

    header_idx = _find_header_row(df)
    if header_idx is None:
        extraction["notes"].append("Could not find header row in equity ledger")
        return

    # Use that row as headers
    headers = [str(v).strip().lower() if pd.notna(v) else "" for v in df.iloc[header_idx].values]

    # Column mapping
    col_map = {}
    for i, h in enumerate(headers):
        if "stakeholder name" in h or h == "stakeholder name":
            col_map["name"] = i
        elif h in ("name",) and "name" not in col_map:
            col_map["name"] = i
        elif "quantity outstanding" in h:
            col_map["shares"] = i
        elif "quantity issued" in h and "shares" not in col_map:
            col_map["shares_issued"] = i
        elif "share class" in h:
            col_map["share_class"] = i
        elif "price paid per share" in h or "price per share" in h:
            col_map["price_per_share"] = i
        elif "cash contributed" in h:
            col_map["cash_contributed"] = i
        elif "vesting schedule" in h:
            col_map["vesting"] = i
        elif "outstanding vested" in h:
            col_map["vested"] = i
        elif "outstanding unvested" in h:
            col_map["unvested"] = i
        elif h == "relationship":
            col_map["relationship"] = i
        elif "issue date" in h:
            col_map["issue_date"] = i

    data_rows = df.iloc[header_idx + 1:]
    total_shares = 0

    for _, row in data_rows.iterrows():
        vals = row.values

        # Get name
        name_idx = col_map.get("name")
        if name_idx is None or name_idx >= len(vals) or pd.isna(vals[name_idx]):
            # Check for grand total row
            for v in vals:
                if pd.notna(v) and "grand total" in str(v).lower():
                    shares_idx = col_map.get("shares", col_map.get("shares_issued"))
                    if shares_idx is not None and shares_idx < len(vals) and pd.notna(vals[shares_idx]):
                        try:
                            extraction["total_shares_outstanding"] = int(float(vals[shares_idx]))
                        except (ValueError, TypeError):
                            pass
            continue

        name = str(vals[name_idx]).strip()
        if not name or name.lower() in ("nan", "none", ""):
            continue

        # Parse shares
        shares = 0
        shares_idx = col_map.get("shares", col_map.get("shares_issued"))
        if shares_idx is not None and shares_idx < len(vals) and pd.notna(vals[shares_idx]):
            try:
                shares = int(float(vals[shares_idx]))
            except (ValueError, TypeError):
                pass

        if shares == 0:
            continue

        total_shares += shares

        # Parse other fields
        share_class = "Common"
        if "share_class" in col_map and col_map["share_class"] < len(vals) and pd.notna(vals[col_map["share_class"]]):
            share_class = str(vals[col_map["share_class"]]).strip()

        price_per_share = None
        if "price_per_share" in col_map and col_map["price_per_share"] < len(vals) and pd.notna(vals[col_map["price_per_share"]]):
            try:
                price_per_share = float(vals[col_map["price_per_share"]])
            except (ValueError, TypeError):
                pass

        cash = None
        if "cash_contributed" in col_map and col_map["cash_contributed"] < len(vals) and pd.notna(vals[col_map["cash_contributed"]]):
            try:
                cash = float(vals[col_map["cash_contributed"]])
            except (ValueError, TypeError):
                pass

        vesting = None
        if "vesting" in col_map and col_map["vesting"] < len(vals) and pd.notna(vals[col_map["vesting"]]):
            vesting = str(vals[col_map["vesting"]]).strip()

        vested = None
        if "vested" in col_map and col_map["vested"] < len(vals) and pd.notna(vals[col_map["vested"]]):
            try:
                vested = int(float(vals[col_map["vested"]]))
            except (ValueError, TypeError):
                pass

        unvested = None
        if "unvested" in col_map and col_map["unvested"] < len(vals) and pd.notna(vals[col_map["unvested"]]):
            try:
                unvested = int(float(vals[col_map["unvested"]]))
            except (ValueError, TypeError):
                pass

        investor_type = "Investor"
        if "relationship" in col_map and col_map["relationship"] < len(vals) and pd.notna(vals[col_map["relationship"]]):
            rel = str(vals[col_map["relationship"]]).strip()
            if rel:
                investor_type = rel
        else:
            investor_type = _infer_investor_type(name)

        issue_date = None
        if "issue_date" in col_map and col_map["issue_date"] < len(vals) and pd.notna(vals[col_map["issue_date"]]):
            issue_date = str(vals[col_map["issue_date"]]).strip()

        shareholder: Dict[str, Any] = {
            "name": name,
            "shares": shares,
            "ownership_percentage": 0.0,  # Computed after all shareholders collected
            "amount_invested": cash,
            "share_class": share_class,
            "investor_type": investor_type,
            "vesting_schedule": vesting,
            "vested_shares": vested,
            "unvested_shares": unvested,
            "price_per_share": price_per_share,
            "issue_date": issue_date,
        }
        extraction["shareholders"].append(shareholder)

    # Set total and compute ownership percentages
    if not extraction["total_shares_outstanding"] and total_shares > 0:
        extraction["total_shares_outstanding"] = total_shares

    total = extraction["total_shares_outstanding"] or total_shares
    if total > 0:
        for sh in extraction["shareholders"]:
            sh["ownership_percentage"] = round((sh["shares"] / total) * 100, 2)


def _extract_convertible_ledger(df, extraction: Dict[str, Any]) -> None:
    """Parse a Carta-style Convertible Ledger sheet."""
    import pandas as pd

    header_idx = None
    conv_keywords = ["stakeholder", "principal", "valuation cap", "discount", "interest"]
    for idx in range(min(10, len(df))):
        row_text = " ".join(str(v).lower() for v in df.iloc[idx].values if pd.notna(v))
        if sum(1 for kw in conv_keywords if kw in row_text) >= 2:
            header_idx = idx
            break

    if header_idx is None:
        extraction["notes"].append("Could not find header row in convertible ledger")
        return

    headers = [str(v).strip().lower() if pd.notna(v) else "" for v in df.iloc[header_idx].values]

    col_map = {}
    for i, h in enumerate(headers):
        if "stakeholder name" in h or h == "stakeholder name":
            col_map["name"] = i
        elif h == "principal":
            col_map["principal"] = i
        elif h == "total":
            col_map["total"] = i
        elif "valuation cap" in h:
            col_map["valuation_cap"] = i
        elif "conversion discount" in h or "discount" in h:
            col_map["discount"] = i
        elif "interest rate" in h:
            col_map["interest_rate"] = i
        elif "maturity" in h:
            col_map["maturity"] = i
        elif "issue date" in h:
            col_map["issue_date"] = i
        elif h == "interest":
            col_map["interest_accrued"] = i
        elif "note block" in h:
            col_map["note_block"] = i
        elif h == "relationship":
            col_map["relationship"] = i

    data_rows = df.iloc[header_idx + 1:]
    total_invested = 0.0

    for _, row in data_rows.iterrows():
        vals = row.values
        name_idx = col_map.get("name")
        if name_idx is None or name_idx >= len(vals) or pd.isna(vals[name_idx]):
            continue

        name = str(vals[name_idx]).strip()
        if not name or name.lower() in ("nan", "none", "", "grand total"):
            continue

        principal = 0.0
        if "principal" in col_map and col_map["principal"] < len(vals) and pd.notna(vals[col_map["principal"]]):
            try:
                principal = float(vals[col_map["principal"]])
            except (ValueError, TypeError):
                pass

        if principal == 0:
            continue

        total_invested += principal

        valuation_cap = None
        if "valuation_cap" in col_map and col_map["valuation_cap"] < len(vals) and pd.notna(vals[col_map["valuation_cap"]]):
            try:
                valuation_cap = float(vals[col_map["valuation_cap"]])
            except (ValueError, TypeError):
                pass

        discount = None
        if "discount" in col_map and col_map["discount"] < len(vals) and pd.notna(vals[col_map["discount"]]):
            try:
                d = float(vals[col_map["discount"]])
                discount = d if d <= 1.0 else d / 100.0  # Normalize to decimal
            except (ValueError, TypeError):
                pass

        interest_rate = None
        if "interest_rate" in col_map and col_map["interest_rate"] < len(vals) and pd.notna(vals[col_map["interest_rate"]]):
            try:
                interest_rate = float(vals[col_map["interest_rate"]])
            except (ValueError, TypeError):
                pass

        maturity = None
        if "maturity" in col_map and col_map["maturity"] < len(vals) and pd.notna(vals[col_map["maturity"]]):
            maturity = str(vals[col_map["maturity"]]).strip()

        issue_date = None
        if "issue_date" in col_map and col_map["issue_date"] < len(vals) and pd.notna(vals[col_map["issue_date"]]):
            issue_date = str(vals[col_map["issue_date"]]).strip()

        note_block = None
        if "note_block" in col_map and col_map["note_block"] < len(vals) and pd.notna(vals[col_map["note_block"]]):
            note_block = str(vals[col_map["note_block"]]).strip()

        # Determine if SAFE or convertible note based on context
        is_safe = False
        if note_block and "safe" in note_block.lower():
            is_safe = True
        elif interest_rate is None or interest_rate == 0:
            is_safe = True  # SAFEs typically have no interest

        if is_safe:
            safe_entry: Dict[str, Any] = {
                "investor_name": name,
                "amount_invested": principal,
                "valuation_cap": valuation_cap,
                "discount_rate": discount,
                "conversion_trigger": "Equity financing",
                "issue_date": issue_date,
                "pro_rata_rights": None,
                "estimated_ownership_percentage": None,
            }
            extraction["safes"].append(safe_entry)
        else:
            note_entry: Dict[str, Any] = {
                "investor_name": name,
                "principal_amount": principal,
                "interest_rate": interest_rate or 0.0,
                "maturity_date": maturity,
                "valuation_cap": valuation_cap,
                "discount_rate": discount,
                "estimated_ownership_percentage": None,
            }
            extraction["convertible_notes"].append(note_entry)

    if total_invested > 0:
        existing = extraction.get("total_capital_raised") or 0
        extraction["total_capital_raised"] = existing + total_invested


# ---------------------------------------------------------------------------
# Pre-round / post-round classification
# ---------------------------------------------------------------------------

def _classify_table_type(extraction: Dict[str, Any]) -> tuple[str, str]:
    """
    Determine if cap table is pre-round or post-round.

    Returns:
        (table_type, reasoning) where table_type is "pre_round" or "post_round"
    """
    has_safes = len(extraction.get("safes", [])) > 0
    has_notes = len(extraction.get("convertible_notes", [])) > 0
    shareholders = extraction.get("shareholders", [])

    # Check if any shareholders have preferred/series shares (priced round completed)
    has_priced_round = any(
        sh.get("share_class", "").lower() not in ("common", "common (cs)", "")
        and "series" in sh.get("share_class", "").lower()
        for sh in shareholders
    )

    if has_priced_round:
        return "post_round", "Shareholders include priced round shares (Series A/B/etc.)"

    if has_safes or has_notes:
        # SAFEs/notes exist but no priced round shares → pre-round
        return "pre_round", (
            f"{'SAFEs' if has_safes else ''}{'and ' if has_safes and has_notes else ''}"
            f"{'convertible notes' if has_notes else ''} present but no priced round shares. "
            "This is a pre-round cap table showing current equity plus unconverted instruments."
        )

    # Only common stock, no convertibles
    if shareholders:
        founder_only = all(
            sh.get("investor_type", "").lower() in ("founder", "employee", "option pool")
            for sh in shareholders
        )
        if founder_only:
            return "pre_round", "Only founder/employee equity issued, no external investment shares."

    return "pre_round", "Default classification: no indicators of completed priced round."


# ---------------------------------------------------------------------------
# Post-conversion ownership estimation
# ---------------------------------------------------------------------------

def _estimate_post_conversion_ownership(extraction: Dict[str, Any]) -> Optional[List[dict]]:
    """
    For pre-round cap tables with SAFEs/notes, estimate what ownership will
    look like after conversion at the best available valuation cap.

    Returns sorted list of {"name", "type", "shares_or_equivalent", "ownership_pct", "amount_invested"}
    """
    shareholders = extraction.get("shareholders", [])
    safes = extraction.get("safes", [])
    convertible_notes = extraction.get("convertible_notes", [])

    if not shareholders and not safes and not convertible_notes:
        return None

    total_shares = extraction.get("total_shares_outstanding", 0)
    if not total_shares:
        total_shares = sum(sh.get("shares", 0) for sh in shareholders)

    if total_shares == 0:
        return None

    # Build ownership table starting with equity holders
    ownership_table: List[dict] = []

    for sh in shareholders:
        ownership_table.append({
            "name": sh.get("name", "Unknown"),
            "type": sh.get("investor_type", "Equity"),
            "instrument": sh.get("share_class", "Common"),
            "shares_or_equivalent": sh.get("shares", 0),
            "amount_invested": sh.get("amount_invested"),
            "ownership_pct": 0.0,  # Recomputed below
        })

    # Estimate SAFE conversions
    for safe in safes:
        cap = safe.get("valuation_cap")
        discount = safe.get("discount_rate") or 0
        amount = safe.get("amount_invested", 0)

        if not amount:
            continue

        estimated_shares = 0
        if cap and cap > 0:
            # SAFE converts: shares = amount / (cap / total_pre_money_shares)
            price_per_share = cap / total_shares
            if discount and discount > 0:
                price_per_share = price_per_share * (1 - discount)
            estimated_shares = int(amount / price_per_share) if price_per_share > 0 else 0
        elif discount and discount > 0:
            # Discount-only SAFE: we can't estimate without a round price
            # Use a placeholder note
            estimated_shares = 0

        ownership_table.append({
            "name": safe.get("investor_name", "Unknown"),
            "type": "SAFE Holder",
            "instrument": f"SAFE (cap: ${cap:,.0f})" if cap else f"SAFE (discount: {discount:.0%})",
            "shares_or_equivalent": estimated_shares,
            "amount_invested": amount,
            "ownership_pct": 0.0,
        })

    # Estimate convertible note conversions
    for note in convertible_notes:
        cap = note.get("valuation_cap")
        discount = note.get("discount_rate") or 0
        principal = note.get("principal_amount", 0)

        if not principal:
            continue

        estimated_shares = 0
        if cap and cap > 0:
            price_per_share = cap / total_shares
            if discount and discount > 0:
                price_per_share = price_per_share * (1 - discount)
            estimated_shares = int(principal / price_per_share) if price_per_share > 0 else 0

        ownership_table.append({
            "name": note.get("investor_name", "Unknown"),
            "type": "Note Holder",
            "instrument": f"Note (cap: ${cap:,.0f})" if cap else "Note",
            "shares_or_equivalent": estimated_shares,
            "amount_invested": principal,
            "ownership_pct": 0.0,
        })

    # Compute total post-conversion shares and percentages
    total_post = sum(entry["shares_or_equivalent"] for entry in ownership_table)
    if total_post > 0:
        for entry in ownership_table:
            entry["ownership_pct"] = round((entry["shares_or_equivalent"] / total_post) * 100, 2)

    # Sort by ownership descending
    ownership_table.sort(key=lambda x: x["ownership_pct"], reverse=True)

    return ownership_table


# ---------------------------------------------------------------------------
# Markdown table generation
# ---------------------------------------------------------------------------

def generate_ownership_markdown(cap_table: CapTableData) -> str:
    """
    Generate a markdown summary of the cap table with ownership tables.

    Returns markdown string with:
    - Current equity ownership table (sorted by ownership)
    - SAFEs and convertible instruments table
    - Estimated post-conversion ownership table (if applicable)
    """
    lines: List[str] = []
    lines.append("## Cap Table Summary\n")

    as_of = cap_table.get("as_of_date", "Unknown date")
    table_type = cap_table.get("table_type", "unknown")
    lines.append(f"**As of:** {as_of}")
    lines.append(f"**Type:** {'Pre-Round' if table_type == 'pre_round' else 'Post-Round'} Cap Table")
    if cap_table.get("table_type_reasoning"):
        lines.append(f"**Classification:** {cap_table['table_type_reasoning']}")
    lines.append("")

    total_shares = cap_table.get("total_shares_outstanding")
    total_raised = cap_table.get("total_capital_raised")
    if total_shares:
        lines.append(f"**Total Shares Outstanding:** {total_shares:,}")
    if total_raised:
        lines.append(f"**Total Capital Raised:** ${total_raised:,.0f}")
    lines.append("")

    # Current equity holders
    shareholders = cap_table.get("shareholders", [])
    if shareholders:
        lines.append("### Current Equity Ownership\n")
        lines.append("| Rank | Shareholder | Type | Share Class | Shares | Ownership % | Amount Invested | Vesting |")
        lines.append("|------|-------------|------|-------------|--------|-------------|-----------------|---------|")

        sorted_sh = sorted(shareholders, key=lambda x: x.get("ownership_percentage", 0), reverse=True)
        for i, sh in enumerate(sorted_sh, 1):
            name = sh.get("name", "Unknown")
            inv_type = sh.get("investor_type", "—")
            share_class = sh.get("share_class", "—")
            shares = f"{sh.get('shares', 0):,}"
            pct = f"{sh.get('ownership_percentage', 0):.2f}%"
            invested = f"${sh['amount_invested']:,.0f}" if sh.get("amount_invested") else "—"
            vesting = sh.get("vesting_schedule") or "—"
            lines.append(f"| {i} | {name} | {inv_type} | {share_class} | {shares} | {pct} | {invested} | {vesting} |")
        lines.append("")

    # SAFEs
    safes = cap_table.get("safes", [])
    if safes:
        total_safe = sum(s.get("amount_invested", 0) for s in safes)
        lines.append("### SAFE Instruments\n")
        lines.append(f"**Total SAFE Investment:** ${total_safe:,.0f}\n")
        lines.append("| Investor | Amount | Valuation Cap | Discount | Issue Date |")
        lines.append("|----------|--------|---------------|----------|------------|")

        sorted_safes = sorted(safes, key=lambda x: x.get("amount_invested", 0), reverse=True)
        for s in sorted_safes:
            name = s.get("investor_name", "Unknown")
            amt = f"${s.get('amount_invested', 0):,.0f}"
            cap = f"${s['valuation_cap']:,.0f}" if s.get("valuation_cap") else "—"
            disc = f"{s['discount_rate']:.0%}" if s.get("discount_rate") else "—"
            date = s.get("issue_date", "—") or "—"
            lines.append(f"| {name} | {amt} | {cap} | {disc} | {date} |")
        lines.append("")

    # Convertible notes
    notes = cap_table.get("convertible_notes", [])
    if notes:
        lines.append("### Convertible Notes\n")
        lines.append("| Investor | Principal | Interest Rate | Valuation Cap | Discount | Maturity |")
        lines.append("|----------|-----------|---------------|---------------|----------|----------|")

        for n in notes:
            name = n.get("investor_name", "Unknown")
            principal = f"${n.get('principal_amount', 0):,.0f}"
            rate = f"{n['interest_rate']:.1f}%" if n.get("interest_rate") else "—"
            cap = f"${n['valuation_cap']:,.0f}" if n.get("valuation_cap") else "—"
            disc = f"{n['discount_rate']:.0%}" if n.get("discount_rate") else "—"
            maturity = n.get("maturity_date", "—") or "—"
            lines.append(f"| {name} | {principal} | {rate} | {cap} | {disc} | {maturity} |")
        lines.append("")

    # Post-conversion estimates
    post_conv = cap_table.get("estimated_post_conversion_ownership")
    if post_conv:
        lines.append("### Estimated Post-Conversion Ownership\n")
        lines.append("> **Note:** These estimates assume SAFEs convert at their respective valuation caps.")
        lines.append("> Actual ownership will depend on the priced round terms.\n")
        lines.append("| Rank | Stakeholder | Type | Instrument | Est. Shares | Est. Ownership % | Amount Invested |")
        lines.append("|------|-------------|------|------------|-------------|------------------|-----------------|")

        for i, entry in enumerate(post_conv, 1):
            name = entry.get("name", "Unknown")
            etype = entry.get("type", "—")
            instrument = entry.get("instrument", "—")
            shares = f"{entry.get('shares_or_equivalent', 0):,}"
            pct = f"{entry.get('ownership_pct', 0):.2f}%"
            invested = f"${entry['amount_invested']:,.0f}" if entry.get("amount_invested") else "—"
            lines.append(f"| {i} | {name} | {etype} | {instrument} | {shares} | {pct} | {invested} |")
        lines.append("")

    # Notes
    extraction_notes = cap_table.get("extraction_notes", [])
    if extraction_notes:
        lines.append("### Extraction Notes\n")
        for note in extraction_notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rule-based PDF extraction (kept for backward compat)
# ---------------------------------------------------------------------------

def _extract_cap_table_rules(
    tables: List[List[List[str]]],
    text: str,
    filename: str,
) -> Dict[str, Any]:
    """Rule-based extraction of cap table data from PDF tables/text."""
    extraction: Dict[str, Any] = {
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
        "total_capital_raised": None,
        "notes": [],
    }

    # Extract date
    date_patterns = [
        r"[Aa]s of (\d{1,2}/\d{1,2}/\d{4})",
        r"[Aa]s of (\w+ \d+, \d{4})",
        r"(\d{4}-\d{2}-\d{2})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            extraction["as_of_date"] = match.group(1)
            break

    # Extract total shares
    for pattern in [
        r"Total (?:Authorized|Outstanding)[:\s]+([0-9,]+)",
        r"([0-9,]+)\s+Total\s+Shares",
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                extraction["total_shares_outstanding"] = int(match.group(1).replace(",", ""))
            except ValueError:
                pass

    # Process tables for shareholder data
    for table in tables:
        if not table or len(table) < 2:
            continue
        header_row = None
        for i, row in enumerate(table[:3]):
            row_text = " ".join(str(cell or "").lower() for cell in row)
            if any(kw in row_text for kw in ["shares", "ownership", "%", "capital"]):
                header_row = i
                break

        if header_row is not None:
            headers = [str(cell or "").lower().strip() for cell in table[header_row]]
            name_col = _find_column(headers, ["name", "shareholder", "investor", ""])
            shares_col = _find_column(headers, ["shares", "total shares", "common"])
            pct_col = _find_column(headers, ["%", "ownership", "% ownership", "percentage"])
            class_col = _find_column(headers, ["class", "share class", "type"])

            for row in table[header_row + 1:]:
                if not row or not any(row):
                    continue
                first_cell = str(row[0] or "").strip()
                if not first_cell or first_cell.lower() in ["total", "totals", ""]:
                    continue
                shareholder = _parse_shareholder_row(row, name_col, shares_col, pct_col, class_col, headers)
                if shareholder:
                    extraction["shareholders"].append(shareholder)

    return extraction


def _find_column(headers: List[str], keywords: List[str]) -> Optional[int]:
    """Find column index matching any of the keywords."""
    for i, header in enumerate(headers):
        for keyword in keywords:
            if keyword and keyword in header:
                return i
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
    headers: List[str],
) -> Optional[Dict[str, Any]]:
    """Parse a single shareholder row into structured data."""
    name = None
    if name_col is not None and name_col < len(row):
        name = str(row[name_col] or "").strip()
    elif row:
        name = str(row[0] or "").strip()

    if not name or name.lower() in ["total", "totals", "none", ""]:
        return None
    if name.lower() in ["founders", "investors", "employee option pool", "seed", "series"]:
        return None

    shareholder: Dict[str, Any] = {
        "name": name,
        "shares": 0,
        "ownership_percentage": 0.0,
        "amount_invested": None,
        "share_class": "Common",
        "investor_type": _infer_investor_type(name),
        "vesting_schedule": None,
        "vested_shares": None,
        "unvested_shares": None,
        "price_per_share": None,
        "issue_date": None,
    }

    if shares_col is not None and shares_col < len(row):
        shares_str = str(row[shares_col] or "").replace(",", "").replace("$", "").strip()
        try:
            shareholder["shares"] = int(float(shares_str)) if shares_str else 0
        except ValueError:
            pass

    if pct_col is not None and pct_col < len(row):
        pct_str = str(row[pct_col] or "").replace("%", "").strip()
        try:
            shareholder["ownership_percentage"] = float(pct_str) if pct_str else 0.0
        except ValueError:
            pass

    if class_col is not None and class_col < len(row):
        share_class = str(row[class_col] or "").strip()
        if share_class:
            shareholder["share_class"] = share_class

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
    elif any(term in name_lower for term in ["ventures", "capital", "partners", "fund", "vc", "gmbh", "llc"]):
        return "VC"
    elif any(term in name_lower for term in ["angel", "seed"]):
        return "Angel"
    else:
        return "Investor"


def _needs_llm_extraction(extraction: Dict[str, Any]) -> bool:
    """Check if extraction needs LLM enhancement."""
    shareholders = extraction.get("shareholders", [])
    if len(shareholders) < 2:
        return True
    if not extraction.get("total_shares_outstanding"):
        return True
    return False


# ---------------------------------------------------------------------------
# LLM-based extraction
# ---------------------------------------------------------------------------

def _extract_cap_table_with_llm(
    filename: str,
    text: str,
    tables: List[List[List[str]]],
) -> Optional[Dict[str, Any]]:
    """Use LLM to extract cap table data from text and tables."""
    client = Anthropic()

    tables_text = ""
    for i, table in enumerate(tables[:3]):
        if table:
            tables_text += f"\n--- Table {i+1} ---\n"
            for row in table[:30]:
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
            "amount_invested": number or null,
            "share_class": "Common" or "Seed" or "Series A" etc,
            "investor_type": "Founder" or "VC" or "Angel" or "Employee" or "Option Pool",
            "vesting_schedule": "string or null",
            "price_per_share": number or null,
            "issue_date": "date string or null"
        }}
    ],
    "safes": [
        {{
            "investor_name": "name",
            "amount_invested": number,
            "valuation_cap": number or null,
            "discount_rate": number (0-1 decimal) or null,
            "issue_date": "date string or null"
        }}
    ],
    "convertible_notes": [
        {{
            "investor_name": "name",
            "principal_amount": number,
            "interest_rate": number or null,
            "valuation_cap": number or null,
            "discount_rate": number (0-1 decimal) or null,
            "maturity_date": "date string or null"
        }}
    ],
    "option_pool_size": total option pool shares or null,
    "option_pool_percentage": percentage (0-100) or null,
    "share_prices": {{"round_name": price_per_share}},
    "total_capital_raised": total investment amount or null,
    "notes": ["any important notes about the cap table"]
}}

IMPORTANT:
- Extract ALL shareholders, SAFEs, and convertible notes you can identify
- Include founders, investors, and option pool as separate entries
- Ownership percentages should sum to ~100%
- Discount rates should be decimal (0.20 = 20% discount)
- If data is unclear, use null rather than guessing

Document: {filename}

Text Content:
{text[:6000]}

Tables:
{tables_text}

Return ONLY the JSON object, no other text."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.content[0].text.strip()

        if response_text.startswith("```"):
            response_text = re.sub(r"^```(?:json)?\n?", "", response_text)
            response_text = re.sub(r"\n?```$", "", response_text)

        return json.loads(response_text)

    except Exception as e:
        print(f"   ⚠️ LLM extraction error: {e}")
        return None


def _extract_cap_table_from_dataframe(df) -> Optional[Dict[str, Any]]:
    """Extract cap table data from a pandas DataFrame without LLM."""
    extraction: Dict[str, Any] = {
        "shareholders": [],
        "safes": [],
        "convertible_notes": [],
        "notes": ["Extracted from spreadsheet without LLM"],
    }

    columns_lower = [c.lower() for c in df.columns]
    name_col = shares_col = pct_col = None

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
                    "amount_invested": None,
                    "share_class": "Unknown",
                    "investor_type": _infer_investor_type(name),
                }
                extraction["shareholders"].append(shareholder)

    return extraction if extraction["shareholders"] else None


# ---------------------------------------------------------------------------
# Merging helpers
# ---------------------------------------------------------------------------

def _merge_extractions(rule_based: Dict[str, Any], llm_based: Dict[str, Any]) -> Dict[str, Any]:
    """Merge rule-based and LLM-based extractions."""
    merged = rule_based.copy()
    for key in [
        "as_of_date", "total_shares_outstanding", "fully_diluted_shares",
        "option_pool_size", "option_pool_percentage", "options_granted",
        "options_available", "total_capital_raised",
    ]:
        if not merged.get(key) and llm_based.get(key):
            merged[key] = llm_based[key]

    if len(llm_based.get("shareholders", [])) > len(merged.get("shareholders", [])):
        merged["shareholders"] = llm_based["shareholders"]
    if len(llm_based.get("safes", [])) > len(merged.get("safes", [])):
        merged["safes"] = llm_based["safes"]
    if len(llm_based.get("convertible_notes", [])) > len(merged.get("convertible_notes", [])):
        merged["convertible_notes"] = llm_based["convertible_notes"]

    merged_prices = merged.get("share_prices", {})
    merged_prices.update(llm_based.get("share_prices", {}))
    merged["share_prices"] = merged_prices

    merged_notes = merged.get("notes", [])
    merged_notes.extend(llm_based.get("notes", []))
    merged["notes"] = merged_notes

    return merged


def _merge_cap_table_extractions(extractions: List[Dict[str, Any]]) -> CapTableData:
    """Merge multiple cap table extractions."""
    extractions.sort(key=lambda x: len(x.get("shareholders", [])), reverse=True)
    best = extractions[0]

    source_files = [e.get("source_file", "unknown") for e in extractions]
    best["notes"] = best.get("notes", [])
    best["notes"].append(f"Merged from {len(extractions)} sources: {', '.join(source_files)}")

    return _build_cap_table_data(best)


# ---------------------------------------------------------------------------
# Build final CapTableData
# ---------------------------------------------------------------------------

def _build_cap_table_data(extraction: Dict[str, Any]) -> CapTableData:
    """Build CapTableData TypedDict from extraction dict."""
    # Classify pre/post round
    table_type, reasoning = _classify_table_type(extraction)

    # Convert shareholders
    shareholders: List[ShareholderEntry] = []
    for sh in extraction.get("shareholders", []):
        entry: ShareholderEntry = {
            "name": sh.get("name", "Unknown"),
            "shares": sh.get("shares", 0),
            "ownership_percentage": sh.get("ownership_percentage", 0.0),
            "amount_invested": sh.get("amount_invested"),
            "share_class": sh.get("share_class", "Common"),
            "investor_type": sh.get("investor_type", "Unknown"),
            "vesting_schedule": sh.get("vesting_schedule"),
            "vested_shares": sh.get("vested_shares"),
            "unvested_shares": sh.get("unvested_shares"),
            "price_per_share": sh.get("price_per_share"),
            "issue_date": sh.get("issue_date"),
        }
        shareholders.append(entry)

    # Convert SAFEs
    safes: List[SAFEEntry] = []
    for s in extraction.get("safes", []):
        safe_entry: SAFEEntry = {
            "investor_name": s.get("investor_name", "Unknown"),
            "amount_invested": s.get("amount_invested", 0),
            "valuation_cap": s.get("valuation_cap"),
            "discount_rate": s.get("discount_rate"),
            "conversion_trigger": s.get("conversion_trigger", "Equity financing"),
            "issue_date": s.get("issue_date"),
            "pro_rata_rights": s.get("pro_rata_rights"),
            "estimated_ownership_percentage": s.get("estimated_ownership_percentage"),
        }
        safes.append(safe_entry)

    # Convert notes
    conv_notes: List[ConvertibleNoteEntry] = []
    for n in extraction.get("convertible_notes", []):
        note_entry: ConvertibleNoteEntry = {
            "investor_name": n.get("investor_name", "Unknown"),
            "principal_amount": n.get("principal_amount", 0),
            "interest_rate": n.get("interest_rate", 0),
            "maturity_date": n.get("maturity_date"),
            "valuation_cap": n.get("valuation_cap"),
            "discount_rate": n.get("discount_rate"),
            "estimated_ownership_percentage": n.get("estimated_ownership_percentage"),
        }
        conv_notes.append(note_entry)

    # Build notes
    notes = extraction.get("notes", [])
    if extraction.get("share_prices"):
        prices_str = ", ".join(f"{k}: ${v}" for k, v in extraction["share_prices"].items())
        notes.append(f"Share prices: {prices_str}")

    total_raised = extraction.get("total_capital_raised")
    if total_raised:
        notes.append(f"Total capital raised: ${total_raised:,.0f}")

    # Estimate post-conversion ownership for pre-round tables
    post_conv = None
    post_conv_shares = None
    if table_type == "pre_round" and (safes or conv_notes):
        post_conv = _estimate_post_conversion_ownership(extraction)
        if post_conv:
            post_conv_shares = sum(e.get("shares_or_equivalent", 0) for e in post_conv)

    cap_table_data: CapTableData = {
        "document_source": extraction.get("source_file", "unknown"),
        "as_of_date": extraction.get("as_of_date"),
        "table_type": table_type,
        "table_type_reasoning": reasoning,
        "total_shares_outstanding": extraction.get("total_shares_outstanding"),
        "fully_diluted_shares": extraction.get("fully_diluted_shares"),
        "total_capital_raised": total_raised,
        "shareholders": shareholders,
        "option_pool_size": extraction.get("option_pool_size"),
        "option_pool_percentage": extraction.get("option_pool_percentage"),
        "options_granted": extraction.get("options_granted"),
        "options_available": extraction.get("options_available"),
        "safes": safes,
        "convertible_notes": conv_notes,
        "last_priced_round_valuation": extraction.get("last_priced_round_valuation"),
        "last_priced_round_date": extraction.get("last_priced_round_date"),
        "estimated_post_conversion_shares": post_conv_shares,
        "estimated_post_conversion_ownership": post_conv,
        "extraction_notes": notes,
    }

    return cap_table_data

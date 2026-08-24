"""
Legal Document Extractor

Pulls deal terms out of financing paper: SAFEs, convertible notes, purchase
agreements, term sheets, side letters, charters, and the schedules that travel
with them.

``DataroomAnalysis`` has carried a ``legal_docs`` slot since the beginning, and
the orchestrator has always initialized it to ``[]`` and never filled it. For a
company still being diligenced that was a survivable gap. For a portfolio
archive it is the whole corpus: what an investor holds, at what cap, with which
rights, is stated only in the executed paper.

Two rules shape the design.

**Regex first, model second.** Valuation caps, discount rates, principal
amounts, and dates appear in stereotyped sentences that a pattern matches more
reliably and far more cheaply than a model. The model runs on what is left, and
on the qualitative rights that resist patterning.

**Every number carries the sentence it came from.** A cap table reconciled from
legal documents is only as trustworthy as a reviewer's ability to check it, so
each extracted scalar is stored with its surrounding text in ``evidence``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..dataroom_state import LegalDocData
from ..document_text import extract_text


# Document types this extractor is responsible for.
LEGAL_DOCUMENT_TYPES = {
    "safe_note",
    "convertible_note",
    "purchase_agreement",
    "term_sheet",
    "side_letter",
    "charter_document",
    "subscription_agreement",
    "schedule_of_purchasers",
    "warrant",
    "stockholder_consent",
    "disclosure_schedule",
    "executed_financing_doc",
}


# =============================================================================
# Public API
# =============================================================================

def extract_legal_data(
    documents: List[Dict[str, Any]],
    use_llm: bool = True,
    company_name: Optional[str] = None,
) -> List[LegalDocData]:
    """
    Extract deal terms from every legal document in a classified inventory.

    Args:
        documents: DocumentInventoryItem dicts whose type is in
            ``LEGAL_DOCUMENT_TYPES``.
        use_llm: Run the model pass for the fields patterns cannot reach.
        company_name: Used to disambiguate which party is the issuer.

    Returns:
        One LegalDocData per document that yielded anything, most confident first.
    """
    results: List[LegalDocData] = []

    for doc in documents:
        record = extract_from_document(doc, use_llm=use_llm, company_name=company_name)
        if record:
            results.append(record)

    results.sort(key=lambda r: r.get("confidence", 0.0), reverse=True)
    return results


def extract_from_document(
    doc: Dict[str, Any],
    use_llm: bool = True,
    company_name: Optional[str] = None,
) -> Optional[LegalDocData]:
    """Extract one document's terms. Returns None when there is no text to read."""
    path = Path(doc["file_path"])

    # Legal paper is routinely scanned; OCR is not optional here the way it is
    # for a deck. Cap the page budget — terms live in the first pages and the
    # signature block, not in forty pages of representations.
    extraction = extract_text(path, max_chars=300_000, ocr=True, ocr_max_pages=12)

    record = _blank_record(doc, company_name)

    if not extraction.ok:
        record["extraction_notes"].append(
            f"no readable text: {extraction.error or 'document was empty'}"
        )
        record["confidence"] = 0.0
        return record

    text = extraction.text
    record["extraction_notes"].extend(extraction.notes)
    if extraction.is_scanned:
        record["extraction_notes"].append(
            "text recovered by OCR — verify figures against the source before relying on them"
        )

    _apply_patterns(record, text)
    _apply_signature_check(record, text, doc)

    if use_llm:
        _apply_llm(record, text, doc)

    record["confidence"] = _score(record, extraction.is_scanned)
    return record


# =============================================================================
# Pattern pass
# =============================================================================

# Money written as "$1,500,000", "$1.5 million", "$200K".
_MONEY = r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion|thousand|mm|m\b|k\b)?"

# Contracts define terms in quotes, and the smart quotes survive PDF extraction.
_Q = r"[\"“”‘’']?"

# The copula in a definitions block: `"Valuation Cap" is $48,000,000`.
_DEF = r"\s*(?:means|is|shall\s+be|of|:|equal\s+to)?\s*"

_PATTERNS: List[Tuple[str, str, str]] = [
    # (field, regex, kind)
    ("valuation_cap",
     rf"{_Q}(?:post-money\s+|pre-money\s+)?valuation\s+cap{_Q}{_DEF}{_MONEY}",
     "money"),
    # A YC SAFE names the amount before labelling it:
    # `payment ... of $200,000 (the "Purchase Amount")`.
    ("investment_amount",
     rf"{_MONEY}\s*\(\s*the\s+{_Q}(?:purchase|subscription|investment)\s+amount",
     "money"),
    ("pre_money_valuation",
     rf"pre-?money\s+valuation\s*(?:of|is|:|equal\s+to)?\s*{_MONEY}",
     "money"),
    ("post_money_valuation",
     rf"post-?money\s+valuation\s*(?:of|is|:|equal\s+to)?\s*{_MONEY}",
     "money"),
    ("investment_amount",
     rf"(?:purchase\s+amount|principal\s+amount|aggregate\s+(?:purchase\s+)?(?:price|amount)|"
     rf"subscription\s+amount|investment\s+amount)\s*(?:of|is|:|equal\s+to)?\s*{_MONEY}",
     "money"),
    ("share_price",
     rf"(?:price\s+per\s+share|purchase\s+price\s+per\s+share)\s*(?:of|is|:|equal\s+to)?\s*"
     rf"\$\s?([\d,]+\.\d+)",
     "decimal"),
    ("discount_rate",
     rf"{_Q}discount\s+rate{_Q}{_DEF}(\d{{1,3}}(?:\.\d+)?)\s*%",
     "percent"),
    ("discount_rate",
     r"discount\s+of\s+(\d{1,2}(?:\.\d+)?)\s*%",
     "percent"),
    ("interest_rate",
     r"(?:interest\s+(?:rate|shall\s+accrue)|simple\s+interest)[^.]{0,60}?(\d{1,2}(?:\.\d+)?)\s*%",
     "percent"),
    ("shares_purchased",
     r"([\d,]{4,})\s+shares\s+of\s+(?:series\s+[a-z0-9-]+\s+)?preferred\s+stock",
     "int"),
    ("maturity_date",
     r"maturity\s+date[^.]{0,40}?((?:january|february|march|april|may|june|july|august|"
     r"september|october|november|december)\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
     "date"),
    ("governing_law",
     r"governed\s+by[^.]{0,80}?laws?\s+of\s+the\s+State\s+of\s+([A-Z][a-z]+)",
     "text"),
]

_MULTIPLIERS = {
    "million": 1_000_000, "mm": 1_000_000, "m": 1_000_000,
    "billion": 1_000_000_000,
    "thousand": 1_000, "k": 1_000,
}


def _apply_patterns(record: LegalDocData, text: str) -> None:
    """Fill scalar fields from stereotyped contract sentences."""
    flat = re.sub(r"\s+", " ", text)

    for field, pattern, kind in _PATTERNS:
        # Patterns are listed most-specific-first per field; the first to match
        # wins so a broad fallback cannot overwrite a precise hit.
        if record.get(field) is not None:
            continue

        match = re.search(pattern, flat, re.IGNORECASE)
        if not match:
            continue

        value = _coerce(match, kind)
        if value is None:
            continue

        if field == "discount_rate":
            value = _normalize_discount(value, record, flat, match)
            if value is None:
                continue

        record[field] = value
        record["evidence"][field] = _context(flat, match)

    # Boolean rights. Presence of the phrase is the signal; these clauses are
    # not written in the negative when they are absent, they are simply omitted.
    for field, pattern in (
        ("mfn_clause", r"most\s+favou?red\s+nation|\bMFN\b"),
        ("pro_rata_rights", r"pro\s*rata\s+right|right\s+of\s+first\s+offer\s+to\s+purchase"),
        ("information_rights", r"information\s+rights?"),
        ("management_rights", r"management\s+rights?\s+letter|management\s+rights?"),
    ):
        match = re.search(pattern, flat, re.IGNORECASE)
        if match:
            record[field] = True
            record["evidence"][field] = _context(flat, match)

    # Security type, read off the instrument's own title rather than any mention
    # anywhere in it. An Investors' Rights Agreement discusses warrants at
    # length without being one, and matching on the whole body labelled every
    # ancillary document in a Series A package as a warrant.
    title = flat[:1200]
    for label, pattern in (
        ("SAFE", r"simple\s+agreement\s+for\s+future\s+equity"),
        ("Convertible Note", r"convertible\s+promissory\s+note|note\s+purchase\s+agreement|promissory\s+note"),
        ("Warrant", r"warrant\s+to\s+purchase\s+(?:shares|stock)"),
    ):
        if re.search(pattern, title, re.IGNORECASE):
            record["security_type"] = label
            break
    else:
        series = re.search(r"series\s+([A-Z](?:-\d)?)\s+preferred\s+stock", title, re.IGNORECASE)
        if series:
            record["security_type"] = f"Series {series.group(1).upper()} Preferred"

    # Liquidation preference, e.g. "one times (1x) the Original Issue Price".
    liq = re.search(
        r"(one|two|1|2)\s*(?:\(\d\))?\s*times?[^.]{0,60}?original\s+issue\s+price",
        flat, re.IGNORECASE,
    )
    if liq:
        record["liquidation_preference"] = liq.group(0)[:160]
        record["evidence"]["liquidation_preference"] = _context(flat, liq)

    anti = re.search(
        r"(broad-based\s+weighted\s+average|narrow-based\s+weighted\s+average|full\s+ratchet)",
        flat, re.IGNORECASE,
    )
    if anti:
        record["anti_dilution"] = anti.group(1)
        record["evidence"]["anti_dilution"] = _context(flat, anti)

    # Effective date from the preamble: "dated as of March 21, 2024".
    dated = re.search(
        r"dated\s+as\s+of\s+((?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2},\s+\d{4})",
        flat, re.IGNORECASE,
    )
    if dated:
        record["effective_date"] = dated.group(1)
        record["document_date"] = dated.group(1)
        record["evidence"]["effective_date"] = _context(flat, dated)


def _normalize_discount(
    value: float, record: LegalDocData, flat: str, match: re.Match
) -> Optional[float]:
    """
    Convert a SAFE's "Discount Rate" into the discount actually granted.

    This is the trap in the instrument. A Y Combinator SAFE reading
    ``"Discount Rate" is 85%`` grants a **15%** discount — the rate is the
    fraction of the price the investor pays, not the reduction. Recording 85
    here would overstate the discount by more than five times and flow straight
    into any conversion math built on it.

    A term sheet saying "a discount of 20%" means what it says. The two are told
    apart by magnitude, which is safe because real discounts are small and real
    Discount Rates are large; anything ambiguous is rejected rather than guessed.
    """
    if value <= 0 or value > 100:
        return None

    if value >= 50:
        converted = round(100.0 - value, 4)
        record["extraction_notes"].append(
            f"'Discount Rate' of {value:g}% is the SAFE convention for a "
            f"{converted:g}% discount; recorded as {converted:g}%"
        )
        record["evidence"]["discount_rate"] = _context(flat, match)
        return converted

    return value


def _coerce(match: re.Match, kind: str):
    raw = match.group(1)
    try:
        if kind == "money":
            amount = float(raw.replace(",", ""))
            unit = (match.group(2) or "").strip().lower()
            return amount * _MULTIPLIERS.get(unit, 1)
        if kind == "decimal":
            return float(raw.replace(",", ""))
        if kind == "percent":
            return float(raw)
        if kind == "int":
            return int(raw.replace(",", ""))
        return raw.strip()
    except (ValueError, IndexError):
        return None


def _context(text: str, match: re.Match, window: int = 110) -> str:
    """The sentence fragment around a match, for a reviewer to check against."""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


# =============================================================================
# Execution status
# =============================================================================

_SIGNATURE_MARKERS = [
    r"/s/\s*[A-Z]",                     # conformed signature
    r"DocuSign|Adobe\s+Sign|HelloSign|Dropbox\s+Sign",
    r"Envelope\s+ID",
    r"By:\s*_+\s*\n?\s*Name:",
]

_FORM_MARKERS = [
    r"\bFORM\s+OF\b",
    r"\[\s*(?:signature\s+page\s+follows|_+)\s*\]",
    r"\bDRAFT\b",
    r"\[\s*●\s*\]|\[\s*\*\s*\]",       # unfilled bracketed blanks
]


def _apply_signature_check(record: LegalDocData, text: str, doc: Dict[str, Any]) -> None:
    """
    Decide whether the paper is signed.

    The filename is checked first because "[Executed]" in a filename is a
    deliberate assertion by whoever filed it, then the text is checked for
    corroboration. Disagreement is recorded rather than resolved silently.
    """
    filename = doc.get("filename", "").lower()
    from_name: Optional[bool] = None
    if re.search(r"executed|signed|countersigned", filename):
        from_name = True
    elif re.search(r"form of|template|draft|unexecuted", filename):
        from_name = False

    head_and_tail = text[:6000] + "\n" + text[-8000:]
    signed = any(re.search(p, head_and_tail, re.IGNORECASE) for p in _SIGNATURE_MARKERS)
    is_form = any(re.search(p, head_and_tail, re.IGNORECASE) for p in _FORM_MARKERS)

    from_text: Optional[bool] = None
    if signed and not is_form:
        from_text = True
    elif is_form and not signed:
        from_text = False

    if from_name is not None and from_text is not None and from_name != from_text:
        record["extraction_notes"].append(
            f"filename says {'executed' if from_name else 'unexecuted'} but the text "
            f"says {'executed' if from_text else 'unexecuted'} — verify manually"
        )

    record["is_executed"] = from_name if from_name is not None else from_text


# =============================================================================
# Model pass
# =============================================================================

_LLM_FIELDS = """
- investors: list of investing entity names, exactly as written
- company_name: the issuing company
- counsel: law firms named in the document
- board_seats: integer number of board seats granted to investors, if stated
- conversion_trigger: what causes conversion (e.g. "Equity Financing of at least $1,000,000")
- closing_conditions: list of conditions to closing
- key_covenants: list of the operative obligations the company takes on
- liquidation_preference: the preference as stated, if present
- anti_dilution: the anti-dilution formula as stated, if present
"""


def _apply_llm(record: LegalDocData, text: str, doc: Dict[str, Any]) -> None:
    """
    Fill the qualitative fields the pattern pass cannot reach.

    Sends the head and the tail: the economics are in the opening sections and
    the parties are in the signature block, while the middle is boilerplate
    representations that would only spend tokens.
    """
    excerpt = text[:14_000]
    if len(text) > 22_000:
        excerpt += "\n\n[...omitted middle...]\n\n" + text[-8_000:]

    prompt = f"""Extract deal terms from this legal document. Report only what the
document states. If a field is not stated, use null — never infer, never fill from
what is typical for this instrument type.

FILENAME: {doc.get('filename')}
CLASSIFIED AS: {doc.get('document_type')}

Fields to extract:
{_LLM_FIELDS}

DOCUMENT:
---
{excerpt}
---

Respond with JSON only, no prose:
{{"investors": [], "company_name": null, "counsel": [], "board_seats": null,
"conversion_trigger": null, "closing_conditions": [], "key_covenants": [],
"liquidation_preference": null, "anti_dilution": null}}
"""

    try:
        from anthropic import Anthropic

        client = Anthropic()
        response = client.messages.create(
            model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
            max_tokens=2000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            record["extraction_notes"].append("model returned no JSON")
            return

        parsed = json.loads(match.group())
    except Exception as e:
        record["extraction_notes"].append(f"model extraction failed: {type(e).__name__}: {e}")
        return

    # The pattern pass is the more trustworthy of the two for anything it found,
    # because its result is anchored to a quoted sentence. The model only fills
    # holes; it never overwrites.
    for field in (
        "investors", "counsel", "closing_conditions", "key_covenants",
    ):
        value = parsed.get(field)
        if isinstance(value, list) and value:
            record[field] = [str(v) for v in value]

    for field in (
        "company_name", "board_seats", "conversion_trigger",
        "liquidation_preference", "anti_dilution",
    ):
        value = parsed.get(field)
        if value not in (None, "", []) and not record.get(field):
            record[field] = value
            record["evidence"][field] = "model extraction (no quoted anchor)"

    record["extraction_notes"].append("model pass completed")


# =============================================================================
# Scoring and scaffolding
# =============================================================================

# Fields that make a legal extraction useful. Confidence is the share of these
# that were actually found, not a model's self-report.
_SCORED_FIELDS = [
    "investment_amount", "valuation_cap", "discount_rate", "pre_money_valuation",
    "post_money_valuation", "share_price", "security_type", "effective_date",
    "investors", "is_executed",
]


def _score(record: LegalDocData, was_scanned: bool) -> float:
    found = sum(1 for f in _SCORED_FIELDS if record.get(f) not in (None, "", [], {}))
    score = found / len(_SCORED_FIELDS)

    # An anchored figure is worth more than an unanchored one.
    anchored = sum(1 for k, v in record["evidence"].items() if v != "model extraction (no quoted anchor)")
    score = min(1.0, score + 0.02 * anchored)

    if was_scanned:
        score *= 0.8  # OCR text can transpose digits; say so in the number.

    return round(score, 2)


def _blank_record(doc: Dict[str, Any], company_name: Optional[str]) -> LegalDocData:
    return {
        "document_source": doc.get("filename", ""),
        "document_type": doc.get("document_type", "unknown"),
        "document_date": None,
        "is_executed": doc.get("is_executed"),
        "effective_date": None,
        "investment_amount": None,
        "pre_money_valuation": None,
        "post_money_valuation": None,
        "share_price": None,
        "shares_purchased": None,
        "security_type": None,
        "valuation_cap": None,
        "discount_rate": None,
        "interest_rate": None,
        "maturity_date": None,
        "mfn_clause": None,
        "conversion_trigger": None,
        "liquidation_preference": None,
        "anti_dilution": None,
        "board_seats": None,
        "pro_rata_rights": None,
        "information_rights": None,
        "management_rights": None,
        "closing_conditions": [],
        "key_covenants": [],
        "investors": [],
        "company_name": company_name or "",
        "counsel": [],
        "governing_law": None,
        "evidence": {},
        "confidence": 0.0,
        "extraction_notes": [],
    }


# =============================================================================
# Reconciliation
# =============================================================================

def reconcile_legal_docs(records: List[LegalDocData]) -> Dict[str, Any]:
    """
    Roll a company's legal documents into one position, flagging disagreement.

    Executed documents outrank forms: when a signed purchase agreement and an
    unexecuted form of the same instrument state different numbers, the signed
    one is what happened. Conflicts are reported rather than averaged away.
    """
    summary: Dict[str, Any] = {
        "documents": len(records),
        "executed": sum(1 for r in records if r.get("is_executed")),
        "unexecuted": sum(1 for r in records if r.get("is_executed") is False),
        "instruments": {},
        "terms": {},
        "conflicts": [],
        "investors": [],
    }

    for record in records:
        kind = record.get("security_type") or record.get("document_type") or "unknown"
        summary["instruments"][kind] = summary["instruments"].get(kind, 0) + 1

    seen_investors: Dict[str, str] = {}
    for record in records:
        for investor in record.get("investors", []):
            seen_investors.setdefault(investor.strip().lower(), investor.strip())
    summary["investors"] = sorted(seen_investors.values())

    for field in (
        "valuation_cap", "discount_rate", "pre_money_valuation",
        "post_money_valuation", "share_price", "investment_amount",
    ):
        claims = [
            {
                "value": r[field],
                "source": r["document_source"],
                "executed": r.get("is_executed"),
                "evidence": r["evidence"].get(field, ""),
            }
            for r in records
            if r.get(field) is not None
        ]
        if not claims:
            continue

        distinct = {c["value"] for c in claims}
        if len(distinct) == 1:
            summary["terms"][field] = claims[0]["value"]
            continue

        executed_claims = [c for c in claims if c["executed"]]
        preferred = executed_claims or claims
        summary["terms"][field] = preferred[0]["value"]
        summary["conflicts"].append({
            "field": field,
            "values": sorted(distinct, key=lambda v: (v is None, v)),
            "claims": claims,
            "resolution": (
                "took the executed document's value"
                if executed_claims else
                "no executed document states this field — value is provisional"
            ),
        })

    return summary

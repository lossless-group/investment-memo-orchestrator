"""
Document Classifier for Dataroom Analysis

Four-stage classification, cheapest signal first:

1. Path-based classification over the whole relative path, not just the parent
2. Filename heuristics
3. Content signals matched against real extracted text (free, no API call)
4. LLM classification for whatever still has not resolved

Two failure modes drove the current design and are worth stating plainly,
because both produced confidently wrong answers rather than honest unknowns.

**The company name leaks into the patterns.** Every file in a dataroom repeats
the company's name, and a company called "Vantage Products" put the token
``product`` into all 43 of its filenames. Substring matching then classified the
cap table, the charter, the voting agreement, and the side letter alike as
``product_documentation`` at 0.83 confidence. Names are stripped from the
matching surface before any pattern runs — see ``build_name_stopwords``.

**Bidirectional containment.** The old directory match accepted
``category in key or key in category``, so the short keys in the category map
matched almost anything. Matching is now anchored on word boundaries in one
direction only.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .dataroom_state import DocumentInventoryItem
from .document_scanner import parse_directory_category


# =============================================================================
# Taxonomy
# =============================================================================

# Every type the classifier may emit. A dataroom for a company being diligenced
# and an archive for a company already held are different corpora: the second is
# dominated by executed paper, board materials, and internal memos, none of
# which the original pitch-oriented taxonomy could name.
DOCUMENT_TYPES: Set[str] = {
    # --- Pitch / narrative ---
    "pitch_deck",
    "product_documentation",
    "marketing_collateral",
    "competitive_analysis",
    "team_bios",
    # --- Numbers ---
    "financial_statements",
    "financial_projections",
    "cap_table",
    "traction_metrics",
    "customer_list",
    "pipeline_metrics",
    # --- Deal paper, pre-close ---
    "term_sheet",
    "safe_note",
    "convertible_note",
    "purchase_agreement",
    # --- Deal paper, executed ---
    "executed_financing_doc",
    "charter_document",
    "stockholder_consent",
    "side_letter",
    "warrant",
    "disclosure_schedule",
    "schedule_of_purchasers",
    # --- Fund / SPV administration ---
    "spv_document",
    "subscription_agreement",
    "investor_questionnaire",
    "wire_instructions",
    # --- Post-investment ---
    "board_materials",
    "investor_update",
    # --- Internal ---
    "internal_deal_memo",
    "memo_template",
    "correspondence",
    # --- Supporting research ---
    "market_research",
    "scientific_paper",
    "ip_strategy",
    "diligence_analysis",
    "call_notes",
    # --- Catch-all ---
    "unknown",
}


# =============================================================================
# Path Category Mapping
# =============================================================================

# Matched against the document's whole relative path, most specific first.
DIRECTORY_CATEGORY_MAP: Dict[str, str] = {
    # Multi-word keys first — they carry more evidence than the single words
    # further down and must win when both would match.
    "executive summary": "pitch_deck",
    "executed documents": "executed_financing_doc",
    "transaction documents": "executed_financing_doc",
    "closing documents": "executed_financing_doc",
    "series seed documents": "executed_financing_doc",
    "financing documents": "executed_financing_doc",
    "second tranch": "executed_financing_doc",
    "second tranche": "executed_financing_doc",
    "board materials": "board_materials",
    "board meeting": "board_materials",
    "market research": "market_research",
    "competitive overview": "competitive_analysis",
    "gtm": "competitive_analysis",
    "cap table": "cap_table",
    "data room": "unknown",
    "dataroom": "unknown",

    # Single-word keys
    "pitch": "pitch_deck",
    "deck": "pitch_deck",
    "decks": "pitch_deck",
    "presentation": "pitch_deck",
    "product": "product_documentation",
    "technology": "product_documentation",
    "architecture": "product_documentation",
    "marketing": "marketing_collateral",
    "collateral": "marketing_collateral",
    "competitive": "competitive_analysis",
    "competitors": "competitive_analysis",
    "financial": "financial_statements",
    "financials": "financial_statements",
    "finance": "financial_statements",
    "legal": "executed_financing_doc",
    "corporate": "charter_document",
    "team": "team_bios",
    "leadership": "team_bios",
    "management": "team_bios",
    "founders": "team_bios",
    "traction": "traction_metrics",
    "customers": "customer_list",
    "pipeline": "pipeline_metrics",
    "metrics": "traction_metrics",
    "governance": "board_materials",
    "board": "board_materials",
    "updates": "investor_update",
    "research": "market_research",
    "diligence": "diligence_analysis",
    "spv": "spv_document",
    "misc": "unknown",
    "miscellaneous": "unknown",
}

# Directory names that describe a shelf rather than a document kind. They still
# provide a default, but at a confidence any real content signal will beat.
WEAK_DIRECTORY_KEYS: Set[str] = {
    "research", "misc", "miscellaneous", "diligence", "data room", "dataroom",
}


# =============================================================================
# Filename Patterns
# =============================================================================

# Ordered most-specific-first within each type. Patterns are matched against a
# filename with the company name already removed.
FILENAME_PATTERNS: Dict[str, List[str]] = {
    # --- Executed deal paper. Checked early: an executed charter is a charter,
    #     not "corporate documentation", and the signature is the salient fact.
    "charter_document": [
        r"certificate of incorporation", r"a[_\s]?r charter", r"\bcharter\b",
        r"certificate of amendment", r"articles of incorporation", r"\bbylaws?\b",
    ],
    "schedule_of_purchasers": [r"schedule of purchasers", r"schedule of investors"],
    "disclosure_schedule": [r"disclosure schedule"],
    "side_letter": [r"side[\s_-]?letter"],
    "warrant": [r"\bwarrant\b"],
    "stockholder_consent": [
        r"stockholder consent", r"shareholder consent", r"board consent",
        r"written consent", r"\bconsent\b.*\bexecuted\b",
    ],
    "purchase_agreement": [
        r"stock purchase agreement", r"preferred stock.*purchase agreement",
        r"purchase agreement", r"preferred stock agreement", r"\bspa\b",
    ],
    "convertible_note": [
        r"note purchase agreement", r"convertible note", r"promissory note",
        r"\bnote\b.*\bfund\b",
    ],
    "safe_note": [
        r"\bsafe\b", r"simple agreement for future equity",
        r"pre[\s_-]?money[\s_-]?safe", r"post[\s_-]?money[\s_-]?safe",
    ],
    "term_sheet": [r"term[\s_-]?sheet", r"termsheet"],

    # --- Fund / SPV administration ---
    "subscription_agreement": [r"subscription agreement"],
    "investor_questionnaire": [
        r"accredited investor", r"investor questionnaire", r"suitability questionnaire",
    ],
    "wire_instructions": [
        r"wire (?:transfer )?(?:transaction )?routing", r"wire instructions",
        r"\bach\b.*\bwire\b", r"routing instructions",
    ],
    "spv_document": [r"\bspv\b", r"special purpose vehicle", r"series of decile"],

    # --- Internal ---
    "memo_template": [r"memo template", r"template v\d", r"\btemplate\b"],
    "internal_deal_memo": [r"deal[\s_-]?memo", r"investment memo", r"ic memo"],
    "correspondence": [
        r"\bmail\b[\s_-]", r"\bemail\b", r"closing update", r"\bcorrespondence\b",
    ],

    # --- Post-investment ---
    "board_materials": [
        r"board meeting", r"\bbod\b", r"board deck", r"board update", r"non[\s_-]?con",
    ],
    "investor_update": [r"investor update", r"lp update", r"quarterly update", r"lpac"],

    # --- Numbers ---
    "cap_table": [
        r"cap[\s_-]?table", r"captable", r"detailed[\s_-]?cap", r"pro[\s_-]?forma",
        r"stock ledger", r"capitalization",
    ],
    "financial_statements": [
        r"p\s*&\s*l", r"profit.{0,5}loss", r"income statement",
        r"balance sheet", r"cash flow", r"^financials?$",
    ],
    "financial_projections": [
        r"financial model", r"operating model", r"projection", r"forecast", r"budget",
    ],

    # --- Supporting research ---
    "ip_strategy": [
        r"patent strategy", r"\bip\b strategy", r"ip pov", r"freedom to operate",
        r"\bfto\b", r"patent",
    ],
    "scientific_paper": [
        r"\bet al\b", r"whitepaper", r"white paper", r"journal", r"preprint",
        r"\barxiv\b", r"doi[\s_-]", r"psychrev", r"nature[\s_-]",
    ],
    "market_research": [
        r"market (?:size|report|analysis)", r"industry report", r"market share",
        r"forecast to \d{4}", r"market size.*\d{4}", r"trends?[\s_-]",
        # Sizing language about an industry, not about this company's P&L.
        r"sales forecast", r"market forecast", r"sales estimate",
        r"\bmarkets?\b.*projections?", r"blockbuster", r"growth analysis",
    ],

    # --- Pitch / narrative ---
    "pitch_deck": [
        r"pitch[\s_-]?deck", r"investor[\s_-]?deck", r"reading deck",
        r"\bdeck\b", r"one[\s_-]?pager", r"teaser", r"executive summary",
    ],
    "competitive_analysis": [
        r"competitive", r"competitor", r"landscape", r"battlecard",
        r"market map", r"\bswot\b",
    ],
    "team_bios": [r"\bteam\b", r"\bbios?\b", r"founders?", r"leadership"],
    "customer_list": [r"customer list", r"\bcustomers\b", r"\blogos\b"],
    "product_documentation": [
        r"\bspec(?:ification)?s?\b", r"architecture", r"roadmap",
        r"technical overview", r"\bmvp\b",
    ],
    "marketing_collateral": [r"\bcollateral\b", r"datasheet", r"brochure"],
    "traction_metrics": [r"\btraction\b", r"\bkpis?\b", r"\bmetrics\b"],
    "call_notes": [
        r"call notes", r"meeting notes", r"\bnotes\b[\s_-]", r"diligence call",
        r"reference call", r"founder call",
    ],
}

# Types whose evidence is a signature or a filing rather than a topic. When one
# of these matches, it outranks a topical match of similar strength.
_EXECUTED_TYPES = {
    "charter_document", "schedule_of_purchasers", "disclosure_schedule",
    "side_letter", "warrant", "stockholder_consent", "purchase_agreement",
    "convertible_note", "safe_note", "term_sheet", "subscription_agreement",
    "investor_questionnaire", "wire_instructions",
}


# =============================================================================
# Content Signals
# =============================================================================

# Phrases that identify a document from its own text. This stage used to exist
# as a dict that nothing read; it now runs against the shared text layer and
# resolves most of what filenames cannot, without an API call.
CONTENT_SIGNALS: Dict[str, List[str]] = {
    "pitch_deck": [
        # "market size"/"tam" removed: a market report is not a pitch deck.
        "investment opportunity", "use of funds", "our team", "the ask",
        "go-to-market", "why now", "traction to date", "founded in",
    ],
    "competitive_analysis": [
        "competitive landscape", "competitors", "differentiation",
        "feature comparison", "barriers to entry", "market share",
    ],
    "financial_statements": [
        "total liabilities", "statement of operations", "balance sheet",
        "cost of goods sold", "total operating expenses", "net income (loss)",
    ],
    "financial_projections": [
        "projected revenue", "forecast assumptions", "run rate", "burn rate",
    ],
    "cap_table": [
        # Deliberately narrow. "preferred stock" and "price per share" appear in
        # every equity financing instrument; only ledger language is diagnostic.
        "fully diluted", "shares outstanding", "option pool",
        "capitalization table", "% ownership", "ownership %",
        "outstanding shares", "as converted",
    ],
    "term_sheet": [
        "pre-money valuation", "post-money valuation", "liquidation preference",
        "anti-dilution", "protective provisions", "board composition",
    ],
    "safe_note": [
        "simple agreement for future equity", "valuation cap", "discount rate",
        "safe preferred stock", "post-money safe", "pre-money safe",
    ],
    "convertible_note": [
        "promissory note", "principal amount", "maturity date",
        "interest rate", "conversion price", "note purchase agreement",
    ],
    "purchase_agreement": [
        "purchase agreement", "representations and warranties",
        "conditions to closing", "the closing", "purchased shares",
    ],
    "charter_document": [
        "certificate of incorporation", "authorized to issue",
        "the corporation", "par value", "secretary of state",
    ],
    "stockholder_consent": [
        "written consent", "undersigned stockholders", "action by written consent",
        "resolved, that", "in lieu of a meeting",
    ],
    "side_letter": ["side letter", "this letter agreement", "management rights"],
    "subscription_agreement": [
        "subscription agreement", "the subscriber", "subscription amount",
    ],
    "investor_questionnaire": [
        "accredited investor", "rule 501", "regulation d",
        "net worth", "please check", "verification of status",
    ],
    "wire_instructions": [
        "routing number", "account number", "swift", "beneficiary bank",
        "aba number", "wire instructions",
    ],
    "board_materials": [
        "board of directors", "bod meeting", "board deck",
        "management update", "quarter in review",
    ],
    "investor_update": [
        "investor update", "dear investors", "quarterly update", "highlights",
    ],
    "internal_deal_memo": [
        "investment thesis", "recommendation", "deal memo",
        "why now", "risks and mitigations", "investment recommendation",
    ],
    "scientific_paper": [
        "doi.org", "et al.", "supplementary material", "peer review",
        "we show that", "this paper", "in this study", "our results",
        "corresponding author", "conflict of interest", "acknowledgements",
        "received:", "accepted:", "keywords:",
    ],
    "market_research": [
        "cagr", "market is expected to", "industry analysis",
        "forecast period", "market size", "market share", "compound annual growth",
        "market is projected", "global market",
    ],
    "ip_strategy": [
        "patent", "prior art", "claims", "uspto",
        "provisional application", "freedom to operate",
    ],
    "team_bios": [
        "prior to founding", "he holds", "she holds", "they hold",
        "co-founder", "ph.d.", "previously served",
    ],
    "correspondence": ["from:", "sent:", "subject:", "wrote:", "best regards"],
    "call_notes": [
        # Fragmentary, bulleted, first-person shorthand — the shape of live notes.
        "risk:", "follow up", "next steps", "he said", "they said",
        "action item", "takeaway",
    ],
}


# =============================================================================
# Name stripping
# =============================================================================

# Words that appear in company names but also carry classification meaning.
# Removing them along with the name would be safe; keeping them would let the
# name leak. They are dropped from the matching surface either way, so the
# entry exists to document the tradeoff rather than to change behavior.
_NAME_NOISE = {
    "inc", "inc.", "llc", "ltd", "corp", "corporation", "co", "company",
    "holdings", "labs", "technologies", "the", "and", "of", "a", "an",
}


def build_name_stopwords(*names: Optional[str]) -> Set[str]:
    """
    Turn company / firm names into the token set to strip before matching.

    ``"Vantage Products"`` yields ``{"vantage", "products", "product"}`` —
    the singular is included because filenames pluralize inconsistently and a
    surviving ``product`` is exactly the leak this exists to stop.
    """
    stop: Set[str] = set()
    for name in names:
        if not name:
            continue
        for token in re.split(r"[^A-Za-z0-9]+", name.lower()):
            if not token or token in _NAME_NOISE or len(token) < 3:
                continue
            stop.add(token)
            # Cheap depluralization; a token and its plural are the same name.
            if token.endswith("s") and len(token) > 3:
                stop.add(token[:-1])
            else:
                stop.add(token + "s")
    return stop


def strip_names(text: str, stopwords: Set[str]) -> str:
    """Remove name tokens from a matching surface, leaving separators intact."""
    if not stopwords:
        return text
    return re.sub(
        r"\b(?:%s)\b" % "|".join(re.escape(w) for w in sorted(stopwords, key=len, reverse=True)),
        " ",
        text,
        flags=re.IGNORECASE,
    )


def _normalize(text: str) -> str:
    """Lowercase, turn separators into spaces, collapse runs."""
    text = re.sub(r"[_\-.]+", " ", text.lower())
    return re.sub(r"\s{2,}", " ", text).strip()


# =============================================================================
# Main Classification
# =============================================================================

def classify_documents(
    inventory: List[DocumentInventoryItem],
    use_llm: bool = False,
    company_name: Optional[str] = None,
    firm_name: Optional[str] = None,
    dataroom_root: Optional[str] = None,
    use_content: bool = True,
) -> List[DocumentInventoryItem]:
    """
    Classify every document in an inventory.

    Args:
        inventory: DocumentInventoryItem dicts from the scanner.
        use_llm: Send still-unresolved documents to the LLM.
        company_name: Portfolio company name, stripped before pattern matching.
        firm_name: Investing firm name, stripped for the same reason — every
            executed document names the investor too.
        dataroom_root: Root the relative path is computed against. Inferred
            from the common prefix of the inventory when omitted.
        use_content: Match document text against CONTENT_SIGNALS. Free but
            requires reading each file; disable for a fast filename-only pass.

    Returns:
        The same list, with classification fields populated.
    """
    if not inventory:
        return inventory

    root = Path(dataroom_root) if dataroom_root else _infer_root(inventory)
    stopwords = build_name_stopwords(company_name, firm_name, root.name if root else None)

    for item in inventory:
        rel_path = _relative_path(item, root)
        surface = strip_names(_normalize(rel_path), stopwords)
        filename_surface = strip_names(_normalize(Path(item["filename"]).stem), stopwords)

        candidates: List[Tuple[str, float, str, str]] = []  # (type, conf, source, why)

        # --- Stage 1: path ---
        path_type, path_conf, path_why = _classify_by_path(rel_path, stopwords)
        if path_type != "unknown":
            candidates.append((path_type, path_conf, "directory", path_why))

        # --- Stage 2: filename ---
        name_type, name_conf, name_why = _classify_by_filename(filename_surface, item["extension"])
        if name_type != "unknown":
            candidates.append((name_type, name_conf, "filename", name_why))

        best = _pick(candidates)

        # --- Stage 3: content signals ---
        # Run whenever the cheap stages are not convincing. Text is authoritative
        # over a filename: an "Executed Documents" folder says where a file sits,
        # its text says what it is.
        if use_content and (best is None or best[1] < 0.85):
            content_type, content_conf, content_why = _classify_by_signals(item["file_path"])
            if content_type != "unknown":
                candidates.append((content_type, content_conf, "content", content_why))
                best = _pick(candidates)

        # --- Stage 4: LLM ---
        if use_llm and (best is None or best[1] < 0.7):
            llm_type, llm_conf, llm_why = _classify_by_content(item, surface)
            if llm_type != "unknown":
                candidates.append((llm_type, llm_conf, "llm", llm_why))
                best = _pick(candidates)

        if best is None:
            item["document_type"] = "unknown"
            item["classification_confidence"] = 0.0
            item["classification_source"] = "unknown"
            item["classification_reasoning"] = "no directory, filename, or content signal matched"
        else:
            doc_type, confidence, source, why = best
            item["document_type"] = doc_type
            item["classification_confidence"] = round(confidence, 2)
            item["classification_source"] = source
            item["classification_reasoning"] = why

        item = refine_classification(item)

    return inventory


def _pick(candidates: Sequence[Tuple[str, float, str, str]]):
    """
    Choose among competing signals.

    Agreement between two independent signals is stronger evidence than either
    alone, so a type named by more than one source gets a bonus before the
    highest-confidence candidate wins.
    """
    if not candidates:
        return None

    votes: Dict[str, int] = {}
    for doc_type, _, _, _ in candidates:
        votes[doc_type] = votes.get(doc_type, 0) + 1

    def score(c: Tuple[str, float, str, str]) -> float:
        doc_type, confidence, _, _ = c
        bonus = 0.08 * (votes[doc_type] - 1)
        if doc_type in _EXECUTED_TYPES:
            bonus += 0.03
        return min(confidence + bonus, 0.99)

    best = max(candidates, key=score)
    return (best[0], score(best), best[2], best[3])


def _infer_root(inventory: List[DocumentInventoryItem]) -> Optional[Path]:
    """Deepest directory containing every document in the inventory."""
    try:
        paths = [Path(i["file_path"]).parent for i in inventory]
        common = os.path.commonpath([str(p) for p in paths])
        return Path(common)
    except (ValueError, KeyError):
        return None


def _relative_path(item: DocumentInventoryItem, root: Optional[Path]) -> str:
    p = Path(item["file_path"])
    if root:
        try:
            return str(p.relative_to(root))
        except ValueError:
            pass
    return str(Path(item.get("parent_directory", "")) / p.name)


# =============================================================================
# Stage 1 — Path
# =============================================================================

def _classify_by_path(rel_path: str, stopwords: Set[str]) -> Tuple[str, float, str]:
    """
    Match category keys against the directory portion of the relative path.

    Only directories are considered; the filename gets its own stage. Longer
    keys win, so ``executed documents`` beats a bare ``documents``.
    """
    directory = str(Path(rel_path).parent)
    if directory in (".", ""):
        return "unknown", 0.0, ""

    surface = strip_names(_normalize(directory), stopwords)
    if not surface:
        return "unknown", 0.0, ""

    best_type, best_key = "unknown", ""
    for key, doc_type in DIRECTORY_CATEGORY_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", surface) and len(key) > len(best_key):
            best_type, best_key = doc_type, key

    if best_type == "unknown":
        return "unknown", 0.0, ""

    # A two-word directory name is much better evidence than a one-word one.
    confidence = 0.86 if " " in best_key else 0.72

    # Container words name a shelf, not a kind. A "Research" folder holds market
    # reports and journal articles side by side, so it must not outvote what the
    # document itself says.
    if best_key in WEAK_DIRECTORY_KEYS:
        confidence = 0.50

    return best_type, confidence, f"directory '{best_key}' in path"


# =============================================================================
# Stage 2 — Filename
# =============================================================================

def _classify_by_filename(surface: str, extension: str) -> Tuple[str, float, str]:
    """
    Match filename patterns against a name with the company name removed.

    Confidence scales with how much of the (name-stripped) filename the match
    accounts for, so a long specific phrase outranks an incidental word.
    """
    if not surface:
        return "unknown", 0.0, ""

    best_type, best_conf, best_match = "unknown", 0.0, ""

    for doc_type, patterns in FILENAME_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, surface)
            if not m:
                continue
            matched = m.group().strip()
            coverage = len(matched) / max(len(surface), 1)
            confidence = min(0.62 + len(matched) / 40 + coverage * 0.15, 0.92)
            if doc_type in _EXECUTED_TYPES:
                confidence = min(confidence + 0.03, 0.93)
            if confidence > best_conf:
                best_type, best_conf, best_match = doc_type, confidence, matched

    if best_type != "unknown":
        return best_type, best_conf, f"filename matched '{best_match}'"

    # Extension-only hints. Deliberately weak — a spreadsheet in a dataroom is
    # usually financial, but "usually" is not a classification.
    if extension in (".xlsx", ".xls", ".xlsm", ".csv"):
        return "financial_statements", 0.35, f"{extension} with no other signal"

    return "unknown", 0.0, ""


# =============================================================================
# Stage 3 — Content signals
# =============================================================================

def _classify_by_signals(file_path: str) -> Tuple[str, float, str]:
    """
    Score document text against CONTENT_SIGNALS.

    Reads only the head of the document: the identifying phrases of a legal
    instrument or a paper are in its first page, and scanning a 74-page board
    deck in full to learn it is a board deck is wasted work.
    """
    from .document_text import extract_text

    # OCR only the first few pages, and only when the text layer came back
    # empty. A scanned document is still a document; leaving scans permanently
    # unclassified was how the EEG paper and the executed signature pages ended
    # up in the same "unknown" bucket as genuinely unreadable files.
    extraction = extract_text(file_path, max_chars=20_000, ocr=False)
    if not extraction.ok and Path(file_path).suffix.lower() == ".pdf":
        extraction = extract_text(file_path, max_chars=20_000, ocr=True, ocr_max_pages=3)
    if not extraction.ok:
        return "unknown", 0.0, ""

    text = extraction.text.lower()

    scores: Dict[str, List[str]] = {}
    for doc_type, phrases in CONTENT_SIGNALS.items():
        hits = [p for p in phrases if p in text]
        if hits:
            scores[doc_type] = hits

    if not scores:
        return "unknown", 0.0, ""

    doc_type, hits = max(scores.items(), key=lambda kv: len(kv[1]))
    if len(hits) < 2:
        # One generic phrase is noise; "abstract" appears in plenty of decks.
        return "unknown", 0.0, ""

    confidence = min(0.60 + 0.07 * len(hits), 0.90)
    shown = ", ".join(f"'{h}'" for h in hits[:3])
    return doc_type, confidence, f"content signals: {shown} ({len(hits)} hits)"


# =============================================================================
# Stage 4 — LLM
# =============================================================================

def _classify_by_content(item: DocumentInventoryItem, surface: str) -> Tuple[str, float, str]:
    """
    Ask the model, offering the full taxonomy.

    The previous implementation built its category list from the directory map's
    values only, so the model could not return ``cap_table`` or ``term_sheet``
    however clearly the document said so.
    """
    from .document_text import extract_text

    extraction = extract_text(item["file_path"], max_chars=8_000, ocr=False)
    if not extraction.ok:
        return "unknown", 0.0, f"no text to classify: {extraction.error or 'empty'}"

    category_list = "\n".join(f"- {c}" for c in sorted(DOCUMENT_TYPES - {"unknown"}))

    prompt = f"""Classify this document into exactly ONE category.

CATEGORIES:
{category_list}

FILENAME (company name removed): {surface}
EXTENSION: {item["extension"]}

CONTENT SAMPLE:
---
{extraction.head(4000)}
---

Respond with JSON only:
{{"document_type": "<category>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}
"""

    try:
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
            temperature=0,
            max_tokens=500,
        )
        response = llm.invoke(prompt)
        raw = response.content if isinstance(response.content, str) else str(response.content)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return "unknown", 0.0, "LLM returned no JSON"

        result = json.loads(match.group())
        doc_type = result.get("document_type", "unknown")
        if doc_type not in DOCUMENT_TYPES:
            return "unknown", 0.0, f"LLM returned unknown type '{doc_type}'"

        return (
            doc_type,
            float(result.get("confidence", 0.5)),
            f"LLM: {result.get('reasoning', 'no reasoning given')}",
        )
    except Exception as e:
        return "unknown", 0.0, f"LLM classification failed: {e}"


# =============================================================================
# Refinement
# =============================================================================

def refine_classification(item: DocumentInventoryItem) -> DocumentInventoryItem:
    """
    Apply cross-signal corrections a single stage cannot see.

    Kept as a public function because the analyzer imported it.
    """
    filename = _normalize(item["filename"])

    # An executed instrument stays its own kind — but note the execution, since
    # signed-versus-form is the distinction that matters when reconciling terms.
    if re.search(r"\b(?:executed|signed|fully[\s_-]?executed)\b", filename):
        item["is_executed"] = True
    elif re.search(r"\bform of\b|\btemplate\b|\bdraft\b", filename):
        item["is_executed"] = False
    else:
        item["is_executed"] = None

    # A spreadsheet whose name says pro forma is a cap table, wherever it sits.
    if item["document_type"] == "financial_statements":
        if re.search(r"pro[\s_-]?forma|cap\b|capitaliz", filename):
            item["document_type"] = "cap_table"
            item["classification_reasoning"] += " → refined to cap_table (pro forma/cap in name)"

    return item


# =============================================================================
# Summary
# =============================================================================

def get_classification_summary(inventory: List[DocumentInventoryItem]) -> dict:
    """Counts by type, source, and confidence band."""
    summary = {
        "total": len(inventory),
        "by_type": {},
        "by_source": {},
        "by_confidence": {"high": 0, "medium": 0, "low": 0},
        "unknown_count": 0,
        "executed_count": 0,
    }

    for item in inventory:
        doc_type = item["document_type"]
        summary["by_type"][doc_type] = summary["by_type"].get(doc_type, 0) + 1

        source = item["classification_source"]
        summary["by_source"][source] = summary["by_source"].get(source, 0) + 1

        conf = item["classification_confidence"]
        if conf >= 0.8:
            summary["by_confidence"]["high"] += 1
        elif conf >= 0.5:
            summary["by_confidence"]["medium"] += 1
        else:
            summary["by_confidence"]["low"] += 1

        if doc_type == "unknown":
            summary["unknown_count"] += 1
        if item.get("is_executed"):
            summary["executed_count"] += 1

    return summary

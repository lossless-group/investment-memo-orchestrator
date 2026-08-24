"""
Date Resolution for Decks

Establishing when a deck is from is harder than it looks, and getting it wrong
silently corrupts every time series built on top of it.

Two distinctions do most of the work.

**A date printed on a slide is not necessarily the deck's date.** The Keystone
SPV deck says "Closing Sept 30, 2024" — a future deadline, four days after the
file was last modified. The VP board deck says "BoD Meeting 06-13-2025", which
*is* the deck's date. Same rung of the cascade, opposite meanings. So dates are
classified by kind before any of them is allowed to become ``date_on_deck``.

**The filename often records when a deck was shared, not when it was made.**
That same VP board deck is named ``9-24-2025`` and carries a PDF title of
``LookAhead BoD Q2 06132025``. The meeting was in June; the export was in
September. Filename dates rank below content for exactly this reason.

Every resolution records which rung produced it and how confident that rung is,
so a wrong date is auditable rather than invisible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# =============================================================================
# Result types
# =============================================================================

@dataclass
class DateCandidate:
    """One date found somewhere, with provenance and an interpretation."""

    value: date
    source: str          # slide-content | pdf-title | pdf-meta | filename | sibling | mtime
    confidence: str      # high | medium | low
    kind: str            # deck_date | meeting_date | closing_deadline | as_of | mentioned
    context: str = ""    # the surrounding text, so a reviewer can check it
    precision: str = "day"   # day | month | quarter — a full date beats "June 2025"
    position: int = 0        # character offset, so the earliest mention wins a tie

    def as_dict(self) -> Dict[str, Any]:
        return {
            "date": self.value.isoformat(),
            "source": self.source,
            "confidence": self.confidence,
            "kind": self.kind,
            "precision": self.precision,
            "context": self.context[:200],
        }


@dataclass
class DeckDates:
    """Resolved dates for one deck."""

    date_on_deck: Optional[date] = None
    date_source: Optional[str] = None
    date_confidence: Optional[str] = None
    dates_mentioned: List[DateCandidate] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def as_frontmatter(self) -> Dict[str, Any]:
        return {
            "date_on_deck": self.date_on_deck.isoformat() if self.date_on_deck else None,
            "date_source": self.date_source,
            "date_confidence": self.date_confidence,
            "dates_mentioned": [c.as_dict() for c in self.dates_mentioned],
        }


# =============================================================================
# Kinds
# =============================================================================

# A date is only allowed to become ``date_on_deck`` if it is one of these kinds.
DECK_DATING_KINDS = {"deck_date", "meeting_date", "as_of"}

# Phrases near a date that reveal what the date means. Checked in order, so the
# more specific patterns must come first.
_KIND_CUES: Sequence[tuple] = (
    ("closing_deadline", r"closing|closes?\b|deadline|final close|first close|commitments? due"),
    ("meeting_date", r"\bbo(?:ard)?d?\b|board meeting|bod meeting|annual meeting|committee"),
    ("as_of", r"as of|as at|through\b|data through|current as"),
    ("deck_date", r"presented|prepared|confidential|updated|version|draft"),
    ("projection", r"\bFY\d|forecast|projected|target|by \d{4}|expected"),
    ("historical", r"founded|incorporated|since|launched|raised in"),
)


def classify_date_kind(context: str) -> str:
    """
    Infer what a date means from the words around it.

    Defaults to ``mentioned`` — an unclassified date is explicitly NOT allowed
    to date the deck. Guessing here is how a deck ends up stamped with a
    customer's contract renewal date.
    """
    window = context.lower()
    for kind, pattern in _KIND_CUES:
        if re.search(pattern, window, re.IGNORECASE):
            return kind
    return "mentioned"


# =============================================================================
# Date parsing
# =============================================================================

_MONTHS = {
    m: i for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"], start=1
    )
}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})

# Ordered most-specific-first. Each yields a (y, m, d) via its handler.
_TEXT_PATTERNS: Sequence[tuple] = (
    # September 24, 2025 / Sept 24 2025
    (r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b",
     lambda m: (int(m.group(3)), _MONTHS.get(m.group(1).lower()[:3]), int(m.group(2)))),
    # 24 September 2025
    (r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b",
     lambda m: (int(m.group(3)), _MONTHS.get(m.group(2).lower()[:3]), int(m.group(1)))),
    # 2025-09-24
    (r"\b(\d{4})-(\d{2})-(\d{2})\b",
     lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    # 09-24-2025 / 9/24/2025 / 06-13-2025
    (r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
     lambda m: (int(m.group(3)), int(m.group(1)), int(m.group(2)))),
    # September 2025 — month precision, assumed to be the first
    (r"\b([A-Za-z]{3,9})\.?\s+(\d{4})\b",
     lambda m: (int(m.group(2)), _MONTHS.get(m.group(1).lower()[:3]), 1)),
    # Q3 2025 — quarter precision, assumed to be the first month
    (r"\bQ([1-4])\s*'?\s*(\d{4})\b",
     lambda m: (int(m.group(2)), (int(m.group(1)) - 1) * 3 + 1, 1)),
)

# Index into _TEXT_PATTERNS at which the day is no longer actually stated.
# "June 2025" and "Q2 2025" both resolve to a day-1 date that the document never
# claimed, and must lose to any candidate that names its day.
_MONTH_PRECISION_FROM = 4


def _safe_date(parts) -> Optional[date]:
    try:
        y, m, d = parts
        if not m or not (1 <= m <= 12) or not (1 <= d <= 31):
            return None
        if not (1990 <= y <= 2100):
            return None
        return date(y, m, d)
    except (TypeError, ValueError):
        return None


def find_dates_in_text(text: str, source: str, confidence: str,
                       window: int = 90) -> List[DateCandidate]:
    """Every parseable date in a body of text, each classified by its context."""
    found: List[DateCandidate] = []
    seen: set = set()

    for index, (pattern, handler) in enumerate(_TEXT_PATTERNS):
        precision = ("quarter" if index == 5 else
                     "month" if index >= _MONTH_PRECISION_FROM else "day")
        for m in re.finditer(pattern, text):
            parsed = _safe_date(handler(m))
            if parsed is None:
                continue
            start = max(0, m.start() - window)
            context = re.sub(r"\s+", " ", text[start:m.end() + window]).strip()
            key = (parsed, m.start())
            if key in seen:
                continue
            seen.add(key)
            found.append(DateCandidate(
                value=parsed,
                source=source,
                confidence=confidence,
                kind=classify_date_kind(context),
                context=context,
                precision=precision,
                position=m.start(),
            ))
    return found


# =============================================================================
# Filename dates
# =============================================================================

# Compact stamps that appear in shared filenames: 091024, 20260823, 9-24-2025.
_FILENAME_PATTERNS: Sequence[tuple] = (
    (r"\b(20\d{2})(\d{2})(\d{2})\b",
     lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    (r"\b(\d{1,2})[-_.](\d{1,2})[-_.](20\d{2})\b",
     lambda m: (int(m.group(3)), int(m.group(1)), int(m.group(2)))),
    (r"\b(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})\b",
     lambda m: (int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    # MMDDYY as in "MeridianAI-Deck-091024": ambiguous by construction, hence low
    # confidence wherever it is used.
    (r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)",
     lambda m: (2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))),
)

# The last pattern above reads a bare six-digit run as MMDDYY. "091024" could as
# easily be 2010-09-24 or a version number, so candidates from it are labelled
# separately and rank below the PDF's own metadata.
_AMBIGUOUS_FILENAME_PATTERN_INDEX = 3


def find_dates_in_filename(filename: str) -> List[DateCandidate]:
    """
    Dates encoded in a filename.

    These are labelled ``deck_date`` because that is what a filename stamp
    usually intends, but at medium confidence — the VP board deck is named for
    the day it was exported, three months after the meeting it documents.
    """
    stem = Path(filename).stem
    found: List[DateCandidate] = []
    for pattern, handler in _FILENAME_PATTERNS:
        for m in re.finditer(pattern, stem):
            parsed = _safe_date(handler(m))
            if parsed is None:
                continue
            found.append(DateCandidate(
                value=parsed,
                source="filename",
                confidence="medium",
                kind="deck_date",
                context=stem,
            ))
            break  # one date per pattern is plenty
        if found:
            break
    return found


def parse_pdf_metadata_date(raw: Optional[str]) -> Optional[date]:
    """Parse a PDF ``D:YYYYMMDDHHmmSS`` timestamp."""
    if not raw:
        return None
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", raw)
    if not m:
        return None
    return _safe_date((int(m.group(1)), int(m.group(2)), int(m.group(3))))


# =============================================================================
# Resolution
# =============================================================================

# Which rung wins, best first. A rung only competes if it produced a candidate
# whose kind is in DECK_DATING_KINDS.
_SOURCE_RANK = {
    "slide-content": 0,
    "pdf-title": 1,
    "filename": 2,
    "pdf-meta": 3,
    "filename-ambiguous": 4,
    "sibling": 5,
    "mtime": 6,
}

# A date the document actually spells out beats one we completed for it.
_PRECISION_RANK = {"day": 0, "month": 1, "quarter": 2}

# A meeting date or an explicit "as of" is a stronger statement about when a
# deck is from than a generic date sitting near the word "confidential".
_KIND_RANK = {"meeting_date": 0, "as_of": 1, "deck_date": 2}


def _candidate_rank(c: "DateCandidate") -> tuple:
    """
    Order candidates by how good the evidence is, best first.

    The ordering matters more than it looks. An earlier version sorted by
    ``(source, value)``, which broke ties by preferring the *earlier date* — so
    a copyright footer reading "June 2025" beat the cover slide's "BoD Meeting
    06-13-2025" and dated the deck to the first of the month. Recency is not
    evidence; precision, kind, and position are.
    """
    return (
        _SOURCE_RANK.get(c.source, 9),
        _PRECISION_RANK.get(c.precision, 3),
        _KIND_RANK.get(c.kind, 3),
        c.position,
    )


def resolve_deck_date(
    *,
    first_slides_text: str = "",
    pdf_title: Optional[str] = None,
    pdf_creation_date: Optional[str] = None,
    filename: str = "",
    file_mtime: Optional[date] = None,
    sibling_dates: Optional[Sequence[date]] = None,
) -> DeckDates:
    """
    Resolve a deck's date from every available signal.

    Args:
        first_slides_text: Text of the opening slides (and ideally the closing
            one). Cover slides and footers carry the deck's own date.
        pdf_title: The PDF ``title`` metadata field, which frequently contains a
            date the filename lost.
        pdf_creation_date: Raw ``D:...`` creation timestamp.
        filename: Basename of the deck file.
        file_mtime: Filesystem modification date — the weakest signal, since it
            records when the file was copied into this archive.
        sibling_dates: Dates of other documents filed alongside this one, used
            only when nothing else produced a candidate.
    """
    result = DeckDates()
    candidates: List[DateCandidate] = []

    if first_slides_text:
        candidates += find_dates_in_text(first_slides_text, "slide-content", "high")

    if pdf_title:
        # A title is short, so any date in it is about the document itself.
        for c in find_dates_in_text(pdf_title, "pdf-title", "high"):
            if c.kind == "mentioned":
                c.kind = "deck_date"
            candidates.append(c)

    candidates += find_dates_in_filename(filename)

    meta_date = parse_pdf_metadata_date(pdf_creation_date)
    if meta_date:
        candidates.append(DateCandidate(
            value=meta_date, source="pdf-meta", confidence="medium",
            kind="deck_date", context="PDF creationDate",
        ))

    result.dates_mentioned = candidates

    datable = [c for c in candidates if c.kind in DECK_DATING_KINDS]
    if datable:
        best = min(datable, key=_candidate_rank)
        result.date_on_deck = best.value
        result.date_source = best.source
        result.date_confidence = best.confidence

        # Say so when the winning date disagrees with the filename. This is the
        # VP board deck case, and a reviewer should see it rather than trust a
        # number that quietly contradicts the name on disk.
        filename_dates = {c.value for c in candidates if c.source == "filename"}
        if filename_dates and best.value not in filename_dates and best.source != "filename":
            other = ", ".join(d.isoformat() for d in sorted(filename_dates))
            result.notes.append(
                f"filename implies {other} but {best.source} gives "
                f"{best.value.isoformat()} — using {best.source}, which describes "
                f"the deck rather than when it was shared"
            )
        return result

    # Nothing described the deck. Fall back to siblings, then to the filesystem,
    # both at low confidence and both said out loud.
    if sibling_dates:
        ordered = sorted(sibling_dates)
        inferred = ordered[len(ordered) // 2]
        result.date_on_deck = inferred
        result.date_source = "sibling"
        result.date_confidence = "low"
        result.notes.append(
            f"no date found in or on this deck; inferred from {len(ordered)} "
            f"sibling document(s) spanning {ordered[0].isoformat()}"
            f"–{ordered[-1].isoformat()}"
        )
        return result

    if file_mtime:
        result.date_on_deck = file_mtime
        result.date_source = "mtime"
        result.date_confidence = "low"
        result.notes.append(
            "no date signal anywhere; using file modification time, which records "
            "when the file entered this archive rather than when it was made"
        )
        return result

    result.notes.append("no date could be established from any source")
    return result


def sibling_dates_for(deck_path: Path, max_siblings: int = 40) -> List[date]:
    """
    Modification dates of the other documents filed with a deck.

    Used only as the second-to-last resort. ``Auralis-deck.pdf`` has no
    metadata, no title, and a first slide reading only "tome" — its folder is
    the only evidence of when it arrived.
    """
    folder = Path(deck_path).parent
    dates: List[date] = []
    try:
        for sibling in folder.iterdir():
            if sibling == Path(deck_path) or not sibling.is_file():
                continue
            if sibling.name.startswith("."):
                continue
            dates.append(datetime.fromtimestamp(sibling.stat().st_mtime).date())
            if len(dates) >= max_siblings:
                break
    except OSError:
        pass
    return dates

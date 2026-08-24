"""
Slide Stenographer

Per-slide transcription of decks into markdown, one document per slide.

Additive to `src/agents/deck_analyst.py`, which is untouched: that agent reads a
deck at deck level and emits the memo-shaped JSON the MemoPop workflow depends
on. This package reads the same decks at slide level and emits a faithful record
— verbatim text, layout structure, typed content — for corpus search, deck
rebuilding, and citable memo input.
"""

from .slide_schemas import (
    SLIDE_TYPES,
    LAYOUT_PATTERNS,
    CONTENT_SCHEMAS,
    schema_for,
    is_valid_slide_type,
    validate_slide_record,
)
from .visual_collector import (
    collect_deck_visuals,
    collect_charts,
    collect_imagery,
    detect_visuals,
)
from .date_resolution import (
    DeckDates,
    DateCandidate,
    resolve_deck_date,
    sibling_dates_for,
)

__all__ = [
    "SLIDE_TYPES", "LAYOUT_PATTERNS", "CONTENT_SCHEMAS",
    "schema_for", "is_valid_slide_type", "validate_slide_record",
    "DeckDates", "DateCandidate", "resolve_deck_date", "sibling_dates_for",
    "collect_deck_visuals", "collect_charts", "collect_imagery", "detect_visuals",
]

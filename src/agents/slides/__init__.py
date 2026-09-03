"""
Slide Stenographer

Per-slide transcription of decks into markdown, one document per slide.

Additive to `src/agents/deck_analyst.py`, which is untouched: that agent reads a
deck at deck level and emits the memo-shaped JSON the MemoPop workflow depends
on. This package reads the same decks at slide level and emits a faithful record
— verbatim text, layout structure, typed content — for corpus search, deck
rebuilding, and citable memo input.
"""

# Load .env at the package boundary.
#
# Every agent in here reads ANTHROPIC_API_KEY at call time. The pipeline's own
# entry points load .env before importing anything, but these agents are also
# invoked directly -- from a notebook, a one-off script, or another agent -- and
# in that path the key was simply absent. The symptom was not an error at
# startup: extraction proceeded, every model call failed on authentication, and
# each extractor caught its own exception and reported "no data extracted". A
# whole cap-table pass looked like a dataroom with no cap table in it.
#
# Doing this once here rather than in each of seven call sites means a new
# extractor cannot reintroduce it by forgetting.
from dotenv import load_dotenv as _load_dotenv

_load_dotenv()


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

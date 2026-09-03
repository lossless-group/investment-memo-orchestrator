"""
What a run reaches for first, and who answers when it reaches outward.

Two settings, both read from the environment, both with defaults chosen so an
existing run behaves exactly as it did before either existed.

``MEMOPOP_SOURCE_PRIORITY``   local-first (default) | web-first
``MEMOPOP_RESEARCH_PROVIDER`` perplexity (default) | claude-code | auto

**Why local-first is the default.** The dataroom is the company's own documents:
signed instruments, its cap table, its financials, its competitive work. Web
research is what the internet believes about the company, which for a seed-stage
private company is usually thin, sometimes wrong, and never authoritative about
terms. Reaching for the web while a company's own answer sits unread is the
failure this module exists to prevent — it produced a memo that reported
"valuation terms are not publicly available" beside seven executed SAFEs.

Local-first does **not** mean web-never. It means: establish what the documents
say, then send the web after what is genuinely missing.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

SOURCE_PRIORITIES = ("local-first", "web-first")
RESEARCH_PROVIDERS = ("perplexity", "claude-code", "auto")


def source_priority() -> str:
    """``local-first`` unless told otherwise."""
    value = (os.getenv("MEMOPOP_SOURCE_PRIORITY") or "local-first").strip().lower()
    return value if value in SOURCE_PRIORITIES else "local-first"


def research_provider() -> str:
    """
    Who answers a research question.

    ``perplexity`` — Sonar, live web with citations. The default, and the only
        one that returns real source URLs today.
    ``claude-code`` — the local CLI. No metered research spend, and it can read
        the dataroom directly, but it is not a citation engine.
    ``auto`` — Perplexity when ``PERPLEXITY_API_KEY`` is set, otherwise the CLI.

    Perplexity is never removed by this switch; it is selected away from.
    """
    value = (os.getenv("MEMOPOP_RESEARCH_PROVIDER") or "perplexity").strip().lower()
    if value not in RESEARCH_PROVIDERS:
        return "perplexity"
    if value == "auto":
        return "perplexity" if os.getenv("PERPLEXITY_API_KEY") else "claude-code"
    return value


# =============================================================================
# What we already hold
# =============================================================================

# Which local material answers which kind of section. Keys are matched against
# the section's name and filename, lowercased.
_COVERAGE: Dict[str, tuple] = {
    "funding": ("legal_docs", "cap_table"),
    "terms": ("legal_docs", "cap_table"),
    "capital": ("legal_docs", "cap_table"),
    "organization": ("team",),
    "team": ("team",),
    "people": ("team",),
    "founder": ("team",),
    "origins": ("team",),
    "traction": ("traction", "financials"),
    "opportunity": ("traction", "financials", "competitive"),
    "offering": ("traction", "competitive"),
    "opening": ("competitive", "traction"),
    "competitive": ("competitive",),
    "landscape": ("competitive",),
    "market": ("competitive",),
    "positioning": ("competitive",),
}


def local_coverage(section_def, dataroom_analysis, deck_analysis=None) -> List[str]:
    """
    Name the local material that speaks to this section.

    Returns the field names actually populated — ``[]`` when nothing local
    applies, which is the normal case for a pipeline deal with no dataroom.
    Callers treat an empty list as "the web is all we have."
    """
    try:
        found: List[str] = []
        room = dataroom_analysis if isinstance(dataroom_analysis, dict) else {}

        name = " ".join(str(getattr(section_def, attr, "") or "")
                        for attr in ("name", "filename")).lower()

        wanted: set = set()
        for word, fields in _COVERAGE.items():
            if word in name:
                wanted.update(fields)

        for field in sorted(wanted):
            value = room.get(field)
            if value not in (None, [], {}, ""):
                found.append(field)

        if deck_analysis and isinstance(deck_analysis, dict):
            found.append("deck_analysis")

        return found
    except Exception:
        return []


def web_research_is_warranted(section_def, dataroom_analysis, deck_analysis=None) -> bool:
    """
    Whether to send this section to the web.

    Under ``web-first`` this is always true — the prior behaviour, unchanged.

    Under ``local-first`` the web is still called for every section, because the
    memo legitimately needs outside context a dataroom cannot hold: market size,
    regulatory posture, what competitors have raised. What changes is that local
    material is put in front of the writer first and outranks whatever comes
    back. This function exists as the seam where a future run could skip the
    call entirely for a fully-covered section; it does not skip one today,
    because silently not researching is a worse failure than researching twice.
    """
    return True


def describe() -> str:
    """One line for a run header, so a reader knows how the run was configured."""
    return (f"sources: {source_priority()} · research: {research_provider()}")

"""
Curation modules.

  - best_sources : cross-version curation (merges every version's
                   3-source-catalog/ into one best-of file).
  - sources_md   : per-deal codified-source loader from
                   `deals/<deal>/inputs/Sources.md`.
  - fetch        : URL → clean markdown via Jina Reader (with httpx fallback).
"""

from .best_sources import CurationResult, canonical_url, curate_best_sources
from .sources_md import (
    SourceEntry,
    SourcesMd,
    approved_urls,
    deal_is_codified,
    is_approved_entry,
    is_explicitly_approved,
    is_approved_url,
    is_codified,
    load_deal_sources,
    load_sources_md,
    sources_for_section,
)
from .fetch import fetch_url_markdown

__all__ = [
    "CurationResult",
    "canonical_url",
    "curate_best_sources",
    "SourceEntry",
    "SourcesMd",
    "approved_urls",
    "deal_is_codified",
    "is_approved_entry",
    "is_approved_url",
    "is_codified",
    "load_deal_sources",
    "load_sources_md",
    "sources_for_section",
    "fetch_url_markdown",
]

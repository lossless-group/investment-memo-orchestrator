"""
URL-drift recovery for citations whose original URL has gone dead or
fabricated.

When `remove_invalid_sources_agent` classifies a citation as invalid
(hard-404, soft-404 body, paywall stub, or hallucination-pattern match),
this module tries to find a working URL for the same underlying source by:

  1. Building a search query — `"<claimed title>" site:<publisher-domain>`
     when the publisher resolves to a known domain (via
     `gated_publishers.yaml` or the original URL's host), otherwise
     `"<title>" "<author>"` or title-only.
  2. Searching via Tavily.
  3. For each top candidate, validating the URL through the same pipeline
     used for the original (so a candidate that's itself a soft-404 or
     paywall stub gets rejected, not promoted).
  4. Fuzzy-matching the candidate's page title against the claimed title
     using token-set Jaccard. First candidate clearing the threshold
     wins.

The canonical use case: a real McKinsey report whose URL has drifted
because McKinsey re-organized their site. The citation's title is rich
enough that the recovery search reliably finds the new URL.

Phase 1 step 5 of the Trustworthy-Citations rollout
(context-v/plans/Trustworthy-Citations-Source-Harvester-Rollout.md).
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# Resolved at import time so tests can override.
_DEFAULT_ALLOW_LIST_PATH = Path(__file__).resolve().parent / "gated_publishers.yaml"


@dataclass
class CitationMetadata:
    """Subset of citation metadata used by recovery."""
    title: str
    publisher: str = ""
    author: str = ""
    published_date: str = ""
    original_url: str = ""


@dataclass
class RecoveryResult:
    """Successful recovery of a drifted URL."""
    recovered_url: str
    matched_title: str
    claimed_title: str
    jaccard: float
    via_query: str
    via_provider: str


def _load_publisher_allow_list(path: Path) -> List[Dict]:
    """Load the gated_publishers.yaml entries. Returns [] if missing or malformed."""
    if not path.exists():
        return []
    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return data.get("publishers", [])
    except Exception:
        return []


def _derive_publisher_domain(
    publisher_name: str,
    original_url: str,
    allow_list: List[Dict],
) -> Optional[str]:
    """
    Resolve a `site:<domain>` to use in the recovery query.

    Strategy:
      1. If `publisher_name` fuzzy-matches an allow-list entry's name,
         use that entry's first domain.
      2. Else if the original URL's host matches an allow-list entry, use
         that host.
      3. Else if the original URL is parseable, use its naked host as a
         best-effort.
      4. Else return None — recovery will fall back to title-only or
         title+author search.
    """
    if publisher_name:
        name_lower = publisher_name.lower().strip()
        for entry in allow_list:
            entry_name = (entry.get("name") or "").lower()
            # Direct match, substring, or vice versa
            if (name_lower == entry_name
                    or name_lower in entry_name
                    or entry_name in name_lower):
                domains = entry.get("domains") or []
                if domains:
                    return domains[0]

    if original_url:
        m = re.match(r'https?://(?:www\.)?([^/]+)', original_url)
        if m:
            host = m.group(1).lower()
            for entry in allow_list:
                if host in (entry.get("domains") or []):
                    return host
            return host

    return None


def _title_jaccard(a: str, b: str) -> float:
    """
    Token-set Jaccard similarity, lowercased, punctuation stripped.

    Returns 0.0 if either string is empty.
    """
    if not a or not b:
        return 0.0

    def tokens(s: str) -> set:
        s = re.sub(r'[^\w\s]', ' ', s.lower())
        # Drop stopwords-ish noise so "The Promise and challenge of the age of AI"
        # matches "Promise and challenge of the age of AI". Conservative list.
        stop = {'the', 'a', 'an', 'of', 'and', 'or', 'to', 'in', 'on', 'for'}
        return {t for t in s.split() if t and t not in stop}

    a_tokens = tokens(a)
    b_tokens = tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def attempt_url_recovery(
    metadata: CitationMetadata,
    *,
    max_candidates: int = 5,
    jaccard_threshold: float = 0.6,
    publisher_allow_list_path: Optional[Path] = None,
) -> Optional[RecoveryResult]:
    """
    Try to recover a working URL for a citation whose original URL failed.

    Args:
        metadata: Citation metadata; `title` is required, `publisher`/
            `author`/`original_url` improve query targeting.
        max_candidates: How many search results to evaluate.
        jaccard_threshold: Minimum title fuzzy-match score (0.0–1.0). 0.6
            is permissive enough to match re-titled articles while rejecting
            unrelated results.
        publisher_allow_list_path: Override the default
            `gated_publishers.yaml` location (for tests).

    Returns:
        `RecoveryResult` if a candidate clears the threshold, else None.

    No-ops gracefully:
      - Returns None if `metadata.title` is empty.
      - Returns None if `TAVILY_API_KEY` is unset.
      - Returns None if the `tavily` package isn't installed.
      - Returns None on any search-provider error.
    """
    if not metadata.title:
        return None

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None

    try:
        from tavily import TavilyClient
    except ImportError:
        return None

    allow_list_path = publisher_allow_list_path or _DEFAULT_ALLOW_LIST_PATH
    allow_list = _load_publisher_allow_list(allow_list_path)

    # Build the most targeted query we can.
    domain = _derive_publisher_domain(
        metadata.publisher,
        metadata.original_url,
        allow_list,
    )
    if domain:
        query = f'"{metadata.title}" site:{domain}'
    elif metadata.author:
        query = f'"{metadata.title}" "{metadata.author}"'
    else:
        query = f'"{metadata.title}"'

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=max_candidates,
            include_raw_content=False,
        )
    except Exception:
        return None

    candidates = (response or {}).get("results", [])
    if not candidates:
        return None

    # Lazy import to avoid circular dependency with remove_invalid_sources.
    from ..agents.remove_invalid_sources import (
        validate_url,
        CONTENT_INVALID_CODES,
        VERIFIED_GATED,
    )

    for candidate in candidates[:max_candidates]:
        candidate_url = candidate.get("url") or ""
        candidate_title = candidate.get("title") or ""

        if not candidate_url:
            continue
        if candidate_url == metadata.original_url:
            continue  # Same dead URL came back; skip

        # Validate via the same pipeline that classified the original.
        # Acceptable verdicts: real 2xx OR VERIFIED_GATED (paywalled-but-
        # reputable). Without the gated branch, recovering an FT/WSJ/
        # Bloomberg URL would be impossible because the candidate's own
        # paywall body would re-classify as PAYWALL_STUB and get rejected.
        _, code, _ = validate_url(candidate_url)
        if code in CONTENT_INVALID_CODES:
            continue
        if not (200 <= code < 300 or code == VERIFIED_GATED):
            continue

        # Fuzzy-match titles.
        jaccard = _title_jaccard(metadata.title, candidate_title)
        if jaccard >= jaccard_threshold:
            return RecoveryResult(
                recovered_url=candidate_url,
                matched_title=candidate_title,
                claimed_title=metadata.title,
                jaccard=jaccard,
                via_query=query,
                via_provider="tavily",
            )

    return None

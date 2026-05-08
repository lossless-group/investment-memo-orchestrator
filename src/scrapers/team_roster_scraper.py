"""Team roster scraper.

Implements the `Scraper` Protocol from
context-v/plans/Team-and-People-Metadata-Ingestion.md (Phase 2).

`FirecrawlScraper` is the default implementation. The Protocol exists so a
Crawl4AI-backed alternative can be swapped in later without touching the CLI.

Discovery strategy is link-graph-driven, not path-guessing:
1. firecrawl.map(root, search="team")  — ranked by relevance
2. firecrawl.scrape(root, formats=["links"]) — read the nav/footer ourselves
3. Probe canonical paths (/team, /about, /leadership, /people) — last resort
"""

from __future__ import annotations

import re
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from firecrawl import Firecrawl


# Path-segment keywords that signal a team-style page, scored by how
# strongly the segment names a team page. We match on full path *segments*,
# not substrings — so "/more-about/weak-pointers" does NOT count as "/about".
_HIGH_PRIORITY_SEGMENTS = {
    "team", "teams", "our-team", "the-team",
    "people", "our-people",
    "leadership", "founders", "who-we-are",
}
_MED_PRIORITY_SEGMENTS = {
    "about", "about-us", "company", "management", "staff",
}

_FALLBACK_PATHS = (
    "/team",
    "/about",
    "/about-us",
    "/leadership",
    "/people",
    "/our-team",
    "/who-we-are",
    "/founders",
)

_HTTP_TIMEOUT = 8.0


# Flat JSON schema for Firecrawl extract. We hand-write this instead of using
# Pydantic's model_json_schema() because Firecrawl rejects $defs/$ref. The
# response is still validated against TeamRosterExtraction on our side.
EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "team_page_url": {
            "type": "string",
            "description": "Canonical team/people/leadership page URL these members were extracted from.",
        },
        "members": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full name."},
                    "title": {
                        "type": "string",
                        "description": "Current title at the organization.",
                    },
                    "bio_short": {
                        "type": "string",
                        "description": "One-sentence summary suitable for a card.",
                    },
                    "bio_long": {
                        "type": "string",
                        "description": "Paragraph-length bio if visible on the page.",
                    },
                    "photo": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "Exact image URL referenced in the HTML for this person's headshot. Do not paraphrase or rewrite.",
                            },
                            "source": {
                                "type": "string",
                                "enum": [
                                    "org_site",
                                    "wikipedia",
                                    "crunchbase",
                                    "conference",
                                    "github_avatar",
                                    "linkedin_public",
                                    "other",
                                ],
                                "description": "Where this photo URL was found. Set 'org_site' for any photo on the company's own pages.",
                            },
                        },
                        "required": ["url", "source"],
                    },
                    "socials": {
                        "type": "object",
                        "description": "Professional-only social profiles. NEVER include Facebook or Instagram. Include YouTube/TikTok ONLY if the channel is clearly a branded professional creator presence.",
                        "properties": {
                            "linkedin": {"type": "string"},
                            "x_twitter": {"type": "string"},
                            "bluesky": {"type": "string"},
                            "medium": {"type": "string"},
                            "youtube": {"type": "string"},
                            "tiktok": {"type": "string"},
                            "github": {"type": "string"},
                            "personal_site": {"type": "string"},
                        },
                    },
                },
                "required": ["name", "title"],
            },
        },
    },
    "required": ["members"],
}


class Scraper(Protocol):
    """Pluggable interface for team-page discovery + roster extraction."""

    def discover_team_pages(self, root_url: str) -> list[str]:
        """Return candidate team-page URLs in priority order. Empty list if none."""
        ...

    def extract_roster(self, urls: list[str], schema: dict) -> dict:
        """Return a JSON dict matching `schema` (TeamRosterExtraction shape).

        Caller is responsible for validating with TeamRosterExtraction.model_validate.
        """
        ...


class FirecrawlScraper:
    """Firecrawl-backed Scraper. Wraps `firecrawl-py 4.x`."""

    def __init__(self, api_key: str, *, map_limit: int = 20):
        self._fc = Firecrawl(api_key=api_key)
        self._map_limit = map_limit

    def discover_team_pages(self, root_url: str) -> list[str]:
        """Merge candidates from three independent channels, score, dedupe.

        Channel A: firecrawl.map(search="team") — link-graph relevance.
        Channel B: HEAD-probe canonical paths (/team, /people, /leadership, ...).
        Channel C: the root URL itself, low-priority — many sites put the team
                   on the homepage with no dedicated /team page.

        We always run B and C even when A returns hits, because:
        - sites often have /team that isn't in the static link graph
          (e.g., aixventures.com — /team is 200 but map doesn't surface it)
        - sites often have team on the homepage with no dedicated page
        """
        same_domain = _same_root(root_url)
        urls: list[str] = []

        # --- Channel A: map with search="team" ---
        try:
            result = self._fc.map(
                root_url,
                search="team",
                limit=self._map_limit,
                ignore_query_parameters=True,
            )
            urls.extend(_extract_urls_from_map(result))
        except Exception as e:  # noqa: BLE001 — Firecrawl errors are varied
            print(f"  [discover] map(search='team') failed: {e}")

        # --- Channel B: HEAD-probe canonical paths ---
        urls.extend(_probe_canonical_paths(root_url))

        # Filter to same-root-domain so cross-subdomain noise (e.g.
        # careers.example.com/jobs) doesn't dilute the candidate set.
        urls = [u for u in urls if same_domain(u)]

        # Score and rank — drops URLs that have no team-keyword segment.
        ranked = _dedupe_team_like(urls, top_n=4)

        # --- Channel C: always append root URL as a low-priority candidate ---
        # Many sites put the team on the homepage with no dedicated page.
        if root_url not in ranked:
            ranked.append(root_url)

        return ranked

    def extract_roster(self, urls: list[str], schema: dict | None = None) -> dict:
        if not urls:
            raise ValueError("extract_roster called with empty URL list")

        schema = schema if schema is not None else EXTRACT_SCHEMA

        prompt = (
            "Extract every team member visible on these pages. "
            "For each person, capture name, title, bio (if present), and the "
            "exact image URL referenced in the HTML for their headshot. Do not "
            "paraphrase or rewrite image URLs. "
            "For socials, include only LinkedIn, X/Twitter, Bluesky, Medium, "
            "GitHub, personal websites. NEVER include Facebook or Instagram. "
            "Include YouTube/TikTok ONLY if the channel is clearly a "
            "professional/branded creator presence (not personal/family content). "
            "Set photo.source='org_site' for any photos found on these pages."
        )

        result = self._fc.extract(
            urls=urls,
            prompt=prompt,
            schema=schema,
            ignore_invalid_urls=True,
        )
        return _coerce_extract_payload(result)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _extract_urls_from_map(result: Any) -> list[str]:
    """Pull URL strings out of a Firecrawl MapData. SDK returns object-or-dict."""
    links = getattr(result, "links", None)
    if links is None and isinstance(result, dict):
        links = result.get("links") or result.get("data", {}).get("links")
    if not links:
        return []
    out = []
    for item in links:
        if isinstance(item, str):
            out.append(item)
        else:
            url = getattr(item, "url", None) or (
                item.get("url") if isinstance(item, dict) else None
            )
            if url:
                out.append(url)
    return out


def _extract_urls_from_scrape(doc: Any) -> list[str]:
    """Pull URL strings out of a Firecrawl Document's links payload."""
    links = getattr(doc, "links", None)
    if links is None and isinstance(doc, dict):
        links = doc.get("links") or doc.get("data", {}).get("links")
    if not links:
        return []
    out = []
    for item in links:
        if isinstance(item, str):
            out.append(item)
        else:
            url = getattr(item, "url", None) or (
                item.get("url") if isinstance(item, dict) else None
            )
            if url:
                out.append(url)
    return out


def _score_team_url(url: str) -> tuple[int, int] | None:
    """Score a URL on team-relevance via path-segment matching.

    Returns (priority, -path_depth) where higher is better, or None to reject.
    Priority: 2 = high-priority segment (team/people/leadership/...),
              1 = medium (about/company/...).
    Tiebreak: shorter paths win (so /about beats /company/about).
    """
    try:
        path = urlparse(url).path or ""
    except ValueError:
        return None
    segments = [s for s in path.strip("/").split("/") if s]
    if not segments:
        return None
    for seg in segments:
        if seg.lower() in _HIGH_PRIORITY_SEGMENTS:
            return (2, -len(segments))
    for seg in segments:
        if seg.lower() in _MED_PRIORITY_SEGMENTS:
            return (1, -len(segments))
    return None


def _dedupe_team_like(urls: list[str], *, top_n: int = 5) -> list[str]:
    """Score URLs on team-relevance, dedupe, and return the top N."""
    seen: set[str] = set()
    scored: list[tuple[tuple[int, int], str]] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        score = _score_team_url(url)
        if score is not None:
            scored.append((score, url))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in scored[:top_n]]


def _same_root(root_url: str):
    """Return a predicate that's True when a URL shares the registrable host
    with `root_url`. Treats `www.` as equivalent. Used to drop cross-subdomain
    noise like `careers.example.com/jobs/...`.
    """
    root_host = urlparse(root_url).netloc.removeprefix("www.").lower()

    def _check(url: str) -> bool:
        try:
            host = urlparse(url).netloc.removeprefix("www.").lower()
        except ValueError:
            return False
        return host == root_host

    return _check


def _probe_canonical_paths(root_url: str) -> list[str]:
    """HEAD each canonical path; return any that respond 2xx."""
    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    out: list[str] = []
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        for path in _FALLBACK_PATHS:
            url = base + path
            try:
                r = client.head(url)
                if r.status_code < 400:
                    out.append(str(r.url))
                    continue
                # Some servers reject HEAD; try GET.
                r = client.get(url)
                if r.status_code < 400:
                    out.append(str(r.url))
            except httpx.HTTPError:
                continue
    return out


def _coerce_extract_payload(result: Any) -> dict:
    """Firecrawl extract returns either an object with .data or a raw dict."""
    if isinstance(result, dict):
        return result.get("data", result)
    data = getattr(result, "data", None)
    if data is not None:
        if isinstance(data, dict):
            return data
        # Pydantic-like object
        if hasattr(data, "model_dump"):
            return data.model_dump()
    raise TypeError(f"Unexpected extract response shape: {type(result)!r}")

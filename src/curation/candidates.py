"""LLM-free candidate-source discovery for the frontloaded curation surface.

The governing constraint, from the operator (2026-08-06):

    "What happens now is Perplexity just invents sources, and going
     through them takes forever."

Two failures in one sentence — the candidates are *fabricated*, and there
are *too many* of them. Both follow from putting a language model in the
candidate path.

This module has no language model in it. Every URL it returns came out of
a search index via SearXNG, so it cannot be hallucinated — the property is
structural, not probabilistic. Terms are derived from the deck analysis by
string manipulation, never by generation.

Volume is treated as a first-class requirement, not polish: results are
capped per term and globally, and deduped by canonical URL. A short list
the analyst extends beats a long one they must prune.

Wire format is `ConnectorResult`, copied verbatim from augment-it's
`services/social-search/src/connectors/types.ts` so the two trees don't
fork a third shape:

    {url, title, content, score?, published_date?, known?}

SearXNG must have the JSON format enabled and its limiter disabled — see
`augment-it/services/social-search/searxng/settings.yml`, which is the
working config. Reached via `SEARXNG_URL`; when that is unset or the
instance is unreachable, every function here degrades to a graceful no-op
rather than raising, matching the contract in
`context-v/plans/Sources-Curation-UI-Tool.md`.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence

from .best_sources import canonical_url

# Caps exist to keep the approval list workable. Tune deliberately.
DEFAULT_MAX_PER_TERM = 8
DEFAULT_MAX_TOTAL = 40
DEFAULT_TIMEOUT = 10

# Noise that adds nothing to a search query.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "for", "of", "to", "in", "on", "with",
    "inc", "llc", "ltd", "corp", "co", "company", "platform", "solution",
    "solutions", "technologies", "technology", "labs", "group", "holdings",
})


def searxng_base_url() -> Optional[str]:
    """The configured SearXNG base URL, or None when unset."""
    raw = (os.environ.get("SEARXNG_URL") or "").strip()
    return raw.rstrip("/") or None


def is_available() -> bool:
    """Whether candidate search is configured at all."""
    return searxng_base_url() is not None


def _clean_term(term: str) -> str:
    term = re.sub(r"\s+", " ", (term or "").strip())
    return term


def derive_terms(
    state: Dict[str, Any],
    deck_analysis: Optional[Dict[str, Any]] = None,
    *,
    max_terms: int = 6,
) -> List[str]:
    """Build search terms from the deal + deck analysis. No LLM.

    Pure string manipulation over fields the deck analyst already
    extracted. If a term cannot be derived from real data it is simply
    not emitted — this function never invents a topic to search for.

    Returns terms ordered most- to least-specific, deduped, capped.
    """
    deck = deck_analysis or state.get("deck_analysis") or {}
    company = _clean_term(state.get("company_name") or deck.get("company_name") or "")

    terms: List[str] = []
    if company:
        terms.append(company)
        stage = _clean_term(state.get("stage") or "")
        if stage:
            terms.append(f"{company} {stage} funding")
        terms.append(f"{company} competitors")

    # The market category, taken from the deck's own words — the most
    # useful non-company term, and the one an analyst would type first.
    for field in ("tagline", "problem_statement", "competitive_landscape"):
        raw = _clean_term(str(deck.get(field) or ""))
        if not raw:
            continue
        words = [
            w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", raw.lower())
            if w not in _STOPWORDS and len(w) > 2
        ][:4]
        if len(words) >= 2:
            terms.append(" ".join(words))
            break

    if company:
        terms.append(f"{company} market size")

    seen, out = set(), []
    for t in terms:
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            out.append(t)
    return out[:max_terms]


def _normalize_result(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map one SearXNG result onto the ConnectorResult wire shape."""
    url = (raw.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return None
    return {
        "url": url,
        "title": (raw.get("title") or "").strip(),
        "content": (raw.get("content") or "").strip(),
        "score": raw.get("score"),
        "published_date": raw.get("publishedDate") or raw.get("published_date"),
    }


def search_one(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_PER_TERM,
    timeout: int = DEFAULT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """Run one SearXNG query. Returns [] on any failure — never raises.

    Degrading to an empty list is deliberate: a search outage must not
    take down the curation surface, and it must never be mistaken for
    "no results exist".
    """
    base = searxng_base_url()
    if not base or not (query or "").strip():
        return []

    try:
        import httpx

        resp = httpx.get(
            f"{base}/search",
            params={"q": query, "format": "json"},
            timeout=timeout,
            headers={
                "accept": "application/json",
                # Some SearXNG configs reject requests with no UA as bot traffic.
                "user-agent": "memopop-curation/0.1",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []

    results = []
    for raw in (payload.get("results") or []):
        if not isinstance(raw, dict):
            continue
        norm = _normalize_result(raw)
        if norm:
            results.append(norm)
        if len(results) >= max_results:
            break
    return results


def gather_candidates(
    terms: Sequence[str],
    *,
    max_per_term: int = DEFAULT_MAX_PER_TERM,
    max_total: int = DEFAULT_MAX_TOTAL,
    known_urls: Optional[set] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Search every term and return a capped, deduped candidate list.

    Args:
        terms: Search terms, most-specific first (see `derive_terms`).
        max_per_term: Cap per query.
        max_total: Global cap. The list an analyst must work through is
            the product being designed here; an uncapped one is a defect.
        known_urls: Canonicalized URLs already in the corpus. Matches are
            returned flagged `known` rather than dropped, so the analyst
            can see coverage instead of wondering what was hidden.

    Returns:
        `{"available": bool, "reason": str|None, "terms": [...],
          "candidates": [ConnectorResult, ...], "truncated": bool}`
    """
    if not is_available():
        return {
            "available": False,
            "reason": "SEARXNG_URL is not set — candidate search is disabled",
            "terms": list(terms),
            "candidates": [],
            "truncated": False,
        }

    known = known_urls or set()
    seen: set = set()
    candidates: List[Dict[str, Any]] = []
    truncated = False

    for term in terms:
        for result in search_one(term, max_results=max_per_term, timeout=timeout):
            key = canonical_url(result["url"])
            if key in seen:
                continue
            seen.add(key)
            result["known"] = key in known
            result["found_via"] = term
            candidates.append(result)
            if len(candidates) >= max_total:
                truncated = True
                break
        if truncated:
            break

    return {
        "available": True,
        "reason": None,
        "terms": list(terms),
        "candidates": candidates,
        "truncated": truncated,
    }


def candidates_for_deal(
    state: Dict[str, Any],
    *,
    deck_analysis: Optional[Dict[str, Any]] = None,
    max_per_term: int = DEFAULT_MAX_PER_TERM,
    max_total: int = DEFAULT_MAX_TOTAL,
) -> Dict[str, Any]:
    """Derive terms for a deal and gather candidates in one call.

    Anything already in the deal's `Sources.md` is marked `known` so the
    analyst sees what they have rather than re-approving it.
    """
    from .sources_md import load_deal_sources

    _, approved = load_deal_sources(state)
    terms = derive_terms(state, deck_analysis)
    return gather_candidates(
        terms,
        max_per_term=max_per_term,
        max_total=max_total,
        known_urls=approved,
    )

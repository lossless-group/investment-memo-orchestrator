"""Sidecar endpoints for the frontloaded source-approval surface.

Mounted on the main FastAPI app, so these inherit its CORS allowlist for
Tauri origins — the webview calls them directly, per the transport seam
in `context-v/explorations/Moving-an-Agent-Orchestrator-to-an-API.md`.

These are the four endpoints `tools/curate_sources.py` proved out, moved
rather than reimplemented (they share `src/curation/serialize.py`), plus
two the frontloaded flow adds:

    GET  /firms/{firm}/deals/{deal}/sources     read the curated list
    POST /firms/{firm}/deals/{deal}/sources     write it back (backed up)
    POST /actions/search-sources                LLM-free candidate search
    POST /actions/fetch-source                  Jina preview of one URL
    POST /actions/recover-source                re-search a drifted URL
    POST /actions/approve-sources               approve set → mode: codified

Every route is deal-scoped by `(firm, deal)` and resolves paths through
`io/<firm>/deals/<deal>/`; none accepts an arbitrary filesystem path.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# --------------------------------------------------------------------------- #
# Request models                                                               #
# --------------------------------------------------------------------------- #

class SaveSourcesRequest(BaseModel):
    meta: Dict[str, Any] = {}
    sources: List[Dict[str, Any]] = []
    body: str = ""
    mode: Optional[str] = None


class SearchSourcesRequest(BaseModel):
    firm: Optional[str] = None
    deal: Optional[str] = None
    query: Optional[str] = None
    terms: Optional[List[str]] = None
    max_per_term: int = 8
    max_total: int = 40


class FetchSourceRequest(BaseModel):
    url: str


class RecoverSourceRequest(BaseModel):
    title: str
    url: Optional[str] = None
    publisher: Optional[str] = None
    max_candidates: int = 5


class ApproveSourcesRequest(BaseModel):
    firm: str
    deal: str
    sources: List[Dict[str, Any]]
    meta: Dict[str, Any] = {}
    body: str = ""


# --------------------------------------------------------------------------- #
# Path resolution                                                              #
# --------------------------------------------------------------------------- #

def _deal_inputs_dir(firm: str, deal: str) -> Path:
    """Resolve `io/<firm>/deals/<deal>/inputs`, rejecting traversal.

    `firm` and `deal` arrive from the webview. Anything with a separator
    or a parent reference is rejected outright rather than sanitized —
    these are directory names, and a name that needs sanitizing is a bug
    or an attack, not a name.
    """
    for part, label in ((firm, "firm"), (deal, "deal")):
        if not part or not part.strip():
            raise HTTPException(status_code=400, detail=f"{label} is required")
        if "/" in part or "\\" in part or ".." in part:
            raise HTTPException(status_code=400, detail=f"invalid {label}")

    from ..paths import get_io_root
    return get_io_root() / firm / "deals" / deal / "inputs"


# --------------------------------------------------------------------------- #
# Read / write the curated list                                                #
# --------------------------------------------------------------------------- #

@router.get("/firms/{firm}/deals/{deal}/sources")
async def get_sources(firm: str, deal: str) -> dict:
    """Read a deal's curated source list.

    Returns the aggregated worksheet when no curated `Sources.md` exists
    yet, so the approval surface has something to show on a fresh deal.
    Reads raw frontmatter (not the typed loader) to keep any per-source
    key the analyst added by hand.
    """
    from ..curation.sources_md import parse_frontmatter

    inputs = _deal_inputs_dir(firm, deal)
    path = inputs / "Sources.md"

    origin = "curated"
    if not path.exists():
        aggregated = sorted(inputs.parent.glob("outputs/*/Sources-aggregated.md"))
        if aggregated:
            path, origin = aggregated[-1], "aggregated"

    if not path.exists():
        return {
            "firm": firm, "deal": deal, "exists": False, "origin": None,
            "path": str(inputs / "Sources.md"), "meta": {},
            "sources": [], "body": "",
        }

    meta, body = parse_frontmatter(path.read_text())
    sources = [s for s in (meta.pop("sources", None) or []) if isinstance(s, dict)]
    return {
        "firm": firm, "deal": deal, "exists": True, "origin": origin,
        "path": str(path), "meta": meta, "sources": sources, "body": body,
        "mode": meta.get("mode", "aggregated"),
    }


@router.post("/firms/{firm}/deals/{deal}/sources")
async def save_sources(firm: str, deal: str, request: SaveSourcesRequest) -> dict:
    """Write a deal's `Sources.md`, backing up any existing file."""
    from ..curation.serialize import write_sources_md

    inputs = _deal_inputs_dir(firm, deal)
    written, backup = await asyncio.to_thread(
        write_sources_md,
        inputs / "Sources.md",
        request.meta, request.sources, request.body, request.mode,
    )
    return {
        "ok": True,
        "written": str(written),
        "backup": str(backup) if backup else None,
        "count": len([s for s in request.sources if str(s.get("url", "")).strip()]),
        "mode": request.mode or request.meta.get("mode", "aggregated"),
    }


# --------------------------------------------------------------------------- #
# Candidate discovery — no LLM in this path                                    #
# --------------------------------------------------------------------------- #

@router.post("/actions/search-sources")
async def search_sources(request: SearchSourcesRequest) -> dict:
    """Find candidate sources via SearXNG.

    Either an explicit `query`, or `terms`, or `(firm, deal)` to derive
    terms from the deck analysis. Never consults a language model — every
    URL returned came out of a search index and therefore cannot be
    fabricated. Degrades to `available: false` when SEARXNG_URL is unset.
    """
    from ..curation import candidates as C

    if request.query:
        terms = [request.query]
    elif request.terms:
        terms = request.terms
    elif request.firm and request.deal:
        state = {"company_name": request.deal, "firm": request.firm}
        return await asyncio.to_thread(
            C.candidates_for_deal, state,
            max_per_term=request.max_per_term, max_total=request.max_total,
        )
    else:
        raise HTTPException(
            status_code=400, detail="one of query, terms, or (firm, deal) is required"
        )

    return await asyncio.to_thread(
        C.gather_candidates, terms,
        max_per_term=request.max_per_term, max_total=request.max_total,
    )


@router.post("/actions/fetch-source")
async def fetch_source(request: FetchSourceRequest) -> dict:
    """Fetch one URL as markdown for inline preview (read-only)."""
    from ..curation import fetch_url_markdown

    url = (request.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="url must be http(s)")

    try:
        result = await asyncio.to_thread(fetch_url_markdown, url)
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e)}

    # fetch_url_markdown returns None on total failure, else a dict with
    # {url, title, markdown, via} — see src/curation/fetch.py.
    if not result:
        return {"ok": False, "url": url, "error": "fetch returned no content"}

    text = result.get("markdown") or ""
    return {
        "ok": bool(text),
        "url": result.get("url", url),
        "title": result.get("title"),
        "via": result.get("via"),
        "markdown": text[:20000],
        "truncated": len(text) > 20000,
    }


@router.post("/actions/recover-source")
async def recover_source(request: RecoverSourceRequest) -> dict:
    """Re-search for the real URL behind a drifted or dead citation.

    The third option beside approve/deny: the article is real, the link
    isn't. Wraps `validation.url_recovery.attempt_url_recovery`, which
    already does Tavily search + title fuzzy-matching + a publisher
    allow-list — this endpoint exists to put a button on it.

    Requires a title (recovery is title-driven and no-ops without one)
    and TAVILY_API_KEY; returns `ok: false` with a reason rather than
    raising when either is missing.
    """
    from ..validation.url_recovery import CitationMetadata, attempt_url_recovery

    title = (request.title or "").strip()
    if not title:
        return {"ok": False, "reason": "a title is required to search for the source"}

    import os
    if not os.environ.get("TAVILY_API_KEY"):
        return {"ok": False, "reason": "TAVILY_API_KEY is not set — recovery is disabled"}

    metadata = CitationMetadata(
        title=title,
        publisher=(request.publisher or "").strip() or None,
        original_url=(request.url or "").strip() or None,
    )
    result = await asyncio.to_thread(
        attempt_url_recovery, metadata, max_candidates=request.max_candidates
    )
    if not result:
        return {"ok": False, "reason": "no candidate matched the title closely enough"}

    # RecoveryResult fields, verbatim from validation/url_recovery.py.
    # Surfaced in full rather than summarized: the analyst is being asked
    # to accept a URL swap, so they need to see the matched title and the
    # similarity score that justified it, not just a link.
    return {
        "ok": True,
        "recovered_url": result.recovered_url,
        "matched_title": result.matched_title,
        "claimed_title": result.claimed_title,
        "jaccard": result.jaccard,
        "via_query": result.via_query,
        "via_provider": result.via_provider,
        "original_url": request.url,
    }


# --------------------------------------------------------------------------- #
# The approval gate                                                            #
# --------------------------------------------------------------------------- #

@router.post("/actions/approve-sources")
async def approve_sources(request: ApproveSourcesRequest) -> dict:
    """Commit the approved set and flip the deal into codified mode.

    The single action that ends curation: everything not explicitly
    rejected becomes the corpus the run may cite, and `mode: codified`
    is what makes the membership gate bite downstream.

    Rejected entries are written through (not dropped) so a later session
    can see what was already turned down and why, instead of re-reviewing
    it — the same institutional-memory rationale as the file's prose body.
    """
    from ..curation.serialize import write_sources_md
    from ..curation.sources_md import _REJECTED_VERDICTS

    inputs = _deal_inputs_dir(request.firm, request.deal)

    kept = [s for s in request.sources if str(s.get("url", "")).strip()]
    approved = [
        s for s in kept
        if str(s.get("verdict", "")).strip().lower() not in _REJECTED_VERDICTS
    ]
    if not approved:
        raise HTTPException(
            status_code=400,
            detail="cannot approve an empty set — every source is rejected",
        )

    meta = dict(request.meta)
    meta.setdefault("deal", request.deal)
    meta.setdefault("firm", request.firm)

    written, backup = await asyncio.to_thread(
        write_sources_md,
        inputs / "Sources.md",
        meta, kept, request.body, "codified",
    )
    return {
        "ok": True,
        "written": str(written),
        "backup": str(backup) if backup else None,
        "mode": "codified",
        "approved_count": len(approved),
        "rejected_count": len(kept) - len(approved),
    }

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
from datetime import datetime, timezone
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
    # Autosaves fire every few seconds while the analyst works. Backing up
    # on each one would bury the deal directory in `.bak-` files, so an
    # autosave takes a backup only the FIRST time it touches a given deal
    # this process — enough to recover the pre-session state, which is the
    # only version anyone would actually want to roll back to. A manual
    # save is a deliberate checkpoint and always backs up.
    autosave: bool = False


# (firm, deal) pairs already backed up by an autosave this process.
_AUTOSAVE_BACKED_UP: set = set()


class SearchSourcesRequest(BaseModel):
    firm: Optional[str] = None
    deal: Optional[str] = None
    query: Optional[str] = None
    terms: Optional[List[str]] = None
    max_per_term: int = 8
    max_total: int = 40


class FetchSourceRequest(BaseModel):
    url: str
    # When the deal is known, the fetched content is persisted to a
    # per-source file instead of being rendered once and discarded. The
    # analyst already paid for this fetch; throwing it away was the gap.
    firm: Optional[str] = None
    deal: Optional[str] = None
    title: Optional[str] = None
    publisher: Optional[str] = None
    # The cheap tier: metadata + excerpt, no body stored. What a paste
    # needs so the row can name itself, without paying to keep content
    # for a source that may be rejected. Per source-with-extracts-md's
    # two-tier rule; `full` is what a Preview or a promote asks for.
    metadata_only: bool = False


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

    key = (firm, deal)
    if request.autosave and key in _AUTOSAVE_BACKED_UP:
        should_backup = False
    else:
        should_backup = True
        if request.autosave:
            _AUTOSAVE_BACKED_UP.add(key)

    written, backup = await asyncio.to_thread(
        write_sources_md,
        inputs / "Sources.md",
        request.meta, request.sources, request.body, request.mode,
        backup=should_backup,
    )
    return {
        "ok": True,
        "written": str(written),
        "backup": str(backup) if backup else None,
        "count": len([s for s in request.sources if str(s.get("url", "")).strip()]),
        "mode": request.mode or request.meta.get("mode", "aggregated"),
        "autosave": request.autosave,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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

    # Persist what we just fetched. Previously this content was rendered
    # into the UI and dropped on the next navigation — the analyst paid a
    # network round-trip per source and kept nothing.
    saved_to = None
    if text and request.firm and request.deal:
        try:
            from ..curation.source_file import (
                SourceFile, apply_fetch, read_source_file, resolve_path, write_source_file,
            )

            inputs = _deal_inputs_dir(request.firm, request.deal)
            sf = SourceFile(
                url=url,
                title=(request.title or "").strip(),
                publisher=(request.publisher or "").strip(),
            )
            # Preserve a decision already recorded for this source — a
            # preview must never silently downgrade an approved source
            # back to a candidate.
            prior = read_source_file(resolve_path(inputs, sf))
            if prior:
                sf.status = prior.status
                sf.verdict = prior.verdict
                sf.verdict_reason = prior.verdict_reason
                sf.machine_verdict = prior.machine_verdict
                sf.sections = prior.sections or sf.sections
                sf.rank = prior.rank
                sf.note = prior.note or sf.note

            # metadata_only is the candidate tier — excerpt kept, body not
            # stored. Otherwise: the body is already in hand, so storing it
            # costs nothing extra. The two-tier rule exists to avoid
            # *fetching* content for a candidate, not to discard content we
            # already have.
            apply_fetch(sf, result, full=not request.metadata_only)
            saved_to = str(await asyncio.to_thread(write_source_file, inputs, sf))
        except Exception:
            # Persistence is a bonus on a read path; never fail the preview.
            saved_to = None

    # Return the PARSED body and the lifted header fields. Previously this
    # handed back Jina's raw string, so the preview pane rendered
    # `Title: / URL Source: / Published Time: / Markdown Content:` as the
    # first four lines of the article, and the client had no structured
    # title or date to put on the row.
    from ..curation.source_file import EXCERPT_CHARS, _iso_date, parse_jina_preamble

    headers, body = parse_jina_preamble(text)
    body = body.strip()
    excerpt = " ".join(body.split())[:EXCERPT_CHARS] if body else ""

    return {
        "ok": bool(text),
        "url": result.get("url", url),
        "title": result.get("title") or headers.get("Title") or "",
        "published_at": _iso_date(headers.get("Published Time", "")),
        "excerpt": excerpt,
        "via": result.get("via"),
        "markdown": body[:20000],
        "truncated": len(body) > 20000,
        "saved_to": saved_to,
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

    # Mirror the decision into each source's own file. The list
    # (Sources.md) is what the membership gate enforces; these files are
    # where content and extracts accumulate across runs.
    #
    # Metadata tier only — no fetching here. Pulling full bodies for 79
    # sources would take minutes and block the analyst behind the very
    # "going through them takes forever" problem this surface exists to
    # fix. Content lands when a source is previewed, or later on demand.
    files_written = await asyncio.to_thread(_mirror_source_files, inputs, kept)

    return {
        "ok": True,
        "written": str(written),
        "backup": str(backup) if backup else None,
        "mode": "codified",
        "approved_count": len(approved),
        "rejected_count": len(kept) - len(approved),
        "source_files_written": files_written,
    }


def _mirror_source_files(inputs: Path, entries: List[Dict[str, Any]]) -> int:
    """Write one file per source, carrying the analyst's decision.

    Rejections are written too, not dropped: a later session should see
    what was already turned down and why rather than re-reviewing it.
    Never raises — a failure here must not lose the Sources.md write that
    already succeeded.
    """
    from ..curation.source_file import (
        SourceFile, promote, read_source_file, reject, resolve_path, write_source_file,
    )
    from ..curation.sources_md import _REJECTED_VERDICTS

    written = 0
    for raw in entries:
        url = str(raw.get("url", "")).strip()
        if not url:
            continue
        try:
            sf = SourceFile(
                url=url,
                title=str(raw.get("title") or ""),
                publisher=str(raw.get("publisher") or ""),
                published_at=str(raw.get("published_date") or ""),
                sections=[str(s) for s in (raw.get("sections") or [])],
                rank=int(raw.get("rank") or 1),
                sensitivity=str(raw.get("sensitivity") or "citable_externally"),
                note=str(raw.get("note") or ""),
            )
            # Keep content already fetched by a preview — this is a
            # decision write, not a content write.
            prior = read_source_file(resolve_path(inputs, sf))
            if prior:
                sf.body = prior.body
                sf.content_pulled = prior.content_pulled
                sf.excerpt = prior.excerpt or sf.excerpt
                sf.fetched_at = prior.fetched_at
                sf.description = prior.description
                sf.origin = prior.origin
                sf.origin_detail = prior.origin_detail
                sf.extra_metadata = prior.extra_metadata

            # Mirror the gate's rule exactly (`is_approved_entry`): presence
            # in a committed set IS approval, and `verdict` revokes rather
            # than grants. Requiring an explicit "approved" here would make
            # the file contradict the list the gate enforces — a source the
            # run may cite, filed as an unreviewed candidate.
            raw_verdict = str(raw.get("verdict") or "")
            verdict = raw_verdict.strip().lower()
            if verdict in _REJECTED_VERDICTS:
                reject(sf, str(raw.get("verdict_reason") or ""))
            else:
                promote(sf)
                # A validator result rides along as context. It is not what
                # granted approval — the analyst committing the set did.
                if verdict and verdict != "approved":
                    sf.machine_verdict = raw_verdict

            write_source_file(inputs, sf)
            written += 1
        except Exception:
            continue
    return written

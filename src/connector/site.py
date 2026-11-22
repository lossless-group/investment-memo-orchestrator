"""The site read endpoint: a deal's latest compiled memo, for the firm's own site.

``GET /site/v1/firms/{firm}/deals/{deal}/memo`` with ``Authorization: Bearer
<site key>``. Site keys come from ``MEMOPOP_SITE_KEYS`` (``firm=key,...``). A
site key reads its own firm's compiled memos and nothing else: it is not a
partner credential, so the tools under ``/v1/`` refuse it, and a partner key is
refused here. Spec: ``context-v/specs/MemoPop-Connector-API.md`` §Site read
endpoint.

Image references in the memo are rewritten to signed links (``compile/links.py``)
when they name a binary the deal has in its bucket. Memos compiled on the server
embed their diagrams as ``data:`` URIs and place no other images (nothing writes
``materials/deck-images.json`` yet); memos imported from local runs point at deck
screenshots and diagrams by local path, and the uploader put each of those files
in the bucket as ``blobs/<sha256>``, recorded as a material with its
``local_path``. That record is what a reference is matched against.
"""

from __future__ import annotations

import hmac
import logging
import re
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from . import API_VERSION
from .compile import links
from .config import ConnectorSettings
from .errors import ConnectorError, envelope
from .workspace import Workspace, is_slug, open_workspace

log = logging.getLogger("memopop.connector.site")

#: ``![alt](target)`` or ``![alt](target "title")``.
_IMAGE = re.compile(r'(!\[[^\]]*\]\()([^)\s]+)((?:\s+"[^"]*")?\))')
_EXTERNAL = ("http://", "https://", "data:", "//", "#", "mailto:")
_IN_DEAL = re.compile(r"(?:^|/)deals/[^/]+/(.+)$")


def _site_firm(settings: ConnectorSettings, authorization: str | None) -> str:
    """The firm whose site key this is; ``unauthenticated`` if it is none."""
    scheme, _, key = (authorization or "").partition(" ")
    key = key.strip()
    if scheme.lower() == "bearer" and key:
        for firm, expected in settings.site_keys.items():
            if hmac.compare_digest(expected.encode(), key.encode()):
                return firm
    raise ConnectorError(
        "unauthenticated",
        "This request has no valid site key.",
        next="Send the firm's site key as `Authorization: Bearer <key>`.",
    )


def _local_ref(target: str) -> str:
    """A memo's image target as a path relative to the deal folder, as far as known."""
    path = unquote(target).split("?", 1)[0].lstrip("./")
    match = _IN_DEAL.search(path)
    return match.group(1) if match else path


def _resolve(ref: str, materials: list[dict], label: str | None) -> str | None:
    """The bucket key of the one binary this reference names, or None."""
    candidates = [
        m
        for m in materials
        if m.get("bucket_key")
        and m.get("local_path")
        and (m["local_path"] == ref or m["local_path"].endswith("/" + ref))
    ]
    if label and len(candidates) > 1:  # the same file name in several runs' outputs
        own = [m for m in candidates if f"-{label}/" in "/" + m["local_path"]]
        candidates = own or candidates
    if len({m["bucket_key"] for m in candidates}) == 1:
        return candidates[0]["bucket_key"]
    return None


def rewrite_images(ws: Workspace, state: dict, memo: str) -> tuple[str, list[str]]:
    """Point the memo's local image references at signed links; list those left as written."""
    materials = state.get("materials") or []
    label = (state.get("compiled") or {}).get("label")
    unresolved: list[str] = []

    def swap(match: re.Match) -> str:
        target = match.group(2)
        if target.lower().startswith(_EXTERNAL):
            return match.group(0)
        key = _resolve(_local_ref(target), materials, label)
        if key is None:
            if target not in unresolved:
                unresolved.append(target)
            return match.group(0)
        return f"{match.group(1)}{links.signed_url(ws, key)}{match.group(3)}"

    return _IMAGE.sub(swap, memo), unresolved


def latest_memo(settings: ConnectorSettings, firm: str, deal: str) -> dict:
    ws = open_workspace(settings, firm)
    if not ws.deal_exists(deal):
        raise ConnectorError(
            "deal_not_found",
            f"No deal called '{deal}' on MemoPop for this firm.",
            next="Check the deal name in the site's memo mapping.",
        )
    state = ws.read_deal(deal)
    compiled = state.get("compiled") or {}
    record = state["artifacts"].get("compile.assemble")
    if not compiled or record is None:
        raise ConnectorError(
            "artifact_not_found",
            "This deal has no compiled memo yet.",
            next="Compile the memo in Claude first; the site shows only compiled memos.",
        )
    memo = ws.read_text(ws.deal_rel(deal) / record["path"])
    markdown, unresolved = rewrite_images(ws, state, memo)
    keys = compiled.get("keys") or {}
    return {
        "ok": True,
        "firm": firm,
        "deal": deal,
        "company": state.get("company"),
        "version": compiled.get("version"),
        "label": compiled.get("label"),
        "compiled_at": compiled.get("at"),
        "markdown": markdown,
        "html_url": links.signed_url(ws, keys["html"]) if keys.get("html") else None,
        "pdf_url": links.signed_url(ws, keys["pdf"]) if keys.get("pdf") else None,
        "images_unresolved": unresolved,
        "api_version": API_VERSION,
    }


def site_url_for(ws: Workspace, deal: str) -> str | None:
    """The deal's page on the firm's site, from ``firm.json``; None if it has none.

    ``site_memo_url`` is a pattern with ``{slug}``; ``site_memo_slugs`` maps a
    deal to the site's slug for it (the site keeps its own slugs).
    """
    config = ws.firm_config()
    pattern = config.get("site_memo_url")
    slug = (config.get("site_memo_slugs") or {}).get(deal)
    if not isinstance(pattern, str) or "{slug}" not in pattern or not isinstance(slug, str):
        return None
    return pattern.replace("{slug}", slug)


def _error(err: ConnectorError) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if err.code == "unauthenticated":
        headers["WWW-Authenticate"] = 'Bearer realm="memopop-site"'
    return JSONResponse(envelope(err), status_code=err.status, headers=headers)


def site_router(settings: ConnectorSettings) -> APIRouter:
    router = APIRouter()

    @router.get("/site/v1/firms/{firm}/deals/{deal}/memo", include_in_schema=False)
    async def memo(firm: str, deal: str, request: Request) -> JSONResponse:
        try:
            key_firm = _site_firm(settings, request.headers.get("authorization"))
            if key_firm != firm or not is_slug(firm):
                log.warning("site read refused: %s key for firm %s", key_firm, firm)
                raise ConnectorError("forbidden_firm", "This site key can't read that firm.")
            body = await run_in_threadpool(latest_memo, settings, firm, deal)
        except ConnectorError as err:
            if err.code == "unauthenticated":
                log.warning("site read refused: no valid site key (firm %s, deal %s)", firm, deal)
            return _error(err)
        except Exception:
            log.exception("site read failed (firm %s, deal %s)", firm, deal)
            return _error(ConnectorError("internal_error"))
        log.info("site read: firm %s, deal %s, %s", firm, deal, body["label"])
        return JSONResponse(body, headers={"Cache-Control": "private, no-store"})

    return router

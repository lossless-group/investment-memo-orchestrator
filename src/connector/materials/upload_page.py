"""The one-time upload page: ``GET /upload/{token}`` serves a form, ``POST`` takes the files.

The token is the only credential (no sign-in), so it is random, single-use, and
expires after an hour (:mod:`.uploads`). The POST stores each original in the
firm's bucket before answering and leaves text extraction to the background
pool, so even a large file gets its answer at once.

Files are matched to the materials waiting for them by filename first, then in
order; extra files become materials of their own, and a waiting material that
got no file is recorded as a ``material_unreadable`` skip so it never stays
pending. Refusals: unknown token 404, used or expired 410, no file 400.
"""

from __future__ import annotations

import html
import secrets
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from starlette.datastructures import UploadFile

from .. import flow
from ..errors import ConnectorError
from ..workspace import now_iso, open_workspace
from . import pipeline, uploads

if TYPE_CHECKING:
    from ..app import Connector

#: Largest single uploaded file, in bytes.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

_STYLE = """
body{font:16px/1.5 system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem;
color:#1d1d1f;background:#fff}
@media (prefers-color-scheme:dark){body{color:#eee;background:#151515}}
h1{font-size:1.4rem}button{font:inherit;padding:.5rem 1.2rem;margin-top:1rem}
.note{opacity:.75;font-size:.9rem}
"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
    )
    return HTMLResponse(doc, status_code=status)


def _refusal(exc: Exception) -> HTMLResponse:
    if isinstance(exc, uploads.TokenUnknown):
        return _page(
            "Upload link not found",
            "<p>This upload link isn't one MemoPop issued. Ask Claude for a new one.</p>",
            404,
        )
    return _page(
        "Upload link already used",
        "<p>This upload link has been used or has expired; each works once, for an hour. "
        "Ask Claude for a new one.</p>",
        410,
    )


def _form(upload: uploads.Upload) -> HTMLResponse:
    names = "".join(
        f"<li>{html.escape(m.get('filename') or m['material_id'])}</li>" for m in upload.materials
    )
    body = (
        f"<p>Upload the files for <strong>{html.escape(upload.deal)}</strong>:</p><ul>{names}</ul>"
        '<form method="post" enctype="multipart/form-data">'
        '<input type="file" name="files" multiple required>'
        "<br><button type=submit>Upload</button></form>"
        '<p class="note">This page works once and expires after an hour. '
        "Files are kept in your firm's private MemoPop storage.</p>"
    )
    return _page("Upload materials to MemoPop", body)


def _assign(waiting: list[dict], files: list[tuple[str, bytes, str | None]]):
    """Pair files with waiting materials: by filename first, then in order."""
    pairs: list[tuple[dict | None, tuple[str, bytes, str | None]]] = []
    left = list(waiting)
    unmatched = []
    for file in files:
        match = next(
            (m for m in left if (m.get("filename") or "").lower() == file[0].lower()), None
        )
        if match:
            left.remove(match)
            pairs.append((match, file))
        else:
            unmatched.append(file)
    for file in unmatched:
        pairs.append((left.pop(0) if left else None, file))
    return pairs, left


def _store(connector: Connector, upload: uploads.Upload, files) -> int:
    """Keep the originals, record them, and queue extraction. Returns files accepted."""
    ws = open_workspace(connector.settings, upload.firm)
    deal = upload.deal
    pairs, unfilled = _assign(upload.materials, files)
    jobs = []
    for waiting, (filename, data, content_type) in pairs:
        mid = waiting["material_id"] if waiting else f"mat-{secrets.token_hex(8)}"
        key = pipeline.bucket_key(mid, filename)
        ws.bucket.put(key, data, content_type)
        jobs.append((mid, waiting, filename, data, content_type, key))

    def record(state: dict) -> None:
        materials = state.setdefault("materials", [])
        kind = upload.materials[0]["kind"] if upload.materials else "other"
        for mid, waiting, filename, data, _, key in jobs:
            entry = pipeline.find(state, mid)
            if entry is None:
                entry = {
                    "material_id": mid,
                    "kind": kind,
                    "status": "queued",
                    "source": "upload",
                    "added_at": now_iso(),
                }
                materials.append(entry)
            entry.update(
                filename=pipeline.safe_filename(filename),
                title=filename,
                bucket_key=key,
                bytes=len(data),
                awaiting_upload=False,
                uploaded_at=now_iso(),
            )
        flow.mark(state, "materials_uploaded", count=len(jobs))

    ws.update_deal(deal, record)
    for waiting in unfilled:
        pipeline.mark_skipped(
            ws,
            deal,
            waiting["material_id"],
            "No file was uploaded for it before the link was used.",
        )
    for mid, _, filename, data, content_type, key in jobs:
        pipeline.run_in_background(
            pipeline.extract_bytes, ws, deal, mid, data, filename, content_type, key
        )
    return len(jobs)


def upload_router(connector: Connector) -> APIRouter:
    router = APIRouter()
    io_root = connector.settings.io_root

    @router.get("/upload/{token}", include_in_schema=False)
    async def upload_form(token: str) -> HTMLResponse:
        try:
            upload = uploads.peek(io_root, token)
        except (uploads.TokenUnknown, uploads.TokenSpent) as exc:
            return _refusal(exc)
        return _form(upload)

    @router.post("/upload/{token}", include_in_schema=False)
    async def upload_files(token: str, request: Request) -> HTMLResponse:
        try:
            uploads.peek(io_root, token)
        except (uploads.TokenUnknown, uploads.TokenSpent) as exc:
            return _refusal(exc)
        form = await request.form()
        files: list[tuple[str, bytes, str | None]] = []
        for _, value in form.multi_items():
            if not isinstance(value, UploadFile) or not value.filename:
                continue
            data = await value.read()
            if len(data) > MAX_UPLOAD_BYTES:
                return _page(
                    "File too large",
                    f"<p>{html.escape(value.filename)} is over 100 MB. Nothing was uploaded; "
                    "this link still works.</p>",
                    413,
                )
            if data:
                files.append((value.filename, data, value.content_type))
        if not files:
            return _page(
                "No file chosen",
                "<p>Choose at least one file. Nothing was uploaded; this link still works.</p>",
                400,
            )
        try:
            upload = uploads.spend(io_root, token)
        except (uploads.TokenUnknown, uploads.TokenSpent) as exc:
            return _refusal(exc)
        try:
            count = await run_in_threadpool(_store, connector, upload, files)
        except ConnectorError as err:
            return _page(
                "Upload failed",
                f"<p>{html.escape(err.message)} {html.escape(err.next)}</p>",
                err.status,
            )
        noun = "file" if count == 1 else "files"
        return _page(
            "Uploaded",
            f"<p>MemoPop received {count} {noun} and is reading them now. You can close this "
            "page and tell Claude they're uploaded.</p>",
        )

    return router

"""The ``materials.extract`` server step: originals to the bucket, text to the workspace.

``add_materials`` and the upload page return at once and hand the slow part
(fetching a link, extracting a large PDF) to a small background pool. Each job
ends in exactly one of two ways, so ``materials_pending`` always drains:

- **ready**: the original is in the firm's bucket under
  ``materials/<material_id>/<filename>``, the text is at
  ``deals/<deal>/materials/<material_id>.md``, and the record says ``ready``.
- **skipped**: the record says ``skipped`` and the deal gets a skip
  (``material_unreadable`` for a link or file that can't be read, ``step_failed``
  for anything unexpected). The memo continues without it.

A material record in ``deal.json`` keeps the fields Phase 1 fixed
(``material_id``, ``kind``, ``status``) and adds ``source`` (text, link, or
upload), ``title``, ``filename``, ``link``, ``bucket_key``, ``bytes``,
``chars``, ``added_at``, ``ready_at``, and ``error``. ``status`` is ``queued``,
``ready``, or ``skipped``.

Jobs run in this process; a restart while a job is queued leaves that material
``queued`` (see the changelog's "not tested").
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import PurePosixPath

from .. import flow
from ..errors import ConnectorError
from ..workspace import Workspace, now_iso
from . import fetch as fetching
from .extract import Unextractable, extract

log = logging.getLogger("memopop.connector.materials")

STEP_ID = "materials.extract"

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memopop-materials")


def run_in_background(fn: Callable[..., None], *args) -> Future:
    return _POOL.submit(fn, *args)


# ------------------------------------------------------------------ records


def safe_filename(name: str | None, fallback: str = "original") -> str:
    base = PurePosixPath((name or "").replace("\\", "/")).name
    base = re.sub(r"[^\w.-]+", "-", base).strip(".-")
    return base[:120] or fallback


def bucket_key(material_id: str, filename: str | None) -> str:
    return f"materials/{material_id}/{safe_filename(filename)}"


def text_rel(deal: str, material_id: str) -> str:
    return f"deals/{deal}/materials/{material_id}.md"


def find(state: dict, material_id: str) -> dict | None:
    return next((m for m in state.get("materials", []) if m["material_id"] == material_id), None)


def describe(record: dict) -> str:
    return record.get("filename") or record.get("link") or record["material_id"]


def mark_ready(ws: Workspace, deal: str, material_id: str, text: str, **fields) -> None:
    """Save the text and flip the record to ``ready``, in one transaction."""
    with ws.lock(deal):
        state = ws.read_deal(deal)
        record = find(state, material_id)
        if record is None:
            return
        record.update(fields)
        record.update(status="ready", chars=len(text), ready_at=now_iso(), error=None)
        flow.mark(state, "material_ready", material_id=material_id)
        state["updated_at"] = now_iso()
        with ws.transaction() as tx:
            path = tx.write_text(text_rel(deal, material_id), text)
            meta = tx.write_json(ws.deal_rel(deal) / "deal.json", state)
        ws.history.record(f"{STEP_ID}: deal {deal}, material {material_id}", [path, meta])


def mark_skipped(
    ws: Workspace, deal: str, material_id: str, reason: str, code: str = "material_unreadable"
) -> None:
    """Record a material that can't be read as a skip; the deal continues."""
    with ws.lock(deal):
        state = ws.read_deal(deal)
        record = find(state, material_id)
        if record is None:
            return
        record.update(status="skipped", error=reason)
        state["skips"].append(
            {
                "step_id": STEP_ID,
                "section": None,
                "code": code,
                "reason": f"{describe(record)}: {reason}",
                "material_id": material_id,
                "at": now_iso(),
            }
        )
        flow.mark(state, "skipped", step=STEP_ID, material_id=material_id, code=code)
        state["updated_at"] = now_iso()
        with ws.transaction() as tx:
            tx.write_json(ws.deal_rel(deal) / "deal.json", state)


def _guarded(ws: Workspace, deal: str, material_id: str, work: Callable[[], None]) -> None:
    """Run one job so that it always ends in ready or skipped."""
    try:
        work()
    except (fetching.Unreadable, Unextractable) as exc:
        _skip_quietly(ws, deal, material_id, str(exc), "material_unreadable")
    except ConnectorError as exc:
        log.warning("materials job for %s/%s: %s", deal, material_id, exc)
        _skip_quietly(ws, deal, material_id, exc.message, "step_failed")
    except Exception:  # a bug: log it in full, and still don't block the deal
        log.exception("materials job for %s/%s failed", deal, material_id)
        _skip_quietly(ws, deal, material_id, "Extraction failed on MemoPop's side.", "step_failed")


def _skip_quietly(ws: Workspace, deal: str, material_id: str, reason: str, code: str) -> None:
    try:
        mark_skipped(ws, deal, material_id, reason, code)
    except Exception:  # storage is down too; the record stays queued and is logged
        log.exception("could not record the skip for %s/%s", deal, material_id)


# ------------------------------------------------------------------ jobs


def extract_bytes(
    ws: Workspace,
    deal: str,
    material_id: str,
    data: bytes,
    filename: str | None,
    content_type: str | None,
    key: str,
) -> None:
    """Background job for an upload whose original is already in the bucket."""

    def work() -> None:
        text = extract(data, filename, content_type)
        mark_ready(ws, deal, material_id, text, bucket_key=key)

    _guarded(ws, deal, material_id, work)


def fetch_link(ws: Workspace, deal: str, material_id: str, link: str) -> None:
    """Background job for a link: fetch, keep the original, extract."""

    def work() -> None:
        got = fetching.fetch(link)
        filename = got.filename or f"{material_id}"
        key = bucket_key(material_id, filename)
        ws.bucket.put(key, got.data, got.content_type or None)
        text = extract(got.data, filename, got.content_type)
        mark_ready(
            ws,
            deal,
            material_id,
            text,
            bucket_key=key,
            filename=safe_filename(filename),
            bytes=len(got.data),
            fetched_url=got.url,
        )

    _guarded(ws, deal, material_id, work)

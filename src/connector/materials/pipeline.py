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

Jobs run in this process, so a restart drops any job in flight, and an upload
link can expire unused. Either would leave a material ``queued`` forever, so
:func:`sweep_deal` marks such a material ``skipped`` (``material_unreadable``,
with a reason): lazily when ``list_deals`` or ``next_step`` reads the deal and a
queued item is past its deadline, and :func:`sweep_all` on startup, when every
job in flight is known to be lost. A job that finishes after its material was
swept leaves the skip alone. One server process per volume is assumed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path, PurePosixPath

from .. import flow
from ..errors import ConnectorError
from ..workspace import Workspace, now_iso
from . import fetch as fetching
from . import uploads
from .extract import Unextractable, extract

log = logging.getLogger("memopop.connector.materials")

STEP_ID = "materials.extract"

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memopop-materials")

#: An upload page is refused after its hour; a POST that began just before then
#: may still be recording its files, so the sweep waits this much longer.
UPLOAD_GRACE_SECONDS = 300
#: The longest a fetch plus extraction may run before its material is presumed
#: lost (a link read can take minutes at the size cap; OCR on a large PDF, more).
PROCESSING_DEADLINE_SECONDS = 1800


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
        if record is None or record.get("status") not in ("queued", "pending"):
            return  # swept as lost while this job ran; the skip stands
        record.update(fields)
        record.update(status="ready", chars=len(text), ready_at=now_iso(), error=None)
        flow.mark(state, "material_ready", material_id=material_id)
        state["updated_at"] = now_iso()
        with ws.transaction() as tx:
            path = tx.write_text(text_rel(deal, material_id), text)
            meta = tx.write_json(ws.deal_rel(deal) / "deal.json", state)
        ws.history.record(f"{STEP_ID}: deal {deal}, material {material_id}", [path, meta])


def mark_skipped(
    ws: Workspace,
    deal: str,
    material_id: str,
    reason: str,
    code: str = "material_unreadable",
    *,
    still: Callable[[dict], bool] | None = None,
) -> bool:
    """Record a material that can't be read as a skip; the deal continues.

    ``still``, if given, is checked against the record under the deal's lock,
    and nothing is recorded unless it holds. Returns whether a skip was recorded.
    """
    with ws.lock(deal):
        state = ws.read_deal(deal)
        record = find(state, material_id)
        if record is None or record.get("status") == "skipped":
            return False
        if still is not None and not still(record):
            return False
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
        return True


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


# ------------------------------------------------------------------ the sweep


def _epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def stale_reason(record: dict, now: float, *, restarted: bool = False) -> str | None:
    """Why a queued material will never finish, or None if it still might."""
    if record.get("status") not in ("queued", "pending"):
        return None
    if record.get("awaiting_upload"):
        expires = _epoch(record.get("upload_expires_at"))
        if expires is not None and now >= expires + UPLOAD_GRACE_SECONDS:
            return "The upload link expired before a file was uploaded; add it again."
        return None
    if restarted:
        return "MemoPop restarted while this was being read; add it again."
    started = max(
        (
            t
            for t in (_epoch(record.get(k)) for k in ("added_at", "retried_at", "uploaded_at"))
            if t is not None
        ),
        default=None,
    )
    if started is not None and now >= started + PROCESSING_DEADLINE_SECONDS:
        return "Reading this took too long and was abandoned; add it again."
    return None


def sweep_deal(
    ws: Workspace, deal: str, state: dict | None = None, *, restarted: bool = False
) -> int:
    """Skip the deal's queued materials that can never finish; return how many.

    Cheap when nothing is stale: it only reads ``state`` (or ``deal.json``).
    Never call it while holding the deal's lock.
    """
    state = state if state is not None else ws.read_deal(deal)
    now = uploads.now()
    stale = [
        (m["material_id"], reason)
        for m in state.get("materials", [])
        if (reason := stale_reason(m, now, restarted=restarted))
    ]
    swept = 0
    for material_id, reason in stale:
        if mark_skipped(
            ws,
            deal,
            material_id,
            reason,
            still=lambda rec: stale_reason(rec, uploads.now(), restarted=restarted) is not None,
        ):
            swept += 1
    return swept


def sweep_all(settings, *, restarted: bool = True) -> int:
    """The startup sweep, over every firm and deal under ``MEMO_IO_ROOT``."""
    from ..workspace import is_slug, open_workspace

    root = Path(settings.io_root)
    if not root.is_dir():
        return 0
    swept = 0
    for firm_dir in sorted(root.iterdir()):
        if not (firm_dir.is_dir() and is_slug(firm_dir.name)):
            continue
        try:
            ws = open_workspace(settings, firm_dir.name)
            for deal in ws.deal_slugs():
                swept += sweep_deal(ws, deal, restarted=restarted)
        except Exception:  # one bad firm must not stop startup or the others
            log.exception("materials sweep failed for firm %s", firm_dir.name)
    if swept:
        log.warning("materials sweep: %d stale material(s) marked skipped", swept)
    return swept

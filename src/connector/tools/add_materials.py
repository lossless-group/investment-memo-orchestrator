"""add_materials: give a deal the partner's deck, dataroom, financials, notes, or links.

Three ways in (spec §The tools, ``add_materials``):

- ``text`` (up to 100,000 characters) is saved as the material's text at once
  and is ``ready`` in the response.
- ``link`` is fetched by the server in the background (Google Drive and Dropbox
  share links are rewritten to direct downloads); it is ``queued`` until then.
- ``filename`` alone is ``queued`` until the partner uses the one-time
  ``upload_url`` returned for the call.

Everything slow runs in the background (``src/connector/materials/pipeline.py``),
so the call returns within the 5-second budget whatever the file size. A link or
file that can't be read never fails the call: it becomes a
``material_unreadable`` skip on the deal, and the memo continues.

Repeat-safe: the same text, or the same link, on the same deal is the same
material and is not stored twice. A link that was skipped is fetched again.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import flow
from ..errors import ConnectorError
from ..materials import pipeline, uploads
from ..materials.fetch import check_link
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace, now_iso

MAX_INLINE_TEXT = 100_000


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["deck", "dataroom", "financials", "notes", "other"]
    link: str | None = Field(default=None, max_length=2000)
    text: str | None = None
    filename: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def one_source(self):
        if self.link is not None and self.text is not None:
            raise ValueError("give either link or text, not both")
        if self.link is None and self.text is None and self.filename is None:
            raise ValueError("give one of link, text, or filename")
        if self.text is not None and not self.text:
            raise ValueError("text is empty")
        return self


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    items: list[Item] = Field(min_length=1, max_length=50)


def _material_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"mat-{digest[:16]}"


def _validate(items: list[Item]) -> None:
    """Every refusal happens here, before anything is written."""
    for index, item in enumerate(items):
        if item.text is not None and len(item.text) > MAX_INLINE_TEXT:
            raise ConnectorError(
                "material_too_large",
                f"Item {index + 1}'s text is {len(item.text):,} characters; inline text is "
                f"limited to {MAX_INLINE_TEXT:,}.",
                details={"item": index, "chars": len(item.text), "limit": MAX_INLINE_TEXT},
            )
        if item.link is not None:
            try:
                check_link(item.link)
            except ValueError:
                raise ConnectorError(
                    "link_unreachable",
                    f"Item {index + 1}'s link can't be fetched: only http and https links can.",
                    details={"item": index, "link": item.link[:200]},
                ) from None


def _text_record(mid: str, item: Item, now: str) -> dict:
    return {
        "material_id": mid,
        "kind": item.kind,
        "status": "ready",
        "source": "text",
        "title": item.filename or f"{item.kind.capitalize()} (pasted text)",
        "filename": item.filename,
        "chars": len(item.text or ""),
        "added_at": now,
        "ready_at": now,
    }


def _link_record(mid: str, item: Item, link: str, now: str) -> dict:
    return {
        "material_id": mid,
        "kind": item.kind,
        "status": "queued",
        "source": "link",
        "title": item.filename or link,
        "link": link,
        "added_at": now,
    }


def _upload_record(mid: str, item: Item, now: str) -> dict:
    return {
        "material_id": mid,
        "kind": item.kind,
        "status": "queued",
        "source": "upload",
        "title": item.filename,
        "filename": item.filename,
        "awaiting_upload": True,
        "added_at": now,
    }


def handle(ws: Workspace, params: Input) -> dict:
    deal = params.deal
    ws.read_deal(deal)
    _validate(params.items)

    accepted: list[dict] = []
    texts: dict[str, str] = {}
    to_fetch: list[tuple[str, str]] = []
    awaiting: list[dict] = []
    upload: dict = {}

    with ws.lock(deal):
        state = ws.read_deal(deal)
        materials = state.setdefault("materials", [])
        for item in params.items:
            now = now_iso()
            if item.text is not None:
                mid = _material_id(deal, "text", item.kind, item.text)
                record = pipeline.find(state, mid)
                if record is None:
                    record = _text_record(mid, item, now)
                    materials.append(record)
                    texts[mid] = item.text
            elif item.link is not None:
                link = check_link(item.link)
                mid = _material_id(deal, "link", link)
                record = pipeline.find(state, mid)
                if record is None:
                    record = _link_record(mid, item, link, now)
                    materials.append(record)
                    to_fetch.append((mid, link))
                elif record["status"] == "skipped":
                    record.update(status="queued", error=None, retried_at=now)
                    to_fetch.append((mid, link))
            else:
                mid = f"mat-{secrets.token_hex(8)}"
                record = _upload_record(mid, item, now)
                materials.append(record)
                awaiting.append({"material_id": mid, "filename": item.filename, "kind": item.kind})
            accepted.append({"material_id": mid, "kind": item.kind, "status": record["status"]})

        if awaiting:
            token, expires = uploads.issue(ws.settings.io_root, ws.firm, deal, awaiting)
            upload = {
                "upload_url": f"{ws.settings.public_base_url}/upload/{token}",
                "upload_expires_at": uploads.iso(expires),
            }
            waiting = {a["material_id"] for a in awaiting}
            for record in materials:
                if record["material_id"] in waiting:
                    record["upload_expires_at"] = upload["upload_expires_at"]

        if texts or to_fetch or awaiting:
            flow.mark(state, "materials_added", count=len(texts) + len(to_fetch) + len(awaiting))
            state["updated_at"] = now_iso()
            with ws.transaction() as tx:
                paths = [
                    tx.write_text(pipeline.text_rel(deal, mid), text) for mid, text in texts.items()
                ]
                paths.append(tx.write_json(ws.deal_rel(deal) / "deal.json", state))
            if texts:
                ws.history.record(f"{pipeline.STEP_ID}: deal {deal}, {len(texts)} text(s)", paths)

    for mid, link in to_fetch:
        pipeline.run_in_background(pipeline.fetch_link, ws, deal, mid, link)

    return {"deal": deal, "accepted": accepted, **upload}


TOOL = ToolDef(
    name="add_materials",
    summary="Add the partner's materials to a deal: a deck, dataroom, financials, notes, or links.",
    when_to_use=(
        "the partner shares or mentions documents about the company: a pitch deck, a dataroom "
        "link, financials, call notes, or a URL worth reading."
    ),
    when_not_to_use=(
        "to save your own research or drafts: those go through submit_artifact for the step "
        "next_step handed you."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "items",
            "array",
            "The materials. Each has `kind` (deck, dataroom, financials, notes, or other) and one "
            "of `link` (fetched by the server; Google Drive and Dropbox share links work, DocSend "
            "does not yet), `text` (up to 100,000 characters, stored as is), or `filename` alone "
            "(returns a one-time upload page). A `filename` beside `text` or `link` names it.",
            [{"kind": "notes", "text": "Call notes: founders met at Stanford..."}],
            required=True,
        ),
    ],
    returns=[
        ReturnDoc(
            "accepted",
            "One entry per item, in order: its material_id, kind, and status. `ready` means its "
            "text can be read now; `queued` means it is being fetched or waits for its upload.",
        ),
        ReturnDoc(
            "upload_url",
            "Only when an item had a filename alone: a one-time page where the partner uploads "
            "those files. No sign-in; it works once and expires after an hour.",
        ),
        ReturnDoc("upload_expires_at", "When the upload page stops working (ISO 8601, UTC)."),
    ],
    changes=(
        "stores each material (originals in the firm's bucket under materials/, text in the "
        "workspace); fetching and text extraction continue in the background. A link or file "
        "that can't be read becomes a material_unreadable skip on the deal; the memo continues."
    ),
    duration=(
        "returns within 5 seconds; extraction finishes in the background (list_deals shows "
        "materials_pending until it does)."
    ),
    errors=["deal_not_found", "material_too_large", "link_unreachable"],
    error_next_overrides={
        "link_unreachable": "Only http and https links can be fetched. Ask the partner for a "
        "web link to the file, or send an item with only `filename` to get an upload page.",
    },
    next=(
        "give the partner the upload_url if there is one and tell them it works once, for an "
        "hour. Then call next_step: once a material is ready it hands out materials.brief "
        "before research."
    ),
    examples=[
        Example(
            title="Inline call notes are ready at once",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={
                "deal": "acme-ai",
                "items": [{"kind": "notes", "text": "Founders met at Stanford in 2019."}],
            },
            response={
                "ok": True,
                "deal": "acme-ai",
                "accepted": [{"material_id": ANY, "kind": "notes", "status": "ready"}],
                "api_version": "1",
            },
        ),
        Example(
            title="A deck by filename gets a one-time upload page",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai", "items": [{"kind": "deck", "filename": "acme-deck.pdf"}]},
            response={
                "ok": True,
                "deal": "acme-ai",
                "accepted": [{"material_id": ANY, "kind": "deck", "status": "queued"}],
                "upload_url": ANY,
                "upload_expires_at": ANY,
                "api_version": "1",
            },
        ),
        Example(
            title="A link that isn't http or https is refused",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai", "items": [{"kind": "deck", "link": "file:///etc/hosts"}]},
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "link_unreachable"},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    rest_method="POST",
    rest_path="/v1/deals/{deal}/materials",
)

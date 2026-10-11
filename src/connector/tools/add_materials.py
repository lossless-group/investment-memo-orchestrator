"""add_materials: give a deal the partner's deck, dataroom, financials, notes, or links.

Plan 1 declares the tool with its full docs; plan 4 implements it (link fetching,
the one-time upload page, background extraction, originals in the firm's bucket).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..errors import ConnectorError
from ..registry.types import Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace

MAX_INLINE_TEXT = 100_000


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["deck", "dataroom", "financials", "notes", "other"]
    link: str | None = Field(default=None, max_length=2000)
    text: str | None = None
    filename: str | None = Field(default=None, max_length=300)


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    items: list[Item] = Field(min_length=1, max_length=50)


def handle(ws: Workspace, params: Input) -> dict:
    ws.read_deal(params.deal)
    raise ConnectorError("not_implemented", "add_materials is not live on this server yet.")


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
            "of `link` (fetched by the server), `text` (up to 100,000 characters, stored as is), "
            "or `filename` alone (returns a one-time upload page).",
            [{"kind": "notes", "text": "Call notes: founders met at Stanford..."}],
            required=True,
        ),
    ],
    returns=[
        ReturnDoc("accepted", "One entry per item: its material_id and status, queued or ready."),
        ReturnDoc(
            "upload_url", "A one-time page where the partner uploads files given by filename."
        ),
        ReturnDoc("upload_expires_at", "When the upload page stops working."),
    ],
    changes=(
        "stores each material (originals in the firm's bucket, text in the workspace); text "
        "extraction continues in the background."
    ),
    duration="returns within 5 seconds; extraction finishes in the background (list_deals shows materials_pending).",
    errors=["deal_not_found", "material_too_large", "link_unreachable", "not_implemented"],
    error_next_overrides={
        "not_implemented": "Materials can't be added yet: ask the partner to paste the key facts "
        "into the conversation, and continue with next_step.",
    },
    next="give the partner the upload_url if there is one, then call next_step.",
    examples=[
        Example(
            title="Inline notes (until materials ship, this returns not_implemented)",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={
                "deal": "acme-ai",
                "items": [{"kind": "notes", "text": "Founders met at Stanford."}],
            },
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "not_implemented"},
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
    implemented=False,
)

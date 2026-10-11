"""list_deals: the firm's deals, where each stands, a page at a time."""

from __future__ import annotations

import base64
import binascii
import json

from pydantic import Field

from .. import flow
from ..errors import ConnectorError
from ..materials import pipeline
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace, is_slug

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class Input(ToolInput):
    cursor: str | None = Field(default=None, max_length=400)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1)


def encode_cursor(after: str) -> str:
    return base64.urlsafe_b64encode(json.dumps({"after": after}).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> str:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        after = json.loads(base64.urlsafe_b64decode(padded.encode()))["after"]
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError):
        after = None
    if not isinstance(after, str) or not is_slug(after):
        raise ConnectorError(
            "validation_failed",
            "That cursor is not one list_deals returned.",
            details={"errors": [{"field": "cursor", "problem": "unrecognised cursor"}]},
        )
    return after


def summarise(ws: Workspace, state: dict) -> dict:
    from .compile import job_summary

    registry = load_registry()
    return {
        "deal": state["deal"],
        "company": state["company"],
        "stage": state.get("stage"),
        "template": state["template"],
        "phase": flow.phase_of(registry, state, ws),
        "next_step_hint": flow.hint(registry, state, ws),
        "materials_pending": len(flow.pending_materials(state)),
        "skips": [
            {
                "step_id": s["step_id"],
                "section": s.get("section"),
                "code": s["code"],
                "reason": s.get("reason"),
            }
            for s in state.get("skips", [])
        ],
        "compile": job_summary(ws, state),
        "updated_at": state["updated_at"],
    }


def handle(ws: Workspace, params: Input) -> dict:
    limit = min(params.limit, MAX_LIMIT)
    slugs = ws.deal_slugs()
    if params.cursor:
        after = decode_cursor(params.cursor)
        slugs = [s for s in slugs if s > after]
    page = slugs[:limit]
    deals = []
    for slug in page:
        state = ws.read_deal(slug)
        if pipeline.sweep_deal(ws, slug, state):  # materials that can never finish
            state = ws.read_deal(slug)
        deals.append(summarise(ws, state))
    body: dict = {"deals": deals, "next_cursor": None}
    if len(slugs) > limit:
        body["next_cursor"] = encode_cursor(page[-1])
    return body


TOOL = ToolDef(
    name="list_deals",
    summary="List this firm's deals with where each one stands and what comes next.",
    when_to_use=(
        "the partner asks what they're working on, names a company you need to find, or "
        "you start a new conversation and need the deal's slug before calling next_step."
    ),
    when_not_to_use=(
        "to see the work inside one deal: call next_step with its slug (or get_artifact "
        "for a specific file). To start a deal that isn't listed, call create_new_deal."
    ),
    inputs=[
        InputDoc(
            "cursor",
            "string",
            "The next_cursor from a previous call, to get the following page. Omit for the first page.",
            "eyJhZnRlciI6ICJhY21lLWFpIn0",
        ),
        InputDoc(
            "limit",
            "integer",
            "How many deals per page, 1 to 100 (larger values are capped at 100). Default 20.",
            20,
        ),
    ],
    returns=[
        ReturnDoc("deals", "One entry per deal, ordered by slug."),
        ReturnDoc("deals[].deal", "The deal's slug, used by every other tool."),
        ReturnDoc("deals[].company", "The company's name as the partner gave it."),
        ReturnDoc("deals[].stage", "The stage, if one was given."),
        ReturnDoc("deals[].template", "The memo template (outline) the deal uses."),
        ReturnDoc("deals[].phase", "materials, research, draft, enhance, compile, or done."),
        ReturnDoc("deals[].next_step_hint", "One line saying what next_step will hand out."),
        ReturnDoc("deals[].materials_pending", "How many materials are still being extracted."),
        ReturnDoc("deals[].skips", "Optional steps that were skipped, with the code and reason."),
        ReturnDoc(
            "deals[].compile",
            "The last compile: job_id, status (running, done, or failed), version, and, once "
            "done, fresh html_url and pdf_url links; null if the deal was never compiled.",
        ),
        ReturnDoc("deals[].updated_at", "When the deal last changed (UTC, ISO 8601)."),
        ReturnDoc("next_cursor", "Pass as cursor to get the next page; null on the last page."),
    ],
    changes="nothing.",
    duration="under a second; a firm with hundreds of deals, a few seconds.",
    errors=["validation_failed"],
    error_next_overrides={
        "validation_failed": "Call again without cursor to start from the first page, "
        "with limit between 1 and 100.",
    },
    next="call next_step with a deal's slug to continue it, or create_new_deal to start one.",
    examples=[
        Example(
            title="A firm with one deal",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={},
            response={
                "ok": True,
                "deals": [
                    {
                        "deal": "acme-ai",
                        "company": "Acme Robotics",
                        "stage": None,
                        "template": "direct-early-stage-12Ps",
                        "phase": "research",
                        "next_step_hint": "Call next_step: research.section for Executive Summary is next.",
                        "materials_pending": 0,
                        "skips": [],
                        "updated_at": ANY,
                    }
                ],
                "next_cursor": None,
                "api_version": "1",
            },
        ),
        Example(
            title="Paging",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                ("create_new_deal", {"company": "Beta Labs", "url": "https://betalabs.io"}),
            ],
            request={"limit": 1},
            response={"ok": True, "deals": [{"deal": "acme-ai"}], "next_cursor": ANY},
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=True,
    destructive=False,
    rest_method="GET",
    rest_path="/v1/deals",
)

"""cancel_revision: drop an open revision and put the memo back as it was."""

from __future__ import annotations

import hashlib

from pydantic import Field

from .. import flow
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace
from ._examples import drafts_walk, research_walk
from .start_revision import EXAMPLE_ANGLE
from .submit_artifact import EXAMPLE_RESEARCH


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)


def handle(ws: Workspace, params: Input) -> dict:
    registry = load_registry()
    deal = params.deal
    rel = ws.deal_rel(deal) if ws.deal_exists(deal) else None
    with ws.lock(deal) if rel else _no_lock():
        state = ws.read_deal(deal)
        revision = state.get("revision")
        if not revision:
            raise ConnectorError("no_open_revision")

        restored: list[str] = []
        dropped: list[str] = []
        writes: dict = {}
        for key, base in revision["baseline"].items():
            record = state["artifacts"].get(key)
            if record is None or record.get("revision_id") != revision["id"]:
                continue  # not touched during the revision
            record.pop("revision_id", None)
            if record["version"] == base["version"]:
                continue  # confirmed unchanged
            if base["copy"] is None:
                del state["artifacts"][key]  # first done during the revision
                dropped.append(key)
                continue
            text = ws.read_text(rel / base["copy"])
            record.update(
                version=record["version"] + 1,
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                chars=len(text),
                seq=base["seq"],  # back in its old place, so the old current text is current
                saved_at=flow.now_iso(),
            )
            writes[rel / record["path"]] = text
            restored.append(key)

        now = flow.now_iso()
        state.setdefault("revisions", []).append(
            {**revision, "status": "cancelled", "closed_at": now}
        )
        state["revision"] = None
        flow.mark(state, "revision_cancelled", revision_id=revision["id"], restored=restored)
        state["updated_at"] = now
        with ws.transaction() as tx:
            written = [tx.write_text(path, text) for path, text in writes.items()]
            written.append(tx.write_json(rel / "deal.json", state))
        ws.history.record(f"cancel_revision: deal {deal}, {revision['id']}", written)
    return {
        "deal": deal,
        "revision_id": revision["id"],
        "restored": restored,
        "dropped": dropped,
        "memo_version": flow.last_label(state),
        "next_hint": flow.hint(registry, state, ws),
    }


class _no_lock:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


TOOL = ToolDef(
    name="cancel_revision",
    summary="Drop the open revision of a memo and put every reopened section back as it was.",
    when_to_use=(
        "the partner decides not to go ahead with a revision, or wants to start it over "
        "differently."
    ),
    when_not_to_use=(
        "to finish a revision: call next_step until done, then compile. Cancelling discards "
        "the revision's changes (they stay in the deal's history)."
    ),
    inputs=[InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True)],
    returns=[
        ReturnDoc("revision_id", "The revision that was cancelled."),
        ReturnDoc(
            "restored",
            "Artifacts changed during the revision and now back to their earlier text, each "
            "at a new version.",
        ),
        ReturnDoc("dropped", "Artifacts first made during the revision, now removed."),
        ReturnDoc("memo_version", "The last compiled memo's version, which still stands."),
        ReturnDoc("next_hint", "What next_step will say now."),
    ],
    changes=(
        "closes the revision, restores each changed artifact's earlier text as a new version, "
        "and removes artifacts the revision made. The revision's work stays in the history."
    ),
    duration="under a second.",
    errors=["deal_not_found", "no_open_revision"],
    next="tell the partner the memo is back to the version named in memo_version.",
    examples=[
        Example(
            title="Cancel a revision before anything was resubmitted",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                *research_walk("acme-ai", EXAMPLE_RESEARCH),
                *drafts_walk("acme-ai", EXAMPLE_RESEARCH),
                ("start_revision", {"deal": "acme-ai", "sections": ["2"], "angle": EXAMPLE_ANGLE}),
            ],
            request={"deal": "acme-ai"},
            response={
                "ok": True,
                "deal": "acme-ai",
                "revision_id": ANY,
                "restored": [],
                "dropped": [],
                "memo_version": None,
                "next_hint": ANY,
                "api_version": "1",
            },
        ),
        Example(
            title="No revision to cancel",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai"},
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "no_open_revision"},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=True,
    rest_method="DELETE",
    rest_path="/v1/deals/{deal}/revisions/current",
)

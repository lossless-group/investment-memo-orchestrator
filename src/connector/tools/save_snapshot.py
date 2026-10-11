"""save_snapshot: back up the firm's whole workspace to its bucket.

Plan 1 declares the tool with its full docs; plan 6 implements it (an archive
under snapshots/ in the firm's bucket, change counts against the last one).
"""

from __future__ import annotations

from pydantic import Field

from ..errors import ConnectorError
from ..registry.types import Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace


class Input(ToolInput):
    label: str | None = Field(default=None, max_length=120)


def handle(ws: Workspace, params: Input) -> dict:
    raise ConnectorError("not_implemented", "save_snapshot is not live on this server yet.")


TOOL = ToolDef(
    name="save_snapshot",
    summary="Save a backup of this firm's whole MemoPop workspace to the firm's private bucket.",
    when_to_use=(
        "the partner asks to back up, checkpoint, or save a copy of their work, for example "
        "before a big revision or at the end of a deal."
    ),
    when_not_to_use=(
        "to save a step's work: submit_artifact already keeps every version. A snapshot is a "
        "whole-workspace backup."
    ),
    inputs=[InputDoc("label", "string", "A short name for the snapshot.", "before IC meeting")],
    returns=[
        ReturnDoc("snapshot_id", "The snapshot's id."),
        ReturnDoc("label", "The label given, if any."),
        ReturnDoc("created_at", "When it was taken (UTC, ISO 8601)."),
        ReturnDoc("bytes", "The archive's size."),
        ReturnDoc("files_added", "Files new since the previous snapshot."),
        ReturnDoc("files_changed", "Files changed since the previous snapshot."),
        ReturnDoc("files_removed", "Files gone since the previous snapshot."),
    ],
    changes="writes one archive to the firm's bucket under snapshots/; changes nothing in the workspace.",
    duration="a few seconds; up to a minute for a large workspace.",
    errors=["not_implemented"],
    error_next_overrides={
        "not_implemented": "Snapshots aren't live yet; every submitted artifact is already kept. "
        "Tell the partner and continue.",
    },
    next="tell the partner the snapshot's label and time, then carry on.",
    examples=[
        Example(
            title="A labelled snapshot (until snapshots ship, this returns not_implemented)",
            request={"label": "before IC meeting"},
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
    rest_path="/v1/snapshots",
    implemented=False,
)

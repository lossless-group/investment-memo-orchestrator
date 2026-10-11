"""get_artifact: read one artifact or material, a page at a time."""

from __future__ import annotations

import re

from pydantic import Field, model_validator

from .. import flow
from ..errors import ConnectorError
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace
from .submit_artifact import EXAMPLE_RESEARCH

MATERIAL_ID = re.compile(r"^mat-[a-z0-9]{4,40}$")


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    artifact_id: str | None = Field(default=None, max_length=300)
    material_id: str | None = Field(default=None, max_length=60)
    version: int | None = Field(default=None, ge=1)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def one_id(self):
        if (self.artifact_id is None) == (self.material_id is None):
            raise ValueError("give exactly one of artifact_id or material_id")
        return self


def _page(text: str, offset: int) -> dict:
    if offset > len(text):
        raise ConnectorError(
            "validation_failed",
            f"offset {offset} is past the end ({len(text)} characters).",
            details={"errors": [{"field": "offset", "problem": "past the end"}]},
        )
    end = offset + flow.PAGE_SIZE
    return {
        "text": text[offset:end],
        "offset": offset,
        "total_chars": len(text),
        "next_offset": end if end < len(text) else None,
    }


def handle(ws: Workspace, params: Input) -> dict:
    state = ws.read_deal(params.deal)
    base = f"deals/{params.deal}"
    if params.material_id is not None:
        material = next(
            (m for m in state.get("materials", []) if m.get("material_id") == params.material_id),
            None,
        )
        if material is None or not MATERIAL_ID.match(params.material_id):
            raise ConnectorError("artifact_not_found")
        text = ws.read_text(f"{base}/materials/{params.material_id}.md")
        return {
            "deal": params.deal,
            "material_id": params.material_id,
            "title": material.get("title") or material.get("filename") or params.material_id,
            "kind": material.get("kind", "material"),
            "version": 1,
            **_page(text, params.offset),
        }

    record = state["artifacts"].get(params.artifact_id)
    if record is None:
        raise ConnectorError(
            "artifact_not_found",
            f"No artifact '{params.artifact_id}' on this deal.",
            details={"available": sorted(state["artifacts"])},
        )
    if params.version is not None and params.version != record["version"]:
        text = ws.history.read(ws.root / base / record["path"], params.version)
        if text is None:
            raise ConnectorError(
                "artifact_not_found",
                f"Version {params.version} of '{params.artifact_id}' is not available.",
                next=f"Call again without version to read the latest (version {record['version']}).",
            )
        version = params.version
    else:
        text = ws.read_text(f"{base}/{record['path']}")
        version = record["version"]
    section = flow.section_info(state, record.get("section")) or {}
    title = record["step_id"] + (f": {section.get('name')}" if section else "")
    return {
        "deal": params.deal,
        "artifact_id": params.artifact_id,
        "title": title,
        "kind": record.get("kind", "artifact"),
        "version": version,
        "partner_approved": record.get("partner_approved", False),
        **_page(text, params.offset),
    }


TOOL = ToolDef(
    name="get_artifact",
    summary="Read one of a deal's artifacts or materials by id, 100,000 characters at a time.",
    when_to_use=(
        "you need the full text of something next_step cut short (use its next_offset), the "
        "partner asks to see a research file or draft again, or you need an earlier version."
    ),
    when_not_to_use=(
        "to find out what to do next: call next_step, which already includes the inputs a step needs."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "artifact_id",
            "string",
            "The artifact's id, as next_step or submit_artifact returned it. Give this or material_id.",
            "research.section:01-executive-summary",
        ),
        InputDoc(
            "material_id",
            "string",
            "A material's id, from add_materials. Give this or artifact_id.",
            "mat-3f9a1c",
        ),
        InputDoc("version", "integer", "An earlier version to read; omit for the latest.", 1),
        InputDoc(
            "offset",
            "integer",
            "Where to start reading, from a previous next_offset. Default 0.",
            100000,
        ),
    ],
    returns=[
        ReturnDoc("title", "What the artifact is, e.g. research.section: Origins."),
        ReturnDoc("kind", "research, section, enhancement, brief, or the material's kind."),
        ReturnDoc("version", "The version returned."),
        ReturnDoc("text", "Up to 100,000 characters of the artifact, starting at offset."),
        ReturnDoc("total_chars", "The artifact's full length."),
        ReturnDoc("next_offset", "Pass as offset to read on; null when this page reaches the end."),
    ],
    changes="nothing.",
    duration="under a second.",
    errors=["deal_not_found", "artifact_not_found", "validation_failed"],
    next="carry on with the step you are doing, or call next_step.",
    examples=[
        Example(
            title="Read approved research",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                ("next_step", {"deal": "acme-ai"}),
                (
                    "submit_artifact",
                    {
                        "deal": "acme-ai",
                        "step_id": "research.section",
                        "section": "01-executive-summary",
                        "content": EXAMPLE_RESEARCH,
                        "partner_approved": True,
                    },
                ),
            ],
            request={"deal": "acme-ai", "artifact_id": "research.section:01-executive-summary"},
            response={
                "ok": True,
                "artifact_id": "research.section:01-executive-summary",
                "title": "research.section: Executive Summary",
                "kind": "research",
                "version": 1,
                "partner_approved": True,
                "text": EXAMPLE_RESEARCH,
                "offset": 0,
                "total_chars": len(EXAMPLE_RESEARCH),
                "next_offset": None,
                "api_version": "1",
            },
        ),
        Example(
            title="An artifact that doesn't exist yet",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai", "artifact_id": "research.section:01-executive-summary"},
            response={
                "ok": False,
                "error": {
                    "kind": "invalid",
                    "code": "artifact_not_found",
                    "details": {"available": []},
                },
                "api_version": "1",
            },
        ),
        Example(
            title="Neither id given",
            request={"deal": "acme-ai"},
            response={
                "ok": False,
                "error": {"code": "validation_failed", "details": {"errors": ANY}},
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=True,
    destructive=False,
    rest_method="GET",
    rest_path="/v1/deals/{deal}/artifacts/{id}",
)

"""get_outline: the outline a deal uses, one outline, or the firm's outlines."""

from __future__ import annotations

import yaml
from pydantic import Field

from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..templates import available_templates, default_template, load_sections, outline_path
from ..workspace import Workspace


class Input(ToolInput):
    deal: str | None = Field(default=None, min_length=1, max_length=100)
    template: str | None = Field(default=None, min_length=1, max_length=100)


def _view(section: dict) -> dict:
    return {
        "key": section["key"],
        "number": section.get("number"),
        "name": section["name"],
        "description": section.get("description") or "",
        "guiding_questions": list(section.get("guiding_questions") or []),
    }


def handle(ws: Workspace, params: Input) -> dict:
    if params.deal is not None:
        state = ws.read_deal(params.deal)
        return {
            "deal": params.deal,
            "template": state["template"],
            "pinned": bool(state.get("outline_pinned_from")),
            "pinned_from": state.get("outline_pinned_from"),
            "sections": [_view(s) for s in state["sections"]],
        }
    if params.template is not None:
        _, source = outline_path(ws, params.template)
        return {
            "template": params.template,
            "source": source,
            "sections": [_view(s) for s in load_sections(ws, params.template)],
        }
    default = default_template(ws)
    outlines = []
    for name in available_templates(ws):
        path, source = outline_path(ws, name)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if (data.get("metadata") or {}).get("pinned_for"):
            continue  # a deal's own copy, not one of the firm's outlines
        outlines.append(
            {
                "name": name,
                "source": source,
                "default": name == default,
                "sections": len(data.get("sections") or []),
            }
        )
    return {"outlines": outlines}


TOOL = ToolDef(
    name="get_outline",
    summary="Read the outline a deal's memo uses, one outline's sections, or the firm's outlines.",
    when_to_use=(
        "before changing a memo's outline with edit_outline, or when the partner asks what "
        "sections a memo has or what each should answer."
    ),
    when_not_to_use=(
        "to read a section's text: call get_artifact. To change the outline: call edit_outline."
    ),
    inputs=[
        InputDoc(
            "deal",
            "string",
            "A deal's slug: returns the sections that memo uses (its pinned copy, if it has one).",
            "acme-ai",
        ),
        InputDoc(
            "template",
            "string",
            "An outline's name: returns its sections. Omit both deal and template to list the "
            "firm's outlines.",
            "direct-early-stage-12Ps",
        ),
    ],
    returns=[
        ReturnDoc("template", "With deal or template: the outline's name."),
        ReturnDoc("pinned", "With deal: true when the deal has its own copy of its outline."),
        ReturnDoc("pinned_from", "With deal: the outline its pinned copy came from, or null."),
        ReturnDoc(
            "sections",
            "With deal or template: each section's key, number, name, description, and "
            "guiding_questions, in order.",
        ),
        ReturnDoc("source", "With template: firm (the firm's own) or memopop (MemoPop's)."),
        ReturnDoc(
            "outlines",
            "With neither: each outline's name, source, whether it is the firm's default, and "
            "its number of sections. Deals' pinned copies are not listed.",
        ),
    ],
    changes="nothing.",
    duration="under a second.",
    errors=["deal_not_found", "template_not_found"],
    next="call edit_outline to change a memo's outline, then next_step.",
    examples=[
        Example(
            title="List the firm's outlines",
            request={},
            response={"ok": True, "outlines": ANY, "api_version": "1"},
        ),
        Example(
            title="The outline a deal uses",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai"},
            response={
                "ok": True,
                "deal": "acme-ai",
                "template": ANY,
                "pinned": False,
                "pinned_from": None,
                "sections": ANY,
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=True,
    destructive=False,
    rest_method="GET",
    rest_path="/v1/outlines",
)

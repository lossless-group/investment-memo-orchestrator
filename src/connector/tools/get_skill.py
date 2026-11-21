"""get_skill: one playbook, to follow for the change the partner asked for."""

from __future__ import annotations

from pydantic import Field

from ..errors import ConnectorError
from ..registry.skills import load_skills
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace


class Input(ToolInput):
    name: str = Field(min_length=1, max_length=100)


def handle(ws: Workspace, params: Input) -> dict:
    skills = load_skills()
    skill = skills.get(params.name.strip().lower())
    if skill is None:
        names = list(skills)
        raise ConnectorError(
            "skill_not_found",
            f"No MemoPop skill called '{params.name}'. The skills are: {', '.join(names)}.",
            details={"available": names},
        )
    return {"name": skill.name, "description": skill.description, "text": skill.text}


TOOL = ToolDef(
    name="get_skill",
    summary="Load one of MemoPop's playbooks by name, so you follow it for the change the partner asked for.",
    when_to_use=(
        "list_skills shows a playbook that fits what the partner wants, or a prompt or another "
        "playbook names one. Load it before you start the change, and follow it."
    ),
    when_not_to_use=(
        "to find out which playbooks exist: call list_skills. To do a step of a memo being "
        "written, call next_step, whose instruction already says what to do."
    ),
    inputs=[
        InputDoc(
            "name",
            "string",
            "The playbook's name, exactly as list_skills returns it.",
            "fix-a-source-or-citation",
            required=True,
        ),
    ],
    returns=[
        ReturnDoc("name", "The playbook's name."),
        ReturnDoc("description", "When it applies, in one line."),
        ReturnDoc("text", "The playbook, in markdown. It ends with the tool to call."),
    ],
    changes="nothing.",
    duration="under a second.",
    errors=["skill_not_found", "validation_failed"],
    next="follow the playbook; it ends with the tool to call.",
    examples=[
        Example(
            title="Load a playbook",
            request={"name": "edit-wording"},
            response={
                "ok": True,
                "name": "edit-wording",
                "description": ANY,
                "text": ANY,
                "api_version": "1",
            },
        ),
        Example(
            title="A name that doesn't exist",
            request={"name": "write-a-poem"},
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "skill_not_found", "details": ANY},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=True,
    destructive=False,
    rest_method="GET",
    rest_path="/v1/skills/{name}",
)

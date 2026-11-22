"""list_skills: the playbooks MemoPop serves, by name and one-line description."""

from __future__ import annotations

from ..registry.skills import load_skills
from ..registry.types import ANY, Example, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace


class Input(ToolInput):
    pass


def handle(ws: Workspace, params: Input) -> dict:
    return {
        "skills": [
            {"name": skill.name, "description": skill.description}
            for skill in load_skills().values()
        ]
    }


TOOL = ToolDef(
    name="list_skills",
    summary="List MemoPop's playbooks for changing a memo, each with its name and a one-line description.",
    when_to_use=(
        "a partner asks to change a finished memo (fix a citation, rewrite a section, change "
        "wording, change the outline, check the memo on the site), or asks what MemoPop can do. "
        "Call it once per conversation, before the first change."
    ),
    when_not_to_use=(
        "when you already know which playbook fits: call get_skill with its name. To find a "
        "deal, call list_deals."
    ),
    inputs=[],
    returns=[
        ReturnDoc(
            "skills",
            "Every playbook, in name order: its `name` (pass it to get_skill) and a one-line "
            "`description` saying when it applies.",
        ),
    ],
    changes="nothing.",
    duration="under a second.",
    errors=[],
    next="call get_skill with the name that fits the partner's request, and follow it.",
    examples=[
        Example(
            title="The playbooks",
            request={},
            response={"ok": True, "skills": ANY, "api_version": "1"},
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=True,
    destructive=False,
    rest_method="GET",
    rest_path="/v1/skills",
)

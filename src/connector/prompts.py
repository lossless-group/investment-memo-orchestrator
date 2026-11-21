"""The MCP prompts: entry points a partner picks from the connector's menu in Claude.

MemoPop's tools start out deferred in Claude, so a request that doesn't name
MemoPop may never load them. Each prompt names MemoPop and the playbook to
load with ``get_skill``, which gets Claude past that (spec §How partners get
the method, CONN-SKL-04).
"""

from __future__ import annotations

from dataclasses import dataclass

#: The one optional argument every prompt takes: the partner's request, in their words.
REQUEST_ARGUMENT = "request"
REQUEST_DESCRIPTION = "What you want, in your own words: which memo, which section, what to change."


@dataclass(frozen=True)
class PromptDef:
    name: str
    title: str
    description: str
    text: str

    def render(self, request: str | None) -> str:
        request = (request or "").strip()
        if not request:
            return self.text + " Ask me what I want changed if I haven't said."
        return f"{self.text}\n\nMy request: {request}"


_LOAD = "Use MemoPop: load its tools, call list_skills, then"

PROMPTS: list[PromptDef] = [
    PromptDef(
        name="edit-a-memo",
        title="Edit a memo",
        description="Change one of your firm's finished memos: a source, a section, the wording.",
        text=(
            f"{_LOAD} call get_skill with the playbook that fits my change: "
            "`fix-a-source-or-citation` when it's about sources, citations or missing "
            "information; `edit-wording` for wording, tone, order or typos; "
            "`just-edit-the-memo` if I say to just edit the memo. Don't ask me which; "
            "tell me in one line where the change went."
        ),
    ),
    PromptDef(
        name="fix-a-citation",
        title="Fix a citation",
        description="Fix a wrong or broken citation or a weak source in a memo, and rewrite the section from it.",
        text=(
            f"{_LOAD} call get_skill with `fix-a-source-or-citation` and follow it to fix "
            "the citation in my firm's memo."
        ),
    ),
    PromptDef(
        name="change-the-outline-for-this-memo",
        title="Change the outline for this memo",
        description="Add, remove, rename or reorder sections in one memo, without touching the others.",
        text=(
            f"{_LOAD} call get_skill with `change-the-outline-for-this-memo` and follow it. "
            "The change is for this memo only."
        ),
    ),
    PromptDef(
        name="check-the-memo-on-the-site",
        title="Check the memo on the site",
        description="Compile a memo's latest changes and get the links to check it.",
        text=(
            f"{_LOAD} call get_skill with `compile-and-check-the-site` and follow it for my "
            "firm's memo."
        ),
    ),
]

BY_NAME: dict[str, PromptDef] = {p.name: p for p in PROMPTS}

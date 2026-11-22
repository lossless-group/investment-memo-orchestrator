"""edit_section: change a section's wording as a new version, without reopening anything."""

from __future__ import annotations

from pydantic import Field, model_validator

from .. import edits, flow
from ..edits import Edit
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace
from ._examples import drafts_walk, research_walk
from .submit_artifact import EXAMPLE_RESEARCH, MAX_CONTENT


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    section: str = Field(min_length=1, max_length=200)
    edits: list[Edit] | None = Field(default=None, min_length=1, max_length=50)
    text: str | None = Field(default=None, min_length=1, max_length=MAX_CONTENT)

    @model_validator(mode="after")
    def edits_or_text(self):
        if (self.edits is None) == (self.text is None):
            raise ValueError("give edits (old/new pairs) or text (the whole section), not both")
        return self


def revision_blocks(state: dict, key: str) -> None:
    """An open revision on the section owns its text until it closes."""
    revision = state.get("revision")
    if revision and key in revision["sections"]:
        raise ConnectorError(
            "revision_open",
            "This section is being revised; the edit would be lost under the revision.",
            next="Finish the revision with next_step and compile, or cancel_revision, then "
            "make the edit.",
            details={
                "sections": revision["sections"],
                "angle": revision["angle"],
                "opened_at": revision["opened_at"],
            },
        )


def handle(ws: Workspace, params: Input) -> dict:
    registry = load_registry()
    deal = params.deal
    with ws.lock(deal) if ws.deal_exists(deal) else _no_lock():
        state = ws.read_deal(deal)
        key = flow.resolve_section(state, params.section)
        if key is None:
            flow.raise_unknown_section(state, params.section)
        if f"draft.section:{key}" not in state["artifacts"]:
            raise ConnectorError("section_not_drafted", details={"sections": [key]})
        revision_blocks(state, key)
        # The artifact compile reads the section from: its latest version, or the
        # revised summaries for a bookend section they replace.
        target = edits.compile_source(ws, registry, state, key)
        if target is None or target not in state["artifacts"]:
            target = flow.current_section_key(registry, state, key)
        name = (flow.section_info(state, key) or {}).get("name", key)
        record = state["artifacts"][target]
        before = ws.read_text(ws.deal_rel(deal) / record["path"])
        if params.text is not None:
            if target == "enhance.summaries":
                raise ConnectorError(
                    "validation_failed",
                    f"{name} is compiled from the revised summaries, so its text can't be "
                    "replaced whole.",
                    next="Call again with edits (old/new pairs) instead of text.",
                    details={"errors": [{"field": "text", "problem": "use edits"}]},
                )
            after = params.text
        else:
            after = edits.apply_edits(before, params.edits, f"the {name} section")

        changed = after != before
        if changed:
            baseline = edits.ensure_baseline(ws, registry, state)
            record = edits.save_version(state, target, after, "edit_section")
            flow.mark(
                state, "section_edited", section=key, artifact=target, version=record["version"]
            )
            state["updated_at"] = flow.now_iso()
            with ws.transaction() as tx:
                written = [tx.write_text(path, text) for path, text in baseline.items()]
                written.append(tx.write_text(ws.deal_rel(deal) / record["path"], after))
                written.append(tx.write_json(ws.deal_rel(deal) / "deal.json", state))
            ws.history.record(
                f"edit_section: deal {deal}, section {key}, {target} v{record['version']}", written
            )
    return {
        "deal": deal,
        "section": key,
        "section_name": name,
        "artifact_id": target,
        "version": record["version"],
        "changed": changed,
        "next_hint": (
            "Saved as a new version of the section. Make any other changes the partner wants, "
            "then call compile once for the new memo."
            if changed
            else "Nothing changed: the section already reads that way."
        ),
    }


class _no_lock:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


TOOL = ToolDef(
    name="edit_section",
    summary="Change the wording of one section of a finished memo, saved as a new version of it.",
    when_to_use=(
        "the partner's change is narrative or clerical: wording, tone, order, emphasis, typos, "
        "formatting, in one section. Read the section with get_artifact first so old matches "
        "it exactly. Several calls can stack before one compile. " + edits.ROUTING
    ),
    when_not_to_use=(
        "when the change is about sources, citations or missing facts (call start_revision "
        "with start research), or when the partner says to just edit the memo they are "
        "looking at (call edit_final)."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "section",
            "string",
            "The section: its key, name, or number.",
            "02-market",
            required=True,
        ),
        InputDoc(
            "edits",
            "array of {old, new}",
            "The changes, applied in order: each old must match the section's current text "
            "exactly once, and new replaces it. Give this or text.",
            [{"old": "a large market", "new": "a $23B market (2024)"}],
        ),
        InputDoc(
            "text",
            "string",
            "The whole new section in markdown, heading and citations included. Give this or "
            "edits.",
            "## Market\n\n...",
        ),
    ],
    returns=[
        ReturnDoc("section", "The section's key."),
        ReturnDoc("section_name", "Its name as the partner sees it."),
        ReturnDoc("artifact_id", "The artifact that now holds the section's text."),
        ReturnDoc("version", "Its new version (unchanged when nothing changed)."),
        ReturnDoc("changed", "false when the section already read that way."),
        ReturnDoc("next_hint", "What to do next."),
    ],
    changes=(
        "saves a new version of the section's current text; earlier versions stay in history. "
        "Research and enhancements are not reopened and no revision opens. The compiled memo "
        "changes only when you call compile."
    ),
    duration="under a second.",
    errors=[
        "deal_not_found",
        "section_not_drafted",
        "revision_open",
        "validation_failed",
    ],
    error_next_overrides={
        "validation_failed": "An old text didn't match the section exactly once, or the section "
        "isn't in this deal: details names it. Read the section with get_artifact, fix the "
        "edit, and call again. Nothing was saved.",
        "revision_open": "The section is being revised. Finish the revision (next_step, then "
        "compile) or cancel_revision, then make the edit.",
    },
    next=(
        "make any other changes the partner asked for, then call compile once and give the "
        "partner the links."
    ),
    examples=[
        Example(
            title="Change a phrase in the first section",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                *research_walk("acme-ai", EXAMPLE_RESEARCH),
                *drafts_walk("acme-ai", EXAMPLE_RESEARCH),
            ],
            request={
                "deal": "acme-ai",
                "section": "1",
                "edits": [
                    {
                        "old": "warehouse picking robots",
                        "new": "warehouse picking robots and their software",
                    }
                ],
            },
            response={
                "ok": True,
                "deal": "acme-ai",
                "section": ANY,
                "section_name": ANY,
                "artifact_id": ANY,
                "version": 2,
                "changed": True,
                "next_hint": ANY,
                "api_version": "1",
            },
        ),
        Example(
            title="An old text that isn't in the section",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                *research_walk("acme-ai", EXAMPLE_RESEARCH),
                *drafts_walk("acme-ai", EXAMPLE_RESEARCH),
            ],
            request={
                "deal": "acme-ai",
                "section": "1",
                "edits": [{"old": "flying cars", "new": "warehouse robots"}],
            },
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "validation_failed", "details": ANY},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    rest_method="POST",
    rest_path="/v1/deals/{deal}/section-edits",
)

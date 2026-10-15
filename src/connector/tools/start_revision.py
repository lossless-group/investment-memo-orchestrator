"""start_revision: reopen sections of a finished memo so they can be redone and recompiled."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from .. import flow
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace
from ._examples import drafts_walk, research_walk
from .submit_artifact import EXAMPLE_RESEARCH


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    sections: list[str] = Field(min_length=1, max_length=50)
    angle: str = Field(min_length=10, max_length=5_000)
    start: Literal["research", "draft"] = "research"
    material_ids: list[str] = Field(default_factory=list, max_length=50)


def _keys(state: dict, values: list[str]) -> list[str]:
    keys: list[str] = []
    for value in values:
        key = flow.resolve_section(state, value)
        if key is None:
            flow.raise_unknown_section(state, value)
        if key not in keys:
            keys.append(key)
    return keys


def handle(ws: Workspace, params: Input) -> dict:
    registry = load_registry()
    deal = params.deal
    with ws.lock(deal) if ws.deal_exists(deal) else _no_lock():
        state = ws.read_deal(deal)
        open_now = state.get("revision")
        if open_now:
            raise ConnectorError(
                "revision_open",
                details={
                    "sections": open_now["sections"],
                    "angle": open_now["angle"],
                    "opened_at": open_now["opened_at"],
                },
            )
        keys = _keys(state, params.sections)
        missing = [k for k in keys if f"draft.section:{k}" not in state["artifacts"]]
        if missing:
            raise ConnectorError("section_not_drafted", details={"sections": missing})
        known = {m["material_id"] for m in state.get("materials", [])}
        unknown = [m for m in params.material_ids if m not in known]
        if unknown:
            raise ConnectorError(
                "validation_failed",
                "Those materials aren't in this deal: add them with add_materials first.",
                details={"errors": [{"field": "material_ids", "unknown": unknown}]},
            )

        revision_id = f"rev-{uuid.uuid4().hex[:10]}"
        section_steps = [
            s
            for s in flow.REOPEN_SECTION_STEPS
            if params.start == "research" or s != "research.section"
        ]
        reopen = [f"{step}:{key}" for key in keys for step in section_steps]
        reopen += list(flow.REOPEN_DEAL_STEPS)
        reopen = [k for k in reopen if registry.step(k.split(":", 1)[0]) is not None]

        # Keep the text as it stands, so cancel_revision can put it back exactly.
        baseline: dict[str, dict] = {}
        saved = {}
        folder = ws.deal_rel(deal) / "revisions" / revision_id
        for key in reopen:
            record = state["artifacts"].get(key)
            entry = {"version": 0, "seq": 0, "copy": None}
            if record is not None:
                copy = folder / f"{key.replace(':', '__')}.md"
                saved[copy] = ws.read_text(ws.deal_rel(deal) / record["path"])
                entry = {
                    "version": record["version"],
                    "seq": record.get("seq", 0),
                    "copy": copy.relative_to(ws.deal_rel(deal)).as_posix(),
                }
            baseline[key] = entry

        now = flow.now_iso()
        state["revision"] = {
            "id": revision_id,
            "sections": keys,
            "angle": params.angle.strip(),
            "start": params.start,
            "material_ids": list(dict.fromkeys(params.material_ids)),
            "opened_at": now,
            "base_label": flow.last_label(state),
            "skips_before": len(state["skips"]),
            "baseline": baseline,
        }
        state.setdefault("revisions", [])
        # New materials would make the materials brief due again; a revision's
        # materials go straight to the reopened steps instead.
        brief = flow.Instance(registry.step("materials.brief"), None)
        if (
            params.material_ids
            and not flow.is_done(brief, state)
            and not flow.is_skipped(brief, state)
        ):
            state["skips"].append(
                {
                    "step_id": "materials.brief",
                    "section": None,
                    "code": "step_skipped",
                    "reason": "Materials added for a revision go straight to the revised sections.",
                    "at": now,
                }
            )
            state["skips_reported"] = len(state["skips"])
            state["revision"]["skips_before"] = len(state["skips"])
        flow.mark(state, "revision_opened", revision_id=revision_id, sections=keys)
        state["updated_at"] = now
        with ws.transaction() as tx:
            written = [tx.write_text(path, text) for path, text in saved.items()]
            written.append(tx.write_json(ws.deal_rel(deal) / "deal.json", state))
        ws.history.record(
            f"start_revision: deal {deal}, sections {', '.join(keys)} ({params.start})", written
        )
    return {
        "deal": deal,
        "revision_id": revision_id,
        "sections": keys,
        "section_names": [(flow.section_info(state, k) or {}).get("name", k) for k in keys],
        "start": params.start,
        "reopened": reopen,
        "base_label": state["revision"]["base_label"],
        "next_hint": flow.hint(registry, state, ws),
    }


class _no_lock:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


EXAMPLE_ANGLE = "We have a 2026 market survey; weight the market sizing by it."

TOOL = ToolDef(
    name="start_revision",
    summary="Reopen one or more sections of a finished memo to revise them, then recompile.",
    when_to_use=(
        "the partner wants to change a memo that is drafted or compiled: new research to add, "
        "a different angle on a section, a correction. Read the section with get_artifact and "
        "agree with the partner which sections change and how before you call it."
    ),
    when_not_to_use=(
        "for a memo that is still being written (finish it with next_step), or to fix a step "
        "next_step has just handed you (submit it again instead)."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "sections",
            "array of strings",
            "The sections to reopen: keys, names, or numbers. Several are fine.",
            ["02-market"],
            required=True,
        ),
        InputDoc(
            "angle",
            "string",
            "What the partner wants changed and why, in their words. Every reopened step "
            "shows it to you again.",
            EXAMPLE_ANGLE,
            required=True,
        ),
        InputDoc(
            "start",
            "string",
            "research (new evidence: redo the research, then the draft) or draft (same "
            "evidence, new framing: redo only the draft). Default research.",
            "research",
        ),
        InputDoc(
            "material_ids",
            "array of strings",
            "Materials added with add_materials for this revision; they become inputs of "
            "every reopened step.",
            ["mat-0123456789abcdef"],
        ),
    ],
    returns=[
        ReturnDoc("revision_id", "The revision's id."),
        ReturnDoc("sections", "The reopened sections' keys, in the order given."),
        ReturnDoc("section_names", "Their names as the partner sees them."),
        ReturnDoc("start", "research or draft."),
        ReturnDoc(
            "reopened",
            "Every step that will be handed out again: the sections' research (when start is "
            "research), drafts, and section enhancements, then the summaries and one-pager.",
        ),
        ReturnDoc("base_label", "The memo version being revised (v0.2.3); null if never compiled."),
        ReturnDoc("next_hint", "What next_step will hand out first."),
    ],
    changes=(
        "opens a revision on the deal and keeps a copy of each reopened artifact's text so "
        "cancel_revision can restore it. Nothing is overwritten until you submit."
    ),
    duration="under a second.",
    errors=[
        "deal_not_found",
        "revision_open",
        "section_not_drafted",
        "validation_failed",
    ],
    error_next_overrides={
        "validation_failed": "A section or material id isn't in this deal: details lists the "
        "allowed sections, or the unknown material ids. Fix it and call again.",
    },
    next=(
        "call next_step and do what it hands out, as for any step: show revised research to "
        "the partner and save it approved on their say-so, then the draft, then the rest. "
        "When next_step says done, call compile for the new version."
    ),
    examples=[
        Example(
            title="Reopen the second section from research",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                *research_walk("acme-ai", EXAMPLE_RESEARCH),
                *drafts_walk("acme-ai", EXAMPLE_RESEARCH),
            ],
            request={"deal": "acme-ai", "sections": ["2"], "angle": EXAMPLE_ANGLE},
            response={
                "ok": True,
                "deal": "acme-ai",
                "revision_id": ANY,
                "sections": ANY,
                "section_names": ANY,
                "start": "research",
                "reopened": ANY,
                "base_label": None,
                "next_hint": ANY,
                "api_version": "1",
            },
        ),
        Example(
            title="A section that has no draft yet",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai", "sections": ["1"], "angle": EXAMPLE_ANGLE},
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "section_not_drafted", "details": ANY},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    rest_method="POST",
    rest_path="/v1/deals/{deal}/revisions",
)

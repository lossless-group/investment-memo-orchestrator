"""next_step: hand Claude the next unit of the method for a deal."""

from __future__ import annotations

from pydantic import Field

from .. import flow
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)


def handle(ws: Workspace, params: Input) -> dict:
    registry = load_registry()
    deal = params.deal
    with ws.lock(deal) if ws.deal_exists(deal) else _no_lock():
        state = ws.read_deal(deal)
        inst, new_skips = flow.walk(registry, state, ws)
        changed = False
        for skip in new_skips:
            state["skips"].append({**skip, "at": flow.now_iso()})
            flow.mark(state, "skipped", step=skip["step_id"], section=skip["section"])
            changed = True
        reported = state["skips"][state.get("skips_reported", 0) :]
        if reported:
            state["skips_reported"] = len(state["skips"])
            changed = True
        if inst is not None and inst.key not in state["handed_out"]:
            state["handed_out"].append(inst.key)
            flow.mark(state, "handed_out", step=inst.step.id, section=inst.section)
            changed = True
        if changed:
            state["updated_at"] = flow.now_iso()
            with ws.transaction() as tx:
                tx.write_json(ws.deal_rel(deal) / "deal.json", state)

    skipped = [
        {
            "step_id": s["step_id"],
            "section": s.get("section"),
            "code": s["code"],
            "reason": s.get("reason"),
        }
        for s in reported
    ]
    progress = flow.progress(registry, state)
    if inst is None:
        return {
            "deal": deal,
            "step_id": None,
            "done": True,
            "compile_ready": True,
            "skipped_since_last_call": skipped,
            "progress": progress,
        }
    info = flow.section_info(state, inst.section) or {}
    produces = inst.step.produces
    return {
        "deal": deal,
        "step_id": inst.step.id,
        "phase": inst.step.phase,
        "section": inst.section,
        "section_name": info.get("name"),
        "instruction": flow.render_instruction(inst, state),
        "instruction_version": inst.step.version,
        "inputs": flow.gather_inputs(registry, ws, state, inst),
        "produces": {"kind": produces.kind, "checks": produces.checks} if produces else None,
        "needs_partner": inst.step.needs_partner,
        "skipped_since_last_call": skipped,
        "progress": progress,
        "done": False,
    }


class _no_lock:
    """read_deal raises deal_not_found before any write; no lock file is made for it."""

    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


TOOL = ToolDef(
    name="next_step",
    summary="Get the next step of the memo method for a deal: what to do, what to read, and what to submit.",
    when_to_use=(
        "you are working on a deal and need to know what to do next: at the start of every "
        "conversation about a deal, and after every submit_artifact. Always do only what it says."
    ),
    when_not_to_use=(
        "to read an artifact you already have the id of: call get_artifact. To see all deals, "
        "call list_deals."
    ),
    inputs=[
        InputDoc(
            "deal",
            "string",
            "The deal's slug, from list_deals or create_new_deal.",
            "acme-ai",
            required=True,
        )
    ],
    returns=[
        ReturnDoc(
            "step_id", "The step to do, e.g. research.section; null when every step is done."
        ),
        ReturnDoc("phase", "materials, research, draft, enhance, or compile."),
        ReturnDoc("section", "The section's key for per-section steps; null for whole-deal steps."),
        ReturnDoc("section_name", "The section's name as the partner sees it."),
        ReturnDoc("instruction", "What to do, written for you. Follow it."),
        ReturnDoc("instruction_version", "The instruction's version, recorded on what you submit."),
        ReturnDoc(
            "inputs",
            "Artifacts to read, each with artifact_id, title, version, and text (long texts are cut; get_artifact pages the rest from next_offset).",
        ),
        ReturnDoc("produces", "The kind of artifact to submit and the checks it must pass."),
        ReturnDoc(
            "needs_partner",
            "true if the partner must approve the artifact before the step is done.",
        ),
        ReturnDoc(
            "skipped_since_last_call",
            "Optional steps skipped since the last call, with code and reason. Tell the partner in one line each.",
        ),
        ReturnDoc("progress", "done and total step counts for the deal."),
        ReturnDoc(
            "done", "true when every step is done or skipped; then compile_ready is true too."
        ),
    ],
    changes=(
        "records the step as handed out and records any skips; no artifact changes. Calling "
        "it again returns the same step until that step is done."
    ),
    duration="under a second.",
    errors=["deal_not_found", "validation_failed"],
    next=(
        "do what the instruction says, show the partner what it asks you to show, then call "
        "submit_artifact. When done is true, call compile."
    ),
    examples=[
        Example(
            title="The first step of a new deal",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai"},
            response={
                "ok": True,
                "deal": "acme-ai",
                "step_id": "research.section",
                "phase": "research",
                "section": "01-executive-summary",
                "section_name": "Executive Summary",
                "instruction": ANY,
                "inputs": [],
                "produces": {"kind": "research", "checks": ANY},
                "needs_partner": True,
                "skipped_since_last_call": [],
                "progress": {"done": 0, "total": ANY},
                "done": False,
                "api_version": "1",
            },
        ),
        Example(
            title="A deal that doesn't exist",
            request={"deal": "no-such-deal"},
            response={
                "ok": False,
                "error": {
                    "kind": "invalid",
                    "code": "deal_not_found",
                    "message": "No deal called 'no-such-deal' in this workspace.",
                    "next": "Call list_deals to see this firm's deals, or create_new_deal to start one.",
                },
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    rest_method="POST",
    rest_path="/v1/deals/{deal}/next-step",
)

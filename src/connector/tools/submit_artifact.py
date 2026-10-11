"""submit_artifact: save what a step produced, after its checks pass."""

from __future__ import annotations

import hashlib

from pydantic import Field, model_validator

from .. import flow
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.checks import run_checks
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace
from ._examples import research_walk

MAX_CONTENT = 500_000

#: Synthetic research used by the docs examples (and executed by CONN-DOCS-01).
EXAMPLE_RESEARCH = (
    "## Executive Summary: research\n\nAcme Robotics builds warehouse picking "
    "robots for mid-sized distributors in North America and Europe. [^1] The "
    "company reported annual recurring revenue of four million dollars in 2025, "
    "growing from one and a half million in 2024, and it counts forty customers, "
    "the largest of them a regional grocery wholesaler. [^1] [^2] The warehouse "
    "automation market was estimated at twenty-three billion dollars in 2024 and "
    "is projected to keep growing through the decade as labour costs rise. [^2]\n\n"
    "### Citations\n\n[^1]: 2025, Jan 08. [Acme Robotics raises seed round]"
    "(https://example.com/acme-seed). Example News. Published: 2025-01-08 | "
    "Updated: N/A\n\n[^2]: 2024, Nov 12. [Warehouse automation outlook]"
    "(https://example.com/outlook). Example Research. Published: 2024-11-12 | "
    "Updated: N/A\n"
)


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    step_id: str = Field(min_length=1, max_length=100)
    section: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=MAX_CONTENT)
    partner_approved: bool = False
    partner_notes: str | None = Field(default=None, max_length=20_000)
    skip: bool = False
    reason: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def content_or_skip(self):
        if self.skip:
            if self.content is not None:
                raise ValueError("a skip carries no content: send skip and reason only")
            if not (self.reason or "").strip():
                raise ValueError("a skip needs a reason, one sentence the partner can read")
        elif self.content is None:
            raise ValueError("content is required unless skip is true")
        return self


def _resolve_required(token: str, section: str | None, state: dict) -> str:
    name, _, scope = token.partition(":")
    return f"{name}:{section}" if scope == "@section" else name


def handle(ws: Workspace, params: Input) -> dict:
    registry = load_registry()
    deal = params.deal
    state = ws.read_deal(deal)  # deal_not_found before anything else
    step = registry.step(params.step_id)
    if step is None or step.produces is None:
        raise ConnectorError(
            "validation_failed",
            f"No step called '{params.step_id}' takes a submission.",
            details={
                "errors": [
                    {
                        "field": "step_id",
                        "allowed": [s.id for s in registry.steps if s.runs_on == "claude"],
                    }
                ]
            },
        )

    if params.skip and step.required:
        raise ConnectorError(
            "validation_failed",
            f"'{step.id}' is required and can't be skipped.",
            next="Do the step and submit its content; only optional steps can be skipped.",
            details={"errors": [{"field": "skip", "problem": "required step"}]},
        )

    with ws.lock(deal):
        state = ws.read_deal(deal)
        if step.scope == "section":
            section = flow.resolve_section(state, params.section)
            if section is None:
                flow.raise_unknown_section(state, params.section)
        else:
            section = None
        inst = flow.Instance(step, section)

        for token in step.requires_approved:
            needed = _resolve_required(token, section, state)
            record = state["artifacts"].get(needed)
            if not record or not record.get("partner_approved"):
                info = flow.section_info(state, section) or {}
                raise ConnectorError(
                    "research_not_approved",
                    f"The research for '{info.get('name', section)}' has not been approved by the partner.",
                )
        if step.runs_on != "claude" or inst.key not in state["handed_out"]:
            raise ConnectorError(
                "step_out_of_order",
                f"'{inst.key}' has not been handed out by next_step.",
                next=f"Call next_step for deal '{deal}' and do the step it returns.",
            )

        if params.skip:
            return _skip(ws, registry, state, inst, params.reason.strip())

        checks = run_checks(params.content, step.produces.checks)
        failures = [{"name": c["name"], "detail": c["detail"]} for c in checks if not c["passed"]]
        if failures:
            raise ConnectorError("checks_failed", details={"failures": failures})

        digest = hashlib.sha256(params.content.encode("utf-8")).hexdigest()
        approved = bool(params.partner_approved) if step.needs_partner else False
        existing = state["artifacts"].get(inst.key)
        rel = step.artifact_rel(section)
        if existing and existing["sha256"] == digest:
            if step.needs_partner and approved and not existing.get("partner_approved"):
                existing["partner_approved"] = True
                if params.partner_notes:
                    existing["partner_notes"] = params.partner_notes
                flow.mark(
                    state, "approved", step=step.id, section=section, version=existing["version"]
                )
                state["updated_at"] = flow.now_iso()
                with ws.transaction() as tx:
                    path = tx.write_json(ws.deal_rel(deal) / "deal.json", state)
                ws.history.record(f"{step.id}: {deal}/{section or '-'} approved", [path])
            version = existing["version"]
        else:
            version = (existing["version"] + 1) if existing else 1
            state["artifacts"][inst.key] = {
                "step_id": step.id,
                "section": section,
                "path": rel,
                "kind": step.produces.kind,
                "version": version,
                "sha256": digest,
                "chars": len(params.content),
                "partner_approved": approved,
                "partner_notes": params.partner_notes,
                "instruction_version": step.version,
                "saved_at": flow.now_iso(),
            }
            flow.mark(state, "saved", step=step.id, section=section, version=version)
            state["updated_at"] = flow.now_iso()
            with ws.transaction() as tx:
                artifact = tx.write_text(ws.deal_rel(deal) / rel, params.content)
                record = tx.write_json(ws.deal_rel(deal) / "deal.json", state)
            ws.history.record(
                f"{step.id}: deal {deal}, section {section or '-'}, v{version}", [artifact, record]
            )

        advanced = flow.is_done(inst, state)
        if advanced:
            next_hint = flow.hint(registry, state, ws)
        else:
            next_hint = (
                "Saved, but not approved: show the partner this research and submit it again "
                "with partner_approved: true once they approve it."
            )
    return {
        "deal": deal,
        "artifact_id": inst.key,
        "step_id": step.id,
        "section": section,
        "version": version,
        "checks": checks,
        "advanced": advanced,
        "skipped": False,
        "next_hint": next_hint,
    }


def _skip(ws: Workspace, registry, state: dict, inst: flow.Instance, reason: str) -> dict:
    """Record Claude's skip of an optional, handed-out step (called under the deal's lock)."""
    deal = state["deal"]
    if flow.is_skipped(inst, state):
        raise ConnectorError(
            "step_out_of_order",
            f"'{inst.key}' was already skipped.",
            next=f"Call next_step for deal '{deal}' and do the step it returns.",
        )
    if inst.key in state["artifacts"]:
        raise ConnectorError(
            "validation_failed",
            f"'{inst.key}' already has an artifact, so there is nothing to skip.",
            next=f"Call next_step for deal '{deal}'.",
            details={"errors": [{"field": "skip", "problem": "step already done"}]},
        )
    state["skips"].append(
        {
            "step_id": inst.step.id,
            "section": inst.section,
            "code": "step_skipped",
            "reason": reason,
            "at": flow.now_iso(),
        }
    )
    flow.mark(state, "skipped", step=inst.step.id, section=inst.section, by="claude")
    state["updated_at"] = flow.now_iso()
    with ws.transaction() as tx:
        path = tx.write_json(ws.deal_rel(deal) / "deal.json", state)
    ws.history.record(
        f"{inst.step.id}: deal {deal}, section {inst.section or '-'}, skipped", [path]
    )
    return {
        "deal": deal,
        "artifact_id": None,
        "step_id": inst.step.id,
        "section": inst.section,
        "version": None,
        "checks": [],
        "advanced": True,
        "skipped": True,
        "next_hint": flow.hint(registry, state, ws),
    }


TOOL = ToolDef(
    name="submit_artifact",
    summary="Submit the artifact a step produced; it is checked, saved as a new version, and the deal moves on.",
    when_to_use=(
        "you have finished the step next_step handed you (and, for research, the partner has "
        "seen it), or the partner approves research you saved earlier."
    ),
    when_not_to_use=(
        "for a step next_step hasn't handed out (it is refused as step_out_of_order), or to add "
        "the partner's own documents: call add_materials for those."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "step_id",
            "string",
            "The step_id next_step gave you.",
            "research.section",
            required=True,
        ),
        InputDoc(
            "section",
            "string",
            "The section key next_step gave you, for per-section steps; omit for whole-deal steps.",
            "01-executive-summary",
        ),
        InputDoc(
            "content",
            "string",
            "The artifact itself, in markdown, complete (not a diff). Required unless skip is true.",
            "## Executive Summary: research\n\n...",
        ),
        InputDoc(
            "partner_approved",
            "boolean",
            "true only when the partner has seen and approved this artifact. Research can't be drafted until it is.",
            True,
        ),
        InputDoc(
            "partner_notes",
            "string",
            "The partner's comments on the artifact, in their words.",
            "Add the 2024 revenue figure.",
        ),
        InputDoc(
            "skip",
            "boolean",
            "true to skip an optional step you can't do well with what you have, instead of "
            "submitting filler. Send it with reason and no content. Required steps can't be skipped.",
            True,
        ),
        InputDoc(
            "reason",
            "string",
            "With skip: why, in one sentence the partner can read.",
            "The section has no figures worth putting in a table.",
        ),
    ],
    returns=[
        ReturnDoc("artifact_id", "The artifact's id, for get_artifact."),
        ReturnDoc(
            "version", "The artifact's version; unchanged when identical content is resubmitted."
        ),
        ReturnDoc("checks", "Each check the artifact passed, with name, passed, and detail."),
        ReturnDoc("advanced", "true if the step is now done and next_step will move on."),
        ReturnDoc(
            "skipped",
            "true when the step was skipped (artifact_id and version are then null); the skip "
            "is listed by next_step, list_deals, and compile's report.",
        ),
        ReturnDoc("next_hint", "One line on what to do next."),
    ],
    changes=(
        "saves the artifact as a new version and records it in the deal; earlier versions stay "
        "in history. Identical content changes nothing. Failed checks save nothing. A skip "
        "records the skip on the deal and saves no artifact."
    ),
    duration="under a second.",
    errors=[
        "deal_not_found",
        "validation_failed",
        "checks_failed",
        "step_out_of_order",
        "research_not_approved",
    ],
    error_next_overrides={
        "validation_failed": "Use the step_id and section exactly as next_step returned them; "
        "send content, or skip with a reason for an optional step.",
    },
    next="call next_step.",
    examples=[
        Example(
            title="Research, approved by the partner",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                ("next_step", {"deal": "acme-ai"}),
            ],
            request={
                "deal": "acme-ai",
                "step_id": "research.section",
                "section": "01-executive-summary",
                "content": EXAMPLE_RESEARCH,
                "partner_approved": True,
            },
            response={
                "ok": True,
                "artifact_id": "research.section:01-executive-summary",
                "version": 1,
                "checks": ANY,
                "advanced": True,
                "next_hint": "Call next_step: research.section for Origins is next.",
                "api_version": "1",
            },
        ),
        Example(
            title="Drafting before the research is approved",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                ("next_step", {"deal": "acme-ai"}),
            ],
            request={
                "deal": "acme-ai",
                "step_id": "draft.section",
                "section": "01-executive-summary",
                "content": "## Executive Summary\n\nA draft.",
            },
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "research_not_approved"},
                "api_version": "1",
            },
        ),
        Example(
            title="Skipping an optional step Claude can't do well",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                *research_walk("acme-ai", EXAMPLE_RESEARCH),
            ],
            request={
                "deal": "acme-ai",
                "step_id": "research.sources",
                "skip": True,
                "reason": "The research cites too few sources to be worth consolidating.",
            },
            response={
                "ok": True,
                "artifact_id": None,
                "version": None,
                "advanced": True,
                "skipped": True,
                "next_hint": "Call next_step: draft.section for Executive Summary is next.",
                "api_version": "1",
            },
        ),
        Example(
            title="Skipping a required step",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                ("next_step", {"deal": "acme-ai"}),
            ],
            request={
                "deal": "acme-ai",
                "step_id": "research.section",
                "section": "01-executive-summary",
                "skip": True,
                "reason": "No sources found.",
            },
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "validation_failed"},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    blocks="yes, for required steps",
    rest_method="POST",
    rest_path="/v1/deals/{deal}/artifacts",
)

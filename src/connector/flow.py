"""Deal state: where a deal stands and what comes next (spec §Deal state).

The server is the only source of truth. ``deal.json`` records the deal's
sections, the artifacts saved (with version, hash, and approval), which steps
have been handed out, and the skips. "Done" is derived, never stored: a step
instance is done when its artifact exists and, if it needs the partner, is
approved.

Order: materials, then each section's research (approved), then each section's
draft, then enhancements, then compile. Because instances are walked in that
order and the first not-done one is handed out, the spec's gates hold by
construction: no draft before all research is approved, no enhancement before
every section has a draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ConnectorError
from .registry import Registry
from .registry.types import StepDef
from .workspace import Workspace, now_iso

#: Total characters of artifact text handed out as inputs by one next_step call,
#: keeping its result under Claude's 150,000-character tool-result limit.
INPUT_BUDGET = 100_000
#: get_artifact pages text at this size.
PAGE_SIZE = 100_000


@dataclass(frozen=True)
class Instance:
    step: StepDef
    section: str | None

    @property
    def key(self) -> str:
        return self.step.artifact_id(self.section)


def new_deal_state(
    deal: str,
    company: str,
    url: str | None,
    domain: str | None,
    stage: str | None,
    template: str,
    sections: list[dict],
) -> dict:
    now = now_iso()
    return {
        "deal": deal,
        "company": company,
        "url": url,
        "domain": domain,
        "stage": stage,
        "template": template,
        "sections": sections,
        "created_at": now,
        "updated_at": now,
        "materials": [],
        "artifacts": {},
        "handed_out": [],
        "skips": [],
        "skips_reported": 0,
        "compiled": None,
        "log": [{"at": now, "event": "created"}],
    }


def section_keys(state: dict) -> list[str]:
    return [s["key"] for s in state["sections"]]


def section_info(state: dict, key: str | None) -> dict | None:
    return next((s for s in state["sections"] if s["key"] == key), None)


def resolve_section(state: dict, value: str | None) -> str | None:
    """Accept a section's key, its name, or its number; return the key."""
    if value is None:
        return None
    text = str(value).strip()
    for s in state["sections"]:
        if text in (s["key"], str(s.get("number"))) or text.lower() == s["name"].lower():
            return s["key"]
    return None


def instances(registry: Registry, state: dict, *, runs_on: str = "claude") -> list[Instance]:
    out: list[Instance] = []
    for step in registry.steps:
        if step.runs_on != runs_on:
            continue
        if step.scope == "section":
            out += [Instance(step, key) for key in section_keys(state)]
        else:
            out.append(Instance(step, None))
    return out


def ready_materials(state: dict) -> list[dict]:
    return [m for m in state.get("materials", []) if m.get("status") == "ready"]


def pending_materials(state: dict) -> list[dict]:
    return [m for m in state.get("materials", []) if m.get("status") in ("queued", "pending")]


def applicable(inst: Instance, state: dict) -> bool:
    """materials.brief exists only once some material is ready."""
    if inst.step.id == "materials.brief":
        return bool(ready_materials(state))
    return True


def is_done(inst: Instance, state: dict) -> bool:
    record = state["artifacts"].get(inst.key)
    if record is None:
        return False
    return bool(record.get("partner_approved")) if inst.step.needs_partner else True


def is_skipped(inst: Instance, state: dict) -> bool:
    return any(
        s["step_id"] == inst.step.id and s.get("section") == inst.section for s in state["skips"]
    )


def is_disabled(step: StepDef, ws: Workspace) -> bool:
    """Only optional steps can be switched off; a required step always runs."""
    if step.required:
        return False
    return (not step.enabled) or step.id in ws.settings.disabled_steps


def walk(registry: Registry, state: dict, ws: Workspace) -> tuple[Instance | None, list[dict]]:
    """The first instance not yet done, and the skips that must be recorded to reach it.

    Pure: it changes nothing. ``next_step`` persists the skips; ``list_deals``
    only reads the answer.
    """
    new_skips: list[dict] = []
    for inst in instances(registry, state):
        if is_done(inst, state) or is_skipped(inst, state) or not applicable(inst, state):
            continue
        if is_disabled(inst.step, ws):
            new_skips.append(
                {
                    "step_id": inst.step.id,
                    "section": inst.section,
                    "code": "step_disabled",
                    "reason": f"{inst.step.title} is turned off on this server.",
                }
            )
            continue
        return inst, new_skips
    return None, new_skips


def progress(registry: Registry, state: dict) -> dict:
    counted = [i for i in instances(registry, state) if applicable(i, state)]
    done = sum(1 for i in counted if is_done(i, state) or is_skipped(i, state))
    compiled = 1 if state.get("compiled") else 0
    return {"done": done + compiled, "total": len(counted) + 1}


def phase_of(registry: Registry, state: dict, ws: Workspace) -> str:
    inst, _ = walk(registry, state, ws)
    if inst is not None:
        return inst.step.phase
    return "done" if state.get("compiled") else "compile"


def hint(registry: Registry, state: dict, ws: Workspace) -> str:
    inst, _ = walk(registry, state, ws)
    if inst is None:
        return "Every step is done or skipped: call compile."
    where = ""
    if inst.section:
        info = section_info(state, inst.section) or {}
        where = f" for {info.get('name', inst.section)}"
    return f"Call next_step: {inst.step.id}{where} is next."


# ------------------------------------------------------------------ rendering


def render_instruction(inst: Instance, state: dict) -> str:
    info = section_info(state, inst.section) or {}
    target = info.get("target_length") or {}
    words = target.get("ideal_words") or target.get("max_words") or 400
    questions = info.get("guiding_questions") or []
    values = {
        "company": state["company"],
        "deal": state["deal"],
        "url": state.get("url") or "the company's website (not given)",
        "stage": state.get("stage") or "not given",
        "step_id": inst.step.id,
        "section_key": inst.section or "",
        "section_name": info.get("name", ""),
        "section_description": info.get("description") or "(No description in the template.)",
        "guiding_questions": "\n".join(f"- {q}" for q in questions) or "- (None listed.)",
        "target_words": str(words),
    }
    text = inst.step.instruction_text()
    for name, value in values.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text


def current_section_key(registry: Registry, state: dict, section: str) -> str | None:
    """The artifact holding a section's text as it now stands.

    Every section-scoped step whose artifact kind is ``section`` (the draft, and
    the enhancements that revise it: tables, citations, fact check) produces a
    whole new version of the section; the one latest in registry order wins.
    Read as ``section.current:@section`` or ``section.current:*``; compile uses it too.
    """
    current = None
    for step in registry.steps:
        if step.scope == "section" and step.produces and step.produces.kind == "section":
            key = step.artifact_id(section)
            if key in state["artifacts"]:
                current = key
    return current


def _artifact_text(ws: Workspace, state: dict, key: str) -> str | None:
    record = state["artifacts"].get(key)
    if record is None:
        return None
    return ws.read_text(f"deals/{state['deal']}/{record['path']}")


def gather_inputs(registry: Registry, ws: Workspace, state: dict, inst: Instance) -> list[dict]:
    """Resolve the step's ``reads`` (plus its own earlier submission) to texts."""
    wanted: list[tuple[str, str]] = []  # (id, title)
    for read in inst.step.reads:
        name, _, scope = read.partition(":")
        if name == "materials":
            for m in ready_materials(state):
                wanted.append((f"material:{m['material_id']}", f"Material: {m.get('kind')}"))
            continue
        if name == "section.current":
            keys = section_keys(state) if scope == "*" else [inst.section]
            for key in keys:
                current = current_section_key(registry, state, key)
                if current is not None:
                    info = section_info(state, key) or {}
                    wanted.append((current, f"Current text: {info.get('name', key)}"))
            continue
        step = registry.step(name)
        if step is None:
            continue
        if step.scope == "section":
            keys = section_keys(state) if scope == "*" else [inst.section]
            for key in keys:
                info = section_info(state, key) or {}
                wanted.append((step.artifact_id(key), f"{step.title}: {info.get('name', key)}"))
        else:
            wanted.append((step.artifact_id(None), step.title))
    own = inst.key
    if own in state["artifacts"] and own not in [w[0] for w in wanted]:
        wanted.append((own, "Your previous submission for this step"))

    found: list[dict] = []
    for artifact_id, title in wanted:
        if artifact_id.startswith("material:"):
            text = ws.read_text(f"deals/{state['deal']}/materials/{artifact_id[9:]}.md")
            version = 1
        else:
            text = _artifact_text(ws, state, artifact_id)
            if text is None:
                continue
            version = state["artifacts"][artifact_id]["version"]
        found.append({"artifact_id": artifact_id, "title": title, "version": version, "text": text})
    return _fit(found)


def _fit(items: list[dict]) -> list[dict]:
    """Share INPUT_BUDGET fairly; a cut input says where to resume with get_artifact."""
    remaining = INPUT_BUDGET
    for index, item in enumerate(items):
        share = remaining // (len(items) - index)
        text = item["text"]
        if len(text) > share:
            item["text"] = text[:share]
            item["truncated"] = True
            item["next_offset"] = share
            item["total_chars"] = len(text)
        remaining -= len(item["text"])
    return items


def require_deal(ws: Workspace, deal: str) -> dict:
    return ws.read_deal(deal)


def mark(state: dict, event: str, **fields: Any) -> None:
    state.setdefault("log", []).append({"at": now_iso(), "event": event, **fields})


def raise_unknown_section(state: dict, value: Any) -> None:
    raise ConnectorError(
        "validation_failed",
        f"No section '{value}' in this deal's template.",
        details={"errors": [{"field": "section", "allowed": section_keys(state)}]},
    )

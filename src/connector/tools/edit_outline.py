"""edit_outline: change the outline one memo uses, or (asked for) the firm's outline.

Decided 2026-11-20: an outline change made while working on a memo applies to
that memo only. By default the deal gets its own pinned copy of its outline
(``<template>--<deal>``, in the firm's outlines, written once from the sections
the deal has), the edits apply there, and the deal's ``template`` points at it.
With ``apply_to: firm`` the firm's outline itself changes (a MemoPop outline is
first copied into the firm's), no deal changes, and the reply lists the deals on
it so Claude can take the change to each one with the partner, one at a time.

Section keys never change: every section in an outline this writes carries an
explicit ``filename``, so inserting one doesn't renumber the others' keys. A
section that is added has no research yet, so ``next_step`` hands it out; a
section whose description or questions changed is marked (``outline_seq``) so
its research and draft count as not done until they are saved again.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import edits, flow
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..templates import NAME_RE, load_sections, outline_path, section_key
from ..workspace import Workspace


class OutlineEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_section", "update_section", "move_section", "remove_section"]
    section: str | None = Field(default=None, max_length=200)
    after: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)
    guiding_questions: list[str] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def fits_op(self):
        if self.op == "add_section" and not self.name:
            raise ValueError("add_section needs a name")
        if self.op != "add_section" and not self.section:
            raise ValueError(f"{self.op} needs section (its key, name, or number)")
        if self.op == "update_section" and (
            self.name is None and self.description is None and self.guiding_questions is None
        ):
            raise ValueError("update_section needs a name, description, or guiding_questions")
        return self


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    edits: list[OutlineEdit] = Field(min_length=1, max_length=30)
    apply_to: Literal["deal", "firm"] = "deal"


def outline_rel(name: str) -> Path:
    return Path("templates") / "outlines" / f"{name}.yaml"


def _with_keys(raw: list[dict]) -> list[dict]:
    """Give every section an explicit filename (its key), so later inserts keep keys."""
    out = []
    for index, section in enumerate(raw):
        section = dict(section)
        section["filename"] = f"{section_key(section, index)}.md"
        out.append(section)
    return out


def _key(section: dict) -> str:
    return str(section["filename"])[:-3]


def _find(raw: list[dict], value: str, index: int, field: str) -> int:
    text = str(value).strip()
    for pos, section in enumerate(raw):
        if text in (_key(section), str(pos + 1), str(section.get("number"))) or (
            text.lower() == str(section.get("name", "")).lower()
        ):
            return pos
    raise ConnectorError(
        "validation_failed",
        f"Edit {index}: no section '{value}' in this outline.",
        details={
            "errors": [{"field": f"edits.{index}.{field}", "allowed": [_key(s) for s in raw]}]
        },
    )


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "section"


def apply_outline_edits(raw: list[dict], edits: list[OutlineEdit]) -> tuple[list[dict], dict]:
    """The edited section list, and which keys were added, changed, removed, or need work."""
    raw = _with_keys(raw)
    result: dict[str, list[str]] = {"added": [], "changed": [], "removed": [], "needs_work": []}
    for index, edit in enumerate(edits):
        if edit.op == "add_section":
            pos = _find(raw, edit.after, index, "after") + 1 if edit.after else len(raw)
            taken = {_key(s) for s in raw}
            key = f"{pos + 1:02d}-{_slug(edit.name)}"
            n = 2
            while key in taken:
                key, n = f"{pos + 1:02d}-{_slug(edit.name)}-{n}", n + 1
            section = {
                "name": edit.name.strip(),
                "filename": f"{key}.md",
                "description": (edit.description or "").strip(),
                "guiding_questions": [q.strip() for q in edit.guiding_questions or [] if q.strip()],
            }
            raw.insert(pos, section)
            result["added"].append(key)
        elif edit.op == "update_section":
            pos = _find(raw, edit.section, index, "section")
            section = dict(raw[pos])
            if edit.name is not None:
                section["name"] = edit.name.strip()
            content = False
            if edit.description is not None:
                content = (
                    content
                    or edit.description.strip() != str(section.get("description") or "").strip()
                )
                section["description"] = edit.description.strip()
            if edit.guiding_questions is not None:
                questions = [q.strip() for q in edit.guiding_questions if q.strip()]
                content = content or questions != section.get("guiding_questions")
                section["guiding_questions"] = questions
            raw[pos] = section
            key = _key(section)
            result["changed"].append(key)
            if content and key not in result["added"]:
                result["needs_work"].append(key)
        elif edit.op == "move_section":
            section = raw.pop(_find(raw, edit.section, index, "section"))
            pos = _find(raw, edit.after, index, "after") + 1 if edit.after else 0
            raw.insert(pos, section)
            result["changed"].append(_key(section))
        else:
            pos = _find(raw, edit.section, index, "section")
            if len(raw) == 1:
                raise ConnectorError(
                    "validation_failed",
                    f"Edit {index}: an outline needs at least one section.",
                    details={"errors": [{"field": f"edits.{index}", "problem": "last section"}]},
                )
            result["removed"].append(_key(raw.pop(pos)))
    for number, section in enumerate(raw, start=1):
        section["number"] = number
    for name in ("added", "changed", "needs_work"):
        result[name] = [k for k in dict.fromkeys(result[name]) if k not in result["removed"]]
    return raw, result


def _from_state(sections: list[dict]) -> list[dict]:
    """The deal's sections as outline YAML entries."""
    out = []
    for s in sections:
        entry = {
            "number": s.get("number"),
            "name": s["name"],
            "filename": f"{s['key']}.md",
            "description": s.get("description") or "",
            "guiding_questions": list(s.get("guiding_questions") or []),
        }
        if s.get("target_length"):
            entry["target_length"] = s["target_length"]
        out.append(entry)
    return out


def _dump(metadata: dict, sections: list[dict]) -> str:
    return yaml.safe_dump(
        {"metadata": metadata, "sections": sections},
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


def _pinned_name(base: str, deal: str) -> str:
    name = f"{base}--{deal}"
    if len(name) > 100:
        name = f"{base[: 100 - len(deal) - 2]}--{deal}"[:100]
    return name if NAME_RE.match(name) else f"deal--{deal}"[:100]


def _firm(ws: Workspace, state: dict, params: Input) -> dict:
    base = state.get("outline_pinned_from") or state["template"]
    path, source = outline_path(ws, base)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw, result = apply_outline_edits(list(data.get("sections") or []), params.edits)
    metadata = dict(data.get("metadata") or {})
    with ws.lock("_outlines"):
        with ws.transaction() as tx:
            written = [tx.write_text(outline_rel(base), _dump(metadata, raw))]
        ws.history.record(
            f"edit_outline: firm outline {base} ({_summary(result)}), "
            f"{'copied from MemoPop, ' if source == 'memopop' else ''}no deal changed",
            written,
        )
    using = []
    for slug in ws.deal_slugs():
        other = ws.read_deal(slug)
        if other.get("template") == base:
            using.append({"deal": slug, "company": other.get("company")})
    return {
        "deal": params.deal,
        "template": base,
        "apply_to": "firm",
        **{k: result[k] for k in ("added", "changed", "removed")},
        "sections": [{"key": s["key"], "name": s["name"]} for s in load_sections(ws, base)],
        "deals_using": using,
        "next_hint": (
            "No deal changed. Ask the partner which of these memos should get the change, then "
            "for each one, one at a time, call edit_outline with that deal and the same edits."
        ),
    }


def _summary(result: dict) -> str:
    parts = [f"{k} {', '.join(result[k])}" for k in ("added", "changed", "removed") if result[k]]
    return "; ".join(parts) or "no change"


def handle(ws: Workspace, params: Input) -> dict:
    deal = params.deal
    if params.apply_to == "firm":
        return _firm(ws, ws.read_deal(deal), params)
    registry = load_registry()
    with ws.lock(deal) if ws.deal_exists(deal) else _no_lock():
        state = ws.read_deal(deal)
        pinned_from = state.get("outline_pinned_from")
        if pinned_from:
            name, base = state["template"], pinned_from
        else:
            base = state["template"]
            name = _pinned_name(base, deal)
        try:
            path, _ = outline_path(ws, name if pinned_from else base)
            metadata = dict((yaml.safe_load(path.read_text("utf-8")) or {}).get("metadata") or {})
        except ConnectorError:
            metadata = {}
        metadata.update(pinned_for=deal, pinned_from=base)
        raw, result = apply_outline_edits(_from_state(state["sections"]), params.edits)

        old = {s["key"]: s for s in state["sections"]}
        with ws.transaction() as tx:
            written = [tx.write_text(outline_rel(name), _dump(metadata, raw))]
        sections = load_sections(ws, name)
        for section in sections:
            if old.get(section["key"], {}).get("outline_seq"):
                section["outline_seq"] = old[section["key"]]["outline_seq"]
            if section["key"] in result["needs_work"]:
                section["outline_seq"] = flow.next_seq(state)
        state["sections"] = sections
        state["template"] = name
        state["outline_pinned_from"] = base
        flow.mark(state, "outline_edited", template=name, **result)
        state["updated_at"] = flow.now_iso()
        with ws.transaction() as tx:
            written.append(tx.write_json(ws.deal_rel(deal) / "deal.json", state))
        ws.history.record(
            f"edit_outline: deal {deal}, outline {name} pinned from {base} ({_summary(result)})",
            written,
        )
        next_hint = flow.hint(registry, state, ws)
    return {
        "deal": deal,
        "template": name,
        "apply_to": "deal",
        "pinned_from": base,
        **{k: result[k] for k in ("added", "changed", "removed")},
        "needs_work": result["needs_work"],
        "sections": [{"key": s["key"], "name": s["name"]} for s in sections],
        "next_hint": next_hint,
    }


class _no_lock:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


TOOL = ToolDef(
    name="edit_outline",
    summary="Change the outline one memo uses (add, rename, reword, or remove sections).",
    when_to_use=(
        "the partner wants this memo to have a section it lacks, lose one, or cover different "
        "questions. It changes this memo only; take the change to other memos only when the "
        "partner asks, one memo at a time, or with apply_to firm when they want the firm's "
        "outline itself changed. " + edits.ROUTING
    ),
    when_not_to_use=(
        "to change a section's wording (call edit_section) or its facts (call start_revision)."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "edits",
            "array of objects",
            "The changes, in order. op is add_section (name, optional after, description, "
            "guiding_questions), update_section (section, and any of name, description, "
            "guiding_questions), move_section (section, and after; no after puts it first), or "
            "remove_section (section). section and after take a key, name, or number.",
            [
                {
                    "op": "add_section",
                    "name": "Competition",
                    "after": "Market",
                    "guiding_questions": ["Who are the three closest competitors?"],
                }
            ],
            required=True,
        ),
        InputDoc(
            "apply_to",
            "string",
            "deal (the default: this memo only, on its own pinned copy of the outline) or firm "
            "(the firm's outline itself; no deal changes, and the deals on it are listed).",
            "deal",
        ),
    ],
    returns=[
        ReturnDoc("template", "The outline changed: the deal's pinned copy, or the firm's."),
        ReturnDoc("apply_to", "deal or firm."),
        ReturnDoc("pinned_from", "With apply_to deal: the outline the pinned copy came from."),
        ReturnDoc("added", "Keys of the sections added."),
        ReturnDoc(
            "changed",
            "Keys of the sections renamed, moved, or whose description or questions changed.",
        ),
        ReturnDoc("removed", "Keys of the sections removed (their texts stay in history)."),
        ReturnDoc(
            "needs_work",
            "With apply_to deal: sections whose description or questions changed, which "
            "next_step hands out again for research and a draft.",
        ),
        ReturnDoc("sections", "The outline's sections now, key and name, in order."),
        ReturnDoc("deals_using", "With apply_to firm: the deals on that outline, none changed."),
        ReturnDoc("next_hint", "What to do next."),
    ],
    changes=(
        "with apply_to deal, writes the deal's pinned outline (copied once from its outline) and "
        "points the deal at it; other deals and the firm's outline stay as they are. With "
        "apply_to firm, writes the firm's outline and changes no deal. Both are recorded in "
        "the firm's history."
    ),
    duration="under a second.",
    errors=["deal_not_found", "template_not_found", "validation_failed"],
    error_next_overrides={
        "validation_failed": "An edit names a section the outline doesn't have, or is missing "
        "what its op needs: details says which. Fix it and call again. Nothing was saved.",
    },
    next=(
        "call next_step: an added section, or one whose questions changed, is handed out for "
        "research and then a draft; then compile. With apply_to firm, ask the partner which "
        "listed memos should change and call edit_outline for each, one at a time."
    ),
    examples=[
        Example(
            title="Add a section to one memo's outline",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={
                "deal": "acme-ai",
                "edits": [
                    {
                        "op": "add_section",
                        "name": "Regulation",
                        "description": "The rules that govern warehouse robots.",
                        "guiding_questions": ["Which safety standards apply?"],
                    }
                ],
            },
            response={
                "ok": True,
                "deal": "acme-ai",
                "template": ANY,
                "apply_to": "deal",
                "pinned_from": ANY,
                "added": ANY,
                "changed": [],
                "removed": [],
                "needs_work": [],
                "sections": ANY,
                "next_hint": ANY,
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    rest_method="POST",
    rest_path="/v1/deals/{deal}/outline-edits",
)

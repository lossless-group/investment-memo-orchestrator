"""edit_final: edit the compiled memo itself, then carry each change back to its section.

The partner sees the change at once: the edited final becomes the next compiled
version (label bumped, exports re-rendered). Each edit is then made again in the
artifact compile reads its section from, as a new version, so the next compile
reproduces the final instead of overwriting it. The pairing is kept in the
deal's ``final_edits``.

Where an edit goes is found from the final's level-2 headings, matched to the
sections the way compile assembled them (see :mod:`..edits`). An edit that
spans two sections, falls outside every section, or whose text the section
doesn't have as written (a numbered citation key in a section is its source's hex
key in the final) is
refused as ``edit_not_placed``, and nothing is saved.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .. import edits, flow
from ..edits import Edit
from ..compile import links
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.types import Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..site import site_url_for
from ..workspace import Workspace
from . import compile as compile_tool
from .edit_section import revision_blocks


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    edits: list[Edit] = Field(min_length=1, max_length=50)
    facts_changed: bool = False
    formats: list[Literal["html", "pdf"]] | None = Field(default=None, min_length=1)


def _not_placed(index: int, edit: Edit, reason: str) -> ConnectorError:
    return ConnectorError(
        "edit_not_placed",
        f"Edit {index} can't be placed: {reason}",
        details={"edit": index, "old": edit.old, "reason": reason},
    )


def _place(final: str, index: int, edit: Edit) -> str:
    """The normalised heading of the one section block ``edit.old`` falls inside."""
    count = final.count(edit.old)
    if count != 1:
        problem = "matches nothing" if count == 0 else f"matches {count} times"
        raise ConnectorError(
            "validation_failed",
            f"Edit {index}: its old text {problem} in the final draft; it must match exactly "
            "once.",
            next="Copy old exactly from the latest compiled memo (get_artifact with "
            "compile.assemble), with enough words around it to match once. Nothing was saved.",
            details={
                "errors": [
                    {
                        "field": f"edits.{index}.old",
                        "edit": index,
                        "old": edit.old,
                        "matches": count,
                    }
                ]
            },
        )
    start = final.index(edit.old)
    end = start + len(edit.old)
    for key, (_heading, _block, lo, hi) in edits.section_blocks(final).items():
        if lo <= start < hi:
            if end > hi:
                raise _not_placed(index, edit, "it runs from one section into the next.")
            if start < lo + len(_block.split("\n", 1)[0]):
                raise _not_placed(index, edit, "it changes a section heading.")
            return key
    raise _not_placed(
        index,
        edit,
        "it is outside every section (the title, the contents, or the consolidated citations).",
    )


def handle(ws: Workspace, params: Input) -> dict:
    registry = load_registry()
    deal = params.deal
    formats = list(dict.fromkeys(params.formats or ["html", "pdf"]))
    with ws.lock(deal) if ws.deal_exists(deal) else _no_lock():
        state = ws.read_deal(deal)
        final = edits.read_final(ws, state)
        if final is None:
            raise ConnectorError(
                "artifact_not_found",
                "This deal has no compiled memo to edit yet.",
                next="Call compile first (or edit_section to change a section's text).",
            )
        ctx = edits.gathered(ws, registry, state)
        by_heading = edits.heading_map(state, ctx)

        working = final
        texts: dict[str, str] = {}  # artifact id -> its text with the edits so far
        carried: list[dict] = []
        for index, edit in enumerate(params.edits):
            heading = _place(working, index, edit)
            section = by_heading.get(heading)
            if section is None:
                raise _not_placed(index, edit, "its heading matches none of the deal's sections.")
            revision_blocks(state, section["key"])
            target = section["from"]
            text = texts[target] if target in texts else ctx.text(target)
            if text is None or text.count(edit.old) != 1:
                raise _not_placed(
                    index,
                    edit,
                    f"the {section['name']} section doesn't have that text exactly once as "
                    "written (a citation key in the final can differ from the section's).",
                )
            texts[target] = text.replace(edit.old, edit.new, 1)
            working = working.replace(edit.old, edit.new, 1)
            carried.append(
                {
                    "edit": index,
                    "section": section["key"],
                    "section_name": section["name"],
                    "artifact_id": target,
                }
            )

        compiled = state["compiled"]
        baseline = edits.ensure_baseline(ws, registry, state)
        from_sections = edits.assemble(ws, registry, state, overrides=texts)
        version = compiled["version"] + 1
        label = flow.bump_label(flow.last_label(state))
        keys = compile_tool.export(ws, state, version, working, formats, {})

        saved: dict[str, dict] = {}
        for target, text in texts.items():
            saved[target] = edits.save_version(state, target, text, "edit_final")
        for item in carried:
            item["version"] = saved[item["artifact_id"]]["version"]

        now = flow.now_iso()
        digest = edits.sha(working)
        state["compiled"] = {
            "version": version,
            "label": label,
            "sha256": digest,
            "keys": keys,
            "at": now,
            "from_sections": edits.baseline_rel(version),
            "edited_final": True,
        }
        state["artifacts"]["compile.assemble"] = {
            **state["artifacts"]["compile.assemble"],
            "path": f"compiled/{version}/memo.md",
            "version": version,
            "sha256": digest,
            "chars": len(working),
            "partner_notes": "Edited in the final draft with edit_final.",
            "saved_at": now,
        }
        state.setdefault("final_edits", []).append(
            {
                "at": now,
                "version": version,
                "label": label,
                "facts_changed": params.facts_changed,
                "edits": [
                    {
                        **item,
                        "old": params.edits[item["edit"]].old,
                        "new": params.edits[item["edit"]].new,
                    }
                    for item in carried
                ],
            }
        )
        flow.mark(state, "final_edited", version=version, label=label, edits=len(carried))
        state["updated_at"] = now
        rel = ws.deal_rel(deal)
        with ws.transaction() as tx:
            written = [tx.write_text(path, text) for path, text in baseline.items()]
            written.append(tx.write_text(rel / "compiled" / str(version) / "memo.md", working))
            written.append(tx.write_text(rel / edits.baseline_rel(version), from_sections))
            for target, text in texts.items():
                written.append(tx.write_text(rel / state["artifacts"][target]["path"], text))
            written.append(tx.write_json(rel / "deal.json", state))
        ws.history.record(f"edit_final: deal {deal}, v{version} ({label})", written)

    sections = list(dict.fromkeys(item["section_name"] for item in carried))
    if params.facts_changed:
        next_hint = (
            f"The memo now reads as the partner asked, and {', '.join(sections)} carries the "
            "change. A fact or source changed, so update the research to match: call "
            "start_revision for those sections with start research and the change as the "
            "angle, then next_step, then compile."
        )
    else:
        next_hint = (
            f"The memo now reads as the partner asked, and {', '.join(sections)} carries the "
            "change, so the next compile keeps it. Give the partner the links."
        )
    body = {
        "deal": deal,
        "version": version,
        "label": label,
        "html_url": links.signed_url(ws, keys["html"]) if "html" in keys else None,
        "pdf_url": links.signed_url(ws, keys["pdf"]) if "pdf" in keys else None,
        "carried": carried,
        "next_hint": next_hint,
    }
    site_url = site_url_for(ws, deal)
    if site_url:
        body["site_url"] = site_url
    return body


class _no_lock:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


TOOL = ToolDef(
    name="edit_final",
    summary="Edit the compiled memo itself so the partner sees it now, and carry it to its section.",
    when_to_use=(
        "the partner says to just edit the memo they are looking at, or objects to the process: "
        "edit the final draft and don't argue. Also to carry back a change compile reported as "
        "final_has_untracked_edits. " + edits.ROUTING
    ),
    when_not_to_use=(
        "for a memo that was never compiled (call edit_section), or when the partner wants the "
        "research fixed (call start_revision with start research)."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "edits",
            "array of {old, new}",
            "The changes, applied in order to the latest compiled memo: each old must match it "
            "exactly once and sit inside one section's text, without citation numbers.",
            [{"old": "a large market", "new": "a $23B market (2024)"}],
            required=True,
        ),
        InputDoc(
            "facts_changed",
            "boolean",
            "true when the change alters a fact or a source, so the research should change "
            "too; next_hint then says how.",
            False,
        ),
        InputDoc(
            "formats",
            "array",
            "Which exports to render for the new version: html, pdf, or both (the default).",
            ["html"],
        ),
    ],
    returns=[
        ReturnDoc("version", "The new compiled version, holding the edited memo."),
        ReturnDoc("label", "Its label, the next patch (v0.2.3 becomes v0.2.4)."),
        ReturnDoc("html_url", "A signed link to the edited HTML memo, valid for seven days."),
        ReturnDoc("pdf_url", "A signed link to the edited PDF; null if it wasn't asked for."),
        ReturnDoc(
            "carried",
            "Per edit: its index, the section it was carried to (key and name), and the "
            "artifact and version that now hold it.",
        ),
        ReturnDoc("site_url", "Only when the firm's site has a page for this deal."),
        ReturnDoc("next_hint", "What to do next, including the research when facts changed."),
    ],
    changes=(
        "writes the edited memo as the next compiled version with its exports, saves a new "
        "version of each section it changed, and records the pairing in the deal. Nothing is "
        "saved unless every edit places."
    ),
    duration="a few seconds; the PDF takes longest.",
    errors=[
        "deal_not_found",
        "artifact_not_found",
        "edit_not_placed",
        "revision_open",
        "validation_failed",
        "service_unavailable",
    ],
    error_next_overrides={
        "artifact_not_found": "The deal has no compiled memo yet: call compile first, or use "
        "edit_section on the section.",
        "validation_failed": "An old text didn't match the compiled memo exactly once: details "
        "names it. Read the memo with get_artifact (compile.assemble), fix the edit, and call "
        "again. Nothing was saved.",
        "revision_open": "The section is being revised. Finish the revision (next_step, then "
        "compile) or cancel_revision, then make the edit.",
        "service_unavailable": 'The PDF export is down: call again with formats ["html"], and '
        "tell the partner the PDF will follow.",
    },
    next=(
        "give the partner the links and say in one line which section now carries the change; "
        "if facts_changed, follow next_hint to update the research."
    ),
    examples=[
        Example(
            title="Editing a memo that was never compiled",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={
                "deal": "acme-ai",
                "edits": [{"old": "warehouse picking robots", "new": "picking robots"}],
            },
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "artifact_not_found"},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    rest_method="POST",
    rest_path="/v1/deals/{deal}/final-edits",
)

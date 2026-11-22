"""What the edit tools share: applying old/new edits, saving a new artifact version,
and telling a compiled final apart from what its sections produce.

The compile guard (``untracked_differences``) works on three texts:

- **F**, the latest compiled final, as it is stored now (``compiled/<v>/memo.md``);
- **B**, what the deal's sections produced for that version. compile and
  edit_final keep it beside the final as ``compiled/<v>/from-sections.md``. A
  memo imported from a local run has none; the first tool that changes a
  section after the import (edit_section, edit_final, start_revision) writes it
  from the sections as they were, and until then they are rebuilt;
- **C**, what the sections produce now.

The texts are compared section by section, on each level-2 heading's block with
citation numbers, citation lists, and whitespace normalised away. A section
whose block in F equals B's was not edited in the final. One that equals C's
was edited, then carried back into its section (by edit_section or edit_final).
Anything else is untracked: compiling would overwrite it. The citation
definitions are compared the same way, as one more block.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from . import flow
from .compile import pipeline
from .errors import ConnectorError
from .registry import Registry
from .workspace import Workspace

log = logging.getLogger("memopop.connector.edits")

#: The file beside each compiled final holding what the sections produced for it.
FROM_SECTIONS = "from-sections.md"
#: Characters shown either side of where two texts first differ.
EXCERPT = 160


class Edit(BaseModel):
    """One change: ``old`` must match the text exactly once; ``new`` replaces it."""

    model_config = ConfigDict(extra="forbid")

    old: str = Field(min_length=1, max_length=20_000)
    new: str = Field(max_length=20_000)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_edits(text: str, edits: list[Edit], where: str) -> str:
    """Apply ``edits`` in order; each ``old`` must match exactly once, or nothing applies."""
    for index, edit in enumerate(edits):
        count = text.count(edit.old)
        if count != 1:
            problem = "matches nothing" if count == 0 else f"matches {count} times"
            raise ConnectorError(
                "validation_failed",
                f"Edit {index}: its old text {problem} in {where}; it must match exactly once.",
                next="Copy old exactly from the current text (get_artifact reads it), with enough "
                "words around it to match once, and call again. Nothing was saved.",
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
        text = text.replace(edit.old, edit.new, 1)
    return text


def save_version(state: dict, key: str, text: str, by: str) -> dict:
    """Record ``text`` as the next version of artifact ``key`` in ``state`` (not written yet)."""
    record = dict(state["artifacts"][key])
    record.update(
        version=record["version"] + 1,
        sha256=sha(text),
        chars=len(text),
        saved_at=flow.now_iso(),
        edited_by=by,
    )
    record["seq"] = flow.next_seq(state)
    state["artifacts"][key] = record
    return record


# ------------------------------------------------------------------ assembling


@dataclass
class _Overlay(pipeline.Context):
    """A compile context that reads some artifacts from memory instead of the workspace."""

    overrides: dict[str, str] = field(default_factory=dict)

    def text(self, artifact_id: str) -> str | None:
        if artifact_id in self.overrides:
            return self.overrides[artifact_id]
        return super().text(artifact_id)


def gathered(
    ws: Workspace, registry: Registry, state: dict, overrides: dict[str, str] | None = None
) -> pipeline.Context:
    """The compile context after gathering sections: each section's text and its source."""
    ctx = _Overlay(ws=ws, registry=registry, state=state, overrides=dict(overrides or {}))
    pipeline.gather_sections(ctx)
    return ctx


def assemble(
    ws: Workspace, registry: Registry, state: dict, overrides: dict[str, str] | None = None
) -> str:
    """The memo the sections produce now (with ``overrides`` in place of saved texts)."""
    ctx = _Overlay(ws=ws, registry=registry, state=state, overrides=dict(overrides or {}))
    pipeline.assemble(ctx)
    return ctx.memo


def compile_source(ws: Workspace, registry: Registry, state: dict, key: str) -> str | None:
    """The artifact compile takes ``key``'s text from (a draft, an enhancement, the summaries)."""
    try:
        ctx = gathered(ws, registry, state)
    except ConnectorError:  # some section has no draft yet: compile can't run either
        return None
    return next((s["from"] for s in ctx.sections if s["key"] == key), None)


# ------------------------------------------------------------------ blocks and headings

_NUMBERING = re.compile(r"^(?:\d+|[ivxlc]+)[.)]\s*", re.IGNORECASE)
_NOT_SECTIONS = re.compile(r"^(table of )?contents$|^citations$|^sources$|^references$")
_DEFINITION = re.compile(r"^\[\^[^\]\s]+\]:[ \t]*(.*)$", re.MULTILINE)
_MARKER = re.compile(r"\[\^[^\]\s]+\]")


def norm_heading(heading: str) -> str:
    text = " ".join(heading.replace("*", "").split()).strip().lower()
    return _NUMBERING.sub("", text).strip(" :.-")


def _norm_body(text: str) -> str:
    text = _DEFINITION.sub("", text)
    text = re.sub(r"^#{2,4}\s*Citations\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^-{3,}\s*$", "", text, flags=re.MULTILINE)
    text = _MARKER.sub("[^]", text)
    return " ".join(text.split())


def section_blocks(memo: str) -> dict[str, tuple[str, str, int, int]]:
    """Each level-2 section of a memo: normalised heading -> (heading, block, start, end).

    The consolidated citation list, a contents block, and anything before the
    first level-2 heading (the title) are not sections.
    """
    body, _ = pipeline._split_citations(memo)
    marks = list(pipeline._H2.finditer(body))
    out: dict[str, tuple[str, str, int, int]] = {}
    for i, mark in enumerate(marks):
        heading = mark.group(1).strip()
        key = norm_heading(heading)
        if _NOT_SECTIONS.match(key):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out.setdefault(key, (heading, body[mark.start() : end], mark.start(), end))
    return out


def heading_map(state: dict, ctx: pipeline.Context) -> dict[str, dict]:
    """Normalised heading -> the gathered section it belongs to (by its heading, or its name)."""
    out: dict[str, dict] = {}
    for section in ctx.sections:
        first = pipeline._H2.search(section["text"])
        if first:
            out.setdefault(norm_heading(first.group(1)), section)
        out.setdefault(norm_heading(section["name"]), section)
    return out


def _definitions(memo: str) -> list[str]:
    return sorted({" ".join(m.group(1).split()) for m in _DEFINITION.finditer(memo)})


def _excerpts(final: str, sections: str) -> tuple[str, str]:
    """Where two normalised texts first differ, a window of each."""
    at = next(
        (i for i, (a, b) in enumerate(zip(final, sections, strict=False)) if a != b),
        min(len(final), len(sections)),
    )
    lo = max(0, at - EXCERPT)
    return final[lo : at + EXCERPT], sections[lo : at + EXCERPT]


# ------------------------------------------------------------------ the guard


def final_record(state: dict) -> dict | None:
    if not state.get("compiled"):
        return None
    return state["artifacts"].get("compile.assemble")


def read_final(ws: Workspace, state: dict) -> str | None:
    record = final_record(state)
    if record is None:
        return None
    path = ws.root / ws.deal_rel(state["deal"]) / record["path"]
    return path.read_text(encoding="utf-8") if path.is_file() else None


def baseline_rel(version: int) -> str:
    return f"compiled/{version}/{FROM_SECTIONS}"


def ensure_baseline(ws: Workspace, registry: Registry, state: dict) -> dict[Path, str]:
    """Before a section changes: keep what the sections produce for the latest compiled
    version, if it isn't kept yet (a memo imported from a local run).

    Returns the files to write in the caller's transaction, and records the path
    in ``state``. Best effort: if the sections can't be assembled, nothing is kept
    and the guard rebuilds them later.
    """
    compiled = state.get("compiled")
    if not compiled or compiled.get("from_sections") or final_record(state) is None:
        return {}
    try:
        memo = assemble(ws, registry, state)
    except Exception:  # never block an edit on this
        log.exception("could not keep the sections' memo for %s", state["deal"])
        return {}
    rel = baseline_rel(compiled["version"])
    compiled["from_sections"] = rel
    return {ws.deal_rel(state["deal"]) / rel: memo}


def untracked_differences(ws: Workspace, registry: Registry, state: dict) -> list[dict]:
    """Text in the latest compiled final that isn't traceable to a section (see module doc)."""
    final = read_final(ws, state)
    if final is None:
        return []
    compiled = state["compiled"]
    baseline = None
    if compiled.get("from_sections"):
        path = ws.root / ws.deal_rel(state["deal"]) / compiled["from_sections"]
        if path.is_file():
            baseline = path.read_text(encoding="utf-8")
            if baseline == final:
                return []
    ctx = gathered(ws, registry, state)
    current = assemble(ws, registry, state)
    if baseline is None:
        baseline = current
    by_heading = heading_map(state, ctx)

    f_blocks, b_blocks, c_blocks = (section_blocks(t) for t in (final, baseline, current))
    out: list[dict] = []
    for key in [*f_blocks, *[k for k in b_blocks if k not in f_blocks]]:
        f = _norm_body(f_blocks[key][1]) if key in f_blocks else None
        b = _norm_body(b_blocks[key][1]) if key in b_blocks else None
        c = _norm_body(c_blocks[key][1]) if key in c_blocks else None
        if f == b or f == c:
            continue
        heading = (f_blocks.get(key) or b_blocks.get(key))[0]
        section = by_heading.get(key)
        if f is None:
            change, shown = "missing_from_final", ("", b or "")
        elif b is None and c is None:
            change, shown = "only_in_final", (f[: 2 * EXCERPT], "")
        else:
            change, shown = "edited", _excerpts(f, b if b is not None else c or "")
        out.append(
            {
                "section": section["key"] if section else None,
                "name": heading,
                "change": change,
                "final": shown[0],
                "sections": shown[1],
            }
        )
    f_defs, b_defs, c_defs = (_definitions(t) for t in (final, baseline, current))
    if f_defs not in (b_defs, c_defs):
        out.append(
            {
                "section": None,
                "name": "Citations",
                "change": "edited",
                "final": "\n".join(d for d in f_defs if d not in b_defs)[: 2 * EXCERPT],
                "sections": "\n".join(d for d in b_defs if d not in f_defs)[: 2 * EXCERPT],
            }
        )
    return out


#: Where a partner's change goes (spec, "Where an edit goes"). Carried by the docs
#: of start_revision, edit_section, edit_final, edit_outline and compile.
ROUTING = (
    "Where a change goes, decided from what the partner says, without asking them which "
    "layer: a source, citation, missing fact or weak research goes in the section's "
    "research (start_revision with start research; the section is then rewritten from it, "
    "then compile); wording, tone, order, emphasis, typos or formatting go in the section "
    "(edit_section, then compile once every change is in); \"just edit the memo I'm looking "
    'at" goes in the final draft now (edit_final, which carries it back to its section); a '
    "change to which sections the memo has or what they cover goes in this memo's outline "
    "(edit_outline). Say in one line where the change went."
)

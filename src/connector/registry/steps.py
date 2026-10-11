"""Load step definitions from ``src/connector/steps/*.md``.

Frontmatter fields (spec §The step registry): ``id``, ``title``, ``phase``,
``scope``, ``required``, ``runs_on``, ``reads``, ``produces`` (``kind`` and
``checks``), ``needs_partner``, ``source_agent``, ``enabled``, plus ``order``
(registry order; steps are handed out by it), ``version`` (the instruction's
version, recorded on every artifact the step produces), ``path`` (where the
artifact is saved inside the deal), and ``requires_approved``.

The body is the instruction, with ``{{placeholders}}`` filled per deal.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .types import Produces, StepDef

STEPS_DIR = Path(__file__).resolve().parent.parent / "steps"

PHASES = ["materials", "research", "draft", "enhance", "compile"]


def _split(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("step file has no frontmatter")
    end = text.find("\n---", 3)
    meta = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4 :].lstrip("\n")
    return meta, body


def load_step(path: Path) -> StepDef:
    meta, body = _split(path.read_text(encoding="utf-8"))
    produces = meta.get("produces")
    step = StepDef(
        id=str(meta["id"]),
        title=str(meta.get("title") or meta["id"]),
        phase=str(meta["phase"]),
        scope=str(meta["scope"]),
        required=bool(meta.get("required", False)),
        runs_on=str(meta["runs_on"]),
        reads=[str(r) for r in meta.get("reads") or []],
        produces=(
            Produces(str(produces["kind"]), dict(produces.get("checks") or {}))
            if produces
            else None
        ),
        needs_partner=bool(meta.get("needs_partner", False)),
        source_agent=str(meta.get("source_agent") or ""),
        enabled=bool(meta.get("enabled", True)),
        order=int(meta["order"]),
        version=str(meta.get("version", "1")),
        path=meta.get("path"),
        requires_approved=[str(r) for r in meta.get("requires_approved") or []],
        instruction_path=path,
        _body=body,
    )
    if step.phase not in PHASES or step.scope not in ("deal", "section"):
        raise ValueError(f"{path.name}: bad phase or scope")
    if step.runs_on not in ("claude", "server"):
        raise ValueError(f"{path.name}: runs_on must be claude or server")
    return step


def load_steps() -> list[StepDef]:
    steps = [load_step(p) for p in sorted(STEPS_DIR.glob("*.md"))]
    ids = [s.id for s in steps]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate step id")
    orders = [s.order for s in steps]
    if len(orders) != len(set(orders)):
        raise ValueError("two steps share an order")
    return sorted(steps, key=lambda s: s.order)

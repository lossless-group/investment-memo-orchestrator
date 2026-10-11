"""Memo templates: the outlines in ``templates/outlines/*.yaml``.

A firm's own outlines (``<firm>/templates/outlines/<name>.yaml``) win over
MemoPop's. The connector reads only what it needs from an outline (the section
list and each section's guidance), straight from the YAML, so it never goes
through code that resolves paths against a hardcoded ``io/``.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .errors import ConnectorError
from .workspace import Workspace

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


def _dirs(ws: Workspace) -> list[Path]:
    return [ws.root / "templates" / "outlines", Path(ws.settings.templates_dir)]


def available_templates(ws: Workspace) -> list[str]:
    names: set[str] = set()
    for d in _dirs(ws):
        if d.is_dir():
            names.update(p.stem for p in d.glob("*.yaml") if NAME_RE.match(p.stem))
    return sorted(names)


def default_template(ws: Workspace) -> str:
    return str(ws.firm_config().get("default_template") or ws.settings.default_template)


def _section_key(section: dict, index: int) -> str:
    filename = str(section.get("filename") or "")
    if filename.endswith(".md"):
        return filename[:-3]
    name = re.sub(r"[^a-z0-9]+", "-", str(section.get("name", "")).lower()).strip("-")
    return f"{index + 1:02d}-{name or 'section'}"


def load_sections(ws: Workspace, name: str) -> list[dict]:
    """The template's sections, in order, or ``template_not_found``."""
    path = None
    if NAME_RE.match(name or ""):
        for d in _dirs(ws):
            candidate = d / f"{name}.yaml"
            if candidate.is_file():
                path = candidate
                break
    if path is None:
        raise ConnectorError(
            "template_not_found",
            f"No memo template called '{name}'." if NAME_RE.match(name or "") else None,
            details={"available": available_templates(ws)},
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sections = []
    for index, section in enumerate(data.get("sections") or []):
        questions = section.get("guiding_questions") or []
        if isinstance(questions, dict):  # some outlines group questions by dimension
            questions = [q for group in questions.values() for q in (group or [])]
        sections.append(
            {
                "key": _section_key(section, index),
                "name": str(section.get("name") or f"Section {index + 1}"),
                "number": section.get("number", index + 1),
                "description": str(section.get("description") or "").strip(),
                "guiding_questions": [str(q) for q in questions if isinstance(q, str)],
                "target_length": section.get("target_length") or {},
            }
        )
    if not sections:
        raise ConnectorError("template_not_found", f"Template '{name}' has no sections.")
    return sections

"""Load the playbooks served by ``list_skills`` and ``get_skill``.

Each skill is one markdown file in ``src/connector/skills/``: frontmatter with
``name`` (the file's stem) and a one-line ``description``, then the playbook.
They live in git, so an edit reaches every partner's Claude on its next call,
the way event-hog serves its skills (spec §How partners get the method).

Read from disk on every call rather than cached: the files are small, and a
running server picks up an edited playbook without a restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    text: str


def _load(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"skill {path.name} has no frontmatter")
    end = text.find("\n---", 3)
    meta = yaml.safe_load(text[4:end]) or {}
    name = str(meta.get("name") or path.stem)
    if name != path.stem:
        raise ValueError(f"skill {path.name} is named {name!r}; name it after its file")
    description = " ".join(str(meta.get("description") or "").split())
    if not description:
        raise ValueError(f"skill {path.name} has no description")
    return Skill(name=name, description=description, text=text[end + 4 :].strip() + "\n")


def load_skills(directory: Path = SKILLS_DIR) -> dict[str, Skill]:
    """Every skill, keyed and ordered by name."""
    return {s.name: s for s in sorted(map(_load, directory.glob("*.md")), key=lambda s: s.name)}

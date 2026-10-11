"""Setup walks for docs examples that need a deal part-way through the method.

Docs examples run on a fresh firm with MemoPop's default outline
(CONN-DOCS-01), so a walk has one step per section of that outline. Sections
are named by number, which ``submit_artifact`` accepts as well as keys.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from ..config import ConnectorSettings

Call = tuple[str, dict[str, Any]]


@lru_cache(maxsize=1)
def default_section_count() -> int:
    settings = ConnectorSettings()
    path = settings.templates_dir / f"{settings.default_template}.yaml"
    return len(yaml.safe_load(path.read_text(encoding="utf-8"))["sections"])


def research_walk(deal: str, content: str) -> list[Call]:
    """Every section's research, submitted approved, then next_step (research.sources)."""
    calls: list[Call] = []
    for number in range(1, default_section_count() + 1):
        calls.append(("next_step", {"deal": deal}))
        calls.append(
            (
                "submit_artifact",
                {
                    "deal": deal,
                    "step_id": "research.section",
                    "section": str(number),
                    "content": content,
                    "partner_approved": True,
                },
            )
        )
    calls.append(("next_step", {"deal": deal}))
    return calls


def drafts_walk(deal: str, content: str) -> list[Call]:
    """Skip research.sources, then draft every section."""
    calls: list[Call] = [
        (
            "submit_artifact",
            {
                "deal": deal,
                "step_id": "research.sources",
                "skip": True,
                "reason": "The example cites too few sources to consolidate.",
            },
        )
    ]
    for number in range(1, default_section_count() + 1):
        calls.append(("next_step", {"deal": deal}))
        calls.append(
            (
                "submit_artifact",
                {
                    "deal": deal,
                    "step_id": "draft.section",
                    "section": str(number),
                    "content": content,
                },
            )
        )
    return calls

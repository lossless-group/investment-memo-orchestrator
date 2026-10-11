"""The registry: every tool and every step, declared once.

- Tools: one module per tool in ``src/connector/tools/``, each exporting
  ``TOOL``; :data:`.tools.TOOL_MODULES` lists them, one line per tool.
- Steps: one markdown file per step in ``src/connector/steps/``; its
  frontmatter is the definition and its body the instruction. Adding a step is
  adding a file.

Transports, docs, and lint all read from :func:`load_registry`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .steps import load_steps
from .tools import load_tools
from .types import StepDef, ToolDef


@dataclass(frozen=True)
class Registry:
    tools: dict[str, ToolDef]
    steps: list[StepDef]

    def step(self, step_id: str) -> StepDef | None:
        return next((s for s in self.steps if s.id == step_id), None)


@lru_cache(maxsize=1)
def load_registry() -> Registry:
    return Registry(tools=load_tools(), steps=load_steps())


__all__ = ["Registry", "load_registry"]

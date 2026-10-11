"""Which tool modules make up the registry. One line per tool.

Each module in ``src/connector/tools/`` exports ``TOOL`` (a ``ToolDef``). A phase
that implements a stubbed tool edits only that tool's module; a phase that adds
a tool adds its module and one line here.
"""

from __future__ import annotations

from importlib import import_module

from .types import ToolDef

TOOL_MODULES = [
    "list_deals",
    "create_new_deal",
    "add_materials",
    "next_step",
    "submit_artifact",
    "get_artifact",
    "save_snapshot",
    "compile",
]


def load_tools() -> dict[str, ToolDef]:
    tools: dict[str, ToolDef] = {}
    for module_name in TOOL_MODULES:
        tool = import_module(f"src.connector.tools.{module_name}").TOOL
        if tool.name in tools:
            raise ValueError(f"Tool {tool.name} registered twice")
        tools[tool.name] = tool
    return tools

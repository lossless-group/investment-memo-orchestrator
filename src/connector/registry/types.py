"""Tool and step definitions: the single source for transports, docs, and lint.

A :class:`ToolDef` carries the tool's behaviour (input model, handler, hints,
REST route) *and* its docs entry (spec §Each tool's docs entry). MCP tool
descriptions, OpenAPI, ``llms.txt``, and ``/docs`` are all generated from it, so
the docs cannot drift from the code.

A :class:`StepDef` is one unit of the method, loaded from a markdown file in
``src/connector/steps/`` whose frontmatter is the definition and whose body is
the instruction Claude receives.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..errors import CATALOGUE

#: In a docs example's response, matches any value.
ANY = "<any>"


class ToolInput(BaseModel):
    """Base for every tool's input. ``firm`` is accepted everywhere.

    Strings are not stripped here: artifact ``content`` must be saved byte for
    byte. Inputs that should be trimmed (a company name) say so themselves.
    """

    model_config = ConfigDict(extra="forbid")

    firm: str | None = Field(default=None, max_length=80)


@dataclass(frozen=True)
class InputDoc:
    name: str
    type: str
    description: str
    example: Any
    required: bool = False


@dataclass(frozen=True)
class ReturnDoc:
    name: str
    description: str


@dataclass(frozen=True)
class Example:
    """A documented call, executed by CONN-DOCS-01.

    ``setup`` is a list of ``(tool, request)`` calls made first on a fresh firm.
    ``response`` is matched as a subset of the real response (see :func:`matches`).
    """

    title: str
    request: dict[str, Any]
    response: dict[str, Any]
    setup: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


FIRM_INPUT = InputDoc(
    "firm",
    "string",
    "The firm to act for. Omit it unless the partner belongs to more than one firm; "
    "a sign-in can only act for its own firms.",
    "hypernova",
)

# Shown on every tool's docs; the transport can return these on any call.
COMMON_ERRORS = ["unauthenticated", "forbidden_firm", "validation_failed"]
DOWN_ERRORS = ["storage_unavailable", "service_unavailable", "internal_error"]


@dataclass
class ToolDef:
    name: str
    summary: str
    when_to_use: str
    when_not_to_use: str
    inputs: list[InputDoc]
    returns: list[ReturnDoc]
    changes: str
    duration: str
    errors: list[str]
    next: str
    examples: list[Example]
    input_model: type[ToolInput]
    handler: Callable[..., dict[str, Any]]
    read_only: bool
    destructive: bool
    rest_method: str
    rest_path: str
    #: "no", "yes", or "yes, for required steps" (spec §The tools, "Blocks?").
    blocks: str = "no"
    #: Tool-specific `next` text for a code, where the catalogue's default is too general.
    error_next_overrides: dict[str, str] = field(default_factory=dict)
    implemented: bool = True

    def __post_init__(self) -> None:
        if not any(i.name == "firm" for i in self.inputs):
            self.inputs = [*self.inputs, FIRM_INPUT]
        for code in [*COMMON_ERRORS, *DOWN_ERRORS]:
            if code not in self.errors:
                self.errors = [*self.errors, code]

    def error_next(self, code: str) -> str:
        return self.error_next_overrides.get(code) or CATALOGUE[code].next

    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for the input, with each property's docs attached and refs inlined."""
        schema = _inline_refs(self.input_model.model_json_schema())
        _strip_titles(schema)
        docs = {i.name: i for i in self.inputs}
        for name, prop in schema.get("properties", {}).items():
            if name in docs:
                prop["description"] = docs[name].description
                prop["examples"] = [docs[name].example]
        schema["additionalProperties"] = False
        return schema

    def docs_markdown(self, heading: str = "###") -> str:
        """The full docs entry as markdown (llms-full.txt and the MCP description)."""
        lines = [f"{heading} {self.name}", "", self.summary, ""]
        lines += [
            f"**Use when** {self.when_to_use}",
            "",
            f"**Don't use** {self.when_not_to_use}",
            "",
        ]
        lines.append("**Inputs.**")
        for item in self.inputs:
            req = "required" if item.required else "optional"
            lines.append(
                f"- `{item.name}` ({item.type}, {req}): {item.description} "
                f"Example: `{_short(item.example)}`."
            )
        lines += ["", "**Returns.**"]
        lines += [f"- `{r.name}`: {r.description}" for r in self.returns]
        lines += ["", f"**Changes** {self.changes}", "", f"**Takes** {self.duration}", ""]
        lines.append("**Errors.**")
        for code in self.errors:
            lines.append(f"- `{code}` ({CATALOGUE[code].kind}): {self.error_next(code)}")
        lines += ["", f"**Next:** {self.next}", ""]
        return "\n".join(lines)

    def mcp_description(self) -> str:
        """Summary first, then when to use it, when not to, and what comes next."""
        errors = "; ".join(f"{c}: {self.error_next(c)}" for c in self.errors)
        return "\n\n".join(
            [
                self.summary,
                f"Use when {self.when_to_use}",
                f"Don't use {self.when_not_to_use}",
                f"Changes: {self.changes} Takes: {self.duration}",
                f"Errors: {errors}",
                f"Next: {self.next}",
            ]
        )


@dataclass(frozen=True)
class Produces:
    kind: str
    checks: dict[str, Any]


@dataclass
class StepDef:
    id: str
    title: str
    phase: str
    scope: str
    required: bool
    runs_on: str
    reads: list[str]
    produces: Produces | None
    needs_partner: bool
    source_agent: str
    enabled: bool
    order: int
    version: str
    #: Artifact path relative to the deal folder; ``{section}`` is replaced.
    path: str | None
    #: Artifacts that must be partner-approved before this step can be submitted.
    requires_approved: list[str]
    instruction_path: Path | None
    _body: str = ""

    def instruction_text(self) -> str:
        return self._body

    def artifact_id(self, section: str | None) -> str:
        return f"{self.id}:{section}" if section else self.id

    def artifact_rel(self, section: str | None) -> str:
        assert self.path, f"step {self.id} produces no artifact"
        return self.path.replace("{section}", section or "deal")


def matches(expected: Any, actual: Any) -> bool:
    """Is ``actual`` what the docs example documents?

    Dicts match as subsets (the documented keys must be present and match);
    lists must have the same length and match element-wise; ``"<any>"`` matches
    anything; everything else must be equal.
    """
    if expected == ANY:
        return True
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and matches(v, actual[k]) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(matches(e, a) for e, a in zip(expected, actual, strict=True))
        )
    return expected == actual


def _short(value: Any) -> str:
    import json

    text = json.dumps(value) if not isinstance(value, str) else value
    return text if len(text) <= 80 else text[:77] + "..."


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = copy.deepcopy(defs[ref.split("/")[-1]])
                rest = {k: v for k, v in node.items() if k != "$ref"}
                return walk({**target, **rest})
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def _strip_titles(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("title", None)
        props = node.get("properties")
        for key, value in node.items():
            if key == "properties" and isinstance(props, dict):
                for prop in props.values():
                    _strip_titles(prop)
            else:
                _strip_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_titles(item)

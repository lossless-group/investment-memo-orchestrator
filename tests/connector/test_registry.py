"""Layer 1: registry lint (CONN-REG-01 to CONN-REG-05)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.connector.errors import CATALOGUE

from .conftest import REPO

EIGHT_TOOLS = {
    "list_deals",
    "create_new_deal",
    "add_materials",
    "next_step",
    "submit_artifact",
    "get_artifact",
    "save_snapshot",
    "compile",
}

#: (readOnlyHint, destructiveHint) per tool, from the spec's tools table.
HINTS = {
    "list_deals": (True, False),
    "create_new_deal": (False, False),
    "add_materials": (False, False),
    "next_step": (False, False),
    "submit_artifact": (False, False),
    "get_artifact": (True, False),
    "save_snapshot": (False, False),
    "compile": (False, False),
}

#: The starting codes from the spec's Errors section, with their kinds.
SPEC_CODES = {
    "down": ["service_unavailable", "storage_unavailable", "timeout", "internal_error"],
    "invalid": [
        "unauthenticated",
        "forbidden_firm",
        "deal_not_found",
        "artifact_not_found",
        "template_not_found",
        "validation_failed",
        "checks_failed",
        "step_out_of_order",
        "research_not_approved",
        "material_too_large",
        "link_unreachable",
        "unsupported_version",
    ],
    "skipped": ["step_disabled", "step_failed", "material_unreadable"],
}

#: The spec's "First mapping from today's workflow".
SPEC_STEPS = {
    "materials.extract": ("materials", "deal", "server", True),
    "materials.brief": ("materials", "deal", "claude", False),
    "research.section": ("research", "section", "claude", True),
    "research.sources": ("research", "deal", "claude", False),
    "draft.section": ("draft", "section", "claude", True),
    "enhance.tables": ("enhance", "section", "claude", False),
    "enhance.diagrams": ("enhance", "deal", "claude", False),
    "enhance.citations": ("enhance", "section", "claude", False),
    "enhance.fact_check": ("enhance", "section", "claude", False),
    "enhance.scorecard": ("enhance", "deal", "claude", False),
    "enhance.summaries": ("enhance", "deal", "claude", False),
    "enhance.one_pager": ("enhance", "deal", "claude", False),
    "compile.assemble": ("compile", "deal", "server", True),
}


@pytest.mark.spec("CONN-REG-01")
def test_exactly_the_eight_tools_are_registered(registry):
    assert set(registry.tools) == EIGHT_TOOLS
    for name, tool in registry.tools.items():
        assert tool.name == name


@pytest.mark.spec("CONN-REG-02")
def test_every_tool_fills_every_docs_field(registry):
    for tool in registry.tools.values():
        where = f"tool {tool.name}"
        for field in ("summary", "when_to_use", "when_not_to_use", "changes", "duration", "next"):
            value = getattr(tool, field)
            assert isinstance(value, str) and value.strip(), f"{where}: {field} is empty"
        assert len(tool.summary) <= 200, f"{where}: summary is {len(tool.summary)} chars"
        assert "\n" not in tool.summary.strip(), f"{where}: summary is more than one line"
        assert tool.summary.rstrip().endswith("."), f"{where}: summary is not a sentence"
        assert tool.returns, f"{where}: returns is empty"
        for ret in tool.returns:
            assert ret.name and ret.description.strip(), f"{where}: return {ret.name}"
        assert tool.errors, f"{where}: errors is empty"
        assert tool.examples, f"{where}: no example"
        for example in tool.examples:
            assert example.title and isinstance(example.request, dict), where
            assert isinstance(example.response, dict), where

        # Every input in the schema is documented, and nothing undocumented exists.
        schema_props = set(tool.input_schema()["properties"])
        documented = {i.name for i in tool.inputs}
        assert schema_props == documented, f"{where}: schema {schema_props} vs docs {documented}"
        required = set(tool.input_schema().get("required", []))
        for item in tool.inputs:
            assert item.description.strip(), f"{where}: input {item.name} has no meaning"
            assert item.type.strip(), f"{where}: input {item.name} has no type"
            assert item.required == (item.name in required), f"{where}: {item.name} required"
            assert item.example is not None, f"{where}: input {item.name} has no example"


@pytest.mark.spec("CONN-REG-03")
def test_every_listed_error_code_exists_and_is_documented(registry):
    for kind, codes in SPEC_CODES.items():
        for code in codes:
            assert code in CATALOGUE, f"spec code {code} missing from the catalogue"
            assert CATALOGUE[code].kind == kind, f"{code} should be {kind}"
    for code, spec in CATALOGUE.items():
        assert spec.kind in {"down", "invalid", "skipped"}, code
        for field in ("message", "next", "docs"):
            assert getattr(spec, field).strip(), f"{code}: {field} is empty"
    for tool in registry.tools.values():
        for code in tool.errors:
            assert code in CATALOGUE, f"{tool.name} lists unknown code {code}"
            assert tool.error_next(code).strip(), f"{tool.name}: no next text for {code}"


@pytest.mark.spec("CONN-REG-04")
def test_every_tool_declares_both_hints_matching_the_spec(registry, mcp):
    for name, (read_only, destructive) in HINTS.items():
        tool = registry.tools[name]
        assert tool.read_only is read_only, name
        assert tool.destructive is destructive, name
    listed = {t["name"]: t for t in mcp.list_tools()}
    for name, (read_only, destructive) in HINTS.items():
        annotations = listed[name].get("annotations") or {}
        assert annotations.get("readOnlyHint") is read_only, name
        assert annotations.get("destructiveHint") is destructive, name


@pytest.mark.spec("CONN-REG-05")
def test_every_claude_step_has_instruction_reads_produces_and_source_agent(registry):
    claude_steps = [s for s in registry.steps if s.runs_on == "claude"]
    assert claude_steps
    for step in claude_steps:
        where = f"step {step.id}"
        assert step.instruction_path is not None, where
        path = Path(step.instruction_path)
        assert path.is_file(), f"{where}: no instruction file at {path}"
        assert step.instruction_text().strip(), f"{where}: instruction is empty"
        assert "submit_artifact" in step.instruction_text(), f"{where}: no submit ending"
        assert step.reads, f"{where}: reads is empty"
        assert step.produces and step.produces.kind, f"{where}: produces has no kind"
        assert step.produces.checks, f"{where}: produces has no checks"
        assert step.source_agent, f"{where}: no source_agent"
        agent = REPO / step.source_agent
        assert agent.exists(), f"{where}: source agent {step.source_agent} does not exist"
        assert agent.resolve().is_relative_to((REPO / "src" / "agents").resolve()), where


def test_steps_match_the_specs_first_mapping(registry):
    """Not a spec ID: guards the registry against drifting from §First mapping."""
    got = {s.id: (s.phase, s.scope, s.runs_on, s.required) for s in registry.steps}
    assert got == SPEC_STEPS


def test_step_checks_are_all_known(registry):
    """Not a spec ID: a typo in a check name would otherwise never run."""
    from src.connector.registry.checks import CHECKS

    for step in registry.steps:
        if step.produces:
            for name in step.produces.checks:
                assert name in CHECKS, f"{step.id}: unknown check {name}"

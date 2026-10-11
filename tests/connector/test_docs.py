"""Layer 2: the docs are generated from the registry, and their examples run
(CONN-DOCS-01 to CONN-DOCS-05)."""

from __future__ import annotations

import html

import pytest
from openapi_spec_validator import validate

from src.connector.config import ConnectorSettings
from src.connector.errors import CATALOGUE, ConnectorError, envelope
from src.connector.registry.types import matches
from src.connector.tools import invoke
from src.connector.workspace import open_workspace, provision_firm

from .conftest import REST_ROUTES


def _run(tool: str, request: dict, ws) -> dict:
    try:
        return invoke(tool, request, ws)
    except ConnectorError as err:
        return envelope(err)


@pytest.mark.spec("CONN-DOCS-01")
def test_every_docs_example_runs_and_matches(registry, tmp_path_factory):
    ran = 0
    for tool in registry.tools.values():
        for example in tool.examples:
            # A fresh firm per example, with the default template, so examples
            # document what a new firm actually sees.
            base = tmp_path_factory.mktemp(f"example-{tool.name}")
            provision_firm(base / "firms", "example-firm")
            settings = ConnectorSettings(
                io_root=base / "firms",
                bucket_backend="local",
                bucket_local_root=base / "buckets",
                static_keys={},
            )
            ws = open_workspace(settings, "example-firm")
            for setup_tool, setup_request in example.setup:
                _run(setup_tool, setup_request, ws)
            got = _run(tool.name, example.request, ws)
            assert matches(example.response, got), (
                f"{tool.name} example {example.title!r}\n"
                f"documented: {example.response}\n"
                f"got: {got}"
            )
            ran += 1
    assert ran >= len(registry.tools)


def test_matches_is_strict_where_it_should_be():
    """Not a spec ID: the example matcher must not pass everything."""
    assert matches({"a": 1}, {"a": 1, "b": 2})
    assert not matches({"a": 1}, {"a": 2})
    assert not matches({"a": 1}, {"b": 1})
    assert matches({"a": "<any>"}, {"a": [1, 2]})
    assert not matches({"a": [1]}, {"a": [1, 2]})
    assert matches({"a": [{"x": 1}]}, {"a": [{"x": 1, "y": 2}]})


@pytest.mark.spec("CONN-DOCS-02")
def test_openapi_validates_and_has_an_operation_per_tool(client, registry):
    response = client.get("/v1/openapi.json")
    assert response.status_code == 200
    doc = response.json()
    assert doc["openapi"].startswith("3.1")
    validate(doc)
    for name, (method, path) in REST_ROUTES.items():
        path = path.replace("{artifact_id}", "{id}")
        operation = doc["paths"][path][method.lower()]
        tool = registry.tools[name]
        assert operation["operationId"] == name
        assert operation["summary"] == tool.summary
        description = operation["description"]
        for text in (tool.when_to_use, tool.when_not_to_use, tool.changes, tool.next):
            assert text.strip() in description, f"{name}: docs text missing from OpenAPI"
        for code in tool.errors:
            assert code in description, f"{name}: error {code} missing from OpenAPI"
        assert operation.get("security"), f"{name}: no security requirement"


@pytest.mark.spec("CONN-DOCS-03")
def test_llms_txt_lists_every_tool_and_full_has_every_entry(client, registry):
    short = client.get("/llms.txt")
    assert short.status_code == 200
    assert short.headers["content-type"].startswith("text/plain")
    assert short.text.startswith("# MemoPop")
    for tool in registry.tools.values():
        line = next((ln for ln in short.text.splitlines() if f"[{tool.name}]" in ln), None)
        assert line is not None, f"{tool.name} missing from llms.txt"
        assert tool.summary in line

    full = client.get("/llms-full.txt")
    assert full.status_code == 200
    for tool in registry.tools.values():
        for text in (
            tool.summary,
            tool.when_to_use,
            tool.when_not_to_use,
            tool.changes,
            tool.duration,
            tool.next,
        ):
            assert text.strip() in full.text, f"{tool.name}: {text[:40]!r} missing"
        for item in tool.inputs:
            assert f"`{item.name}`" in full.text
        for code in tool.errors:
            assert f"`{code}`" in full.text
    for code in CATALOGUE:
        assert f"`{code}`" in full.text


@pytest.mark.spec("CONN-DOCS-04")
def test_docs_pages_render_every_tool_and_every_error(client, registry):
    page = client.get("/docs")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    for tool in registry.tools.values():
        assert f'id="{tool.name}"' in page.text
        assert html.escape(tool.summary) in page.text
        assert html.escape(tool.when_to_use.strip()) in page.text

    errors = client.get("/docs/errors")
    assert errors.status_code == 200
    assert errors.headers["content-type"].startswith("text/html")
    for code, spec in CATALOGUE.items():
        assert f'id="{code}"' in errors.text
        assert html.escape(spec.next) in errors.text
        assert html.escape(spec.docs.strip()) in errors.text

    changelog = client.get("/docs/changelog")
    assert changelog.status_code == 200
    assert changelog.headers["content-type"].startswith("text/html")


@pytest.mark.spec("CONN-DOCS-05")
def test_mcp_tool_listing_carries_docs_and_schemas(mcp, registry):
    listed = {t["name"]: t for t in mcp.list_tools()}
    assert set(listed) == set(registry.tools)
    for name, tool in registry.tools.items():
        entry = listed[name]
        description = entry["description"]
        assert description.startswith(tool.summary), name
        for text in (tool.when_to_use, tool.when_not_to_use, tool.next):
            assert text.strip() in description, f"{name}: {text[:40]!r} missing"
        schema = entry["inputSchema"]
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {i.name for i in tool.inputs}
        for item in tool.inputs:
            assert schema["properties"][item.name].get("description"), f"{name}.{item.name}"

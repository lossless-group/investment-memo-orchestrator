"""The full flow: the scripted client takes fixture-co from creation to compile
(CONN-FLOW-01 over MCP, CONN-FLOW-02 over REST)."""

from __future__ import annotations

import pytest

from src.connector.registry import load_registry

from .conftest import SECTIONS, Mcp, key_headers
from .fake_claude import FakeClaude, OverMcp, OverRest
from .fixtures import canned


def _expected_steps() -> list[tuple[str, str | None]]:
    """Every Claude step fixture-co needs, in the order the server must hand them out."""
    out: list[tuple[str, str | None]] = []
    for step in load_registry().steps:
        if step.runs_on != "claude" or step.id == "materials.brief":  # no materials yet
            continue
        out += [(step.id, s) for s in SECTIONS] if step.scope == "section" else [(step.id, None)]
    return out


def _check_compiled_memo(client, walk) -> None:
    compiled = walk.compiled
    report = compiled["report"]
    assert [s["key"] for s in report["sections"]] == SECTIONS
    assert report["skipped"] == [] and report["not_run"] == []
    assert sorted(report["enhancements_run"]) == sorted(
        s.id for s in load_registry().steps if s.phase == "enhance"
    )

    page = client.get(compiled["html_url"])
    assert page.status_code == 200
    html = page.text
    for name, _ in canned.SECTIONS.values():
        assert f">{name}<" in html, f"section {name} missing from the compiled memo"
    assert canned.TABLE_MARKER in html, "the tables enhancement is not in the memo"
    assert canned.SUMMARY_MARKER in html, "the revised summary is not in the memo"
    assert f">{canned.SCORECARD_MARKER}<" in html, "the scorecard is not in the memo"
    assert "data:image/svg+xml" in html, "the market-sizing diagram is not in the memo"
    assert "Table of Contents" in html
    pdf = client.get(compiled["pdf_url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def _shape(walk) -> list[dict]:
    """The transcript, which must be the same whichever transport carried it."""
    return walk.transcript


@pytest.mark.spec("CONN-FLOW-01")
def test_the_scripted_client_walks_fixture_co_to_compile_over_mcp(client, mcp):
    fake = FakeClaude(OverMcp(mcp))
    deal = fake.create()
    walk = fake.walk(deal)

    assert walk.handed_out == _expected_steps()
    assert walk.reported_skips == []
    _check_compiled_memo(client, walk)
    assert walk.transcript[-1]["tool"] == "compile"


@pytest.mark.spec("CONN-FLOW-02")
def test_the_same_walk_over_rest_succeeds_identically(client):
    # Two firms so the walks don't share a deal: REST as test-firm, MCP as other-firm.
    over_rest = FakeClaude(OverRest(client))
    rest_walk = over_rest.walk(over_rest.create())

    mcp = Mcp(client, headers=key_headers("other-firm"))
    mcp.initialize()
    over_mcp = FakeClaude(OverMcp(mcp))
    mcp_walk = over_mcp.walk(over_mcp.create())

    assert rest_walk.handed_out == _expected_steps()
    _check_compiled_memo(client, rest_walk)
    assert _shape(rest_walk) == _shape(mcp_walk)
    assert rest_walk.compiled["report"] == mcp_walk.compiled["report"]
    assert "/test-firm/" in rest_walk.compiled["html_url"]
    assert "/other-firm/" in mcp_walk.compiled["html_url"]

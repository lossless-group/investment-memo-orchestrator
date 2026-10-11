"""The ledger's parsing rules, tested directly (no spec IDs: this is the harness)."""

from __future__ import annotations

from src.ledger import GATED, GREEN, MISSING, RED, classify, join_outcomes, parse_plan, parse_spec_ids

from .conftest import REPO

SPEC = REPO / "context-v" / "specs" / "MemoPop-Connector-API.md"
PLAN = REPO / "context-v" / "plans" / "MemoPop-Connector-API-Phase-1-Foundation.md"


def test_level_three_headings_do_not_end_the_tests_section(tmp_path):
    spec = tmp_path / "s.md"
    spec.write_text(
        "# S\n\nProse mentions `X-PROSE-01`.\n\n## Tests\n\n### Group A\n\n| `A-ONE-01` | x |\n\n"
        "### Group B\n\n| `B-TWO-02` | y |\n| ~~`B-OLD-03`~~ | z |\n\n## Done when\n\n`C-AFTER-04`\n"
    )
    active, retired = parse_spec_ids(spec)
    assert active == ["A-ONE-01", "B-TWO-02"]
    assert retired == []  # the strike sits outside the backticks, so it stays out
    spec.write_text("## Tests\n\n| `~~B-OLD-03~~` | z |\n")
    assert parse_spec_ids(spec) == ([], ["B-OLD-03"])


def test_a_spec_without_a_tests_section_yields_nothing(tmp_path):
    spec = tmp_path / "s.md"
    spec.write_text("# S\n\n| `A-ONE-01` | x |\n")
    assert parse_spec_ids(spec) == ([], [])


def test_the_connector_spec_and_plan_one_agree():
    active, _ = parse_spec_ids(SPEC)
    owned, status = parse_plan(PLAN)
    assert len(owned) == 33
    assert set(owned) <= set(active)
    assert status


def test_worst_outcome_wins_and_classify():
    results = join_outcomes({"a": ["X-01"], "b": ["X-01", "Y-02"], "c": ["Z-03"]}, {"a": "passed", "b": "failed", "c": "skipped"})
    assert classify("X-01", results) == RED
    assert classify("Y-02", results) == RED
    assert classify("Z-03", results) == GATED
    assert classify("W-04", results) == MISSING
    assert classify("Q-05", join_outcomes({"q": ["Q-05"]}, {"q": "passed"})) == GREEN

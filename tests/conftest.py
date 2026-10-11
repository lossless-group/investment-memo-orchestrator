"""Pytest configuration shared by the whole suite.

Registers the ``spec`` marker that binds a test function to a spec test ID, and
writes ``.spec-results.json`` at the repo root after every run so
``scripts/spec_status.py`` can derive spec status from *execution* rather than
from prose.

Copied from corpora-builder's ``tests/conftest.py``. The join logic lives in
:mod:`src.ledger` so it can be tested directly; this module is only the pytest
plumbing that feeds it. Hand-written status drifts: a plan that says "Shipped"
while its tests are red is worse than no status, because it is trusted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ledger import SEVERITY, join_outcomes

RESULTS_PATH = Path(__file__).parent.parent / ".spec-results.json"

# Module-level rather than stashed on `config`: TestReport carries no reference
# back to the config object, so the report hook cannot reach it.
_spec_ids_by_node: dict[str, list[str]] = {}
_outcome_by_node: dict[str, str] = {}


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "spec(id): bind this test to a spec test ID, e.g. @pytest.mark.spec('CONN-REG-01')",
    )
    _spec_ids_by_node.clear()
    _outcome_by_node.clear()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Map every collected test to the spec IDs it claims."""
    for item in items:
        for marker in item.iter_markers(name="spec"):
            for spec_id in marker.args:
                _spec_ids_by_node.setdefault(item.nodeid, []).append(str(spec_id))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record the worst outcome seen across setup/call/teardown for each test."""
    outcome = "error" if (report.failed and report.when != "call") else report.outcome
    prior = _outcome_by_node.get(report.nodeid)
    if prior is None or SEVERITY[outcome] > SEVERITY[prior]:
        _outcome_by_node[report.nodeid] = outcome


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Join outcomes onto spec IDs and write the results file.

    Skipped under xdist workers and when nothing claimed a spec ID, so a narrow
    run of unrelated tests does not wipe the last useful results.
    """
    if hasattr(session.config, "workerinput") or not _spec_ids_by_node:
        return
    results = join_outcomes(_spec_ids_by_node, _outcome_by_node)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")

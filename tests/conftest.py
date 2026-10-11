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
import time
from pathlib import Path

import pytest

from src.ledger import SEVERITY, join_outcomes

RESULTS_PATH = Path(__file__).parent.parent / ".spec-results.json"

# Module-level rather than stashed on `config`: TestReport carries no reference
# back to the config object, so the report hook cannot reach it.
_spec_ids_by_node: dict[str, list[str]] = {}
_outcome_by_node: dict[str, str] = {}

#: A test or run whose wall time exceeds its awake time by this much is reported.
SLEEP_NOTICE_SECONDS = 10.0
_clocks: dict[str, tuple[float, float]] = {}
_config: list[pytest.Config] = []


def _now() -> tuple[float, float]:
    return time.time(), time.monotonic()


def slept_seconds(start: tuple[float, float], end: tuple[float, float]) -> float:
    """How long the machine was asleep between two ``(wall, monotonic)`` readings.

    The wall clock runs through system sleep; the monotonic clock does not (on
    macOS it is mach_absolute_time, on Linux CLOCK_MONOTONIC). The difference is
    the time this process could not run. A laptop that idle-sleeps mid-suite
    looks exactly like a hang: wall time grows, nothing progresses, the CPU
    reads 100% whenever it is awake, and faulthandler's timer (monotonic) never
    fires. This makes that visible instead of silent.
    """
    return max(0.0, (end[0] - start[0]) - (end[1] - start[1]))


def pytest_configure(config: pytest.Config) -> None:
    _config[:] = [config]
    config.addinivalue_line(
        "markers",
        "spec(id): bind this test to a spec test ID, e.g. @pytest.mark.spec('CONN-REG-01')",
    )
    _spec_ids_by_node.clear()
    _outcome_by_node.clear()
    _clocks.clear()
    _clocks["session"] = _now()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Map every collected test to the spec IDs it claims."""
    for item in items:
        for marker in item.iter_markers(name="spec"):
            for spec_id in marker.args:
                _spec_ids_by_node.setdefault(item.nodeid, []).append(str(spec_id))


def pytest_runtest_logstart(nodeid: str) -> None:
    _clocks[nodeid] = _now()


@pytest.hookimpl(optionalhook=True)
def pytest_runtest_logfinish(nodeid: str) -> None:
    start = _clocks.pop(nodeid, None)
    if start is None:
        return
    slept = slept_seconds(start, _now())
    if slept >= SLEEP_NOTICE_SECONDS:
        _say(f"the machine slept {slept:.0f}s during {nodeid} (the test itself is unaffected)")


def pytest_terminal_summary(terminalreporter) -> None:
    start = _clocks.get("session")
    if start is None:
        return
    slept = slept_seconds(start, _now())
    if slept >= SLEEP_NOTICE_SECONDS:
        terminalreporter.write_sep(
            "=",
            f"the machine slept {slept:.0f}s of this run; pytest's own timings exclude it. "
            "On macOS run under `caffeinate -i` (scripts/check.sh does).",
            yellow=True,
        )


def _say(line: str) -> None:
    reporter = _config[0].pluginmanager.get_plugin("terminalreporter") if _config else None
    if reporter is not None:
        reporter.write_line(f"  [suite clock] {line}", yellow=True)


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

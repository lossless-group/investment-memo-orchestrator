"""The ledger's pure logic: parsing spec test IDs and joining them to outcomes.

Copied from corpora-builder's ``src/ledger.py`` (knots-style: copied, never
imported across repos) and adapted for this repo:

- A spec's ``## Tests`` section ends only at the next **level-2** heading. The
  connector spec groups its IDs under ``###`` subheadings, which corpora-builder's
  parser treated as the end of the section.
- Specs without a ``## Tests`` section yield no IDs and are ignored; most of the
  orchestrator's specs predate the ledger.
- Plans name the IDs they own in frontmatter (``owns_test_ids: [...]``), so a
  plan's IDs can be checked on their own (:func:`parse_plan`).

Kept importable, rather than inside ``conftest.py`` or the CLI script, so it can
be tested directly. See ``context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

import yaml


class TestRecord(TypedDict):
    """One test function's contribution to a spec ID."""

    nodeid: str
    outcome: str


class SpecEntry(TypedDict):
    """The joined state of one spec ID: worst outcome plus its claimants."""

    outcome: str
    tests: list[TestRecord]


GREEN = "GREEN"
RED = "RED"
MISSING = "MISSING"
RETIRED = "RETIRED"
#: A test that exists and deliberately did not run (its gate, such as an env var
#: or real credentials, was not set). Not a failure, but not green either, so
#: --require-green still refuses to call a plan complete until someone runs it.
GATED = "GATED"

#: Worst-wins ordering. A test that errors during setup is not green merely
#: because its never-executed call phase did not fail.
SEVERITY = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}

#: CONN-REG-01, CONN-AUTH-05: an uppercase stem plus a numeric tail.
ID_PATTERN = re.compile(r"`(~~)?([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{2,})(~~)?`")
_TESTS_HEADING = re.compile(r"^##\s+Tests\b", re.IGNORECASE)
_LEVEL_TWO_HEADING = re.compile(r"^##(?!#)\s+")

#: Plan statuses whose owned IDs the ledger enforces with --active-plans.
ACTIVE_PLAN_STATUSES = {"in-progress", "shipped", "done", "complete"}


def parse_spec_ids(path: Path) -> tuple[list[str], list[str]]:
    """Return ``(active_ids, retired_ids)`` from a spec's ``## Tests`` section.

    IDs mentioned outside that section are ignored, so prose may reference an ID
    without enrolling it as a promise. A struck-through ID (``~~ID~~``) is
    retired: excluded from totals, never renumbered, never reused. ``###``
    subheadings inside the section do not end it; the next ``##`` does.
    """
    active: list[str] = []
    retired: list[str] = []
    in_tests = False

    for line in path.read_text(encoding="utf-8").splitlines():
        if _TESTS_HEADING.match(line):
            in_tests = True
            continue
        if in_tests and _LEVEL_TWO_HEADING.match(line):
            break
        if not in_tests:
            continue
        for open_strike, spec_id, close_strike in ID_PATTERN.findall(line):
            target = retired if (open_strike and close_strike) else active
            if spec_id not in target:
                target.append(spec_id)

    return active, retired


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data = yaml.safe_load(text[3:end]) or {}
    return data if isinstance(data, dict) else {}


def parse_plan(path: Path) -> tuple[list[str], str]:
    """Return ``(owned_ids, status)`` from a plan's frontmatter.

    ``status`` is normalised to lowercase with dashes (``In Progress`` becomes
    ``in-progress``) so the active-plan check does not depend on spelling.
    """
    meta = _frontmatter(path)
    owned = [str(i) for i in (meta.get("owns_test_ids") or [])]
    status = re.sub(r"[\s_]+", "-", str(meta.get("status") or "").strip().lower())
    return owned, status


def worst(outcomes: list[str]) -> str:
    """Return the most severe outcome in ``outcomes``."""
    if not outcomes:
        return "error"
    return max(outcomes, key=lambda o: SEVERITY.get(o, SEVERITY["error"]))


def join_outcomes(
    spec_ids_by_node: dict[str, list[str]],
    outcome_by_node: dict[str, str],
) -> dict[str, SpecEntry]:
    """Join collected spec markers to test outcomes.

    A spec ID claimed by several tests resolves to the **worst** of them: one
    failing claimant makes the ID red however many others pass, because the spec
    promised all of it.
    """
    per_spec: dict[str, SpecEntry] = {}

    for nodeid, ids in spec_ids_by_node.items():
        outcome = outcome_by_node.get(nodeid, "error")
        for spec_id in ids:
            entry = per_spec.setdefault(spec_id, {"outcome": outcome, "tests": []})
            entry["tests"].append({"nodeid": nodeid, "outcome": outcome})
            entry["outcome"] = worst([entry["outcome"], outcome])

    for entry in per_spec.values():
        entry["tests"].sort(key=lambda t: t["nodeid"])

    return per_spec


def classify(spec_id: str, results: dict[str, SpecEntry]) -> str:
    """Return GREEN, RED, GATED, or MISSING for one spec ID against a results map."""
    entry = results.get(spec_id)
    if entry is None:
        return MISSING
    outcome = entry.get("outcome")
    if outcome == "passed":
        return GREEN
    if outcome == "skipped":
        return GATED
    return RED

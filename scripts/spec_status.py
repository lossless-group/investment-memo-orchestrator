#!/usr/bin/env python3
"""The ledger: derive spec status by running the suite, never by reading prose.

A spec in ``context-v/specs/`` may carry a ``## Tests`` section whose table rows
each begin with a stable ID. Every test function that implements one carries
``@pytest.mark.spec("<ID>")``. This script joins the two and reports the truth.

    GREEN     a test claims the ID and passes
    RED       a test claims the ID and does not pass
    GATED     a test claims the ID and was skipped (its gate was not set)
    MISSING   the spec promises a behaviour that no test function claims
    RETIRED   the ID is struck through in the spec (~~ID~~); excluded from totals

Specs with no ``## Tests`` section are ignored.

Copied from corpora-builder's ``scripts/spec_status.py`` and adapted: no
frontend results to merge, and plans can be checked on their own.

Usage
-----
    uv run python scripts/spec_status.py                     # every spec, runs pytest
    uv run python scripts/spec_status.py --no-run            # reuse the last results
    uv run python scripts/spec_status.py --spec Connector    # one spec (substring ok)
    uv run python scripts/spec_status.py --plan context-v/plans/MemoPop-Connector-API-Phase-1-Foundation.md
    uv run python scripts/spec_status.py --active-plans      # plans In Progress or Shipped
    uv run python scripts/spec_status.py --plan <file> --tdd-floor      # after writing failing tests
    uv run python scripts/spec_status.py --plan <file> --require-green  # plan-completion gate

``--plan`` (repeatable) and ``--active-plans`` restrict the report and every
gate to the IDs those plans own (``owns_test_ids`` in their frontmatter). Without
them, every ID in every selected spec is reported and enforced.

Exit codes
----------
    0  the requested condition holds
    1  MISSING IDs exist, or a plan owns an ID no spec defines (always fatal)
    2  --require-green was asked for and something is not green
    3  --tdd-floor was asked for and something is already green
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "context-v" / "specs"
PLANS_DIR = REPO_ROOT / "context-v" / "plans"
RESULTS_PATH = REPO_ROOT / ".spec-results.json"

sys.path.insert(0, str(REPO_ROOT))

from src.ledger import (  # noqa: E402
    ACTIVE_PLAN_STATUSES,
    GATED,
    GREEN,
    MISSING,
    RED,
    RETIRED,
    classify,
    parse_plan,
    parse_spec_ids,
)

_GLYPH = {GREEN: "✓", RED: "✗", MISSING: "○", RETIRED: "—", GATED: "⊘"}
_BOLD, _DIM, _OFF = "\033[1m", "\033[2m", "\033[0m"
_REDC, _GREENC = "\033[31m", "\033[32m"


def run_pytest() -> int:
    """Run the suite so the results file is fresh. Returns pytest's exit code."""
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=line"], cwd=REPO_ROOT)
    return proc.returncode


def load_results(path: Path = RESULTS_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _resolve_plan(arg: str) -> Path:
    path = Path(arg)
    if not path.is_absolute():
        path = (Path.cwd() / path) if (Path.cwd() / path).exists() else REPO_ROOT / path
    if not path.exists():
        candidates = [p for p in PLANS_DIR.glob("*.md") if arg.lower() in p.stem.lower()]
        if len(candidates) == 1:
            return candidates[0]
        raise SystemExit(f"No plan at {arg!r}")
    return path


def enforced_ids(args: argparse.Namespace) -> tuple[set[str] | None, list[str]]:
    """Return the IDs to report and enforce (None means all), plus plan labels."""
    plans: list[Path] = [_resolve_plan(p) for p in (args.plan or [])]
    if args.active_plans:
        for path in sorted(PLANS_DIR.glob("*.md")):
            owned, status = parse_plan(path)
            if owned and status in ACTIVE_PLAN_STATUSES and path not in plans:
                plans.append(path)
    if not plans and not args.active_plans:
        return None, []
    ids: set[str] = set()
    labels: list[str] = []
    for path in plans:
        owned, status = parse_plan(path)
        ids.update(owned)
        labels.append(f"{path.stem} ({status or 'no status'}, {len(owned)} IDs)")
    return ids, labels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--spec", help="only this spec (filename stem, substring ok)")
    parser.add_argument("--no-run", action="store_true", help="reuse the last results")
    parser.add_argument(
        "--plan",
        action="append",
        help="only the IDs this plan owns (path or stem substring; repeatable)",
    )
    parser.add_argument(
        "--active-plans",
        action="store_true",
        help="only the IDs owned by plans whose status is In Progress, Shipped, or Done",
    )
    parser.add_argument(
        "--require-green",
        action="store_true",
        help="exit non-zero unless every reported ID is GREEN (completion gate)",
    )
    parser.add_argument(
        "--tdd-floor",
        action="store_true",
        help="exit non-zero unless every reported ID exists and is RED (TDD floor)",
    )
    args = parser.parse_args()

    if not SPECS_DIR.exists():
        print(f"No specs directory at {SPECS_DIR}", file=sys.stderr)
        return 0

    spec_files = sorted(p for p in SPECS_DIR.glob("*.md") if not p.name.startswith("_"))
    if args.spec:
        needle = args.spec.lower()
        spec_files = [p for p in spec_files if needle in p.stem.lower()]
        if not spec_files:
            print(f"No spec matching {args.spec!r}", file=sys.stderr)
            return 1

    only, plan_labels = enforced_ids(args)
    if only is not None:
        print(f"{_BOLD}Plans{_OFF}")
        for label in plan_labels or ["(none active: nothing to enforce)"]:
            print(f"  {label}")
        print()

    if not args.no_run:
        run_pytest()
        print()
    results = load_results()

    totals = {GREEN: 0, RED: 0, MISSING: 0, RETIRED: 0, GATED: 0}
    saw_any = False
    defined: set[str] = set()
    not_enforced = 0

    for spec_file in spec_files:
        active, retired = parse_spec_ids(spec_file)
        defined.update(active)
        defined.update(retired)
        if only is not None:
            not_enforced += sum(1 for sid in active if sid not in only)
            active = [sid for sid in active if sid in only]
            retired = [sid for sid in retired if sid in only]
        if not active and not retired:
            continue
        saw_any = True

        rows = [(sid, classify(sid, results)) for sid in active]
        rows += [(sid, RETIRED) for sid in retired]
        for _, status in rows:
            totals[status] += 1

        green = sum(1 for _, s in rows if s == GREEN)
        print(f"{_BOLD}{spec_file.stem}{_OFF}  ({green}/{len(active)} green)")
        for spec_id, status in rows:
            colour = _GREENC if status == GREEN else (_REDC if status in (RED, MISSING) else _DIM)
            print(f"  {colour}{_GLYPH[status]} {status:<8}{_OFF} {spec_id}")
        print()

    orphans = sorted((only or set()) - defined)
    if orphans:
        print(
            f"{_REDC}FAIL{_OFF}  plan(s) own ID(s) no spec defines: {', '.join(orphans)}",
            file=sys.stderr,
        )
        return 1

    if not saw_any:
        print("Nothing to derive: no selected spec ID is in scope.")
        return 0

    print(
        f"{_BOLD}Totals{_OFF}  {totals[GREEN]} green · {totals[RED]} red · "
        f"{totals[GATED]} gated · {totals[MISSING]} missing · {totals[RETIRED]} retired"
    )
    if not_enforced:
        print(f"{_DIM}  {not_enforced} other spec ID(s) belong to plans not in scope{_OFF}")

    if totals[MISSING]:
        print(
            f"\n{_REDC}FAIL{_OFF}  {totals[MISSING]} spec test ID(s) have no "
            f"implementing test.\n"
            f"      A promise with no test is the one failure that looks like success.\n"
            f'      Add @pytest.mark.spec("<ID>") to the test that proves each.',
            file=sys.stderr,
        )
        return 1

    if args.require_green and (totals[RED] or totals[GATED]):
        print(
            f"\n{_REDC}FAIL{_OFF}  --require-green: {totals[RED]} red, "
            f"{totals[GATED]} gated. Not complete.\n"
            f"      Do NOT edit a test to close this gap: if a test cannot pass\n"
            f"      against honest code, the spec is wrong. Stop and report it.",
            file=sys.stderr,
        )
        return 2

    if args.tdd_floor and totals[GREEN]:
        print(
            f"\n{_REDC}FAIL{_OFF}  --tdd-floor: {totals[GREEN]} ID(s) are already green "
            f"before implementation.\n"
            f"      A test that passes before the code exists is not testing the code.",
            file=sys.stderr,
        )
        return 3

    if totals[RED]:
        # Red is expected mid-TDD, so this is not a failure, but it is not "OK".
        print(f"\n{_REDC}{totals[RED]} red{_OFF}: expected during TDD, not at completion.")
        return 0

    print(f"\n{_GREENC}OK{_OFF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

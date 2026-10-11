#!/usr/bin/env bash
#
# The check ladder, cheapest rung first. See
# context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md.
#
#   1. ruff check   (connector code, its tests, and the ledger only)
#   2. black --check (same scope; the rest of the repo is not reformatted)
#   3. pytest       (the whole suite, in one session so the ledger sees it all)
#   4. ledger       (every ID owned by a plan that is In Progress or Shipped
#                    must have a test, and must be GREEN)
#
# Every rung is blocking. Pass plan files to check those plans instead of the
# active ones:  scripts/check.sh context-v/plans/MemoPop-Connector-API-Phase-1-Foundation.md
#
# Without the private io/<firm> submodules (CI, fresh worktrees), the tests that
# read real firm data cannot run. They are listed in IO_DEPENDENT below and
# ignored when io/ is empty; CI reports them in a separate non-blocking step.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

LINT_PATHS=(src/connector tests/connector src/ledger.py scripts/spec_status.py tests/conftest.py
            scripts/health_check.py scripts/provision_firm.py)
IO_DEPENDENT=(tests/test_amend_on_polish_path.py)

# WeasyPrint (compile's PDF export) loads pango and gobject by bare name. On macOS
# those live in Homebrew's lib, and DYLD_* variables never survive into this
# script (macOS strips them when it starts the protected /bin/bash), so set it here.
if [ "$(uname)" = "Darwin" ] && [ -d /opt/homebrew/lib ]; then
  export DYLD_FALLBACK_LIBRARY_PATH="${DYLD_FALLBACK_LIBRARY_PATH:-/opt/homebrew/lib}"
fi

FAILED=0
hdr() { printf '\n\033[1m── %s\033[0m\n' "$1"; }

hdr "ruff check"
uv run ruff check "${LINT_PATHS[@]}" || FAILED=1

hdr "black --check"
uv run black --check --quiet "${LINT_PATHS[@]}" || FAILED=1

hdr "pytest"
PYTEST_ARGS=(-q -p no:cacheprovider)
if [ -z "$(find io -mindepth 2 -maxdepth 2 -print -quit 2>/dev/null)" ]; then
  echo "  io/ submodules absent: ignoring ${IO_DEPENDENT[*]} (they read private firm data)"
  for f in "${IO_DEPENDENT[@]}"; do PYTEST_ARGS+=(--ignore="$f"); done
fi
uv run pytest "${PYTEST_ARGS[@]}" || FAILED=1

hdr "ledger"
if [ "$#" -gt 0 ]; then
  LEDGER_ARGS=()
  for plan in "$@"; do LEDGER_ARGS+=(--plan "$plan"); done
else
  LEDGER_ARGS=(--active-plans)
fi
uv run python scripts/spec_status.py --no-run --require-green "${LEDGER_ARGS[@]}" || FAILED=1

printf '\n\033[1m── summary\033[0m\n'
if [ "$FAILED" -ne 0 ]; then
  printf '  \033[31mblocking checks FAILED\033[0m\n'
  exit 1
fi
printf '  \033[32mblocking checks passed\033[0m\n'

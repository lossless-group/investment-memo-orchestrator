"""A test-only fault hook, so the real-Claude run (CONN-PLUG-02) can meet a skip and a
``down`` on the live server.

The run needs both from the server's side: an optional step the server skips, and
a ``next_step`` that fails with ``down``. Neither can be forced with the ordinary
ops switch (``MEMOPOP_DISABLED_STEPS`` is server-wide and would touch real firms),
so this hook fires only when **both** keys turn:

1. the firm is listed in ``MEMOPOP_FAULT_FIRMS`` (``settings.fault_firms``; empty
   by default, and only ever ``test-firm`` in production), and
2. the deal's outline is the firm's **own** (``<firm>/templates/outlines/``, which
   only an operator writes) and carries a ``test_faults`` block::

       test_faults:
         disable: [research.sources]   # optional steps only; required ones are ignored
         down_at: enhance.tables       # next_step fails with service_unavailable here

MemoPop's shared outlines never fire it, a malformed block is ignored, and any
error reading it means "no faults": the hook can't break a firm. A ``down`` raised
here is raised before ``next_step`` writes anything, as a real outage would be.

Install the outline with ``python -m src.connector.faults install-outline <firm>``
(reads ``MEMO_IO_ROOT``), run where the volume is mounted.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .errors import ConnectorError
from .templates import NAME_RE
from .workspace import is_slug

if TYPE_CHECKING:
    from .workspace import Workspace

OUTLINE_NAME = "real-claude-three"
OUTLINE_PATH = Path(__file__).resolve().parent / "fault_outlines" / f"{OUTLINE_NAME}.yaml"


@dataclass(frozen=True)
class Faults:
    disable: frozenset[str] = frozenset()
    down_at: str | None = None


NONE = Faults()


def for_deal(ws: Workspace, state: dict) -> Faults:
    """The faults a deal is under: :data:`NONE` unless both keys turn."""
    if ws.firm not in ws.settings.fault_firms:
        return NONE
    name = str(state.get("template") or "")
    if not NAME_RE.match(name):
        return NONE
    path = ws.root / "templates" / "outlines" / f"{name}.yaml"
    try:
        if not path.is_file() or path.is_symlink():
            return NONE
        block = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("test_faults")
    except (OSError, ValueError, yaml.YAMLError, AttributeError):
        return NONE
    if not isinstance(block, dict):
        return NONE
    disable = block.get("disable") or []
    down_at = block.get("down_at")
    if not isinstance(disable, list) or not (down_at is None or isinstance(down_at, str)):
        return NONE
    return Faults(frozenset(str(s) for s in disable), down_at)


def raise_if_down(faults: Faults, step_id: str | None) -> None:
    """``next_step`` calls this before writing anything."""
    if faults.down_at is not None and step_id == faults.down_at:
        raise ConnectorError("service_unavailable", details={"test_fault": True})


def install_outline(io_root: Path, firm: str) -> Path:
    """Copy the real-Claude outline into an existing firm's own outlines."""
    if not is_slug(firm):
        raise ValueError(f"Bad firm slug {firm!r}")
    root = Path(io_root) / firm
    if not root.is_dir():
        raise FileNotFoundError(f"No firm workspace at {root}; provision the firm first")
    outlines = root / "templates" / "outlines"
    outlines.mkdir(parents=True, exist_ok=True)
    dest = outlines / f"{OUTLINE_NAME}.yaml"
    shutil.copy(OUTLINE_PATH, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.connector.faults")
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install-outline", help="install the real-Claude outline in a firm")
    install.add_argument("firm")
    args = parser.parse_args(argv)
    io_root = Path(os.environ.get("MEMO_IO_ROOT") or "/data/firms")
    try:
        dest = install_outline(io_root, args.firm)
    except (ValueError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"installed {dest}")
    print("It fires only if MEMOPOP_FAULT_FIRMS on the server lists this firm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Provision a firm's workspace: an operator act, never a tool.

``scripts/provision_firm.py`` is the command line for it; run it where the
volume is mounted (on Railway, ``railway ssh`` into the service). Re-running
is safe: the deals folder is kept and ``firm.json`` is merged, not replaced.

With ``health_check=True`` the firm also gets the one-section
``health-check`` outline in its own ``templates/outlines/``, which
``scripts/health_check.py`` uses so it can walk research, draft, and compile
in a few calls. It is a firm-local outline, so no other firm sees it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .workspace import is_slug

HEALTH_CHECK_TEMPLATE = "health-check"
HEALTH_CHECK_OUTLINE = Path(__file__).resolve().parent / "ops" / "health-check.yaml"


def provision_firm(
    io_root: Path,
    firm: str,
    *,
    default_template: str | None = None,
    entity_id: str | None = None,
    health_check: bool = False,
) -> Path:
    """Create (or update) ``<io_root>/<firm>``; return its path."""
    if not is_slug(firm):
        raise ValueError(f"Bad firm slug {firm!r}: lowercase letters, digits, and dashes")
    root = Path(io_root) / firm
    (root / "deals").mkdir(parents=True, exist_ok=True)

    path = root / "firm.json"
    config: dict[str, Any] = {}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8") or "{}")
        config = loaded if isinstance(loaded, dict) else {}
    if default_template:
        config["default_template"] = default_template
    if entity_id:
        config["entity_id"] = entity_id
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    if health_check:
        outlines = root / "templates" / "outlines"
        outlines.mkdir(parents=True, exist_ok=True)
        shutil.copy(HEALTH_CHECK_OUTLINE, outlines / f"{HEALTH_CHECK_TEMPLATE}.yaml")
    return root

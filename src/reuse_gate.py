"""
Reuse gates: decide, stage by stage, whether prior work still stands.

Spec: context-v/specs/Reuse-and-Augment-Research-Across-Runs.md

A stage records a fingerprint of the inputs that determine its output. The next
run compares against the latest prior version's fingerprint: equal means copy
the prior artifact forward and skip the work; different means do the new part.
The dataroom analyzer already worked this way (`_reusable_dataroom_analysis`);
this generalizes it.

Every decision is written to `0-reuse-report.md` in the version directory, so
the operator can see in one file what a run actually spent effort on.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

REPORT_NAME = "0-reuse-report.md"


def fresh_requested(state: Dict[str, Any]) -> bool:
    """`--fresh` means ignore every prior artifact."""
    return bool(state.get("fresh"))


def fingerprint(payload: Any) -> str:
    """A stable hash of any JSON-serializable input description."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def prior_version_dir(output_dir: Any) -> Optional[Path]:
    if not output_dir:
        return None
    from .version_seed import previous_version_dir
    return previous_version_dir(Path(output_dir))


def prior_artifact(output_dir: Any, name: str) -> Optional[Path]:
    """The named artifact in the latest prior version, if it exists there."""
    prior = prior_version_dir(output_dir)
    if prior is None:
        return None
    path = prior / name
    return path if path.exists() else None


def load_prior_json(output_dir: Any, name: str) -> Optional[Dict[str, Any]]:
    path = prior_artifact(output_dir, name)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def note(output_dir: Any, stage: str, decision: str, detail: str) -> None:
    """Record one gate decision: print it and append it to the version's report."""
    icon = {"reused": "♻️", "augmented": "➕", "regenerated": "↻", "ran": "▶"}.get(decision, "•")
    print(f"   {icon}  {stage}: {decision} — {detail}")
    if not output_dir:
        return
    path = Path(output_dir) / REPORT_NAME
    try:
        if not path.exists():
            path.write_text(
                "# Reuse Report\n\n"
                "What this run reused from earlier versions and what it actually did. "
                "Spec: `context-v/specs/Reuse-and-Augment-Research-Across-Runs.md`.\n\n"
                "| Time | Stage | Decision | Why |\n| --- | --- | --- | --- |\n"
            )
        with path.open("a") as f:
            f.write(f"| {datetime.now().strftime('%H:%M:%S')} | {stage} | {decision} | "
                    f"{detail.replace('|', '/')} |\n")
    except OSError:
        pass


def reuse_disabled() -> bool:
    """Escape hatch for debugging a gate: MEMOPOP_DISABLE_REUSE=1."""
    return os.getenv("MEMOPOP_DISABLE_REUSE", "").strip() in ("1", "true", "yes")

"""Serialize a curated source list back to `Sources.md`.

Extracted from `tools/curate_sources.py` so the standalone tool and the
FastAPI sidecar share one implementation. Two writers of the same file
format will drift, and this file is the analyst's work product — the one
artifact in the pipeline that must never be silently corrupted.

Field order is fixed (not alphabetical) so a `git diff` of a curated file
shows what the analyst changed rather than a reshuffle.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Per-source key order on write.
FIELD_ORDER = [
    "url", "title", "publisher", "published_date",
    "sections", "rank", "sensitivity", "verdict", "verdict_reason", "note",
]

# Top-level frontmatter keys preserved (in this order) on save.
META_ORDER = [
    "mode", "deal", "firm",
    "date_curated_initial", "date_curated_current",
    "at_semantic_version", "curated_by", "augmented_with",
]


def clean_source(s: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize one source dict into canonical field order and types."""
    out: Dict[str, Any] = {}
    for key in FIELD_ORDER:
        val = s.get(key)
        if key == "url":
            out["url"] = str(val or "").strip()
        elif key == "sections":
            secs = val or []
            if isinstance(secs, str):
                secs = [x.strip() for x in secs.split(",") if x.strip()]
            out["sections"] = [str(x).strip() for x in secs if str(x).strip()]
        elif key == "rank":
            try:
                out["rank"] = int(val)
            except (TypeError, ValueError):
                out["rank"] = 1
        else:
            sval = str(val or "").strip()
            if sval:
                out[key] = sval
    return out


def serialize_doc(
    meta: Dict[str, Any],
    sources: List[Dict[str, Any]],
    body: str,
    mode: Optional[str] = None,
) -> str:
    """Render frontmatter + body back to a `Sources.md` document.

    The body (the analyst's "how this list was built / what was rejected"
    notes) is preserved verbatim — it is the institutional memory that
    stops the same junk being re-added next iteration.
    """
    import yaml

    fm: Dict[str, Any] = {}
    for key in META_ORDER:
        if key in meta and meta[key] is not None:
            fm[key] = meta[key]
    if mode:
        fm["mode"] = mode
    fm.setdefault("mode", meta.get("mode", "aggregated"))
    fm["date_curated_current"] = datetime.now().date().isoformat()
    fm["sources"] = [
        clean_source(s) for s in sources if str(s.get("url", "")).strip()
    ]

    # sort_keys=False preserves insertion order (top-level + per-source).
    yaml_block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False, width=4096
    )
    body = body if body.endswith("\n") else body + "\n"
    return f"---\n{yaml_block}---\n\n{body}"


def write_sources_md(
    target: Path,
    meta: Dict[str, Any],
    sources: List[Dict[str, Any]],
    body: str,
    mode: Optional[str] = None,
    *,
    backup: bool = True,
) -> Tuple[Path, Optional[Path]]:
    """Write `Sources.md`, backing up any existing file first.

    Always-backup is deliberate. This file is hand-made by an analyst and
    can represent hours of judgment; an overwrite with no undo is the one
    unrecoverable failure this surface could have.

    Returns:
        `(written_path, backup_path_or_None)`
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    if backup and target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = target.with_name(target.name + f".bak-{stamp}")
        shutil.copy2(target, backup_path)
    target.write_text(serialize_doc(meta, sources, body, mode))
    return target, backup_path

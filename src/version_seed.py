"""
Seed a new version directory from the one before it, so a framed run can extend.

Without this, everything the thesis-frame feature promises is inert.

`create_artifact_directory` makes an empty directory. `write_or_append_research`
appends only when the research file already exists — in an empty directory it
does not, so it writes instead, and ProfileHealth's 62.8 KB of clinician research
would be regathered rather than extended. The `prose: unchanged` guard is
`existing.exists()` against the same empty directory, so Section 9's
hand-written per-instrument SAFE transcription would be regenerated and lost.

Both guarantees depend on the prior version's artifacts being present before the
agents run. That is what this does, and it is deliberately scoped:

- Only under a frame. An unframed run keeps today's behaviour exactly — a clean
  directory, everything regenerated — because that is what an unframed re-run
  means and changing it would surprise every existing caller.
- Never under `--fresh`, whose entire meaning is "ignore prior artifacts".
- Only `1-research/` and `2-sections/`, the two durable layers. Build outputs
  (the assembled draft, exports, validation reports, the scorecard) are
  regenerated from those and copying them forward would ship a stale artifact
  next to fresh prose.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# The durable layers, per context-v/specs/Thesis-Frames-And-The-Re-Angle-Run.md.
SEEDED_DIRS = ("1-research", "2-sections")

VERSION_RE = re.compile(r"-v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


@dataclass
class SeedResult:
    source: Optional[Path] = None
    destination: Optional[Path] = None
    files_copied: int = 0
    dirs_copied: List[str] = field(default_factory=list)
    already_present: int = 0
    reason: str = ""

    @property
    def seeded(self) -> bool:
        return self.files_copied > 0


def _version_key(path: Path):
    m = VERSION_RE.search(path.name)
    return (int(m["major"]), int(m["minor"]), int(m["patch"])) if m else (-1, -1, -1)


def previous_version_dir(output_dir: Path) -> Optional[Path]:
    """
    The highest-versioned sibling below this one.

    Sorted numerically rather than lexically: v0.0.10 must beat v0.0.9, which a
    string sort gets backwards.
    """
    output_dir = Path(output_dir)
    outputs_root = output_dir.parent
    if not outputs_root.exists():
        return None

    this = _version_key(output_dir)
    candidates = [
        p for p in outputs_root.iterdir()
        if p.is_dir() and p != output_dir and VERSION_RE.search(p.name)
        and _version_key(p) < this
    ]
    return max(candidates, key=_version_key) if candidates else None


def seed_version(output_dir: Path, *, frame=None, fresh: bool = False) -> SeedResult:
    """
    Copy the durable layers from the previous version into this one.

    Never overwrites: a file already present in the new directory wins, so this
    is safe to call after something has already written there, and safe to call
    twice.
    """
    result = SeedResult(destination=Path(output_dir))

    if frame is None:
        result.reason = "no frame — unframed runs start clean, as before"
        return result
    if fresh:
        result.reason = "--fresh — prior artifacts deliberately ignored"
        return result

    source = previous_version_dir(Path(output_dir))
    if source is None:
        result.reason = "no previous version to seed from"
        return result
    result.source = source

    for name in SEEDED_DIRS:
        src_dir = source / name
        if not src_dir.is_dir():
            continue
        dst_dir = Path(output_dir) / name
        dst_dir.mkdir(parents=True, exist_ok=True)
        copied_here = 0
        for src_file in sorted(src_dir.rglob("*")):
            if not src_file.is_file():
                continue
            dst_file = dst_dir / src_file.relative_to(src_dir)
            if dst_file.exists():
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied_here += 1
        if copied_here:
            result.dirs_copied.append(name)
            result.files_copied += copied_here

    if not result.files_copied:
        already = sum(
            1 for name in SEEDED_DIRS
            for _ in (Path(output_dir) / name).glob("*")
            if (Path(output_dir) / name).is_dir()
        )
        result.reason = (
            f"already seeded from {source.name} ({already} file(s) present)"
            if already else f"nothing to seed from {source.name}"
        )
        result.already_present = already
    return result

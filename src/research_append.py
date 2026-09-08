"""
Write a section's research additively when a frame says to extend it.

The design rule this enforces, from
context-v/specs/Thesis-Frames-And-The-Re-Angle-Run.md:

    1-research/ accumulates. 2-sections/ is regenerated from it.

Both codified synthesis paths previously ended in `write_text`, which meant a
second run over the same section silently replaced the first run's findings. For
an unframed run that is fine — the corpus is being regathered from the same
curated sources and the result is equivalent. For a framed run it is not: the
frame's whole premise is that the existing evidence stays true and new evidence
is being added beside it. A `write_text` there throws away the half of the
picture nobody asked to discard, and a second gathering will not reproduce the
first exactly, so facts disappear between versions.

Appended blocks carry a provenance stamp naming the frame and run that produced
them. That is what lets a later reader — or the fact-checker — tell one thesis's
evidence from another's, and what makes a frame reversible: dropping a thesis
means dropping its blocks, not re-deriving the file.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

STAMP_RE = re.compile(
    r"<!--\s*research-block:\s*frame=(?P<frame>[^\s]+)\s+run=(?P<run>[^\s]+)\s+appended=(?P<date>[^\s]+)\s*-->"
)


def stamp_for(frame_slug: str, run_version: str, when: Optional[str] = None) -> str:
    return (
        f"<!-- research-block: frame={frame_slug} run={run_version} "
        f"appended={when or date.today().isoformat()} -->"
    )


def existing_stamps(text: str) -> list[dict]:
    """Every provenance stamp already in a research file, oldest first."""
    return [m.groupdict() for m in STAMP_RE.finditer(text)]


def has_block(text: str, frame_slug: str, run_version: str) -> bool:
    """
    True when this exact frame+run already contributed to this file.

    Guards re-entrancy: a resumed run must not append its own findings twice.
    """
    return any(
        s["frame"] == frame_slug and s["run"] == run_version
        for s in existing_stamps(text)
    )


def write_or_append_research(
    path: Path,
    content: str,
    *,
    frame: Any = None,
    section_filename: str = "",
    run_version: str = "",
) -> str:
    """
    Write a research file, appending instead of replacing when a frame extends it.

    Returns the action taken: "written", "appended", or "skipped-duplicate".

    Appends only when ALL of these hold, so the additive path can never fire by
    accident on an ordinary run:
      - a frame is active,
      - this section's research directive is extend or refresh,
      - the file already exists with real content.
    """
    directive = frame.directive_for(section_filename) if frame is not None else None
    should_append = (
        directive is not None
        and directive.researches
        and path.exists()
        and path.read_text().strip()
    )

    if not should_append:
        path.write_text(content)
        return "written"

    prior = path.read_text()
    slug = getattr(frame, "slug", "frame")
    version = run_version or "unversioned"

    if has_block(prior, slug, version):
        return "skipped-duplicate"

    heading = (
        f"## Added under thesis frame: {getattr(frame, 'name', slug)}"
        if directive.research == "extend"
        else f"## Refreshed under thesis frame: {getattr(frame, 'name', slug)}"
    )

    body = content.strip()
    # The appended body is a whole research file in its own right, with its own
    # H1 and its own "### Citations" heading. Demote the H1 so the merged file
    # keeps one top-level heading, and leave the citations block alone — the
    # assembler reads definitions wherever they appear.
    body = re.sub(r"^#\s+", "### ", body, count=1, flags=re.MULTILINE)

    merged = (
        prior.rstrip()
        + "\n\n---\n\n"
        + stamp_for(slug, version)
        + f"\n\n{heading}\n\n"
        + body
        + "\n"
    )
    path.write_text(merged)
    return "appended"

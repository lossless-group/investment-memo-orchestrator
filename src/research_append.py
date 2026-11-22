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

An appended block is re-keyed before it is written (`rekey_appended()`): its
footnotes get hex keys from src/citation_keys.py, and a source the file already
defines keeps the key it has there. So a file defines each key once, and a key
means the same source in every block. Appended blocks used to number from 1
again, which made assembly link the reused block's footnotes to the appended
block's sources (context-v/issues/Appended-Research-Blocks-Reuse-Footnote-Keys.md).

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

from .citation_keys import LONG, _key, assign_keys, source_identity
from .md_breaks import normalize_section_breaks
from .research_blocks import line_definitions, read_research_keys

_MARKER = re.compile(r"\[\^([a-zA-Z0-9_-]+)\]")
_DEF_LINE = re.compile(r"^\[\^([a-zA-Z0-9_-]+)\]:")

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


def rekey_appended(prior: str, body: str) -> str:
    """Re-key a block about to be appended to ``prior`` so no key is reused.

    Each source the block defines gets its hex key from ``assign_keys()``. A
    source ``prior`` already defines (one meaning, in any block) keeps the key it
    has there, and its definition is dropped from the block, so the file defines
    it once. A hex key that ``prior`` already uses for another source is widened
    to 8 characters. Keys the block cites but does not define are left alone.

    Hex keys rather than continued numbering: the hex key is the one assembly
    gives the source anyway, it needs no count of the keys above it, and it
    cannot collide with a numbered or hex key already in the file.
    """
    new_defs: dict[str, str] = {}
    for key, definition in line_definitions(body):
        new_defs.setdefault(key, definition)
    if not new_defs:
        return body
    known = read_research_keys(prior)
    prior_key_of: dict[str, str] = {}
    for key, definition in known.merged().items():
        prior_key_of.setdefault(source_identity(definition), key)
    taken = set(known.keys())

    mapping: dict[str, str] = {}
    dropped: set[str] = set()
    for old, new in assign_keys(new_defs).items():
        identity = source_identity(new_defs[old])
        if identity in prior_key_of:
            mapping[old] = prior_key_of[identity]
            dropped.add(old)
        elif new in taken:
            mapping[old] = _key(identity, LONG)
        else:
            mapping[old] = new

    def dropped_definition(line: str) -> bool:
        m = _DEF_LINE.match(line)
        return bool(m) and m.group(1) in dropped

    kept_lines = [line for line in body.split("\n") if not dropped_definition(line)]
    return _MARKER.sub(lambda m: f"[^{mapping.get(m.group(1), m.group(1))}]", "\n".join(kept_lines))


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

    content = normalize_section_breaks(content)
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

    body = rekey_appended(prior, content.strip())
    # The appended body is a whole research file in its own right, with its own
    # H1 and its own "### Citations" heading. Demote the H1 so the merged file
    # keeps one top-level heading, and leave the citations block alone — the
    # assembler reads definitions wherever they appear.
    body = re.sub(r"^#\s+", "### ", body, count=1, flags=re.MULTILINE)

    merged = (
        prior.rstrip()
        + "\n\n***\n\n"
        + stamp_for(slug, version)
        + f"\n\n{heading}\n\n"
        + body
        + "\n"
    )
    path.write_text(merged)
    return "appended"


AUGMENT_SLUG = "augment"


def append_augmentation(path: Path, content: str, *, run_version: str, new_sources: int) -> str:
    """
    Append research synthesized from net-new sources to an existing section file.

    The unframed counterpart of the frame-extend path, per
    context-v/specs/Reuse-and-Augment-Research-Across-Runs.md: when a section's
    curated sources only grew, the new sources are synthesized on their own and
    added beneath what is already recorded, stamped `frame=augment`, rather than
    regenerating a file whose existing findings are still true.
    """
    content = normalize_section_breaks(content)
    prior = path.read_text() if path.exists() else ""
    if not prior.strip():
        path.write_text(content)
        return "written"
    version = run_version or "unversioned"
    if has_block(prior, AUGMENT_SLUG, version):
        return "skipped-duplicate"
    body = re.sub(r"^#\s+", "### ", rekey_appended(prior, content.strip()), count=1, flags=re.MULTILINE)
    noun = "source" if new_sources == 1 else "sources"
    path.write_text(
        prior.rstrip()
        + "\n\n***\n\n"
        + stamp_for(AUGMENT_SLUG, version)
        + f"\n\n## Added from {new_sources} new {noun}\n\n"
        + body
        + "\n"
    )
    return "appended"

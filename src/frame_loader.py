"""
Resolve a thesis frame from disk and validate it against the active outline.

The validation is the point. A frame names sections, and if it names one the
outline does not declare, the run must fail at load rather than silently skip a
section the operator believed was being reframed. Cross-version filename drift
is real in this tree — v0.0.3 wrote `07-risks--what-could-go-wrong.md` while the
outline declares `07-risks.md` — so the loader resolves drift and frames only
ever key off the outline contract.

See context-v/specs/Thesis-Frames-And-The-Re-Angle-Run.md.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .schemas.frame_schema import (
    PROSE_DIRECTIVES,
    RESEARCH_DIRECTIVES,
    STANCES,
    EvidenceDoc,
    SectionDirective,
    ThesisFrame,
)


class FrameError(ValueError):
    """A frame that cannot be trusted to drive a run."""


def frames_dir_for(firm: Optional[str], deal: str, root: Optional[Path] = None) -> Path:
    root = Path(root or ".")
    if firm:
        return root / "io" / firm / "deals" / deal / "frames"
    return root / "frames"


def _slugify(stem: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", stem.lower()).strip("-")


def _parse_directive(raw: Any, section: str) -> SectionDirective:
    """
    Accept the two-axis mapping, and also a bare string as a shorthand for a
    prose directive with additive research — `05-offering.md: amend` means
    {research: extend, prose: amend}, because a frame that bothers to name a
    section almost always has new evidence for it.
    """
    if isinstance(raw, str):
        prose = raw.strip()
        if prose not in PROSE_DIRECTIVES:
            raise FrameError(
                f"affects['{section}']: unknown prose directive {prose!r}. "
                f"Expected one of {sorted(PROSE_DIRECTIVES)}."
            )
        research = "reuse" if prose == "unchanged" else "extend"
        return SectionDirective(research=research, prose=prose)

    if not isinstance(raw, dict):
        raise FrameError(
            f"affects['{section}'] must be a mapping with `research` and `prose`, "
            f"or a bare prose directive string. Got {type(raw).__name__}."
        )

    research = str(raw.get("research", "reuse")).strip()
    prose = str(raw.get("prose", "unchanged")).strip()
    if research not in RESEARCH_DIRECTIVES:
        raise FrameError(
            f"affects['{section}'].research: unknown directive {research!r}. "
            f"Expected one of {sorted(RESEARCH_DIRECTIVES)}."
        )
    if prose not in PROSE_DIRECTIVES:
        raise FrameError(
            f"affects['{section}'].prose: unknown directive {prose!r}. "
            f"Expected one of {sorted(PROSE_DIRECTIVES)}."
        )
    return SectionDirective(research=research, prose=prose)


def parse_frame(data: Dict[str, Any], *, source_path: Optional[str] = None,
                fallback_slug: str = "") -> ThesisFrame:
    """Build a ThesisFrame from raw YAML. Structure only; no outline check yet."""
    if not isinstance(data, dict):
        raise FrameError("Frame file must contain a YAML mapping.")

    name = str(data.get("name") or "").strip()
    if not name:
        raise FrameError("Frame is missing a `name`.")

    premise = str(data.get("premise") or "").strip()
    if not premise:
        raise FrameError(
            f"Frame {name!r} is missing a `premise`. The premise is the paragraph "
            "every affected section must be consistent with; a frame without one "
            "cannot constrain anything."
        )

    stance = str(data.get("stance") or "re-sequencing").strip()
    if stance not in STANCES:
        raise FrameError(
            f"Frame {name!r}: unknown stance {stance!r}. Expected one of {sorted(STANCES)}."
        )

    evidence: List[EvidenceDoc] = []
    for item in data.get("evidence") or []:
        if isinstance(item, str):
            evidence.append(EvidenceDoc(path=item))
        elif isinstance(item, dict) and item.get("path"):
            evidence.append(EvidenceDoc(path=str(item["path"]), note=str(item.get("note", "")).strip()))
        else:
            raise FrameError(f"Frame {name!r}: each `evidence` entry needs a `path`.")

    caveats = [str(c).strip() for c in (data.get("caveats") or []) if str(c).strip()]

    questions: Dict[str, List[str]] = {}
    for section, qs in (data.get("questions") or {}).items():
        if isinstance(qs, str):
            qs = [qs]
        questions[str(section)] = [str(q).strip() for q in qs if str(q).strip()]

    affects = {
        str(section): _parse_directive(raw, str(section))
        for section, raw in (data.get("affects") or {}).items()
    }

    notes = {str(k): str(v).strip() for k, v in (data.get("directive_notes") or {}).items()}

    return ThesisFrame(
        name=name,
        slug=str(data.get("slug") or fallback_slug or _slugify(name)),
        stance=stance,
        premise=premise,
        evidence=evidence,
        caveats=caveats,
        questions=questions,
        affects=affects,
        directive_notes=notes,
        source_path=source_path,
    )


def validate_against_outline(frame: ThesisFrame, outline_filenames: List[str]) -> None:
    """
    Every section a frame names must be declared by the active outline.

    Fails loudly rather than skipping: a frame that names a section the outline
    does not have is either a typo or a taxonomy change, and both are things the
    operator must see before the run spends money.
    """
    valid = set(outline_filenames)
    for label, keys in (("affects", frame.affects), ("questions", frame.questions),
                        ("directive_notes", frame.directive_notes)):
        unknown = sorted(set(keys) - valid)
        if unknown:
            raise FrameError(
                f"Frame {frame.slug!r}: {label} names section(s) the active outline does "
                f"not declare: {unknown}. Outline declares: {sorted(valid)}. "
                "Frames key off the outline contract, never the filenames a previous "
                "version happened to write."
            )


def load_frame(slug: str, *, firm: Optional[str], deal: str,
               outline_filenames: Optional[List[str]] = None,
               root: Optional[Path] = None) -> ThesisFrame:
    """Load `<frames_dir>/<slug>.yaml`, validated against the outline when given."""
    directory = frames_dir_for(firm, deal, root)
    path = directory / f"{slug}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in directory.glob("*.yaml")) if directory.exists() else []
        raise FrameError(
            f"No frame {slug!r} at {path}. "
            + (f"Available frames: {available}." if available else
               f"No frames directory yet — create {directory}/{slug}.yaml.")
        )

    frame = parse_frame(
        yaml.safe_load(path.read_text()) or {},
        source_path=str(path),
        fallback_slug=slug,
    )
    if outline_filenames:
        validate_against_outline(frame, outline_filenames)
    return frame


def list_frames(firm: Optional[str], deal: str, root: Optional[Path] = None) -> List[str]:
    directory = frames_dir_for(firm, deal, root)
    return sorted(p.stem for p in directory.glob("*.yaml")) if directory.exists() else []

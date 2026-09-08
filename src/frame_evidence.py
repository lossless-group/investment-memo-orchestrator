"""
Ingest a thesis frame's evidence documents into the codified research corpus.

A frame introduces documents the deal has never seen — the Prudential proposal
is not in ProfileHealth's dataroom and is not in its curated Sources.md. Without
this step a framed run writes prose about evidence the research layer has no
record of, which is the same durability failure that loses citations on
re-assembly: the claim exists only in prose, and prose is regenerated.

So frame evidence becomes a first-class curated source before any section is
researched. It is synthesised as a SourceEntry with a `file://` URL, tagged for
exactly the sections the frame puts in scope, and ranked ahead of the standing
corpus — the frame's own documents are what the thesis rests on.

See context-v/specs/Thesis-Frames-And-The-Re-Angle-Run.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .curation.sources_md import SourceEntry


def _read_document(path: Path) -> Optional[str]:
    """
    Read an evidence document to markdown-ish text.

    Markdown and text are read directly. Anything else goes through the shared
    curation fetcher, which already knows how to pull text out of .docx/.pptx/
    .xlsx and OCR image PDFs — reimplementing that here would give frame
    evidence a second, worse reader.
    """
    if path.suffix.lower() in {".md", ".markdown", ".txt"}:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    try:
        from .curation.fetch import fetch_local_file
        result = fetch_local_file(path, url=path.as_uri())
        return (result or {}).get("markdown")
    except Exception:  # noqa: BLE001 - evidence must never break a run
        return None


def resolve_evidence_path(rel_path: str, deal_dir: Optional[Path]) -> Optional[Path]:
    """Frame evidence paths are deal-relative; absolute paths pass through."""
    candidate = Path(rel_path)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    if deal_dir:
        resolved = Path(deal_dir) / rel_path
        if resolved.exists():
            return resolved
    return candidate if candidate.exists() else None


def ingest_frame_evidence(
    frame: Any,
    deal_dir: Optional[Path],
    fetched: Dict[str, Dict[str, Any]],
) -> Tuple[List[SourceEntry], List[str]]:
    """
    Turn a frame's evidence into curated sources and load their content.

    Mutates `fetched` in place — the same dict the codified researcher fills
    from Sources.md — so downstream synthesis treats frame evidence exactly like
    any other approved source and needs no special case.

    Returns (entries, problems). Problems are reported rather than raised: a
    missing evidence file should make a loud run, not a dead one, because the
    rest of the frame is still worth applying.
    """
    if frame is None or not getattr(frame, "evidence", None):
        return [], []

    entries: List[SourceEntry] = []
    problems: List[str] = []

    # Tag evidence for every section the frame actually researches. A frame's
    # documents are relevant to its own scope by definition; tagging them for
    # sections the frame leaves alone would pull new evidence into prose the
    # operator asked to preserve.
    in_scope = [
        name for name, directive in getattr(frame, "affects", {}).items()
        if directive.researches
    ]

    for doc in frame.evidence:
        path = resolve_evidence_path(doc.path, deal_dir)
        if path is None:
            problems.append(f"evidence not found: {doc.path}")
            continue

        content = _read_document(path)
        if not content or not content.strip():
            problems.append(f"evidence unreadable or empty: {doc.path}")
            continue

        url = path.resolve().as_uri()
        entry = SourceEntry(
            url=url,
            sections=list(in_scope),
            rank=0,  # ahead of the standing corpus — the thesis rests on these
            sensitivity="internal_only",
            note=(doc.note or f"Frame evidence for '{frame.name}'").strip(),
            title=path.stem.replace("-", " ").replace("_", " "),
            local_path=str(path),
        )
        entries.append(entry)
        fetched[url] = {
            "url": url,
            "title": entry.title,
            "markdown": content,
            "via": "frame-evidence",
        }

    return entries, problems

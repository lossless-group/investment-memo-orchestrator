"""
Loader for the per-deal `inputs/Sources.md` codified-source workflow.

A deal's `Sources.md` is a markdown file with YAML frontmatter that
encodes the analyst's hand-curated source list. When present and
`mode: codified`, the research agent skips broad search entirely and
uses only these URLs as the per-memo corpus.

This matches the team's convention of frontmatter-for-machines, body-for-
humans — the structured source list lives in frontmatter (parseable by
the loader), and the analyst's notes about how the list was built /
what was rejected / what's still missing live in the markdown body (the
"institutional memory" layer that prevents re-adding the same junk on
the next iteration).

Schema (frontmatter):

    mode: codified                       # "codified" locks the run; absent or "search" = legacy broad search
    deal: ChromaDB
    firm: alpha-partners
    date_curated_initial: 2026-05-22
    date_curated_current: 2026-05-22
    at_semantic_version: 0.0.0.1
    curated_by:
      - Michael Staton
    augmented_with: Claude Code (Opus 4.7)
    sources:
      - url: https://www.trychroma.com/blog/series-a
        sections: [funding-terms, team]
        rank: 1
        sensitivity: citable_externally
        note: "Series A announcement; primary"
      - url: https://github.com/chroma-core/chroma
        sections: [technology-product, traction-milestones]
        rank: 1
        sensitivity: citable_externally
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SourceEntry:
    """A single curated source from `Sources.md`."""
    url: str
    sections: List[str] = field(default_factory=list)    # section tags this source supports
    rank: int = 1                                         # 1 = primary; higher = lower priority
    sensitivity: str = "citable_externally"               # or "internal_only"
    note: str = ""                                        # analyst's free-form note


@dataclass
class SourcesMd:
    """Parsed `inputs/Sources.md` for a single deal."""
    mode: str = "search"
    deal: str = ""
    firm: str = ""
    sources: List[SourceEntry] = field(default_factory=list)
    body: str = ""                                        # analyst notes (markdown)
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)
    source_path: Optional[Path] = None


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Split a markdown file's YAML frontmatter from its body.

    Returns `({}, original_content)` if the file has no frontmatter or
    the frontmatter is malformed — so callers can fall back gracefully.
    """
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    try:
        import yaml
        metadata = yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}, content
    if not isinstance(metadata, dict):
        return {}, content
    body = parts[2].lstrip("\n")
    return metadata, body


def load_sources_md(deal_inputs_dir: Path) -> Optional[SourcesMd]:
    """
    Load `inputs/Sources.md` from a deal directory.

    Returns None when:
      - The file is absent (legacy broad-search pipeline applies).
      - The file exists but lacks frontmatter or fails to parse.

    Never raises — failures are silent and fall through to legacy behavior.
    """
    if not deal_inputs_dir or not deal_inputs_dir.exists():
        return None

    path = deal_inputs_dir / "Sources.md"
    if not path.exists():
        return None

    try:
        content = path.read_text()
    except Exception:
        return None

    metadata, body = parse_frontmatter(content)
    if not metadata:
        return None

    source_entries: List[SourceEntry] = []
    for raw in (metadata.get("sources") or []):
        if not isinstance(raw, dict):
            continue
        url = (raw.get("url") or "").strip()
        if not url:
            continue
        sections = raw.get("sections") or []
        if isinstance(sections, str):
            sections = [sections]
        try:
            rank = int(raw.get("rank", 1))
        except (TypeError, ValueError):
            rank = 1
        source_entries.append(SourceEntry(
            url=url,
            sections=[str(s) for s in sections],
            rank=rank,
            sensitivity=str(raw.get("sensitivity", "citable_externally")),
            note=str(raw.get("note", "")),
        ))

    return SourcesMd(
        mode=str(metadata.get("mode", "search")).strip().lower(),
        deal=str(metadata.get("deal", "")),
        firm=str(metadata.get("firm", "")),
        sources=source_entries,
        body=body,
        raw_frontmatter=metadata,
        source_path=path,
    )


def is_codified(sources_md: Optional[SourcesMd]) -> bool:
    """Whether `Sources.md` instructs the pipeline to use codified mode."""
    return sources_md is not None and sources_md.mode == "codified"


def sources_for_section(
    sources_md: SourcesMd,
    section_name: str,
    section_number: Optional[int] = None,
) -> List[SourceEntry]:
    """
    Filter the curated source list to entries tagged for a given section.

    Tag matching is forgiving — a source tagged `team` matches a section
    named `"Team"`, `"04-team"`, or `"04 Team"`. The analyst can use
    short slugs in Sources.md without worrying about exact section-file
    naming.

    Args:
        sources_md: Parsed Sources.md.
        section_name: Outline section name (e.g., "Team", "Market Context").
        section_number: Optional 1-based section number for extra-strict
            matching against tags like "01-overview".

    Returns:
        Matching entries, sorted by rank (primary sources first).
    """
    if not sources_md or not sources_md.sources:
        return []

    target = _normalize_tag(section_name)
    number_strs = []
    if section_number is not None:
        number_strs = [f"{section_number:02d}", str(section_number)]

    matches: List[SourceEntry] = []
    for entry in sources_md.sources:
        for tag in entry.sections:
            tag_norm = _normalize_tag(tag)
            if (
                tag_norm == target
                or tag_norm in target
                or target in tag_norm
                or any(n in tag_norm for n in number_strs)
            ):
                matches.append(entry)
                break

    return sorted(matches, key=lambda e: e.rank)


def _normalize_tag(s: str) -> str:
    """
    Lowercase, strip, replace whitespace and underscores with hyphens —
    so 'Market Context', 'market-context', and 'market_context' all
    match the same tag.
    """
    return (s or "").strip().lower().replace(" ", "-").replace("_", "-")

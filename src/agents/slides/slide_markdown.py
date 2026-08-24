"""
Slide Markdown Emitter

Renders one stenographer record as the per-slide document.

The document has a deliberate order: machine-readable identity in frontmatter,
then a human description of the layout, then the verbatim content as typed JSON,
then opinion — the agent's, and below it a section reserved for the reader's.

That ordering is the whole editorial contract. Transcription is what the
stenographer is for and it comes first; commentary is useful but secondary, and
keeping it below the fold in its own section means a later reader can always tell
which parts of the file the deck said and which parts an agent thought.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional

import yaml

from .slide_schemas import LAYOUT_PATTERNS


# The section a person writes in. Never overwritten on re-analysis: an analyst's
# note is the one thing in the file no agent produced and no agent may discard.
USER_COMMENTARY_HEADING = "# Users' Commentary"
_USER_PLACEHOLDER = "*No commentary yet.*"


def _yaml_block(data: Dict[str, Any]) -> str:
    """Frontmatter with keys in declaration order rather than alphabetized."""
    return yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    ).rstrip()


def build_frontmatter(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Assemble frontmatter in a fixed, meaningful order.

    Grouped identity → dates → imagery → content → provenance, because the file
    is read by people as often as by machines and a grouped block is scannable.
    """
    fm: Dict[str, Any] = {}

    # --- identity and lineage ---
    for key in ("company", "round", "deck_family", "deck_variant", "deck_version",
                "authored_by", "slide_uid", "lineage_id", "content_hash",
                "index_position", "reveal_sequence", "reveal_canonical",
                "reveal_confirmed_by_vision", "reveal_evidence",
                "derived_from", "supersedes"):
        if key in record:
            fm[key] = record[key]

    # --- dates ---
    for key in ("date_on_deck", "date_source", "date_confidence",
                "date_received", "date_first_analyzed", "date_last_analyzed"):
        if key in record:
            value = record[key]
            fm[key] = value.isoformat() if isinstance(value, date) else value
    if record.get("dates_mentioned"):
        fm["dates_mentioned"] = record["dates_mentioned"]

    # --- imagery ---
    for key in ("slide_image_local", "slide_image_cdn", "slide_image_alt"):
        if key in record:
            fm[key] = record[key]

    # --- content ---
    for key in ("slide_type", "core_message", "tags", "layout_rows",
                "layout_pattern", "transcription_fidelity", "claims_to_verify"):
        if key in record:
            fm[key] = record[key]

    # --- provenance ---
    for key in ("augmented_with", "path_to_deck", "extraction_warnings"):
        if key in record:
            fm[key] = record[key]

    return fm


def _layout_prose(record: Dict[str, Any]) -> str:
    """Describe the layout in words, then row by row."""
    rows: List[Dict[str, Any]] = record.get("layout_description", []) or []
    pattern = record.get("layout_pattern", "single")
    count = record.get("layout_rows") or len(rows) or 1

    spelled = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(count, str(count))
    pattern_note = LAYOUT_PATTERNS.get(pattern, pattern)

    lines = [
        "# Layout",
        "",
        f"The layout of the content body is a {spelled} row {pattern} arrangement "
        f"— {pattern_note.lower()} — composed of",
    ]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. {row.get('summary', 'Unlabelled region')}")
    if not rows:
        lines.append("1. A single undivided region")
    lines.append("")

    for i, row in enumerate(rows, start=1):
        label = row.get("label") or f"Row {i}"
        position = row.get("position", "")
        heading = f"## Row {i}, {position}".rstrip(", ") if position else f"## Row {i}, {label}"
        lines.append(heading)
        lines.append("")
        if row.get("headingTxt"):
            lines.append(f'Heading: "{row["headingTxt"]}"')
        if row.get("subheadingTxt"):
            lines.append(f'Subheading: "{row["subheadingTxt"]}"')
        if row.get("note"):
            lines.append("")
            lines.append(row["note"])
        lines.append("")

    return "\n".join(lines)


def render_slide_markdown(record: Dict[str, Any],
                          existing_user_commentary: Optional[str] = None) -> str:
    """
    Render the full document.

    Args:
        record: The stenographer's assembled record.
        existing_user_commentary: Prior human commentary, read off the file being
            replaced. Passed back in so re-analysis never destroys it.
    """
    parts: List[str] = [
        "---",
        _yaml_block(build_frontmatter(record)),
        "---",
        "",
        _layout_prose(record),
    ]

    content = record.get("content") or {}
    parts += [
        "```json-content",
        json.dumps(content, indent=2, ensure_ascii=False),
        "```",
        "",
    ]

    metrics = record.get("metrics") or {}
    if metrics:
        parts += [
            "```json-metrics",
            json.dumps(metrics, indent=2, ensure_ascii=False),
            "```",
            "",
        ]

    parts += ["# Analyst Agent Commentary", ""]
    commentary = (record.get("analyst_commentary") or "").strip()
    parts += [commentary or "*No commentary generated.*", ""]

    # Warnings live with the commentary rather than in frontmatter prose so a
    # reader meets them while forming a view, not after.
    warnings = record.get("extraction_warnings") or []
    if warnings:
        parts += ["**Transcription caveats:**", ""]
        parts += [f"- {w}" for w in warnings]
        parts.append("")

    parts += [USER_COMMENTARY_HEADING, ""]
    parts.append((existing_user_commentary or "").strip() or _USER_PLACEHOLDER)
    parts.append("")

    return "\n".join(parts)


def extract_user_commentary(markdown: str) -> Optional[str]:
    """
    Recover the human-written section from an existing document.

    Re-analysis rewrites everything an agent produced. This is the one part it
    must carry forward, so it is read before the file is replaced.
    """
    if USER_COMMENTARY_HEADING not in markdown:
        return None
    body = markdown.split(USER_COMMENTARY_HEADING, 1)[1].strip()
    if not body or body == _USER_PLACEHOLDER:
        return None
    return body


def render_deck_manifest(deck: Dict[str, Any], slides: List[Dict[str, Any]]) -> str:
    """
    ``deck.yaml`` — the deck-level record that sits beside the slide documents.

    Holds what belongs to the deck rather than to any one slide: where it came
    from, how it was dated, what it is a version or fork of, and the slide index.
    """
    manifest = {
        "deck_family": deck.get("deck_family"),
        "company": deck.get("company"),
        "round": deck.get("round"),
        "deck_variant": deck.get("deck_variant"),
        "deck_version": deck.get("deck_version"),
        "authored_by": deck.get("authored_by"),
        "date_on_deck": deck.get("date_on_deck"),
        "date_source": deck.get("date_source"),
        "date_confidence": deck.get("date_confidence"),
        "date_notes": deck.get("date_notes", []),
        "source_file": deck.get("source_file"),
        "source_sha256": deck.get("source_sha256"),
        "page_count": deck.get("page_count"),
        "logical_slide_count": len(slides),
        "reveal_groups": deck.get("reveal_groups", []),
        "relationships": deck.get("relationships", []),
        "analyzed_with": deck.get("analyzed_with"),
        "date_first_analyzed": deck.get("date_first_analyzed"),
        "date_last_analyzed": deck.get("date_last_analyzed"),
        "slides": [
            {
                "index": s.get("index_position"),
                "file": s.get("filename"),
                "slide_type": s.get("slide_type"),
                "lineage_id": s.get("lineage_id"),
                "core_message": s.get("core_message"),
                "slide_image_cdn": s.get("slide_image_cdn"),
            }
            for s in slides
        ],
    }
    return _yaml_block(manifest) + "\n"

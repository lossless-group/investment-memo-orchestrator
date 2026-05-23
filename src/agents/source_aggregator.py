"""
Source Aggregator Agent.

Sits between `cleanup_research` (Phase 1 URL validation gate) and
`draft` (writer) in the workflow. Its job is to turn the broad-search
research output into an analyst-reviewable `Sources.md` draft, then
HALT the pipeline so the analyst can rank/prune/x-out before the
writer ever touches the corpus.

Why halt: the whole premise of the human-curated-source workflow (per
the exploration at
`memopop-ai/context-v/explorations/Human-Curated-Source-Sets-and-Per-Firm-RAG-for-Memo-Narrative.md`)
is that the writer composes from sources *the analyst approved*, not
from sources *the broad-search providers happened to surface*. If the
writer runs before curation, the curation step is purely cosmetic.

Two-phase workflow:

  PHASE 1 (this run, broad search):
    deck → research → section_research (broad) → cleanup_research →
      source_aggregator → writes outputs/<v>/Sources-aggregated.md → HALT

  Analyst opens outputs/<v>/Sources-aggregated.md, reorders rows,
  x-es out junk, copies the file to inputs/Sources.md, sets
  `mode: codified`, saves.

  PHASE 2 (re-run with curated input):
    deck → research → section_research (codified short-circuit; uses
      inputs/Sources.md) → cleanup_research → source_aggregator
      (detects codified mode; passes through with no halt) →
      draft → enrichment → finalize.

The aggregator deliberately does NOT halt when codified mode is active —
otherwise the analyst's approved Sources.md would never get to the writer.
"""

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from ..state import MemoState
from ..curation import is_codified, load_sources_md


def source_aggregator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Aggregate URLs from broad-search research into a draft Sources.md
    for analyst review, then HALT — unless codified mode is already
    active, in which case pass through.
    """
    from ..utils import get_output_dir_from_state
    output_dir = get_output_dir_from_state(state)

    # ───── Codified-mode short-circuit ─────
    # If the deal already has an approved Sources.md, the analyst has
    # done their job; let the pipeline proceed to the writer.
    company_name = state.get("company_name") or ""
    firm = state.get("firm") or ""
    inputs_dir = (
        Path("io") / firm / "deals" / company_name / "inputs"
        if firm
        else Path("data")
    )
    sources_md = load_sources_md(inputs_dir)
    if is_codified(sources_md):
        print(
            f"📚 Source aggregator: codified Sources.md present "
            f"({len(sources_md.sources)} curated URLs) — passing through to writer."
        )
        return {
            "messages": [
                f"Source aggregator passed through (codified mode: "
                f"{len(sources_md.sources)} curated sources)"
            ]
        }

    # ───── Aggregation path ─────
    print("\n📋 Source Aggregator — collecting URLs from broad-search research...")

    research_dir = output_dir / "1-research"
    if not research_dir.exists():
        print("  ⚠️  No 1-research/ directory — nothing to aggregate. Continuing.")
        return {"messages": ["Source aggregator: no research dir to walk"]}

    # Lazy import the citation parser + validator to avoid circular imports at module load.
    from .remove_invalid_sources import (
        CONTENT_INVALID_CODES,
        INVALID_HTTP_CODES,
        VERIFIED_GATED,
        extract_citation_details,
        validate_url,
        _extract_host,
        _is_gated_publisher,
    )

    # Walk per-section research files; collect (file_name → section_label, citation rows)
    section_files = sorted(research_dir.glob("*-research.md"))
    if not section_files:
        print("  ⚠️  No *-research.md files — nothing to aggregate. Continuing.")
        return {"messages": ["Source aggregator: no research files to walk"]}

    # url → {title, publisher, published_date, sections, occurrence_count}
    by_url: Dict[str, Dict[str, Any]] = {}
    for f in section_files:
        section_label = _section_label_from_filename(f.name)
        rows = extract_citation_details(f.read_text(), f.name, source_path=f)
        for row in rows:
            url = (row.get("url") or "").strip()
            if not url:
                continue
            entry = by_url.setdefault(url, {
                "title": "",
                "publisher": "",
                "published_date": "",
                "sections": set(),
                "occurrence_count": 0,
            })
            # First non-empty title/publisher/date wins
            entry["title"] = entry["title"] or row.get("title", "")
            entry["publisher"] = entry["publisher"] or row.get("publisher", "")
            entry["published_date"] = entry["published_date"] or row.get("published_date", "")
            entry["sections"].add(section_label)
            entry["occurrence_count"] += 1

    if not by_url:
        print("  ⚠️  No URLs found in research files. Continuing.")
        return {"messages": ["Source aggregator: no URLs in research"]}

    print(f"  Found {len(by_url)} unique URL(s) across {len(section_files)} section research file(s)")
    print(f"  Validating each URL (parallel, 10 workers)...")

    # Parallel validation
    from concurrent.futures import ThreadPoolExecutor, as_completed
    verdicts: Dict[str, Tuple[int, str]] = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(validate_url, url): url for url in by_url}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                _, code, status = future.result()
            except Exception as e:
                code, status = 0, f"Error: {str(e)[:80]}"
            verdicts[url] = (code, status)

    # Drop hard-fails. Keep paywalled-but-reputable as `verified-gated`.
    surviving: List[Dict[str, Any]] = []
    dropped = 0
    for url, info in by_url.items():
        code, status = verdicts.get(url, (0, "not checked"))
        if code in CONTENT_INVALID_CODES or code in INVALID_HTTP_CODES:
            dropped += 1
            continue
        info["url"] = url
        info["verdict_code"] = code
        info["verdict_status"] = status
        info["sections"] = sorted(info["sections"])
        info["is_gated"] = (code == VERIFIED_GATED) or _is_gated_publisher(url)
        surviving.append(info)

    # Heuristic initial rank — the analyst will reorder, this is just a
    # sensible default sort.
    #   tier 1: verified-accessible on the gated-publisher allow-list
    #   tier 2: verified-accessible (non-allow-list)
    #   tier 3: verified-gated (paywalled-but-reputable)
    #   tier 4: anything else
    # Then within tier, descending by occurrence count (URLs cited across
    # many sections rank higher).
    def _rank(entry: Dict[str, Any]) -> Tuple[int, int]:
        code = entry["verdict_code"]
        on_allow_list = entry["is_gated"] or _is_gated_publisher(entry["url"])
        if 200 <= code < 300 and on_allow_list:
            tier = 1
        elif 200 <= code < 300:
            tier = 2
        elif code == VERIFIED_GATED:
            tier = 3
        else:
            tier = 4
        return (tier, -entry["occurrence_count"])

    surviving.sort(key=_rank)

    # Write to outputs/<version>/Sources-aggregated.md
    aggregated_path = output_dir / "Sources-aggregated.md"
    aggregated_path.write_text(
        _build_aggregated_sources_md(
            company_name=company_name,
            firm=firm,
            survivors=surviving,
            dropped_count=dropped,
            section_files=[f.name for f in section_files],
        )
    )

    print(
        f"  ✓ Kept {len(surviving)} URL(s); dropped {dropped} (hard-fail or hallucination)."
    )
    print(f"  📝 Aggregated draft written: {aggregated_path}")
    print()
    print("─" * 70)
    print("🛑 HALTING PIPELINE for analyst curation.")
    print()
    print("Next steps:")
    print(f"  1. Open: {aggregated_path}")
    print("  2. Reorder rows (top = primary), x-out sources that aren't quality")
    print("     or don't have the info you want, fill in any analyst notes.")
    print(f"  3. Copy or move the curated file to: {inputs_dir / 'Sources.md'}")
    print("     (or edit it in place and rename) — and set `mode: codified`.")
    print("  4. Re-run the pipeline. The codified-mode researcher will use")
    print("     ONLY your approved sources; no broad search, no model invention.")
    print("─" * 70)

    # Halt the pipeline. Raises SystemExit(0); LangGraph and the orchestrator's
    # main.py propagate this cleanly.
    sys.exit(0)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────


def _section_label_from_filename(filename: str) -> str:
    """
    Turn '02-category-leadership-research.md' into 'category-leadership'.

    Strips the 2-digit prefix and the '-research.md' suffix, leaving the
    section slug the analyst will recognize and that matches `sections:`
    tags in Sources.md.
    """
    name = filename
    if name.endswith("-research.md"):
        name = name[: -len("-research.md")]
    elif name.endswith(".md"):
        name = name[: -len(".md")]
    parts = name.split("-", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1]
    return name


def _build_aggregated_sources_md(
    *,
    company_name: str,
    firm: str,
    survivors: List[Dict[str, Any]],
    dropped_count: int,
    section_files: List[str],
) -> str:
    """Render the aggregated Sources.md content with YAML frontmatter + analyst-notes scaffold."""
    today = datetime.now().date().isoformat()
    lines: List[str] = []
    lines.append("---")
    lines.append("# Aggregated source draft — produced by the pipeline's broad-search pass.")
    lines.append("#")
    lines.append("# This file is the analyst's worksheet. Reorder the `sources:` list")
    lines.append("# (top = primary). Delete entries that are low quality, irrelevant,")
    lines.append("# or redundant. When you're ready, change `mode: aggregated` to")
    lines.append("# `mode: codified`, move/copy this file to inputs/Sources.md, and")
    lines.append("# re-run the pipeline. The codified-mode researcher will then use")
    lines.append("# ONLY these URLs — no broad search, no model invention.")
    lines.append("#")
    lines.append(f"# Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"# Walked: {', '.join(section_files)}")
    lines.append(f"# Dropped (hard-fail / hallucination): {dropped_count}")
    lines.append("")
    lines.append("mode: aggregated")
    lines.append(f"deal: {company_name}")
    if firm:
        lines.append(f"firm: {firm}")
    lines.append(f"date_curated_initial: {today}")
    lines.append(f"date_curated_current: {today}")
    lines.append("at_semantic_version: 0.0.0.1")
    lines.append("curated_by:")
    lines.append("  - (TODO — fill in your name)")
    lines.append("augmented_with: Claude Code (Opus 4.7)")
    lines.append("")
    lines.append("# Sorted by pipeline heuristic: verified+reputable first, then by")
    lines.append("# how many sections the URL was cited in. The analyst's reorder is")
    lines.append("# what actually matters — this is just a starting point.")
    lines.append("sources:")

    for entry in survivors:
        url = entry["url"]
        title = (entry.get("title") or "").replace('"', "'")
        publisher = (entry.get("publisher") or "").replace('"', "'")
        published_date = entry.get("published_date") or ""
        sections = entry.get("sections") or []
        occurrence_count = entry.get("occurrence_count", 0)
        verdict = entry.get("verdict_status") or ""
        is_gated = entry.get("is_gated", False)

        lines.append(f"  - url: {url}")
        if title:
            lines.append(f"    title: \"{title}\"")
        if publisher:
            lines.append(f"    publisher: \"{publisher}\"")
        if published_date:
            lines.append(f"    published_date: {published_date}")
        if sections:
            sections_inline = "[" + ", ".join(sections) + "]"
            lines.append(f"    sections: {sections_inline}")
        lines.append("    rank: 1")
        lines.append(f"    sensitivity: {'internal_only' if is_gated else 'citable_externally'}")
        if verdict:
            lines.append(f"    # verdict: {verdict}  (informational; the analyst doesn't need to keep this)")
        if occurrence_count > 1:
            lines.append(f"    # cited in {occurrence_count} section research file(s)")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"# Aggregated Sources — {company_name}")
    lines.append("")
    lines.append("## How this list was built")
    lines.append("")
    lines.append("This is the pipeline's broad-search output, post-validation. The aggregator")
    lines.append("walked the per-section research files, deduped by URL across sections, ran")
    lines.append("each URL through the Phase 1 validator, dropped hard-fails, and sorted")
    lines.append("survivors by a simple tier heuristic (reputable + verified first, then by")
    lines.append("how many sections each URL was cited in).")
    lines.append("")
    lines.append("**Your job from here:** read the list, drop the junk, reorder so the most")
    lines.append("important sources are at the top of each section's bucket. When ready,")
    lines.append("set `mode: codified` in the frontmatter and save this file (renamed to")
    lines.append("`Sources.md`) into the deal's `inputs/` directory.")
    lines.append("")
    lines.append("## Excluded — examined and rejected")
    lines.append("")
    lines.append("Record what you looked at and *why you dropped it*, so the next iteration")
    lines.append("(or another analyst on this deal) doesn't re-add the same junk. This is the")
    lines.append("institutional-memory layer that re-runs lose otherwise.")
    lines.append("")
    lines.append("- (your notes here)")
    lines.append("")
    lines.append("## Open questions / coverage gaps")
    lines.append("")
    lines.append("Sections where the broad-search results were thin or missing entirely —")
    lines.append("these are the `<needs-source>` candidates and the right input to a future")
    lines.append("harvester's per-section query strategy.")
    lines.append("")
    lines.append("- (your notes here)")
    lines.append("")
    return "\n".join(lines)

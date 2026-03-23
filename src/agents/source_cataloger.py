"""
Source Cataloger Agent - Compiles per-section comprehensive source lists.

Creates {Section-Name}-Complete-Source-List.md files in 3-source-catalog/
that document every source encountered during the pipeline: found, verified,
included, excluded, and hallucinated.

This artifact is valuable for investment analysts who want to:
- See ALL sources the system discovered, not just the ones that made it to the final draft
- Follow up on sources that were excluded (e.g., paywalled McKinsey reports)
- Understand why certain sources were removed
- Use the source list as a starting point for their own research

Pipeline position: runs AFTER fact_correct, BEFORE validate.

Reads from:
- 1-research/*.md — Sources discovered during research phase
- 2-sections/*.md — Citations included in the final sections
- source-validation-log-*.json — URL validation results from cleanup gates
- 4-fact-check-verified.json — LLM verification results
- 4-corrections-log.json — Sources added during fact correction
"""

import json
import re
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from ..state import MemoState


def _extract_citations_with_details(content: str) -> List[Dict[str, str]]:
    """
    Extract citation definitions with full details from markdown content.

    Returns list of dicts: citation_num, url, title, full_definition
    """
    citations = []

    pattern = r'\[\^([a-zA-Z0-9_]+)\]:\s*(.+?)(?=\n\[\^|\n\n|\Z)'
    for match in re.finditer(pattern, content, re.DOTALL):
        citation_num = match.group(1)
        full_def = match.group(2).strip()

        url_match = re.search(r'\[([^\]]+)\]\((https?://[^)]+)\)', full_def)
        url = url_match.group(2) if url_match else ""
        title = url_match.group(1) if url_match else ""

        citations.append({
            "citation_num": citation_num,
            "url": url,
            "title": title,
            "full_definition": full_def
        })

    return citations


def _extract_inline_citation_nums(content: str) -> Set[str]:
    """Extract all inline citation reference numbers from content."""
    return set(re.findall(r'\[\^([a-zA-Z0-9_]+)\](?!:)', content))


def _map_sections_to_files(sections_dir: Path) -> Dict[str, Path]:
    """
    Build mapping from display section names to file paths.

    Returns dict like: {"Executive Summary": Path(...01-executive-summary.md)}
    """
    mapping = {}
    for f in sorted(sections_dir.glob("*.md")):
        # Convert filename to display name: "01-executive-summary.md" -> "Executive Summary"
        name = f.stem
        # Remove leading number prefix
        name = re.sub(r'^\d+[-_]', '', name)
        # Convert to title case
        display_name = name.replace('-', ' ').replace('_', ' ').title()
        mapping[display_name] = f
    return mapping


def _determine_source_status(
    url: str,
    validation_log: Dict[str, Dict],
    section_citation_nums: Set[str],
    section_citations: Dict[str, str],
    verified_claims: Dict[str, Dict],
    correction_sources: Set[str]
) -> str:
    """
    Determine the pipeline status of a source URL.

    Returns one of: included, excluded-invalid, excluded-uncertain,
    found-in-research, verified-by-llm, added-by-correction, hallucinated
    """
    # Check if URL was added during fact correction
    if url in correction_sources:
        return "added-by-correction"

    # Check validation log
    log_entry = validation_log.get(url, {})
    validation_status = log_entry.get("validation_status", "")

    if validation_status == "removed":
        http_code = log_entry.get("http_code", 0)
        if http_code == -1:
            return "hallucinated"
        return "excluded-invalid"

    # Check if included in final section
    for num, s_url in section_citations.items():
        if s_url == url and num in section_citation_nums:
            return "included"

    if validation_status == "uncertain":
        return "excluded-uncertain"

    if validation_status == "valid":
        return "found-valid-not-cited"

    return "found-in-research"


def source_cataloger_agent(state: MemoState) -> Dict[str, Any]:
    """
    Source Cataloger Agent - Compiles per-section comprehensive source lists.

    Args:
        state: Current memo state

    Returns:
        State updates with catalog summary
    """
    company_name = state["company_name"]

    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("⊘ Source catalog skipped - no output directory")
        return {"messages": ["Source catalog skipped - no output directory"]}

    sections_dir = output_dir / "2-sections"
    research_dir = output_dir / "1-research"
    catalog_dir = output_dir / "3-source-catalog"

    if not sections_dir.exists():
        print("⊘ Source catalog skipped - no sections directory")
        return {"messages": ["Source catalog skipped - no sections"]}

    print("\n" + "=" * 70)
    print(f"📚 COMPILING SOURCE CATALOG FOR {company_name}")
    print("=" * 70)

    catalog_dir.mkdir(exist_ok=True)

    # ── Load all available data sources ──────────────────────────────

    # 1. Load validation logs (from cleanup gates)
    validation_log_by_url: Dict[str, Dict] = {}
    for log_file in output_dir.glob("source-validation-log-*.json"):
        try:
            with open(log_file) as f:
                log_data = json.load(f)
            for source in log_data.get("sources", []):
                url = source.get("url", "")
                if url:
                    validation_log_by_url[url] = source
        except (json.JSONDecodeError, KeyError):
            pass

    print(f"  Loaded {len(validation_log_by_url)} sources from validation logs")

    # 2. Load fact-check verification results
    verified_claims: Dict[str, Dict] = {}
    verified_path = output_dir / "4-fact-check-verified.json"
    if verified_path.exists():
        try:
            with open(verified_path) as f:
                verified_data = json.load(f)
            for section in verified_data.get("fact_check_results", []):
                for detail in section.get("details", []):
                    v = detail.get("verification", {})
                    if v and v.get("source_url"):
                        verified_claims[v["source_url"]] = v
        except (json.JSONDecodeError, KeyError):
            pass

    print(f"  Loaded {len(verified_claims)} verification results")

    # 3. Load correction sources
    correction_sources: Set[str] = set()
    corrections_path = output_dir / "4-corrections-log.json"
    if corrections_path.exists():
        try:
            with open(corrections_path) as f:
                corrections_data = json.load(f)
            for correction in corrections_data.get("corrections", []):
                if correction.get("source_url") and correction.get("status") == "applied":
                    correction_sources.add(correction["source_url"])
        except (json.JSONDecodeError, KeyError):
            pass

    # 4. Collect research-phase sources per section
    research_sources_by_section: Dict[str, List[Dict]] = defaultdict(list)
    if research_dir.exists():
        for research_file in sorted(research_dir.glob("*.md")):
            citations = _extract_citations_with_details(research_file.read_text())
            # Map research file to section: "03-market-context.md" matches section "03-..."
            stem = research_file.stem
            research_sources_by_section[stem].extend(citations)

    # ── Process each section ─────────────────────────────────────────

    section_map = _map_sections_to_files(sections_dir)
    total_sources = 0
    total_sections = 0

    for display_name, section_file in section_map.items():
        section_content = section_file.read_text()
        section_stem = section_file.stem

        # Collect all sources for this section
        sources: List[Dict[str, Any]] = []
        seen_urls: Set[str] = set()

        # Get inline citation nums used in this section
        inline_nums = _extract_inline_citation_nums(section_content)

        # Get citation definitions from this section
        section_citations = _extract_citations_with_details(section_content)
        section_url_map = {c["citation_num"]: c["url"] for c in section_citations if c["url"]}

        # A) Sources from the section itself (included)
        for cite in section_citations:
            if cite["url"] and cite["url"] not in seen_urls:
                seen_urls.add(cite["url"])
                is_inline = cite["citation_num"] in inline_nums

                # Check validation status
                val_entry = validation_log_by_url.get(cite["url"], {})
                verification = verified_claims.get(cite["url"], {})

                sources.append({
                    "url": cite["url"],
                    "title": cite["title"],
                    "full_definition": cite["full_definition"],
                    "status": "included" if is_inline else "defined-not-cited",
                    "validation_http_code": val_entry.get("http_code", ""),
                    "validation_status": val_entry.get("validation_status", "not checked"),
                    "verification_result": verification.get("result", ""),
                    "origin": "section",
                })

        # B) Sources from research files (may or may not be in section)
        for research_stem, research_cites in research_sources_by_section.items():
            # Match research file to section by prefix number
            section_prefix = re.match(r'^(\d+)', section_stem)
            research_prefix = re.match(r'^(\d+)', research_stem)
            if not section_prefix or not research_prefix:
                continue
            if section_prefix.group(1) != research_prefix.group(1):
                continue

            for cite in research_cites:
                if cite["url"] and cite["url"] not in seen_urls:
                    seen_urls.add(cite["url"])
                    val_entry = validation_log_by_url.get(cite["url"], {})

                    status = "found-in-research"
                    val_status = val_entry.get("validation_status", "")
                    if val_status == "removed":
                        status = "excluded-invalid"
                        if val_entry.get("http_code") == -1:
                            status = "hallucinated"
                    elif val_status == "uncertain":
                        status = "excluded-uncertain"

                    sources.append({
                        "url": cite["url"],
                        "title": cite["title"],
                        "full_definition": cite["full_definition"],
                        "status": status,
                        "validation_http_code": val_entry.get("http_code", ""),
                        "validation_status": val_status or "not checked",
                        "verification_result": "",
                        "origin": "research",
                    })

        # C) Sources from validation log not yet seen (removed before reaching section)
        for url, entry in validation_log_by_url.items():
            if url in seen_urls:
                continue
            source_file = entry.get("source_file", "")
            # Check if this source came from a file related to this section
            if not source_file:
                continue
            source_prefix = re.match(r'^(\d+)', source_file)
            section_prefix = re.match(r'^(\d+)', section_stem)
            if not source_prefix or not section_prefix:
                continue
            if source_prefix.group(1) != section_prefix.group(1):
                continue

            seen_urls.add(url)
            status = "excluded-invalid" if entry.get("validation_status") == "removed" else "excluded-uncertain"
            if entry.get("http_code") == -1:
                status = "hallucinated"

            sources.append({
                "url": url,
                "title": entry.get("title", ""),
                "full_definition": entry.get("full_definition", ""),
                "status": status,
                "validation_http_code": entry.get("http_code", ""),
                "validation_status": entry.get("validation_status", ""),
                "verification_result": "",
                "origin": "validation-log",
            })

        # D) Sources added during fact correction
        for url in correction_sources:
            if url not in seen_urls:
                seen_urls.add(url)
                verification = verified_claims.get(url, {})
                sources.append({
                    "url": url,
                    "title": verification.get("source_title", ""),
                    "full_definition": "",
                    "status": "added-by-correction",
                    "validation_http_code": "",
                    "validation_status": "verified",
                    "verification_result": verification.get("result", ""),
                    "origin": "fact-correction",
                })

        if not sources:
            continue

        # ── Write the per-section source list ────────────────────────

        total_sources += len(sources)
        total_sections += 1

        md = _format_section_source_list(display_name, sources, company_name)
        safe_name = section_file.stem
        catalog_path = catalog_dir / f"{safe_name}-Complete-Source-List.md"
        catalog_path.write_text(md, encoding="utf-8")

        included = sum(1 for s in sources if s["status"] == "included")
        excluded = sum(1 for s in sources if s["status"].startswith("excluded"))
        hallucinated = sum(1 for s in sources if s["status"] == "hallucinated")
        print(f"  📋 {display_name}: {len(sources)} sources ({included} included, {excluded} excluded, {hallucinated} hallucinated)")

    # Save a combined index
    _save_catalog_index(catalog_dir, section_map, output_dir, company_name)

    print(f"\n{'=' * 70}")
    print(f"SOURCE CATALOG COMPLETE")
    print(f"{'=' * 70}")
    print(f"  {total_sections} sections cataloged, {total_sources} total sources")
    print(f"  Output: {catalog_dir}/")
    print(f"{'=' * 70}\n")

    return {
        "messages": [
            f"✓ Source catalog: {total_sources} sources across {total_sections} sections",
            f"  Saved to {catalog_dir}/"
        ]
    }


def _format_section_source_list(
    section_name: str,
    sources: List[Dict[str, Any]],
    company_name: str
) -> str:
    """Format a per-section source list as markdown."""
    md = f"# {section_name} — Complete Source List\n\n"
    md += f"**Company**: {company_name}\n"
    md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    # Group by status
    status_groups = defaultdict(list)
    for source in sources:
        status_groups[source["status"]].append(source)

    # Status display order and labels
    status_labels = {
        "included": ("Included in Final Draft", "Sources that appear in the final memo with citations."),
        "added-by-correction": ("Added During Fact Correction", "Sources found by LLM verification and added to correct inaccurate claims."),
        "found-valid-not-cited": ("Valid but Not Cited", "Sources found during research that passed URL validation but weren't cited in the final section."),
        "found-in-research": ("Found in Research", "Sources discovered during the research phase."),
        "defined-not-cited": ("Defined but Not Cited Inline", "Citation definitions exist but no inline reference in the section text."),
        "excluded-uncertain": ("Excluded — Uncertain", "Sources removed due to uncertain accessibility (403, 401, timeout). May still be valid behind paywalls or login walls."),
        "excluded-invalid": ("Excluded — Invalid URL", "Sources removed because the URL returned 404 or other definitive error codes."),
        "hallucinated": ("Excluded — Hallucinated", "Sources identified as fabricated URLs (hallucination patterns, fake paths)."),
    }

    for status_key, (label, description) in status_labels.items():
        group = status_groups.get(status_key, [])
        if not group:
            continue

        md += f"## {label} ({len(group)})\n\n"
        md += f"*{description}*\n\n"

        for source in group:
            title = source.get("title", "") or "Untitled"
            url = source.get("url", "")

            if url:
                md += f"- **[{title}]({url})**\n"
            else:
                md += f"- **{title}** (no URL)\n"

            # Show validation details
            http_code = source.get("validation_http_code", "")
            if http_code:
                md += f"  - HTTP: {http_code}\n"

            verification = source.get("verification_result", "")
            if verification:
                md += f"  - LLM Verification: {verification}\n"

            if source.get("full_definition"):
                # Show first 200 chars of definition
                defn = source["full_definition"][:200]
                if len(source["full_definition"]) > 200:
                    defn += "..."
                md += f"  - Definition: {defn}\n"

            md += "\n"

    return md


def _save_catalog_index(
    catalog_dir: Path,
    section_map: Dict[str, Path],
    output_dir: Path,
    company_name: str
) -> None:
    """Save an index file for the source catalog."""
    md = f"# Source Catalog Index — {company_name}\n\n"
    md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    md += "This directory contains comprehensive source lists for each section of the investment memo. "
    md += "Every source the system encountered during research, validation, and fact-checking is cataloged here, "
    md += "including sources that were excluded from the final draft.\n\n"

    md += "## Sections\n\n"
    for display_name, section_file in section_map.items():
        catalog_file = f"{section_file.stem}-Complete-Source-List.md"
        if (catalog_dir / catalog_file).exists():
            md += f"- [{display_name}]({catalog_file})\n"

    md += "\n## Source Status Legend\n\n"
    md += "| Status | Meaning |\n|--------|--------|\n"
    md += "| Included | Source appears in the final memo with inline citation |\n"
    md += "| Added by Correction | Source found by LLM verification to fix an inaccurate claim |\n"
    md += "| Valid but Not Cited | Source passed URL validation but wasn't used in the section |\n"
    md += "| Found in Research | Source discovered during research phase |\n"
    md += "| Excluded — Uncertain | Removed due to 403/401/timeout (may be behind paywall) |\n"
    md += "| Excluded — Invalid | URL returned 404 or other error |\n"
    md += "| Hallucinated | Fabricated URL detected by hallucination patterns |\n"

    (catalog_dir / "README.md").write_text(md, encoding="utf-8")

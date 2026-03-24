"""
Scorecard Navigator Agent.

Runs AFTER scorecard integration to insert a compact scorecard overview table
near the top of the memo. This gives investors immediate visibility into
scorecard scores with anchor links to jump to detailed analysis.

Also regenerates the TOC so it reflects the integrated scorecard headings.
"""

import json
import re
from typing import Dict, Any, Optional
from pathlib import Path


def _slugify(text: str) -> str:
    """Generate pandoc-compatible anchor slug from header text."""
    # Remove leading numbers like "1. " or "01. "
    text = re.sub(r'^\d+\.\s*', '', text)
    # Remove bold markers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    slug = text.lower().strip()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


def _score_bar(score: int, max_score: int = 5) -> str:
    """Create a visual score indicator."""
    filled = "●" * score
    empty = "○" * (max_score - score)
    return f"{filled}{empty}"


def build_scorecard_nav_table(scorecard_json_path: Path) -> Optional[str]:
    """
    Build a compact scorecard navigation table from scorecard JSON data.

    Returns markdown string with:
    - Overall score prominently displayed
    - Each dimension with score, visual bar, and anchor link to detailed section
    - Group organization matching the scorecard structure
    """
    if not scorecard_json_path.exists():
        return None

    with open(scorecard_json_path) as f:
        data = json.load(f)

    overall_score = data.get("overall_score", 0)
    dimensions = data.get("dimensions", {})
    group_scores = data.get("group_scores", {})
    scorecard_name = data.get("scorecard_name", "Scorecard")

    # Determine recommendation based on thresholds
    min_score = min(d["score"] for d in dimensions.values()) if dimensions else 0
    if min_score < 2 or overall_score < 2.5:
        recommendation = "PASS"
    elif min_score >= 3 and overall_score > 3.5:
        # Check for at least two 5s
        fives = sum(1 for d in dimensions.values() if d["score"] >= 5)
        recommendation = "COMMIT" if fives >= 2 else "CONSIDER"
    else:
        recommendation = "CONSIDER"

    # Map dimension IDs to display names
    dim_display_names = {
        "capital_syndicate": "Capital Syndicate",
        "category_leadership": "Category Leadership",
        "cagr": "CAGR (Revenue Growth)",
        "capital_efficiency": "Capital Efficiency",
        "colossal_market_size": "Colossal Market Size",
        "counter_cyclicality": "Counter Cyclicality",
        "cash_on_cash_return_probability": "Cash-on-Cash Return",
    }

    # Map group IDs to display info
    group_display = {
        "capital_quality": ("Capital Quality", ["capital_syndicate", "capital_efficiency"]),
        "market_dominance": ("Market Dominance", ["category_leadership", "colossal_market_size"]),
        "growth_durability": ("Growth Durability", ["cagr", "counter_cyclicality"]),
        "return_profile": ("Return Profile", ["cash_on_cash_return_probability"]),
    }

    lines = []
    lines.append("### Scorecard Overview")
    lines.append("")
    lines.append(f"**Overall Score: {overall_score:.1f}/5** | **Recommendation: {recommendation}**")
    lines.append("")
    lines.append("| Dimension | Score | Rating | Detail |")
    lines.append("|-----------|:-----:|--------|--------|")

    for group_id, (group_name, dim_ids) in group_display.items():
        g_score = group_scores.get(group_id, 0)
        lines.append(f"| **{group_name}** | **{g_score:.1f}/5** | | |")
        for dim_id in dim_ids:
            dim_data = dimensions.get(dim_id)
            if not dim_data:
                continue
            display_name = dim_display_names.get(dim_id, dim_id.replace("_", " ").title())
            score = dim_data["score"]
            bar = _score_bar(score)
            percentile = dim_data.get("percentile", "")
            # Anchor link to the detailed scorecard section heading
            anchor = _slugify(f"{display_name}")
            lines.append(f"| &nbsp;&nbsp;&nbsp;{display_name} | {score}/5 | {bar} {percentile} | [Jump to detail](#{anchor}) |")

    lines.append("")
    lines.append(f"*[View full scorecard analysis](#scorecard-summary)*")
    lines.append("")

    return "\n".join(lines)


def insert_nav_into_executive_summary(draft_content: str, nav_table: str) -> str:
    """
    Insert the scorecard navigation table at the END of the Executive Summary,
    just before the next section heading. The table becomes part of the
    Executive Summary so investors see scores immediately.

    Placement priority:
    1. End of Executive Summary (before next ## heading)
    2. End of first section (before second ## heading)
    3. After first --- separator
    """
    # Strategy 1: Find Executive Summary heading (any level: #, ##, ###)
    # then insert at the end of the Executive Summary — just before the
    # first ## numbered section heading (e.g., "## 1. Capital Syndicate")
    exec_match = re.search(
        r'^#{1,6}\s+(?:\d+\.\s+)?Executive Summary\b',
        draft_content,
        re.MULTILINE | re.IGNORECASE
    )
    if exec_match:
        after_exec = draft_content[exec_match.end():]
        # Find the first ## numbered section (the start of memo body content)
        next_section = re.search(r'\n##\s+\d+\.', after_exec)
        if next_section:
            insert_pos = exec_match.end() + next_section.start()
        else:
            # Fallback: first ## heading of any kind
            next_any = re.search(r'\n##\s', after_exec)
            insert_pos = exec_match.end() + next_any.start() if next_any else len(draft_content)
        return draft_content[:insert_pos] + "\n\n" + nav_table + "\n" + draft_content[insert_pos:]

    # Strategy 2: Insert before the second ## heading (end of first section)
    headings = list(re.finditer(r'\n(##\s)', draft_content))
    if len(headings) >= 2:
        insert_pos = headings[1].start()
        return draft_content[:insert_pos] + "\n\n" + nav_table + "\n" + draft_content[insert_pos:]

    # Strategy 3: After first --- separator
    first_hr = draft_content.find('\n---\n')
    if first_hr != -1:
        insert_pos = first_hr + 5
        return draft_content[:insert_pos] + "\n" + nav_table + "\n" + draft_content[insert_pos:]

    # Fallback: beginning of document
    return nav_table + "\n\n" + draft_content


def scorecard_navigator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scorecard Navigator Agent.

    Inserts a compact scorecard overview table with anchor links near the top
    of the memo, then regenerates the TOC to include scorecard headings.

    Runs AFTER integrate_scorecard in the workflow.
    """
    from ..utils import get_output_dir_from_state
    from ..final_draft import find_final_draft

    company_name = state["company_name"]

    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("⊘ Scorecard navigator skipped - no output directory")
        return {"messages": ["Scorecard navigator skipped - no output directory"]}

    # Find scorecard JSON
    scorecard_json = output_dir / "5-scorecard" / "12Ps-scorecard.json"
    if not scorecard_json.exists():
        # Try alternate naming patterns
        scorecard_dir = output_dir / "5-scorecard"
        if scorecard_dir.exists():
            json_files = list(scorecard_dir.glob("*scorecard*.json"))
            if json_files:
                scorecard_json = json_files[0]

    if not scorecard_json.exists():
        print("⊘ Scorecard navigator skipped - no scorecard JSON found")
        return {"messages": ["Scorecard navigator skipped - no scorecard data"]}

    # Build the navigation table
    nav_table = build_scorecard_nav_table(scorecard_json)
    if not nav_table:
        print("⊘ Scorecard navigator skipped - could not build navigation table")
        return {"messages": ["Scorecard navigator skipped - build failed"]}

    # Find and update the final draft
    final_draft_path = find_final_draft(output_dir)
    if not final_draft_path:
        print("⊘ Scorecard navigator skipped - no final draft found")
        return {"messages": ["Scorecard navigator skipped - no final draft"]}

    draft_content = final_draft_path.read_text()

    # Check if navigator already inserted (avoid duplicates on re-runs)
    if "### Scorecard Overview" in draft_content:
        # Remove existing navigator before re-inserting
        draft_content = re.sub(
            r'### Scorecard Overview\n.*?(?=\n##|\n---\n|\Z)',
            '',
            draft_content,
            count=1,
            flags=re.DOTALL
        )

    # Insert navigation table
    updated_content = insert_nav_into_executive_summary(draft_content, nav_table)
    final_draft_path.write_text(updated_content)

    # Count dimensions in the table
    dim_count = nav_table.count("/5 |")
    print(f"✓ Scorecard navigator inserted ({dim_count} dimensions with anchor links)")

    # TOC will be generated as the final content step (toc node runs after scorecard_nav)

    return {"messages": [
        f"Scorecard navigator inserted with {dim_count} dimensions"
    ]}

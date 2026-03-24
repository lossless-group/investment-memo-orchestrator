"""
Trademark Enrichment Agent.

Creates a header.md for every memo with company name, date, and investment metadata.
Includes company trademark/logo when available.
"""

import os
from typing import Dict, Any
from pathlib import Path
from ..utils import get_latest_output_dir
from datetime import datetime


def _resolve_trademark_url(trademark_path: str) -> str:
    """Resolve a trademark path (URL or local file) to a usable URL string."""
    if trademark_path.startswith('http'):
        return trademark_path

    path = Path(trademark_path)

    project_root = os.getenv("PROJECT_PATH")
    if project_root:
        project_root = Path(project_root)
    else:
        project_root = Path(__file__).parent.parent.parent

    if path.is_absolute():
        return str(path)

    abs_path = project_root / trademark_path
    if abs_path.exists():
        return str(abs_path.resolve())

    return f"../../{trademark_path}"


def trademark_enrichment_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trademark Enrichment Agent.

    Always creates a header.md with company name, date, and memo metadata.
    Includes company trademark/logo image when trademark paths are provided.

    Args:
        state: Current memo state containing company info and trademark paths

    Returns:
        Updated state message
    """
    company_name = state["company_name"]
    firm = state.get("firm")
    company_trademark_light = state.get("company_trademark_light")
    company_trademark_dark = state.get("company_trademark_dark")
    investment_type = state.get("investment_type", "direct")
    memo_mode = state.get("memo_mode", "consider")

    # Get output directory (respects state["output_dir"] for resume, falls back to auto-detect)
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print(f"⊘ Header creation skipped - no output directory found for {company_name}")
        return {"messages": ["Header creation skipped - no output directory"]}

    # Build header content
    parts = []

    # Trademark/logo (if available)
    if company_trademark_light or company_trademark_dark:
        trademark_path = company_trademark_light or company_trademark_dark
        trademark_url = _resolve_trademark_url(trademark_path)
        parts.append(f'![{company_name} Logo]({trademark_url})')
        parts.append("")

    # Company name as title
    type_label = "Fund Commitment Memo" if investment_type == "fund" else "Investment Memo"
    mode_label = "Retrospective Justification" if memo_mode == "justify" else "Prospective Analysis"
    date_str = datetime.now().strftime("%B %d, %Y")

    parts.append(f"# {company_name}")
    parts.append("")
    parts.append(f"**{type_label}** | {mode_label}")
    if firm:
        parts.append(f"**Prepared by:** {firm}")
    parts.append(f"**Date:** {date_str}")
    parts.append("")
    parts.append("---")
    parts.append("")

    header_content = "\n".join(parts)

    # Save header to file
    header_file = output_dir / "header.md"
    with open(header_file, "w") as f:
        f.write(header_content)

    has_logo = bool(company_trademark_light or company_trademark_dark)
    logo_note = " (with logo)" if has_logo else " (text only)"
    print(f"✓ Memo header saved{logo_note}: {header_file}")

    return {
        "messages": [f"Memo header created for {company_name}{logo_note}"]
    }

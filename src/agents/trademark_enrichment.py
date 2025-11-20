"""
Trademark Enrichment Agent.

Inserts company trademark/logo images into memo header.
"""

from typing import Dict, Any
from pathlib import Path
from ..utils import get_latest_output_dir
from datetime import datetime


def trademark_enrichment_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Trademark Enrichment Agent.

    Creates a header.md file with company trademark/logo if trademark paths are provided.
    The finalizer will use this header when assembling the complete memo.

    Args:
        state: Current memo state containing company info and trademark paths

    Returns:
        Updated state message
    """
    company_name = state["company_name"]
    company_trademark_light = state.get("company_trademark_light")
    company_trademark_dark = state.get("company_trademark_dark")

    # Skip if no trademarks provided
    if not company_trademark_light and not company_trademark_dark:
        print("⊘ Trademark enrichment skipped - no trademark paths provided")
        return {"messages": ["Trademark enrichment skipped - no trademark paths provided"]}

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name)
    except FileNotFoundError:
        print(f"⊘ Trademark enrichment skipped - no output directory found for {company_name}")
        return {"messages": ["Trademark enrichment skipped - no output directory"]}

    # Create trademark markdown (use light mode as default, will be swapped during export)
    trademark_path = company_trademark_light or company_trademark_dark

    # Check if path is URL or local file
    if trademark_path.startswith('http'):
        trademark_url = trademark_path
    else:
        # Convert local path to relative path from output directory
        trademark_url = f"../../{trademark_path}"

    trademark_markdown = f'![{company_name} Logo]({trademark_url})\n\n---\n\n'

    # Create header.md with title, date, and trademark
    current_date = datetime.now().strftime("%B %Y")
    header_content = f"""# Investment Memo: {company_name}

**Date**: {current_date}

{trademark_markdown}"""

    # Save header to file
    header_file = output_dir / "header.md"
    with open(header_file, "w") as f:
        f.write(header_content)

    print(f"✓ Company trademark header saved: {header_file}")

    return {
        "messages": [f"Company trademark header created for {company_name}"]
    }

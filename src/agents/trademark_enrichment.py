"""
Trademark Enrichment Agent.

Inserts company trademark/logo images into memo header.
"""

import os
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
        # Handle local paths - use absolute paths so pandoc can find them
        # regardless of where it's invoked from
        path = Path(trademark_path)

        # Get project root from PROJECT_PATH env var or fallback to file-based detection
        project_root = os.getenv("PROJECT_PATH")
        if project_root:
            project_root = Path(project_root)
        else:
            project_root = Path(__file__).parent.parent.parent

        if path.is_absolute():
            # Already absolute, use as-is
            trademark_url = str(path)
        else:
            # Relative path - convert to absolute from project root
            abs_path = project_root / trademark_path
            if abs_path.exists():
                trademark_url = str(abs_path.resolve())
            else:
                # Fallback to relative path if file doesn't exist
                trademark_url = f"../../{trademark_path}"

    trademark_markdown = f'![{company_name} Logo]({trademark_url})\n\n---\n\n'

    # Create header.md with just the trademark (title/date are in memo body)
    header_content = trademark_markdown

    # Save header to file
    header_file = output_dir / "header.md"
    with open(header_file, "w") as f:
        f.write(header_content)

    print(f"✓ Company trademark header saved: {header_file}")

    return {
        "messages": [f"Company trademark header created for {company_name}"]
    }

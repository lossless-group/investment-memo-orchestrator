"""
Inject Deck Images Agent

This agent injects deck screenshots into the appropriate 2-sections/ files
AFTER the writer has polished the research but BEFORE final assembly.

The agent reads the section_to_screenshots mapping from 0-deck-analysis.json
(created by deck_analyst) and adds image embeds to matching sections.

Why this agent exists:
- Screenshots are extracted by deck_analyst and embedded in 0-deck-sections/
- Section researcher passes deck content to Perplexity as context
- Perplexity integrates the INFORMATION but doesn't preserve ![image](path) markdown
- Writer polishes Perplexity output → 2-sections/ (no images)
- This agent adds the images back by reading the mapping from deck_analyst

Flow:
    deck_analyst → 0-deck-analysis.json (with section_to_screenshots mapping)
    deck_analyst → 0-deck-sections/ (with embedded images)
    section_researcher → 1-research/ (Perplexity, images lost)
    writer → 2-sections/ (polished, no images)
    inject_deck_images → 2-sections/ (images added) ← THIS AGENT
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state import MemoState


def inject_deck_images_agent(state: MemoState) -> Dict[str, Any]:
    """
    Inject deck screenshots into 2-sections/ files based on section_to_screenshots mapping.

    Reads the mapping from 0-deck-analysis.json and adds image embeds to the top
    of matching section files.

    Args:
        state: Current memo state

    Returns:
        State update with messages about injection results
    """
    company_name = state.get("company_name", "Unknown")
    firm = state.get("firm")

    print(f"\n🖼️  Injecting deck screenshots into sections for {company_name}...")

    # Find output directory
    output_dir = _find_output_dir(state, company_name, firm)
    if not output_dir:
        return {"messages": ["Inject deck images: Could not find output directory"]}

    # Read deck analysis to get the mapping
    deck_analysis_path = output_dir / "0-deck-analysis.json"
    if not deck_analysis_path.exists():
        print("  ⚠️  No 0-deck-analysis.json found, skipping image injection")
        return {"messages": ["Inject deck images: No deck analysis found"]}

    try:
        with open(deck_analysis_path) as f:
            deck_analysis = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  ⚠️  Failed to read deck analysis: {e}")
        return {"messages": [f"Inject deck images: Failed to read deck analysis: {e}"]}

    # Get section_to_screenshots mapping
    section_to_screenshots = deck_analysis.get("section_to_screenshots", {})
    if not section_to_screenshots:
        print("  ℹ️  No section_to_screenshots mapping found, skipping image injection")
        return {"messages": ["Inject deck images: No screenshot mapping found"]}

    print(f"  Found mappings for {len(section_to_screenshots)} section keywords")

    # Find 2-sections directory
    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        print("  ⚠️  No 2-sections/ directory found, skipping image injection")
        return {"messages": ["Inject deck images: No 2-sections directory found"]}

    # Process each section file
    sections_updated = 0
    images_injected = 0

    for section_file in sorted(sections_dir.glob("*.md")):
        # Extract section name from filename
        # Format: 01-executive-summary.md → "executive summary"
        # or: 04-organization.md → "organization"
        filename_stem = section_file.stem
        # Remove leading number prefix (e.g., "01-", "04-")
        if filename_stem[:2].isdigit() and filename_stem[2] == "-":
            section_name_raw = filename_stem[3:]
        else:
            section_name_raw = filename_stem

        # Normalize section name for matching
        section_name_normalized = section_name_raw.lower().replace("-", " ").replace("_", " ")

        # Find matching screenshots
        matching_screenshots = _find_matching_screenshots(
            section_name_normalized, section_to_screenshots
        )

        if not matching_screenshots:
            continue

        # Read current content
        current_content = section_file.read_text()

        # Check if images are already embedded
        existing_images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', current_content)
        existing_paths = {path for _, path in existing_images}

        # Filter out already-embedded screenshots
        new_screenshots = [s for s in matching_screenshots if s not in existing_paths]
        if not new_screenshots:
            continue

        # Build image embeds
        image_embeds = []
        for screenshot_path in new_screenshots:
            # Extract description from path
            # e.g., /path/to/page-14-team.png → "Team slide from pitch deck"
            path_obj = Path(screenshot_path)
            category = _extract_category_from_filename(path_obj.stem)
            description = f"{category.title()} slide from pitch deck"
            image_embeds.append(f"![{description}]({screenshot_path})")

        # Prepend images to content
        images_block = "\n\n".join(image_embeds)
        new_content = f"{images_block}\n\n{current_content}"

        # Write updated content
        section_file.write_text(new_content)
        sections_updated += 1
        images_injected += len(new_screenshots)
        print(f"  ✓ {section_file.name}: +{len(new_screenshots)} image(s)")

    if sections_updated > 0:
        print(f"\n✅ Injected {images_injected} screenshot(s) into {sections_updated} section(s)")
    else:
        print("  ℹ️  No sections needed image injection")

    return {
        "messages": [f"Inject deck images: Added {images_injected} screenshots to {sections_updated} sections"]
    }


def _find_output_dir(state: MemoState, company_name: str, firm: Optional[str]) -> Optional[Path]:
    """Find the output directory for this company."""
    # Check if output_dir is in state
    if state.get("output_dir"):
        return Path(state["output_dir"])

    # Try to find via firm-scoped paths
    if firm:
        from ..paths import resolve_deal_context
        ctx = resolve_deal_context(company_name, firm=firm)
        if ctx.outputs_dir and ctx.outputs_dir.exists():
            # Find latest version
            versions = sorted(ctx.outputs_dir.glob(f"*-v*"), reverse=True)
            if versions:
                return versions[0]

    # Fallback to default output directory
    from ..artifacts import sanitize_filename
    safe_name = sanitize_filename(company_name)
    output_base = Path("output")
    if output_base.exists():
        versions = sorted(output_base.glob(f"{safe_name}-v*"), reverse=True)
        if versions:
            return versions[0]

    return None


def _find_matching_screenshots(
    section_name: str,
    section_to_screenshots: Dict[str, List[str]]
) -> List[str]:
    """
    Find screenshots that match the given section name.

    Uses keyword matching - if any keyword in section_to_screenshots
    appears in the section name, return those screenshots.

    Args:
        section_name: Normalized section name (lowercase, spaces)
        section_to_screenshots: Mapping from keywords to screenshot paths

    Returns:
        List of screenshot paths that match
    """
    matching = []

    for keyword, screenshots in section_to_screenshots.items():
        # Check if keyword appears in section name
        # e.g., "organization" matches "04-organization.md"
        # e.g., "team" matches "04-team.md" or "organization" (since org→team in mapping)
        if keyword.lower() in section_name:
            matching.extend(screenshots)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for path in matching:
        if path not in seen:
            seen.add(path)
            unique.append(path)

    return unique


def _extract_category_from_filename(stem: str) -> str:
    """
    Extract category from screenshot filename.

    Args:
        stem: Filename without extension, e.g., "page-14-team"

    Returns:
        Category string, e.g., "team"
    """
    # Format: page-{number}-{category}
    parts = stem.split("-")
    if len(parts) >= 3:
        return parts[-1]  # Last part is the category
    return "deck"


# CLI entry point for standalone usage
def main():
    """CLI entry point for standalone image injection."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.inject_deck_images <output_dir>")
        print("Example: python -m src.agents.inject_deck_images io/dark-matter/deals/ProfileHealth/outputs/ProfileHealth-v0.0.4")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        sys.exit(1)

    # Create minimal state for the agent
    state = {
        "company_name": output_dir.name.rsplit("-v", 1)[0],  # Extract company name from dir
        "output_dir": str(output_dir),
    }

    result = inject_deck_images_agent(state)
    print(result.get("messages", ["Done"])[0])


if __name__ == "__main__":
    main()

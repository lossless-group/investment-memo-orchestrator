"""
Inject Deck Images Agent

This agent injects deck screenshots into the appropriate 2-sections/ files
AFTER the writer has polished the research but BEFORE final assembly.

The agent reads the screenshot mapping from 0-deck-analysis.json
(created by deck_analyst) and places images according to the placement rules
defined in templates/deck-classification-guide.md.

Placement Rules:
    1. Each image appears at most TWICE: once in its primary section, once
       optionally in the Executive Summary Key Slides gallery.
    2. Each image goes into exactly ONE body section (its primary match).
    3. Images are placed under the most relevant header within a section,
       NOT prepended at the top.
    4. Executive Summary gets a ## Key Slides gallery at the bottom (up to 5).
    5. Scorecard/summary/recommendation sections get NO images.

Flow:
    deck_analyst → 0-deck-analysis.json (with section_to_screenshots mapping)
    deck_analyst → 0-deck-sections/ (with embedded images)
    section_researcher → 1-research/ (Perplexity, images lost)
    writer → 2-sections/ (polished, no images)
    inject_deck_images → 2-sections/ (images placed) ← THIS AGENT
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..state import MemoState


# Section filename patterns that should NEVER receive deck screenshots.
# These are synthesis/summary sections, not content sections.
EXCLUDED_SECTION_PATTERNS = {
    "scorecard", "recommendation", "closing-assessment",
    "investment-thesis", "12ps-scorecard",
}


def inject_deck_images_agent(state: MemoState) -> Dict[str, Any]:
    """
    Inject deck screenshots into 2-sections/ files based on classification mapping.

    Each image is placed at most twice: once in its primary content section
    (under the best-matching header) and once in the Key Slides gallery.

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

    # Get screenshot mapping (new format with 'images' and 'key_slides')
    screenshot_mapping = deck_analysis.get("section_to_screenshots", {})
    images = screenshot_mapping.get("images", [])
    key_slides_paths = screenshot_mapping.get("key_slides", [])

    if not images:
        # Try legacy format: flat dict of keyword → paths
        if isinstance(screenshot_mapping, dict) and "images" not in screenshot_mapping:
            print("  ℹ️  Legacy screenshot mapping format detected, skipping (re-run deck analyst)")
            return {"messages": ["Inject deck images: Legacy mapping format, re-run deck analyst to update"]}
        print("  ℹ️  No screenshot images found in mapping, skipping")
        return {"messages": ["Inject deck images: No images in mapping"]}

    print(f"  Found {len(images)} classified screenshots")

    # Find 2-sections directory
    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        print("  ⚠️  No 2-sections/ directory found, skipping image injection")
        return {"messages": ["Inject deck images: No 2-sections directory found"]}

    # Track how many times each image has been placed (max 2)
    placement_count: Dict[str, int] = {}

    # PHASE 1: Place each image in its primary body section
    sections_updated = 0
    images_injected = 0

    # Build a mapping from category → list of image entries
    category_to_images: Dict[str, List[Dict]] = {}
    for img in images:
        cat = img.get("category", "general")
        if cat not in category_to_images:
            category_to_images[cat] = []
        category_to_images[cat].append(img)

    for section_file in sorted(sections_dir.glob("*.md")):
        # Check if this section is excluded
        filename_stem = section_file.stem.lower()
        if any(pattern in filename_stem for pattern in EXCLUDED_SECTION_PATTERNS):
            continue

        # Find images whose category best matches this section
        matching_images = _match_images_to_section(
            section_file.stem, category_to_images
        )

        if not matching_images:
            continue

        # Read current content
        current_content = section_file.read_text()

        # Check for already-embedded images
        existing_images = set(
            path for _, path in re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', current_content)
        )

        # Place each matching image under the best header
        new_content = current_content
        section_images_added = 0

        for img in matching_images:
            img_path = img["path"]

            # Skip if already embedded or at placement limit
            if img_path in existing_images:
                continue
            if placement_count.get(img_path, 0) >= 2:
                continue

            # Build the image embed
            alt_text = _build_alt_text(img)
            embed = f"![{alt_text}]({img_path})"

            # Find the best header to place under
            new_content = _insert_after_best_header(
                new_content, embed, img.get("category", ""), img.get("slug", "")
            )

            placement_count[img_path] = placement_count.get(img_path, 0) + 1
            section_images_added += 1

        if section_images_added > 0:
            section_file.write_text(new_content)
            sections_updated += 1
            images_injected += section_images_added
            print(f"  ✓ {section_file.name}: +{section_images_added} image(s)")

    # PHASE 2: Append Key Slides gallery to Executive Summary
    key_slides_added = 0
    exec_summary = _find_executive_summary(sections_dir)
    if exec_summary and key_slides_paths:
        key_slides_added = _append_key_slides_gallery(
            exec_summary, key_slides_paths, images, placement_count
        )

    if sections_updated > 0 or key_slides_added > 0:
        total = images_injected + key_slides_added
        print(f"\n✅ Injected {total} screenshot(s) into {sections_updated} section(s)"
              f"{f' + {key_slides_added} in Key Slides' if key_slides_added else ''}")
    else:
        print("  ℹ️  No sections needed image injection")

    return {
        "messages": [
            f"Inject deck images: Added {images_injected} screenshots to "
            f"{sections_updated} sections, {key_slides_added} in Key Slides gallery"
        ]
    }


# ---------------------------------------------------------------------------
# Category → Section matching
# ---------------------------------------------------------------------------

# Maps image categories to section filename keywords (lowercase).
# Each category has ONE primary match and an optional fallback.
# This replaces the old many-to-many SECTION_TO_DECK_TOPICS mapping.
CATEGORY_TO_SECTION_KEYWORDS = {
    # Category              → (primary keywords, fallback keywords)
    "overview":               (["executive-summary"], ["opening"]),
    "problem":                (["origins", "business-overview"], ["market"]),
    "customer-pain":          (["origins", "business-overview"], ["opening"]),
    "ideal-customer-profile": (["market", "opening", "opportunity"], ["business-overview"]),
    "solution":               (["origins", "business-overview"], ["opening"]),
    "product-demo":           (["offering", "technology", "product"], []),
    "value-proposition":      (["offering", "business-overview", "opening"], []),
    "technology":             (["offering", "technology", "product"], ["origins"]),
    "business-model":         (["opening", "business-overview"], []),
    "unit-economics":         (["opening", "traction", "funding"], []),
    "market-size":            (["opportunity", "market"], []),
    "competitive-positioning": (["opportunity", "market"], ["risks"]),
    "competition-landscape":  (["opportunity", "market"], []),
    "traction":               (["traction", "milestones"], []),
    "team":                   (["organization", "team"], []),
    "go-to-market":           (["opening", "traction", "business-overview"], []),
    "fundraising":            (["funding", "terms"], []),
    "financials":             (["funding", "terms", "traction"], []),
    "partnerships":           (["opening", "traction", "business-overview"], []),
    "branding":               (["offering", "product", "business-overview"], []),
    "vision":                 (["closing", "investment-thesis", "executive-summary"], []),
    "impact":                 (["closing", "investment-thesis", "opportunity"], []),
}


def _match_images_to_section(
    section_stem: str,
    category_to_images: Dict[str, List[Dict]]
) -> List[Dict]:
    """
    Find images whose primary section matches this section file.

    Args:
        section_stem: Filename stem, e.g. "04-organization"
        category_to_images: Mapping from category to image entry list

    Returns:
        List of image entries that should go in this section
    """
    # Normalize: "04-organization" → "organization"
    normalized = section_stem.lower()
    if len(normalized) > 2 and normalized[2] == '-' and normalized[:2].isdigit():
        normalized = normalized[3:]

    matched = []
    for category, img_list in category_to_images.items():
        keywords = CATEGORY_TO_SECTION_KEYWORDS.get(category)
        if not keywords:
            continue

        primary_kws, fallback_kws = keywords

        # Check primary keywords first
        if any(kw in normalized for kw in primary_kws):
            matched.extend(img_list)
        elif any(kw in normalized for kw in fallback_kws):
            matched.extend(img_list)

    return matched


# ---------------------------------------------------------------------------
# Header-aware image insertion
# ---------------------------------------------------------------------------

def _insert_after_best_header(
    content: str,
    embed: str,
    category: str,
    slug: str
) -> str:
    """
    Insert an image embed after the most relevant header in the section content.

    Searches for headers that match the image's category or slug keywords.
    Falls back to inserting after the first ## header if no match found.

    Args:
        content: Section markdown content
        embed: The ![alt](path) string to insert
        category: Image category for matching
        slug: Image slug for matching

    Returns:
        Updated content with image inserted
    """
    lines = content.split('\n')

    # Build match terms from category and slug
    match_terms = set()
    for term in category.replace('-', ' ').split():
        match_terms.add(term.lower())
    for term in slug.replace('-', ' ').split():
        match_terms.add(term.lower())

    # Score each header line
    best_idx = -1
    best_score = 0
    first_h2_idx = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('#'):
            continue

        # Track first ## header as fallback
        if stripped.startswith('## ') and first_h2_idx == -1:
            first_h2_idx = i

        # Score based on keyword overlap
        header_words = set(
            stripped.lstrip('#').strip().lower()
            .replace('&', ' ').replace('-', ' ').replace('_', ' ')
            .split()
        )
        overlap = len(match_terms & header_words)
        if overlap > best_score:
            best_score = overlap
            best_idx = i

    # Choose insertion point
    if best_score > 0:
        insert_idx = best_idx
    elif first_h2_idx >= 0:
        insert_idx = first_h2_idx
    else:
        # No headers at all — insert at top
        return f"{embed}\n\n{content}"

    # Insert image on the line after the header (with blank line separation)
    lines.insert(insert_idx + 1, f"\n{embed}\n")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Key Slides gallery
# ---------------------------------------------------------------------------

def _find_executive_summary(sections_dir: Path) -> Optional[Path]:
    """Find the executive summary file in 2-sections/."""
    for f in sections_dir.glob("*.md"):
        if "executive-summary" in f.stem.lower() or f.stem.startswith("01-"):
            return f
    return None


def _append_key_slides_gallery(
    exec_summary_path: Path,
    key_slides_paths: List[str],
    all_images: List[Dict],
    placement_count: Dict[str, int]
) -> int:
    """
    Append a ## Key Slides gallery to the Executive Summary.

    Selects up to 5 high-signal slides, respecting the 2-placement maximum.

    Args:
        exec_summary_path: Path to executive summary markdown file
        key_slides_paths: Pre-selected key slide paths from deck_analyst
        all_images: Full list of image metadata dicts
        placement_count: Global placement counter (mutated in place)

    Returns:
        Number of images added to the gallery
    """
    content = exec_summary_path.read_text()

    # Don't add if Key Slides already exists
    if "## Key Slides" in content:
        return 0

    # Build a lookup from path → image metadata
    path_to_meta = {img["path"]: img for img in all_images}

    gallery_lines = ["\n\n## Key Slides\n"]
    added = 0

    for img_path in key_slides_paths:
        if placement_count.get(img_path, 0) >= 2:
            continue

        meta = path_to_meta.get(img_path, {})
        alt_text = _build_alt_text(meta) if meta else "Deck slide"
        gallery_lines.append(f"![{alt_text}]({img_path})\n")

        placement_count[img_path] = placement_count.get(img_path, 0) + 1
        added += 1

    if added > 0:
        content += '\n'.join(gallery_lines)
        exec_summary_path.write_text(content)
        print(f"  ✓ 01-executive-summary.md: +{added} Key Slides")

    return added


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_alt_text(img: Dict) -> str:
    """
    Build descriptive alt text from image metadata.

    Format: "{Category} — {slug} (Slide {N})"
    Example: "Unit Economics — unit-margins (Slide 14)"
    """
    category = img.get("category", "deck")
    slug = img.get("slug", "")
    page = img.get("page_number", "?")

    # Title-case the category
    cat_display = category.replace('-', ' ').title()

    if slug:
        return f"{cat_display} — {slug} (Slide {page})"
    return f"{cat_display} (Slide {page})"


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

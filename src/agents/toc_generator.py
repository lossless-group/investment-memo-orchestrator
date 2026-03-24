"""
Table of Contents Generator Agent.

Generates a markdown Table of Contents with anchor links for the final memo.
The TOC includes main sections (h2) and subsections (h3) with working anchor links
that function in both HTML and PDF exports.
"""

import re
from typing import Dict, Any, List, Tuple
from pathlib import Path

from ..utils import get_latest_output_dir


def slugify(text: str) -> str:
    """
    Convert header text to a URL-friendly slug for anchor links.

    Matches pandoc's default anchor generation:
    - Lowercase
    - Replace spaces with hyphens
    - Remove special characters except hyphens
    - Remove leading numbers and dots (e.g., "01. " prefix)

    Args:
        text: Header text to convert

    Returns:
        URL-friendly slug
    """
    # Remove leading section numbers like "01. " or "10. "
    text = re.sub(r'^\d+\.\s*', '', text)

    # Convert to lowercase
    slug = text.lower()

    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)

    # Remove special characters except hyphens and alphanumerics
    slug = re.sub(r'[^a-z0-9\-]', '', slug)

    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    return slug


def extract_headers(content: str) -> List[Tuple[int, str, str]]:
    """
    Extract all h1, h2, and h3 headers from markdown content.

    Args:
        content: Markdown content

    Returns:
        List of tuples: (level, header_text, anchor_slug)
        level: 1 for h1, 2 for h2, 3 for h3
    """
    headers = []

    # Skip headers that are part of citations section
    in_citations = False

    for line in content.split('\n'):
        # Match h1 headers (# Header) — but not ## or ###
        h1_match = re.match(r'^#\s+(.+)$', line)
        if h1_match:
            header_text = h1_match.group(1).strip()
            slug = slugify(header_text)
            headers.append((1, header_text, slug))
            in_citations = False
            continue

        # Match h2 headers (## Header) — but not ###
        h2_match = re.match(r'^##\s+(?!#)(.+)$', line)
        if h2_match:
            header_text = h2_match.group(1).strip()
            # Skip "Table of Contents" header
            if header_text.lower() == 'table of contents':
                continue
            slug = slugify(header_text)
            headers.append((2, header_text, slug))
            in_citations = False
            continue

        # Check if we've entered a citations subsection (within a section)
        if re.match(r'^###?\s*Citations?\s*$', line, re.IGNORECASE):
            in_citations = True
            continue

        if in_citations:
            continue

        # Match h3 headers (### Header)
        h3_match = re.match(r'^###\s+(.+)$', line)
        if h3_match:
            header_text = h3_match.group(1).strip()
            slug = slugify(header_text)
            headers.append((3, header_text, slug))
            continue

    return headers


def generate_toc_markdown(headers: List[Tuple[int, str, str]]) -> str:
    """
    Generate markdown Table of Contents from headers.

    Uses numbered (ordered) lists with indentation reflecting header hierarchy.
    h1 = top-level, h2 = one indent, h3 = two indents.

    Args:
        headers: List of (level, header_text, anchor_slug) tuples

    Returns:
        Markdown TOC string with anchor links
    """
    toc_lines = ["## Table of Contents\n"]

    # Build a mapping from actual header levels to sequential depth values
    # e.g., if we have h1 and h3 (no h2), map h1->0, h3->1 (not h3->2)
    if not headers:
        return ""
    levels_present = sorted(set(h[0] for h in headers))
    level_to_depth = {lvl: i for i, lvl in enumerate(levels_present)}

    # Track counters per indent level for numbered lists
    counters = {}

    for level, header_text, slug in headers:
        depth = level_to_depth[level]
        indent = "   " * depth  # 3 spaces per level (markdown ordered list nesting)

        # Reset deeper counters when a higher-level heading appears
        for d in list(counters.keys()):
            if d > depth:
                del counters[d]

        counters[depth] = counters.get(depth, 0) + 1

        # Create numbered markdown link
        toc_lines.append(f"{indent}{counters[depth]}. [{header_text}](#{slug})")

    # Add horizontal rule after TOC to separate from content
    toc_lines.append("")
    toc_lines.append("---")
    toc_lines.append("")

    return "\n".join(toc_lines)


def insert_toc_after_executive_summary(content: str, toc: str) -> str:
    """
    Insert TOC after the Executive Summary section, before the next main section.

    The TOC should appear after the Executive Summary content and before the
    next ## heading (e.g., "## 02. Origins" or "## Business Overview").

    Strategy:
    1. Find the Executive Summary heading (## ... Executive Summary)
    2. Find the next ## heading after it
    3. Insert TOC between them

    Fallback: If no Executive Summary found, insert after the first --- (header/logo).

    Args:
        content: Full memo markdown content
        toc: Generated TOC markdown

    Returns:
        Content with TOC inserted
    """
    lines = content.split('\n')
    insert_index = None

    # Phase 1: Find Executive Summary section and the next ## heading after it
    exec_summary_idx = None
    for i, line in enumerate(lines):
        h2_match = re.match(r'^##\s+(.+)$', line)
        if h2_match:
            header_text = h2_match.group(1).strip().lower()
            if 'executive summary' in header_text:
                exec_summary_idx = i
            elif exec_summary_idx is not None:
                # This is the next h2 after Executive Summary — insert TOC before it
                insert_index = i
                break

    # Phase 2 fallback: insert after first --- (logo/header separator)
    if insert_index is None:
        hr_pattern = r'^---\s*$'
        for i, line in enumerate(lines):
            if re.match(hr_pattern, line):
                insert_index = i + 1
                break

    if insert_index is not None:
        # Insert TOC before the target line
        lines.insert(insert_index, '\n' + toc)
        return '\n'.join(lines)
    else:
        # Last fallback: insert at the beginning
        return toc + '\n' + content


def remove_existing_toc(content: str) -> str:
    """
    Remove existing Table of Contents section from content.

    Finds the TOC heading and all list items below it (up to the next
    ## heading, --- separator, or non-list content) and removes them.

    Args:
        content: Markdown content

    Returns:
        Content with TOC removed
    """
    # Pattern: ## Table of Contents heading, followed by list items (bulleted or numbered,
    # possibly indented), blank lines, and optional trailing --- separator.
    # Remove ALL occurrences to prevent duplicates from multi-pass assembly.
    toc_pattern = r'## Table of Contents\n(?:[ \t]*(?:-|\d+\.)[^\n]*\n)*\n*(?:---\n*)?'
    result = content
    while re.search(toc_pattern, result):
        result = re.sub(toc_pattern, '', result, count=1)
    return result


def extract_existing_toc(content: str) -> str:
    """
    Extract the existing TOC block from content, if present.

    Args:
        content: Markdown content

    Returns:
        The existing TOC block as a string, or empty string if none found
    """
    match = re.search(r'(## Table of Contents\n(?:[ \t]*(?:-|\d+\.)[^\n]*\n)*\n*(?:---\n*)?)', content)
    return match.group(1) if match else ""


def toc_generator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Table of Contents Generator Agent.

    Context-aware: if a TOC already exists, validates its accuracy and location.
    Only rewrites if the TOC is missing, incorrect, or misplaced.

    The correct TOC should:
    - Reflect all current h2/h3 headers in the document
    - Be located after Executive Summary, before the next section
    - Have working anchor links

    Args:
        state: Current memo state

    Returns:
        Updated state with TOC validated/added to final draft
    """
    company_name = state["company_name"]

    # Get output directory (respects state["output_dir"] for resume, falls back to auto-detect)
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("⊘ TOC generation skipped - no output directory found")
        return {"messages": ["TOC generation skipped - no output directory"]}

    from ..final_draft import find_final_draft, read_final_draft
    final_draft_path = find_final_draft(output_dir)

    if not final_draft_path:
        print("⊘ TOC generation skipped - no final draft found")
        return {"messages": ["TOC generation skipped - no final draft"]}

    # Read final draft
    content = read_final_draft(output_dir)

    print("\n📑 Checking Table of Contents...")

    # Strip any existing TOC so we can extract headers from clean content
    # and generate the correct TOC from scratch
    content_without_toc = remove_existing_toc(content)
    had_existing_toc = ('## Table of Contents' in content)

    # Extract headers from the clean (TOC-free) content
    headers = extract_headers(content_without_toc)

    if not headers:
        print("⊘ No headers found, skipping TOC generation")
        return {"messages": ["TOC generation skipped - no headers found"]}

    # Generate the correct TOC
    correct_toc = generate_toc_markdown(headers)

    # If a TOC already existed, check if it matches the correct one
    if had_existing_toc:
        existing_toc = extract_existing_toc(content)
        if existing_toc.strip() == correct_toc.strip():
            # Also verify location: TOC should be before the second h2 heading
            # (i.e., after Executive Summary). Check it's not at the very end or
            # in some other wrong spot.
            toc_pos = content.index('## Table of Contents')
            # Find the second h2 (first non-TOC, non-exec-summary h2)
            h2_positions = [m.start() for m in re.finditer(r'^## (?!Table of Contents)', content, re.MULTILINE)]
            # TOC should be between first and second h2
            if len(h2_positions) >= 2 and h2_positions[0] < toc_pos < h2_positions[1]:
                h2_count = sum(1 for h in headers if h[0] == 2)
                h3_count = sum(1 for h in headers if h[0] == 3)
                print(f"✓ TOC is accurate and correctly placed ({h2_count} sections, {h3_count} subsections)")
                return {"messages": [f"TOC validated: {h2_count} sections, {h3_count} subsections (no changes needed)"]}

        # TOC exists but is wrong or misplaced — will regenerate below
        print("  ⚠️  Existing TOC is outdated or misplaced, regenerating...")

    # Insert correct TOC into the clean content
    updated_content = insert_toc_after_executive_summary(content_without_toc, correct_toc)

    # Save updated final draft
    with open(final_draft_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

    h2_count = sum(1 for h in headers if h[0] == 2)
    h3_count = sum(1 for h in headers if h[0] == 3)

    action = "regenerated" if had_existing_toc else "generated"
    print(f"✓ TOC {action}: {h2_count} sections, {h3_count} subsections")
    print(f"✓ Updated: {final_draft_path}")

    return {
        "messages": [f"TOC {action} with {h2_count} sections and {h3_count} subsections"]
    }

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
    Extract all h2 and h3 headers from markdown content.

    Args:
        content: Markdown content

    Returns:
        List of tuples: (level, header_text, anchor_slug)
        level: 2 for h2, 3 for h3
    """
    headers = []

    # Match h2 (##) and h3 (###) headers
    # Skip headers that are part of citations section
    in_citations = False

    for line in content.split('\n'):
        # Check if we've entered citations section
        if re.match(r'^###?\s*Citations?\s*$', line, re.IGNORECASE):
            in_citations = True
            continue

        if in_citations:
            continue

        # Match h2 headers (## Header)
        h2_match = re.match(r'^##\s+(.+)$', line)
        if h2_match:
            header_text = h2_match.group(1).strip()
            slug = slugify(header_text)
            headers.append((2, header_text, slug))
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

    Args:
        headers: List of (level, header_text, anchor_slug) tuples

    Returns:
        Markdown TOC string with anchor links
    """
    toc_lines = ["## Table of Contents\n"]

    for level, header_text, slug in headers:
        # Indent subsections (h3)
        indent = "  " if level == 3 else ""

        # Create markdown link
        toc_lines.append(f"{indent}- [{header_text}](#{slug})")

    toc_lines.append("")  # Trailing newline

    return "\n".join(toc_lines)


def insert_toc_after_header(content: str, toc: str) -> str:
    """
    Insert TOC after the header section (logo + horizontal rule).

    The memo structure is:
    1. Logo/trademark image
    2. Horizontal rule (---)
    3. [INSERT TOC HERE]
    4. Section content

    Args:
        content: Full memo markdown content
        toc: Generated TOC markdown

    Returns:
        Content with TOC inserted
    """
    # Find the first horizontal rule after the logo
    # Pattern: logo line(s), then ---, then content
    hr_pattern = r'^---\s*$'

    lines = content.split('\n')
    insert_index = None

    for i, line in enumerate(lines):
        if re.match(hr_pattern, line):
            insert_index = i + 1
            break

    if insert_index is not None:
        # Insert TOC after the horizontal rule
        lines.insert(insert_index, '\n' + toc)
        return '\n'.join(lines)
    else:
        # Fallback: insert at the beginning
        return toc + '\n' + content


def toc_generator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Table of Contents Generator Agent.

    Reads the final draft, extracts headers, generates a TOC with anchor links,
    and inserts it into the document.

    Args:
        state: Current memo state

    Returns:
        Updated state with TOC added to final draft
    """
    company_name = state["company_name"]

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name)
    except FileNotFoundError:
        print("⊘ TOC generation skipped - no output directory found")
        return {"messages": ["TOC generation skipped - no output directory"]}

    final_draft_path = output_dir / "4-final-draft.md"

    if not final_draft_path.exists():
        print("⊘ TOC generation skipped - no final draft found")
        return {"messages": ["TOC generation skipped - no final draft"]}

    # Read final draft
    with open(final_draft_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if TOC already exists
    if '## Table of Contents' in content:
        print("⊘ TOC already exists, skipping generation")
        return {"messages": ["TOC already exists"]}

    print("\n📑 Generating Table of Contents...")

    # Extract headers
    headers = extract_headers(content)

    if not headers:
        print("⊘ No headers found, skipping TOC generation")
        return {"messages": ["TOC generation skipped - no headers found"]}

    # Count sections and subsections
    h2_count = sum(1 for h in headers if h[0] == 2)
    h3_count = sum(1 for h in headers if h[0] == 3)

    # Generate TOC
    toc = generate_toc_markdown(headers)

    # Insert TOC into content
    updated_content = insert_toc_after_header(content, toc)

    # Save updated final draft
    with open(final_draft_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

    print(f"✓ TOC generated: {h2_count} sections, {h3_count} subsections")
    print(f"✓ Updated: {final_draft_path}")

    return {
        "messages": [f"TOC generated with {h2_count} sections and {h3_count} subsections"]
    }

"""
Citation Assembly Agent - Consolidates and renumbers citations across all sections.

This agent runs after all citation-adding and cleanup agents to:
1. Collect all citations from section files (2-sections/)
2. Build a global renumbering map (sequential, by first appearance)
3. Remove citation definitions from section bodies
4. Update inline references with new numbers
5. Consolidate all citations into ONE block at document end
6. Assemble the final draft

Can be called:
- As part of the workflow (after remove_invalid_sources, before validate_citations)
- Independently via CLI: python -m src.agents.citation_assembly <output_dir>

Runs AFTER: citation_enrichment, toc_generator, revise_summaries, remove_invalid_sources
Runs BEFORE: validate_citations, fact_checker
"""

import re
import sys
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from collections import OrderedDict

from ..state import MemoState
from ..utils import get_latest_output_dir


def extract_inline_citations(content: str) -> List[str]:
    """
    Extract all inline citation references from content in order of appearance.

    Args:
        content: Markdown content

    Returns:
        List of citation numbers (as strings) in order of first appearance
    """
    seen = set()
    ordered = []

    for match in re.finditer(r'\[\^(\d+)\](?!:)', content):
        num = match.group(1)
        if num not in seen:
            seen.add(num)
            ordered.append(num)

    return ordered


def extract_citation_definitions(content: str) -> Dict[str, str]:
    """
    Extract all citation definitions from content.

    Args:
        content: Markdown content

    Returns:
        Dict mapping citation number to full definition text
    """
    definitions = {}

    # Match citation definitions: [^N]: ... (until next [^ or end of content)
    pattern = r'^\[\^(\d+)\]:\s*(.+?)(?=^\[\^|\Z)'

    for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
        num = match.group(1)
        text = match.group(2).strip()
        definitions[num] = text

    return definitions


def remove_citation_definitions_from_content(content: str) -> str:
    """
    Remove all citation definition blocks from content.

    Args:
        content: Markdown content

    Returns:
        Content with citation definitions removed
    """
    # Remove citation definitions (lines starting with [^N]:)
    lines = content.split('\n')
    filtered = []
    in_citation_block = False

    for line in lines:
        # Check if this line starts a citation definition
        if re.match(r'^\[\^\d+\]:', line):
            in_citation_block = True
            continue

        # Check if we're continuing a multi-line citation
        if in_citation_block:
            # If line is empty or starts with new citation, stay in block
            if line.strip() == '' or re.match(r'^\[\^\d+\]:', line):
                continue
            # If line starts with content (not indented continuation), exit block
            if not line.startswith(' ') and not line.startswith('\t'):
                in_citation_block = False
                filtered.append(line)
            # Otherwise skip (indented continuation)
            continue

        filtered.append(line)

    # Clean up trailing empty lines
    while filtered and filtered[-1].strip() == '':
        filtered.pop()

    return '\n'.join(filtered)


def renumber_inline_citations(content: str, old_to_new: Dict[str, str]) -> str:
    """
    Renumber all inline citation references in content.

    Args:
        content: Markdown content
        old_to_new: Mapping from old citation numbers to new ones

    Returns:
        Content with renumbered citations
    """
    if not old_to_new:
        return content

    # Sort by old number descending to avoid replacement conflicts
    # (replace [^100] before [^10] before [^1])
    for old_num in sorted(old_to_new.keys(), key=lambda x: int(x), reverse=True):
        new_num = old_to_new[old_num]
        # Replace inline references [^N] (not definitions [^N]:)
        content = re.sub(
            rf'\[\^{old_num}\](?!:)',
            f'[^{new_num}]',
            content
        )

    return content


def format_citation_block(citations: Dict[str, str], ordered_nums: List[str]) -> str:
    """
    Format citations as a consolidated markdown block.

    Args:
        citations: Dict mapping citation numbers to definition text
        ordered_nums: List of citation numbers in desired order

    Returns:
        Formatted citation block
    """
    lines = ['\n---\n', '\n### Citations\n']

    for num in ordered_nums:
        if num in citations:
            lines.append(f'[^{num}]: {citations[num]}\n')

    return '\n'.join(lines)


def citation_assembly_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation Assembly Agent implementation.

    Consolidates all citations from section files into a single block
    with sequential numbering.

    Args:
        state: Current memo state

    Returns:
        Updated state with messages
    """
    company_name = state["company_name"]
    firm = state.get("firm")

    print(f"\n📚 Assembling citations for {company_name}...")

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        return {
            "messages": ["Citation assembly skipped: no output directory found"]
        }

    return assemble_citations(output_dir)


def assemble_citations(output_dir: Path) -> Dict[str, Any]:
    """
    Core citation assembly logic. Can be called independently.

    Args:
        output_dir: Path to output directory containing 2-sections/

    Returns:
        Dict with messages and stats
    """
    output_dir = Path(output_dir)
    sections_dir = output_dir / "2-sections"
    header_file = output_dir / "header.md"

    if not sections_dir.exists():
        print("  ⚠️  No sections directory found")
        return {"messages": ["Citation assembly skipped: no sections directory"]}

    # Step 1: Read all sections and collect citations
    print("  📖 Reading sections and collecting citations...")

    all_content_parts = []  # (filename, content) tuples
    all_definitions: Dict[str, str] = {}  # citation_num -> definition
    appearance_order: List[str] = []  # citation numbers in order of first appearance

    # Process header first if exists
    if header_file.exists():
        content = header_file.read_text()
        for num in extract_inline_citations(content):
            if num not in appearance_order:
                appearance_order.append(num)
        all_content_parts.append(("header.md", content))

    # Process sections in order
    section_files = sorted(sections_dir.glob("*.md"))

    for section_file in section_files:
        content = section_file.read_text()

        # Extract inline citations (track order)
        for num in extract_inline_citations(content):
            if num not in appearance_order:
                appearance_order.append(num)

        # Extract definitions
        definitions = extract_citation_definitions(content)
        for num, text in definitions.items():
            if num not in all_definitions:
                all_definitions[num] = text

        all_content_parts.append((section_file.name, content))

    total_citations = len(appearance_order)
    print(f"  📊 Found {total_citations} unique citations across {len(section_files)} sections")

    if total_citations == 0:
        print("  ⚠️  No citations found to assemble")
        return {"messages": ["Citation assembly: no citations found"]}

    # Step 2: Build renumbering map (sequential starting at 1)
    old_to_new: Dict[str, str] = {}
    new_to_old: Dict[str, str] = {}

    for new_num, old_num in enumerate(appearance_order, 1):
        old_to_new[old_num] = str(new_num)
        new_to_old[str(new_num)] = old_num

    # Check if renumbering is needed
    needs_renumbering = any(old != new for old, new in old_to_new.items())

    if needs_renumbering:
        print(f"  🔢 Renumbering {total_citations} citations...")
    else:
        print(f"  ✓ Citations already sequential (1-{total_citations})")

    # Step 3: Process each section - remove definitions and renumber inline refs
    print("  ✏️  Processing sections...")

    for section_file in section_files:
        content = section_file.read_text()
        original = content

        # Remove citation definitions from section
        content = remove_citation_definitions_from_content(content)

        # Renumber inline references
        if needs_renumbering:
            content = renumber_inline_citations(content, old_to_new)

        if content != original:
            section_file.write_text(content)
            print(f"    ✓ {section_file.name}")

    # Process header if exists
    if header_file.exists():
        content = header_file.read_text()
        original = content
        content = remove_citation_definitions_from_content(content)
        if needs_renumbering:
            content = renumber_inline_citations(content, old_to_new)
        if content != original:
            header_file.write_text(content)
            print(f"    ✓ header.md")

    # Step 4: Build renumbered citation definitions
    renumbered_definitions: Dict[str, str] = {}
    for new_num in sorted(new_to_old.keys(), key=int):
        old_num = new_to_old[new_num]
        if old_num in all_definitions:
            renumbered_definitions[new_num] = all_definitions[old_num]
        else:
            print(f"    ⚠️  Warning: No definition found for [^{old_num}] (now [^{new_num}])")

    # Step 5: Assemble final draft
    print("  📄 Assembling final draft...")

    final_parts = []

    # Add header if exists
    if header_file.exists():
        final_parts.append(header_file.read_text())

    # Add all sections
    for section_file in section_files:
        final_parts.append(section_file.read_text())

    # Add consolidated citation block
    citation_block = format_citation_block(
        renumbered_definitions,
        sorted(renumbered_definitions.keys(), key=int)
    )
    final_parts.append(citation_block)

    # Write final draft
    final_content = '\n\n'.join(final_parts)

    # Determine final draft filename
    final_draft_path = None
    for f in output_dir.glob("6-*.md"):
        final_draft_path = f
        break

    if not final_draft_path:
        # Create new final draft with version from directory name
        dir_name = output_dir.name
        final_draft_path = output_dir / f"6-{dir_name}.md"

    final_draft_path.write_text(final_content)
    print(f"  ✓ Final draft: {final_draft_path.name}")

    # Summary
    defined_count = len(renumbered_definitions)
    missing_count = total_citations - defined_count

    summary = f"Assembled {defined_count} citations (sequential 1-{defined_count})"
    if missing_count > 0:
        summary += f", {missing_count} missing definitions"

    print(f"\n  ✅ {summary}")

    return {
        "messages": [summary],
        "citation_assembly": {
            "total_inline_refs": total_citations,
            "definitions_found": defined_count,
            "missing_definitions": missing_count,
            "renumbered": needs_renumbering,
            "final_draft": str(final_draft_path)
        }
    }


# CLI interface for standalone usage
def main():
    """CLI entry point for standalone citation assembly."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.citation_assembly <output_dir>")
        print("Example: python -m src.agents.citation_assembly io/dark-matter/deals/ProfileHealth/outputs/ProfileHealth-v0.0.3")
        sys.exit(1)

    output_dir = Path(sys.argv[1])

    if not output_dir.exists():
        print(f"Error: Directory not found: {output_dir}")
        sys.exit(1)

    result = assemble_citations(output_dir)

    if "error" in str(result.get("messages", [])).lower():
        sys.exit(1)


if __name__ == "__main__":
    main()

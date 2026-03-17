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

    Handles both numeric ([^1], [^2]) and alphanumeric ([^deck], [^ehrtime]) citations.

    Args:
        content: Markdown content

    Returns:
        List of citation keys (as strings) in order of first appearance
    """
    seen = set()
    ordered = []

    # Match both numeric and alphanumeric citation keys
    for match in re.finditer(r'\[\^([a-zA-Z0-9_]+)\](?!:)', content):
        key = match.group(1)
        if key not in seen:
            seen.add(key)
            ordered.append(key)

    return ordered


def extract_citation_definitions(content: str) -> Dict[str, str]:
    """
    Extract all citation definitions from content.

    Handles both numeric ([^1]:) and alphanumeric ([^deck]:) definitions.

    Args:
        content: Markdown content

    Returns:
        Dict mapping citation key to full definition text
    """
    definitions = {}

    # Match citation definitions: [^key]: ... (until next [^ or end of content)
    # Handles numeric and alphanumeric keys
    pattern = r'^\[\^([a-zA-Z0-9_]+)\]:\s*(.+?)(?=^\[\^|\Z)'

    for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
        key = match.group(1)
        text = match.group(2).strip()
        definitions[key] = text

    return definitions


def remove_citation_definitions_from_content(content: str) -> str:
    """
    Remove all citation definition blocks from content.

    Handles both numeric ([^1]:) and alphanumeric ([^deck]:) definitions.

    Args:
        content: Markdown content

    Returns:
        Content with citation definitions removed
    """
    # Remove citation definitions (lines starting with [^key]:)
    lines = content.split('\n')
    filtered = []
    in_citation_block = False

    for line in lines:
        # Check if this line starts a citation definition (numeric or alphanumeric)
        if re.match(r'^\[\^[a-zA-Z0-9_]+\]:', line):
            in_citation_block = True
            continue

        # Check if we're continuing a multi-line citation
        if in_citation_block:
            # If line is empty or starts with new citation, stay in block
            if line.strip() == '' or re.match(r'^\[\^[a-zA-Z0-9_]+\]:', line):
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

    result = '\n'.join(filtered)

    # Remove empty "### Citations" header (with optional preceding ---)
    result = re.sub(r'\n*---\n*### Citations\s*$', '', result, flags=re.MULTILINE)
    result = re.sub(r'\n*### Citations\s*$', '', result, flags=re.MULTILINE)

    return result.rstrip()


def renumber_inline_citations(content: str, old_to_new: Dict[str, str]) -> str:
    """
    Renumber all inline citation references in content.

    Handles both numeric and alphanumeric citation keys.

    Args:
        content: Markdown content
        old_to_new: Mapping from old citation keys to new ones

    Returns:
        Content with renumbered citations
    """
    if not old_to_new:
        return content

    # Sort by key length descending to avoid replacement conflicts
    # (replace [^deck] before [^1], and [^100] before [^10] before [^1])
    def sort_key(key):
        # Longer keys first, then by numeric value or alphabetically
        try:
            return (-len(key), int(key), '')
        except ValueError:
            return (-len(key), 0, key)

    for old_key in sorted(old_to_new.keys(), key=sort_key):
        new_key = old_to_new[old_key]
        # Replace inline references [^key] (not definitions [^key]:)
        content = re.sub(
            rf'\[\^{re.escape(old_key)}\](?!:)',
            f'[^{new_key}]',
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

    # Get output directory from state (created at workflow start)
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        return {
            "messages": ["Citation assembly skipped: no output directory found"]
        }

    return assemble_citations(output_dir)


def renumber_citations(output_dir: Path) -> Dict[str, Any]:
    """
    Renumber citations in section files and build a consolidated citation block.

    This is the RENUMBERING-ONLY function. It:
    1. Reads all sections and collects citations
    2. Builds a sequential renumbering map
    3. Renumbers inline refs in section files (writes back to disk)
    4. Removes citation definitions from section files
    5. Returns the consolidated citation block as a string

    Does NOT assemble the final draft — that's the assembler's job.

    Args:
        output_dir: Path to output directory containing 2-sections/

    Returns:
        Dict with:
          - "citation_block": str — the consolidated citation definitions block
          - "stats": dict with total_inline_refs, definitions_found, etc.
          - "messages": list of status messages
    """
    output_dir = Path(output_dir)
    sections_dir = output_dir / "2-sections"
    research_dir = output_dir / "1-research"
    header_file = output_dir / "header.md"

    if not sections_dir.exists():
        print("  ⚠️  No sections directory found")
        return {"citation_block": "", "stats": {}, "messages": ["Citation renumbering skipped: no sections directory"]}

    # Step 1: Read all sections and collect citations
    print("  📖 Reading sections and collecting citations...")

    all_definitions: Dict[str, str] = {}  # citation_num -> definition
    appearance_order: List[str] = []  # citation numbers in order of first appearance

    # Process header first if exists
    if header_file.exists():
        content = header_file.read_text()
        for num in extract_inline_citations(content):
            if num not in appearance_order:
                appearance_order.append(num)

    # Process sections in order
    section_files = sorted(sections_dir.glob("*.md"))

    for section_file in section_files:
        content = section_file.read_text()

        # Extract inline citations (track order)
        for num in extract_inline_citations(content):
            if num not in appearance_order:
                appearance_order.append(num)

        # Extract definitions from sections
        definitions = extract_citation_definitions(content)
        for num, text in definitions.items():
            if num not in all_definitions:
                all_definitions[num] = text

    # Also collect definitions from 1-research/ as fallback source
    # (definitions may have been stripped from sections in previous runs)
    if research_dir.exists():
        for research_file in sorted(research_dir.glob("*.md")):
            content = research_file.read_text()
            definitions = extract_citation_definitions(content)
            for num, text in definitions.items():
                if num not in all_definitions:
                    all_definitions[num] = text

    total_citations = len(appearance_order)
    print(f"  📊 Found {total_citations} unique citations across {len(section_files)} sections")

    if total_citations == 0:
        print("  ℹ️  No citations found")
        return {"citation_block": "", "stats": {"total_inline_refs": 0, "definitions_found": 0, "missing_definitions": 0, "renumbered": False}, "messages": ["No citations to renumber"]}

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

    # Build citation block string
    citation_block = ""
    if renumbered_definitions:
        citation_block = format_citation_block(
            renumbered_definitions,
            sorted(renumbered_definitions.keys(), key=int)
        )

    defined_count = len(renumbered_definitions)
    missing_count = total_citations - defined_count

    summary = f"Renumbered {defined_count} citations (sequential 1-{defined_count})"
    if missing_count > 0:
        summary += f", {missing_count} missing definitions"

    print(f"\n  ✅ {summary}")

    return {
        "citation_block": citation_block,
        "stats": {
            "total_inline_refs": total_citations,
            "definitions_found": defined_count,
            "missing_definitions": missing_count,
            "renumbered": needs_renumbering,
        },
        "messages": [summary],
    }


def assemble_citations(output_dir: Path) -> Dict[str, Any]:
    """
    Full citation assembly: renumber citations AND assemble the final draft.

    This is the pipeline-facing function used by the workflow agent.
    It calls renumber_citations() for the renumbering, then concatenates
    sections + citation block into the final draft file.

    Args:
        output_dir: Path to output directory containing 2-sections/

    Returns:
        Dict with messages and stats
    """
    output_dir = Path(output_dir)
    sections_dir = output_dir / "2-sections"
    header_file = output_dir / "header.md"

    # Step 1: Renumber citations (stays in its lane)
    renumber_result = renumber_citations(output_dir)
    citation_block = renumber_result.get("citation_block", "")

    if not sections_dir.exists():
        return renumber_result

    # Step 2: Assemble final draft from renumbered sections
    print("  📄 Assembling final draft...")

    final_parts = []

    # Add header if exists
    if header_file.exists():
        final_parts.append(header_file.read_text())

    # Add all sections
    section_files = sorted(sections_dir.glob("*.md"))
    for section_file in section_files:
        final_parts.append(section_file.read_text())

    # Add consolidated citation block at the end
    if citation_block:
        final_parts.append(citation_block)

    # Write final draft
    final_content = '\n\n'.join(final_parts)

    # Use canonical final draft path from final_draft module
    from ..final_draft import get_final_draft_path
    final_draft_path = get_final_draft_path(output_dir)
    final_draft_path.write_text(final_content)
    print(f"  ✓ Final draft: {final_draft_path.name}")

    stats = renumber_result.get("stats", {})
    stats["final_draft"] = str(final_draft_path)

    return {
        "messages": renumber_result.get("messages", []),
        "citation_assembly": stats,
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

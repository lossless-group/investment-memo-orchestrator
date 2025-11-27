#!/usr/bin/env python3
"""
Consolidate section-level citations to the bottom of a markdown file.

This script takes a final draft that has ### Citations blocks scattered
throughout (one per section) and consolidates them into ONE citation block
at the end with globally renumbered footnotes.

Usage:
    python consolidate_citations.py <final-draft.md>
    python consolidate_citations.py output/Company-v0.0.3/4-final-draft.md
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict


def consolidate_citations_from_file(content: str) -> str:
    """
    Consolidate all section-level ### Citations blocks into one at the bottom.

    Renumbers all footnotes globally so [^1] in section 1 and [^1] in section 2
    become [^1] and [^N] respectively.
    """
    # First, fix the malformed concatenation where citations run into next section
    # Pattern: text immediately followed by # or ## Section (no newline)
    # This handles cases like: "N/A# GP Background" -> "N/A\n\n# GP Background"
    # But NOT ### Citations (we want to keep that together)
    content = re.sub(r'([^\n#])(#{1,2} [A-Z])', r'\1\n\n\2', content)

    # Split by "### Citations" to separate content from citation blocks
    parts = content.split("### Citations")

    if len(parts) <= 1:
        print("No multiple citation blocks found - nothing to consolidate")
        return content

    # Track all content sections and their citations
    content_sections = []
    citation_blocks = []

    # First part is always pure content up to first citations
    content_sections.append(parts[0])

    for i, part in enumerate(parts[1:], 1):
        # Each part after split starts with citation content
        # Find where citations end - at next section header (# or ##) or --- divider

        # Look for next section header or divider
        next_section_match = re.search(r'\n(#+\s+[A-Z]|---\s*\n)', part)

        if next_section_match:
            citation_text = part[:next_section_match.start()].strip()
            remaining_content = part[next_section_match.start():]
            content_sections.append(remaining_content)
        else:
            citation_text = part.strip()

        if citation_text:
            citation_blocks.append(citation_text)

    # Now renumber citations globally
    all_citation_defs = []  # List of (new_num, definition_text)
    citation_counter = 1
    section_maps = []  # List of dicts mapping old_num -> new_num for each block

    for block_idx, block in enumerate(citation_blocks):
        section_map = {}

        # Find all citation definitions in this block
        # Pattern: [^N]: followed by content until next [^M]: or end
        def_pattern = r'\[\^([^\]]+)\]:\s*(.+?)(?=\[\^[^\]]+\]:|$)'
        defs = re.findall(def_pattern, block, re.DOTALL)

        for old_label, definition in defs:
            # Skip if we've already seen this exact definition (dedup)
            def_text = definition.strip()
            section_map[old_label] = str(citation_counter)
            all_citation_defs.append((citation_counter, def_text))
            citation_counter += 1

        section_maps.append(section_map)

    # Now update inline citations in content sections
    # The tricky part: content_sections[0] uses citation_blocks[0]'s numbering
    # But wait - actually each section's citations appear AFTER the section content
    # So content_sections[0] has inline [^N] that reference citation_blocks[0]
    # And content_sections[1] (which comes after citation_blocks[0]) has inline [^N]
    # that reference citation_blocks[1], etc.

    # Actually the relationship is:
    # content_sections[0] -> uses numbering that will be in citation_blocks[0]
    # content_sections[1] -> uses numbering that will be in citation_blocks[1]
    # etc.

    # But we appended content AFTER the citations split, so:
    # content_sections[0] = text before first ### Citations
    # content_sections[1] = text after first citations block up to second ### Citations
    # etc.

    # So content_sections[i] uses section_maps[i] for i > 0? No wait...
    # Let me think again:

    # Original: Section1 Content | ### Citations | Citations1 | Section2 Content | ### Citations | Citations2
    # After split: ["Section1 Content ", " Citations1 | Section2 Content ", " Citations2"]

    # So parts[0] = "Section1 Content " (uses Citations1's numbering)
    # parts[1] = " Citations1 | Section2 Content " -> citation_blocks[0] = Citations1, content_sections[1] = Section2 Content
    # parts[2] = " Citations2" -> citation_blocks[1] = Citations2

    # Hmm, actually content_sections[0]'s inline refs are defined in citation_blocks[0]
    # content_sections[1]'s inline refs are defined in citation_blocks[1]
    # etc.

    # So section_maps[i] should be applied to content_sections[i]

    updated_sections = []
    for i, section_content in enumerate(content_sections):
        if i < len(section_maps):
            section_map = section_maps[i]
            # Replace inline citations
            updated = section_content
            # Sort by length of old_label descending to avoid [^1] replacing part of [^10]
            for old_label in sorted(section_map.keys(), key=lambda x: -len(x)):
                new_num = section_map[old_label]
                # Replace [^old_label] with [^new_num] but not [^old_label]:
                updated = re.sub(
                    rf'\[\^{re.escape(old_label)}\](?!:)',
                    f'[^{new_num}]',
                    updated
                )
            updated_sections.append(updated)
        else:
            updated_sections.append(section_content)

    # Build final content
    final_content = "".join(updated_sections).strip()

    # Remove any stray "### Citations" that might have been left
    final_content = re.sub(r'\n### Citations\s*\n', '\n', final_content)

    # Clean up excessive newlines
    final_content = re.sub(r'\n{3,}', '\n\n', final_content)

    # Add consolidated citations at end
    if all_citation_defs:
        final_content += "\n\n### Citations\n\n"
        for num, definition in all_citation_defs:
            final_content += f"[^{num}]: {definition}\n\n"

    return final_content.strip() + "\n"


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Consolidate section-level citations to bottom of markdown file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s output/Company-v0.0.3/4-final-draft.md
    %(prog)s memo.md -o memo-consolidated.md
    %(prog)s memo.md --dry-run
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        help='Markdown file to consolidate'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output file (default: overwrite input)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without modifying files'
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: File not found: {args.input}")
        return 1

    print(f"Reading: {args.input}")

    with open(args.input, 'r', encoding='utf-8') as f:
        original_content = f.read()

    # Count citation blocks before
    blocks_before = original_content.count("### Citations")
    print(f"Found {blocks_before} '### Citations' blocks")

    if blocks_before <= 1:
        print("Already consolidated or no citations - nothing to do")
        return 0

    # Consolidate
    consolidated = consolidate_citations_from_file(original_content)

    # Count after
    blocks_after = consolidated.count("### Citations")
    citations_after = len(re.findall(r'\[\^\d+\]:', consolidated))

    print(f"Consolidated to {blocks_after} citation block with {citations_after} unique citations")

    if args.dry_run:
        print("\n(dry-run: no changes written)")
        print("\n--- Preview (first 2000 chars of citations section) ---")
        cit_start = consolidated.rfind("### Citations")
        if cit_start > 0:
            print(consolidated[cit_start:cit_start+2000])
        return 0

    # Write output
    output_path = args.output or args.input

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(consolidated)

    print(f"✓ Saved: {output_path}")

    return 0


if __name__ == '__main__':
    sys.exit(main())

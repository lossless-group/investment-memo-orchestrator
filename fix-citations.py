#!/usr/bin/env python3
"""
Fix duplicate citations in HTML exports to match Obsidian-style behavior.

This script:
1. Identifies duplicate footnote content
2. Consolidates references to the same source
3. Shows multiple back-references (↩︎ ↩︎ ↩︎) for repeated citations
4. Renumbers citations to match deduplicated sources
"""

import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


def extract_footnotes(html_content: str) -> Dict[str, Tuple[str, str]]:
    """
    Extract all footnotes from HTML.

    Returns:
        Dict mapping footnote ID to (content, backref_id)
    """
    footnotes = {}

    # Match footnote list items like:
    # <li id="fn1"><p>Content...<a href="#fnref1" class="footnote-back" role="doc-backlink">↩︎</a></p></li>
    # Note: content may span multiple lines and include links
    pattern = r'<li\s+id="(fn\d+)"><p>(.*?)<a\s+href="#(fnref\d+)"\s+class="footnote-back"[^>]*>↩︎</a></p></li>'

    for match in re.finditer(pattern, html_content, re.DOTALL):
        fn_id = match.group(1)
        content = match.group(2).strip()
        backref_id = match.group(3)
        footnotes[fn_id] = (content, backref_id)

    return footnotes


def find_duplicate_sources(footnotes: Dict[str, Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    Find footnotes with identical content.

    Returns:
        Dict mapping content to list of footnote IDs with that content
    """
    content_to_ids = defaultdict(list)

    for fn_id, (content, _) in footnotes.items():
        # Normalize content for comparison
        normalized = re.sub(r'\s+', ' ', content).strip()
        content_to_ids[normalized].append(fn_id)

    # Only return duplicates
    return {content: ids for content, ids in content_to_ids.items() if len(ids) > 1}


def consolidate_footnotes(html_content: str) -> str:
    """
    Consolidate duplicate footnotes in HTML.

    Process:
    1. Find all footnotes and their content
    2. Identify duplicates (same URL/content)
    3. Keep first instance, map others to it
    4. Update all references to use first instance
    5. Add multiple back-arrows for consolidated refs
    """

    # Extract all footnotes
    footnotes = extract_footnotes(html_content)

    if not footnotes:
        print("⚠️  No footnotes found in HTML")
        return html_content

    print(f"Found {len(footnotes)} footnote definitions")

    # Find duplicates
    duplicates = find_duplicate_sources(footnotes)

    if not duplicates:
        print("✓ No duplicate footnotes found")
        return html_content

    print(f"Found {len(duplicates)} unique sources with duplicates")

    # Create mapping: duplicate ID -> canonical ID
    canonical_map = {}
    sources_to_remove = set()

    for content, ids in duplicates.items():
        # First ID is canonical
        canonical_id = ids[0]
        canonical_num = canonical_id[2:]  # Remove 'fn' prefix

        print(f"\nConsolidating {len(ids)} refs to same source:")
        print(f"  Canonical: {canonical_id}")

        for dup_id in ids[1:]:
            canonical_map[dup_id] = canonical_id
            sources_to_remove.add(dup_id)
            print(f"  Duplicate: {dup_id} -> {canonical_id}")

    # Step 1: Update all in-text references to use canonical IDs
    for dup_id, canonical_id in canonical_map.items():
        dup_num = dup_id[2:]
        canonical_num = canonical_id[2:]
        dup_ref_id = f"fnref{dup_num}"
        canonical_ref_id = f"fnref{canonical_num}"

        # Replace in-text reference links
        # <a href="#fn3" class="footnote-ref" id="fnref3" role="doc-noteref"><sup>3</sup></a>
        # becomes
        # <a href="#fn2" class="footnote-ref" id="fnref3" role="doc-noteref"><sup>2</sup></a>
        pattern = f'<a href="#{dup_id}"([^>]*id="{dup_ref_id}"[^>]*)><sup>{dup_num}</sup></a>'
        replacement = f'<a href="#{canonical_id}"\\1><sup>{canonical_num}</sup></a>'
        html_content = re.sub(pattern, replacement, html_content)

    # Step 2: Collect all backrefs for each canonical footnote
    backref_counts = defaultdict(list)

    # Find all in-text references
    ref_pattern = r'<a href="#(fn\d+)"[^>]*id="(fnref\d+)"[^>]*><sup>(\d+)</sup></a>'
    for match in re.finditer(ref_pattern, html_content):
        fn_id = match.group(1)
        fnref_id = match.group(2)
        backref_counts[fn_id].append(fnref_id)

    # Step 3: Update footnote entries with multiple back-arrows
    footnote_section_pattern = r'<section id="footnotes"[^>]*>.*?</section>'
    footnote_section_match = re.search(footnote_section_pattern, html_content, re.DOTALL)

    if not footnote_section_match:
        print("⚠️  Could not find footnotes section")
        return html_content

    footnote_section = footnote_section_match.group(0)
    new_footnote_section = footnote_section

    # Remove duplicate footnote entries
    for dup_id in sources_to_remove:
        dup_num = dup_id[2:]
        # Remove entire <li> entry for duplicate
        pattern = f'<li id="{dup_id}">.*?</li>'
        new_footnote_section = re.sub(pattern, '', new_footnote_section, flags=re.DOTALL)

    # Update canonical entries with multiple back-arrows
    for fn_id, fnref_ids in backref_counts.items():
        if len(fnref_ids) > 1:
            # Create multiple back-arrows
            back_arrows = ' '.join([
                f'<a href="#{fnref_id}" class="footnote-back" role="doc-backlink">↩︎</a>'
                for fnref_id in fnref_ids
            ])

            # Replace single back-arrow with multiple
            single_pattern = f'(<li id="{fn_id}"><p>.*?)<a href="#fnref\\d+" class="footnote-back"[^>]*>↩︎</a>(</p></li>)'
            replacement = f'\\1{back_arrows}\\2'
            new_footnote_section = re.sub(single_pattern, replacement, new_footnote_section, flags=re.DOTALL)

    # Replace the footnote section
    html_content = html_content.replace(footnote_section, new_footnote_section)

    # Step 4: Renumber remaining footnotes sequentially (1, 2, 3 instead of 1, 2, 9)
    remaining_ids = sorted([fn_id for fn_id in footnotes.keys() if fn_id not in sources_to_remove],
                          key=lambda x: int(x[2:]))  # Sort by number

    renumber_map = {}
    for new_num, old_id in enumerate(remaining_ids, start=1):
        old_num = old_id[2:]
        if int(old_num) != new_num:
            renumber_map[old_id] = f"fn{new_num}"

    if renumber_map:
        print(f"\nRenumbering {len(renumber_map)} footnotes for sequential ordering...")

        for old_id, new_id in renumber_map.items():
            old_num = old_id[2:]
            new_num = new_id[2:]

            # Update footnote definition
            html_content = re.sub(f'<li\\s+id="{old_id}">', f'<li id="{new_id}">', html_content)

            # Update all in-text references
            html_content = re.sub(f'<a\\s+href="#{old_id}"([^>]*><sup>){old_num}(</sup></a>)',
                                f'<a href="#{new_id}"\\g<1>{new_num}\\g<2>',
                                html_content)

            # Update all backrefs in footnotes section
            html_content = re.sub(f'<a\\s+href="#fnref{old_num}"',
                                f'<a href="#fnref{new_num}"',
                                html_content)

            # Update fnref IDs in text
            html_content = re.sub(f'id="fnref{old_num}"',
                                f'id="fnref{new_num}"',
                                html_content)

    # Calculate stats
    removed_count = len(sources_to_remove)
    remaining_count = len(footnotes) - removed_count

    print(f"\n✓ Consolidated {removed_count} duplicate footnotes")
    print(f"✓ {remaining_count} unique sources remain")

    return html_content


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Fix duplicate citations in HTML exports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s exports/Bear-AI.html                    # Fix in place
  %(prog)s exports/Bear-AI.html -o fixed.html      # Save to new file
  %(prog)s exports/*.html                          # Fix multiple files
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        nargs='+',
        help='HTML file(s) to fix'
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

    files = []
    for path in args.input:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.glob('*.html'))

    if not files:
        print("No HTML files found")
        return 1

    print(f"Processing {len(files)} file(s)...\n")

    for html_file in files:
        print(f"\n{'='*60}")
        print(f"File: {html_file.name}")
        print(f"{'='*60}")

        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                original_content = f.read()

            fixed_content = consolidate_footnotes(original_content)

            if args.dry_run:
                print("(dry-run: no changes written)")
                continue

            # Determine output path
            if args.output and len(files) == 1:
                output_path = args.output
            else:
                output_path = html_file

            # Write fixed content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)

            print(f"\n✓ Saved: {output_path}")

        except Exception as e:
            print(f"\n✗ Error processing {html_file.name}: {e}")
            import traceback
            traceback.print_exc()

    return 0


if __name__ == '__main__':
    sys.exit(main())

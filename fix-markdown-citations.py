#!/usr/bin/env python3
"""
Consolidate duplicate citations in Markdown files.

This script:
1. Finds footnote definitions with identical content
2. Maps duplicates to the first occurrence
3. Updates all in-text references to use consolidated footnote numbers
4. Removes duplicate footnote definitions

This ensures that when the same source is cited multiple times, it uses
the same footnote number (e.g., [^2] everywhere instead of [^2], [^3], [^4]
for the same URL).
"""

import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


def extract_footnote_definitions(content: str) -> Dict[str, str]:
    """
    Extract all footnote definitions from markdown.

    Returns:
        Dict mapping footnote label (e.g., "1") to content
    """
    footnotes = {}

    # Match footnote definitions like:
    # [^1]: Content here
    # Can span multiple lines until next footnote or end
    pattern = r'^\[\^(\d+)\]:\s*(.+?)(?=^\[\^\d+\]:|$)'

    for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
        label = match.group(1)
        footnote_content = match.group(2).strip()
        footnotes[label] = footnote_content

    return footnotes


def normalize_footnote_content(content: str) -> str:
    """Normalize footnote content for comparison."""
    # Remove extra whitespace and normalize
    normalized = re.sub(r'\s+', ' ', content).strip()
    return normalized


def find_duplicate_footnotes(footnotes: Dict[str, str]) -> Dict[str, List[str]]:
    """
    Find footnotes with identical content.

    Returns:
        Dict mapping content to list of labels with that content
    """
    content_to_labels = defaultdict(list)

    for label, content in footnotes.items():
        normalized = normalize_footnote_content(content)
        content_to_labels[normalized].append(label)

    # Only return duplicates
    return {content: labels for content, labels in content_to_labels.items() if len(labels) > 1}


def consolidate_markdown_citations(content: str) -> Tuple[str, int, int]:
    """
    Consolidate duplicate citations in markdown.

    Returns:
        Tuple of (updated_content, duplicates_removed, total_citations)
    """

    # Extract all footnote definitions
    footnotes = extract_footnote_definitions(content)

    if not footnotes:
        return content, 0, 0

    total_citations = len(footnotes)

    # Find duplicates
    duplicates = find_duplicate_footnotes(footnotes)

    if not duplicates:
        return content, 0, total_citations

    print(f"Found {len(duplicates)} unique sources with duplicates")

    # Create mapping: duplicate label -> canonical label
    label_map = {}
    labels_to_remove = set()

    for footnote_content, labels in duplicates.items():
        # Sort labels numerically to keep lowest number as canonical
        labels_sorted = sorted(labels, key=int)
        canonical_label = labels_sorted[0]

        print(f"\nConsolidating {len(labels)} refs to same source:")
        print(f"  Canonical: [^{canonical_label}]")

        for dup_label in labels_sorted[1:]:
            label_map[dup_label] = canonical_label
            labels_to_remove.add(dup_label)
            print(f"  Duplicate: [^{dup_label}] -> [^{canonical_label}]")

    # Step 1: Replace in-text citations
    for dup_label, canonical_label in label_map.items():
        # Replace [^3] with [^2] (for example)
        content = re.sub(
            rf'\[\^{dup_label}\]',
            f'[^{canonical_label}]',
            content
        )

    # Step 2: Remove duplicate footnote definitions
    for dup_label in labels_to_remove:
        # Remove entire footnote definition
        # Match from [^N]: to either next footnote or end of file
        pattern = rf'^\[\^{dup_label}\]:.*?(?=^\[\^\d+\]:|$)'
        content = re.sub(pattern, '', content, flags=re.MULTILINE | re.DOTALL)

    # Step 3: Clean up extra blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)

    duplicates_removed = len(labels_to_remove)

    return content, duplicates_removed, total_citations


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Consolidate duplicate citations in Markdown files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s memo.md                    # Fix in place
  %(prog)s memo.md -o fixed.md        # Save to new file
  %(prog)s output/*.md                # Fix multiple files
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        nargs='+',
        help='Markdown file(s) to fix'
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
            files.extend(path.glob('*.md'))

    if not files:
        print("No Markdown files found")
        return 1

    print(f"Processing {len(files)} file(s)...\n")

    for md_file in files:
        print(f"\n{'='*60}")
        print(f"File: {md_file.name}")
        print(f"{'='*60}")

        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                original_content = f.read()

            fixed_content, removed, total = consolidate_markdown_citations(original_content)

            if removed == 0:
                print("✓ No duplicate footnotes found")
            else:
                print(f"\n✓ Consolidated {removed} duplicate footnotes")
                print(f"✓ {total - removed} unique sources remain")

            if args.dry_run:
                print("(dry-run: no changes written)")
                continue

            # Determine output path
            if args.output and len(files) == 1:
                output_path = args.output
            else:
                output_path = md_file

            # Write fixed content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)

            print(f"\n✓ Saved: {output_path}")

        except Exception as e:
            print(f"\n✗ Error processing {md_file.name}: {e}")
            import traceback
            traceback.print_exc()

    return 0


if __name__ == '__main__':
    sys.exit(main())

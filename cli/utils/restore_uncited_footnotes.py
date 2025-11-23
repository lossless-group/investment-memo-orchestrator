#!/usr/bin/env python3
"""
Restore unreferenced footnotes to HTML that Pandoc excluded.

Pandoc only includes footnotes that are referenced in the text. This script
adds back any footnote definitions from the markdown that weren't included.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Set


def extract_markdown_footnotes(md_content: str) -> Dict[int, str]:
    """Extract all footnote definitions from markdown."""
    footnotes = {}

    # Match footnote definitions: [^1]: Content
    pattern = r'^\[\^(\d+)\]:\s*(.+?)(?=^\[\^\d+\]:|$)'

    for match in re.finditer(pattern, md_content, re.MULTILINE | re.DOTALL):
        num = int(match.group(1))
        content = match.group(2).strip()
        footnotes[num] = content

    return footnotes


def extract_html_footnote_ids(html_content: str) -> Set[int]:
    """Extract footnote IDs that are in the HTML."""
    ids = set()

    # Find footnote list items: <li id="fn1">
    pattern = r'<li\s+id="fn(\d+)">'

    for match in re.finditer(pattern, html_content):
        ids.add(int(match.group(1)))

    return ids


def add_uncited_footnotes(html_content: str, md_content: str) -> str:
    """Add unreferenced footnotes from markdown to HTML."""

    # Extract footnotes from both sources
    md_footnotes = extract_markdown_footnotes(md_content)
    html_ids = extract_html_footnote_ids(html_content)

    # Find uncited footnotes
    uncited = {num: content for num, content in md_footnotes.items()
               if num not in html_ids}

    if not uncited:
        print("✓ All footnotes are cited")
        return html_content

    print(f"Found {len(uncited)} uncited footnote(s): {sorted(uncited.keys())}")

    # Find the footnotes section
    footnote_section_pattern = r'(<section id="footnotes"[^>]*>.*?<ol>)(.*?)(</ol>.*?</section>)'
    match = re.search(footnote_section_pattern, html_content, re.DOTALL)

    if not match:
        print("⚠️  No footnotes section found in HTML")
        return html_content

    section_start = match.group(1)
    existing_list = match.group(2)
    section_end = match.group(3)

    # Generate HTML for uncited footnotes
    uncited_html = []
    for num in sorted(uncited.keys()):
        content = uncited[num]

        # Convert markdown links to HTML if present
        content = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', content)

        # Create list item without backref (since it's not cited)
        uncited_html.append(
            f'        <li id="fn{num}"><p>{content} '
            f'<em style="color: var(--brand-text-light); font-size: 0.9em;">(Uncited)</em></p></li>'
        )

    # Insert uncited footnotes at the end of the list
    new_list = existing_list.rstrip() + '\n' + '\n'.join(uncited_html) + '\n        '
    new_section = section_start + new_list + section_end

    # Replace the footnotes section
    html_content = re.sub(footnote_section_pattern, new_section, html_content, flags=re.DOTALL)

    print(f"✓ Added {len(uncited)} uncited footnote(s) to HTML")

    return html_content


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Add unreferenced footnotes to HTML that Pandoc excluded'
    )

    parser.add_argument(
        'html_file',
        type=Path,
        help='HTML file to process'
    )

    parser.add_argument(
        'markdown_file',
        type=Path,
        help='Original markdown file with all footnote definitions'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without modifying file'
    )

    args = parser.parse_args()

    if not args.html_file.exists():
        print(f"Error: HTML file not found: {args.html_file}")
        return 1

    if not args.markdown_file.exists():
        print(f"Error: Markdown file not found: {args.markdown_file}")
        return 1

    print(f"Processing: {args.html_file.name}")
    print(f"Source: {args.markdown_file.name}\n")

    try:
        with open(args.html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        with open(args.markdown_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        updated_html = add_uncited_footnotes(html_content, md_content)

        if args.dry_run:
            print("\n(dry-run: no changes written)")
            return 0

        with open(args.html_file, 'w', encoding='utf-8') as f:
            f.write(updated_html)

        print(f"\n✓ Updated: {args.html_file}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
Fix duplicate citation sections in research files.

The citation_enrichment agent sometimes appends a second ### Citations section
instead of merging. This script consolidates all citation definitions into a
single section.

Usage:
    python scripts/fix_duplicate_citations.py <research_dir>

Example:
    python scripts/fix_duplicate_citations.py io/dark-matter/deals/ExoLux/outputs/ExoLux-v0.0.2/1-research
"""

import re
import sys
from pathlib import Path


def fix_duplicate_citations(filepath: Path) -> bool:
    """
    Fix a file that has multiple ### Citations sections.

    Args:
        filepath: Path to the markdown file

    Returns:
        True if file was modified, False if no changes needed
    """
    content = filepath.read_text()

    # Check if there are multiple ### Citations sections
    if content.count("### Citations") <= 1:
        return False

    # Split on ### Citations
    parts = content.split("### Citations")
    main_content = parts[0].rstrip()

    # Also remove any trailing "---" separator from main content
    if main_content.endswith("---"):
        main_content = main_content[:-3].rstrip()

    # Collect all citation definitions from all sections
    all_defs = {}
    for section in parts[1:]:
        # Clean up the section - remove leading/trailing separators
        section = section.strip()
        if section.startswith("---"):
            section = section[3:].strip()

        # Extract citation definitions
        # Pattern matches [^key]: followed by content until next [^ or end
        for match in re.finditer(r'\[\^([a-zA-Z0-9_]+)\]:\s*(.+?)(?=\n\[\^|\Z)', section, re.DOTALL):
            key = match.group(1)
            text = match.group(2).strip()
            if key not in all_defs:
                all_defs[key] = text

    # Build new citations section with sorted keys
    # Sort: alphabetic keys first (like 'deck'), then numeric keys in order
    def sort_key(k):
        try:
            return (1, int(k), '')  # Numeric keys: sort by number
        except ValueError:
            return (0, 0, k)  # Alphabetic keys: sort alphabetically, come first

    citations = []
    for key in sorted(all_defs.keys(), key=sort_key):
        citations.append(f"[^{key}]: {all_defs[key]}")

    # Rebuild content
    new_content = main_content + "\n\n### Citations\n\n" + "\n\n".join(citations) + "\n"

    filepath.write_text(new_content)
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/fix_duplicate_citations.py <research_dir>")
        print("Example: python scripts/fix_duplicate_citations.py io/dark-matter/deals/ExoLux/outputs/ExoLux-v0.0.2/1-research")
        sys.exit(1)

    research_dir = Path(sys.argv[1])

    if not research_dir.exists():
        print(f"Error: Directory not found: {research_dir}")
        sys.exit(1)

    fixed = 0
    for f in sorted(research_dir.glob("*.md")):
        if fix_duplicate_citations(f):
            print(f"Fixed: {f.name}")
            fixed += 1
        else:
            print(f"OK: {f.name}")

    print(f"\nTotal files fixed: {fixed}")


if __name__ == "__main__":
    main()

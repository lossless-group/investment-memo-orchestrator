"""
Citation Spacing Agent — Ensures correct spacing of inline citations in markdown.

This agent enforces the citation spacing rules documented in:
  context-v/reminders/Extended-Markdown-Citation-System-Syntax.md
  context-v/reminders/Citation-Reminders.md

Rules enforced:
  1. Exactly one space before an inline citation after punctuation or word:
     "claim.[^1]"  → "claim. [^1]"
     "claim [^1]"  → (correct, no change)

  2. Exactly one space between consecutive citations:
     "[^1][^2]"    → "[^1] [^2]"
     "[^1]  [^2]"  → "[^1] [^2]"

  3. No duplicate consecutive citations:
     "[^3] [^3]"   → "[^3]"

  4. Citation definitions start at column 0 with no space before bracket:
     " [^1]: text"  → "[^1]: text"

  5. Exactly one space after the colon in definitions:
     "[^1]:text"    → "[^1]: text"
     "[^1]:  text"  → "[^1]: text"

Pipeline position: runs after assemble_citations, before or after toc.
This is a purely mechanical agent — no LLM calls.
"""

import re
from typing import Dict, Any
from pathlib import Path

from ..state import MemoState


def fix_citation_spacing(content: str) -> str:
    """
    Fix all citation spacing issues in markdown content.

    Args:
        content: Markdown text with inline citations

    Returns:
        Content with corrected citation spacing
    """
    # Rule 1: Ensure exactly one space before inline citation after punctuation or word
    # "claim.[^1]" → "claim. [^1]"
    # "claim,[^1]" → "claim, [^1]"
    # But NOT definition lines "[^1]: ..."
    content = re.sub(r'([.!?,;:])(\[\^)', r'\1 \2', content)

    # "claimword[^1]" → "claimword [^1]" (no space between word and citation)
    # But NOT "[^1][^2]" (consecutive citations handled separately)
    # And NOT "[^1]:" (definition lines)
    content = re.sub(r'([a-zA-Z0-9%)])(\[\^)', r'\1 \2', content)

    # Rule 2: Ensure exactly one space between consecutive citations
    # "[^1][^2]" → "[^1] [^2]"
    # "[^1]  [^2]" → "[^1] [^2]"
    # "[^1] , [^2]" → "[^1] [^2]" (remove comma separators in markdown)
    content = re.sub(r'(\[\^\w+\])\s*,?\s*(\[\^)', r'\1 \2', content)

    # Rule 3: Remove duplicate consecutive citations
    # "[^3] [^3]" → "[^3]"
    # "[^3] [^3] [^3]" → "[^3]"
    def dedup_citations(match):
        citations = re.findall(r'\[\^\w+\]', match.group(0))
        seen = []
        for c in citations:
            if c not in seen:
                seen.append(c)
        return ' '.join(seen)

    # Find runs of consecutive citations and deduplicate
    content = re.sub(r'(\[\^\w+\](?:\s+\[\^\w+\])+)', dedup_citations, content)

    # Rule 4: Citation definitions start at column 0
    # " [^1]: text" → "[^1]: text"
    content = re.sub(r'^[ \t]+(\[\^\w+\]:)', r'\1', content, flags=re.MULTILINE)

    # Rule 5: Exactly one space after colon in definitions
    # "[^1]:text" → "[^1]: text"
    # "[^1]:  text" → "[^1]: text"
    content = re.sub(r'(\[\^\w+\]):[ \t]*', r'\1: ', content)

    # Clean up: no double spaces that we might have introduced
    # But only around citations, not in general text
    content = re.sub(r'(\[\^\w+\])  +', r'\1 ', content)
    content = re.sub(r'  +(\[\^)', r' \1', content)

    return content


def citation_spacing_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation Spacing Agent — Fixes citation spacing in the final draft.

    Reads the final draft, applies mechanical spacing fixes, and writes
    the corrected version back. Also fixes spacing in individual section
    files for consistency.

    Args:
        state: Current memo state

    Returns:
        State updates with messages
    """
    company_name = state["company_name"]

    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("⊘ Citation spacing skipped - no output directory")
        return {"messages": ["Citation spacing skipped - no output directory"]}

    print("\n📐 Fixing citation spacing...")

    fixes_total = 0

    # Fix section files
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        for section_file in sorted(sections_dir.glob("*.md")):
            original = section_file.read_text(encoding="utf-8")
            fixed = fix_citation_spacing(original)
            if fixed != original:
                section_file.write_text(fixed, encoding="utf-8")
                fixes_total += 1
                print(f"  ✓ Fixed: {section_file.name}")

    # Fix final draft
    from ..final_draft import find_final_draft
    final_draft_path = find_final_draft(output_dir)
    if final_draft_path:
        original = final_draft_path.read_text(encoding="utf-8")
        fixed = fix_citation_spacing(original)
        if fixed != original:
            final_draft_path.write_text(fixed, encoding="utf-8")
            fixes_total += 1
            print(f"  ✓ Fixed: {final_draft_path.name}")

    # Fix header.md if exists
    header_file = output_dir / "header.md"
    if header_file.exists():
        original = header_file.read_text(encoding="utf-8")
        fixed = fix_citation_spacing(original)
        if fixed != original:
            header_file.write_text(fixed, encoding="utf-8")
            fixes_total += 1

    if fixes_total == 0:
        print("  ✓ Citation spacing is correct (no changes needed)")
    else:
        print(f"  ✓ Fixed spacing in {fixes_total} file(s)")

    return {
        "messages": [f"Citation spacing: {fixes_total} file(s) fixed"]
    }

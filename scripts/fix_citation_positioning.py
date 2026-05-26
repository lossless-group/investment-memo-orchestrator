#!/usr/bin/env python3
"""
Fix citation positioning per house style:
1. Inline citations belong AFTER the terminal punctuation of the sentence/clause
   (".  [^1]" not " [^1].").
2. If the same citation ID appears multiple times in a single paragraph,
   consolidate to ONE marker at the end of the paragraph.

Operates on prose paragraphs only. Skips: headers, citation definitions,
code blocks, HTML/SVG blocks, list items, tables, horizontal rules,
blockquotes. List items inside acquisition-precedent-style bullets are
NOT processed because they already follow per-bullet citation semantics
the consolidation rule would mangle.

Obsidian compliance: a single space always precedes ` [^X]` markers.

Usage:
    python scripts/fix_citation_positioning.py path/to/file.md [path/to/another.md ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

INLINE_CITATION_RE = re.compile(r'\s*\[\^([a-zA-Z0-9_-]+)\]')


def looks_like_skippable_block(block: str) -> bool:
    """Return True if this block should NOT have its citations rewritten."""
    stripped = block.strip()
    if not stripped:
        return True
    if stripped.startswith('```'):  # code fence
        return True
    if stripped.startswith('<'):  # HTML/SVG
        return True
    if stripped.startswith('|'):  # table
        return True
    if re.match(r'^#{1,6}\s', stripped):  # header
        return True
    if re.match(r'^-{3,}$', stripped):  # horizontal rule
        return True
    if re.match(r'^\[\^[a-zA-Z0-9_-]+\]:\s', stripped):  # citation definition
        return True
    if re.match(r'^>\s', stripped):  # blockquote
        return True
    # List items: each item is its own logical paragraph but may already
    # cite cleanly per-item. Skip rather than risk consolidating across items.
    if re.match(r'^[-*+]\s', stripped) or re.match(r'^\d+\.\s', stripped):
        return True
    return False


def fix_paragraph(paragraph: str) -> str:
    """Rewrite citations in a single prose paragraph per the house-style rules."""
    citations_in_order: list[str] = []
    seen: set[str] = set()

    for match in INLINE_CITATION_RE.finditer(paragraph):
        cid = match.group(1)
        if cid not in seen:
            seen.add(cid)
            citations_in_order.append(cid)

    if not citations_in_order:
        return paragraph

    # Strip every inline citation marker (and its leading whitespace).
    cleaned = INLINE_CITATION_RE.sub('', paragraph)
    # Collapse any double-spaces left by the strip.
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    # Trim trailing whitespace from each line but preserve internal newlines.
    cleaned = re.sub(r'[ \t]+(\n|$)', r'\1', cleaned)
    cleaned = cleaned.rstrip()

    # Append the unique citations after the final character (which should be
    # terminal punctuation for well-formed prose).
    suffix = ' ' + ' '.join(f'[^{cid}]' for cid in citations_in_order)
    return cleaned + suffix


def fix_file(path: Path) -> tuple[int, int]:
    """Rewrite citations in `path`. Returns (paragraphs_changed, citations_moved)."""
    content = path.read_text(encoding='utf-8')
    # Split on blank-line paragraph boundaries while preserving the separators.
    blocks = re.split(r'(\n\s*\n)', content)

    paragraphs_changed = 0
    citations_moved = 0

    out: list[str] = []
    for block in blocks:
        if looks_like_skippable_block(block) or re.fullmatch(r'\s+', block):
            out.append(block)
            continue
        original_citation_count = len(INLINE_CITATION_RE.findall(block))
        rewritten = fix_paragraph(block)
        if rewritten != block:
            paragraphs_changed += 1
            new_count = len(INLINE_CITATION_RE.findall(rewritten))
            citations_moved += original_citation_count
            # `new_count` may be smaller (consolidation), but we count moved as a proxy.
        out.append(rewritten)

    new_content = ''.join(out)
    if new_content != content:
        path.write_text(new_content, encoding='utf-8')
    return paragraphs_changed, citations_moved


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    total_paragraphs = 0
    total_citations = 0
    for raw in argv[1:]:
        path = Path(raw)
        if not path.exists():
            print(f"⚠️  not found: {path}")
            continue
        changed, moved = fix_file(path)
        total_paragraphs += changed
        total_citations += moved
        print(f"  ✓ {path}: {changed} paragraphs rewritten ({moved} inline citations processed)")
    print(f"\n✅ Total: {total_paragraphs} paragraphs rewritten across {len(argv) - 1} files")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

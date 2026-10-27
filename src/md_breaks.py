"""
Section breaks in markdown are `***`, never `---`.

A `---` line outside the opening YAML frontmatter can be read as a frontmatter
delimiter, and a `---` directly under a paragraph is a setext H2 underline: the
whole paragraph above it renders as a heading. Both have reached exported memos.

Every writer that emits a break uses `SECTION_BREAK`. Every reader that looks for
one matches `BREAK_LINE_RE`, which accepts both forms so older artifacts still
parse. `normalize_section_breaks` is the backstop for text an LLM wrote.
"""

from __future__ import annotations

import re

SECTION_BREAK = "***"

# A whole line that is a thematic break, in either spelling.
BREAK_LINE_RE = re.compile(r"^[ \t]{0,3}(?:-{3,}|\*{3,})[ \t]*$")

_DASH_RULE_RE = re.compile(r"^[ \t]{0,3}-{3,}[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def is_break_line(line: str) -> bool:
    return bool(BREAK_LINE_RE.match(line))


def _frontmatter_end(lines: list[str]) -> int:
    """Index just past the closing delimiter of a leading frontmatter block, else 0."""
    if not lines or lines[0].strip() != "---":
        return 0
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return i + 1
    return 0


def normalize_section_breaks(text: str) -> str:
    """
    Rewrite every `---` break as `***`, with a blank line above it.

    Leaves the opening frontmatter and fenced code alone. Table delimiter rows
    contain `|` and never match. The blank line is what keeps a preceding
    paragraph from becoming a setext heading.
    """
    lines = text.split("\n")
    start = _frontmatter_end(lines)
    out = lines[:start]
    fence = None
    for line in lines[start:]:
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
            out.append(line)
            continue
        if fence is None and is_break_line(line):
            if out and out[-1].strip():
                out.append("")
            out.append(SECTION_BREAK if _DASH_RULE_RE.match(line) else line.strip())
            continue
        out.append(line)
    return "\n".join(out)

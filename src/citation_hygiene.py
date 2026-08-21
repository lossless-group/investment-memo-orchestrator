"""
Obsidian-style inline citation hygiene — mechanical, idempotent, no model call.

THE RULES (house spec, not preferences)
---------------------------------------
1. **Exactly one space before an inline marker.** Ported from
   `content-farm/plugin-modules/cite-wide/src/utils/citationSpacing.ts`, which
   documents why this is correctness rather than style: Obsidian only gives a
   footnote its hover-preview and click-to-jump behavior when the marker is
   separated from the preceding text. Glued, it renders as inert literal text.

2. **The marker goes AFTER punctuation.** `Market size is $50B. [^1]` — never
   `$50B [^1].` or `$50B[^1].`

3. **One marker per source per paragraph.** Repeating `[^1]` three times in a
   61-word paragraph is noise, and it is a symptom: if one source genuinely
   backs that much text, the paragraph is too long. Measured on ChromaDB
   v0.0.1 before this existed — 23 of 50 cited paragraphs (46%) repeated a
   citation.

WHAT IT DELIBERATELY DOES NOT TOUCH
-----------------------------------
- **Reference definitions.** `[^abc]: body` — the `(?!:)` guard excludes them.
- **Markdown reference links.** `[text][ref]` is left alone. An earlier
  cite-wide rule matched any `][` boundary and split these, breaking the link.
- **Fenced code blocks.** cite-wide's own docstring flags this as known and
  unfixed; inherited rather than silently diverged from.

ON THE ALLOWLIST TRAP
---------------------
cite-wide's history is instructive: the original spacing rule enumerated which
characters could precede a marker (`[A-Za-z0-9.,:;!?]`) and silently skipped
quotes, parens, dashes, ellipses, `%`, `*`, and every non-ASCII letter —
`café[^abc]` stayed glued. The rule wanted is "any non-whitespace character",
so this matches `\\S` and drops the character class entirely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

# Keys here are wider than cite-wide's `[a-z0-9]+`: memopop uses `[^1]` and
# `[^deck]` alongside hex codes.
KEY = r"[a-zA-Z0-9_-]+"
INLINE = rf"\[\^{KEY}\](?!:)"          # (?!:) excludes reference definitions

_MISSING_SPACE = re.compile(rf"(?<=\S)(?={INLINE})")
_EXTRA_SPACE = re.compile(rf"[ \t]{{2,}}(?={INLINE})")
_MARKER = re.compile(rf"\[\^({KEY})\](?!:)")

# " [^1]." / " [^1] ." -> ". [^1]"  — marker must follow the terminator.
_BEFORE_PUNCT = re.compile(rf"[ \t]*({INLINE})[ \t]*([.,;:!?])")

_REFDEF_LINE = re.compile(rf"^\s*\[\^{KEY}\]:")


@dataclass
class HygieneReport:
    spaced: int = 0
    repunctuated: int = 0
    deduped: int = 0
    paragraphs_touched: int = 0

    @property
    def total(self) -> int:
        return self.spaced + self.repunctuated + self.deduped

    def summary(self) -> str:
        return (f"{self.spaced} spacing, {self.repunctuated} punctuation-order, "
                f"{self.deduped} duplicate marker(s) removed "
                f"across {self.paragraphs_touched} paragraph(s)")


def _fix_punctuation_order(text: str, report: HygieneReport) -> str:
    """Move a marker that landed before its sentence terminator to after it."""
    def repl(m: re.Match) -> str:
        report.repunctuated += 1
        return f"{m.group(2)} {m.group(1)}"
    return _BEFORE_PUNCT.sub(repl, text)


def _fix_spacing(text: str, report: HygieneReport) -> str:
    before = text
    text = _MISSING_SPACE.sub(" ", text)
    if text != before:
        report.spaced += 1
    before = text
    text = _EXTRA_SPACE.sub(" ", text)
    if text != before:
        report.spaced += 1
    return text


def _dedupe_paragraph(para: str, report: HygieneReport) -> str:
    """Keep only the LAST occurrence of each citation key in this paragraph.

    Last rather than first, so the marker sits at the end of the span it
    supports rather than orphaned at the start of it.
    """
    keys = _MARKER.findall(para)
    if len(keys) == len(set(keys)):
        return para

    seen_from_end: set = set()
    keep: List[bool] = []
    for k in reversed(keys):
        keep.append(k not in seen_from_end)
        seen_from_end.add(k)
    keep.reverse()

    idx = -1

    def repl(m: re.Match) -> str:
        nonlocal idx
        idx += 1
        if keep[idx]:
            return m.group(0)
        report.deduped += 1
        return ""          # leading space is cleaned up by the spacing pass

    out = _MARKER.sub(repl, para)
    report.paragraphs_touched += 1
    # Marker removal can leave doubled spaces mid-sentence.
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"[ \t]+([.,;:!?])", r"\1", out)
    return out


def clean(content: str, *, dedupe: bool = True) -> Tuple[str, HygieneReport]:
    """Apply all citation-hygiene rules. Idempotent."""
    report = HygieneReport()
    if not content:
        return content, report

    # Split on blank lines so paragraph scope is real, and never disturb the
    # blank lines themselves.
    chunks = re.split(r"(\n\s*\n)", content)
    out: List[str] = []
    for chunk in chunks:
        if not chunk.strip() or re.fullmatch(r"\n\s*\n", chunk):
            out.append(chunk)
            continue
        # Reference-definition blocks are left entirely alone.
        if all(_REFDEF_LINE.match(l) or not l.strip() for l in chunk.splitlines()):
            out.append(chunk)
            continue

        fixed = chunk
        if dedupe:
            fixed = _dedupe_paragraph(fixed, report)
        fixed = _fix_punctuation_order(fixed, report)
        fixed = _fix_spacing(fixed, report)
        out.append(fixed)

    return "".join(out), report

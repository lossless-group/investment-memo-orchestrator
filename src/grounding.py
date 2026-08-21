"""
Grounding verification — did the model actually read the source it cites?

THE FAILURE THIS EXISTS FOR
---------------------------
Models default to the cheapest path. Given a curated source set and a section to
write, the lazy strategy is not to read the documents at all: answer from
parametric knowledge, attach plausible `[^N]` markers, and move on. The output
is indistinguishable from real work at a glance — the citations point at real,
retrieved, live URLs, so provenance passes, liveness passes, and the numbers are
often roughly true.

The worse version is **fabricated reading**: the model asserts a quote or a
specific figure and attributes it to source N, where that string appears nowhere
in source N. It has invented the evidence, not just the framing.

None of the other defenses catch this:

  - provenance  answers "was this URL retrieved?"          → yes, it was
  - liveness    answers "does the URL resolve?"            → yes
  - attribution answers "is this about the right company?" → often yes
  - fact-verify answers "is this true?"                    → often roughly true

The question none of them ask is: **does the cited document actually contain
this?** That one is cheap to answer, because at synthesis time the fetched text
is already in memory. A quote is either a substring of the source or it is not.

WHAT THIS CHECKS
----------------
Two kinds of evidence, both verbatim-checkable:

  quotes   — any "..." or “...” span attached to a [^N] marker
  figures  — dollar amounts, percentages and large numbers attached to a [^N]

Both are normalized (whitespace, smart quotes, thin spaces) before comparison,
because extraction pipelines mangle those constantly and a false positive here
is expensive — it makes the check untrustworthy and therefore ignored.

WHAT IT DOES NOT CHECK
----------------------
Paraphrase. A model can faithfully summarize a source without reusing any span,
and that is legitimate research writing. This catches invented *evidence*, not
weak synthesis. Unverifiable ≠ false; it means "not mechanically confirmable,"
which is why callers should report rather than delete.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Quoted spans worth checking. Short quotes produce noise ("AI", "the company"),
# so require enough characters to be a real assertion of evidence.
MIN_QUOTE_CHARS = 25

_QUOTE_PATTERNS = [
    r'"([^"\n]{%d,400})"' % MIN_QUOTE_CHARS,
    r'“([^”\n]{%d,400})”' % MIN_QUOTE_CHARS,
]

# Figures specific enough that their absence from the source is meaningful.
_FIGURE_PATTERN = (
    r'(\$\s?[\d,]+(?:\.\d+)?\s*(?:[KMB]|million|billion|trillion)?'
    r'|\b\d{1,3}(?:,\d{3})+\b'
    r'|\b\d+(?:\.\d+)?\s?%)'
)

_MARKER = r'\[\^([a-zA-Z0-9_-]+)\]'


def normalize(text: str) -> str:
    """Fold the differences that extraction introduces but meaning does not."""
    if not text:
        return ""
    t = text.replace("“", '"').replace("”", '"')
    t = t.replace("‘", "'").replace("’", "'")
    t = t.replace("–", "-").replace("—", "-").replace("−", "-")
    t = t.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


def _nearby_markers(sentence: str) -> List[str]:
    return re.findall(_MARKER, sentence)


def sentences(text: str):
    for chunk in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        c = chunk.strip()
        if c:
            yield c


def extract_evidence(content: str) -> List[Dict[str, Any]]:
    """Every quote/figure that a [^N] marker vouches for, with its marker(s)."""
    out: List[Dict[str, Any]] = []
    body = content.partition("### Citations")[0] or content
    for sent in sentences(body):
        markers = _nearby_markers(sent)
        if not markers:
            continue
        for pattern in _QUOTE_PATTERNS:
            for m in re.findall(pattern, sent):
                out.append({"kind": "quote", "value": m.strip(),
                            "markers": markers, "sentence": sent[:300]})
        for m in re.findall(_FIGURE_PATTERN, sent):
            out.append({"kind": "figure", "value": m.strip(),
                        "markers": markers, "sentence": sent[:300]})
    return out


def _figure_variants(fig: str) -> List[str]:
    """A figure can be written many ways; accept the common equivalents."""
    f = normalize(fig)
    variants = {f, f.replace(" ", ""), f.replace(",", "")}
    m = re.match(r"\$?\s?([\d,.]+)\s*(k|m|b|million|billion|trillion)?%?", f)
    if m:
        num = m.group(1).replace(",", "")
        unit = (m.group(2) or "").strip()
        variants.add(num)
        long_short = {"million": "m", "billion": "b", "trillion": "t",
                      "m": "million", "b": "billion", "k": "thousand"}
        if unit in long_short:
            variants.add(f"{num} {long_short[unit]}")
            variants.add(f"{num}{long_short[unit]}")
        variants.add(f"{num} {unit}".strip())
        variants.add(f"{num}{unit}".strip())
    return [v for v in variants if v and len(v) > 1]


def verify(
    content: str,
    source_text_by_marker: Dict[str, str],
    *,
    protected_markers: Tuple[str, ...] = ("deck", "dataroom", "internal"),
) -> Dict[str, Any]:
    """Check each piece of evidence against the text of the source it cites.

    `source_text_by_marker` maps "1" -> the fetched markdown for source [^1].

    A finding is `unsupported` only when EVERY marker on its sentence has known
    source text and none of them contain it. If any cited source's text is
    unavailable, the item is `unverifiable` rather than unsupported — absence of
    text is not evidence of fabrication.
    """
    normalized_sources = {
        k: normalize(v) for k, v in (source_text_by_marker or {}).items() if v
    }
    supported, unsupported, unverifiable = [], [], []

    for item in extract_evidence(content):
        markers = [m for m in item["markers"] if m.lower() not in protected_markers]
        if not markers:
            continue
        known = [m for m in markers if m in normalized_sources]
        if not known:
            unverifiable.append(item)
            continue

        if item["kind"] == "quote":
            needles = [normalize(item["value"])]
        else:
            needles = _figure_variants(item["value"])

        hit_marker = None
        for m in known:
            hay = normalized_sources[m]
            if any(n in hay for n in needles):
                hit_marker = m
                break

        if hit_marker:
            item["found_in"] = hit_marker
            supported.append(item)
        else:
            item["checked"] = known
            unsupported.append(item)

    total = len(supported) + len(unsupported)
    return {
        "supported": supported,
        "unsupported": unsupported,
        "unverifiable": unverifiable,
        "checked": total,
        "grounded_rate": (len(supported) / total) if total else 1.0,
    }


def uncited_sources(content: str, all_markers: List[str],
                    protected: Tuple[str, ...] = ("deck", "dataroom", "internal")) -> List[str]:
    """Markers that were offered to the model but never used — the lazy-skip signal."""
    body = content.partition("### Citations")[0] or content
    used = set(re.findall(_MARKER, body))
    return [m for m in all_markers
            if m not in used and m.lower() not in protected]

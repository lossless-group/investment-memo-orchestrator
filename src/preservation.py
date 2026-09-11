"""What a section said, and whether a rewrite still says it.

Four places in this pipeline rewrite prose that is already written and already
cited: the bookend reviser (`revise_summary_sections`), the two section CLIs
(`improve_section`, `refocus_section`), and the ad-hoc reviser
(`section_reviser`). Every one of them could drop a citation, a figure or a
quoted span and report success, because nothing measured.

That is not a cosmetic failure. The entire argument for this orchestrator is
that a partner can pick the memo up and spot-check it — every number traceable
to the source that vouches for it. A rewrite that quietly deletes `[^4]` breaks
that promise in the way hardest to notice, because the prose reads *better*
afterwards: shorter, cleaner, and unsupported.

ProfileHealth v0.0.4 took its Executive Summary from 2 citations to 0 and its
Closing Assessment from 5 to 0 in a single unattended run, and nothing in the
log said so.

So: measure before, instruct explicitly, verify after, and refuse the result
that lost something. One implementation, used by all four.

**Two regimes, because a memo is not uniformly cited.**

A *body* section carries the argument and the evidence, and every marker in it
is load-bearing: losing one orphans a claim. Those sections are held to full
citation preservation.

The *bookends* — Executive Summary and Closing Assessment — summarise sections
that are already sourced. They read better lightly cited, and a summary studded
with footnotes for figures the body already vouches for is worse prose for no
gain in traceability. So the bookends are NOT required to keep markers.

What they are required to do is keep the numbers honest and never cite
something that does not exist. A summary may drop `[^4]`; it may not quietly
change $5.9M to $6M, and it may not carry a marker that resolves to nothing.
That is `SUMMARY` mode below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set, Tuple

CITATION_RE = re.compile(r"\[\^([a-zA-Z0-9_-]+)\]")

# Wider than src/grounding._FIGURE_PATTERN on purpose.
#
# That one checks a figure against the source text it cites, so it is
# conservative — a false positive there reads as an ungrounded claim. Here the
# job is the opposite: notice a deletion. A false positive costs nothing; a miss
# costs a silently dropped statistic. grounding's pattern does not match a bare
# scaled count, so "5.8M policies", "700 clinics" and "2-5X throughput" were all
# unprotected, and those are the numbers a memo turns on.
FIGURE_RE = re.compile(
    r"""(
          \$\s?[\d,]+(?:\.\d+)?\s*(?:[KMB]\b|million|billion|trillion)?
        | \b\d{1,3}(?:,\d{3})+\b
        | \b\d+(?:\.\d+)?\s?%
        | \b\d+(?:\.\d+)?\s*(?:[KMB]\b|million|billion|trillion)
        | \b\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?\s*[Xx]\b
        | \b\d+(?:\.\d+)?[Xx]\b
    )""",
    re.VERBOSE,
)

_QUOTE_RE = re.compile(r'["“]([^"”\n]{25,400})["”]')

MARKER_RE = re.compile(
    r"<(needs-source|insufficient-data|conflicting-sources|thin-section)\b"
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def body_of(content: str) -> str:
    """Prose only. The reference list is full of dates and page numbers that are
    not claims, and counting them as figures makes every rewrite look lossy."""
    return content.partition("### Citations")[0] or content


@dataclass
class Preservation:
    citations: Set[str] = field(default_factory=set)
    figures: Set[str] = field(default_factory=set)
    quotes: Set[str] = field(default_factory=set)
    markers: Set[str] = field(default_factory=set)
    words: int = 0

    @classmethod
    def of(cls, content: str) -> "Preservation":
        body = body_of(content)
        folded = re.sub(r"\s+", " ", body)
        return cls(
            citations=set(CITATION_RE.findall(content)),
            figures={_normalize(m) for m in FIGURE_RE.findall(body)},
            # Folded first: a quotation that wraps across lines is still a
            # quotation, and in a hard-wrapped memo most of them wrap.
            quotes={_normalize(m) for m in _QUOTE_RE.findall(folded)},
            markers=set(MARKER_RE.findall(content)),
            words=len(content.split()),
        )


@dataclass
class Losses:
    citations: List[str] = field(default_factory=list)
    figures: List[str] = field(default_factory=list)
    quotes: List[str] = field(default_factory=list)
    # Markers the rewrite introduced that resolve to nothing. Not a loss in the
    # literal sense, but the same kind of failure: the reader is shown evidence
    # that is not there.
    invented_citations: List[str] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.citations or self.figures or self.quotes
                    or self.invented_citations)

    def summary(self) -> str:
        bits = []
        if self.citations:
            bits.append(f"{len(self.citations)} citation(s)")
        if self.figures:
            bits.append(f"{len(self.figures)} figure(s)")
        if self.quotes:
            bits.append(f"{len(self.quotes)} quote(s)")
        if self.invented_citations:
            bits.append(f"{len(self.invented_citations)} invented marker(s)")
        return ", ".join(bits) or "nothing"


BODY = "body"        # a section that carries the argument: every marker is load-bearing
SUMMARY = "summary"  # a bookend: light citation is correct, but the numbers must hold


def compare(
    before: Preservation,
    after: Preservation,
    *,
    mode: str = BODY,
    known_citations: Optional[Set[str]] = None,
) -> Losses:
    """What the rewrite dropped. Figures and quotes compare normalised, so a
    revision may re-punctuate a number it keeps; deleting it is the offence.

    In SUMMARY mode dropped markers are not losses — a summary is allowed to be
    clean prose over an already-sourced body. Invented markers still are: a
    footnote that resolves to nothing is worse than no footnote, because it
    looks like evidence.
    """
    dropped_citations = sorted(before.citations - after.citations)
    dropped_quotes = sorted(before.quotes - after.quotes)
    invented: List[str] = []

    if mode == SUMMARY:
        # A summary condenses. Shedding a marker or a direct quotation is what
        # condensing looks like, and requiring either would produce a bookend
        # that is really just the body again.
        dropped_citations = []
        dropped_quotes = []
        if known_citations is not None:
            invented = sorted(after.citations - known_citations)

    return Losses(
        citations=dropped_citations,
        # Figures are the exception in both regimes. A summary may say less; it
        # may not say something different. $5.9M becoming $6M is not concision.
        figures=sorted(before.figures - after.figures),
        quotes=dropped_quotes,
        invented_citations=invented,
    )


def instructions(keep: Preservation, *, mode: str = BODY) -> str:
    """The block that goes into any prompt that rewrites already-cited prose."""
    if not keep.citations and not keep.figures:
        return ""

    lines = ["CITATION AND EVIDENCE DISCIPLINE — THIS WILL BE CHECKED:"]
    if mode == BODY and keep.citations:
        keys = ", ".join(f"[^{c}]" for c in sorted(keep.citations))
        lines += [
            f"- Every one of these {len(keep.citations)} citation markers must still "
            "appear, byte-identical, attached to the claim it supports:",
            f"    {keys}",
            "- Do NOT renumber, rename, merge or 'tidy' a marker. [^deck] stays [^deck].",
            "- If you merge two sentences, carry BOTH markers into the result.",
        ]
    elif mode == SUMMARY:
        lines += [
            "- This is a SUMMARY of sections that are already sourced. It does not need "
            "heavy citation, and reads better without it. Do not footnote a figure "
            "merely because the body footnotes it.",
            "- Cite only where the summary makes a claim the body does not already "
            "carry, or where a single number is doing enough work to want its source "
            "at hand.",
            "- Any marker you do use must already exist in the memo, unchanged. A "
            "footnote that resolves to nothing is worse than no footnote.",
        ]
    if keep.figures:
        shown = sorted(keep.figures)[:40]
        lines += [
            f"- These {len(keep.figures)} figures appeared before and must still appear, "
            "with their values unchanged (rephrasing is fine, deleting or rounding is not):",
            "    " + ", ".join(shown) + ("…" if len(keep.figures) > len(shown) else ""),
        ]
    if keep.markers:
        lines.append(
            "- Leave these unresolved markers exactly where they are: "
            + ", ".join(sorted(keep.markers))
            + ". Resolving one needs a source, not a rewrite."
        )
    return "\n".join(lines)


def correction(previous: str, losses: Losses) -> str:
    """What to say when a draft dropped something — itemised, with the draft.

    "Keep what was correct" is unfollowable without the thing being changed;
    this pipeline has learned that twice already, in the `amend` directive and
    in the codified researcher's grounding re-prompt.
    """
    parts = []
    if losses.citations:
        parts.append(
            "MISSING CITATION MARKERS — re-attach each to the claim it supports:\n"
            + "\n".join(f"  [^{c}]" for c in losses.citations)
        )
    if losses.figures:
        parts.append(
            "MISSING FIGURES — each appeared before and is now gone:\n"
            + "\n".join(f"  {f}" for f in losses.figures)
        )
    if losses.quotes:
        parts.append(
            "MISSING QUOTED SPANS:\n" + "\n".join(f"  {q}" for q in losses.quotes)
        )
    if losses.invented_citations:
        parts.append(
            "MARKERS THAT RESOLVE TO NOTHING — remove them, or use the marker the "
            "memo actually carries for that claim:\n"
            + "\n".join(f"  [^{c}]" for c in losses.invented_citations)
        )
    return (
        "=== YOUR PREVIOUS DRAFT ===\n"
        f"{previous}\n\n"
        "=== WHAT IT LOST ===\n" + "\n\n".join(parts) + "\n\n"
        "Rewrite it again. Keep every improvement you just made, and put back "
        "everything listed above. Return ONLY the revised text."
    )


def guard(
    before_text: str,
    generate: Callable[[int, Optional[str], Optional[Losses]], Optional[str]],
    *,
    max_attempts: int = 2,
    label: str = "revision",
    indent: str = "     ",
    mode: str = BODY,
    known_citations: Optional[Set[str]] = None,
) -> Tuple[Optional[str], List[Losses]]:
    """Run `generate` until it returns prose that lost nothing, or give up.

    `generate(attempt, previous_draft, losses)` returns the next draft, or None
    when the model call itself failed.

    Returns `(accepted_text_or_None, losses_per_attempt)`. Giving up returns
    None rather than raising, because callers differ on what to do about it —
    keep the original, fall back to unpolished research, emit a neutral score.
    Forcing an exception takes that choice away.
    """
    keep = Preservation.of(before_text)
    losses_log: List[Losses] = []
    previous: Optional[str] = None
    last_losses: Optional[Losses] = None

    for attempt in range(1, max_attempts + 1):
        draft = generate(attempt, previous, last_losses)
        if draft is None:
            return None, losses_log

        losses = compare(keep, Preservation.of(draft),
                         mode=mode, known_citations=known_citations)
        losses_log.append(losses)
        if not losses.any:
            return draft, losses_log

        print(f"{indent}⚠️  {label} attempt {attempt} lost {losses.summary()}")
        if attempt < max_attempts:
            print(f"{indent}↺ re-prompting with an itemised list of what it dropped")
        previous, last_losses = draft, losses

    print(f"{indent}❌ {label} still lost {losses_log[-1].summary()}; keeping the original")
    return None, losses_log

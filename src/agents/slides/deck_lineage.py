"""
Deck Lineage

Multiple versions of one deck per round, multiple rounds per company. Time-series
analysis only works if the same logical slide can be recognized across versions,
and only if things that are not versions are kept out of the series.

Three distinctions this module exists to make.

**Version versus fork.** Keystone's MeridianAI SPV deck shares 15 of 16 slides with
the company's own deck — the founder's contact slide is swapped for Keystone's SPV
terms and a Keystone closing slide. It is not v2 of the company deck. Folding it in
would report that MeridianAI "removed their contact slide and added fund terms",
which the company never did. Forks branch off the company axis and are diffed
separately, if at all.

**Sibling versus version.** The 38-page Reading Deck shares *zero* slides with
the 16-page company deck from the same week. Same company, same round, different
document. Two decks in one round are siblings, not successive versions.

**Animation reveals versus slides.** The Reading Deck has consecutive near
duplicates at pages 3/4, 5/6, 11/12, 30/31, and 34–37 — PowerPoint animation
states exported as separate pages. Untreated, one logical slide becomes four
documents and pollutes the corpus and the series alike.

The fingerprinting underneath all three has to be lenient. A first attempt using
exact hashes reported that a deck and its own PDF export shared only 8 of 17
slides; they share all 17, and the differences were line-break placement between
two text extractors. Exact matching fabricates version churn.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Set, Tuple


# =============================================================================
# Naming
# =============================================================================

def _token(value: str) -> str:
    """One CamelCase-ish token, safe for a filename and readable in a listing."""
    cleaned = unicodedata.normalize("NFKD", value or "")
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)
    parts = [p for p in re.split(r"[\s_-]+", cleaned) if p]
    # Preserve intentional internal capitals — "MeridianAI" must not become "Meridianai".
    return "".join(p if any(c.isupper() for c in p[1:]) else p.capitalize() for p in parts)


def deck_slug(
    company: str,
    round_name: str,
    deck_date: Optional[date],
    version: int = 1,
    variant: Optional[str] = None,
) -> str:
    """
    Folder name for one deck, per house convention: ``20240910_MeridianAI_Seed--v1``.

    A firm-authored fork carries its variant as another underscore token so the
    ``--vN`` suffix stays purely about version:
    ``20240926_MeridianAI_Seed_SPV--v1``.
    """
    stamp = deck_date.strftime("%Y%m%d") if deck_date else "00000000"
    parts = [stamp, _token(company), _token(round_name)]
    if variant and variant.lower() not in ("company", "", "none"):
        parts.append(_token(variant))
    return f"{'_'.join(parts)}--v{version}"


def slide_filename(index: int, slide_type: str, total: int) -> str:
    """``03-team.md``, zero-padded to the deck's width so listings sort."""
    width = max(2, len(str(total)))
    return f"{index:0{width}d}-{slide_type.replace('_', '-')}.md"


# =============================================================================
# Fingerprinting
# =============================================================================

# Words too common to distinguish one slide from another.
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "our", "are", "was",
    "will", "can", "has", "have", "not", "but", "all", "its", "their", "them",
    "how", "who", "what", "when", "more", "than", "into", "out", "over",
}


def normalize_slide_text(text: str) -> str:
    """
    Reduce slide text to comparable content.

    Deliberately lossy. Line breaks, bullet glyphs, page numbers, and casing all
    differ between a PPTX and its PDF export while the slide is identical, so all
    of them go. What survives is the words.
    """
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFKD", text)
    cleaned = cleaned.replace("’", "'").replace("‘", "'")
    cleaned = cleaned.replace("“", '"').replace("”", '"')
    cleaned = re.sub(r"[•●▪–—>*·●○◆]", " ", cleaned)
    cleaned = cleaned.lower()
    # Standalone integers are usually slide numbers, which shift between variants.
    cleaned = re.sub(r"\b\d{1,3}\b(?!\s*[%$])", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9%$.\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def content_tokens(text: str) -> List[str]:
    """Meaningful words from a slide, in order, stop words removed."""
    return [w for w in normalize_slide_text(text).split() if len(w) > 2 and w not in _STOP]


def content_hash(text: str) -> str:
    """
    Stable hash over the normalized token *set*.

    Set rather than sequence: reading order differs between extractors for
    multi-column slides even when the content is identical.
    """
    tokens = sorted(set(content_tokens(text)))
    return hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()[:16]


def shingles(text: str, size: int = 3) -> Set[str]:
    """Overlapping n-grams, the unit of similarity comparison."""
    tokens = content_tokens(text)
    if len(tokens) < size:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def similarity(a: str, b: str) -> float:
    """Jaccard overlap of two slides' shingles, 0.0–1.0."""
    sa, sb = shingles(a), shingles(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def title_of(text: str) -> str:
    """
    Best guess at a slide's title: its first substantial line.

    Used as a cheap high-precision match before falling back to similarity —
    two slides with the same title are almost always the same slide.
    """
    for line in (text or "").splitlines():
        stripped = line.strip()
        if len(stripped) > 3 and not stripped.isdigit():
            return normalize_slide_text(stripped)
    return ""


# =============================================================================
# Thresholds
# =============================================================================

# Above this, two slides are the same slide. Set from the observed PDF-vs-PPTX
# case, where genuinely identical slides scored well below an exact match.
SAME_SLIDE = 0.62

# Above this but below SAME_SLIDE, two slides are related — the same slide
# edited between versions, which is exactly what a time series wants to catch.
EDITED_SLIDE = 0.35

# Consecutive slides above this are almost certainly animation reveals of one
# slide rather than two slides that happen to be similar.
REVEAL_SEQUENCE = 0.80


# =============================================================================
# Animation reveals
# =============================================================================

@dataclass
class RevealGroup:
    """
    Consecutive pages that are states of a single logical slide.

    A *reveal* is one slide animated so its content appears in stages, then
    exported to PDF — which writes each stage as its own page. One slide, five
    pages. Presentation software calls these "builds"; that word is avoided here
    because in a codebase it means compilation.
    """

    indices: List[int]                 # 1-based page numbers
    canonical: int                     # the state to treat as the slide itself
    confirmed: bool = True             # False when grouped only by a repeated title

    @property
    def size(self) -> int:
        return len(self.indices)


def detect_reveal_sequences(slide_texts: Sequence[str]) -> List[RevealGroup]:
    """
    Group consecutive pages that are states of one slide.

    Two signals, because text alone is not sufficient and measuring said so.

    **High text overlap** catches reveals that repeat their content while adding
    to it. In the MeridianAI Reading Deck this correctly grouped pages 10–12.

    **A repeated title** catches the harder and more common case: a progressive
    reveal where each frame shows *different* content under the same heading.
    Pages 34–37 of that deck all read "Our Solution | Translating how the brain
    actually computes…" and score as low as 0.056 against each other, because
    almost none of their body text is shared. Similarity alone declared them four
    unrelated slides.

    Title-grouped runs are marked ``confirmed=False``: a repeated heading is
    genuine evidence but not proof, since a deck may legitimately run several
    distinct slides under one section header. The stenographer sees the rendered
    images and makes the final call.

    The last state is canonical — a reveal shows progressively, so only the
    final frame carries the whole slide.
    """
    groups: List[RevealGroup] = []
    titles = [title_of(t) for t in slide_texts]

    current: List[int] = [1]
    current_confirmed = True

    for i in range(1, len(slide_texts)):
        by_text = similarity(slide_texts[i - 1], slide_texts[i]) >= REVEAL_SEQUENCE
        by_title = bool(titles[i]) and titles[i] == titles[i - 1]

        if by_text or by_title:
            current.append(i + 1)
            current_confirmed = current_confirmed and by_text
        else:
            if len(current) > 1:
                groups.append(RevealGroup(
                    indices=current, canonical=current[-1], confirmed=current_confirmed
                ))
            current = [i + 1]
            current_confirmed = True

    if len(current) > 1:
        groups.append(RevealGroup(
            indices=current, canonical=current[-1], confirmed=current_confirmed
        ))
    return groups


def reveal_map(slide_texts: Sequence[str]) -> Dict[int, Tuple[int, int, bool]]:
    """
    Per-page reveal position: ``{page: (position, total, is_canonical, confirmed)}``.

    Pages not part of a reveal are absent, so a caller can write
    ``reveal_sequence: null`` for them.
    """
    mapping: Dict[int, Tuple[int, int, bool, bool]] = {}
    for group in detect_reveal_sequences(slide_texts):
        for position, page in enumerate(group.indices, start=1):
            mapping[page] = (position, group.size, page == group.canonical, group.confirmed)
    return mapping


# =============================================================================
# Deck relationships
# =============================================================================

@dataclass
class SlideMatch:
    """One slide in deck A paired with its counterpart in deck B."""

    index_a: Optional[int]
    index_b: Optional[int]
    score: float
    relation: str          # identical | edited | added | removed
    matched_on: str = "similarity"   # title | similarity


@dataclass
class DeckComparison:
    """How two decks relate."""

    relationship: str      # version | fork | sibling | duplicate
    shared: int
    edited: int
    added: int
    removed: int
    matches: List[SlideMatch] = field(default_factory=list)
    reasoning: str = ""

    @property
    def overlap(self) -> float:
        total = self.shared + self.edited + self.added + self.removed
        return (self.shared + self.edited) / total if total else 0.0


def match_slides(texts_a: Sequence[str], texts_b: Sequence[str]) -> List[SlideMatch]:
    """
    Pair slides between two decks.

    Title equality is tried first because it is cheap and nearly always right;
    similarity is the fallback for retitled or heavily edited slides. Greedy
    rather than optimal — decks are tens of slides, and a globally optimal
    assignment would not change the answer often enough to justify it.
    """
    titles_a = [title_of(t) for t in texts_a]
    titles_b = [title_of(t) for t in texts_b]
    used_b: Set[int] = set()
    matches: List[SlideMatch] = []

    for i, text_a in enumerate(texts_a):
        best_j, best_score, title_hit = None, 0.0, False

        for j, text_b in enumerate(texts_b):
            if j in used_b:
                continue
            if titles_a[i] and titles_a[i] == titles_b[j]:
                # A shared title is strong evidence these are the same *logical*
                # slide, so pair them — but the relation still comes from the
                # content. MeridianAI's "Thank you." slide and Keystone's "Thank you."
                # slide share a title and score 0.00 similarity: same slide in
                # the deck's structure, entirely rewritten. Forcing that to
                # "identical" reported a swapped contact card as unchanged.
                best_j, best_score, title_hit = j, similarity(text_a, text_b), True
                break
            score = similarity(text_a, text_b)
            if score > best_score:
                best_j, best_score = j, score

        if best_j is not None and (best_score >= EDITED_SLIDE or title_hit):
            used_b.add(best_j)
            matches.append(SlideMatch(
                index_a=i + 1,
                index_b=best_j + 1,
                score=round(best_score, 3),
                relation="identical" if best_score >= SAME_SLIDE else "edited",
                matched_on="title" if title_hit else "similarity",
            ))
        else:
            matches.append(SlideMatch(i + 1, None, 0.0, "removed"))

    for j in range(len(texts_b)):
        if j not in used_b:
            matches.append(SlideMatch(None, j + 1, 0.0, "added"))

    return matches


def compare_decks(
    texts_a: Sequence[str],
    texts_b: Sequence[str],
    author_a: str = "company",
    author_b: str = "company",
) -> DeckComparison:
    """
    Classify how deck B relates to deck A.

    Authorship is decisive, not advisory. A deck the firm assembled from the
    company's slides is a fork however much it overlaps — the edits are the
    firm's, and attributing them to the company would misread the series.
    """
    matches = match_slides(texts_a, texts_b)
    shared = sum(1 for m in matches if m.relation == "identical")
    edited = sum(1 for m in matches if m.relation == "edited")
    added = sum(1 for m in matches if m.relation == "added")
    removed = sum(1 for m in matches if m.relation == "removed")

    comparison = DeckComparison(
        relationship="sibling", shared=shared, edited=edited,
        added=added, removed=removed, matches=matches,
    )
    overlap = comparison.overlap

    if author_a != author_b:
        comparison.relationship = "fork"
        comparison.reasoning = (
            f"authored by different parties ({author_a} vs {author_b}) — "
            f"{shared} shared slides are borrowed, not revised"
        )
    elif overlap >= 0.95 and not added and not removed:
        comparison.relationship = "duplicate"
        comparison.reasoning = "same slides in the same order; one is an export of the other"
    elif overlap >= 0.45:
        comparison.relationship = "version"
        comparison.reasoning = (
            f"{shared} identical and {edited} edited slides against "
            f"{added} added and {removed} removed"
        )
    else:
        comparison.relationship = "sibling"
        comparison.reasoning = (
            f"only {overlap:.0%} overlap — a different document for the same "
            f"company, not a revision"
        )

    return comparison


def lineage_id(company: str, round_name: str, slide_title: str, slide_type: str) -> str:
    """
    Stable identifier for a logical slide across every version it appears in.

    The time-series key. Built from the title where there is one, since a team
    slide keeps its heading across revisions far more reliably than it keeps its
    position; slide type is the fallback for untitled slides.
    """
    basis = title_of(slide_title) or slide_type
    digest = hashlib.sha256(
        f"{_token(company)}|{_token(round_name)}|{basis}".encode("utf-8")
    ).hexdigest()[:10]
    return f"{_token(company).lower()}-{slide_type.replace('_', '-')}-{digest}"

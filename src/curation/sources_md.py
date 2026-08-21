"""
Loader for the per-deal `inputs/Sources.md` codified-source workflow.

A deal's `Sources.md` is a markdown file with YAML frontmatter that
encodes the analyst's hand-curated source list. When present and
`mode: codified`, the research agent skips broad search entirely and
uses only these URLs as the per-memo corpus.

This matches the team's convention of frontmatter-for-machines, body-for-
humans — the structured source list lives in frontmatter (parseable by
the loader), and the analyst's notes about how the list was built /
what was rejected / what's still missing live in the markdown body (the
"institutional memory" layer that prevents re-adding the same junk on
the next iteration).

Schema (frontmatter):

    mode: codified                       # "codified" locks the run; absent or "search" = legacy broad search
    deal: ChromaDB
    firm: alpha-partners
    date_curated_initial: 2026-05-22
    date_curated_current: 2026-05-22
    at_semantic_version: 0.0.0.1
    curated_by:
      - Michael Staton
    augmented_with: Claude Code (Opus 4.7)
    sources:
      - url: https://www.trychroma.com/blog/series-a
        sections: [funding-terms, team]
        rank: 1
        sensitivity: citable_externally
        note: "Series A announcement; primary"
      - url: https://github.com/chroma-core/chroma
        sections: [technology-product, traction-milestones]
        rank: 1
        sensitivity: citable_externally
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SourceEntry:
    """A single curated source from `Sources.md`."""
    url: str
    sections: List[str] = field(default_factory=list)    # section tags this source supports
    rank: int = 1                                         # 1 = primary; higher = lower priority
    sensitivity: str = "citable_externally"               # or "internal_only"
    note: str = ""                                        # analyst's free-form note

    # --- Bibliographic fields -------------------------------------------
    # Previously dropped by this loader, which forced `tools/curate_sources.py`
    # to bypass it and parse raw frontmatter to keep them. `title` in
    # particular is load-bearing: `validation.url_recovery.attempt_url_recovery`
    # returns None without one, so the curation UI's "re-search for the real
    # source" action is dead unless the loader round-trips it.
    title: str = ""
    publisher: str = ""
    published_date: str = ""

    # Analyst-staged local copy, relative to the deal dir or absolute. Set when
    # a source is approved but unreachable to bots (McKinsey, Reuters, NYT all
    # refuse automated fetches). The codified researcher reads this instead of
    # the URL, so downloading the document actually gets it into the memo.
    local_path: str = ""

    # --- Analyst verdict -------------------------------------------------
    # Promoted from a YAML *comment* (`# verdict: ...`) to a real field.
    # Comments are discarded by `yaml.safe_load`, so the previous encoding
    # forced a lossy regex-recovery pass on every read. Approve/deny is the
    # curation surface's primary output; it cannot live in a lossy channel.
    #
    # Vocabulary: "" (unreviewed) | "approved" | "rejected" | plus the
    # machine verdicts written by the validation ladder (soft-404, paywall,
    # timeout, 403, unapproved, ...). Only "approved" grants membership.
    verdict: str = ""
    verdict_reason: str = ""                              # why denied — training data for tuning


@dataclass
class SourcesMd:
    """Parsed `inputs/Sources.md` for a single deal."""
    mode: str = "search"
    deal: str = ""
    firm: str = ""
    sources: List[SourceEntry] = field(default_factory=list)
    body: str = ""                                        # analyst notes (markdown)
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)
    source_path: Optional[Path] = None


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Split a markdown file's YAML frontmatter from its body.

    Returns `({}, original_content)` if the file has no frontmatter or
    the frontmatter is malformed — so callers can fall back gracefully.
    """
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    try:
        import yaml
        metadata = yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}, content
    if not isinstance(metadata, dict):
        return {}, content
    body = parts[2].lstrip("\n")
    return metadata, body


def load_sources_md(deal_inputs_dir: Path) -> Optional[SourcesMd]:
    """
    Load `inputs/Sources.md` from a deal directory.

    Returns None when:
      - The file is absent (legacy broad-search pipeline applies).
      - The file exists but lacks frontmatter or fails to parse.

    Never raises — failures are silent and fall through to legacy behavior.
    """
    if not deal_inputs_dir or not deal_inputs_dir.exists():
        return None

    path = deal_inputs_dir / "Sources.md"
    if not path.exists():
        return None

    try:
        content = path.read_text()
    except Exception:
        return None

    metadata, body = parse_frontmatter(content)
    if not metadata:
        return None

    # A stray `---` inside the source list silently truncates the frontmatter:
    # everything past it parses as prose body, so those sources vanish from the
    # loader, the approval surface, and the membership gate — while still
    # sitting in the file, which makes the loss invisible from every direction.
    #
    # ImmuneCo carried exactly this from 2026-07-14 (commit bbe294d) until
    # 2026-08-08: 93 sources on disk, 80 visible, and nothing anywhere said so.
    # A cheap shape check on the body turns a silent 13-source hole into a
    # message. Warn rather than raise — a partially readable list still beats
    # refusing to load one.
    if body and re.search(r"^- url:\s*\S", body, re.M):
        stranded = len(re.findall(r"^- url:\s*\S", body, re.M))
        print(
            f"  ⚠️  {path}: {stranded} source(s) appear AFTER the closing "
            f"frontmatter fence and are being ignored. A stray '---' inside "
            f"the source list truncates it — splice them back above the fence."
        )

    source_entries: List[SourceEntry] = []
    for raw in (metadata.get("sources") or []):
        if not isinstance(raw, dict):
            continue
        url = (raw.get("url") or "").strip()
        if not url:
            continue
        sections = raw.get("sections") or []
        if isinstance(sections, str):
            sections = [sections]
        try:
            rank = int(raw.get("rank", 1))
        except (TypeError, ValueError):
            rank = 1
        source_entries.append(SourceEntry(
            url=url,
            sections=[str(s) for s in sections],
            rank=rank,
            sensitivity=str(raw.get("sensitivity", "citable_externally")),
            note=str(raw.get("note", "")),
            title=str(raw.get("title") or ""),
            publisher=str(raw.get("publisher") or ""),
            published_date=str(raw.get("published_date") or ""),
            local_path=str(raw.get("local_path") or ""),
            verdict=str(raw.get("verdict") or "").strip().lower(),
            verdict_reason=str(raw.get("verdict_reason") or ""),
        ))

    return SourcesMd(
        mode=str(metadata.get("mode", "search")).strip().lower(),
        deal=str(metadata.get("deal", "")),
        firm=str(metadata.get("firm", "")),
        sources=source_entries,
        body=body,
        raw_frontmatter=metadata,
        source_path=path,
    )


def is_codified(sources_md: Optional[SourcesMd]) -> bool:
    """Whether `Sources.md` instructs the pipeline to use codified mode."""
    return sources_md is not None and sources_md.mode == "codified"


# Verdicts that revoke membership. Everything else — including the empty
# string — leaves a source approved; see `approved_urls` for why.
_REJECTED_VERDICTS = frozenset({"rejected", "denied", "excluded"})


def is_approved_entry(entry: SourceEntry) -> bool:
    """Whether a single entry is a member of the approved set.

    Presence in a codified `Sources.md` *is* the approval — that is what
    "codified" has always meant. `verdict` is therefore a **revocation**
    field, not a grant: an entry is approved unless explicitly rejected.

    This is deliberate and load-bearing for backward compatibility. Every
    `Sources.md` written before the verdict field existed carries no
    verdict at all; requiring `verdict == "approved"` to grant membership
    would empty the approved set for all of them and cause the membership
    gate to strip every citation from every existing codified deal.
    """
    return entry.verdict not in _REJECTED_VERDICTS


def is_explicitly_approved(entry: SourceEntry) -> bool:
    """Whether a human has AFFIRMATIVELY approved this source.

    Deliberately stricter than `is_approved_entry`, and the two answer different
    questions:

      is_approved_entry      — may the memo CITE this? Deny-based: approved
                               unless explicitly rejected. Permissive on purpose,
                               because legacy Sources.md files carry no verdicts
                               at all and requiring one would empty the set.

      is_explicitly_approved — may we spend money and WRITE THIS DOWN PERMANENTLY?
                               Requires a real "approved". Used to gate full
                               content fetch, extraction, and registration in the
                               shared SurrealDB system of record.

    The asymmetry is the point. Citing an unreviewed source is recoverable — the
    analyst sees it in the draft. Pulling full content for a candidate that may be
    rejected wastes a fetch, and writing it into a shared registry puts junk in
    the system of record permanently, where every other client and deal sees it.
    The skill's two-tier rule says it directly: don't fetch full content for a
    candidate that may be rejected.
    """
    return (entry.verdict or "").strip().lower() == "approved"


def approved_urls(sources_md: Optional[SourcesMd]) -> set:
    """The canonicalized URL set a codified run is allowed to cite.

    Returns an empty set when `sources_md` is None or not in codified mode
    — callers MUST check `is_codified()` first and skip enforcement
    entirely rather than treating an empty set as "nothing is allowed".

    URLs are canonicalized with `best_sources.canonical_url` (the same
    normalization Pass A of the cross-run curation uses), so membership
    survives trailing slashes, `www.`, tracking params, and http/https
    drift. Comparisons against this set must canonicalize the candidate
    the same way — use `is_approved_url`.
    """
    if not sources_md or not sources_md.sources:
        return set()
    from .best_sources import canonical_url
    return {
        canonical_url(e.url)
        for e in sources_md.sources
        if e.url and is_approved_entry(e)
    }


def is_approved_url(url: str, approved: set) -> bool:
    """Whether `url` is a member of a set produced by `approved_urls`."""
    if not url:
        return False
    from .best_sources import canonical_url
    return canonical_url(url) in approved


def load_deal_sources(state) -> Tuple[Optional[SourcesMd], set]:
    """Resolve a deal's `Sources.md` and approved-URL set from workflow state.

    The single entry point every agent should use to ask "is this deal
    codified, and what may it cite?" — so a new agent opts *in* to the
    constraint by using the standard helper rather than having to know
    the `io/<firm>/deals/<deal>/inputs` convention.

    Returns `(sources_md, approved)`. `approved` is empty whenever the
    deal is not codified; callers must treat that as "enforcement does
    not apply", never as "nothing is allowed". Never raises.
    """
    try:
        from ..agents.codified_section_researcher import find_deal_inputs_dir
        inputs_dir = find_deal_inputs_dir(state)
        if not inputs_dir:
            return None, set()
        sources_md = load_sources_md(inputs_dir)
        if not is_codified(sources_md):
            return sources_md, set()
        return sources_md, approved_urls(sources_md)
    except Exception:
        return None, set()


def deal_is_codified(state) -> bool:
    """Whether this deal's run is constrained to an approved source set."""
    sources_md, _ = load_deal_sources(state)
    return is_codified(sources_md)


def sources_for_section(
    sources_md: SourcesMd,
    section_name: str,
    section_number: Optional[int] = None,
) -> List[SourceEntry]:
    """
    Filter the curated source list to entries tagged for a given section.

    Tag matching is forgiving — a source tagged `team` matches a section
    named `"Team"`, `"04-team"`, or `"04 Team"`. The analyst can use
    short slugs in Sources.md without worrying about exact section-file
    naming.

    Args:
        sources_md: Parsed Sources.md.
        section_name: Outline section name (e.g., "Team", "Market Context").
        section_number: Optional 1-based section number for extra-strict
            matching against tags like "01-overview".

    Returns:
        Matching entries, sorted by rank (primary sources first).
    """
    if not sources_md or not sources_md.sources:
        return []

    target = _normalize_tag(section_name)
    number_strs = []
    if section_number is not None:
        number_strs = [f"{section_number:02d}", str(section_number)]

    matches: List[SourceEntry] = []
    for entry in sources_md.sources:
        for tag in entry.sections:
            tag_norm = _normalize_tag(tag)
            if (
                tag_norm == target
                or tag_norm in target
                or target in tag_norm
                or any(n in tag_norm for n in number_strs)
            ):
                matches.append(entry)
                break

    return sorted(matches, key=lambda e: e.rank)


def _normalize_tag(s: str) -> str:
    """
    Lowercase, strip, replace whitespace and underscores with hyphens —
    so 'Market Context', 'market-context', and 'market_context' all
    match the same tag.
    """
    return (s or "").strip().lower().replace(" ", "-").replace("_", "-")

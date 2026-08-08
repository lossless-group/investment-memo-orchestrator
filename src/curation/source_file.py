"""Write and read one source's own markdown file.

Implements the canonical schema in
`corpora-builder/context-v/blueprints/Source-File-Schema-Reconciliation.md`,
which reconciles this repo's `agent-skills/source-with-extracts-md` with
augment-it's `services/content-ingest/src/corpus.ts`. Adoption is
copy-from, knots-style — there is no shared package across a Python
orchestrator, a Node service, and a Tauri app.

Two files, two jobs, do not confuse them:

  inputs/Sources.md            the per-deal LIST — what may be cited
  inputs/sources/<file>.md     ONE source — its content and extracts

The list is the contract the membership gate enforces. These files are
where the content we already paid to fetch actually lands. Before this
module existed the approval surface fetched a page via Jina, rendered it,
and discarded it.

Three rules carried from the blueprint, each load-bearing:

1. **`fetched_at` is not `published_at`.** When we pulled it is not when
   it was written. Conflating them makes staleness unanswerable.
2. **Two-tier fetch.** Cheap excerpt while a source is a `candidate`;
   full body only on promote. Never pay for content that may be rejected.
3. **`verdict` is a person, `machine_verdict` is a machine.** Reachability
   is not approval — the category error the membership gate exists to fix.

Extracts (quotes, stats, claims) are punctuation-heavy strings full of
`: " $ % [ ] |` — every character that breaks YAML. They live in the BODY
as Lossless Flavored Markdown directives, never as frontmatter values.
This module preserves an existing `# Extracts` section verbatim on
rewrite and never generates one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .best_sources import canonical_url

# Length of the cheap preview kept on a candidate. Arbitrary and untested
# against how analysts actually triage — open question 4 in the blueprint.
EXCERPT_CHARS = 200

# Frontmatter key order. Fixed, not alphabetical, so a git diff of a
# curated file shows what changed rather than a reshuffle.
FIELD_ORDER = [
    "url", "normalized_url", "title", "publisher", "authors",
    "fetched_at", "published_at",
    "status", "content_pulled", "excerpt", "description",
    "origin", "origin_detail",
    "domains", "sections", "tags", "rank", "sensitivity",
    "verdict", "verdict_reason", "machine_verdict", "confidence", "note",
    "binary_asset",
    "extra_metadata",
]

VALID_STATUS = ("candidate", "promoted", "archived", "rejected")

_EXTRACTS_RE = re.compile(r"^#\s+Extracts\s*$", re.M)


@dataclass
class SourceFile:
    """One source's file: frontmatter scalars plus a markdown body."""

    url: str
    normalized_url: str = ""
    title: str = ""
    publisher: str = ""
    authors: List[str] = field(default_factory=list)

    fetched_at: str = ""          # when WE pulled it
    published_at: str = ""        # when the source was authored

    status: str = "candidate"
    content_pulled: bool = False
    excerpt: str = ""
    description: str = ""

    origin: str = ""              # searxng | perplexity | analyst-paste | pack | inbox
    origin_detail: Dict[str, Any] = field(default_factory=dict)

    domains: List[str] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    rank: int = 1
    sensitivity: str = "citable_externally"

    verdict: str = ""             # analyst only: approved | rejected
    verdict_reason: str = ""
    machine_verdict: str = ""     # validator reachability — never an approval
    confidence: Optional[int] = None
    note: str = ""

    binary_asset: Dict[str, Any] = field(default_factory=dict)
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    body: str = ""                # fetched content and/or an # Extracts section
    source_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.url and not self.normalized_url:
            self.normalized_url = canonical_url(self.url)


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------

def slugify(text: str, *, max_len: int = 72) -> str:
    """Filesystem-safe lower-kebab slug.

    Filenames cannot hold `/ : ? " * |`, so the slug is lossy by design;
    the verbatim title always survives in frontmatter. Truncation lands
    on a word boundary when one is near the limit, because a slug cut
    mid-word reads like corruption.
    """
    s = (text or "").strip().lower()
    s = re.sub(r"https?://", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > max_len:
        cut = s[:max_len]
        s = cut.rsplit("-", 1)[0] if "-" in cut[max_len // 2:] else cut
    return s or "untitled"


def source_filename(
    title: str,
    url: str = "",
    *,
    when: Optional[str] = None,
    suffix: Optional[int] = None,
) -> str:
    """`<YYYY-MM-DD>_<slug>.md`, falling back to the URL when untitled.

    `when` is an ISO date or datetime; defaults to today. `suffix`
    produces the collision form `<date>_<slug>_<n>.md`.
    """
    date_part = (when or datetime.now(timezone.utc).date().isoformat())[:10]
    slug = slugify(title or url)
    stem = f"{date_part}_{slug}"
    if suffix:
        stem = f"{stem}_{suffix}"
    return f"{stem}.md"


def sources_dir(deal_inputs_dir: Path) -> Path:
    """Where a deal's per-source files live: `inputs/sources/`.

    The blueprint fixes the filename grammar and the frontmatter as the
    contract, and leaves placement to each app because the directory tree
    encodes that app's tenancy model. memopop is deal-scoped, so these sit
    beside the `Sources.md` list they belong to.
    """
    return Path(deal_inputs_dir) / "sources"


def resolve_path(deal_inputs_dir: Path, sf: SourceFile) -> Path:
    """Path for a source, reusing the existing file when the URL matches.

    Collision handling distinguishes two cases that look identical on
    disk: the SAME source being rewritten (reuse the path — a promote
    must not orphan the candidate file it supersedes) and a DIFFERENT
    source that slugs to the same name (take the next `_n`).
    """
    directory = sources_dir(deal_inputs_dir)
    base = source_filename(sf.title, sf.url, when=sf.fetched_at or None)
    candidate = directory / base
    if not candidate.exists():
        return candidate

    target = canonical_url(sf.url)
    n = 0
    while candidate.exists():
        existing = read_source_file(candidate)
        if existing and canonical_url(existing.url) == target:
            return candidate          # same source — rewrite in place
        n += 1
        candidate = directory / source_filename(
            sf.title, sf.url, when=sf.fetched_at or None, suffix=n
        )
    return candidate


# --------------------------------------------------------------------------
# Serialization
# --------------------------------------------------------------------------

def _is_empty(value: Any) -> bool:
    """Whether a field should be omitted. `False` and `0` are NOT empty."""
    if value is None:
        return True
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return True
    return False


def to_frontmatter(sf: SourceFile) -> Dict[str, Any]:
    """The frontmatter mapping, in canonical order, empties dropped.

    `url`, `status`, and `content_pulled` are always written even when
    falsy: `url` is the one required field, and the two lifecycle fields
    are orthogonal axes a reader must never have to infer.
    """
    raw = {
        "url": sf.url,
        "normalized_url": sf.normalized_url,
        "title": sf.title,
        "publisher": sf.publisher,
        "authors": sf.authors,
        "fetched_at": sf.fetched_at,
        "published_at": sf.published_at,
        "status": sf.status,
        "content_pulled": sf.content_pulled,
        "excerpt": sf.excerpt,
        "description": sf.description,
        "origin": sf.origin,
        "origin_detail": sf.origin_detail,
        "domains": sf.domains,
        "sections": sf.sections,
        "tags": sf.tags,
        "rank": sf.rank,
        "sensitivity": sf.sensitivity,
        "verdict": sf.verdict,
        "verdict_reason": sf.verdict_reason,
        "machine_verdict": sf.machine_verdict,
        "confidence": sf.confidence,
        "note": sf.note,
        "binary_asset": sf.binary_asset,
        "extra_metadata": sf.extra_metadata,
    }
    always = {"url", "status", "content_pulled"}
    return {
        k: raw[k] for k in FIELD_ORDER
        if k in always or not _is_empty(raw.get(k))
    }


def render(sf: SourceFile) -> str:
    """Render the complete file: frontmatter, then body verbatim."""
    import yaml

    block = yaml.safe_dump(
        to_frontmatter(sf),
        sort_keys=False, allow_unicode=True, default_flow_style=False, width=4096,
    )
    body = (sf.body or "").strip()
    return f"---\n{block}---\n\n{body}\n" if body else f"---\n{block}---\n"


# --------------------------------------------------------------------------
# Read / write
# --------------------------------------------------------------------------

def read_source_file(path: Path) -> Optional[SourceFile]:
    """Parse a source file. Returns None rather than raising."""
    from .sources_md import parse_frontmatter

    path = Path(path)
    if not path.exists():
        return None
    try:
        meta, body = parse_frontmatter(path.read_text())
    except Exception:
        return None
    if not meta or not meta.get("url"):
        return None

    def _list(key: str) -> List[str]:
        v = meta.get(key) or []
        return [str(x) for x in (v if isinstance(v, list) else [v])]

    def _dict(key: str) -> Dict[str, Any]:
        v = meta.get(key)
        return dict(v) if isinstance(v, dict) else {}

    try:
        rank = int(meta.get("rank", 1))
    except (TypeError, ValueError):
        rank = 1
    confidence = meta.get("confidence")
    try:
        confidence = int(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    return SourceFile(
        url=str(meta["url"]),
        normalized_url=str(meta.get("normalized_url") or ""),
        title=str(meta.get("title") or ""),
        publisher=str(meta.get("publisher") or ""),
        authors=_list("authors"),
        fetched_at=str(meta.get("fetched_at") or ""),
        published_at=str(meta.get("published_at") or ""),
        status=str(meta.get("status") or "candidate"),
        content_pulled=bool(meta.get("content_pulled", False)),
        excerpt=str(meta.get("excerpt") or ""),
        description=str(meta.get("description") or ""),
        origin=str(meta.get("origin") or ""),
        origin_detail=_dict("origin_detail"),
        domains=_list("domains"),
        sections=_list("sections"),
        tags=_list("tags"),
        rank=rank,
        sensitivity=str(meta.get("sensitivity") or "citable_externally"),
        verdict=str(meta.get("verdict") or ""),
        verdict_reason=str(meta.get("verdict_reason") or ""),
        machine_verdict=str(meta.get("machine_verdict") or ""),
        confidence=confidence,
        note=str(meta.get("note") or ""),
        binary_asset=_dict("binary_asset"),
        extra_metadata=_dict("extra_metadata"),
        body=body,
        source_path=path,
    )


def write_source_file(deal_inputs_dir: Path, sf: SourceFile) -> Path:
    """Write a source file, preserving any hand-authored extracts.

    A rewrite must never destroy the analyst's `# Extracts` section — it
    is the one part of the file no machine can regenerate. When the
    incoming body carries no extracts and the file on disk has some, the
    existing section is carried forward beneath the new content.
    """
    directory = sources_dir(deal_inputs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = resolve_path(deal_inputs_dir, sf)

    existing = read_source_file(path)
    if existing and existing.body and not _EXTRACTS_RE.search(sf.body or ""):
        m = _EXTRACTS_RE.search(existing.body)
        if m:
            sf.body = f"{(sf.body or '').strip()}\n\n{existing.body[m.start():].strip()}".strip()

    path.write_text(render(sf))
    sf.source_path = path
    return path


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def from_entry(entry: Any, *, origin: str = "", origin_detail: Optional[Dict] = None) -> SourceFile:
    """Build a SourceFile from a `Sources.md` SourceEntry.

    Carries the entry's verdict across the person/machine split: only
    `approved` and `rejected` are analyst judgments; anything else the
    validator wrote (`HTTP 200 (body verified)`, `timeout`, `403`) is a
    reachability result and lands in `machine_verdict`.
    """
    analyst = (entry.verdict or "").strip().lower()
    is_analyst = analyst in ("approved", "rejected", "denied", "excluded")
    return SourceFile(
        url=entry.url,
        title=getattr(entry, "title", "") or "",
        publisher=getattr(entry, "publisher", "") or "",
        published_at=getattr(entry, "published_date", "") or "",
        sections=list(entry.sections or []),
        rank=entry.rank,
        sensitivity=entry.sensitivity,
        note=entry.note or "",
        verdict=("rejected" if is_analyst and analyst != "approved" else analyst) if is_analyst else "",
        verdict_reason=getattr(entry, "verdict_reason", "") or "",
        machine_verdict="" if is_analyst else (entry.verdict or ""),
        origin=origin,
        origin_detail=dict(origin_detail or {}),
    )


_JINA_KEYS = ("Title", "URL Source", "Published Time", "Markdown Content")
_JINA_LINE = re.compile(
    rf"^({'|'.join(re.escape(k) for k in _JINA_KEYS)}):[ \t]*(.*)$", re.M
)


def parse_jina_preamble(markdown: str) -> tuple[Dict[str, str], str]:
    """Split Jina Reader's header block from the article body.

    Jina prefixes fetched content with:

        Title: …
        URL Source: …
        Published Time: 2023-06-12T20:54:51Z
        Markdown Content:
        <the actual article>

    That block is metadata, not content. Left in place it poisons the
    excerpt (which then reads "Title: … URL Source: … Markdown Content:")
    and, worse, strands `Published Time` — the one authoritative signal
    for `published_at`, without which staleness is unanswerable.

    augment-it's `content-ingest/src/corpus.ts` lifts the same field out
    of the same preamble (`liftPublishedAt`); this is the Python side of
    that convergence.

    Returns `(headers, body)`. When no preamble is present the input is
    returned unchanged — the httpx fallback path synthesizes a similar
    header, and a plain markdown file has none at all.
    """
    text = markdown or ""
    marker = "Markdown Content:"
    idx = text.find(marker)
    # Only treat it as a preamble if the marker is near the top; the
    # phrase could legitimately appear deep inside an article.
    if idx == -1 or idx > 600:
        return {}, text

    head, body = text[:idx], text[idx + len(marker):]
    headers = {k: v.strip() for k, v in _JINA_LINE.findall(head) if v.strip()}
    return headers, body.lstrip("\n")


def _iso_date(value: str) -> str:
    """Normalize a timestamp to a bare ISO date, or pass it through."""
    v = (value or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
    return m.group(1) if m else v


def apply_fetch(sf: SourceFile, fetched: Optional[Dict[str, Any]], *, full: bool) -> SourceFile:
    """Fold a `fetch_url_markdown` result into a SourceFile.

    `full=False` keeps only the cheap excerpt (the candidate tier);
    `full=True` stores the body and flips `content_pulled`. A failed
    fetch is a no-op rather than an error — a source with no content is
    still a valid, citable source.
    """
    if not fetched:
        return sf

    headers, markdown = parse_jina_preamble((fetched.get("markdown") or "").strip())
    markdown = markdown.strip()

    if not sf.title:
        sf.title = str(fetched.get("title") or headers.get("Title") or "")
    # The source's own authored date, distinct from when we pulled it.
    if not sf.published_at and headers.get("Published Time"):
        sf.published_at = _iso_date(headers["Published Time"])
    # Excerpt comes from the BODY, never the preamble.
    if not sf.excerpt and markdown:
        sf.excerpt = " ".join(markdown.split())[:EXCERPT_CHARS]

    sf.fetched_at = sf.fetched_at or _now()
    if fetched.get("via"):
        sf.extra_metadata.setdefault("fetched_via", fetched["via"])
    if full and markdown:
        sf.body = markdown
        sf.content_pulled = True
    return sf


def promote(sf: SourceFile) -> SourceFile:
    """Mark a source approved and promoted.

    Deliberately does NOT set `content_pulled` — that says what is on
    disk, and promoting is a decision, not a download. The two axes stay
    independent so a promoted-but-unfetched source is representable.
    """
    sf.status = "promoted"
    sf.verdict = "approved"
    sf.verdict_reason = ""
    return sf


def reject(sf: SourceFile, reason: str = "") -> SourceFile:
    """Mark a source rejected, keeping it on disk.

    Rejections are institutional memory: the next session should see what
    was already turned down and why rather than re-reviewing it.
    """
    sf.status = "rejected"
    sf.verdict = "rejected"
    sf.verdict_reason = reason
    return sf

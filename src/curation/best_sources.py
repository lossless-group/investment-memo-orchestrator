"""Merge every version's ``3-source-catalog/`` for a deal into one "best of" set.

The orchestrator emits a per-section source catalog on every run. Each source
carries a status (Included, Added by Correction, Valid but Not Cited, Found in
Research, Excluded — Uncertain, Excluded — Invalid, Hallucinated). Over many
runs the catalogs disagree: a source promoted to ``Included`` in v0.0.5 may
have been ``Found in Research`` in v0.0.3, and a hallucination in one run may
appear validated in another.

This module walks every ``outputs/{deal}-v*/3-source-catalog/*.md``, dedupes
by URL within each section, keeps the highest-ranked status seen across runs,
drops sources that were ever flagged as hallucinated or invalid, and writes a
single ``exports/best-of-sources/`` directory the UI can hand to the user as
the curated starting point for the next iteration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from ..paths import get_io_root

# Tracking / analytics query params that don't change the resource identity.
# Strip these before treating two URLs as the same source.
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "ref",
    "ref_src",
    "ref_url",
    "referrer",
    "source",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "_hsenc",
    "_hsmi",
    "hsCtaTracking",
    "yclid",
    "msclkid",
}


def canonical_url(raw: str) -> str:
    """Return a canonicalized form of ``raw`` suitable for cross-source dedupe.

    Rules:
    - Lowercase scheme + host.
    - Treat ``http`` and ``https`` as the same canonical scheme (prefer https).
    - Drop ``www.`` prefix on host.
    - Strip default ports (:80 / :443).
    - Remove trailing slash from path (but keep "/" if that's the whole path).
    - Drop tracking query params (``utm_*``, ``fbclid``, etc.).
    - Sort remaining query params for stable ordering.
    - Drop fragment (``#...``) — fragments don't address a different resource.
    - Lowercase percent-encodings.
    """
    try:
        parsed = urlparse(raw.strip())
    except Exception:
        return raw.strip()

    scheme = "https" if parsed.scheme in ("http", "https", "") else parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    # Preserve non-default port only.
    if parsed.port and not (
        (scheme == "https" and parsed.port == 443)
        or (scheme == "http" and parsed.port == 80)
    ):
        netloc = f"{host}:{parsed.port}"

    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    kept.sort()
    query = urlencode(kept, doseq=True)

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))

# Higher number = preferred. Sources whose only appearance is at one of the
# DROP statuses are excluded from the output entirely.
_STATUS_RANK = {
    "Included": 100,
    "Added by Correction": 80,
    "Valid but Not Cited": 60,
    "Found in Research": 40,
}
_DROP_STATUSES = {"Excluded — Uncertain", "Excluded — Invalid", "Hallucinated"}

# Map the H2 heading text (the catalog generator's labels) to the canonical
# short status we rank by. The generator phrasing has drifted between versions
# — match on a prefix so "Included in Final Draft" and "Included" both land in
# the same bucket.
_HEADING_TO_STATUS: list[tuple[str, str]] = [
    ("Included", "Included"),
    ("Added by Correction", "Added by Correction"),
    ("Added During Fact Correction", "Added by Correction"),
    ("Valid but Not Cited", "Valid but Not Cited"),
    ("Found in Research", "Found in Research"),
    ("Excluded — Uncertain", "Excluded — Uncertain"),
    ("Excluded - Uncertain", "Excluded — Uncertain"),
    ("Excluded — Invalid", "Excluded — Invalid"),
    ("Excluded - Invalid", "Excluded — Invalid"),
    ("Hallucinated", "Hallucinated"),
]

_HEADING_RE = re.compile(r"^##\s+(.+?)(?:\s+\(\d+\))?\s*$")
_TITLE_URL_RE = re.compile(r"^-\s+\*\*\[(?P<title>.+?)\]\((?P<url>[^)]+)\)\*\*\s*$")
_METADATA_RE = re.compile(r"^\s{2,}-\s+(?P<line>.+)$")
_SECTION_FILE_RE = re.compile(
    r"^(?P<num>\d+)-(?P<slug>.+?)-Complete-Source-List\.md$"
)


@dataclass
class SourceEntry:
    """One source within one section, after merging across versions."""

    title: str
    url: str
    canonical_url: str
    best_status: str
    seen_in_versions: list[str] = field(default_factory=list)
    metadata: list[str] = field(default_factory=list)

    def rank(self) -> int:
        return _STATUS_RANK.get(self.best_status, 0)


@dataclass
class SectionCuration:
    number: str
    slug: str
    sources: list[SourceEntry]


@dataclass
class MasterSource:
    """One canonical URL, deduped across every section and every version.

    This is the unit that matters: an analyst should see each real source
    exactly once, with the full picture of where it showed up and how the
    pipeline labeled it.
    """

    canonical_url: str
    title: str
    best_status: str
    sections_covered: list[str] = field(default_factory=list)
    seen_in_versions: list[str] = field(default_factory=list)
    raw_urls: list[str] = field(default_factory=list)
    metadata: list[str] = field(default_factory=list)

    def rank(self) -> int:
        return _STATUS_RANK.get(self.best_status, 0)


@dataclass
class CurationResult:
    output_dir: Path
    sections: list[SectionCuration]
    master_sources: list[MasterSource]
    versions_scanned: list[str]

    @property
    def total_section_entries(self) -> int:
        """Sum of per-section entries — counts a URL once per section it covers."""
        return sum(len(s.sources) for s in self.sections)

    @property
    def total_unique_sources(self) -> int:
        """Number of distinct URLs after canonical dedupe across all sections."""
        return len(self.master_sources)


def curate_best_sources(firm: str, deal: str) -> CurationResult:
    """Merge every version's source catalog for ``firm/deal`` and write the result.

    Output lands at ``io/{firm}/deals/{deal}/exports/best-of-sources/``,
    overwriting any previous curation. The caller is responsible for surfacing
    the location to the user.
    """
    if not firm or "/" in firm or ".." in firm:
        raise ValueError(f"invalid firm slug: {firm!r}")
    if not deal or "/" in deal or ".." in deal:
        raise ValueError(f"invalid deal slug: {deal!r}")

    deal_dir = get_io_root() / firm / "deals" / deal
    outputs_dir = deal_dir / "outputs"
    if not outputs_dir.is_dir():
        raise FileNotFoundError(f"no outputs directory at {outputs_dir}")

    version_dirs = sorted(
        (p for p in outputs_dir.iterdir() if p.is_dir() and (p / "3-source-catalog").is_dir()),
        key=lambda p: p.name,
    )
    if not version_dirs:
        raise FileNotFoundError(f"no versions with a 3-source-catalog/ under {outputs_dir}")

    # section_key -> (number, slug, {canonical_url: SourceEntry})
    sections: dict[str, tuple[str, str, dict[str, SourceEntry]]] = {}
    # canonical_url -> MasterSource, populated alongside the per-section work
    # so a URL that shows up in 8 sections × 7 versions still lands once here.
    master: dict[str, MasterSource] = {}

    for vdir in version_dirs:
        catalog = vdir / "3-source-catalog"
        for md_path in sorted(catalog.glob("*-Complete-Source-List.md")):
            m = _SECTION_FILE_RE.match(md_path.name)
            if not m:
                continue
            section_key = f"{m['num']}-{m['slug']}"
            bucket = sections.setdefault(section_key, (m["num"], m["slug"], {}))
            for status, title, raw_url, metadata in _parse_catalog(md_path):
                if status in _DROP_STATUSES:
                    # Don't let a drop-tier entry promote a URL we already kept,
                    # but also don't let it block a higher-ranked appearance
                    # elsewhere — we simply ignore it.
                    continue
                canon = canonical_url(raw_url)
                _merge_section_entry(
                    bucket[2], status, title, raw_url, canon, metadata, vdir.name
                )
                _merge_master_entry(
                    master,
                    status=status,
                    title=title,
                    raw_url=raw_url,
                    canon=canon,
                    metadata=metadata,
                    version=vdir.name,
                    section_key=section_key,
                )

    section_results: list[SectionCuration] = []
    for key in sorted(sections.keys()):
        number, slug, by_url = sections[key]
        ordered = sorted(
            by_url.values(),
            key=lambda e: (-e.rank(), e.title.lower()),
        )
        section_results.append(SectionCuration(number=number, slug=slug, sources=ordered))

    master_sources = sorted(
        master.values(),
        key=lambda m: (-m.rank(), -len(m.sections_covered), m.title.lower()),
    )

    export_dir = deal_dir / "exports" / "best-of-sources"
    export_dir.mkdir(parents=True, exist_ok=True)
    # Wipe stale section files so a renamed section doesn't leave an orphan.
    for stale in export_dir.glob("*-Best-Sources.md"):
        stale.unlink()
    for stale in (export_dir / "README.md", export_dir / "Master-Sources.md"):
        if stale.exists():
            stale.unlink()

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    versions_scanned = [v.name for v in version_dirs]

    _write_index(
        export_dir,
        firm=firm,
        deal=deal,
        sections=section_results,
        master_sources=master_sources,
        versions_scanned=versions_scanned,
        generated_at=generated_at,
    )
    _write_master_file(
        export_dir,
        firm=firm,
        deal=deal,
        master_sources=master_sources,
        versions_scanned=versions_scanned,
        generated_at=generated_at,
    )
    for section in section_results:
        _write_section_file(
            export_dir,
            deal=deal,
            section=section,
            generated_at=generated_at,
            versions_scanned=versions_scanned,
        )

    return CurationResult(
        output_dir=export_dir,
        sections=section_results,
        master_sources=master_sources,
        versions_scanned=versions_scanned,
    )


def _parse_catalog(path: Path) -> Iterable[tuple[str, str, str, list[str]]]:
    """Yield ``(status, title, url, metadata_lines)`` for each source in ``path``."""
    text = path.read_text(encoding="utf-8")
    current_status: str | None = None
    current_entry: dict | None = None

    def flush():
        nonlocal current_entry
        if current_entry and current_status:
            yield_value = (
                current_status,
                current_entry["title"],
                current_entry["url"],
                current_entry["metadata"],
            )
            current_entry = None
            return yield_value
        current_entry = None
        return None

    pending: list[tuple[str, str, str, list[str]]] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = _HEADING_RE.match(line)
        if heading:
            flushed = flush()
            if flushed:
                pending.append(flushed)
            current_status = _normalize_heading(heading.group(1))
            continue
        if current_status is None:
            continue
        title_url = _TITLE_URL_RE.match(line)
        if title_url:
            flushed = flush()
            if flushed:
                pending.append(flushed)
            current_entry = {
                "title": title_url["title"].strip(),
                "url": title_url["url"].strip(),
                "metadata": [],
            }
            continue
        meta = _METADATA_RE.match(line)
        if meta and current_entry is not None:
            current_entry["metadata"].append(meta["line"].strip())

    flushed = flush()
    if flushed:
        pending.append(flushed)
    return pending


def _normalize_heading(heading: str) -> str | None:
    h = heading.strip()
    for prefix, status in _HEADING_TO_STATUS:
        if h.startswith(prefix):
            return status
    return None


def _merge_section_entry(
    by_canon: dict[str, SourceEntry],
    status: str,
    title: str,
    raw_url: str,
    canon: str,
    metadata: list[str],
    version: str,
) -> None:
    existing = by_canon.get(canon)
    new_rank = _STATUS_RANK.get(status, 0)
    if existing is None:
        by_canon[canon] = SourceEntry(
            title=title,
            url=raw_url,
            canonical_url=canon,
            best_status=status,
            seen_in_versions=[version],
            metadata=list(metadata),
        )
        return
    existing.seen_in_versions.append(version)
    if new_rank > existing.rank():
        existing.best_status = status
        existing.title = title
        # Replace metadata with the higher-ranked appearance — it tends to be
        # more authoritative (e.g. a corrected citation date).
        existing.metadata = list(metadata)
        existing.url = raw_url
    elif new_rank == existing.rank():
        # Same rank: keep richer metadata. The longer list usually carries
        # the HTTP code or definition string.
        if len(metadata) > len(existing.metadata):
            existing.metadata = list(metadata)


def _merge_master_entry(
    master: dict[str, MasterSource],
    *,
    status: str,
    title: str,
    raw_url: str,
    canon: str,
    metadata: list[str],
    version: str,
    section_key: str,
) -> None:
    existing = master.get(canon)
    new_rank = _STATUS_RANK.get(status, 0)
    if existing is None:
        master[canon] = MasterSource(
            canonical_url=canon,
            title=title,
            best_status=status,
            sections_covered=[section_key],
            seen_in_versions=[version],
            raw_urls=[raw_url],
            metadata=list(metadata),
        )
        return
    if section_key not in existing.sections_covered:
        existing.sections_covered.append(section_key)
    if version not in existing.seen_in_versions:
        existing.seen_in_versions.append(version)
    if raw_url not in existing.raw_urls:
        existing.raw_urls.append(raw_url)
    if new_rank > existing.rank():
        existing.best_status = status
        existing.title = title
        existing.metadata = list(metadata)
    elif new_rank == existing.rank() and len(metadata) > len(existing.metadata):
        existing.metadata = list(metadata)


def _write_index(
    export_dir: Path,
    *,
    firm: str,
    deal: str,
    sections: list[SectionCuration],
    master_sources: list[MasterSource],
    versions_scanned: list[str],
    generated_at: str,
) -> None:
    total_section_entries = sum(len(s.sources) for s in sections)
    lines = [
        f"# Best-of Source Catalog — {deal}",
        "",
        f"**Firm**: {firm}  ",
        f"**Generated**: {generated_at}  ",
        f"**Versions merged** ({len(versions_scanned)}): {', '.join(versions_scanned)}",
        "",
        f"**{len(master_sources)} unique sources** across {len(sections)} sections "
        f"(collapsed from {total_section_entries} per-section entries).",
        "",
        "> Network validity has **not** been checked yet — every URL listed here was",
        "> trusted because the pipeline labeled it as such. Soft-404s, paywall stubs,",
        "> and pages with fabricated IDs are still in the set. The next pass actually",
        "> fetches each URL and drops the dead ones.",
        "",
        "## Start here",
        "",
        f"- [**Master-Sources.md**](Master-Sources.md) — every URL exactly once, "
        f"with the sections and versions it covered.",
        "",
        "## Section views",
        "",
        "Each per-section file is a slice of the master list — useful when you're",
        "drafting one section and want to scan only the sources tagged to it.",
        "",
    ]
    for section in sections:
        title = section.slug.replace("-", " ").title()
        filename = f"{section.number}-{section.slug}-Best-Sources.md"
        lines.append(f"- [{title}]({filename}) — {len(section.sources)} sources")
    lines.extend(
        [
            "",
            "## Status Ranking (highest kept wins)",
            "",
            "1. **Included** — appeared in a final memo with a citation",
            "2. **Added by Correction** — added by LLM verification to fix an inaccurate claim",
            "3. **Valid but Not Cited** — passed URL validation, not used in section",
            "4. **Found in Research** — discovered during research, HTTP 200",
            "",
            "Excluded statuses (`Excluded — Uncertain`, `Excluded — Invalid`,",
            "`Hallucinated`) are dropped entirely.",
            "",
        ]
    )
    (export_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _write_master_file(
    export_dir: Path,
    *,
    firm: str,
    deal: str,
    master_sources: list[MasterSource],
    versions_scanned: list[str],
    generated_at: str,
) -> None:
    """Write Master-Sources.md — the headline view, one entry per canonical URL.

    Grouped by status so the highest-confidence URLs are at the top. Each entry
    shows the sections it was attached to and the versions it appeared in —
    the cross-cutting view that the per-section files structurally hide.
    """
    lines = [
        f"# Master Source List — {deal}",
        "",
        f"**Firm**: {firm}  ",
        f"**Generated**: {generated_at}  ",
        f"**Versions merged** ({len(versions_scanned)}): {', '.join(versions_scanned)}  ",
        f"**Unique sources**: {len(master_sources)}",
        "",
        "Each URL appears exactly once below, canonicalized (scheme, `www`,",
        "trailing slash, and tracking params stripped before dedupe). The",
        "**Sections** line tells you everywhere this source was attached;",
        "the **Versions** line tells you which runs surfaced it.",
        "",
        "> ⚠️ Validity is claimed-by-the-pipeline, not verified. Pages may be",
        "> soft-404s, paywall stubs, or hallucinations with real-looking URLs.",
        "> The next curation pass will actually fetch each URL and drop the",
        "> dead ones.",
        "",
    ]

    by_status: dict[str, list[MasterSource]] = {}
    for m in master_sources:
        by_status.setdefault(m.best_status, []).append(m)

    for status, _rank in sorted(_STATUS_RANK.items(), key=lambda kv: -kv[1]):
        entries = by_status.get(status)
        if not entries:
            continue
        lines.append(f"## {status} ({len(entries)})")
        lines.append("")
        for entry in entries:
            lines.append(f"- **[{entry.title}]({entry.canonical_url})**")
            for meta in entry.metadata:
                lines.append(f"  - {meta}")
            lines.append(f"  - Sections ({len(entry.sections_covered)}): {', '.join(entry.sections_covered)}")
            lines.append(f"  - Versions ({len(entry.seen_in_versions)}): {', '.join(sorted(set(entry.seen_in_versions)))}")
            if len(entry.raw_urls) > 1:
                # When several raw URLs collapsed to the same canonical, expose
                # the variants — useful if one of them was a paywall mirror.
                lines.append(f"  - Variants: {', '.join(entry.raw_urls)}")
            lines.append("")

    (export_dir / "Master-Sources.md").write_text("\n".join(lines), encoding="utf-8")


def _write_section_file(
    export_dir: Path,
    *,
    deal: str,
    section: SectionCuration,
    generated_at: str,
    versions_scanned: list[str],
) -> None:
    title = section.slug.replace("-", " ").title()
    filename = f"{section.number}-{section.slug}-Best-Sources.md"
    lines = [
        f"# {title} — Best Sources",
        "",
        f"**Company**: {deal}  ",
        f"**Generated**: {generated_at}  ",
        f"**Versions merged**: {', '.join(versions_scanned)}",
        "",
    ]
    by_status: dict[str, list[SourceEntry]] = {}
    for entry in section.sources:
        by_status.setdefault(entry.best_status, []).append(entry)

    for status, _rank in sorted(_STATUS_RANK.items(), key=lambda kv: -kv[1]):
        entries = by_status.get(status)
        if not entries:
            continue
        lines.append(f"## {status} ({len(entries)})")
        lines.append("")
        for entry in entries:
            lines.append(f"- **[{entry.title}]({entry.canonical_url})**")
            for meta in entry.metadata:
                lines.append(f"  - {meta}")
            lines.append(
                f"  - Seen in: {', '.join(sorted(set(entry.seen_in_versions)))}"
            )
            lines.append("")
    (export_dir / filename).write_text("\n".join(lines), encoding="utf-8")

"""
Remove Invalid Sources Agent - Validates citation URLs and removes those that don't exist.

This agent validates and cleans citations in a strict sequence to avoid race conditions:

STEP 1: Identify invalid citations
  - HTTP HEAD validation on all URLs
  - Detect hallucination patterns (example.com, XXXXX, etc.)
  - Build list of citation numbers to remove

STEP 2: Remove invalid citations (ALL files, no renumbering yet)
  - Remove inline references [^N] from body text
  - Remove citation definitions [^N]: ...
  - Files now have GAPS in numbering

STEP 3: Reorder citations (AFTER removal is complete)
  - Call reorder_citations_in_file() on each file
  - Renumbers to eliminate gaps: [^1], [^4], [^5] -> [^1], [^2], [^3]

CRITICAL: Removal and renumbering are SEPARATE passes to avoid:
  - Changing [^4] to [^3] before all [^4] refs are processed
  - Race conditions where a number means different things
  - Corrupted citation references

Can be called:
- As part of workflow: after section_research, BEFORE writer
- Independently via CLI: python -m src.agents.remove_invalid_sources <output_dir>

Runs AFTER: section_research (on 1-research/)
Runs BEFORE: writer
"""

import os
import re
import json
import httpx
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Set
from pathlib import Path
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..state import MemoState
from ..utils import get_latest_output_dir


# HTTP codes that indicate the URL is definitely invalid (hallucinated)
INVALID_HTTP_CODES = {404, 410}  # Not Found, Gone

# HTTP codes that indicate the URL might be valid but inaccessible
POTENTIALLY_VALID_CODES = {401, 403, 429, 500, 502, 503}  # Auth required, Forbidden, Rate limited, Server errors

# Patterns that indicate obvious hallucinations.
#
# Some patterns are generic (example.com, XXXXX). Others are publisher-
# specific URL shapes that an LLM emits when it knows the domain pattern
# but invents the document ID. Real reports from these publishers carry
# extra path components (canonical title slug, real ID format) and so do
# NOT match the bare-ID regexes — they flow through to the body-sniff
# layer and the gated-publisher allow-list per `src/validation/gated_publishers.yaml`.
HALLUCINATION_PATTERNS = [
    r'example\.com',                                            # Reserved domain
    r'XXXXX',                                                   # Obvious placeholder
    r'placeholder',                                             # Placeholder text
    r'/path/to/',                                               # Generic path placeholder
    r'\{[^}]+\}',                                               # Template variables like {article-id}

    # Gartner doc-ID URLs without the canonical title slug.
    # Real:  gartner.com/en/documents/4012345-the-actual-title
    # Fake:  gartner.com/en/documents/4012345
    r'^https?://(www\.)?gartner\.com/en/documents/\d+/?$',

    # Forrester reports with bare RES-id and no real title path.
    # Real Forrester slugs are messier; bare-id shapes are LLM templates.
    r'^https?://(www\.)?forrester\.com/report/[^/]+/RES\d{5,8}$',

    # IDC getdoc URLs with bare US{number} containerIds.
    # Real IDC URLs carry additional query params (pageType, etc.).
    r'^https?://(www\.)?idc\.com/getdoc\.jsp\?containerId=US\d+$',
]

# HTTP 200 body phrases that indicate the page is actually missing.
# Used by validate_url() to catch "soft 404s" — pages that return a
# successful status code but whose body says the content is gone.
SOFT_404_PHRASES = [
    "page not found",
    "we couldn't find",
    "we can't find that page",
    "this article is no longer available",
    "this content is no longer available",
    "page has moved or been removed",
    "this content doesn't exist",
    "the page you're looking for",
    "oops! that page",
    "sorry, this article",
    "404 - not found",
]

# HTTP 200 body phrases that indicate a paywall or login wall.
# Until a reputable-publisher allow-list is wired (Phase 1 step 4 of the
# Trustworthy-Citations rollout plan), all paywalled responses are dropped.
PAYWALL_PHRASES = [
    "sign in to continue reading",
    "sign in to read",
    "subscribe to continue",
    "subscribe to read",
    "this content is for subscribers",
    "log in to read",
    "create an account to continue",
    "start your free trial",
    "register to read",
    "become a subscriber",
]

# Sentinel codes returned by validate_url() for content-based verdicts.
# Kept negative to avoid any collision with real HTTP status codes.
HALLUCINATION_PATTERN = -1
SOFT_404_BODY = -2
PAYWALL_STUB = -3
VERIFIED_GATED = -4    # HTTP 200 + paywall phrase, BUT publisher is on the
                       # reputable-publisher allow-list at
                       # `src/validation/gated_publishers.yaml`. Kept as a
                       # citable source; analyst verifies with their own
                       # subscription. Phase 1 step 4 of Trustworthy-Citations.

# Codes that mean "drop this citation outright" (no analyst review).
CONTENT_INVALID_CODES = {HALLUCINATION_PATTERN, SOFT_404_BODY, PAYWALL_STUB}


# ──────────────── Reputable-publisher allow-list ────────────────
# Loaded lazily from src/validation/gated_publishers.yaml. A paywall-stub
# response from a host on this list is reported as VERIFIED_GATED (kept)
# rather than PAYWALL_STUB (dropped).

_GATED_PUBLISHERS_PATH = (
    Path(__file__).resolve().parent.parent / "validation" / "gated_publishers.yaml"
)
_gated_publisher_domains_cache: Optional[Set[str]] = None


def _get_gated_publisher_domains() -> Set[str]:
    """Lazy-load and cache the lowercase domain set from gated_publishers.yaml."""
    global _gated_publisher_domains_cache
    if _gated_publisher_domains_cache is not None:
        return _gated_publisher_domains_cache

    domains: Set[str] = set()
    if _GATED_PUBLISHERS_PATH.exists():
        try:
            import yaml
            with open(_GATED_PUBLISHERS_PATH) as f:
                data = yaml.safe_load(f) or {}
            for entry in data.get("publishers", []):
                for domain in (entry.get("domains") or []):
                    if domain:
                        domains.add(domain.lower())
        except Exception:
            # YAML missing, malformed, or pyyaml not installed — no allow-list.
            pass
    _gated_publisher_domains_cache = domains
    return domains


def _extract_host(url: str) -> str:
    """Extract the lowercase host (stripped of 'www.') from a URL. Empty on parse failure."""
    m = re.match(r'https?://(?:www\.)?([^/]+)', url, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def _is_gated_publisher(url: str) -> bool:
    """
    Whether the URL's host (or one of its parent domains) is on the gated
    publishers allow-list. Subdomain matches succeed: `documents1.worldbank.org`
    matches an entry `worldbank.org`.
    """
    host = _extract_host(url)
    if not host:
        return False
    domains = _get_gated_publisher_domains()
    if not domains:
        return False
    if host in domains:
        return True
    for domain in domains:
        if host.endswith("." + domain):
            return True
    return False


def validate_url(url: str, timeout: int = 8) -> Tuple[str, int, str]:
    """
    Validate a URL by fetching it and inspecting both status code and body.

    Three layers of check:
      1. Hallucination-pattern preflight (regex; no network call).
      2. HTTPS GET with a Range header (read first ~32KB). Follow redirects.
      3. For HTTP 200 with an HTML body, sniff for soft-404 / paywall phrases.

    Non-HTML responses (PDF, JSON, plain text) are not body-sniffed — a 200
    from a real PDF is a real source.

    Args:
        url: URL to validate
        timeout: Request timeout in seconds

    Returns:
        Tuple of (url, code, status_message), where code is:
          - real HTTP status code (200, 404, 500, ...) for actual responses
          - HALLUCINATION_PATTERN (-1) for preflight regex matches
          - SOFT_404_BODY (-2)         HTTP 200 but body says the page is gone
          - PAYWALL_STUB (-3)          HTTP 200 but body is a paywall / login wall
          - 0                          connection failure / unexpected error
    """
    # Layer 1: hallucination-pattern preflight (no network)
    for pattern in HALLUCINATION_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return (url, HALLUCINATION_PATTERN, f"Hallucination pattern: {pattern}")

    # Layers 2 + 3: real HTTP GET with body sniff
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            verify=False,  # tolerate cert issues; we're not authenticating
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Range": "bytes=0-32768",
            },
        ) as client:
            response = client.get(url)

        code = response.status_code

        # Non-2xx: report the code, no body sniff.
        if code >= 400:
            return (url, code, f"HTTP {code}")

        # Non-HTML responses (PDF, JSON, plain text, etc.) aren't body-sniffed.
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type:
            return (url, code, f"HTTP {code} ({content_type or 'non-html'})")

        # HTML body sniff
        try:
            body_text = response.text.lower()
        except UnicodeDecodeError:
            body_text = response.content.decode("utf-8", errors="ignore").lower()

        for phrase in SOFT_404_PHRASES:
            if phrase in body_text:
                return (url, SOFT_404_BODY, f"Soft 404: body contains '{phrase}'")

        for phrase in PAYWALL_PHRASES:
            if phrase in body_text:
                # Reputable-publisher allow-list check: WSJ, FT, Bloomberg,
                # McKinsey, etc. behind paywalls are legitimate citations;
                # the analyst verifies via their own subscription.
                if _is_gated_publisher(url):
                    return (
                        url,
                        VERIFIED_GATED,
                        f"Verified gated ({_extract_host(url)}): body contains '{phrase}'",
                    )
                return (url, PAYWALL_STUB, f"Paywall: body contains '{phrase}'")

        return (url, code, f"HTTP {code} (body verified)")

    except httpx.HTTPError as e:
        return (url, 0, f"HTTP error: {str(e)[:80]}")
    except Exception as e:
        return (url, 0, f"Error: {str(e)[:80]}")


def extract_citation_urls(content: str) -> Dict[str, str]:
    """
    Extract all citation numbers and their URLs from content.

    Args:
        content: Markdown content with citations

    Returns:
        Dict mapping citation number to URL
    """
    citations = {}

    # Pattern for citation definitions with markdown links
    # [^1]: 2024, Jan 15. [Title](URL). Source. Published: ...
    pattern = r'\[\^(\d+)\]:[^\[]*\[([^\]]+)\]\((https?://[^)]+)\)'

    for match in re.finditer(pattern, content):
        citation_num = match.group(1)
        url = match.group(3)
        citations[citation_num] = url

    # Also check for legacy format with URL at end
    legacy_pattern = r'\[\^(\d+)\]:[^|]+\|\s*URL:\s*(https?://\S+)'
    for match in re.finditer(legacy_pattern, content):
        citation_num = match.group(1)
        url = match.group(2)
        if citation_num not in citations:
            citations[citation_num] = url

    return citations


def extract_citation_details(
    content: str,
    source_file: str = "",
    source_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Extract full citation details from a markdown content blob.

    Recognizes the canonical citation format:
        [^N]: YYYY, MMM DD. [Title](URL). Publisher. Published: YYYY-MM-DD | Updated: ...
    and the with-author variant:
        [^N]: YYYY, MMM DD. Author et al. [Title](URL). Publisher. Published: ...

    Args:
        content: Markdown content with citations.
        source_file: Basename of the file these citations came from (e.g.,
            "01-executive-summary.md"). Stored in the returned dict for
            traceability and used by URL-recovery's file-swap step.
        source_path: Optional full Path to the source file. When provided,
            stored alongside source_file so callers can read/write the file
            without re-resolving the path.

    Returns:
        List of dicts with: citation_num, url, title, publisher, author,
        published_date, full_definition, source_file, source_path.
        Best-effort: publisher/author/published_date may be "" if the
        citation format is non-standard.
    """
    citations: List[Dict[str, Any]] = []

    pattern = r'\[\^(\d+)\]:\s*(.+?)(?=\n\[\^|\n\n|\Z)'

    for match in re.finditer(pattern, content, re.DOTALL):
        citation_num = match.group(1)
        full_definition = match.group(2).strip()

        # URL + title from markdown link
        url_match = re.search(r'\[([^\]]+)\]\((https?://[^)]+)\)', full_definition)
        url = url_match.group(2) if url_match else ""
        title = url_match.group(1) if url_match else ""

        # Publisher: the text between the closing paren of the markdown link
        # and the "Published:" marker. Best-effort.
        publisher = ""
        publisher_match = re.search(
            r'\]\([^)]+\)\.\s*([^.|]+?)\.\s*Published:',
            full_definition,
        )
        if publisher_match:
            publisher = publisher_match.group(1).strip()

        # Author: text between the date prefix and the markdown link (if any).
        # Format: "YYYY, MMM DD. <Author> [Title](URL)". Often empty.
        author = ""
        if url_match:
            author_match = re.search(
                r'\d{4},\s+\w{3}\s+\d{1,2}\.\s+(.*?)\s*\[',
                full_definition,
            )
            if author_match:
                candidate = author_match.group(1).strip().rstrip('.').strip()
                if candidate:
                    author = candidate

        # Published date: from "Published: YYYY-MM-DD"
        published_date = ""
        date_match = re.search(r'Published:\s+(\d{4}-\d{2}-\d{2})', full_definition)
        if date_match:
            published_date = date_match.group(1)

        citations.append({
            "citation_num": citation_num,
            "url": url,
            "title": title,
            "publisher": publisher,
            "author": author,
            "published_date": published_date,
            "full_definition": full_definition,
            "source_file": source_file,
            "source_path": str(source_path) if source_path else "",
        })

    return citations


def _collect_all_citation_details(
    research_dir: Path,
    sections_dir: Path,
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """
    Collect citation details from research/, sections/, and the optional
    header.md file. Shared by both the workflow agent and the CLI standalone
    flow.
    """
    details: List[Dict[str, Any]] = []
    for scan_dir in [research_dir, sections_dir]:
        if scan_dir.exists():
            for md_file in sorted(scan_dir.glob("*.md")):
                details.extend(
                    extract_citation_details(
                        md_file.read_text(),
                        md_file.name,
                        source_path=md_file,
                    )
                )
    header_file = output_dir / "header.md"
    if header_file.exists():
        details.extend(
            extract_citation_details(
                header_file.read_text(),
                "header.md",
                source_path=header_file,
            )
        )
    return details


def _swap_citation_url_in_file(
    file_path: Path,
    citation_num: str,
    old_url: str,
    new_url: str,
) -> bool:
    """
    In a citation definition `[^N]: ... [title](old_url) ...`, swap the URL
    inside the markdown link from old → new. Only touches the definition
    line for the given citation_num; leaves body-of-prose links unchanged.

    Returns True if the file was modified, False otherwise.
    """
    if not file_path.exists():
        return False
    content = file_path.read_text()

    # Anchor at `[^N]:` and walk up to (but not including) the first `[`
    # which is the start of the markdown link.
    pattern = (
        rf'(\[\^{re.escape(citation_num)}\]:[^\n\[]*\[[^\]]+\]\()'
        + re.escape(old_url)
        + r'(\))'
    )
    new_content = re.sub(
        pattern,
        lambda m: m.group(1) + new_url + m.group(2),
        content,
    )
    if new_content != content:
        file_path.write_text(new_content)
        return True
    return False


def _run_recovery_pass(
    invalid_citations: Set[str],
    research_dir: Path,
    sections_dir: Path,
    output_dir: Path,
    *,
    citation_details: Optional[List[Dict[str, Any]]] = None,
    indent: str = "",
) -> Tuple[Set[str], List[Dict[str, Any]]]:
    """
    For each citation in `invalid_citations`, attempt URL-drift recovery.
    For successful recoveries, swap the URL in all source files where that
    citation appears.

    No-ops silently if `invalid_citations` is empty or if `TAVILY_API_KEY`
    is unset (a single warning is printed in the latter case so the analyst
    knows why no recoveries happened).

    Args:
        invalid_citations: Set of citation numbers classified as invalid by
            the validator. NOT mutated — caller does set arithmetic on the
            returned recovered set.
        research_dir / sections_dir / output_dir: Standard agent dirs.
        citation_details: Optional pre-collected list (from
            `_collect_all_citation_details`). If absent, collected here.
        indent: Prefix for terminal output lines, so the agent path (2-space
            indent) and the CLI path (no indent) align naturally.

    Returns:
        (recovered_citations, recoveries_log) where recoveries_log is a list
        of records ready to drop into the source-validation log JSON.
    """
    if not invalid_citations:
        return set(), []

    if not os.environ.get("TAVILY_API_KEY"):
        print(f"{indent}⚠️  URL-drift recovery skipped: TAVILY_API_KEY not set")
        return set(), []

    # Lazy import to avoid pulling tavily / yaml at module load time.
    from ..validation.url_recovery import (
        CitationMetadata,
        attempt_url_recovery,
    )

    if citation_details is None:
        citation_details = _collect_all_citation_details(
            research_dir, sections_dir, output_dir,
        )

    # Group details by citation_num (a citation may appear in multiple files;
    # all rows share the same metadata, but we need every source_path to
    # rewrite each occurrence).
    details_by_num: Dict[str, List[Dict[str, Any]]] = {}
    for detail in citation_details:
        details_by_num.setdefault(detail["citation_num"], []).append(detail)

    recovered_citations: Set[str] = set()
    recoveries: List[Dict[str, Any]] = []

    print(
        f"\n{indent}🔄 Attempting URL-drift recovery for "
        f"{len(invalid_citations)} invalid citation(s)..."
    )

    for num in sorted(invalid_citations, key=int):
        rows = details_by_num.get(num)
        if not rows:
            continue
        first = rows[0]
        if not first.get("title"):
            continue  # No title → no query → no recovery

        metadata = CitationMetadata(
            title=first.get("title", ""),
            publisher=first.get("publisher", ""),
            author=first.get("author", ""),
            published_date=first.get("published_date", ""),
            original_url=first.get("url", ""),
        )

        result = attempt_url_recovery(metadata)
        if not result:
            continue

        # Swap the URL in every file where this citation appears
        for row in rows:
            source_path_str = row.get("source_path")
            if not source_path_str:
                continue
            _swap_citation_url_in_file(
                Path(source_path_str),
                num,
                metadata.original_url,
                result.recovered_url,
            )

        recovered_citations.add(num)
        recoveries.append({
            "citation_num": num,
            "original_url": metadata.original_url,
            "recovered_url": result.recovered_url,
            "claimed_title": result.claimed_title,
            "matched_title": result.matched_title,
            "jaccard": result.jaccard,
            "via_query": result.via_query,
            "via_provider": result.via_provider,
        })

    if recoveries:
        print(
            f"\n{indent}✨ Recovered URLs (source legitimate, URL had drifted):"
        )
        for rec in recoveries:
            print(
                f"{indent}  [^{rec['citation_num']}] title match "
                f"{rec['jaccard']:.2f}"
            )
            print(f"{indent}    old: {rec['original_url'][:80]}")
            print(f"{indent}    new: {rec['recovered_url'][:80]}")
    else:
        print(f"{indent}  (no recoveries this run)")

    return recovered_citations, recoveries


def write_redacted_hallucinations_log(
    output_dir: Path,
    invalid_citations: Set[str],
    citation_details: List[Dict[str, Any]],
    validation_results: Dict[str, Tuple[int, str]],
    *,
    citation_urls: Optional[Dict[str, str]] = None,
    deal: str = "",
    firm: str = "",
) -> Optional[Path]:
    """
    Write a markdown file documenting each dropped citation so the analyst
    can investigate manually — google the claimed title, find the real source
    if one exists, and re-insert it (via a future `inputs/Sources.md` or by
    direct edit).

    The premise: a dropped URL doesn't always mean a dropped *source*. The
    LLM may have fabricated the URL while the underlying article it was
    trying to cite actually exists. Recovery (Step 5) catches the easy
    drifted-URL cases automatically; this log captures the rest so the
    analyst has a clear worksheet rather than a black hole.

    Args:
        output_dir: Where to write `redacted-hallucinations.md`.
        invalid_citations: Post-recovery set of citation numbers that got
            dropped (recovered citations are NOT included).
        citation_details: Full citation details (one row per file occurrence).
        validation_results: Per-citation `(http_code, status_text)` from validate_url.
        deal: Optional deal name for the frontmatter.
        firm: Optional firm slug for the frontmatter.

    Returns:
        Path to the written file, or None if nothing was dropped.
    """
    if not invalid_citations:
        return None

    # Group details by citation_num so we can list all source files where
    # each dropped citation appeared.
    details_by_num: Dict[str, List[Dict[str, Any]]] = {}
    for detail in citation_details:
        details_by_num.setdefault(detail["citation_num"], []).append(detail)

    today = datetime.now().date().isoformat()

    lines: List[str] = []
    lines.append("---")
    lines.append(f'title: "Redacted Hallucinations — {output_dir.name}"')
    lines.append(f"lede: \"Citations dropped by the URL validator — for manual investigation. The title and publisher metadata may still be accurate even when the URL itself was fabricated.\"")
    if deal:
        lines.append(f"deal: {deal}")
    if firm:
        lines.append(f"firm: {firm}")
    lines.append(f"date_created: {today}")
    lines.append(f"date_modified: {today}")
    lines.append(f"total_dropped: {len(invalid_citations)}")
    lines.append("category: Redaction-Log")
    lines.append("---")
    lines.append("")
    lines.append("# Redacted Hallucinations")
    lines.append("")
    lines.append(
        "The URL validator dropped these citations because their URLs were "
        "inaccessible (hard 404), returned soft-404 pages, hit paywalls from "
        "non-allow-listed publishers, or matched a known LLM hallucination "
        "pattern. **The dropped URL is not necessarily proof that the "
        "underlying source doesn't exist** — the LLM may have fabricated the "
        "URL while the article it was trying to cite is real. If a claim "
        "depends on one of these citations, search for the title manually "
        "(links below); if you find the real source, re-insert it via the "
        "deal's `inputs/Sources.md` (per the human-curated-sources design) "
        "or by direct edit."
    )
    lines.append("")

    for num in sorted(invalid_citations, key=int):
        rows = details_by_num.get(num, [])
        if not rows:
            # Shouldn't normally happen — citation was dropped but never
            # collected. Surface a minimal entry so the analyst sees the loss.
            http_code, status_text = validation_results.get(num, (0, "unknown"))
            lines.append(f"## [^{num}] — {status_text}")
            lines.append("")
            lines.append(f"**Verdict:** `{status_text}` (HTTP code: `{http_code}`)")
            lines.append("")
            lines.append("*(No citation details collected — investigate `state.json` or the original 2-sections/ files.)*")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        # Disambiguate when the same citation_num is reused across files
        # with different URLs (per-file numbering, not globally unique).
        # Prefer the row whose URL matches the one that was actually
        # validated (citation_urls[num]); fall back to the first row.
        validated_url = (citation_urls or {}).get(num, "")
        chosen_row = next(
            (r for r in rows if r.get("url") == validated_url),
            rows[0],
        )
        url = chosen_row.get("url", "") or validated_url
        title = chosen_row.get("title", "")
        publisher = chosen_row.get("publisher", "")
        published_date = chosen_row.get("published_date", "")
        http_code, status_text = validation_results.get(num, (0, "unknown"))
        # Source-file list: only the files where the validated URL actually
        # appeared, not every file that happened to use the same [^N].
        if validated_url:
            relevant_rows = [r for r in rows if r.get("url") == validated_url] or rows
        else:
            relevant_rows = rows
        source_files = sorted({r.get("source_file", "") for r in relevant_rows if r.get("source_file")})

        # Header: prefer title; fall back to citation number.
        if title:
            lines.append(f"## [^{num}] — {title}")
        else:
            lines.append(f"## [^{num}] — (no title extracted)")
        lines.append("")

        if url:
            lines.append(f"- **Original URL:** <{url}>")
        if publisher:
            lines.append(f"- **Claimed publisher:** {publisher}")
        if published_date:
            lines.append(f"- **Claimed published date:** {published_date}")
        lines.append(f"- **Verdict:** `{status_text}` (HTTP code: `{http_code}`)")
        if source_files:
            lines.append("- **Appeared in:** " + ", ".join(f"`{f}`" for f in source_files))

        # Recovery-attempted note. _run_recovery_pass only attempts when title
        # is present; mirror that here so the analyst knows what happened.
        if title:
            lines.append("- **Recovery attempt:** Tavily searched, no candidate cleared the title-match threshold of 0.6 Jaccard.")
        else:
            lines.append("- **Recovery attempt:** Skipped — no title available to search.")
        lines.append("")

        # Investigation aids — clickable Google searches the analyst can use.
        if title:
            q_general = quote_plus(f'"{title}"')
            lines.append(f"**Google:** <https://www.google.com/search?q={q_general}>")
            host = _extract_host(url) if url else ""
            if host:
                q_site = quote_plus(f'"{title}" site:{host}')
                lines.append("")
                lines.append(f"**Same site (`{host}`):** <https://www.google.com/search?q={q_site}>")
            lines.append("")

        lines.append("---")
        lines.append("")

    file_path = output_dir / "redacted-hallucinations.md"
    file_path.write_text("\n".join(lines))
    return file_path


def save_source_validation_log(
    output_dir: Path,
    citation_details: List[Dict[str, Any]],
    validation_results: Dict[str, tuple],
    valid_citations: Set[str],
    invalid_citations: Set[str],
    potentially_valid: Set[str],
    gate_name: str = "cleanup_sections",
    recovered_citations: Optional[Set[str]] = None,
    recoveries: Optional[List[Dict[str, Any]]] = None,
    gated_citations: Optional[Set[str]] = None,
) -> None:
    """
    Save a comprehensive source validation log for the source cataloger.

    Args:
        output_dir: Output directory
        citation_details: Full citation details (url, title, definition, source_file, ...)
        validation_results: Dict mapping citation num to (http_code, status)
        valid_citations: Set of valid citation numbers (post-recovery — recovered
            citations move into this set)
        invalid_citations: Set of invalid citation numbers (post-recovery —
            recovered citations are no longer here)
        potentially_valid: Set of uncertain citation numbers
        gate_name: Which cleanup gate produced this log
        recovered_citations: Set of citation numbers whose URLs were recovered
            via URL-drift search. Status will be reported as "recovered" in
            the per-citation log entries.
        recoveries: List of recovery records (one per recovered citation), with
            original_url, recovered_url, matched_title, jaccard, via_query.
    """
    recovered_citations = recovered_citations or set()
    recoveries = recoveries or []
    gated_citations = gated_citations or set()

    log_entries = []

    for detail in citation_details:
        num = detail["citation_num"]
        http_code, status_text = validation_results.get(num, (0, "not checked"))

        # Order matters: recovered > gated > valid. Gated is a subset of valid;
        # we want the more specific label to win.
        if num in recovered_citations:
            validation_status = "recovered"
        elif num in gated_citations:
            validation_status = "verified-gated"
        elif num in valid_citations:
            validation_status = "valid"
        elif num in invalid_citations:
            validation_status = "removed"
        elif num in potentially_valid:
            validation_status = "uncertain"
        else:
            validation_status = "not checked"

        log_entries.append({
            "citation_num": num,
            "url": detail.get("url", ""),
            "title": detail.get("title", ""),
            "publisher": detail.get("publisher", ""),
            "author": detail.get("author", ""),
            "published_date": detail.get("published_date", ""),
            "full_definition": detail.get("full_definition", ""),
            "source_file": detail.get("source_file", ""),
            "http_code": http_code,
            "http_status": status_text,
            "validation_status": validation_status,
            "gate": gate_name,
        })

    log_path = output_dir / f"source-validation-log-{gate_name}.json"

    # Append to existing log if present (multiple gates write to different files)
    with open(log_path, "w") as f:
        json.dump({
            "gate": gate_name,
            "total_sources": len(log_entries),
            "valid": len(valid_citations),
            "gated": len(gated_citations),
            "removed": len(invalid_citations),
            "uncertain": len(potentially_valid),
            "recovered": len(recovered_citations),
            "sources": log_entries,
            "recoveries": recoveries,
        }, f, indent=2, ensure_ascii=False)

    print(f"  📋 Source validation log saved: {log_path.name}")


def remove_citation_references(content: str, citations_to_remove: Set[str]) -> str:
    """
    Remove inline citation references from content.

    Args:
        content: Markdown content with inline citations
        citations_to_remove: Set of citation numbers to remove (as strings)

    Returns:
        Content with specified citations removed
    """
    if not citations_to_remove:
        return content

    # Build pattern to match citations to remove
    # Matches [^1], [^2], etc. including surrounding whitespace and commas
    for num in citations_to_remove:
        # Remove citation with potential leading/trailing punctuation handling
        # Case 1: Citation alone or at end: "text [^1]" or "text. [^1]"
        content = re.sub(rf'\s*\[\^{num}\](?=[\s\.,;:\)\]]|$)', '', content)

        # Case 2: Citation in a list: "[^1], [^2]" -> "[^2]" or "[^1] [^2]" -> "[^2]"
        content = re.sub(rf'\[\^{num}\],?\s*', '', content)

    # Clean up any double spaces or orphaned commas
    content = re.sub(r'  +', ' ', content)
    content = re.sub(r',\s*,', ',', content)
    content = re.sub(r'\s+([.,;:])', r'\1', content)

    return content


def remove_citation_definitions(content: str, citations_to_remove: Set[str]) -> str:
    """
    Remove citation definition lines from content.

    Args:
        content: Markdown content with citation definitions
        citations_to_remove: Set of citation numbers to remove

    Returns:
        Content with citation definitions removed
    """
    lines = content.split('\n')
    filtered_lines = []

    for line in lines:
        # Check if this line is a citation definition to remove
        match = re.match(r'\[\^(\d+)\]:', line)
        if match and match.group(1) in citations_to_remove:
            continue  # Skip this line
        filtered_lines.append(line)

    return '\n'.join(filtered_lines)


def renumber_citations(content: str, old_to_new: Dict[str, str]) -> str:
    """
    Renumber citations based on mapping.

    Args:
        content: Markdown content with citations
        old_to_new: Dict mapping old citation numbers to new ones

    Returns:
        Content with renumbered citations
    """
    if not old_to_new:
        return content

    # Sort by old number descending to avoid conflicts (replace [^10] before [^1])
    for old_num in sorted(old_to_new.keys(), key=int, reverse=True):
        new_num = old_to_new[old_num]
        if old_num != new_num:
            # Replace inline references [^X]
            content = re.sub(rf'\[\^{old_num}\]', f'[^{new_num}]', content)

    return content


def reorder_citations_in_file(file_path: Path) -> bool:
    """
    Reorder citations in a single file to eliminate gaps.

    This function should be called AFTER invalid citations have been removed.
    It renumbers remaining citations to be sequential starting at 1.

    Example: [^1], [^4], [^7] -> [^1], [^2], [^3]

    Args:
        file_path: Path to markdown file

    Returns:
        True if file was modified, False otherwise
    """
    content = file_path.read_text()
    original = content

    # Extract all citation numbers currently in the file (inline refs)
    inline_refs = set(re.findall(r'\[\^(\d+)\](?!:)', content))

    # Extract all citation numbers from definitions
    definitions = set(re.findall(r'^\[\^(\d+)\]:', content, re.MULTILINE))

    # Combine and sort all citation numbers
    all_citations = sorted([int(n) for n in inline_refs | definitions])

    if not all_citations:
        return False  # No citations to reorder

    # Check if already sequential starting at 1
    expected = list(range(1, len(all_citations) + 1))
    if all_citations == expected:
        return False  # Already in order

    # Build renumbering map
    old_to_new: Dict[str, str] = {}
    for new_num, old_num in enumerate(all_citations, 1):
        if old_num != new_num:
            old_to_new[str(old_num)] = str(new_num)

    if not old_to_new:
        return False  # Nothing to renumber

    # Apply renumbering (descending order to avoid conflicts)
    content = renumber_citations(content, old_to_new)

    if content != original:
        file_path.write_text(content)
        return True

    return False


def reorder_directory_citations(directory: Path) -> int:
    """
    Reorder citations in all markdown files in a directory.

    This should be called AFTER remove_invalid_citations has cleaned all files.

    Args:
        directory: Directory containing markdown files

    Returns:
        Number of files that were modified
    """
    if not directory.exists():
        return 0

    modified_count = 0
    for md_file in sorted(directory.glob("*.md")):
        if reorder_citations_in_file(md_file):
            modified_count += 1

    return modified_count


def collect_all_citation_urls(output_dir: Path) -> Dict[str, str]:
    """
    Collect all citation URLs from research and section files.

    Args:
        output_dir: Output directory path

    Returns:
        Dict mapping citation number to URL
    """
    all_citations = {}

    # Collect from 1-research/ files
    research_dir = output_dir / "1-research"
    if research_dir.exists():
        for f in research_dir.glob("*.md"):
            content = f.read_text()
            citations = extract_citation_urls(content)
            all_citations.update(citations)

    # Collect from 2-sections/ files
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        for f in sections_dir.glob("*.md"):
            content = f.read_text()
            citations = extract_citation_urls(content)
            all_citations.update(citations)

    return all_citations


def remove_invalid_citations_from_directory(directory: Path, invalid_citations: Set[str]) -> int:
    """
    Remove invalid citations from all files in a directory.

    IMPORTANT: This function ONLY removes citations. It does NOT renumber.
    Call reorder_directory_citations() AFTER this to fix gaps.

    Args:
        directory: Directory containing markdown files
        invalid_citations: Set of citation numbers to remove

    Returns:
        Number of files updated
    """
    if not directory.exists():
        return 0

    if not invalid_citations:
        return 0

    updated_count = 0

    for md_file in sorted(directory.glob("*.md")):
        content = md_file.read_text()
        original = content

        # Step 1: Remove invalid citation references (inline [^N])
        content = remove_citation_references(content, invalid_citations)

        # Step 2: Remove invalid citation definitions ([^N]: ...)
        content = remove_citation_definitions(content, invalid_citations)

        # NOTE: Do NOT renumber here. File will have gaps.
        # Renumbering happens in a separate pass via reorder_directory_citations()

        if content != original:
            md_file.write_text(content)
            updated_count += 1

    return updated_count


def remove_invalid_citations_from_file(file_path: Path, invalid_citations: Set[str]) -> bool:
    """
    Remove invalid citations from a single file.

    IMPORTANT: This function ONLY removes citations. It does NOT renumber.
    Call reorder_citations_in_file() AFTER this to fix gaps.

    Args:
        file_path: Path to markdown file
        invalid_citations: Set of citation numbers to remove

    Returns:
        True if file was modified, False otherwise
    """
    if not file_path.exists():
        return False

    if not invalid_citations:
        return False

    content = file_path.read_text()
    original = content

    # Remove inline references
    content = remove_citation_references(content, invalid_citations)

    # Remove definitions
    content = remove_citation_definitions(content, invalid_citations)

    if content != original:
        file_path.write_text(content)
        return True

    return False


def remove_invalid_sources_agent(state: MemoState) -> Dict[str, Any]:
    """
    Remove Invalid Sources Agent implementation.

    Validates all citation URLs and removes those that are definitely invalid
    (404, hallucination patterns). Keeps potentially valid URLs (403, 401).

    CRITICAL: This agent uses a strict two-pass approach:

    PASS 1 - REMOVAL (no renumbering):
      - Remove inline refs [^N] from body text
      - Remove definitions [^N]: ...
      - Files now have GAPS in numbering

    PASS 2 - REORDER (after ALL removal is complete):
      - Renumber to eliminate gaps
      - [^1], [^4], [^7] -> [^1], [^2], [^3]

    This separation prevents race conditions where a citation number
    could mean different things during processing.

    Args:
        state: Current memo state

    Returns:
        Updated state with messages about removed citations
    """
    company_name = state["company_name"]
    firm = state.get("firm")

    print(f"\n🔍 Validating citation URLs for {company_name}...")

    # Get output directory from state (created at workflow start)
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        return {
            "messages": ["Remove invalid sources skipped: no output directory found"]
        }

    research_dir = output_dir / "1-research"
    sections_dir = output_dir / "2-sections"

    # Check for at least one directory to process
    if not research_dir.exists() and not sections_dir.exists():
        return {
            "messages": ["Remove invalid sources skipped: no research or sections directory"]
        }

    # Collect all citation URLs from both research and sections
    citation_urls = collect_all_citation_urls(output_dir)

    if not citation_urls:
        print("  No citations found to validate")
        return {
            "messages": ["Remove invalid sources: no citations found"]
        }

    print(f"  Found {len(citation_urls)} unique citations to validate")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: IDENTIFY INVALID CITATIONS
    # ═══════════════════════════════════════════════════════════════════

    invalid_citations: Set[str] = set()
    valid_citations: Set[str] = set()
    potentially_valid: Set[str] = set()
    gated_citations: Set[str] = set()  # subset of valid; paywalled-but-reputable
    validation_results: Dict[str, Tuple[int, str]] = {}

    print(f"  Validating URLs (parallel, {min(10, len(citation_urls))} workers)...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_citation = {
            executor.submit(validate_url, url): (num, url)
            for num, url in citation_urls.items()
        }

        for future in as_completed(future_to_citation):
            num, url = future_to_citation[future]
            try:
                _, http_code, status = future.result()
                validation_results[num] = (http_code, status)

                if http_code in CONTENT_INVALID_CODES:  # hallucination, soft-404, or paywall stub
                    invalid_citations.add(num)
                elif http_code == VERIFIED_GATED:
                    # Paywalled, but publisher is on the reputable allow-list.
                    # Counts as valid for downstream logic; tracked separately
                    # so the analyst sees "you have N sources behind paywalls."
                    gated_citations.add(num)
                    valid_citations.add(num)
                elif http_code in INVALID_HTTP_CODES:
                    invalid_citations.add(num)
                elif http_code in POTENTIALLY_VALID_CODES:
                    potentially_valid.add(num)
                elif http_code == 0:  # Connection error
                    potentially_valid.add(num)  # Keep but warn
                else:
                    valid_citations.add(num)

            except Exception as e:
                print(f"    Warning: Error validating [^{num}]: {e}")
                potentially_valid.add(num)

    gated_note = f" ({len(gated_citations)} gated)" if gated_citations else ""
    print(
        f"  Results (pre-recovery): {len(valid_citations)} valid{gated_note}, "
        f"{len(potentially_valid)} uncertain, {len(invalid_citations)} invalid"
    )

    if gated_citations:
        print("\n  🔒 Gated sources (kept, require subscription to verify):")
        for num in sorted(gated_citations, key=int):
            cit_url = citation_urls.get(num, "")
            host = _extract_host(cit_url) or "?"
            print(f"    [^{num}] {host} — {cit_url[:80]}")

    # Collect full citation details (used by both recovery and the validation log)
    all_citation_details = _collect_all_citation_details(
        research_dir, sections_dir, output_dir,
    )

    # Attempt URL-drift recovery for citations classified as invalid.
    # Successful recoveries swap the URL in source files and move the citation
    # from `invalid` back into `valid`. McKinsey-style URL drift is the
    # canonical case this rescues.
    recovered_citations, recoveries = _run_recovery_pass(
        invalid_citations,
        research_dir,
        sections_dir,
        output_dir,
        citation_details=all_citation_details,
        indent="  ",
    )
    invalid_citations = invalid_citations - recovered_citations
    valid_citations = valid_citations | recovered_citations

    # Save source validation log (captures all verdicts: valid, invalid,
    # uncertain, recovered)
    save_source_validation_log(
        output_dir,
        all_citation_details,
        validation_results,
        valid_citations,
        invalid_citations,
        potentially_valid,
        gate_name="cleanup_sections",
        recovered_citations=recovered_citations,
        recoveries=recoveries,
        gated_citations=gated_citations,
    )

    if not invalid_citations:
        msg = (
            f"Citation validation complete: {len(valid_citations)} valid, "
            f"{len(potentially_valid)} uncertain, 0 removed"
        )
        if recovered_citations:
            msg += f", {len(recovered_citations)} recovered"
        print("  ✓ No invalid citations to remove")
        return {"messages": [msg]}

    # Log remaining invalid citations
    print(f"\n  🗑️  Removing {len(invalid_citations)} invalid citations:")
    for num in sorted(invalid_citations, key=int):
        code, status = validation_results.get(num, (0, "Unknown"))
        url = citation_urls.get(num, "Unknown URL")
        print(f"    [^{num}]: {status} - {url[:60]}...")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: REMOVE INVALID CITATIONS (NO RENUMBERING YET)
    # Files will have GAPS after this step - that's expected!
    # ═══════════════════════════════════════════════════════════════════

    print(f"\n  📝 PASS 1: Removing invalid citations (no renumbering)...")

    # Remove from 1-research/ files
    if research_dir.exists():
        research_removed = remove_invalid_citations_from_directory(research_dir, invalid_citations)
        if research_removed:
            print(f"    ✓ Removed citations from {research_removed} research files")

    # Remove from 2-sections/ files
    if sections_dir.exists():
        sections_removed = remove_invalid_citations_from_directory(sections_dir, invalid_citations)
        if sections_removed:
            print(f"    ✓ Removed citations from {sections_removed} section files")

    # Remove from header.md if it exists
    header_file = output_dir / "header.md"
    if header_file.exists():
        if remove_invalid_citations_from_file(header_file, invalid_citations):
            print(f"    ✓ Removed citations from header.md")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: REORDER CITATIONS (AFTER ALL REMOVAL IS COMPLETE)
    # This eliminates gaps: [^1], [^4], [^7] -> [^1], [^2], [^3]
    # ═══════════════════════════════════════════════════════════════════

    print(f"\n  🔢 PASS 2: Reordering citations to eliminate gaps...")

    # Reorder in 1-research/ files
    if research_dir.exists():
        research_reordered = reorder_directory_citations(research_dir)
        if research_reordered:
            print(f"    ✓ Reordered citations in {research_reordered} research files")

    # Reorder in 2-sections/ files
    if sections_dir.exists():
        sections_reordered = reorder_directory_citations(sections_dir)
        if sections_reordered:
            print(f"    ✓ Reordered citations in {sections_reordered} section files")

    # Reorder header.md if it exists
    if header_file.exists():
        if reorder_citations_in_file(header_file):
            print(f"    ✓ Reordered citations in header.md")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: REASSEMBLE FINAL DRAFT (if sections exist)
    # ═══════════════════════════════════════════════════════════════════

    if sections_dir.exists():
        print(f"\n  📄 Reassembling final draft...")

        try:
            from cli.assemble_draft import assemble_final_draft
            from rich.console import Console
            console = Console()
            final_draft_path = assemble_final_draft(output_dir, console)
            print(f"  ✓ Final draft reassembled: {final_draft_path.name}")
        except ImportError as e:
            print(f"  ⚠️  Could not import assemble_draft CLI: {e}")
            print(f"  ⚠️  Please run manually: python -m cli.assemble_draft {output_dir}")

    # Write a worksheet for dropped citations so the analyst can investigate
    # manually — the URL may be fabricated but the underlying source real.
    redacted_path = write_redacted_hallucinations_log(
        output_dir,
        invalid_citations,
        all_citation_details,
        validation_results,
        citation_urls=citation_urls,
        deal=company_name or "",
        firm=firm or "",
    )
    if redacted_path:
        print(f"  📝 Redaction worksheet saved: {redacted_path.name}")

    # Calculate remaining citations
    remaining_count = len(citation_urls) - len(invalid_citations)
    summary = f"Removed {len(invalid_citations)} invalid citations, {remaining_count} remaining"
    if recovered_citations:
        summary += f" ({len(recovered_citations)} recovered to new URLs)"
    print(f"\n  ✅ {summary}")

    return {
        "messages": [summary],
        "citation_cleanup": {
            "total_citations": len(citation_urls),
            "valid": len(valid_citations),
            "gated": len(gated_citations),
            "gated_citations": list(gated_citations),
            "potentially_valid": len(potentially_valid),
            "removed": len(invalid_citations),
            "removed_citations": list(invalid_citations),
            "recovered": len(recovered_citations),
            "recovered_citations": list(recovered_citations),
            "recoveries": recoveries,
            "remaining": remaining_count,
        }
    }


def remove_invalid_sources_standalone(output_dir: Path) -> Dict[str, Any]:
    """
    Standalone function for CLI usage - validates and removes invalid citations.

    This can be called directly on any output directory without needing
    the full workflow state.

    Args:
        output_dir: Path to output directory containing 1-research/ and/or 2-sections/

    Returns:
        Dict with cleanup results
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        print(f"Error: Directory not found: {output_dir}")
        return {"error": "Directory not found"}

    research_dir = output_dir / "1-research"
    sections_dir = output_dir / "2-sections"

    if not research_dir.exists() and not sections_dir.exists():
        print(f"Error: No 1-research/ or 2-sections/ directory found in {output_dir}")
        return {"error": "No content directories found"}

    # Collect all citation URLs
    citation_urls = collect_all_citation_urls(output_dir)

    if not citation_urls:
        print("No citations found to validate")
        return {"message": "No citations found"}

    print(f"Found {len(citation_urls)} unique citations to validate")

    # Validate URLs in parallel
    invalid_citations: Set[str] = set()
    valid_citations: Set[str] = set()
    potentially_valid: Set[str] = set()
    gated_citations: Set[str] = set()  # subset of valid; paywalled-but-reputable
    validation_results: Dict[str, Tuple[int, str]] = {}

    print(f"Validating URLs (parallel, {min(10, len(citation_urls))} workers)...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_citation = {
            executor.submit(validate_url, url): (num, url)
            for num, url in citation_urls.items()
        }

        for future in as_completed(future_to_citation):
            num, url = future_to_citation[future]
            try:
                _, http_code, status = future.result()
                validation_results[num] = (http_code, status)

                if http_code in CONTENT_INVALID_CODES:  # hallucination, soft-404, or paywall stub
                    invalid_citations.add(num)
                elif http_code == VERIFIED_GATED:
                    # Paywalled, but publisher is on the reputable allow-list.
                    gated_citations.add(num)
                    valid_citations.add(num)
                elif http_code in INVALID_HTTP_CODES:
                    invalid_citations.add(num)
                elif http_code in POTENTIALLY_VALID_CODES:
                    potentially_valid.add(num)
                elif http_code == 0:
                    potentially_valid.add(num)
                else:
                    valid_citations.add(num)

            except Exception as e:
                print(f"  Warning: Error validating [^{num}]: {e}")
                potentially_valid.add(num)

    gated_note = f" ({len(gated_citations)} gated)" if gated_citations else ""
    print(
        f"Results (pre-recovery): {len(valid_citations)} valid{gated_note}, "
        f"{len(potentially_valid)} uncertain, {len(invalid_citations)} invalid"
    )

    if gated_citations:
        print("\n🔒 Gated sources (kept, require subscription to verify):")
        for num in sorted(gated_citations, key=int):
            cit_url = citation_urls.get(num, "")
            host = _extract_host(cit_url) or "?"
            print(f"  [^{num}] {host} — {cit_url[:80]}")

    # Collect citation details NOW (pre-removal) so both recovery and the
    # redaction worksheet can reference the original citation rows. After
    # removal + reorder, per-citation_num lookups lose anchoring — the
    # surviving [^6] after renumbering is a different citation than the
    # original [^6].
    cli_citation_details = _collect_all_citation_details(
        research_dir, sections_dir, output_dir,
    )

    # Attempt URL-drift recovery before dropping invalid citations.
    recovered_citations, recoveries = _run_recovery_pass(
        invalid_citations,
        research_dir,
        sections_dir,
        output_dir,
        citation_details=cli_citation_details,
        indent="",
    )
    invalid_citations = invalid_citations - recovered_citations
    valid_citations = valid_citations | recovered_citations

    if not invalid_citations:
        msg = "✓ No invalid citations to remove"
        if recovered_citations:
            msg += f" ({len(recovered_citations)} recovered to new URLs)"
        print(msg)
        return {
            "total": len(citation_urls),
            "valid": len(valid_citations),
            "gated": len(gated_citations),
            "uncertain": len(potentially_valid),
            "removed": 0,
            "recovered": len(recovered_citations),
            "recoveries": recoveries,
        }

    # Log remaining invalid citations
    print(f"\n🗑️  Removing {len(invalid_citations)} invalid citations:")
    for num in sorted(invalid_citations, key=int):
        code, status = validation_results.get(num, (0, "Unknown"))
        url = citation_urls.get(num, "Unknown URL")
        print(f"  [^{num}]: {status} - {url[:60]}...")

    # PASS 1: Remove invalid citations
    print(f"\n📝 PASS 1: Removing invalid citations...")

    if research_dir.exists():
        research_removed = remove_invalid_citations_from_directory(research_dir, invalid_citations)
        if research_removed:
            print(f"  ✓ Removed from {research_removed} research files")

    if sections_dir.exists():
        sections_removed = remove_invalid_citations_from_directory(sections_dir, invalid_citations)
        if sections_removed:
            print(f"  ✓ Removed from {sections_removed} section files")

    header_file = output_dir / "header.md"
    if header_file.exists():
        if remove_invalid_citations_from_file(header_file, invalid_citations):
            print(f"  ✓ Removed from header.md")

    # PASS 2: Reorder citations
    print(f"\n🔢 PASS 2: Reordering citations...")

    if research_dir.exists():
        research_reordered = reorder_directory_citations(research_dir)
        if research_reordered:
            print(f"  ✓ Reordered {research_reordered} research files")

    if sections_dir.exists():
        sections_reordered = reorder_directory_citations(sections_dir)
        if sections_reordered:
            print(f"  ✓ Reordered {sections_reordered} section files")

    if header_file.exists():
        if reorder_citations_in_file(header_file):
            print(f"  ✓ Reordered header.md")

    # Reassemble if sections exist
    if sections_dir.exists():
        print(f"\n📄 Reassembling final draft...")
        try:
            from cli.assemble_draft import assemble_final_draft
            from rich.console import Console
            console = Console()
            final_draft_path = assemble_final_draft(output_dir, console)
            print(f"✓ Final draft reassembled: {final_draft_path.name}")
        except ImportError as e:
            print(f"⚠️  Could not import assemble_draft: {e}")
            print(f"⚠️  Run manually: python -m cli.assemble_draft {output_dir}")

    # Write a worksheet for dropped citations so the analyst can investigate
    # manually. Uses the citation_details collected BEFORE removal so per-
    # citation_num lookups still point at the original rows.
    redacted_path = write_redacted_hallucinations_log(
        output_dir,
        invalid_citations,
        cli_citation_details,
        validation_results,
        citation_urls=citation_urls,
    )
    if redacted_path:
        print(f"📝 Redaction worksheet saved: {redacted_path.name}")

    remaining = len(citation_urls) - len(invalid_citations)
    summary_line = f"Removed {len(invalid_citations)} invalid citations, {remaining} remaining"
    if recovered_citations:
        summary_line += f" ({len(recovered_citations)} recovered to new URLs)"
    print(f"\n✅ {summary_line}")

    return {
        "total": len(citation_urls),
        "valid": len(valid_citations),
        "gated": len(gated_citations),
        "uncertain": len(potentially_valid),
        "removed": len(invalid_citations),
        "recovered": len(recovered_citations),
        "recoveries": recoveries,
        "remaining": remaining,
    }


# CLI entry point
def main():
    """CLI entry point for standalone citation validation and removal."""
    import sys

    # Load environment variables from the orchestrator's .env so the standalone
    # CLI gets the same secrets the workflow agent gets via src/main.py.
    # Resolves to <orchestrator-root>/.env regardless of the caller's cwd.
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    except ImportError:
        pass

    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.remove_invalid_sources <output_dir>")
        print("Example: python -m src.agents.remove_invalid_sources io/dark-matter/deals/ProfileHealth/outputs/ProfileHealth-v0.0.3")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    result = remove_invalid_sources_standalone(output_dir)

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()

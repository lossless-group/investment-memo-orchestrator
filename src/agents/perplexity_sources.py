"""
Perplexity provenance capture and citation reconciliation.

WHY THIS EXISTS
---------------
Every Sonar response carries a `search_results` array — the sources Perplexity
ACTUALLY retrieved, each with a real URL, a real title, and a real publication
date. The pipeline historically read only `choices[0].message.content`, which
meant every URL, title, and date that reached a memo was a *generated token*
rather than a *retrieved fact*. That is the mechanism behind citations that look
authoritative and do not exist.

The old system prompt made it worse by explicitly asking the model to emit
`[Source Title](https://full-url.com)` — i.e. instructing it to type a URL from
memory.

THE FIX
-------
Prose is left exactly as the model wrote it (its quality and outline adherence
are why we use Sonar at all). Only the citation *apparatus* is rebuilt, against
the retrieved-source array:

  - A definition whose URL was genuinely retrieved keeps its URL and gets its
    TRUE title and TRUE publication date written in (models drift on both even
    when the URL is right).
  - A definition whose URL was never retrieved is SUBSTITUTED with the retrieved
    source that best supports the claim it is attached to.
  - Only if no retrieved source can back the claim at all is the citation
    dropped — and then its inline markers are removed too.

INVARIANT: never orphan an inline marker. A `[^7]` in prose with no `[^7]:`
definition is the exact failure that makes these memos miserable to hand-edit,
so a citation is either rewritten, substituted, or removed *along with its
markers*. Prose text itself is never rewritten.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, parse_qsl, urlunsplit, urlencode

# Query params that are tracking noise and must not defeat URL matching.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "s", "share",
}

# Hosts whose display name isn't derivable by title-casing the domain.
_PUBLISHER_NAMES = {
    "wsj.com": "The Wall Street Journal",
    "ft.com": "Financial Times",
    "nytimes.com": "The New York Times",
    "cnbc.com": "CNBC",
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "theguardian.com": "The Guardian",
    "techcrunch.com": "TechCrunch",
    "cbinsights.com": "CB Insights",
    "pitchbook.com": "PitchBook",
    "crunchbase.com": "Crunchbase",
    "mckinsey.com": "McKinsey & Company",
    "hbr.org": "Harvard Business Review",
    "sec.gov": "U.S. Securities and Exchange Commission",
    "arxiv.org": "arXiv",
    "theinformation.com": "The Information",
    "venturebeat.com": "VentureBeat",
    "businesswire.com": "Business Wire",
    "prnewswire.com": "PR Newswire",
    "statista.com": "Statista",
    "gartner.com": "Gartner",
    "forrester.com": "Forrester",
    "idc.com": "IDC",
    "reuters.com": "Reuters",
    "bloomberg.com": "Bloomberg",
    "forbes.com": "Forbes",
    "wired.com": "WIRED",
    "axios.com": "Axios",
}

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "it", "its", "this", "that", "these", "those", "has", "have", "had", "will",
    "would", "can", "could", "may", "might", "s", "t", "we", "their", "there",
    "which", "than", "then", "also", "into", "over", "per", "about", "more",
}

# Citation keys that are canonical and must never be reconciled away — they do
# not point at retrieved web sources.
_PROTECTED_KEYS = {"deck", "dataroom", "internal"}

# Minimum number of shared meaningful tokens before a substitution is allowed.
# A high ratio on a one-word coincidence is noise, not support.
_MIN_TOKEN_OVERLAP = 2


# --------------------------------------------------------------------------
# Sonar call wrapper
# --------------------------------------------------------------------------

@dataclass
class SonarResult:
    """A Sonar response with its provenance intact."""

    content: str
    search_results: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None

    @property
    def retrieved_urls(self) -> List[str]:
        """Every URL Perplexity actually retrieved for this call."""
        urls = [r.get("url") for r in self.search_results if r.get("url")]
        urls.extend(u for u in self.citations if u not in urls)
        return urls


def call_sonar(client, **kwargs) -> SonarResult:
    """
    Call Perplexity via the OpenAI-compatible client, keeping the provenance.

    Drop-in replacement for `client.chat.completions.create(...)` at any Sonar
    call site — same kwargs, but returns a `SonarResult` carrying the retrieved
    sources instead of throwing them away.
    """
    response = client.chat.completions.create(**kwargs)

    try:
        payload = response.model_dump()
    except AttributeError:  # pragma: no cover - very old SDKs
        payload = dict(response)

    content = ""
    choices = payload.get("choices") or []
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""

    search_results = payload.get("search_results") or []
    citations = payload.get("citations") or []

    # Some deployments return citations but not search_results. Synthesize
    # minimal records so reconciliation still has ground truth to work with.
    if not search_results and citations:
        search_results = [{"url": u, "title": "", "date": None} for u in citations]

    return SonarResult(
        content=content,
        search_results=search_results,
        citations=citations,
        raw=payload,
    )


# --------------------------------------------------------------------------
# URL / formatting helpers
# --------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """
    Canonical form for comparing two URLs that point at the same document.

    Lowercases scheme and host, drops `www.`, strips the fragment and tracking
    query params, and removes a trailing slash.
    """
    if not url:
        return ""
    url = url.strip().rstrip(".,;)")
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.lower()

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    path = (parts.path or "").rstrip("/")

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS]
    query = urlencode(sorted(kept))

    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def _host_of(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


# Second-level labels that are part of a public suffix rather than a brand,
# so "bbc.co.uk" resolves to "bbc" and not "co".
_PUBLIC_SUFFIX_SLD = {"co", "com", "org", "net", "ac", "gov", "edu"}


def publisher_for(url: str) -> str:
    """
    Human-readable publisher name for a URL.

    Uses the registrable domain rather than the leftmost label, so a subdomain
    like `research.contrary.com` yields "Contrary" and not "Research".
    """
    host = _host_of(url)
    if not host:
        return "Web"
    if host in _PUBLISHER_NAMES:
        return _PUBLISHER_NAMES[host]

    labels = [l for l in host.split(".") if l]
    if len(labels) >= 3 and labels[-2] in _PUBLIC_SUFFIX_SLD:
        stem = labels[-3]          # bbc.co.uk -> bbc
    elif len(labels) >= 2:
        stem = labels[-2]          # research.contrary.com -> contrary
    else:
        stem = labels[0]

    # Re-check the allow-list against the registrable domain, so subdomains of
    # a known publisher still get its proper name.
    for known, name in _PUBLISHER_NAMES.items():
        if host.endswith("." + known):
            return name

    return stem.replace("-", " ").title() if stem else "Web"


def _format_long_date(iso_date: Optional[str]) -> str:
    """`2025-09-02` -> `2025, Sep 02`. Falls back to `n.d.`."""
    if not iso_date:
        return "n.d."
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso_date))
    if not m:
        m_year = re.match(r"(\d{4})", str(iso_date))
        return m_year.group(1) if m_year else "n.d."
    year, month, day = m.group(1), int(m.group(2)), m.group(3)
    month_name = _MONTHS[month - 1] if 1 <= month <= 12 else "Jan"
    return f"{year}, {month_name} {day}"


def _iso_or_na(value: Optional[str]) -> str:
    if not value:
        return "N/A"
    m = re.match(r"\d{4}-\d{2}-\d{2}", str(value))
    return m.group(0) if m else "N/A"


def format_definition(key: str, source: Dict[str, Any]) -> str:
    """
    Render one citation definition in the house format:

        [^1]: 2025, Sep 02. [Title](https://url). Publisher. Published: 2025-09-02 | Updated: N/A
    """
    url = source.get("url", "")
    title = (source.get("title") or "").strip()
    if not title:
        title = f"{publisher_for(url)} — source document"
    # Markdown link text must not contain unescaped brackets.
    title = title.replace("[", "(").replace("]", ")").strip()

    long_date = _format_long_date(source.get("date"))
    published = _iso_or_na(source.get("date"))
    updated = _iso_or_na(source.get("last_updated"))

    return (
        f"[^{key}]: {long_date}. [{title}]({url}). {publisher_for(url)}. "
        f"Published: {published} | Updated: {updated}"
    )


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

_DEF_LINE = re.compile(r"^\[\^([a-zA-Z0-9_-]+)\]:\s*(.*)$")
_URL_IN_TEXT = re.compile(r"https?://[^\s)\]<>\"']+")


def split_citations_section(content: str) -> Tuple[str, str, str]:
    """
    Split content into (main, heading, citations_block).

    `heading` preserves whichever citations heading the model emitted so the
    document is reassembled exactly as it came in.
    """
    m = re.search(r"^(#{1,6}\s*Citations\s*)$", content, re.MULTILINE | re.IGNORECASE)
    if not m:
        return content, "", ""
    return content[:m.start()], m.group(1), content[m.end():]


def parse_definitions(block: str) -> List[Tuple[str, str, str]]:
    """
    Parse `[^key]: ...` definitions out of a citations block.

    Returns a list of (key, url, raw_definition_text). Definitions may span
    multiple lines; a new definition starts only at a line-leading `[^key]:`,
    which is how the pipeline emits them.
    """
    defs: List[Tuple[str, str, str]] = []
    current_key: Optional[str] = None
    current_lines: List[str] = []

    def flush():
        if current_key is None:
            return
        text = "\n".join(current_lines).strip()
        url_match = _URL_IN_TEXT.search(text)
        defs.append((current_key, url_match.group(0) if url_match else "", text))

    for line in block.splitlines():
        m = _DEF_LINE.match(line)
        if m:
            flush()
            current_key = m.group(1)
            current_lines = [line]
        elif current_key is not None:
            current_lines.append(line)

    flush()
    return defs


def claim_context(main: str, key: str) -> str:
    """
    The sentence(s) each inline `[^key]` marker is attached to — i.e. the claim
    this citation is being asked to support.

    Scoped to the sentence, deliberately. A fixed character window bleeds tokens
    in from neighbouring claims, which makes an unsupportable claim look
    supported by whatever the previous sentence was about, and substitution
    stops discriminating.
    """
    marker = re.compile(r"\[\^" + re.escape(key) + r"\]")
    chunks: List[str] = []
    for m in marker.finditer(main):
        prefix = main[:m.start()]

        # House style puts the marker AFTER the sentence's terminator
        # ("Market size is $50B. [^1]"), and adjacent markers stack
        # ("... [^1] [^2]"). Strip those trailing artifacts first, or the
        # backward walk lands past the end of the claim and returns nothing.
        prefix = prefix.rstrip()
        while prefix.endswith("]"):
            open_idx = prefix.rfind("[^")
            if open_idx == -1:
                break
            prefix = prefix[:open_idx].rstrip()
        prefix = prefix.rstrip(".!?").rstrip()

        # Now walk back to the end of the PREVIOUS sentence / block boundary.
        boundary = max(
            prefix.rfind(". "), prefix.rfind("! "), prefix.rfind("? "),
            prefix.rfind("\n"),
        )
        chunks.append(prefix[boundary + 1:] if boundary != -1 else prefix)
    return " ".join(chunks)


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _score(claim_tokens: set, source: Dict[str, Any]) -> Tuple[float, int]:
    """
    Overlap between a claim and a candidate source's title + snippet.

    Returns (ratio, absolute_overlap). The absolute count matters as much as the
    ratio: a one-word coincidence on a short claim yields a high ratio and means
    nothing, so callers gate on both.
    """
    if not claim_tokens:
        return 0.0, 0
    src_tokens = _tokens(f"{source.get('title', '')} {source.get('snippet', '')}")
    if not src_tokens:
        return 0.0, 0
    shared = claim_tokens & src_tokens
    return len(shared) / len(claim_tokens), len(shared)


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------

@dataclass
class ReconcileReport:
    verified: int = 0
    retitled: int = 0
    substituted: int = 0
    dropped: int = 0
    protected: int = 0
    total: int = 0
    details: List[str] = field(default_factory=list)

    @property
    def fabricated(self) -> int:
        """Citations whose URL was never actually retrieved."""
        return self.substituted + self.dropped

    def summary(self) -> str:
        return (
            f"{self.total} citations: {self.verified} verified "
            f"({self.retitled} metadata-corrected), {self.substituted} substituted, "
            f"{self.dropped} dropped, {self.protected} protected"
        )


def reconcile_citations(
    content: str,
    search_results: Sequence[Dict[str, Any]],
    *,
    min_substitution_score: float = 0.20,
) -> Tuple[str, ReconcileReport]:
    """
    Rewrite a research file's citation definitions against retrieved sources.

    Prose is never modified except to remove inline markers for citations that
    could not be backed by any retrieved source.

    Args:
        content: Research markdown, with a `### Citations` block.
        search_results: The `search_results` array from the Sonar response(s)
            that produced this content.
        min_substitution_score: Claim/source token overlap below which a
            substitution is refused and the citation is dropped instead.

    Returns:
        (reconciled_content, report)
    """
    report = ReconcileReport()

    main, heading, block = split_citations_section(content)
    if not heading:
        return content, report

    definitions = parse_definitions(block)
    if not definitions:
        return content, report

    # Ground truth, indexed by normalized URL.
    provenance: Dict[str, Dict[str, Any]] = {}
    for record in search_results:
        url = record.get("url")
        if not url:
            continue
        provenance.setdefault(normalize_url(url), record)

    if not provenance:
        # No provenance available — refuse to guess. Leaving the file untouched
        # is strictly better than substituting against an empty set.
        return content, report

    used_urls: set = set()
    rebuilt: List[str] = []
    dropped_keys: List[str] = []

    for key, url, raw in definitions:
        report.total += 1

        if key.lower() in _PROTECTED_KEYS:
            report.protected += 1
            rebuilt.append(raw)
            continue

        norm = normalize_url(url)
        record = provenance.get(norm) if norm else None

        if record is not None:
            # URL was genuinely retrieved. Rewrite title/date from ground truth.
            new_def = format_definition(key, record)
            rebuilt.append(new_def)
            used_urls.add(norm)
            report.verified += 1
            if (record.get("title") or "").strip() and \
                    (record.get("title") or "").strip() not in raw:
                report.retitled += 1
                report.details.append(f"[^{key}] metadata corrected: {record.get('title')}")
            continue

        # Not retrieved — this URL was invented. Find the retrieved source that
        # best supports the claim it is attached to.
        #
        # Best score wins outright, reused or not: assigning the source that
        # actually supports the claim matters more than source variety, and a
        # duplicate URL across two keys is consolidated downstream by
        # `citation_assembly_agent`. (Preferring unused sources was tried and
        # mis-assigned claims to merely-unspent sources.)
        claim_tokens = _tokens(claim_context(main, key))

        best_norm, best_record, best_score = None, None, 0.0
        for cand_norm, cand_record in provenance.items():
            ratio, overlap = _score(claim_tokens, cand_record)
            if overlap >= _MIN_TOKEN_OVERLAP and ratio >= min_substitution_score \
                    and ratio > best_score:
                best_norm, best_record, best_score = cand_norm, cand_record, ratio

        if best_record is not None:
            rebuilt.append(format_definition(key, best_record))
            used_urls.add(best_norm)
            report.substituted += 1
            report.details.append(
                f"[^{key}] fabricated URL replaced ({url or 'no url'} -> {best_record.get('url')})"
            )
        else:
            dropped_keys.append(key)
            report.dropped += 1
            report.details.append(
                f"[^{key}] dropped — no retrieved source supports the claim ({url or 'no url'})"
            )

    # Remove inline markers for dropped citations so nothing is orphaned.
    for key in dropped_keys:
        main = re.sub(r"[ \t]*\[\^" + re.escape(key) + r"\]", "", main)
    # Tidy punctuation left doubled by marker removal; prose words are untouched.
    main = re.sub(r"[ \t]{2,}", " ", main)
    main = re.sub(r"[ \t]+\n", "\n", main)

    citations_body = "\n\n".join(rebuilt)
    reconciled = f"{main.rstrip()}\n\n{heading}\n\n{citations_body}\n"
    return reconciled, report


# --------------------------------------------------------------------------
# Provenance sidecar
# --------------------------------------------------------------------------

PROVENANCE_FILENAME = ".provenance.json"


def record_provenance(research_dir: Path, search_results: Sequence[Dict[str, Any]]) -> None:
    """
    Append retrieved URLs to a per-run provenance sidecar.

    Downstream validation reads this to tell a real-but-bot-blocked source (403
    on a URL Perplexity actually retrieved) from a fabricated one (403 on a URL
    that was never retrieved). Best-effort: never raises into the pipeline.
    """
    try:
        research_dir.mkdir(parents=True, exist_ok=True)
        path = research_dir / PROVENANCE_FILENAME

        existing: Dict[str, Dict[str, Any]] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                existing = {}

        for record in search_results:
            url = record.get("url")
            if not url:
                continue
            existing[normalize_url(url)] = {
                "url": url,
                "title": record.get("title", ""),
                "date": record.get("date"),
            }

        path.write_text(json.dumps(existing, indent=2, sort_keys=True))
    except Exception:  # noqa: BLE001 - provenance must never break a run
        pass


def load_provenance(research_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Read the provenance sidecar. Returns `{}` when absent or unreadable."""
    path = Path(research_dir) / PROVENANCE_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}

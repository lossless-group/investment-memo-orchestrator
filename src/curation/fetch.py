"""
URL → clean markdown fetcher for codified-mode sources.

Uses Jina Reader (`r.jina.ai`) as the extraction service — it turns
arbitrary URLs into LLM-friendly markdown without our needing to roll
our own HTML/PDF parsing. Free tier is generous; if a `JINA_API_KEY`
is set in the environment, it's sent as a Bearer header for higher
rate limits.

If Jina is unreachable or fails, we fall back to a minimal httpx GET
+ HTML strip via BeautifulSoup (already a project dependency).
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

import httpx


def fetch_url_markdown(
    url: str,
    *,
    timeout: int = 25,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a URL and return its content as clean markdown.

    Strategy:
        1. Try Jina Reader (`https://r.jina.ai/<url>`). It returns
           markdown with a `Title:` header line plus the article body.
        2. On failure, fall back to httpx GET + BeautifulSoup text
           extraction. Coarse but better than nothing.

    Returns:
        Dict with keys `url`, `fetched_at`, `title`, `markdown`, and
        `via` (jina | httpx | None), or None if both paths fail.
    """
    if not url:
        return None

    via_jina = _fetch_via_jina(url, timeout=timeout)
    if via_jina:
        return via_jina

    via_httpx = _fetch_via_httpx(url, timeout=timeout)
    return via_httpx


def _fetch_via_jina(url: str, *, timeout: int = 25) -> Optional[Dict[str, Any]]:
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"User-Agent": "MemoPop-Orchestrator/1.0"}
    api_key = os.environ.get("JINA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = httpx.get(jina_url, timeout=timeout, follow_redirects=True, headers=headers)
        if response.status_code != 200:
            return None
        markdown = response.text or ""
    except Exception:
        return None

    if not markdown.strip():
        return None

    return {
        "url": url,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "title": _extract_title_from_markdown(markdown) or url,
        "markdown": markdown,
        "via": "jina",
    }


def _fetch_via_httpx(url: str, *, timeout: int = 25) -> Optional[Dict[str, Any]]:
    try:
        response = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        if response.status_code != 200:
            return None
    except Exception:
        return None

    content_type = (response.headers.get("content-type") or "").lower()
    if "html" not in content_type:
        # Non-HTML (PDF, JSON) — out of scope for the fallback path.
        return None

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url
        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
    except Exception:
        return None

    if not text.strip():
        return None

    return {
        "url": url,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "title": title,
        "markdown": f"Title: {title}\n\nURL Source: {url}\n\n{text}",
        "via": "httpx",
    }


def _extract_title_from_markdown(markdown: str) -> Optional[str]:
    """Best-effort: Jina Reader prepends 'Title: ...'; otherwise pull first H1."""
    m = re.search(r"^Title:\s*(.+)$", markdown, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None

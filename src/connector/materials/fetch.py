"""Fetch a material link: share-link rewriting, timeouts, a size cap, and no private hosts.

A link that can't be fetched raises :class:`Unreadable`; the caller records it
as a ``material_unreadable`` skip on the deal, so a bad link never blocks the memo.

- **Google Drive** file links (``/file/d/<id>/view``, ``open?id=``) become
  ``uc?export=download&id=<id>``; Google Docs, Sheets, and Slides links become
  their export URLs (PDF, CSV, PDF).
- **Dropbox** links get ``dl=1``.
- **DocSend** is out of scope for v1: it is refused before any request, with a
  message telling the partner to upload the PDF instead.

On the real network every request (each redirect included) is checked against
private, loopback, and link-local addresses, so a partner's link can't make the
server read its own metadata endpoint or internal services. Tests swap in an
``httpx.MockTransport`` through :data:`TRANSPORT`.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from email.message import Message
from pathlib import PurePosixPath
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import httpx

#: Test seam: an httpx transport to use instead of the network. When set, the
#: private-address guard is not installed (the fake internet has no DNS).
TRANSPORT: httpx.BaseTransport | None = None

#: Largest download accepted, in bytes.
MAX_BYTES = 100 * 1024 * 1024
#: Connect, read, write, and pool timeouts, in seconds.
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_REDIRECTS = 5
USER_AGENT = "MemoPop/1 (+https://memopop.didi.sh)"


class Unreadable(Exception):
    """The link could not be fetched or read. ``str(exc)`` is the reason, for the partner."""


@dataclass
class Fetched:
    url: str
    data: bytes
    content_type: str
    filename: str


# ------------------------------------------------------------------ links


def check_link(link: str) -> str:
    """Return the link if it is an http(s) URL with a host, else raise ValueError."""
    parsed = urlparse(link.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("only http and https links can be fetched")
    return link.strip()


def is_docsend(link: str) -> bool:
    host = (urlparse(link).hostname or "").lower()
    return host == "docsend.com" or host.endswith(".docsend.com")


_DRIVE_FILE = re.compile(r"^/file/d/([\w-]+)")
_GOOGLE_DOC = re.compile(r"^/(document|spreadsheets|presentation)/d/([\w-]+)")
_EXPORT = {
    "document": "export?format=pdf",
    "spreadsheets": "export?format=csv",
    "presentation": "export/pdf",
}


def direct_url(link: str) -> str:
    """Rewrite Google Drive and Dropbox share links to their direct-download form."""
    parsed = urlparse(link)
    host = (parsed.hostname or "").lower()
    if host == "drive.google.com":
        match = _DRIVE_FILE.match(parsed.path)
        file_id = match.group(1) if match else (parse_qs(parsed.query).get("id") or [None])[0]
        if file_id:
            return f"https://drive.google.com/uc?{urlencode({'export': 'download', 'id': file_id})}"
    if host == "docs.google.com":
        match = _GOOGLE_DOC.match(parsed.path)
        if match:
            kind, doc_id = match.groups()
            return f"https://docs.google.com/{kind}/d/{doc_id}/{_EXPORT[kind]}"
    if host in ("dropbox.com", "www.dropbox.com"):
        query = {k: v for k, v in parse_qs(parsed.query).items() if k not in ("dl", "raw")}
        query["dl"] = ["1"]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    return link


# ------------------------------------------------------------------ the guard


def is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def guard_request(request: httpx.Request) -> None:
    """Refuse a request whose host resolves to a non-public address."""
    host = request.url.host
    try:
        infos = socket.getaddrinfo(host, request.url.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise Unreadable(f"The link's host '{host}' could not be found.") from exc
    for info in infos:
        if not is_public_address(info[4][0]):
            raise Unreadable(f"The link's host '{host}' is not a public address.")


# ------------------------------------------------------------------ fetching


def _filename(response: httpx.Response, url: str) -> str:
    disposition = response.headers.get("content-disposition")
    if disposition:
        message = Message()
        message["content-disposition"] = disposition
        name = message.get_filename()
        if name:
            return PurePosixPath(name).name
    return PurePosixPath(unquote(urlparse(url).path)).name


def client() -> httpx.Client:
    if TRANSPORT is not None:
        return httpx.Client(
            transport=TRANSPORT, timeout=TIMEOUT, follow_redirects=True, max_redirects=MAX_REDIRECTS
        )
    return httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        headers={"User-Agent": USER_AGENT},
        event_hooks={"request": [guard_request]},
    )


def fetch(link: str, max_bytes: int | None = None) -> Fetched:
    """Download a link (after rewriting), or raise :class:`Unreadable`."""
    limit = MAX_BYTES if max_bytes is None else max_bytes
    if is_docsend(link):
        raise Unreadable(
            "DocSend links can't be read by MemoPop yet. Download the deck as a PDF and "
            "upload it instead (an add_materials item with only a filename)."
        )
    url = direct_url(link)
    try:
        with client() as http, http.stream("GET", url) as response:
            if response.status_code >= 400:
                raise Unreadable(f"The link answered HTTP {response.status_code}.")
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                raise Unreadable(f"The file is larger than {limit // (1024 * 1024)} MB.")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise Unreadable(f"The file is larger than {limit // (1024 * 1024)} MB.")
                chunks.append(chunk)
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            return Fetched(
                url=str(response.url),
                data=b"".join(chunks),
                content_type=content_type,
                filename=_filename(response, str(response.url)),
            )
    except Unreadable:
        raise
    except httpx.TimeoutException as exc:
        raise Unreadable("The link took too long to answer.") from exc
    except httpx.TooManyRedirects as exc:
        raise Unreadable("The link redirected too many times.") from exc
    except httpx.HTTPError as exc:
        raise Unreadable(f"The link could not be reached ({type(exc).__name__}).") from exc

"""Tell the firm's site that a deal has a new compiled memo, so it drops its cached copy.

After a new compiled version is saved (a ``compile`` job, or the uploader's
apply step), MemoPop POSTs a small signed event to the firm's ``site_hook_url``
from ``firm.json``. The event names the deal and version, never the memo or a
link; the site fetches the memo itself with the site key it already holds.
Spec: ``context-v/specs/Notify-Firm-Sites-When-a-Memo-Compiles.md``.

- The body is signed with HMAC-SHA256 over ``"<timestamp>.<raw body>"`` using the
  firm's key from ``MEMOPOP_SITE_KEYS``. No ``site_hook_url`` or no site key
  means no notification, logged once.
- Delivery runs on a daemon thread, so it never blocks or fails the caller. Each
  attempt has a 5 s timeout. A connection error, a timeout, or a 5xx is retried
  after 1 s, 5 s and 25 s (up to three retries); a 4xx is not.
- Logs carry firm, deal, status and duration, never the key or the signature.
- Nothing is queued across a restart: a lost notification only means the site's
  cache lives until it expires.

``transport``, ``sleep`` and ``clock`` are module attributes so tests can swap
them for a fake endpoint, a recorder, and a fixed time.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .workspace import Workspace

log = logging.getLogger("memopop.connector.site_hook")

EVENT = "memo.compiled"
TIMEOUT_SECONDS = 5.0
#: Wait before each retry; its length is the number of retries.
RETRY_DELAYS: tuple[float, ...] = (1.0, 5.0, 25.0)

#: Seams for tests: the HTTP transport (None: a real network), the backoff wait,
#: and the clock that stamps each request.
transport: httpx.BaseTransport | None = None
sleep: Callable[[float], None] = time.sleep
clock: Callable[[], float] = time.time

_SENDERS: set[threading.Thread] = set()
_SENDERS_LOCK = threading.Lock()


def body_for(firm: str, deal: str, compiled: dict) -> bytes:
    """The event's exact bytes: which deal changed, and to what version. No memo, no links."""
    event = {
        "event": EVENT,
        "firm": firm,
        "deal": deal,
        "version": compiled.get("version"),
        "label": compiled.get("label"),
        "compiled_at": compiled.get("at"),
    }
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def signature(key: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(key.encode("utf-8"), timestamp.encode() + b"." + body, hashlib.sha256)
    return f"sha256={digest.hexdigest()}"


def _retryable(status: int | None) -> bool:
    return status is None or status >= 500


def deliver(url: str, key: str, firm: str, deal: str, body: bytes) -> int | None:
    """Send the event, retrying as the spec says. Returns the last status, None if none came."""
    status: int | None = None
    outcome = "not sent"
    with httpx.Client(transport=transport, timeout=TIMEOUT_SECONDS) as client:
        for attempt in range(len(RETRY_DELAYS) + 1):
            if attempt:
                sleep(RETRY_DELAYS[attempt - 1])
            timestamp = str(int(clock()))
            headers = {
                "Content-Type": "application/json",
                "X-MemoPop-Timestamp": timestamp,
                "X-MemoPop-Signature": signature(key, timestamp, body),
            }
            started = time.monotonic()
            try:
                status = client.post(url, content=body, headers=headers).status_code
                outcome = str(status)
            except httpx.HTTPError as exc:  # timeout, refused, DNS, ...
                status = None
                outcome = exc.__class__.__name__
            log.info(
                "site hook: firm %s, deal %s, attempt %d, %s, %.0f ms",
                firm,
                deal,
                attempt + 1,
                outcome,
                (time.monotonic() - started) * 1000,
            )
            if not _retryable(status):
                return status
    log.warning("site hook gave up: firm %s, deal %s, last %s", firm, deal, outcome)
    return status


def _target(ws: Workspace, deal: str) -> tuple[str, str] | None:
    """The firm's hook URL and site key, or None (logged) if it has no usable pair."""
    url = ws.firm_config().get("site_hook_url")
    if not url:
        log.info("site hook skipped: firm %s has no site_hook_url (deal %s)", ws.firm, deal)
        return None
    if not isinstance(url, str) or not url.lower().startswith(("https://", "http://")):
        log.warning("site hook skipped: firm %s has a site_hook_url that isn't http(s)", ws.firm)
        return None
    key = ws.settings.site_keys.get(ws.firm)
    if not key:
        log.info("site hook skipped: firm %s has no site key (deal %s)", ws.firm, deal)
        return None
    return url, key


def notify(ws: Workspace, deal: str, compiled: dict) -> bool:
    """Start sending the event for ``deal``'s compiled version in the background.

    Returns whether a send was started. Never raises: a broken hook must not
    break the compile or upload that called it.
    """
    try:
        target = _target(ws, deal)
        if target is None:
            return False
        url, key = target
        body = body_for(ws.firm, deal, compiled)
    except Exception:
        log.exception("site hook skipped: firm %s, deal %s", ws.firm, deal)
        return False
    firm = ws.firm

    def send() -> None:
        try:
            deliver(url, key, firm, deal, body)
        except Exception:
            log.exception("site hook failed: firm %s, deal %s", firm, deal)
        finally:
            with _SENDERS_LOCK:
                _SENDERS.discard(threading.current_thread())

    sender = threading.Thread(target=send, name=f"site-hook-{deal}", daemon=True)
    with _SENDERS_LOCK:
        _SENDERS.add(sender)
    sender.start()
    return True


def wait_for_senders(timeout: float) -> int:
    """Wait up to ``timeout`` seconds for every send to finish; return how many still run.

    The server never needs this. A one-shot script (the uploader's apply step)
    calls it before exiting, since its daemon threads die with the process.
    """
    deadline = time.monotonic() + timeout
    with _SENDERS_LOCK:
        senders = list(_SENDERS)
    for sender in senders:
        sender.join(max(0.0, deadline - time.monotonic()))
    with _SENDERS_LOCK:
        return sum(1 for s in _SENDERS if s.is_alive())

"""One-time upload tokens: random, single-use, and expiring after an hour.

A token is the only credential the upload page takes, so it carries the firm,
the deal, and the materials waiting for files. Records live under
``<MEMO_IO_ROOT>/.uploads/`` (outside every firm's workspace, and not a valid
firm slug), keyed by the token's SHA-256, so the directory never holds a usable
token. A token is spent by renaming its record, which only one caller can win.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

TTL_SECONDS = 3600


def now() -> float:
    """The clock tokens expire by (a seam for tests)."""
    return time.time()


@dataclass
class Upload:
    firm: str
    deal: str
    #: [{material_id, filename, kind}] waiting for a file, in the order given.
    materials: list[dict]
    expires_at: float


class TokenUnknown(Exception):
    pass


class TokenSpent(Exception):
    """Used already, or expired."""


def _dir(io_root: Path) -> Path:
    return Path(io_root) / ".uploads"


def _record(io_root: Path, token: str) -> Path:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return _dir(io_root) / f"{digest}.json"


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def issue(io_root: Path, firm: str, deal: str, materials: list[dict]) -> tuple[str, float]:
    """Create a token for these materials; return it and when it expires."""
    token = secrets.token_urlsafe(32)
    expires_at = now() + TTL_SECONDS
    path = _record(io_root, token)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"firm": firm, "deal": deal, "materials": materials, "expires_at": expires_at}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body), encoding="utf-8")
    os.replace(tmp, path)
    return token, expires_at


def _load(path: Path) -> Upload:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Upload(data["firm"], data["deal"], data["materials"], float(data["expires_at"]))


def peek(io_root: Path, token: str) -> Upload:
    """The upload a token is for, without spending it."""
    path = _record(io_root, token)
    if path.is_file():
        upload = _load(path)
        if now() >= upload.expires_at:
            raise TokenSpent("expired")
        return upload
    if path.with_suffix(".spent").is_file():
        raise TokenSpent("used")
    raise TokenUnknown()


def spend(io_root: Path, token: str) -> Upload:
    """Spend a token once. A second call, or a call after expiry, raises TokenSpent."""
    upload = peek(io_root, token)
    path = _record(io_root, token)
    try:
        os.rename(path, path.with_suffix(".spent"))
    except FileNotFoundError:
        raise TokenSpent("used") from None
    return upload

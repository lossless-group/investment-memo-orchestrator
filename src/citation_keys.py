"""Hex citation keys derived from the source: same source, same key, everywhere.

Numbered keys (``[^1]``) are positions inside one section's research, so they
collide when sections are stitched together. A key derived from the source
itself can't: the same source is the same key in every section, and two
sources never share one. Rendering (Pandoc exports, LFM sites) numbers them.

The contract is fixed in context-v/plans/Hex-Code-Citations-and-a-Repair-Tool.md
and shared by the repair tool and the drafting pipeline, so both write the same
keys:

- Identity: the first ``http(s)://`` or ``file://`` link in the definition,
  percent-decoded, lowercased, trailing slash removed. With no link, the
  definition text with its date prefix removed, whitespace collapsed, lowercased.
- Key: ``sha256(identity)`` as an integer, written in base 36 (``0-9a-z``),
  first 6 characters.
- ``assign_keys()`` maps each old key to its hex key; two different identities
  whose 6 characters collide both get 8.
"""

from __future__ import annotations

import hashlib
import re
import string
from urllib.parse import unquote

_BASE36 = string.digits + string.ascii_lowercase
# Schemes are case-insensitive (HTTPS://, File://); the identity is lowercased anyway.
_LINK = re.compile(r"(?:https?|file)://[^\s)\]>]+", re.IGNORECASE)
# "2025, Jan 08. " — the date every definition starts with.
_DATE_PREFIX = re.compile(r"^\s*\d{4},\s+[A-Za-z]{3,9}\.?\s+\d{1,2}\.\s*")

SHORT = 6
LONG = 8


def source_identity(definition: str) -> str:
    """What makes two definitions the same source: the link, else the text."""
    match = _LINK.search(definition)
    if match:
        return unquote(match.group(0)).lower().rstrip("/")
    return " ".join(_DATE_PREFIX.sub("", definition).split()).lower()


def _base36(digest: bytes) -> str:
    n = int.from_bytes(digest, "big")
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(_BASE36[r])
    return "".join(reversed(out)) or "0"


def _key(identity: str, length: int = SHORT) -> str:
    return _base36(hashlib.sha256(identity.encode("utf-8")).digest())[:length]


def source_key(definition: str) -> str:
    """The hex citation key for a source: same source, same key, everywhere."""
    return _key(source_identity(definition))


def assign_keys(definitions: dict[str, str]) -> dict[str, str]:
    """Map each old key to its source's hex key.

    Two definitions of one source get one key. If two different identities give
    the same 6 characters, both get 8.
    """
    identity_of = {old: source_identity(d) for old, d in definitions.items()}
    identities_by_short: dict[str, set[str]] = {}
    for identity in identity_of.values():
        identities_by_short.setdefault(_key(identity), set()).add(identity)
    keys: dict[str, str] = {}
    for old, identity in identity_of.items():
        short = _key(identity)
        keys[old] = _key(identity, LONG) if len(identities_by_short[short]) > 1 else short
    return keys

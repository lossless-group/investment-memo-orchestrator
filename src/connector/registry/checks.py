"""Checks a submitted artifact must pass, named in each step's ``produces.checks``.

Each check takes the content and its parameter and returns ``(passed, detail)``.
To add one, add a function and a line in :data:`CHECKS`; a step that names an
unknown check fails the registry lint.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_INLINE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
_DEFINITION = re.compile(r"^\[\^([^\]\s]+)\]:", re.MULTILINE)


def _words(content: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][\w'’-]*", content))


def not_empty(content: str, _: Any) -> tuple[bool, str]:
    return (bool(content.strip()), "The artifact is empty." if not content.strip() else "")


def min_words(content: str, minimum: int) -> tuple[bool, str]:
    n = _words(content)
    return n >= minimum, f"{n} words; at least {minimum} are needed."


def max_chars(content: str, maximum: int) -> tuple[bool, str]:
    n = len(content)
    return n <= maximum, f"{n} characters; at most {maximum} are allowed."


def has_citations(content: str, minimum: int | bool) -> tuple[bool, str]:
    minimum = 1 if minimum is True else int(minimum)
    cited = set(_INLINE.findall(content))
    return (
        len(cited) >= minimum,
        f"{len(cited)} distinct inline citations; at least {minimum} needed.",
    )


def citations_resolve(content: str, _: Any) -> tuple[bool, str]:
    used = set(_INLINE.findall(content))
    defined = set(_DEFINITION.findall(content))
    missing = sorted(used - defined)
    if missing:
        listed = ", ".join(f"[^{m}]" for m in missing)
        return False, f"Cited but never defined in the citation list: {listed}."
    return True, "Every inline citation has a definition."


_HEX_KEY = re.compile(r"[0-9a-z]{6}(?:[0-9a-z]{2})?")
_DEFINITION_TEXT = re.compile(r"^\[\^([^\]\s]+)\]:[ \t]*(.*)$", re.MULTILINE)


def hex_keys_match_sources(content: str, _: Any) -> tuple[bool, str]:
    """Every hex-shaped key is the key its definition's source gives.

    A hex key is ``source_key()`` of the source (src/citation_keys.py): six
    base-36 characters, or eight where two sources collide. Numbered keys from
    older drafts are not hex keys and pass; compile converts them.
    """
    from src.citation_keys import source_key

    wrong = []
    for key, definition in _DEFINITION_TEXT.findall(content):
        if not _HEX_KEY.fullmatch(key):
            continue
        expected = source_key(definition)
        if not key.startswith(expected):  # an 8-character key extends the 6
            wrong.append(f"[^{key}] should be [^{expected}]")
    if wrong:
        return False, (
            "Hex keys that don't match their source (a key is sha256 of the source's "
            "link, in base 36, first six characters): " + "; ".join(wrong) + "."
        )
    return True, "Every hex key matches its source."


def required_headings(content: str, headings: list[str]) -> tuple[bool, str]:
    lines = {line.strip().lower() for line in content.splitlines() if line.lstrip().startswith("#")}
    missing = [h for h in headings if h.strip().lower() not in lines]
    if missing:
        return False, "Missing heading(s): " + ", ".join(missing)
    return True, "All required headings present."


_FENCED_YAML = re.compile(r"^```ya?ml[ \t]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def fenced_yaml(content: str, keys: list[str]) -> tuple[bool, str]:
    """A fenced ```yaml block that parses to a mapping with every key in ``keys``."""
    import yaml

    match = _FENCED_YAML.search(content)
    if not match:
        return False, "No ```yaml block found."
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return False, f"The yaml block does not parse: {exc.__class__.__name__}."
    if not isinstance(data, dict):
        return False, "The yaml block is not a mapping of keys to values."
    missing = [k for k in keys if data.get(k) in (None, "")]
    if missing:
        return False, "The yaml block is missing: " + ", ".join(missing)
    return True, "The yaml block has every required key."


CHECKS: dict[str, Callable[[str, Any], tuple[bool, str]]] = {
    "not_empty": not_empty,
    "min_words": min_words,
    "max_chars": max_chars,
    "has_citations": has_citations,
    "citations_resolve": citations_resolve,
    "hex_keys_match_sources": hex_keys_match_sources,
    "required_headings": required_headings,
    "fenced_yaml": fenced_yaml,
}


def run_checks(content: str, checks: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for name, param in checks.items():
        passed, detail = CHECKS[name](content, param)
        results.append({"name": name, "passed": passed, "detail": detail})
    return results

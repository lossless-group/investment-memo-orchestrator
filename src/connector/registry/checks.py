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
        f"{len(cited)} distinct inline citations ([^1] style); at least {minimum} needed.",
    )


def citations_resolve(content: str, _: Any) -> tuple[bool, str]:
    used = set(_INLINE.findall(content))
    defined = set(_DEFINITION.findall(content))
    missing = sorted(used - defined)
    if missing:
        listed = ", ".join(f"[^{m}]" for m in missing)
        return False, f"Cited but never defined in the citation list: {listed}."
    return True, "Every inline citation has a definition."


def required_headings(content: str, headings: list[str]) -> tuple[bool, str]:
    lines = {line.strip().lower() for line in content.splitlines() if line.lstrip().startswith("#")}
    missing = [h for h in headings if h.strip().lower() not in lines]
    if missing:
        return False, "Missing heading(s): " + ", ".join(missing)
    return True, "All required headings present."


CHECKS: dict[str, Callable[[str, Any], tuple[bool, str]]] = {
    "not_empty": not_empty,
    "min_words": min_words,
    "max_chars": max_chars,
    "has_citations": has_citations,
    "citations_resolve": citations_resolve,
    "required_headings": required_headings,
}


def run_checks(content: str, checks: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for name, param in checks.items():
        passed, detail = CHECKS[name](content, param)
        results.append({"name": name, "passed": passed, "detail": detail})
    return results

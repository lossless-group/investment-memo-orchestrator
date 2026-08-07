"""Regression tests for orphaned citation definitions.

A dropped citation used to leave its definition *body* behind: the
inline-reference pass stripped the `[^N]` off the front of the
definition line (its Case-1 lookahead accepted the following `:`), after
which the definition pass could no longer recognize the line. The
orphan then got concatenated onto the preceding definition during
assembly, carrying the dead or fabricated URL into the final draft.

Pre-existing and independent of the membership gate — reproduced with
enforcement off, no Sources.md, and an ordinary hard 404.
"""

from src.agents.remove_invalid_sources import (
    remove_citation_definitions,
    remove_citation_references,
)

CITATIONS = (
    "[^1]: 2026, Jan 01. [Good](https://good.test/a). Pub. Published: 2026-01-01 | Updated: N/A\n"
    "\n"
    "[^2]: 2026, Jan 01. [Dead](https://dead.test/gone). Pub. Published: 2026-01-01 | Updated: N/A\n"
)
BODY = "## Overview\n\nClaim one.[^1]\nClaim two.[^2]\n\n---\n\n### Citations\n\n"


def _drop(content: str, nums):
    """Apply the agent's real two-step removal, in the real order."""
    content = remove_citation_references(content, set(nums))
    return remove_citation_definitions(content, set(nums))


def test_dropped_definition_leaves_no_orphan():
    """The bug, stated directly: no fragment of the dropped URL survives."""
    out = _drop(BODY + CITATIONS, {"2"})
    assert "dead.test/gone" not in out, "dropped URL survived as an orphan"
    assert "[Dead]" not in out


def test_surviving_definition_is_intact():
    """The kept citation must not be corrupted by its neighbor's removal."""
    out = _drop(BODY + CITATIONS, {"2"})
    assert (
        "[^1]: 2026, Jan 01. [Good](https://good.test/a). "
        "Pub. Published: 2026-01-01 | Updated: N/A"
    ) in out, "surviving definition was mangled"


def test_inline_markers_are_handled_correctly():
    out = _drop(BODY + CITATIONS, {"2"})
    assert "[^1]" in out, "kept citation lost its inline marker"
    assert "[^2]" not in out, "dropped citation kept its inline marker"


def test_definitions_on_consecutive_lines_also_survive():
    """No blank line between definitions — the tighter packing that first
    surfaced this. Real memos are blank-line separated, but nothing
    guarantees an agent won't emit them packed."""
    packed = BODY + (
        "[^1]: 2026, Jan 01. [Good](https://good.test/a).\n"
        "[^2]: 2026, Jan 01. [Dead](https://dead.test/gone).\n"
    )
    out = _drop(packed, {"2"})
    assert "dead.test/gone" not in out
    assert "good.test/a" in out


def test_multiple_drops_at_once():
    content = BODY + CITATIONS + (
        "\n[^3]: 2026, Jan 01. [AlsoDead](https://dead.test/two).\n"
    )
    out = _drop(content, {"2", "3"})
    assert "dead.test/gone" not in out
    assert "dead.test/two" not in out
    assert "good.test/a" in out


def test_inline_reference_followed_by_colon_still_removed():
    """The guard keys on line-start, so a mid-sentence `[^N]:` is still
    treated as an inline reference — the guard must not over-apply."""
    out = remove_citation_references("As follows[^2]: a thing.", {"2"})
    assert "[^2]" not in out


def test_removal_is_a_noop_when_nothing_to_remove():
    content = BODY + CITATIONS
    assert _drop(content, set()) == content

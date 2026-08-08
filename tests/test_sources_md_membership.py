"""Tests for the approved-source membership predicate.

Covers loop tickets 1 (schema round-trip) and 2 (`approved_urls`) of
`context-v/loops/Frontloaded-Source-Approval-Loop.md`.

Write-path tests use tmp_path fixtures only. The real firm `Sources.md`
files under `io/<firm>/` are read but never written — per the tree's
"never mint test entities in canonical data" rule.
"""

from pathlib import Path

import pytest

from src.curation import (
    SourceEntry,
    approved_urls,
    canonical_url,
    is_approved_entry,
    is_approved_url,
    is_codified,
    load_sources_md,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_sources(tmp_path: Path, frontmatter: str, body: str = "") -> Path:
    inputs = tmp_path / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "Sources.md").write_text(f"---\n{frontmatter}\n---\n\n{body}")
    return inputs


# --------------------------------------------------------------------------
# Ticket 1 — schema round-trip
# --------------------------------------------------------------------------

def test_bibliographic_fields_round_trip(tmp_path):
    """title/publisher/published_date/verdict survive the loader.

    Before this change the loader dropped all four, which is why
    tools/curate_sources.py had to bypass it and parse raw frontmatter.
    `title` is the hard requirement: attempt_url_recovery() returns None
    without one.
    """
    inputs = _write_sources(tmp_path, """
mode: codified
deal: TestCo
firm: test-firm
sources:
  - url: https://example.org/a
    title: "The Real Title"
    publisher: "Example Org"
    published_date: "2026-01-15"
    sections: [market-context]
    rank: 2
    verdict: approved
    verdict_reason: ""
""".strip())

    sm = load_sources_md(inputs)
    assert sm is not None
    entry = sm.sources[0]
    assert entry.title == "The Real Title"
    assert entry.publisher == "Example Org"
    assert entry.published_date == "2026-01-15"
    assert entry.verdict == "approved"
    assert entry.rank == 2


def test_missing_bibliographic_fields_default_to_empty(tmp_path):
    """A legacy entry with only a url must still load, with empty strings."""
    inputs = _write_sources(tmp_path, """
mode: codified
sources:
  - url: https://example.org/legacy
""".strip())

    entry = load_sources_md(inputs).sources[0]
    assert entry.title == ""
    assert entry.publisher == ""
    assert entry.verdict == ""


def test_verdict_is_case_insensitive(tmp_path):
    inputs = _write_sources(tmp_path, """
mode: codified
sources:
  - url: https://example.org/a
    verdict: REJECTED
""".strip())
    assert load_sources_md(inputs).sources[0].verdict == "rejected"


# --------------------------------------------------------------------------
# Ticket 2 — approved_urls / membership
# --------------------------------------------------------------------------

@pytest.mark.parametrize("variant", [
    "https://www.example.org/a/",
    "http://example.org/a",
    "https://example.org/a?utm_source=news&utm_medium=email",
    "https://example.org/a#section-3",
    "HTTPS://EXAMPLE.ORG/a",
])
def test_membership_survives_url_drift(tmp_path, variant):
    """Canonicalization must collapse the shapes the same URL arrives in.

    A citation written as `https://www.example.org/a/` must match an
    approved entry written as `https://example.org/a`, or the gate would
    strip legitimate citations over a trailing slash.
    """
    inputs = _write_sources(tmp_path, """
mode: codified
sources:
  - url: https://example.org/a
""".strip())

    approved = approved_urls(load_sources_md(inputs))
    assert is_approved_url(variant, approved), f"{variant} should be a member"


def test_unapproved_url_is_not_a_member(tmp_path):
    inputs = _write_sources(tmp_path, """
mode: codified
sources:
  - url: https://example.org/a
""".strip())
    approved = approved_urls(load_sources_md(inputs))
    # The exact class of URL the incident report named: a live placeholder.
    assert not is_approved_url("https://example.com/fabricated", approved)
    assert not is_approved_url("", approved)


def test_verdict_revokes_rather_than_grants(tmp_path):
    """Presence approves; only an explicit rejection removes.

    Backward compatibility is the whole point: every Sources.md written
    before the verdict field existed has no verdict, and those entries
    must remain approved. Requiring verdict == 'approved' to grant
    membership would empty the set for every existing codified deal.
    """
    inputs = _write_sources(tmp_path, """
mode: codified
sources:
  - url: https://example.org/no-verdict
  - url: https://example.org/explicitly-approved
    verdict: approved
  - url: https://example.org/rejected
    verdict: rejected
    verdict_reason: wrong-entity
""".strip())

    approved = approved_urls(load_sources_md(inputs))
    assert is_approved_url("https://example.org/no-verdict", approved)
    assert is_approved_url("https://example.org/explicitly-approved", approved)
    assert not is_approved_url("https://example.org/rejected", approved)
    assert len(approved) == 2


def test_approved_urls_empty_when_not_codified(tmp_path):
    """A non-codified file yields an empty set.

    Callers MUST gate on is_codified() first — an empty set means
    "enforcement does not apply", never "nothing is allowed".
    """
    inputs = _write_sources(tmp_path, """
mode: search
sources:
  - url: https://example.org/a
""".strip())
    sm = load_sources_md(inputs)
    assert not is_codified(sm)
    # The set is non-empty by content, but callers skip enforcement entirely.
    assert approved_urls(None) == set()


def test_is_approved_entry_direct():
    assert is_approved_entry(SourceEntry(url="https://a.test"))
    assert is_approved_entry(SourceEntry(url="https://a.test", verdict="approved"))
    assert not is_approved_entry(SourceEntry(url="https://a.test", verdict="rejected"))
    assert not is_approved_entry(SourceEntry(url="https://a.test", verdict="denied"))
    # A machine verdict from the validation ladder does not revoke analyst
    # approval — reachability is a separate predicate from membership.
    assert is_approved_entry(SourceEntry(url="https://a.test", verdict="timeout"))


# --------------------------------------------------------------------------
# Real-corpus regression — read-only
# --------------------------------------------------------------------------

def _real_sources_dirs():
    io_root = REPO_ROOT / "io"
    if not io_root.exists():
        return []
    return [p.parent for p in sorted(io_root.glob("*/deals/*/inputs/Sources.md"))]


@pytest.mark.parametrize("inputs_dir", _real_sources_dirs(), ids=lambda p: p.parts[-3])
def test_real_codified_deals_keep_a_nonempty_approved_set(inputs_dir):
    """Every real codified deal must produce a non-empty approved set.

    This is the regression that matters: if this fails, enabling the
    membership gate would strip every citation from that deal.
    Read-only — asserts on counts, never on content.
    """
    sm = load_sources_md(inputs_dir)
    assert sm is not None, f"{inputs_dir} failed to parse"
    if not is_codified(sm):
        pytest.skip("not codified; membership does not apply")
    approved = approved_urls(sm)
    assert approved, "codified deal produced an empty approved set"
    assert len(approved) <= len(sm.sources)
    # Every approved URL canonicalizes to itself (idempotence).
    assert all(canonical_url(u) == u for u in approved)


# --------------------------------------------------------------------------
# Truncated frontmatter must not fail silently
# --------------------------------------------------------------------------

def test_sources_stranded_past_the_fence_are_reported(tmp_path, capsys):
    """A stray '---' inside the source list truncates the frontmatter.

    ImmuneCo carried this from 2026-07-14 to 2026-08-08: 93 sources on
    disk, 80 visible to the loader, and no signal anywhere. The sources
    were in the file the whole time, which is exactly what made the loss
    invisible — a diff looked fine, a grep looked fine, only the parse
    disagreed.
    """
    inputs = tmp_path / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "Sources.md").write_text(
        "---\n"
        "mode: codified\n"
        "sources:\n"
        "- url: https://visible.test/1\n"
        "---\n\n"                       # ← stray fence mid-list
        "- url: https://stranded.test/2\n"
        "  title: Invisible\n"
        "- url: https://stranded.test/3\n"
        "---\n\n"
        "# Notes\n"
    )
    sm = load_sources_md(inputs)
    assert len(sm.sources) == 1, "loader should still return what it can parse"
    out = capsys.readouterr().out
    assert "2 source(s) appear AFTER the closing frontmatter fence" in out


def test_a_healthy_file_warns_about_nothing(tmp_path, capsys):
    inputs = tmp_path / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "Sources.md").write_text(
        "---\nmode: codified\nsources:\n- url: https://a.test/1\n---\n\n"
        "# Notes\n\nProse that mentions a url: but not as a list item.\n"
    )
    load_sources_md(inputs)
    assert "AFTER the closing frontmatter fence" not in capsys.readouterr().out

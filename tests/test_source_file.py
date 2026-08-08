"""Tests for the per-source file writer.

Implements the schema in
`corpora-builder/context-v/blueprints/Source-File-Schema-Reconciliation.md`.
The three rulings that blueprint makes load-bearing each get a test:
fetched_at vs published_at, the two orthogonal lifecycle axes, and the
person/machine verdict split.

Everything writes under tmp_path. Real firm deals are never touched.
"""

from pathlib import Path

import pytest

from src.curation.source_file import (
    EXCERPT_CHARS,
    SourceFile,
    apply_fetch,
    from_entry,
    parse_jina_preamble,
    promote,
    read_source_file,
    reject,
    render,
    resolve_path,
    slugify,
    source_filename,
    sources_dir,
    to_frontmatter,
    write_source_file,
)
from src.curation.sources_md import SourceEntry


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("IEA-OES Annual Report", "iea-oes-annual-report"),
    ("State of Digital Health Q1'26", "state-of-digital-health-q1-26"),
    ("  Trailing & leading  ", "trailing-leading"),
    ("https://example.org/a/b", "example-org-a-b"),
    ("", "untitled"),
    ("!!!", "untitled"),
])
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_slug_truncates_on_a_word_boundary():
    """A slug cut mid-word reads like corruption."""
    s = slugify("alpha beta gamma delta epsilon zeta eta theta iota kappa", max_len=24)
    assert len(s) <= 24
    assert not s.endswith("-")
    assert s.split("-")[-1] in {"alpha","beta","gamma","delta","epsilon","zeta","eta","theta"}


def test_filename_grammar():
    assert source_filename("A Report", when="2026-06-27") == "2026-06-27_a-report.md"
    assert source_filename("A Report", when="2026-06-27", suffix=2) == "2026-06-27_a-report_2.md"


def test_filename_falls_back_to_url_when_untitled():
    assert "example-org" in source_filename("", "https://example.org/x", when="2026-01-01")


def test_datetime_when_is_truncated_to_a_date():
    assert source_filename("X", when="2026-06-27T14:31:00Z") == "2026-06-27_x.md"


# --------------------------------------------------------------------------
# Round-trip
# --------------------------------------------------------------------------

def test_round_trip_preserves_every_field(tmp_path):
    sf = SourceFile(
        url="https://example.org/report",
        title="A Real Report",
        publisher="Example Org",
        authors=["A. Author"],
        fetched_at="2026-06-27T14:31:00Z",
        published_at="2025-03-01",
        status="promoted",
        content_pulled=True,
        excerpt="Installed capacity reached…",
        description="Annual stocktake.",
        origin="searxng",
        origin_detail={"search_query": "ocean energy", "engine": "google"},
        sections=["opportunity"],
        tags=["market"],
        rank=2,
        verdict="approved",
        machine_verdict="HTTP 200 (body verified)",
        confidence=88,
        note="primary",
        body="# Content\n\nBody text.",
    )
    path = write_source_file(tmp_path, sf)
    back = read_source_file(path)

    assert back is not None
    for f in ("url", "title", "publisher", "fetched_at", "published_at", "status",
              "content_pulled", "excerpt", "description", "origin", "sections",
              "tags", "rank", "verdict", "machine_verdict", "confidence", "note"):
        assert getattr(back, f) == getattr(sf, f), f"{f} did not survive"
    assert back.origin_detail["engine"] == "google"
    assert "Body text." in back.body


def test_normalized_url_is_derived(tmp_path):
    sf = SourceFile(url="https://www.Example.org/a/?utm_source=x")
    assert sf.normalized_url
    assert "utm_source" not in sf.normalized_url
    assert "www." not in sf.normalized_url


def test_only_url_is_required(tmp_path):
    path = write_source_file(tmp_path, SourceFile(url="https://example.org/bare"))
    back = read_source_file(path)
    assert back and back.url == "https://example.org/bare"


def test_empty_fields_are_omitted_but_lifecycle_is_always_written():
    fm = to_frontmatter(SourceFile(url="https://a.test"))
    assert "note" not in fm and "tags" not in fm, "empty fields should be dropped"
    # content_pulled: False is meaningful, not absent — a reader must never
    # have to infer which lifecycle axis is which.
    assert fm["content_pulled"] is False
    assert fm["status"] == "candidate"
    assert fm["url"]


def test_field_order_is_stable_not_alphabetical():
    keys = list(to_frontmatter(SourceFile(
        url="https://a.test", title="T", verdict="approved", rank=1,
    )))
    assert keys.index("url") < keys.index("title") < keys.index("verdict")


def test_read_returns_none_on_garbage(tmp_path):
    p = tmp_path / "junk.md"
    p.write_text("not a source file")
    assert read_source_file(p) is None
    assert read_source_file(tmp_path / "missing.md") is None


def test_read_rejects_frontmatter_without_a_url(tmp_path):
    p = tmp_path / "nourl.md"
    p.write_text("---\ntitle: No URL\n---\n\nbody\n")
    assert read_source_file(p) is None


# --------------------------------------------------------------------------
# Ruling 1 — fetched_at is not published_at
# --------------------------------------------------------------------------

def test_fetched_and_published_are_distinct(tmp_path):
    """Conflating them makes staleness unanswerable."""
    sf = SourceFile(
        url="https://example.org/old",
        fetched_at="2026-06-27T14:31:00Z",
        published_at="2019-01-15",
    )
    back = read_source_file(write_source_file(tmp_path, sf))
    assert back.fetched_at.startswith("2026")
    assert back.published_at.startswith("2019")


# --------------------------------------------------------------------------
# Ruling 2 — two orthogonal lifecycle axes
# --------------------------------------------------------------------------

def test_promote_is_a_decision_not_a_download():
    """promoted + content_pulled=False must be representable.

    status is where the analyst got to; content_pulled is what is on
    disk. One field cannot express both.
    """
    sf = promote(SourceFile(url="https://a.test"))
    assert sf.status == "promoted"
    assert sf.verdict == "approved"
    assert sf.content_pulled is False


def test_candidate_can_already_have_content():
    """The other diagonal: content cached before any decision."""
    sf = apply_fetch(
        SourceFile(url="https://a.test"),
        {"markdown": "full body here", "title": "T", "via": "jina"},
        full=True,
    )
    assert sf.content_pulled is True
    assert sf.status == "candidate"


def test_reject_keeps_the_file_and_the_reason():
    sf = reject(SourceFile(url="https://a.test"), "wrong entity")
    assert sf.status == "rejected"
    assert sf.verdict == "rejected"
    assert sf.verdict_reason == "wrong entity"


# --------------------------------------------------------------------------
# Ruling 3 — verdict is a person, machine_verdict is a machine
# --------------------------------------------------------------------------

def test_machine_verdict_never_becomes_an_approval():
    """The exact ImmuneCo case: 34 entries reading 'HTTP 200 (body verified)'.

    Reachability is not approval. Counting it as one is the category
    error the membership gate exists to correct.
    """
    sf = from_entry(SourceEntry(url="https://a.test", verdict="HTTP 200 (body verified)"))
    assert sf.verdict == "", "a validator result was promoted to an analyst approval"
    assert sf.machine_verdict == "HTTP 200 (body verified)"


@pytest.mark.parametrize("raw,verdict", [
    ("approved", "approved"),
    ("rejected", "rejected"),
    ("denied", "rejected"),
    ("excluded", "rejected"),
])
def test_analyst_verdicts_are_carried_across(raw, verdict):
    sf = from_entry(SourceEntry(url="https://a.test", verdict=raw))
    assert sf.verdict == verdict
    assert sf.machine_verdict == ""


def test_from_entry_carries_list_metadata():
    e = SourceEntry(
        url="https://a.test", sections=["market-context"], rank=3,
        sensitivity="internal_only", note="analyst note",
    )
    e.title, e.publisher, e.published_date = "T", "P", "2025-01-01"
    sf = from_entry(e, origin="searxng", origin_detail={"engine": "google"})
    assert sf.sections == ["market-context"]
    assert sf.rank == 3 and sf.sensitivity == "internal_only"
    assert sf.title == "T" and sf.publisher == "P" and sf.published_at == "2025-01-01"
    assert sf.origin == "searxng" and sf.origin_detail["engine"] == "google"


# --------------------------------------------------------------------------
# Two-tier fetch
# --------------------------------------------------------------------------

def test_candidate_tier_keeps_only_an_excerpt():
    """Never pay to store content for a source that may be rejected."""
    sf = apply_fetch(
        SourceFile(url="https://a.test"),
        {"markdown": "x" * 5000, "title": "T", "via": "jina"},
        full=False,
    )
    assert sf.body == ""
    assert sf.content_pulled is False
    assert 0 < len(sf.excerpt) <= EXCERPT_CHARS


def test_excerpt_is_whitespace_collapsed():
    sf = apply_fetch(SourceFile(url="https://a.test"),
                     {"markdown": "line one\n\n\nline   two"}, full=False)
    assert sf.excerpt == "line one line two"


def test_failed_fetch_is_a_noop():
    """A source with no content is still a valid, citable source."""
    sf = SourceFile(url="https://a.test", title="Kept")
    out = apply_fetch(sf, None, full=True)
    assert out.title == "Kept" and out.content_pulled is False


def test_fetch_does_not_overwrite_an_analyst_title():
    sf = apply_fetch(SourceFile(url="https://a.test", title="Analyst's title"),
                     {"markdown": "b", "title": "Scraped title"}, full=True)
    assert sf.title == "Analyst's title"


def test_fetch_records_its_provider():
    sf = apply_fetch(SourceFile(url="https://a.test"),
                     {"markdown": "b", "via": "jina"}, full=True)
    assert sf.extra_metadata["fetched_via"] == "jina"


# --------------------------------------------------------------------------
# Collisions and extract preservation
# --------------------------------------------------------------------------

def test_rewriting_the_same_source_reuses_its_file(tmp_path):
    """A promote must not orphan the candidate file it supersedes."""
    sf = SourceFile(url="https://example.org/a", title="Same Title",
                    fetched_at="2026-06-27T00:00:00Z")
    first = write_source_file(tmp_path, sf)
    second = write_source_file(tmp_path, promote(
        SourceFile(url="https://example.org/a", title="Same Title",
                   fetched_at="2026-06-27T00:00:00Z")))
    assert first == second
    assert len(list(sources_dir(tmp_path).glob("*.md"))) == 1
    assert read_source_file(second).status == "promoted"


def test_different_sources_with_the_same_slug_get_a_suffix(tmp_path):
    a = SourceFile(url="https://a.test/x", title="Same Title", fetched_at="2026-06-27T00:00:00Z")
    b = SourceFile(url="https://b.test/y", title="Same Title", fetched_at="2026-06-27T00:00:00Z")
    pa = write_source_file(tmp_path, a)
    pb = write_source_file(tmp_path, b)
    assert pa != pb
    assert pb.name.endswith("_1.md")
    assert len(list(sources_dir(tmp_path).glob("*.md"))) == 2


def test_hand_authored_extracts_survive_a_rewrite(tmp_path):
    """The one part of the file no machine can regenerate."""
    sf = SourceFile(url="https://example.org/a", title="T",
                    fetched_at="2026-06-27T00:00:00Z", body="Old content.")
    path = write_source_file(tmp_path, sf)

    # Analyst adds extracts by hand.
    path.write_text(path.read_text().rstrip()
                    + "\n\n# Extracts\n\n## Quotes\n\n:::quote\nSomething quotable.\n:::\n")

    # A re-fetch replaces the content.
    write_source_file(tmp_path, SourceFile(
        url="https://example.org/a", title="T",
        fetched_at="2026-06-27T00:00:00Z", body="Fresh content."))

    body = read_source_file(path).body
    assert "Something quotable." in body, "extracts were destroyed by a rewrite"
    assert "Fresh content." in body
    assert "Old content." not in body


def test_incoming_extracts_are_not_duplicated(tmp_path):
    sf = SourceFile(url="https://example.org/a", title="T", fetched_at="2026-06-27T00:00:00Z",
                    body="c\n\n# Extracts\n\n## Quotes\n\n:::quote\nA\n:::")
    write_source_file(tmp_path, sf)
    write_source_file(tmp_path, SourceFile(
        url="https://example.org/a", title="T", fetched_at="2026-06-27T00:00:00Z",
        body="c2\n\n# Extracts\n\n## Quotes\n\n:::quote\nB\n:::"))
    body = read_source_file(resolve_path(tmp_path, sf)).body
    assert body.count("# Extracts") == 1


def test_extracts_are_never_written_into_yaml(tmp_path):
    """Quote punctuation breaks YAML — that is why extracts live in the body."""
    sf = SourceFile(url="https://example.org/a", title="T",
                    body='# Extracts\n\n:::quote\nHe said: "40% — $2.1B [sic]"\n:::')
    text = write_source_file(tmp_path, sf).read_text()
    fm = text.split("---")[1]
    assert "40%" not in fm and "sic" not in fm
    assert '"40% — $2.1B [sic]"' in text
    assert read_source_file(resolve_path(tmp_path, sf)) is not None, "file no longer parses"


def test_render_without_a_body_is_still_valid(tmp_path):
    text = render(SourceFile(url="https://a.test"))
    assert text.startswith("---\n") and text.rstrip().endswith("---")


# --------------------------------------------------------------------------
# Jina preamble — metadata, not content
# --------------------------------------------------------------------------

JINA = (
    "Title: Vector database\n\n"
    "URL Source: https://en.wikipedia.org/wiki/Vector_database\n\n"
    "Published Time: 2023-06-12T20:54:51Z\n\n"
    "Markdown Content:\n"
    "From Wikipedia, the free encyclopedia. A **vector database** stores vectors."
)


def test_preamble_is_split_from_the_body():
    headers, body = parse_jina_preamble(JINA)
    assert headers["Title"] == "Vector database"
    assert headers["Published Time"] == "2023-06-12T20:54:51Z"
    assert body.startswith("From Wikipedia")
    assert "URL Source" not in body


def test_published_at_is_lifted_from_the_preamble():
    """The one authoritative signal for when the source was written."""
    sf = apply_fetch(SourceFile(url="https://x.test"),
                     {"markdown": JINA, "via": "jina"}, full=True)
    assert sf.published_at == "2023-06-12"
    assert sf.fetched_at and not sf.fetched_at.startswith("2023"), \
        "fetched_at must not be overwritten by the source's own date"


def test_excerpt_comes_from_the_body_not_the_preamble():
    sf = apply_fetch(SourceFile(url="https://x.test"),
                     {"markdown": JINA, "via": "jina"}, full=False)
    assert sf.excerpt.startswith("From Wikipedia")
    for noise in ("Title:", "URL Source:", "Markdown Content:"):
        assert noise not in sf.excerpt


def test_body_excludes_the_preamble():
    sf = apply_fetch(SourceFile(url="https://x.test"),
                     {"markdown": JINA}, full=True)
    assert "URL Source:" not in sf.body
    assert "vector database" in sf.body


def test_analyst_published_date_wins_over_the_preamble():
    sf = apply_fetch(SourceFile(url="https://x.test", published_at="2020-01-01"),
                     {"markdown": JINA}, full=True)
    assert sf.published_at == "2020-01-01"


def test_plain_markdown_without_a_preamble_is_untouched():
    plain = "# A heading\n\nSome content."
    headers, body = parse_jina_preamble(plain)
    assert headers == {} and body == plain


def test_markdown_content_deep_in_an_article_is_not_a_preamble():
    """The phrase can legitimately appear in prose — only a header block counts."""
    text = "x" * 700 + "\nMarkdown Content: is a phrase about formats."
    headers, body = parse_jina_preamble(text)
    assert headers == {} and body == text

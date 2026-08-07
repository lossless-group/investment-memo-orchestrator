"""Tests for LLM-free candidate discovery (loop ticket 5).

The load-bearing assertion is the last one: no language-model client may
appear anywhere in this module's import graph. Everything else is about
keeping the analyst's list short enough to actually work through.

Network is mocked throughout — no live SearXNG required.
"""

import sys
from pathlib import Path

import pytest

from src.curation import candidates as C

REPO_ROOT = Path(__file__).resolve().parent.parent


def _payload(*urls):
    return {
        "results": [
            {
                "url": u,
                "title": f"Title for {u}",
                "content": "snippet",
                "score": 1.0,
                "publishedDate": "2026-01-01",
            }
            for u in urls
        ]
    }


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


@pytest.fixture
def searx(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(params["q"])
        return _Resp(_payload(
            f"https://a.test/{len(calls)}",
            f"https://b.test/{len(calls)}",
            f"https://c.test/{len(calls)}",
        ))

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


# --------------------------------------------------------------------------
# Availability / graceful degradation
# --------------------------------------------------------------------------

def test_unset_searxng_url_degrades_gracefully(monkeypatch):
    """A missing search backend must not break the curation surface."""
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    assert not C.is_available()
    out = C.gather_candidates(["anything"])
    assert out["available"] is False
    assert "SEARXNG_URL" in out["reason"]
    assert out["candidates"] == []


def test_search_failure_returns_empty_not_raise(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", boom)
    assert C.search_one("q") == []


def test_trailing_slash_is_stripped(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080/")
    assert C.searxng_base_url() == "http://localhost:8080"


# --------------------------------------------------------------------------
# Term derivation — no invention
# --------------------------------------------------------------------------

def test_terms_derive_from_real_fields_only():
    state = {"company_name": "Panthalassa", "stage": "Series B"}
    deck = {"tagline": "Wave energy conversion for utility grids"}
    terms = C.derive_terms(state, deck)
    assert "Panthalassa" in terms
    assert any("Series B" in t for t in terms)
    assert any("competitors" in t for t in terms)
    # The market term comes from the deck's own words.
    assert any("wave" in t.lower() for t in terms)


def test_no_company_no_invented_terms():
    """With nothing real to work from, emit nothing — never guess."""
    assert C.derive_terms({}, {}) == []


def test_terms_are_deduped_and_capped():
    state = {"company_name": "X", "stage": ""}
    terms = C.derive_terms(state, {}, max_terms=2)
    assert len(terms) <= 2
    assert len(terms) == len(set(t.lower() for t in terms))


def test_stopwords_do_not_reach_the_market_term():
    deck = {"tagline": "The platform for the future of company solutions"}
    terms = C.derive_terms({"company_name": "Acme"}, deck)
    market = [t for t in terms if "acme" not in t.lower()]
    for t in market:
        assert " the " not in f" {t} "
        assert "platform" not in t


# --------------------------------------------------------------------------
# Volume control — the originating complaint
# --------------------------------------------------------------------------

def test_global_cap_is_enforced(searx):
    """'Going through them takes forever' is the defect. Cap hard."""
    out = C.gather_candidates(["a", "b", "c", "d", "e"], max_per_term=3, max_total=5)
    assert len(out["candidates"]) == 5
    assert out["truncated"] is True


def test_per_term_cap_is_enforced(searx):
    out = C.gather_candidates(["a"], max_per_term=2, max_total=99)
    assert len(out["candidates"]) == 2


def test_duplicates_are_collapsed(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")
    import httpx
    # Same URL in three cosmetic variants across two queries.
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(_payload(
        "https://dup.test/x",
        "https://www.dup.test/x/",
        "http://dup.test/x?utm_source=news",
    )))
    out = C.gather_candidates(["a", "b"], max_per_term=5, max_total=99)
    assert len(out["candidates"]) == 1, "canonical duplicates were not collapsed"


def test_known_urls_are_flagged_not_dropped(monkeypatch):
    """Hiding what you already have looks like a search failure."""
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp(_payload(
        "https://known.test/a", "https://new.test/b",
    )))
    from src.curation.best_sources import canonical_url
    out = C.gather_candidates(
        ["q"], known_urls={canonical_url("https://known.test/a")}
    )
    by_url = {c["url"]: c for c in out["candidates"]}
    assert by_url["https://known.test/a"]["known"] is True
    assert by_url["https://new.test/b"]["known"] is False


# --------------------------------------------------------------------------
# Wire shape
# --------------------------------------------------------------------------

def test_result_matches_connector_result_shape(searx):
    out = C.gather_candidates(["q"], max_per_term=1)
    c = out["candidates"][0]
    assert set(c) >= {"url", "title", "content", "score", "published_date", "known"}


def test_non_http_results_are_dropped(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp({
        "results": [
            {"url": "javascript:alert(1)", "title": "bad"},
            {"url": "", "title": "empty"},
            {"url": "https://ok.test/a", "title": "good"},
        ]
    }))
    out = C.gather_candidates(["q"])
    assert [c["url"] for c in out["candidates"]] == ["https://ok.test/a"]


def test_provenance_is_recorded(searx):
    """The analyst should be able to see which query surfaced a result."""
    out = C.gather_candidates(["wave energy"], max_per_term=1)
    assert out["candidates"][0]["found_via"] == "wave energy"


# --------------------------------------------------------------------------
# The governing constraint
# --------------------------------------------------------------------------

def test_no_llm_client_in_the_candidate_path():
    """No language model may sit in the candidate path.

    This is the whole point of the module: a URL from a search index
    cannot be hallucinated. If an LLM SDK ever gets imported here, that
    guarantee is gone — so the import graph is asserted, not assumed.
    """
    source = (REPO_ROOT / "src" / "curation" / "candidates.py").read_text()
    banned = ["anthropic", "openai", "perplexity", "sonar", "langchain", "ChatAnthropic"]
    lowered = source.lower()
    for token in banned:
        # Allow the words in prose/comments; forbid them in import statements.
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert token.lower() not in stripped.lower(), (
                    f"LLM dependency '{token}' imported into the candidate path: {stripped}"
                )

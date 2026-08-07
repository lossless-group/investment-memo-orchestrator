"""Endpoint tests for the source-approval surface (loop ticket 6).

Drives the real FastAPI app through TestClient. All filesystem work is
redirected into tmp_path via the io-root — no firm-private data is read
or written.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.server.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App wired to a throwaway io root."""
    io_root = tmp_path / "io"
    (io_root / "test-firm" / "deals" / "TestCo" / "inputs").mkdir(parents=True)
    monkeypatch.setattr("src.paths.get_io_root", lambda: io_root, raising=False)
    monkeypatch.setattr(
        "src.server.sources_api.get_io_root", lambda: io_root, raising=False
    )
    with TestClient(app) as c:
        c.io_root = io_root
        yield c


def _inputs(client) -> Path:
    return client.io_root / "test-firm" / "deals" / "TestCo" / "inputs"


# --------------------------------------------------------------------------- #
# Read / write                                                                 #
# --------------------------------------------------------------------------- #

def test_get_sources_on_fresh_deal(client):
    """A deal with no Sources.md must return an empty shell, not a 404."""
    r = client.get("/firms/test-firm/deals/TestCo/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is False
    assert body["sources"] == []


def test_save_then_get_round_trip(client):
    payload = {
        "meta": {"deal": "TestCo", "firm": "test-firm"},
        "sources": [
            {
                "url": "https://example.org/a",
                "title": "A Real Report",
                "publisher": "Example Org",
                "sections": ["market-context"],
                "rank": 1,
                "verdict": "approved",
            }
        ],
        "body": "## How built\n\nHand-picked.\n",
        "mode": "codified",
    }
    r = client.post("/firms/test-firm/deals/TestCo/sources", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1

    r = client.get("/firms/test-firm/deals/TestCo/sources")
    body = r.json()
    assert body["exists"] is True
    assert body["mode"] == "codified"
    src = body["sources"][0]
    assert src["title"] == "A Real Report"
    assert src["verdict"] == "approved"
    assert "How built" in body["body"], "analyst prose body was lost"


def test_save_backs_up_the_previous_file(client):
    """Overwriting an analyst's work with no undo is the one
    unrecoverable failure this surface could have."""
    payload = {"meta": {}, "sources": [{"url": "https://a.test/1"}], "body": "v1"}
    client.post("/firms/test-firm/deals/TestCo/sources", json=payload)
    payload["body"] = "v2"
    r = client.post("/firms/test-firm/deals/TestCo/sources", json=payload)
    assert r.json()["backup"] is not None
    assert list(_inputs(client).glob("Sources.md.bak-*")), "no backup written"


def test_traversal_in_firm_or_deal_is_rejected(client):
    for bad in ("../etc", "a/b", "..\\x"):
        r = client.get(f"/firms/{bad}/deals/TestCo/sources")
        assert r.status_code in (400, 404), f"{bad} was not rejected"


# --------------------------------------------------------------------------- #
# Candidate search                                                             #
# --------------------------------------------------------------------------- #

def test_search_degrades_when_searxng_unset(client, monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    r = client.post("/actions/search-sources", json={"query": "wave energy"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "SEARXNG_URL" in body["reason"]


def test_search_returns_normalized_results(client, monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8080")

    class _Resp:
        def raise_for_status(self): return None
        def json(self):
            return {"results": [
                {"url": "https://a.test/1", "title": "T1", "content": "c1"},
                {"url": "https://b.test/2", "title": "T2", "content": "c2"},
            ]}

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())

    r = client.post("/actions/search-sources", json={"query": "q", "max_per_term": 5})
    body = r.json()
    assert body["available"] is True
    assert len(body["candidates"]) == 2
    assert set(body["candidates"][0]) >= {"url", "title", "content", "known"}


def test_search_requires_some_input(client):
    assert client.post("/actions/search-sources", json={}).status_code == 400


# --------------------------------------------------------------------------- #
# Preview + recovery                                                           #
# --------------------------------------------------------------------------- #

def test_fetch_rejects_non_http(client):
    r = client.post("/actions/fetch-source", json={"url": "javascript:alert(1)"})
    assert r.status_code == 400


def test_fetch_maps_the_real_return_shape(client, monkeypatch):
    monkeypatch.setattr(
        "src.curation.fetch_url_markdown",
        lambda url, **k: {"url": url, "title": "T", "markdown": "# Body", "via": "jina"},
        raising=False,
    )
    r = client.post("/actions/fetch-source", json={"url": "https://a.test/1"})
    body = r.json()
    assert body["ok"] is True
    assert body["title"] == "T"
    assert body["via"] == "jina"
    assert body["markdown"] == "# Body"


def test_fetch_handles_none_result(client, monkeypatch):
    monkeypatch.setattr(
        "src.curation.fetch_url_markdown", lambda url, **k: None, raising=False
    )
    r = client.post("/actions/fetch-source", json={"url": "https://a.test/1"})
    assert r.json()["ok"] is False


def test_recover_requires_a_title(client):
    """Recovery is title-driven — attempt_url_recovery no-ops without one."""
    r = client.post("/actions/recover-source", json={"title": "", "url": "https://a.test"})
    body = r.json()
    assert body["ok"] is False
    assert "title" in body["reason"]


def test_recover_reports_missing_tavily_key(client, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    r = client.post("/actions/recover-source", json={"title": "A Real Report"})
    body = r.json()
    assert body["ok"] is False
    assert "TAVILY_API_KEY" in body["reason"]


def test_recover_surfaces_the_full_recovery_result(client, monkeypatch):
    """The analyst is accepting a URL swap — they need the evidence."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    from src.validation.url_recovery import RecoveryResult

    monkeypatch.setattr(
        "src.validation.url_recovery.attempt_url_recovery",
        lambda md, **k: RecoveryResult(
            recovered_url="https://real.test/moved",
            matched_title="A Real Report",
            claimed_title="A Real Report",
            jaccard=0.92,
            via_query="A Real Report",
            via_provider="tavily",
        ),
        raising=False,
    )
    r = client.post("/actions/recover-source", json={
        "title": "A Real Report", "url": "https://dead.test/old",
    })
    body = r.json()
    assert body["ok"] is True
    assert body["recovered_url"] == "https://real.test/moved"
    assert body["jaccard"] == 0.92
    assert body["matched_title"] == "A Real Report"


# --------------------------------------------------------------------------- #
# The approval gate                                                            #
# --------------------------------------------------------------------------- #

def test_approve_writes_codified_mode(client):
    r = client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [
            {"url": "https://a.test/1", "title": "Keep"},
            {"url": "https://b.test/2", "title": "Drop", "verdict": "rejected"},
        ],
        "body": "notes",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "codified"
    assert body["approved_count"] == 1
    assert body["rejected_count"] == 1

    # The written file must be codified and loadable by the enforcement path.
    from src.curation import approved_urls, is_codified, load_sources_md
    sm = load_sources_md(_inputs(client))
    assert is_codified(sm)
    approved = approved_urls(sm)
    assert len(approved) == 1, "rejected source leaked into the approved set"


def test_approve_keeps_rejections_on_disk(client):
    """Rejections are institutional memory — don't make the analyst
    re-review what they already turned down."""
    client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [
            {"url": "https://a.test/1"},
            {"url": "https://b.test/2", "verdict": "rejected",
             "verdict_reason": "wrong-entity"},
        ],
    })
    text = (_inputs(client) / "Sources.md").read_text()
    assert "b.test/2" in text
    assert "wrong-entity" in text


def test_approve_refuses_an_empty_set(client):
    """An all-rejected set would strip every citation from the run."""
    r = client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [{"url": "https://a.test/1", "verdict": "rejected"}],
    })
    assert r.status_code == 400

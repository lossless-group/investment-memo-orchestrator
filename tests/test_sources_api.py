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


# --------------------------------------------------------------------------- #
# Persisting what we fetch (the gap this closes)                               #
# --------------------------------------------------------------------------- #

def test_preview_persists_content_when_the_deal_is_known(client, monkeypatch):
    """Before this, preview content was rendered once and discarded."""
    monkeypatch.setattr(
        "src.curation.fetch_url_markdown",
        lambda url, **k: {"url": url, "title": "Fetched Title",
                          "markdown": "# Real content\n\nBody.", "via": "jina"},
        raising=False,
    )
    r = client.post("/actions/fetch-source", json={
        "url": "https://example.org/a", "firm": "test-firm", "deal": "TestCo",
    })
    body = r.json()
    assert body["ok"] is True
    assert body["saved_to"], "content was fetched and thrown away"

    from src.curation.source_file import read_source_file
    sf = read_source_file(Path(body["saved_to"]))
    assert sf.content_pulled is True
    assert "Real content" in sf.body
    assert sf.excerpt


def test_preview_without_a_deal_does_not_persist(client, monkeypatch):
    """No deal context, nowhere to file it — still returns the preview."""
    monkeypatch.setattr(
        "src.curation.fetch_url_markdown",
        lambda url, **k: {"url": url, "title": "T", "markdown": "body", "via": "jina"},
        raising=False,
    )
    r = client.post("/actions/fetch-source", json={"url": "https://example.org/a"})
    assert r.json()["ok"] is True
    assert r.json()["saved_to"] is None


def test_preview_does_not_downgrade_an_approved_source(client, monkeypatch):
    """Re-previewing must not silently revert a decision."""
    client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [{"url": "https://example.org/a", "title": "T", "verdict": "approved"}],
    })
    monkeypatch.setattr(
        "src.curation.fetch_url_markdown",
        lambda url, **k: {"url": url, "title": "T", "markdown": "new body", "via": "jina"},
        raising=False,
    )
    r = client.post("/actions/fetch-source", json={
        "url": "https://example.org/a", "firm": "test-firm", "deal": "TestCo", "title": "T",
    })
    from src.curation.source_file import read_source_file
    sf = read_source_file(Path(r.json()["saved_to"]))
    assert sf.status == "promoted" and sf.verdict == "approved"
    assert "new body" in sf.body


def test_approve_mirrors_the_decision_into_source_files(client):
    r = client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [
            {"url": "https://a.test/1", "title": "Keep"},
            {"url": "https://b.test/2", "title": "Drop", "verdict": "rejected",
             "verdict_reason": "wrong entity"},
        ],
    })
    assert r.json()["source_files_written"] == 2

    from src.curation.source_file import read_source_file, sources_dir
    files = {p.name: read_source_file(p) for p in sources_dir(_inputs(client)).glob("*.md")}
    by_status = {sf.status: sf for sf in files.values()}
    assert "promoted" in by_status and "rejected" in by_status
    assert by_status["rejected"].verdict_reason == "wrong entity", \
        "rejections must keep their reason — that is the institutional memory"


def test_approve_keeps_content_a_preview_already_fetched(client, monkeypatch):
    """Approving is a decision write, not a content write."""
    monkeypatch.setattr(
        "src.curation.fetch_url_markdown",
        lambda url, **k: {"url": url, "title": "T", "markdown": "expensive body", "via": "jina"},
        raising=False,
    )
    client.post("/actions/fetch-source", json={
        "url": "https://a.test/1", "firm": "test-firm", "deal": "TestCo", "title": "T",
    })
    client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [{"url": "https://a.test/1", "title": "T", "verdict": "approved"}],
    })

    from src.curation.source_file import read_source_file, sources_dir
    sf = next(read_source_file(p) for p in sources_dir(_inputs(client)).glob("*.md"))
    assert sf.status == "promoted"
    assert "expensive body" in sf.body, "approve discarded content we already paid for"
    assert sf.content_pulled is True


def test_machine_verdict_rides_along_but_is_not_what_granted_approval(client):
    """Committing the set is the approval; the validator result is context.

    The file must not contradict the list — the gate will let this source
    be cited, so filing it as an unreviewed candidate would be a lie. But
    the reachability string stays in its own field, never as the reason.
    """
    client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [{"url": "https://a.test/1", "title": "T",
                     "verdict": "HTTP 200 (body verified)"}],
    })
    from src.curation.source_file import read_source_file, sources_dir
    sf = next(read_source_file(p) for p in sources_dir(_inputs(client)).glob("*.md"))
    assert sf.status == "promoted"
    assert sf.verdict == "approved"
    assert sf.machine_verdict == "HTTP 200 (body verified)"


def test_the_file_never_contradicts_the_list(client):
    """Whatever the gate would allow, the files must agree with."""
    client.post("/actions/approve-sources", json={
        "firm": "test-firm", "deal": "TestCo",
        "sources": [
            {"url": "https://a.test/1", "title": "no verdict"},
            {"url": "https://a.test/2", "title": "explicit", "verdict": "approved"},
            {"url": "https://a.test/3", "title": "machine", "verdict": "timeout"},
            {"url": "https://a.test/4", "title": "denied", "verdict": "rejected"},
        ],
    })
    from src.curation import approved_urls, load_sources_md
    from src.curation.source_file import read_source_file, sources_dir

    gate_allows = approved_urls(load_sources_md(_inputs(client)))
    files = [read_source_file(p) for p in sources_dir(_inputs(client)).glob("*.md")]
    promoted = {f.url for f in files if f.status == "promoted"}

    from src.curation import canonical_url
    assert {canonical_url(u) for u in promoted} == gate_allows


# --------------------------------------------------------------------------- #
# Autosave — 80 sources is not one sitting                                     #
# --------------------------------------------------------------------------- #

def _save(client, autosave: bool, verdict: str = ""):
    return client.post("/firms/test-firm/deals/TestCo/sources", json={
        "meta": {}, "body": "", "mode": "aggregated", "autosave": autosave,
        "sources": [{"url": "https://a.test/1", "title": "A", "verdict": verdict}],
    })


def test_autosave_backs_up_once_not_every_time(client):
    """Autosave fires every few seconds; a backup per write would bury
    the deal directory in .bak- files within a single session."""
    import src.server.sources_api as sa
    sa._AUTOSAVE_BACKED_UP.clear()

    _save(client, autosave=False)                 # create the file
    before = len(list(_inputs(client).glob("Sources.md.bak-*")))

    for i in range(6):
        _save(client, autosave=True, verdict="approved")

    after = len(list(_inputs(client).glob("Sources.md.bak-*")))
    assert after - before == 1, f"expected exactly one autosave backup, got {after - before}"


def test_a_manual_checkpoint_always_backs_up(client):
    import src.server.sources_api as sa
    sa._AUTOSAVE_BACKED_UP.clear()
    _save(client, autosave=False)
    _save(client, autosave=True)                  # consumes the one autosave backup
    r = _save(client, autosave=False)             # deliberate checkpoint
    assert r.json()["backup"] is not None, "an explicit checkpoint must be recoverable"


def test_autosave_persists_verdicts(client):
    """The whole point: close the window mid-session, come back to your work."""
    import src.server.sources_api as sa
    sa._AUTOSAVE_BACKED_UP.clear()
    _save(client, autosave=True, verdict="approved")

    got = client.get("/firms/test-firm/deals/TestCo/sources").json()
    assert got["sources"][0]["verdict"] == "approved"
    assert got["mode"] == "aggregated", "an autosave must not silently codify the deal"


def test_autosave_reports_when_it_saved(client):
    r = _save(client, autosave=True)
    body = r.json()
    assert body["autosave"] is True
    assert body["saved_at"], "the UI needs a timestamp to show 'saved Ns ago'"


# --------------------------------------------------------------------------- #
# Metadata on paste (Pasted-Link-Shows-Host-Instead-Of-Title)                  #
# --------------------------------------------------------------------------- #

A16Z = (
    "Title: GMV Retention: The Marketplace Metric Most Ignore\n\n"
    "URL Source: https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/\n\n"
    "Published Time: 2022-04-28T03:20:24+00:00\n\n"
    "Markdown Content:\n"
    "Imagine you're running a marketplace startup — let's call it ACo."
)


@pytest.fixture
def a16z(monkeypatch):
    monkeypatch.setattr(
        "src.curation.fetch_url_markdown",
        lambda url, **k: {"url": url, "title": "GMV Retention: The Marketplace Metric Most Ignore",
                          "markdown": A16Z, "via": "jina"},
        raising=False,
    )


def test_fetch_returns_structured_metadata_not_a_raw_blob(client, a16z):
    """The row needs a title and a date, not a string to re-parse."""
    r = client.post("/actions/fetch-source", json={
        "url": "https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/",
    })
    b = r.json()
    assert b["title"] == "GMV Retention: The Marketplace Metric Most Ignore"
    assert b["published_at"] == "2022-04-28"
    assert b["excerpt"].startswith("Imagine you're running")


def test_preview_body_has_no_jina_header(client, a16z):
    """The pane's job is 'is this real content', not 'here are four
    lines of machine header'."""
    r = client.post("/actions/fetch-source", json={
        "url": "https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/",
    })
    md = r.json()["markdown"]
    assert md.startswith("Imagine you're running")
    for noise in ("Title:", "URL Source:", "Published Time:", "Markdown Content:"):
        assert noise not in md


def test_metadata_only_writes_a_candidate_with_no_body(client, a16z):
    """The cheap tier: enough to name the row, without storing content
    for a source that may be rejected."""
    r = client.post("/actions/fetch-source", json={
        "url": "https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/",
        "firm": "test-firm", "deal": "TestCo", "metadata_only": True,
    })
    from src.curation.source_file import read_source_file
    sf = read_source_file(Path(r.json()["saved_to"]))
    assert sf.status == "candidate"
    assert sf.content_pulled is False
    assert sf.body == "", "the cheap tier must not store the body"
    assert sf.excerpt and sf.title and sf.published_at == "2022-04-28"


def test_paste_then_approve_files_under_a_title_slug(client, a16z):
    """Untitled rows file as `…_a16z-com-gmv-retention….md`. With
    metadata the filename is readable — and re-search, which needs a
    title, starts working."""
    r = client.post("/actions/fetch-source", json={
        "url": "https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/",
        "firm": "test-firm", "deal": "TestCo", "metadata_only": True,
    })
    name = Path(r.json()["saved_to"]).name
    assert "gmv-retention" in name
    assert "a16z-com" not in name


def test_a_preview_after_the_cheap_tier_adds_the_body(client, a16z):
    """Promote is what pays for content; the candidate file gets upgraded
    in place rather than orphaned."""
    first = client.post("/actions/fetch-source", json={
        "url": "https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/",
        "firm": "test-firm", "deal": "TestCo", "metadata_only": True,
    }).json()["saved_to"]
    second = client.post("/actions/fetch-source", json={
        "url": "https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/",
        "firm": "test-firm", "deal": "TestCo",
    }).json()["saved_to"]

    assert first == second, "the full fetch orphaned the candidate file"
    from src.curation.source_file import read_source_file
    sf = read_source_file(Path(second))
    assert sf.content_pulled is True and "Imagine you're running" in sf.body


def test_an_analyst_title_is_never_overwritten(client, a16z):
    r = client.post("/actions/fetch-source", json={
        "url": "https://a16z.com/gmv-retention-the-marketplace-metric-most-ignore/",
        "firm": "test-firm", "deal": "TestCo", "title": "a16z — GMV retention (my note)",
    })
    from src.curation.source_file import read_source_file
    assert read_source_file(Path(r.json()["saved_to"])).title == "a16z — GMV retention (my note)"


# --------------------------------------------------------------------------- #
# Regression: a save must never delete a field                                 #
# --------------------------------------------------------------------------- #

def test_save_preserves_fields_the_ui_does_not_model(client):
    """The bug that stripped `sensitivity` from 93 real ImmuneCo sources.

    The read path deliberately preserves hand-added keys; the write path
    must too, or every save is a quiet deletion.
    """
    client.post("/firms/test-firm/deals/TestCo/sources", json={
        "meta": {}, "body": "", "mode": "aggregated",
        "sources": [{
            "url": "https://a.test/1", "title": "T",
            "sensitivity": "internal_only",
            "confidence": 88,
            "analyst_custom_key": "do not delete me",
        }],
    })
    got = client.get("/firms/test-firm/deals/TestCo/sources").json()["sources"][0]
    assert got["sensitivity"] == "internal_only", "internal_only was downgraded"
    assert got["confidence"] == 88
    assert got["analyst_custom_key"] == "do not delete me"


def test_internal_only_survives_repeated_saves(client):
    """Autosave fires constantly — one lossy write would be enough."""
    payload = {
        "meta": {}, "body": "", "mode": "aggregated", "autosave": True,
        "sources": [{"url": "https://a.test/1", "title": "T",
                     "sensitivity": "internal_only"}],
    }
    for _ in range(5):
        client.post("/firms/test-firm/deals/TestCo/sources", json=payload)
        payload["sources"] = client.get(
            "/firms/test-firm/deals/TestCo/sources"
        ).json()["sources"]

    assert payload["sources"][0]["sensitivity"] == "internal_only"

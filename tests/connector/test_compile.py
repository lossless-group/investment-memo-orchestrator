"""compile (CONN-CMP-01 to CONN-CMP-04)."""

from __future__ import annotations

import re
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pytest

from src.connector.config import ConnectorSettings
from src.connector.errors import ConnectorError

from .conftest import SECTIONS, call, rest
from .fake_claude import Direct, FakeClaude
from .fixtures import canned

SEVEN_DAYS = 7 * 24 * 3600
ENHANCEMENTS = [
    "enhance.tables",
    "enhance.diagrams",
    "enhance.citations",
    "enhance.fact_check",
    "enhance.scorecard",
    "enhance.summaries",
    "enhance.one_pager",
]


def drafted(ws) -> str:
    """fixture-co with research approved and every section drafted, nothing enhanced."""
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, until=lambda s: s["phase"] == "enhance", compile=False)
    return deal


def _with_query(url: str, **changes) -> str:
    parts = urlsplit(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()} | changes
    return urlunsplit(parts._replace(query=urlencode(query)))


@pytest.mark.spec("CONN-CMP-01")
def test_compile_returns_working_html_and_pdf_links_and_a_report(ws, client, settings):
    deal = drafted(ws)
    started = time.time()
    body = call(ws, "compile", deal=deal)

    assert body["ok"] is True
    assert body["version"] == 1
    assert "job_id" not in body
    for key in ("html_url", "pdf_url"):
        url = body[key]
        assert url.startswith("https://"), url
        expires = int(parse_qs(urlsplit(url).query)["expires"][0])
        assert abs(expires - (started + SEVEN_DAYS)) < 120, "links must expire after seven days"

    page = client.get(body["html_url"])
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "Fixture Co" in page.text
    for name, _ in canned.SECTIONS.values():
        assert name in page.text
    pdf = client.get(body["pdf_url"])
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 5_000

    report = body["report"]
    assert [s["key"] for s in report["sections"]] == SECTIONS
    assert [s["name"] for s in report["sections"]] == ["Overview", "Market", "Team"]
    assert report["enhancements_run"] == []
    assert report["skipped"] == []
    assert report["not_run"] == ENHANCEMENTS

    # The exports are in the firm's bucket under compiled/, and the memo's
    # markdown is an artifact like any other.
    keys = ws.bucket.list("compiled/")
    assert any(k.endswith(".html") for k in keys) and any(k.endswith(".pdf") for k in keys)
    memo = call(ws, "get_artifact", deal=deal, artifact_id="compile.assemble")
    assert memo["version"] == 1 and "## Overview" in memo["text"]

    # A link that has been tampered with, or has expired, does not work.
    forged = _with_query(body["html_url"], signature="0" * 64)
    assert client.get(forged).status_code in (401, 403, 410)
    stale = _with_query(body["pdf_url"], expires=str(int(started) - 10))
    assert client.get(stale).status_code in (401, 403, 410)
    other = body["html_url"].replace("/test-firm/", "/other-firm/")
    assert client.get(other).status_code in (401, 403, 404, 410)

    # Compiling unchanged sections again makes no new version; fresh links.
    again = call(ws, "compile", deal=deal)
    assert again["version"] == 1
    assert client.get(again["html_url"]).status_code == 200
    html_only = call(ws, "compile", deal=deal, formats=["html"])
    assert html_only["pdf_url"] is None and html_only["html_url"]

    over_rest = rest(client, "compile", {"deal": deal})
    assert over_rest.status_code == 200
    assert over_rest.json()["version"] == 1


@pytest.mark.spec("CONN-CMP-02")
def test_compile_refuses_a_deal_with_a_section_not_drafted(ws, client):
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    walk = fake.walk(
        deal,
        until=lambda s: (s["step_id"], s["section"]) == ("draft.section", SECTIONS[2]),
        compile=False,
    )
    assert walk.stopped_at is not None

    with pytest.raises(ConnectorError) as raised:
        call(ws, "compile", deal=deal)
    err = raised.value
    assert (err.kind, err.code) == ("invalid", "drafts_incomplete")
    assert err.details["missing"] == [SECTIONS[2]]
    assert err.next
    assert not (ws.root / "deals" / deal / "compiled").exists()
    assert ws.bucket.list("compiled/") == []

    response = rest(client, "compile", {"deal": deal})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "drafts_incomplete"

    fresh = fake.create(company="Beta Labs", url="https://betalabs.io")
    with pytest.raises(ConnectorError) as raised:
        call(ws, "compile", deal=fresh)
    assert raised.value.details["missing"] == SECTIONS


@pytest.mark.spec("CONN-CMP-03")
def test_compile_past_its_time_budget_returns_a_job_that_list_deals_reports(
    ws, client, settings, monkeypatch
):
    from src.connector.compile import pipeline

    assert ConnectorSettings().compile_budget_seconds <= 240
    assert (
        ConnectorSettings.from_env({"MEMOPOP_COMPILE_BUDGET_SECONDS": "2.5"}).compile_budget_seconds
        == 2.5
    )
    deal = drafted(ws)
    settings.compile_budget_seconds = 0.2

    gate = threading.Event()
    original = pipeline.STAGE_IMPLS["compile.toc"]

    def slow(ctx):
        assert gate.wait(20), "the test never released the slow stage"
        return original(ctx)

    monkeypatch.setitem(pipeline.STAGE_IMPLS, "compile.toc", slow)
    try:
        body = call(ws, "compile", deal=deal)
        assert body["status"] == "running"
        job_id = body["job_id"]
        assert job_id
        assert "html_url" not in body

        # A second call while it runs returns the same job, not a second compile.
        assert call(ws, "compile", deal=deal)["job_id"] == job_id
        (listed,) = call(ws, "list_deals")["deals"]
        assert listed["compile"]["job_id"] == job_id
        assert listed["compile"]["status"] == "running"
    finally:
        gate.set()

    deadline = time.time() + 30
    while True:
        (listed,) = call(ws, "list_deals")["deals"]
        if listed["compile"]["status"] != "running" or time.time() > deadline:
            break
        time.sleep(0.1)
    job = listed["compile"]
    assert job["status"] == "done", job
    assert job["job_id"] == job_id
    assert job["version"] == 1
    page = client.get(job["html_url"])
    assert page.status_code == 200
    assert "Overview" in page.text
    assert client.get(job["pdf_url"]).content.startswith(b"%PDF")


def _numbers(text: str) -> list[str]:
    seen: list[str] = []
    for key in re.findall(r"\[\^([^\]\s]+)\](?!:)", text):
        if key not in seen:
            seen.append(key)
    return seen


@pytest.mark.spec("CONN-CMP-04")
def test_compiled_citations_are_consolidated_and_renumbered(ws, client):
    from src.agents.citation_assembly import consolidate_citations

    drafts = canned.conflicting_drafts()
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    walk = fake.walk(deal, until=lambda s: s["step_id"] == "draft.section", compile=False)
    step = walk.stopped_at
    for _ in SECTIONS:
        call(
            ws,
            "submit_artifact",
            deal=deal,
            step_id="draft.section",
            section=step["section"],
            content=drafts[step["section"]],
        )
        step = call(ws, "next_step", deal=deal)
    assert step["phase"] == "enhance"

    body = call(ws, "compile", deal=deal, formats=["html"])
    memo = call(ws, "get_artifact", deal=deal, artifact_id="compile.assemble")["text"]

    assert memo.count("### Citations") == 1
    body_text, _, block = memo.partition("### Citations")
    definitions = dict(re.findall(r"^\[\^(\d+)\]: (.+)$", block, re.MULTILINE))
    urls = {k: re.search(r"\((https?://[^)]+)\)", v).group(1) for k, v in definitions.items()}
    assert sorted(urls.values()) == sorted(set(canned.CONFLICTING_CLAIMS.values()))
    assert len(urls) == 4, "the same source cited by two sections is listed once"
    assert _numbers(body_text) == ["1", "2", "3", "4"], "renumbered by first appearance"
    assert list(definitions) == ["1", "2", "3", "4"]
    for claim, url in canned.CONFLICTING_CLAIMS.items():
        cited = re.search(re.escape(claim) + r"[^\[]*\[\^(\d+)\]", body_text)
        assert cited, claim
        assert urls[cited.group(1)] == url, f"{claim} now cites {urls[cited.group(1)]}"

    page = client.get(body["html_url"]).text
    assert page.count('class="footnotes') == 1

    # The pure function compile uses, reused from the existing citation agent.
    bodies, block2, stats = consolidate_citations([drafts[s] for s in SECTIONS])
    assert len(bodies) == 3 and stats["sources"] == 4 and stats["missing"] == []
    assert "### Citations" in block2
    assert all("[^" in b and "]: " not in b for b in bodies)

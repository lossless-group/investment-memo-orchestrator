"""Materials: add_materials, link fetching, the upload page, and extraction
(CONN-MAT-01 to CONN-MAT-07).

Every material is synthetic: inline strings, or PDFs generated in the test
(``fixtures/materials.py``). Links are served by an ``httpx.MockTransport``
patched into the fetcher, so no test touches the internet. Server modules are
imported inside the tests, so a missing implementation fails a test (RED)
instead of stopping collection.
"""

from __future__ import annotations

import importlib
import json
import threading
import time
from urllib.parse import urlparse

import httpx
import pytest

from src.connector.errors import ConnectorError

from .conftest import SECTIONS, call, deal_json, new_deal, rest
from .fixtures.materials import PAGE_MARKERS, large_pdf, two_page_pdf

NOTES = "Call notes: the synthetic founders met at a synthetic distributor in 2019."


# ------------------------------------------------------------------ helpers


class Links:
    """A fake internet: URL -> response (or a callable taking the request)."""

    def __init__(self) -> None:
        self.routes: dict[str, object] = {}
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        route = self.routes.get(url)
        if route is None:
            return httpx.Response(404, text="not found")
        if callable(route):
            return route(request)
        return route


@pytest.fixture
def links(monkeypatch) -> Links:
    fetch = importlib.import_module("src.connector.materials.fetch")
    fake = Links()
    monkeypatch.setattr(fetch, "TRANSPORT", httpx.MockTransport(fake.handler))
    return fake


def state_of(ws, deal: str) -> dict:
    return json.loads(deal_json(ws, deal).read_text())


def wait_for_materials(ws, deal: str, timeout: float = 60) -> dict:
    """Poll list_deals, as a client would, until no material is pending."""
    deadline = time.monotonic() + timeout
    while True:
        (row,) = [d for d in call(ws, "list_deals")["deals"] if d["deal"] == deal]
        if row["materials_pending"] == 0:
            return state_of(ws, deal)
        assert time.monotonic() < deadline, f"materials still pending: {row}"
        time.sleep(0.05)


def material(state: dict, material_id: str) -> dict:
    (record,) = [m for m in state["materials"] if m["material_id"] == material_id]
    return record


def extracted(ws, deal: str, material_id: str) -> str:
    return (ws.root / "deals" / deal / "materials" / f"{material_id}.md").read_text()


def bucket_keys(ws, prefix: str = "") -> list[str]:
    return ws.bucket.list(prefix)


def upload_path(upload_url: str) -> str:
    return urlparse(upload_url).path


# ------------------------------------------------------------------ CONN-MAT-01


@pytest.mark.spec("CONN-MAT-01")
def test_inline_text_is_stored_and_ready(ws):
    deal = new_deal(ws)
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "text": NOTES}])
    (accepted,) = body["accepted"]
    assert accepted["status"] == "ready"
    assert accepted["material_id"].startswith("mat-")
    assert "upload_url" not in body or body["upload_url"] is None

    mid = accepted["material_id"]
    assert NOTES in extracted(ws, deal, mid)
    record = material(state_of(ws, deal), mid)
    assert (record["kind"], record["status"]) == ("notes", "ready")

    read = call(ws, "get_artifact", deal=deal, material_id=mid)
    assert NOTES in read["text"]
    assert read["kind"] == "notes"
    (row,) = call(ws, "list_deals")["deals"]
    assert row["materials_pending"] == 0

    # Repeat-safe: the same text again is the same material, not a second one.
    again = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "text": NOTES}])
    assert again["accepted"] == body["accepted"]
    assert len(state_of(ws, deal)["materials"]) == 1


@pytest.mark.spec("CONN-MAT-01")
def test_inline_text_over_rest_and_mcp(client, mcp, ws):
    deal = new_deal(ws)
    over_rest = rest(
        client, "add_materials", {"deal": deal, "items": [{"kind": "notes", "text": NOTES}]}
    )
    assert over_rest.status_code == 200, over_rest.text
    assert over_rest.json()["accepted"][0]["status"] == "ready"
    over_mcp = mcp.call(
        "add_materials", {"deal": deal, "items": [{"kind": "notes", "text": NOTES}]}
    )
    assert over_mcp["structuredContent"] == over_rest.json()

    with pytest.raises(ConnectorError) as raised:
        call(ws, "add_materials", deal="no-such-deal", items=[{"kind": "notes", "text": NOTES}])
    assert raised.value.code == "deal_not_found"
    other = rest(
        client,
        "add_materials",
        {"deal": deal, "items": [{"kind": "notes", "text": NOTES}]},
        headers={"Authorization": "Bearer sk-other-firm-0e4b8d1f3c"},
    )
    assert other.status_code == 404
    assert other.json()["error"]["code"] == "deal_not_found"


# ------------------------------------------------------------------ CONN-MAT-02


@pytest.mark.spec("CONN-MAT-02")
def test_a_reachable_link_is_fetched_and_becomes_ready(ws, links):
    url = "https://files.example.test/call-notes.txt"
    links.routes[url] = httpx.Response(
        200, text=NOTES, headers={"content-type": "text/plain; charset=utf-8"}
    )
    deal = new_deal(ws)
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "link": url}])
    (accepted,) = body["accepted"]
    assert accepted["status"] in ("queued", "ready")

    state = wait_for_materials(ws, deal)
    assert material(state, accepted["material_id"])["status"] == "ready"
    assert NOTES in extracted(ws, deal, accepted["material_id"])
    assert url in links.requests
    assert state["skips"] == []


@pytest.mark.spec("CONN-MAT-02")
def test_an_unreachable_link_is_a_skip_and_the_deal_continues(ws, links):
    missing = "https://files.example.test/gone.pdf"  # 404 from the fake internet

    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    refused = "https://down.example.test/deck.pdf"
    links.routes[refused] = refuse

    deal = new_deal(ws)
    body = call(
        ws,
        "add_materials",
        deal=deal,
        items=[{"kind": "deck", "link": missing}, {"kind": "deck", "link": refused}],
    )
    ids = [a["material_id"] for a in body["accepted"]]
    assert len(set(ids)) == 2

    state = wait_for_materials(ws, deal)
    skips = [s for s in state["skips"] if s["code"] == "material_unreadable"]
    assert sorted(s["material_id"] for s in skips) == sorted(ids)
    assert all(s["reason"] for s in skips)
    for mid in ids:
        assert material(state, mid)["status"] != "ready"

    (row,) = call(ws, "list_deals")["deals"]
    assert row["materials_pending"] == 0
    assert [s["code"] for s in row["skips"]] == ["material_unreadable"] * 2

    # The deal continues: no material is ready, so research comes next, and the
    # skips are reported once.
    step = call(ws, "next_step", deal=deal)
    assert step["step_id"] == "research.section"
    assert step["section"] == SECTIONS[0]
    assert [s["code"] for s in step["skipped_since_last_call"]] == ["material_unreadable"] * 2
    assert call(ws, "next_step", deal=deal)["skipped_since_last_call"] == []


@pytest.mark.spec("CONN-MAT-02")
def test_share_links_are_rewritten_and_docsend_is_unreadable(ws, links):
    drive_direct = "https://drive.google.com/uc?export=download&id=FILE123abc"
    dropbox_direct = "https://www.dropbox.com/s/abc123/notes.txt?dl=1"
    links.routes[drive_direct] = httpx.Response(
        200, text="Drive notes, synthetic.", headers={"content-type": "text/plain"}
    )
    links.routes[dropbox_direct] = httpx.Response(
        200, text="Dropbox notes, synthetic.", headers={"content-type": "text/plain"}
    )
    deal = new_deal(ws)
    body = call(
        ws,
        "add_materials",
        deal=deal,
        items=[
            {
                "kind": "notes",
                "link": "https://drive.google.com/file/d/FILE123abc/view?usp=sharing",
            },
            {"kind": "notes", "link": "https://www.dropbox.com/s/abc123/notes.txt?dl=0"},
            {"kind": "deck", "link": "https://docsend.com/view/abcdef123"},
        ],
    )
    drive_id, dropbox_id, docsend_id = [a["material_id"] for a in body["accepted"]]
    state = wait_for_materials(ws, deal)

    assert drive_direct in links.requests
    assert dropbox_direct in links.requests
    assert not any("docsend.com" in u for u in links.requests)
    assert "Drive notes" in extracted(ws, deal, drive_id)
    assert "Dropbox notes" in extracted(ws, deal, dropbox_id)

    (skip,) = state["skips"]
    assert (skip["code"], skip["material_id"]) == ("material_unreadable", docsend_id)
    assert "DocSend" in skip["reason"]


# ------------------------------------------------------------------ CONN-MAT-03


@pytest.mark.spec("CONN-MAT-03")
def test_filename_only_gets_a_one_time_upload_page(ws, client):
    deal = new_deal(ws)
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "deck", "filename": "deck.pdf"}])
    (accepted,) = body["accepted"]
    assert accepted["status"] == "queued"
    assert body["upload_url"].startswith(f"{ws.settings.public_base_url}/upload/")
    assert body["upload_expires_at"]
    path = upload_path(body["upload_url"])

    # No sign-in needed beyond the token: no Authorization header anywhere below.
    page = client.get(path)
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "<form" in page.text and 'type="file"' in page.text
    assert "deck.pdf" in page.text

    pdf = two_page_pdf()
    first = client.post(path, files=[("files", ("deck.pdf", pdf, "application/pdf"))])
    assert first.status_code == 200, first.text

    state = wait_for_materials(ws, deal)
    assert material(state, accepted["material_id"])["status"] == "ready"
    text = extracted(ws, deal, accepted["material_id"])

    # A second use is refused, and changes nothing.
    second = client.post(path, files=[("files", ("deck.pdf", b"%PDF-other", "application/pdf"))])
    assert second.status_code == 410
    assert client.get(path).status_code == 410
    assert extracted(ws, deal, accepted["material_id"]) == text

    # A token nobody issued is refused.
    assert client.get("/upload/not-a-real-token").status_code == 404
    assert (
        client.post("/upload/not-a-real-token", files=[("files", ("x.txt", b"x"))]).status_code
        == 404
    )


@pytest.mark.spec("CONN-MAT-03")
def test_an_expired_upload_link_is_refused(ws, client, monkeypatch):
    uploads = importlib.import_module("src.connector.materials.uploads")
    deal = new_deal(ws)
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "filename": "notes.txt"}])
    path = upload_path(body["upload_url"])

    later = time.time() + 3601
    monkeypatch.setattr(uploads, "now", lambda: later)
    assert client.get(path).status_code == 410
    refused = client.post(path, files=[("files", ("notes.txt", b"late notes", "text/plain"))])
    assert refused.status_code == 410
    (accepted,) = body["accepted"]
    assert material(state_of(ws, deal), accepted["material_id"])["status"] != "ready"
    assert not (ws.root / "deals" / deal / "materials" / f"{accepted['material_id']}.md").exists()


# ------------------------------------------------------------------ CONN-MAT-04


@pytest.mark.spec("CONN-MAT-04")
def test_a_large_file_returns_at_once_and_extracts_in_the_background(ws, links, client):
    big = large_pdf()
    assert len(big) > 500_000
    release = threading.Event()

    def slow(request):
        release.wait(timeout=30)
        return httpx.Response(200, content=big, headers={"content-type": "application/pdf"})

    url = "https://files.example.test/big-deck.pdf"
    links.routes[url] = slow
    deal = new_deal(ws)

    started = time.monotonic()
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "deck", "link": url}])
    assert time.monotonic() - started < 5
    (accepted,) = body["accepted"]
    assert accepted["status"] == "queued"
    (row,) = call(ws, "list_deals")["deals"]
    assert row["materials_pending"] == 1

    release.set()
    state = wait_for_materials(ws, deal)
    assert material(state, accepted["material_id"])["status"] == "ready"
    assert "page 400" in extracted(ws, deal, accepted["material_id"])

    # The same holds for a large upload: the page answers before extraction ends.
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "deck", "filename": "big.pdf"}])
    started = time.monotonic()
    posted = client.post(
        upload_path(body["upload_url"]), files=[("files", ("big.pdf", big, "application/pdf"))]
    )
    assert posted.status_code == 200
    assert time.monotonic() - started < 5
    state = wait_for_materials(ws, deal)
    assert material(state, body["accepted"][0]["material_id"])["status"] == "ready"


# ------------------------------------------------------------------ CONN-MAT-05


@pytest.mark.spec("CONN-MAT-05")
def test_a_pdf_decks_text_is_extracted_and_its_original_kept(ws, client, links):
    pdf = two_page_pdf()
    deal = new_deal(ws)

    # Uploaded.
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "deck", "filename": "deck.pdf"}])
    client.post(
        upload_path(body["upload_url"]), files=[("files", ("deck.pdf", pdf, "application/pdf"))]
    )
    uploaded = body["accepted"][0]["material_id"]

    # Linked.
    url = "https://files.example.test/fixture-deck.pdf"
    links.routes[url] = httpx.Response(
        200, content=pdf, headers={"content-type": "application/pdf"}
    )
    linked = call(ws, "add_materials", deal=deal, items=[{"kind": "deck", "link": url}])
    linked_id = linked["accepted"][0]["material_id"]

    state = wait_for_materials(ws, deal)
    for mid in (uploaded, linked_id):
        assert material(state, mid)["status"] == "ready"
        text = extracted(ws, deal, mid)
        for marker in PAGE_MARKERS:
            assert marker in text, (mid, marker)
        keys = [k for k in bucket_keys(ws, "materials/") if f"/{mid}/" in f"/{k}"]
        assert keys, (mid, bucket_keys(ws))
        assert all(k.startswith("materials/") for k in keys)
        assert any(ws.bucket.get(k) == pdf for k in keys)

    # The text is in the workspace, not the bucket; the original is in the bucket only.
    assert not list((ws.root / "deals" / deal).rglob("*.pdf"))


# ------------------------------------------------------------------ CONN-MAT-06


@pytest.mark.spec("CONN-MAT-06")
def test_inline_text_over_the_cap_is_material_too_large(ws, client):
    deal = new_deal(ws)
    before = deal_json(ws, deal).read_bytes()
    too_long = "x" * 100_001
    with pytest.raises(ConnectorError) as raised:
        call(
            ws,
            "add_materials",
            deal=deal,
            items=[{"kind": "notes", "text": NOTES}, {"kind": "notes", "text": too_long}],
        )
    assert (raised.value.kind, raised.value.code) == ("invalid", "material_too_large")
    assert raised.value.next
    assert deal_json(ws, deal).read_bytes() == before
    assert not (ws.root / "deals" / deal / "materials").exists()

    over_rest = rest(
        client, "add_materials", {"deal": deal, "items": [{"kind": "notes", "text": too_long}]}
    )
    assert over_rest.status_code == 413
    assert over_rest.json()["error"]["code"] == "material_too_large"

    # Exactly at the cap is fine.
    ok = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "text": "y" * 100_000}])
    assert ok["accepted"][0]["status"] == "ready"


# ------------------------------------------------------------------ CONN-MAT-07


@pytest.mark.spec("CONN-MAT-07")
def test_ready_materials_bring_the_brief_before_research(ws):
    deal = new_deal(ws)
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "text": NOTES}])
    mid = body["accepted"][0]["material_id"]

    step = call(ws, "next_step", deal=deal)
    assert step["step_id"] == "materials.brief"
    assert step["phase"] == "materials"
    assert "{{" not in step["instruction"]
    assert "Fixture Co" in step["instruction"]
    assert "submit_artifact" in step["instruction"]
    assert [i["artifact_id"] for i in step["inputs"]] == [f"material:{mid}"]
    assert NOTES in step["inputs"][0]["text"]

    brief = (
        "## Materials brief\n\nThe notes say the founders met at a distributor in 2019. [^deck]\n"
    )
    saved = call(ws, "submit_artifact", deal=deal, step_id="materials.brief", content=brief)
    assert saved["advanced"] is True
    after = call(ws, "next_step", deal=deal)
    assert after["step_id"] == "research.section"
    assert after["section"] == SECTIONS[0]
    assert [i["artifact_id"] for i in after["inputs"]] == ["materials.brief"]

"""Materials edge cases that back the CONN-MAT tests: the private-address guard,
the download cap, share-link rewriting, unreadable files, and upload-page refusals.

Not spec IDs: these pin behaviour the plan asks for (timeouts, size cap, no
private hosts, never block) without a Given/When/Then of their own.
"""

from __future__ import annotations

import httpx
import pytest

from src.connector.errors import ConnectorError
from src.connector.materials import extract, fetch

from .conftest import call, new_deal
from .test_materials import Links, material, upload_path, wait_for_materials


@pytest.fixture
def net(monkeypatch) -> Links:
    """The same fake internet test_materials uses."""
    fake = Links()
    monkeypatch.setattr(fetch, "TRANSPORT", httpx.MockTransport(fake.handler))
    return fake


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.8", "192.168.1.1", "169.254.169.254", "::1", "0.0.0.0"]
)
def test_private_addresses_are_refused(address):
    assert not fetch.is_public_address(address)
    host = f"[{address}]" if ":" in address else address
    with pytest.raises(fetch.Unreadable, match="not a public address"):
        fetch.guard_request(httpx.Request("GET", f"http://{host}/latest/meta-data/"))


def test_public_addresses_pass_the_guard():
    assert fetch.is_public_address("93.184.216.34")
    fetch.guard_request(httpx.Request("GET", "http://93.184.216.34/deck.pdf"))


def test_the_real_client_guards_every_request():
    with fetch.client() as http:
        assert fetch.guard_request in http.event_hooks["request"]


def test_share_links_rewrite_to_direct_downloads():
    assert (
        fetch.direct_url("https://drive.google.com/open?id=abc_123")
        == "https://drive.google.com/uc?export=download&id=abc_123"
    )
    assert (
        fetch.direct_url("https://docs.google.com/presentation/d/XYZ/edit#slide=id.p")
        == "https://docs.google.com/presentation/d/XYZ/export/pdf"
    )
    assert (
        fetch.direct_url("https://docs.google.com/spreadsheets/d/S1/edit")
        == "https://docs.google.com/spreadsheets/d/S1/export?format=csv"
    )
    assert fetch.direct_url("https://dropbox.com/scl/fi/x/a.pdf?rlkey=k&dl=0").endswith(
        "?rlkey=k&dl=1"
    )
    assert fetch.direct_url("https://example.org/a.pdf") == "https://example.org/a.pdf"


def test_downloads_over_the_cap_are_unreadable(net):
    url = "https://files.example.test/huge.bin"
    net.routes[url] = httpx.Response(200, content=b"x" * 2048)
    with pytest.raises(fetch.Unreadable, match="larger than"):
        fetch.fetch(url, max_bytes=1024)


def test_timeouts_are_unreadable(net):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    net.routes["https://files.example.test/slow.pdf"] = slow
    with pytest.raises(fetch.Unreadable, match="too long"):
        fetch.fetch("https://files.example.test/slow.pdf")


def test_a_non_http_link_is_link_unreachable_and_saves_nothing(ws):
    deal = new_deal(ws)
    for link in ("file:///etc/passwd", "ftp://files.example.test/deck.pdf", "not a url"):
        with pytest.raises(ConnectorError) as raised:
            call(ws, "add_materials", deal=deal, items=[{"kind": "deck", "link": link}])
        assert raised.value.code == "link_unreachable", link
    assert call(ws, "list_deals")["deals"][0]["materials_pending"] == 0


def test_an_item_needs_exactly_one_source(ws):
    deal = new_deal(ws)
    for item in (
        {"kind": "notes"},
        {"kind": "notes", "text": "a", "link": "https://example.org/a"},
        {"kind": "notes", "text": "   "},
    ):
        with pytest.raises(ConnectorError) as raised:
            call(ws, "add_materials", deal=deal, items=[item])
        assert raised.value.code == "validation_failed", item


def test_an_unreadable_file_type_is_a_skip(ws, net):
    url = "https://files.example.test/photo.png"
    net.routes[url] = httpx.Response(
        200, content=b"\x89PNG\r\n\x1a\n...", headers={"content-type": "image/png"}
    )
    deal = new_deal(ws)
    mid = call(ws, "add_materials", deal=deal, items=[{"kind": "other", "link": url}])["accepted"][
        0
    ]["material_id"]
    state = wait_for_materials(ws, deal)
    assert material(state, mid)["status"] == "skipped"
    assert state["skips"][0]["code"] == "material_unreadable"


def test_html_pages_become_text():
    page = b"<html><head><title>Fixture Co</title><script>x()</script></head><body><p>Hello</p></body></html>"
    text = extract.extract(page, "index", "text/html")
    assert text.startswith("# Fixture Co")
    assert "Hello" in text and "x()" not in text


def test_a_skipped_link_added_again_is_fetched_again(ws, net):
    url = "https://files.example.test/later.txt"
    deal = new_deal(ws)
    first = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "link": url}])
    mid = first["accepted"][0]["material_id"]
    assert material(wait_for_materials(ws, deal), mid)["status"] == "skipped"

    net.routes[url] = httpx.Response(
        200, text="Now it works.", headers={"content-type": "text/plain"}
    )
    again = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "link": url}])
    assert again["accepted"][0]["material_id"] == mid
    assert material(wait_for_materials(ws, deal), mid)["status"] == "ready"


def test_an_upload_with_no_file_keeps_the_link_usable(ws, client):
    deal = new_deal(ws)
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "notes", "filename": "n.txt"}])
    path = upload_path(body["upload_url"])
    empty = client.post(path, files=[("files", ("n.txt", b"", "text/plain"))])
    assert empty.status_code == 400
    ok = client.post(path, files=[("files", ("n.txt", b"Synthetic notes.", "text/plain"))])
    assert ok.status_code == 200


def test_files_match_by_name_and_unfilled_materials_are_skipped(ws, client):
    deal = new_deal(ws)
    body = call(
        ws,
        "add_materials",
        deal=deal,
        items=[
            {"kind": "notes", "filename": "a.txt"},
            {"kind": "notes", "filename": "b.txt"},
            {"kind": "notes", "filename": "c.txt"},
        ],
    )
    a, b, c = [x["material_id"] for x in body["accepted"]]
    posted = client.post(
        upload_path(body["upload_url"]),
        files=[
            ("files", ("B.TXT", b"Synthetic b.", "text/plain")),
            ("files", ("a.txt", b"Synthetic a.", "text/plain")),
        ],
    )
    assert posted.status_code == 200
    state = wait_for_materials(ws, deal)

    def text(mid: str) -> str:
        return (ws.root / "deals" / deal / "materials" / f"{mid}.md").read_text()

    assert "Synthetic a." in text(a) and "Synthetic b." in text(b)
    assert material(state, c)["status"] == "skipped"
    assert [s["material_id"] for s in state["skips"]] == [c]


def test_upload_pages_escape_filenames(ws, client):
    deal = new_deal(ws)
    body = call(
        ws,
        "add_materials",
        deal=deal,
        items=[{"kind": "deck", "filename": "<script>x</script>.pdf"}],
    )
    page = client.get(upload_path(body["upload_url"]))
    assert "<script>x</script>" not in page.text
    assert "&lt;script&gt;" in page.text

"""The site read endpoint and the compile reply's page link (CONN-SITE-01 to CONN-SITE-04).

``GET /site/v1/firms/{firm}/deals/{deal}/memo`` serves a deal's latest compiled
memo to the firm's own site, behind a per-firm site key from
``MEMOPOP_SITE_KEYS``. Every key here is fake.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from src.connector.app import build_app
from src.connector.config import ConnectorSettings

from .conftest import BASE_URL, call, deal_json, key_headers, new_deal, rest
from .fake_claude import Direct, FakeClaude

SITE_KEYS = {
    "test-firm": "site-test-firm-fake-1a2b3c",
    "other-firm": "site-other-firm-fake-4d5e6f",
}


def site_headers(firm: str = "test-firm") -> dict:
    return {"Authorization": f"Bearer {SITE_KEYS[firm]}"}


def memo_path(deal: str, firm: str = "test-firm") -> str:
    return f"/site/v1/firms/{firm}/deals/{deal}/memo"


@pytest.fixture
def site_client(settings, jwks_transport):
    app = build_app(
        dataclasses.replace(settings, site_keys=dict(SITE_KEYS)), http_transport=jwks_transport
    )
    with TestClient(app, base_url=BASE_URL) as c:
        yield c


def compiled(ws, formats=None) -> tuple[str, dict]:
    """fixture-co with every section drafted, then compiled once."""
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, until=lambda s: s["phase"] == "enhance", compile=False)
    args = {"formats": formats} if formats else {}
    return deal, call(ws, "compile", deal=deal, **args)


def test_site_keys_are_read_from_the_environment():
    settings = ConnectorSettings.from_env(
        {"MEMOPOP_SITE_KEYS": "test-firm=site-a, other-firm=site-b"}
    )
    assert settings.site_keys == {"test-firm": "site-a", "other-firm": "site-b"}
    assert ConnectorSettings.from_env({}).site_keys == {}
    with pytest.raises(ValueError):
        ConnectorSettings.from_env({"MEMOPOP_SITE_KEYS": "no-equals-sign"})


@pytest.mark.spec("CONN-SITE-01")
def test_the_site_key_gets_the_latest_compiled_memo_with_its_label_time_and_links(ws, site_client):
    deal, first = compiled(ws)

    response = site_client.get(memo_path(deal), headers=site_headers())
    assert response.status_code == 200, response.text
    assert "no-store" in response.headers.get("cache-control", "")
    body = response.json()
    state = json.loads(deal_json(ws, deal).read_text())
    memo = call(ws, "get_artifact", deal=deal, artifact_id="compile.assemble")

    assert body["ok"] is True
    assert (body["firm"], body["deal"]) == ("test-firm", deal)
    assert body["markdown"] == memo["text"]
    assert body["version"] == first["version"] == 1
    assert body["label"] == first["label"] == "v0.0.1"
    assert body["compiled_at"] == state["compiled"]["at"]
    assert body["images_unresolved"] == []

    html = site_client.get(body["html_url"])
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")
    pdf = site_client.get(body["pdf_url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # A section edited and compiled again: the endpoint serves the new version.
    state = json.loads(deal_json(ws, deal).read_text())
    draft = ws.root / "deals" / deal / state["artifacts"]["draft.section:01-overview"]["path"]
    draft.write_text(draft.read_text() + "\nA sentence the partner added.\n")
    second = call(ws, "compile", deal=deal, formats=["html"])
    assert second["version"] == 2
    latest = site_client.get(memo_path(deal), headers=site_headers()).json()
    assert (latest["version"], latest["label"]) == (2, second["label"])
    assert "A sentence the partner added." in latest["markdown"]


@pytest.mark.spec("CONN-SITE-01")
def test_image_references_to_uploaded_binaries_become_signed_links(ws, site_client):
    """A memo imported from a local run points at images by local path; the
    uploader put each image in the bucket as blobs/<sha256> and recorded it as a
    material with its local_path. The endpoint rewrites those to signed links."""
    deal = new_deal(ws)
    png = b"\x89PNG\r\n\x1a\nfake-image-bytes"
    digest = hashlib.sha256(png).hexdigest()
    ws.bucket.put(f"blobs/{digest}", png, "image/png")
    other = b"\x89PNG\r\n\x1a\nanother"
    other_digest = hashlib.sha256(other).hexdigest()
    ws.bucket.put(f"blobs/{other_digest}", other, "image/png")

    memo = (
        "# Investment Memo: Fixture Co\n\n## Overview\n\n"
        "![Slide 3](io/humain/deals/Fixture/outputs/Fixture-v0.0.2/deck-screenshots/page-03.png)\n\n"
        "![Slide 3 again](deck-screenshots/page-03.png)\n\n"
        "![Diagram](diagrams/03-tam-sam-som.svg)\n\n"
        "![Hosted](https://cdn.example.com/hosted.png)\n\n"
        "![Inline](data:image/svg+xml;base64,PHN2Zy8+)\n"
    )
    folder = ws.root / "deals" / deal / "compiled" / "1"
    folder.mkdir(parents=True)
    (folder / "memo.md").write_text(memo)
    state = json.loads(deal_json(ws, deal).read_text())
    state["compiled"] = {
        "version": 1,
        "label": "v0.0.2",
        "sha256": hashlib.sha256(memo.encode()).hexdigest(),
        "keys": {},
        "at": "2026-11-20T12:00:00Z",
    }
    state["artifacts"]["compile.assemble"] = {
        "step_id": "compile.assemble",
        "section": None,
        "path": "compiled/1/memo.md",
        "kind": "compiled",
        "version": 1,
        "sha256": state["compiled"]["sha256"],
        "chars": len(memo),
        "partner_approved": False,
        "partner_notes": "Imported.",
        "instruction_version": "1",
        "saved_at": "2026-11-20T12:00:00Z",
    }
    for rel, sha in (
        ("outputs/Fixture-v0.0.2/deck-screenshots/page-03.png", digest),
        ("outputs/Fixture-v0.0.1/deck-screenshots/page-03.png", other_digest),
    ):
        state["materials"].append(
            {
                "material_id": f"mat-{sha[:12]}",
                "kind": "image",
                "status": "ready",
                "source": "upload",
                "title": rel,
                "filename": "page-03.png",
                "bucket_key": f"blobs/{sha}",
                "sha256": sha,
                "bytes": 10,
                "local_path": rel,
                "added_at": "2026-11-20T12:00:00Z",
                "ready_at": "2026-11-20T12:00:00Z",
            }
        )
    deal_json(ws, deal).write_text(json.dumps(state, indent=2))

    body = site_client.get(memo_path(deal), headers=site_headers()).json()
    assert body["ok"] is True, body
    assert body["label"] == "v0.0.2"
    assert body["html_url"] is None and body["pdf_url"] is None

    lines = body["markdown"].splitlines()
    links = [line.split("](", 1)[1].rstrip(")") for line in lines if "](" in line]
    slide, slide_again, diagram, hosted, inline = links
    # Both references to the slide resolve to the copy from the memo's own
    # version (v0.0.2), not the older run's file with the same name.
    for url in (slide, slide_again):
        assert url.startswith(BASE_URL) and "signature=" in url, url
        assert site_client.get(url).content == png
    assert hosted == "https://cdn.example.com/hosted.png"
    assert inline == "data:image/svg+xml;base64,PHN2Zy8+"
    # Nothing was uploaded for the diagram: it is left as written and reported.
    assert diagram == "diagrams/03-tam-sam-som.svg"
    assert body["images_unresolved"] == ["diagrams/03-tam-sam-som.svg"]


@pytest.mark.spec("CONN-SITE-02")
def test_another_firms_site_key_is_403_and_no_key_is_401(ws, site_client):
    deal, _ = compiled(ws, formats=["html"])

    other = site_client.get(memo_path(deal), headers=site_headers("other-firm"))
    assert other.status_code == 403, other.text
    assert other.json()["error"]["code"] == "forbidden_firm"
    assert "markdown" not in other.json()

    for headers in (
        {},
        {"Authorization": "Bearer not-a-site-key"},
        {"Authorization": SITE_KEYS["test-firm"]},  # no Bearer scheme
        key_headers(),  # a partner key is not a site key
    ):
        response = site_client.get(memo_path(deal), headers=headers)
        assert response.status_code == 401, (headers, response.text)
        assert response.json()["error"]["code"] == "unauthenticated"
        assert response.headers.get("WWW-Authenticate", "").startswith("Bearer")

    # A site key is read-only and only for this route: the tools refuse it.
    assert rest(site_client, "list_deals", headers=site_headers()).status_code == 401
    assert rest(site_client, "compile", {"deal": deal}, headers=site_headers()).status_code == 401


@pytest.mark.spec("CONN-SITE-02")
def test_with_no_site_keys_configured_every_request_is_401(ws, client):
    deal, _ = compiled(ws, formats=["html"])
    response = client.get(memo_path(deal), headers=site_headers())
    assert response.status_code == 401


@pytest.mark.spec("CONN-SITE-03")
def test_a_deal_with_no_compiled_version_is_404(ws, site_client):
    deal = new_deal(ws)
    response = site_client.get(memo_path(deal), headers=site_headers())
    assert response.status_code == 404, response.text
    assert response.json()["ok"] is False

    missing = site_client.get(memo_path("no-such-deal"), headers=site_headers())
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "deal_not_found"


@pytest.mark.spec("CONN-SITE-04")
def test_compile_returns_the_site_url_when_the_firm_has_a_page_for_the_deal(ws):
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, until=lambda s: s["phase"] == "enhance", compile=False)

    # No site configured: no site_url in the reply.
    plain = call(ws, "compile", deal=deal, formats=["html"])
    assert plain.get("site_url") is None

    config_path = ws.root / "firm.json"
    config = json.loads(config_path.read_text())
    config["site_memo_url"] = "https://www.example-firm.vc/lp/memos/{slug}"
    config["site_memo_slugs"] = {deal: "fixture"}
    config_path.write_text(json.dumps(config))

    body = call(ws, "compile", deal=deal, formats=["html"])
    assert body["site_url"] == "https://www.example-firm.vc/lp/memos/fixture"

    # A deal the firm has no page for gets none.
    config["site_memo_slugs"] = {"some-other-deal": "other"}
    config_path.write_text(json.dumps(config))
    assert call(ws, "compile", deal=deal, formats=["html"]).get("site_url") is None

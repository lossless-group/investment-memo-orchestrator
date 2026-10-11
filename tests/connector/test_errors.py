"""The error envelope on both transports (CONN-ERR-01 to CONN-ERR-04)."""

from __future__ import annotations

import pytest

from src.connector.errors import ConnectorError
from src.connector.workspace import Workspace

from .conftest import TEMPLATE, Mcp, call, deal_json, key_headers, new_deal, rest
from .fixtures import canned

ENVELOPE_FIELDS = {"kind", "code", "message", "next", "retry_after_seconds", "details"}


def _fail_on_call(n: int):
    """A stand-in for Workspace._replace that fails on its nth call."""
    calls = {"count": 0}
    original = Workspace._replace

    def replace(self, tmp, dest):
        calls["count"] += 1
        if calls["count"] >= n:
            raise OSError(28, "No space left on device")
        return original(self, tmp, dest)

    return replace


@pytest.mark.spec("CONN-ERR-01")
def test_failing_mcp_calls_are_tool_errors_with_the_envelope(mcp):
    failures = [
        ("next_step", {"deal": "no-such-deal"}, "deal_not_found"),
        ("create_new_deal", {"company": ""}, "validation_failed"),
        ("create_new_deal", {"company": "Acme", "template": "nope"}, "template_not_found"),
        ("list_deals", {"limit": "many"}, "validation_failed"),
    ]
    for tool, args, code in failures:
        result = mcp.call(tool, args)
        assert result["isError"] is True, (tool, result)
        body = result["structuredContent"]
        assert body["ok"] is False
        assert body["api_version"] == "1"
        assert ENVELOPE_FIELDS <= set(body["error"]), body
        assert body["error"]["kind"] == "invalid"
        assert body["error"]["code"] == code
        text = " ".join(c["text"] for c in result["content"] if c["type"] == "text")
        assert body["error"]["message"] in text
        assert body["error"]["next"] in text


@pytest.mark.spec("CONN-ERR-02")
def test_rest_maps_invalid_to_4xx_and_down_to_503(client, monkeypatch):
    unknown = rest(client, "next_step", {"deal": "no-such-deal"})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "deal_not_found"

    bad = rest(client, "create_new_deal", {"company": ""})
    assert 400 <= bad.status_code < 500
    assert bad.json()["error"]["kind"] == "invalid"

    missing_template = rest(client, "create_new_deal", {"company": "Acme", "template": "nope"})
    assert 400 <= missing_template.status_code < 500

    monkeypatch.setattr(Workspace, "_replace", _fail_on_call(1))
    down = rest(client, "create_new_deal", {"company": "Acme", "template": TEMPLATE})
    assert down.status_code == 503
    assert down.headers.get("Retry-After", "").isdigit()
    body = down.json()
    assert body["error"]["kind"] == "down"
    assert body["error"]["code"] == "storage_unavailable"
    assert body["error"]["retry_after_seconds"] == int(down.headers["Retry-After"])


@pytest.mark.spec("CONN-ERR-03")
def test_storage_failing_mid_call_is_down_and_saves_nothing(ws, monkeypatch):
    # create_new_deal: the deal must not half-exist.
    with monkeypatch.context() as m:
        m.setattr(Workspace, "_replace", _fail_on_call(1))
        with pytest.raises(ConnectorError) as raised:
            new_deal(ws)
    assert (raised.value.kind, raised.value.code) == ("down", "storage_unavailable")
    assert call(ws, "list_deals")["deals"] == []
    assert not (ws.root / "deals" / "fixture-co").exists()

    # submit_artifact: the artifact is written, then deal.json fails. Both roll back.
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    before = deal_json(ws, deal).read_bytes()
    with monkeypatch.context() as m:
        m.setattr(Workspace, "_replace", _fail_on_call(2))
        with pytest.raises(ConnectorError) as raised:
            call(
                ws,
                "submit_artifact",
                deal=deal,
                step_id=step["step_id"],
                section=step["section"],
                content=canned.research(step["section"]),
                partner_approved=True,
            )
    assert (raised.value.kind, raised.value.code) == ("down", "storage_unavailable")
    assert deal_json(ws, deal).read_bytes() == before
    assert not (ws.root / "deals" / deal / "research" / f"{step['section']}.md").exists()
    with pytest.raises(ConnectorError) as raised:
        call(ws, "get_artifact", deal=deal, artifact_id=f"research.section:{step['section']}")
    assert raised.value.code == "artifact_not_found"


@pytest.mark.spec("CONN-ERR-04")
def test_every_response_carries_api_version(client, mcp):
    bodies = []
    created = rest(client, "create_new_deal", {"company": "Fixture Co", "template": TEMPLATE})
    bodies.append(created.json())
    deal = created.json()["deal"]
    bodies.append(rest(client, "list_deals").json())
    bodies.append(rest(client, "next_step", {"deal": deal}).json())
    bodies.append(rest(client, "next_step", {"deal": "nope"}).json())
    bodies.append(rest(client, "list_deals", headers={}).json())  # 401
    bodies.append(rest(client, "compile", {"deal": deal}).json())
    for result in (
        mcp.call("list_deals"),
        mcp.call("next_step", {"deal": deal}),
        mcp.call("next_step", {"deal": "nope"}),
    ):
        bodies.append(result["structuredContent"])
    for body in bodies:
        assert body.get("api_version") == "1", body


def test_unauthenticated_mcp_body_is_the_envelope(client):
    """Not a spec ID: a 401 on /mcp still speaks the envelope."""
    response = Mcp(client, headers={}).post("tools/list")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
    assert key_headers()  # the fixture keys exist

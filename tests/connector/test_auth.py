"""Auth: the protected-resource document, static keys, and id.didi.sh tokens
(CONN-AUTH-01 to CONN-AUTH-05)."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from .conftest import BASE_URL, KID, TEMPLATE, TEST_FIRM_ENTITY, Mcp, make_token, rest

#: Claude requires the document's resource to equal the connector URL, path
#: included, so the challenge points at the path-inserted location.
RESOURCE_DOC = f"{BASE_URL}/.well-known/oauth-protected-resource/mcp"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _urls(value):
    if isinstance(value, str):
        if value.startswith(("http://", "https://")) or "://" in value:
            yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _urls(v)
    elif isinstance(value, list):
        for v in value:
            yield from _urls(v)


@pytest.mark.spec("CONN-AUTH-01")
def test_no_credential_is_401_pointing_at_the_resource_document(client):
    responses = [
        rest(client, "list_deals", headers={}),
        rest(client, "create_new_deal", {"company": "Acme"}, headers={}),
        rest(client, "list_deals", headers={"Authorization": "Bearer not-a-real-key"}),
        Mcp(client, headers={}).post("tools/list"),
    ]
    for response in responses:
        assert response.status_code == 401, response.text
        challenge = response.headers.get("WWW-Authenticate", "")
        assert challenge.startswith("Bearer"), challenge
        assert f'resource_metadata="{RESOURCE_DOC}"' in challenge
        assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.spec("CONN-AUTH-02")
def test_protected_resource_document_is_https_even_behind_a_plain_http_proxy(app):
    with TestClient(app, base_url="http://memopop.didi.sh") as plain:
        for path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            response = plain.get(
                path,
                headers={
                    "X-Forwarded-Proto": "http",
                    "X-Forwarded-Host": "memopop.didi.sh",
                    "Host": "memopop.didi.sh",
                },
            )
            assert response.status_code == 200, path
            doc = response.json()
            assert doc["resource"] == "https://memopop.didi.sh/mcp"
            assert doc["authorization_servers"][0] == "https://id.didi.sh"
            urls = list(_urls(doc))
            assert urls
            for url in urls:
                assert url.startswith("https://"), f"{path}: {url}"


@pytest.mark.spec("CONN-AUTH-03")
def test_firm_a_cannot_see_firm_b(client, signing_key):
    other = {"Authorization": "Bearer sk-other-firm-0e4b8d1f3c"}
    created = rest(client, "create_new_deal", {"company": "Secret Co", "template": TEMPLATE}, other)
    assert created.status_code in (200, 201)
    secret = created.json()["deal"]

    # Over REST, firm A asks for firm B's deal by slug: indistinguishable from a deal
    # that exists nowhere, apart from the slug it asked for.
    theirs = rest(client, "next_step", {"deal": secret})
    nowhere = rest(client, "next_step", {"deal": "zz-no-such-deal"})
    assert theirs.status_code == nowhere.status_code == 404
    assert theirs.json()["error"]["kind"] == "invalid"
    assert json.dumps(theirs.json()).replace(secret, "X") == json.dumps(nowhere.json()).replace(
        "zz-no-such-deal", "X"
    )
    assert "other-firm" not in theirs.text

    # Naming firm B explicitly: forbidden, and the same answer whether B exists or not.
    named = rest(client, "list_deals", {"firm": "other-firm"})
    ghost = rest(client, "list_deals", {"firm": "no-such-firm"})
    assert named.status_code == ghost.status_code == 403
    assert named.json()["error"]["code"] == "forbidden_firm"
    assert named.json() == ghost.json()
    assert "Secret" not in named.text and secret not in named.text

    # A token whose entity is firm A gets the same treatment.
    token = _bearer(make_token(signing_key, entity=TEST_FIRM_ENTITY))
    assert rest(client, "next_step", {"deal": secret}, token).status_code == 404
    assert rest(client, "list_deals", {"firm": "other-firm"}, token).status_code == 403
    assert rest(client, "list_deals", {}, token).json()["deals"] == []

    # Over MCP, the same.
    session = Mcp(client)
    result = session.call("next_step", {"deal": secret})
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "deal_not_found"
    assert "other-firm" not in json.dumps(result)
    result = session.call("list_deals", {"firm": "other-firm"})
    assert result["structuredContent"]["error"]["code"] == "forbidden_firm"


@pytest.mark.spec("CONN-AUTH-04")
def test_a_valid_token_is_served_in_its_entitys_workspace(client, signing_key, io_root):
    # id.didi.sh's audience is the registered resource; the /mcp form is accepted too.
    for aud in (BASE_URL, f"{BASE_URL}/mcp", ["x", BASE_URL]):
        token = _bearer(make_token(signing_key, entity=TEST_FIRM_ENTITY, aud=aud))
        response = rest(client, "list_deals", {}, token)
        assert response.status_code == 200, (aud, response.text)

    token = _bearer(make_token(signing_key, entity=TEST_FIRM_ENTITY))
    created = rest(client, "create_new_deal", {"company": "Token Co", "template": TEMPLATE}, token)
    assert created.status_code in (200, 201), created.text
    assert (io_root / "test-firm" / "deals" / created.json()["deal"] / "deal.json").is_file()
    assert not (io_root / "other-firm" / "deals" / created.json()["deal"]).exists()

    session = Mcp(client, headers=token)
    listed = session.call("list_deals")
    assert [d["deal"] for d in listed["structuredContent"]["deals"]] == [created.json()["deal"]]


@pytest.mark.spec("CONN-AUTH-05")
def test_wrong_audience_expired_or_unknown_key_is_401(client, signing_key):
    stranger = Ed25519PrivateKey.generate()
    e = TEST_FIRM_ENTITY
    bad_tokens = {
        "another audience": make_token(signing_key, entity=e, aud="https://decks.didi.sh"),
        "expired": make_token(signing_key, entity=e, expires_in=-120),
        "unknown key, known kid": make_token(stranger, entity=e, kid=KID),
        "unknown key and kid": make_token(stranger, entity=e, kid="stranger"),
        "another issuer": make_token(signing_key, entity=e, iss="https://evil.example"),
        "not an access token": make_token(signing_key, entity=e, typ="JWT"),
        "no entity": make_token(signing_key),
        "garbage": "eyJhbGciOiJub25lIn0.e30.",
    }
    for label, token in bad_tokens.items():
        response = rest(client, "list_deals", {}, _bearer(token))
        assert response.status_code == 401, f"{label}: {response.status_code} {response.text}"
        assert response.json()["error"]["code"] == "unauthenticated", label
        assert "WWW-Authenticate" in response.headers, label
        mcp_response = Mcp(client, headers=_bearer(token)).post("tools/list")
        assert mcp_response.status_code == 401, label

"""Fixtures for the connector suite.

Everything here is synthetic and lives under ``tmp_path``: two firms
(``test-firm`` and ``other-firm``), the three-section ``fixture-three`` outline,
a local-directory bucket, and a locally generated Ed25519 keypair whose JWKS is
served through an ``httpx.MockTransport``. Nothing reads ``io/`` and nothing
calls id.didi.sh.
"""

from __future__ import annotations

import base64
import json
import shutil
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from src.connector.app import build_app
from src.connector.config import ConnectorSettings
from src.connector.registry import load_registry
from src.connector.tools import invoke
from src.connector.workspace import open_workspace, provision_firm

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]

BASE_URL = "https://memopop.didi.sh"
AUDIENCE = "https://memopop.didi.sh"
ISSUER = "https://id.didi.sh"
JWKS_URL = "https://id.didi.sh/.well-known/jwks.json"
KID = "test-key-1"

STATIC_KEYS = {
    "test-firm": "sk-test-firm-6f1d2c9a7b",
    "other-firm": "sk-other-firm-0e4b8d1f3c",
}

TEMPLATE = "fixture-three"
SECTIONS = ["01-overview", "02-market", "03-team"]

#: The REST surface, written out from the spec's tools table rather than read
#: from the registry, so a registry that drifts from the spec fails these tests.
REST_ROUTES = {
    "list_deals": ("GET", "/v1/deals"),
    "create_new_deal": ("POST", "/v1/deals"),
    "add_materials": ("POST", "/v1/deals/{deal}/materials"),
    "next_step": ("POST", "/v1/deals/{deal}/next-step"),
    "submit_artifact": ("POST", "/v1/deals/{deal}/artifacts"),
    "get_artifact": ("GET", "/v1/deals/{deal}/artifacts/{artifact_id}"),
    "save_snapshot": ("POST", "/v1/snapshots"),
    "compile": ("POST", "/v1/deals/{deal}/compile"),
}

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}


# ------------------------------------------------------------------ keys


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def public_jwk(key: Ed25519PrivateKey, kid: str = KID) -> dict:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": _b64(raw),
        "kid": kid,
        "alg": "EdDSA",
        "use": "sig",
    }


def make_token(
    key: Ed25519PrivateKey,
    *,
    entity: Any = None,
    aud: Any = AUDIENCE,
    iss: str = ISSUER,
    expires_in: int = 3600,
    kid: str = KID,
    typ: str = "at+jwt",
    **claims: Any,
) -> str:
    """An access token shaped exactly like id.didi.sh's.

    Header ``{"alg": "EdDSA", "kid": ..., "typ": "at+jwt"}``; claims ``iss``,
    ``sub`` (the didi_id), ``aud``, ``entity`` (``{"id", "slug"}``), ``scope``,
    ``client_id``, ``iat``, ``exp`` (one hour), ``jti``.
    """
    now = int(time.time())
    payload = {
        "iss": iss,
        "sub": "didi_person_test",
        "aud": aud,
        "scope": "memopop",
        "client_id": "claude-connector-test",
        "iat": now,
        "exp": now + expires_in,
        "jti": f"jti-{now}-{expires_in}-{kid}",
        **claims,
    }
    if entity is not None:
        payload["entity"] = entity
    return jwt.encode(payload, key, algorithm="EdDSA", headers={"kid": kid, "typ": typ})


TEST_FIRM_ENTITY = {"id": "ent_test_firm", "slug": "test-firm"}


@pytest.fixture(scope="session")
def signing_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def jwks(signing_key) -> dict:
    return {"keys": [public_jwk(signing_key)]}


@pytest.fixture
def jwks_transport(jwks) -> httpx.MockTransport:
    """Serves the JWKS at its id.didi.sh URL, and nothing else."""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == JWKS_URL:
            return httpx.Response(200, json=jwks)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


# ------------------------------------------------------------------ workspace


def provision(io_root: Path, firm: str, **kwargs: Any) -> Path:
    path = provision_firm(io_root, firm, **kwargs)
    outlines = path / "templates" / "outlines"
    outlines.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "templates" / f"{TEMPLATE}.yaml", outlines / f"{TEMPLATE}.yaml")
    return path


@pytest.fixture
def io_root(tmp_path) -> Path:
    root = tmp_path / "firms"
    provision(root, "test-firm", default_template=TEMPLATE, entity_id="ent_test_firm")
    provision(root, "other-firm", default_template=TEMPLATE)
    return root


@pytest.fixture
def settings(io_root, tmp_path) -> ConnectorSettings:
    return ConnectorSettings(
        io_root=io_root,
        public_base_url=BASE_URL,
        auth_issuer=ISSUER,
        jwks_url=JWKS_URL,
        token_audience=AUDIENCE,
        static_keys=dict(STATIC_KEYS),
        bucket_backend="local",
        bucket_local_root=tmp_path / "buckets",
    )


@pytest.fixture
def registry():
    return load_registry()


@pytest.fixture
def ws(settings):
    return open_workspace(settings, "test-firm")


def call(ws, tool: str, **args: Any) -> dict:
    """Call a tool directly, transport-free, as the tests for tool logic do."""
    return invoke(tool, args, ws)


# ------------------------------------------------------------------ transports


@pytest.fixture
def app(settings, jwks_transport):
    return build_app(settings, http_transport=jwks_transport)


@pytest.fixture
def client(app):
    with TestClient(app, base_url=BASE_URL) as c:
        yield c


def key_headers(firm: str = "test-firm") -> dict:
    return {"Authorization": f"Bearer {STATIC_KEYS[firm]}"}


def rest(client: TestClient, tool: str, args: dict | None = None, headers: dict | None = None):
    """Send one tool call over REST, routing by the spec's tools table."""
    method, template = REST_ROUTES[tool]
    args = dict(args or {})
    path = template
    for name in ("deal", "artifact_id"):
        token = "{" + name + "}"
        if token in path:
            path = path.replace(token, str(args.pop(name)))
    headers = headers if headers is not None else key_headers()
    if method == "GET":
        return client.get(path, params=args, headers=headers)
    return client.request(method, path, json=args, headers=headers)


class Mcp:
    """A minimal MCP client over Streamable HTTP, enough to drive the tests."""

    def __init__(self, client: TestClient, headers: dict | None = None):
        self.client = client
        self.headers = {**MCP_HEADERS, **(headers if headers is not None else key_headers())}
        self._id = 0

    def post(self, method: str, params: dict | None = None) -> httpx.Response:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        return self.client.post("/mcp", content=json.dumps(body), headers=self.headers)

    def rpc(self, method: str, params: dict | None = None) -> dict:
        response = self.post(method, params)
        assert response.status_code == 200, response.text
        text = response.text
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = data[-1]
        message = json.loads(text)
        assert "error" not in message, message
        return message["result"]

    def initialize(self) -> dict:
        return self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "connector-tests", "version": "1"},
            },
        )

    def list_tools(self) -> list[dict]:
        return self.rpc("tools/list")["tools"]

    def call(self, name: str, arguments: dict | None = None) -> dict:
        return self.rpc("tools/call", {"name": name, "arguments": arguments or {}})


@pytest.fixture
def mcp(client) -> Mcp:
    session = Mcp(client)
    session.initialize()
    return session


# ------------------------------------------------------------------ flow helpers


def new_deal(ws, company: str = "Fixture Co", url: str = "https://fixture.co", **kw) -> str:
    return call(ws, "create_new_deal", company=company, url=url, template=TEMPLATE, **kw)["deal"]


def deal_json(ws, deal: str) -> Path:
    return ws.root / "deals" / deal / "deal.json"

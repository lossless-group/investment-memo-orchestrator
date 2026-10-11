"""The connector mounted on the existing sidecar app (no spec ID).

The sidecar's routes keep working; /docs now belongs to the connector, and its
Swagger UI moved to /sidecar/docs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.server.app import app


def test_the_sidecar_serves_the_connector_beside_its_own_routes():
    with TestClient(app) as client:
        assert client.get("/healthz").json()["ok"] is True
        assert client.get("/llms.txt").text.startswith("# MemoPop")
        assert client.get("/docs").headers["content-type"].startswith("text/html")
        assert client.get("/sidecar/docs").status_code == 200
        assert client.get("/v1/deals").status_code == 401
        mcp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert mcp.status_code == 401
        doc = client.get("/.well-known/oauth-protected-resource/mcp").json()
        assert doc["resource"].endswith("/mcp")


def test_the_sidecar_survives_two_lifespans():
    """The MCP session manager runs once per instance; each lifespan needs a fresh one."""
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get("/healthz").status_code == 200

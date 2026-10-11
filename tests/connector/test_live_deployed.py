"""Deploy and live health (plan 2): CONN-LIVE-02, against the deployed service.

Runs only when ``MEMOPOP_LIVE_URL`` is set (for example
``https://memopop.didi.sh``) and is reported GATED otherwise. It imports only
pytest and httpx, so ``.github/workflows/live-health.yml`` runs it from a
sparse checkout with no project install.
"""

from __future__ import annotations

import os

import httpx
import pytest

# ------------------------------------------------------------------ CONN-LIVE-02

LIVE_URL = os.environ.get("MEMOPOP_LIVE_URL", "").rstrip("/")


@pytest.mark.spec("CONN-LIVE-02")
@pytest.mark.skipif(
    not LIVE_URL,
    reason="MEMOPOP_LIVE_URL is not set; set it to the deployed origin "
    "(e.g. https://memopop.didi.sh) to check the live service",
)
def test_the_deployed_service_answers_over_https():
    assert LIVE_URL.startswith("https://"), f"MEMOPOP_LIVE_URL must be https: {LIVE_URL}"
    with httpx.Client(timeout=20, follow_redirects=False) as http:
        health = http.get(f"{LIVE_URL}/healthz")
        assert health.status_code == 200, health.text
        assert health.json().get("ok") is True

        llms = http.get(f"{LIVE_URL}/llms.txt")
        assert llms.status_code == 200
        assert llms.text.startswith("# MemoPop")
        for tool in ("list_deals", "create_new_deal", "next_step", "compile"):
            assert tool in llms.text

        for path in (
            "/.well-known/oauth-protected-resource/mcp",
            "/.well-known/oauth-protected-resource",
        ):
            doc = http.get(f"{LIVE_URL}{path}")
            assert doc.status_code == 200, (path, doc.text)
            body = doc.json()
            assert body["resource"] == f"{LIVE_URL}/mcp"
            assert body["authorization_servers"][0] == "https://id.didi.sh"
            urls = [body["resource"], *body["authorization_servers"]]
            urls.append(body.get("resource_documentation", "https://"))
            assert all(u.startswith("https://") for u in urls), urls

        # A request with no credential is a 401 pointing at the document above.
        mcp = http.post(f"{LIVE_URL}/mcp", json={})
        assert mcp.status_code == 401
        assert "oauth-protected-resource/mcp" in mcp.headers.get("www-authenticate", "")

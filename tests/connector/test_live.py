"""Deploy and live health (plan 2): CONN-LIVE-01 and CONN-LIVE-02.

CONN-LIVE-01 runs ``scripts/health_check.py`` as a subprocess, exactly as the
scheduled workflow does, against a real uvicorn server started in a thread on
a free local port. The server is the production entry point
(``src.connector.serve.create_app``) over a temporary ``MEMO_IO_ROOT`` holding
a ``test-firm`` provisioned the way an operator provisions one
(``src.connector.provision``). Nothing reads ``io/`` and nothing leaves the
machine.

CONN-LIVE-02 needs the deployed service, so it runs only when
``MEMOPOP_LIVE_URL`` is set (for example ``https://memopop.didi.sh``) and is
reported GATED otherwise.

Server modules are imported inside the fixtures, so a missing implementation
fails these tests (RED) instead of stopping collection.
"""

from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from src.connector.config import ConnectorSettings
from src.connector.errors import ConnectorError

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "health_check.py"
HEALTH_KEY = "sk-health-test-firm-3b7e1d"


@dataclass
class LiveServer:
    url: str
    io_root: Path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(tmp_path) -> LiveServer:
    import uvicorn

    provision = importlib.import_module("src.connector.provision")
    serve = importlib.import_module("src.connector.serve")

    io_root = tmp_path / "firms"
    provision.provision_firm(io_root, "test-firm", health_check=True)
    settings = ConnectorSettings(
        io_root=io_root,
        public_base_url="https://memopop.didi.sh",
        static_keys={"test-firm": HEALTH_KEY},
        bucket_backend="local",
        bucket_local_root=tmp_path / "buckets",
    )
    app = serve.create_app(settings)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert thread.is_alive(), "uvicorn exited during startup"
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    try:
        yield LiveServer(f"http://127.0.0.1:{port}", io_root)
    finally:
        server.should_exit = True
        thread.join(timeout=15)


def run_check(url: str, *extra: str, key: str = HEALTH_KEY) -> subprocess.CompletedProcess:
    env = {**os.environ, "MEMOPOP_HEALTH_KEY": key}
    env.pop("GITHUB_STEP_SUMMARY", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", url, *extra],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        cwd=REPO,
    )


def failure_line(result: subprocess.CompletedProcess) -> str:
    lines = [ln for ln in (result.stdout + result.stderr).splitlines() if ln.startswith("FAIL")]
    assert lines, f"no FAIL line in:\n{result.stdout}\n{result.stderr}"
    return lines[-1]


def _tool(name: str):
    from src.connector.registry import load_registry

    return load_registry().tools[name]


# ------------------------------------------------------------------ CONN-LIVE-01


@pytest.mark.spec("CONN-LIVE-01")
def test_health_check_passes_against_a_healthy_server(live_server):
    result = run_check(live_server.url)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    for step in (
        "healthz",
        "list_deals",
        "create_new_deal",
        "add_materials",
        "research.section",
        "draft.section",
        "compile",
    ):
        assert step in out, f"{step} not reported:\n{out}"
    assert out.rstrip().splitlines()[-1].startswith("PASS"), out
    # The deal it made is in test-firm, uniquely named and marked as a health check.
    deals = sorted(p.name for p in (live_server.io_root / "test-firm" / "deals").iterdir())
    assert len(deals) == 1 and deals[0].startswith("health-check-"), deals


@pytest.mark.spec("CONN-LIVE-01")
def test_two_runs_make_two_distinct_deals(live_server):
    assert run_check(live_server.url).returncode == 0
    assert run_check(live_server.url).returncode == 0
    deals = list((live_server.io_root / "test-firm" / "deals").iterdir())
    assert len(deals) == 2


@pytest.mark.spec("CONN-LIVE-01")
def test_a_failing_step_exits_non_zero_naming_it(live_server):
    # The operator forgot the health-check outline: create_new_deal fails.
    outline = live_server.io_root / "test-firm" / "templates" / "outlines" / "health-check.yaml"
    outline.unlink()
    result = run_check(live_server.url)
    assert result.returncode == 1, result.stdout + result.stderr
    line = failure_line(result)
    assert "create_new_deal" in line and "template_not_found" in line, line


@pytest.mark.spec("CONN-LIVE-01")
def test_a_bad_key_exits_non_zero_naming_the_step(live_server):
    result = run_check(live_server.url, key="sk-not-a-real-key")
    assert result.returncode == 1, result.stdout + result.stderr
    line = failure_line(result)
    assert "list_deals" in line and "unauthenticated" in line, line


@pytest.mark.spec("CONN-LIVE-01")
def test_a_slow_step_exits_non_zero_naming_it(live_server, monkeypatch):
    tool = _tool("next_step")
    real = tool.handler

    def slow(ws, params):
        time.sleep(1.0)
        return real(ws, params)

    monkeypatch.setattr(tool, "handler", slow)
    result = run_check(live_server.url, "--budget", "next_step=0.3", "--allowance", "0")
    assert result.returncode == 1, result.stdout + result.stderr
    line = failure_line(result)
    assert "next_step" in line and "slow" in line, line


@pytest.mark.spec("CONN-LIVE-01")
def test_compile_not_implemented_fails_unless_the_changelog_declares_it(live_server, monkeypatch):
    # Whatever compile does on this branch, force not_implemented, and take away
    # the changelog line that would excuse it: the check must fail on compile.
    def not_implemented(ws, params):
        raise ConnectorError("not_implemented", "compile is not live on this server yet.")

    monkeypatch.setattr(_tool("compile"), "handler", not_implemented)
    monkeypatch.setattr(importlib.import_module("src.connector.docs_build"), "API_CHANGELOG", [])
    result = run_check(live_server.url)
    assert result.returncode == 1, result.stdout + result.stderr
    line = failure_line(result)
    assert "compile" in line and "not_implemented" in line, line


@pytest.mark.spec("CONN-LIVE-01")
def test_an_unreachable_server_exits_non_zero_naming_healthz():
    result = run_check(f"http://127.0.0.1:{_free_port()}")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "healthz" in failure_line(result)


@pytest.mark.spec("CONN-LIVE-01")
def test_no_key_is_a_usage_error_not_a_pass():
    env = {k: v for k, v in os.environ.items() if k != "MEMOPOP_HEALTH_KEY"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", "http://127.0.0.1:9"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=REPO,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "MEMOPOP_HEALTH_KEY" in result.stderr, result.stderr


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

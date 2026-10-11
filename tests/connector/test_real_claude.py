"""Real Claude runs the fixture deal through the connector (CONN-PLUG-02), and the
offline tests that prove the harness and its checks before anyone pays for a run.

**The live run is gated.** The Claude API's MCP connector calls the server from
Anthropic's cloud, so it needs the deployed service, not a local uvicorn. It runs
only when all three are set, and is reported GATED otherwise:

- ``ANTHROPIC_API_KEY``: the key the run is billed to.
- ``MEMOPOP_LIVE_URL``: the deployed origin, e.g. ``https://memopop.didi.sh``.
- ``MEMOPOP_HEALTH_KEY``: ``test-firm``'s static key, sent as the bearer token.

Optional: ``MEMOPOP_REAL_CLAUDE_MODEL`` (default ``claude-haiku-5-5``),
``MEMOPOP_REAL_CLAUDE_MAX_REQUESTS`` (default 24), and
``MEMOPOP_REAL_CLAUDE_REPORT`` (where the JSON report is written).

The server must have ``MEMOPOP_FAULT_FIRMS=test-firm`` and the ``real-claude-three``
outline in ``test-firm`` (``python -m src.connector.faults install-outline
test-firm``); a preflight checks the outline before any token is spent. See
``docs/operator/connect-claude.md``.

The offline tests drive the same :class:`~.real_claude.Conversation` and
:func:`~.real_claude.check` against a local app through :class:`ScriptedModel`:
a well-behaved run passes, and each way of breaking a rule is caught.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx
import pytest

from src.connector.config import ConnectorSettings

from .conftest import BASE_URL, ISSUER, JWKS_URL, STATIC_KEYS, Mcp, key_headers, provision
from .fixtures import canned
from .real_claude import (
    DEFAULT_MODEL,
    OPENING,
    TEMPLATE,
    Conversation,
    ScriptedModel,
    anthropic_sender,
    check,
    server_view,
)

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "plugin" / "skills" / "memopop" / "SKILL.md"

LIVE_ENV = ("ANTHROPIC_API_KEY", "MEMOPOP_LIVE_URL", "MEMOPOP_HEALTH_KEY")
_missing = [name for name in LIVE_ENV if not os.environ.get(name)]


def skill_prompt() -> str:
    """The plugin's skill without its frontmatter: the system prompt for the run."""
    text = SKILL.read_text(encoding="utf-8")
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL).strip()


# ------------------------------------------------------------------ CONN-PLUG-02 (live)


def _preflight(http: httpx.Client) -> None:
    """Check the key, the URL, and the outline, without spending a token."""
    response = http.get("/v1/deals", params={"limit": 1})
    if response.status_code != 200:
        pytest.fail(
            f"GET {http.base_url}/v1/deals with MEMOPOP_HEALTH_KEY returned "
            f"{response.status_code}: {response.text[:500]}"
        )
    probe = http.post("/v1/deals", json={"company": "Preflight", "template": "no-such-outline"})
    available = (probe.json().get("error") or {}).get("details", {}).get("available", [])
    if TEMPLATE not in available:
        pytest.fail(
            f"test-firm has no '{TEMPLATE}' outline (it has {available}). Install it on the "
            "server: python -m src.connector.faults install-outline test-firm"
        )


@pytest.mark.spec("CONN-PLUG-02")
@pytest.mark.skipif(
    bool(_missing),
    reason=f"real-Claude run needs {', '.join(_missing)} (see docs/operator/connect-claude.md)",
)
def test_real_claude_runs_the_fixture_deal_by_the_method(tmp_path):
    base = os.environ["MEMOPOP_LIVE_URL"].rstrip("/")
    key = os.environ["MEMOPOP_HEALTH_KEY"]
    model = os.environ.get("MEMOPOP_REAL_CLAUDE_MODEL") or DEFAULT_MODEL
    max_requests = int(os.environ.get("MEMOPOP_REAL_CLAUDE_MAX_REQUESTS") or 24)
    report_path = Path(os.environ.get("MEMOPOP_REAL_CLAUDE_REPORT") or tmp_path / "real.json")

    http = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {key}"}, timeout=60)
    _preflight(http)

    company = f"Fixture Co {time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    conversation = Conversation(
        anthropic_sender(os.environ["ANTHROPIC_API_KEY"]),
        model=model,
        system=skill_prompt(),
        mcp_url=f"{base}/mcp",
        token=key,
        max_requests=max_requests,
    )
    record = conversation.run(OPENING.format(company=company, template=TEMPLATE))
    view = server_view(lambda path, params: http.get(path, params=params), record.deal())
    failures = check(record, view)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({**record.summary(), "server": view.__dict__, "failures": failures}, indent=2)
    )
    print(
        f"\nreal Claude: {model}, {record.requests} requests, {record.seconds:.0f} s, "
        f"{record.usage}, about ${record.cost_usd:.3f}. Report: {report_path}"
    )
    assert not failures, "\n".join(failures) + f"\n\nReport: {report_path}"


# ------------------------------------------------------------------ the harness, offline


@pytest.fixture
def fault_app(tmp_path, jwks_transport):
    """A local app where test-firm has the fault hook on and the real-Claude outline."""
    from src.connector import faults
    from src.connector.app import build_app

    root = tmp_path / "firms"
    provision(root, "test-firm", entity_id="ent_test_firm")
    provision(root, "other-firm")
    faults.install_outline(root, "test-firm")
    settings = ConnectorSettings(
        io_root=root,
        public_base_url=BASE_URL,
        auth_issuer=ISSUER,
        jwks_url=JWKS_URL,
        static_keys=dict(STATIC_KEYS),
        bucket_local_root=tmp_path / "buckets",
        fault_firms={"test-firm"},
    )
    return build_app(settings, http_transport=jwks_transport)


def _offline_run(app, misbehave=frozenset(), max_requests=30):
    from fastapi.testclient import TestClient

    with TestClient(app, base_url=BASE_URL) as client:
        mcp = Mcp(client)
        mcp.initialize()
        model = ScriptedModel(
            mcp.call, canned.for_step, company="Fixture Co Offline", misbehave=misbehave
        )
        conversation = Conversation(
            model,
            model=DEFAULT_MODEL,
            system=skill_prompt(),
            mcp_url=f"{BASE_URL}/mcp",
            token=STATIC_KEYS["test-firm"],
            max_requests=max_requests,
        )
        record = conversation.run(OPENING.format(company="Fixture Co Offline", template=TEMPLATE))
        view = server_view(
            lambda path, params: client.get(path, params=params, headers=key_headers()),
            record.deal(),
        )
    return record, view, model


def test_a_run_that_follows_the_method_passes_every_check(fault_app):
    record, view, model = _offline_run(fault_app)
    assert check(record, view) == []
    assert record.stop == "down"
    assert any(e.approves for e in record.events)
    # The harness resumed at least one paused turn without a partner message.
    assert any(p["messages"][-1]["role"] == "assistant" for p in model.payloads)
    # The system prompt is the skill, and the run is priced.
    assert model.payloads[0]["system"] == skill_prompt()
    assert record.cost_usd > 0


@pytest.mark.parametrize(
    ("misbehave", "caught"),
    [
        ("approve_without_showing", "saved as approved before the partner approved it"),
        ("ignore_skip", "never told the partner"),
        ("continue_after_down", "kept calling tools after the down"),
    ],
)
def test_the_checks_catch_each_broken_rule(fault_app, misbehave, caught):
    record, view, _ = _offline_run(fault_app, misbehave=frozenset({misbehave}))
    failures = check(record, view)
    assert any(caught in f for f in failures), failures


def test_without_the_fault_hook_the_checks_report_no_skip_and_no_down(tmp_path, jwks_transport):
    """The same run on a server that hasn't opted test-firm in: no faults fire."""
    from src.connector import faults
    from src.connector.app import build_app

    root = tmp_path / "firms"
    provision(root, "test-firm", entity_id="ent_test_firm")
    faults.install_outline(root, "test-firm")
    settings = ConnectorSettings(
        io_root=root,
        public_base_url=BASE_URL,
        static_keys=dict(STATIC_KEYS),
        bucket_local_root=tmp_path / "buckets",
    )
    record, view, _ = _offline_run(
        build_app(settings, http_transport=jwks_transport), max_requests=12
    )
    failures = check(record, view)
    assert record.stop == "capped"
    assert any("forced down never happened" in f for f in failures), failures
    assert any("reported the research.sources skip 0 times" in f for f in failures), failures

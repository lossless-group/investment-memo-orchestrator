"""Notify the firm's site when a memo compiles (CONN-HOOK-01 to CONN-HOOK-06).

After a new compiled version is saved, MemoPop POSTs a signed ``memo.compiled``
event to the firm's ``site_hook_url`` so the site can drop its cached copy.
Spec: ``context-v/specs/Notify-Firm-Sites-When-a-Memo-Compiles.md``. Every key
and URL here is fake; no request leaves the test (an ``httpx.MockTransport``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import shutil
import sys
import threading
from pathlib import Path

import httpx
import pytest

from src.connector import site_hook
from src.connector.compile import pipeline

from .conftest import call, deal_json
from .fake_claude import Direct, FakeClaude

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

SITE_KEY = "site-test-firm-fake-7h8i9j"
HOOK_URL = "https://www.example-firm.vc/api/memopop/revalidate"


class Hook:
    """A fake site endpoint: records each request and answers from ``responses``."""

    def __init__(self, *responses):
        self.requests: list[httpx.Request] = []
        self.responses = list(responses) or [204]
        self.lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.requests.append(request)
            answer = self.responses[min(len(self.requests), len(self.responses)) - 1]
        if callable(answer):
            answer = answer(request)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer)


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Backoff waits are recorded, never slept."""
    waited: list[float] = []
    monkeypatch.setattr(site_hook, "sleep", waited.append)
    return waited


@pytest.fixture
def hook(monkeypatch, sleeps):
    def install(*responses) -> Hook:
        fake = Hook(*responses)
        monkeypatch.setattr(site_hook, "transport", httpx.MockTransport(fake))
        return fake

    return install


def configure(ws, *, url: str | None = HOOK_URL, key: str | None = SITE_KEY) -> None:
    ws.settings.site_keys = {ws.firm: key} if key else {}
    path = ws.root / "firm.json"
    config = json.loads(path.read_text()) if path.exists() else {}
    config.pop("site_hook_url", None)
    if url:
        config["site_hook_url"] = url
    path.write_text(json.dumps(config))


def drafted(ws) -> str:
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, until=lambda s: s["phase"] == "enhance", compile=False)
    return deal


def edit_a_section(ws, deal: str, line: str) -> None:
    state = json.loads(deal_json(ws, deal).read_text())
    draft = ws.root / "deals" / deal / state["artifacts"]["draft.section:01-overview"]["path"]
    draft.write_text(draft.read_text() + f"\n{line}\n")


def settled() -> None:
    assert site_hook.wait_for_senders(10) == 0, "a notification is still being sent"


def verify(request: httpx.Request, key: str = SITE_KEY) -> None:
    timestamp = request.headers["x-memopop-timestamp"]
    expected = hmac.new(
        key.encode(), timestamp.encode() + b"." + request.content, hashlib.sha256
    ).hexdigest()
    assert request.headers["x-memopop-signature"] == f"sha256={expected}"


# ------------------------------------------------------------------ CONN-HOOK-01


@pytest.mark.spec("CONN-HOOK-01")
def test_a_compile_sends_one_signed_memo_compiled_request_to_the_firms_hook(ws, hook):
    configure(ws)
    site = hook(204)
    deal = drafted(ws)

    reply = call(ws, "compile", deal=deal, formats=["html"])
    settled()

    (request,) = site.requests
    assert request.method == "POST"
    assert str(request.url) == HOOK_URL
    assert request.headers["content-type"] == "application/json"
    assert request.headers["x-memopop-timestamp"].isdigit()
    verify(request)
    state = json.loads(deal_json(ws, deal).read_text())
    assert json.loads(request.content) == {
        "event": "memo.compiled",
        "firm": "test-firm",
        "deal": deal,
        "version": reply["version"],
        "label": reply["label"],
        "compiled_at": state["compiled"]["at"],
    }


@pytest.mark.spec("CONN-HOOK-01")
def test_the_timestamp_is_unix_seconds_from_the_injected_clock(ws, hook, monkeypatch):
    configure(ws)
    site = hook(204)
    monkeypatch.setattr(site_hook, "clock", lambda: 1763776800.7)
    call(ws, "compile", deal=drafted(ws), formats=["html"])
    settled()
    (request,) = site.requests
    assert request.headers["x-memopop-timestamp"] == "1763776800"
    verify(request)


@pytest.mark.spec("CONN-HOOK-01")
def test_each_new_version_notifies_once_and_a_compile_that_changes_nothing_does_not(ws, hook):
    configure(ws)
    site = hook(204)
    deal = drafted(ws)

    call(ws, "compile", deal=deal, formats=["html"])
    settled()
    call(ws, "compile", deal=deal, formats=["html"])  # same sections, same version
    settled()
    assert len(site.requests) == 1

    edit_a_section(ws, deal, "A sentence the partner added.")
    second = call(ws, "compile", deal=deal, formats=["html"])
    settled()
    assert second["version"] == 2
    assert [json.loads(r.content)["version"] for r in site.requests] == [1, 2]


# ------------------------------------------------------------------ CONN-HOOK-02


@pytest.mark.spec("CONN-HOOK-02")
def test_no_request_without_a_hook_url_and_the_compile_still_succeeds(ws, hook, caplog):
    configure(ws, url=None)
    site = hook(204)
    with caplog.at_level(logging.INFO, logger="memopop.connector.site_hook"):
        reply = call(ws, "compile", deal=drafted(ws), formats=["html"])
        settled()
    assert reply["version"] == 1 and reply["html_url"]
    assert site.requests == []
    assert any("no site_hook_url" in r.getMessage() for r in caplog.records)


@pytest.mark.spec("CONN-HOOK-02")
def test_no_request_without_a_site_key_and_the_compile_still_succeeds(ws, hook, caplog):
    configure(ws, key=None)
    site = hook(204)
    with caplog.at_level(logging.INFO, logger="memopop.connector.site_hook"):
        reply = call(ws, "compile", deal=drafted(ws), formats=["html"])
        settled()
    assert reply["version"] == 1 and reply["html_url"]
    assert site.requests == []
    assert any("no site key" in r.getMessage() for r in caplog.records)


@pytest.mark.spec("CONN-HOOK-02")
def test_a_hook_url_that_is_not_http_sends_nothing(ws, hook):
    configure(ws, url="file:///etc/passwd")
    site = hook(204)
    assert call(ws, "compile", deal=drafted(ws), formats=["html"])["version"] == 1
    settled()
    assert site.requests == []


# ------------------------------------------------------------------ CONN-HOOK-03


@pytest.mark.spec("CONN-HOOK-03")
def test_a_slow_hook_never_delays_the_compile_reply(ws, hook):
    configure(ws)
    entered, release = threading.Event(), threading.Event()

    def stuck(request):
        entered.set()
        assert release.wait(20), "the test never released the hook"
        return 204

    site = hook(stuck)
    deal = drafted(ws)
    try:
        reply = call(ws, "compile", deal=deal, formats=["html"])
        assert reply["version"] == 1
        assert entered.wait(10), "the notification was never sent"
        assert len(site.requests) == 1  # still in flight while the reply is back
    finally:
        release.set()
    settled()


@pytest.mark.spec("CONN-HOOK-03")
def test_a_5xx_is_retried_three_times_with_backoff_and_the_compile_still_succeeds(ws, hook, sleeps):
    configure(ws)
    site = hook(503)
    reply = call(ws, "compile", deal=drafted(ws), formats=["html"])
    settled()
    assert reply["version"] == 1
    assert len(site.requests) == 1 + 3
    assert sleeps == [1.0, 5.0, 25.0]
    for request in site.requests:
        verify(request)


@pytest.mark.spec("CONN-HOOK-03")
def test_a_timeout_or_connection_error_is_retried_and_stops_at_the_first_success(ws, hook, sleeps):
    configure(ws)
    site = hook(httpx.ReadTimeout("slow"), httpx.ConnectError("refused"), 204)
    call(ws, "compile", deal=drafted(ws), formats=["html"])
    settled()
    assert len(site.requests) == 3
    assert sleeps == [1.0, 5.0]
    timeout = site.requests[0].extensions["timeout"]
    assert timeout["connect"] == timeout["read"] == site_hook.TIMEOUT_SECONDS == 5.0


@pytest.mark.spec("CONN-HOOK-03")
def test_a_4xx_is_not_retried(ws, hook, sleeps):
    configure(ws)
    site = hook(401)
    assert call(ws, "compile", deal=drafted(ws), formats=["html"])["version"] == 1
    settled()
    assert len(site.requests) == 1
    assert sleeps == []


# ------------------------------------------------------------------ CONN-HOOK-04


@pytest.mark.spec("CONN-HOOK-04")
def test_a_failed_compile_sends_nothing(ws, hook, monkeypatch):
    configure(ws)
    site = hook(204)
    deal = drafted(ws)

    def broken(ctx):
        raise RuntimeError("finalize broke")

    monkeypatch.setitem(pipeline.STAGE_IMPLS, "compile.finalize", broken)
    with pytest.raises(Exception):  # noqa: B017 - how it surfaces isn't this test's business
        call(ws, "compile", deal=deal, formats=["html"])
    settled()
    assert site.requests == []
    assert json.loads(deal_json(ws, deal).read_text()).get("compiled") in (None, {})


@pytest.mark.spec("CONN-HOOK-04")
def test_a_refused_compile_sends_nothing(ws, hook):
    configure(ws)
    site = hook(204)
    deal = FakeClaude(Direct(ws)).create()  # nothing drafted: drafts_incomplete
    with pytest.raises(Exception):  # noqa: B017
        call(ws, "compile", deal=deal)
    settled()
    assert site.requests == []


# ------------------------------------------------------------------ CONN-HOOK-05


def copy_deal(ws, source: str, dest_root: Path, name: str, bump: bool = False) -> None:
    """Stage ``source``'s folder as deal ``name``, optionally as a newer compiled version."""
    dest = dest_root / "deals" / name
    shutil.copytree(ws.root / "deals" / source, dest)
    state = json.loads((dest / "deal.json").read_text())
    state["deal"] = name
    if bump:
        state["compiled"] = {
            **state["compiled"],
            "version": state["compiled"]["version"] + 1,
            "label": "v0.0.9",
            "sha256": "f" * 64,
        }
    (dest / "deal.json").write_text(json.dumps(state))


@pytest.mark.spec("CONN-HOOK-05")
def test_the_uploader_notifies_once_per_deal_whose_compiled_version_changed(ws, hook, tmp_path):
    import apply_upload

    configure(ws, url=None)  # the deals' own compiles shouldn't count
    base = drafted(ws)
    call(ws, "compile", deal=base, formats=["html"])
    settled()
    existing = tmp_path / "existing"
    for name in ("same-co", "newer-co"):
        copy_deal(ws, base, existing, name)
        shutil.copytree(existing / "deals" / name, ws.root / "deals" / name)

    staged = tmp_path / "staged"
    copy_deal(ws, base, staged, "same-co")  # unchanged compiled version
    copy_deal(ws, base, staged, "newer-co", bump=True)  # a newer compiled version
    copy_deal(ws, base, staged, "new-co")  # not on the server before

    configure(ws)
    site = hook(204)
    changed = apply_upload.replace_deals(ws, staged, ["same-co", "newer-co", "new-co"])
    assert site.requests == []  # nothing is sent before the change is recorded
    apply_upload.notify_site(ws, changed)
    settled()

    assert sorted(changed) == ["new-co", "newer-co"]
    sent = sorted(
        (json.loads(r.content)["deal"], json.loads(r.content)["version"]) for r in site.requests
    )
    assert sent == [("new-co", 1), ("newer-co", 2)]
    for request in site.requests:
        verify(request)
        assert json.loads(request.content)["event"] == "memo.compiled"
    assert (
        json.loads((ws.root / "deals" / "newer-co" / "deal.json").read_text())["compiled"]["label"]
        == "v0.0.9"
    )


@pytest.mark.spec("CONN-HOOK-05")
def test_the_uploader_sends_nothing_for_a_deal_with_no_compiled_version(ws, hook, tmp_path):
    import apply_upload

    configure(ws)
    deal = drafted(ws)  # drafted, never compiled
    staged = tmp_path / "staged"
    shutil.copytree(ws.root / "deals" / deal, staged / "deals" / "draft-co")
    site = hook(204)
    changed = apply_upload.replace_deals(ws, staged, ["draft-co"])
    assert changed == []
    apply_upload.notify_site(ws, changed)
    settled()
    assert site.requests == []


# ------------------------------------------------------------------ CONN-HOOK-06


@pytest.mark.spec("CONN-HOOK-06")
def test_the_body_carries_no_memo_text_links_or_key_and_logs_carry_no_secret(ws, hook, caplog):
    configure(ws)
    site = hook(503, 204)
    deal = drafted(ws)
    with caplog.at_level(logging.DEBUG):
        reply = call(ws, "compile", deal=deal, formats=["html"])
        settled()

    memo = call(ws, "get_artifact", deal=deal, artifact_id="compile.assemble")["text"]
    signatures = {r.headers["x-memopop-signature"] for r in site.requests}
    for request in site.requests:
        raw = request.content.decode()
        body = json.loads(raw)
        assert set(body) == {"event", "firm", "deal", "version", "label", "compiled_at"}
        assert SITE_KEY not in raw
        assert "http" not in raw and "://" not in raw
        assert reply["html_url"] not in raw
        assert all(len(line) < 40 or line not in raw for line in memo.splitlines())

    hook_logs = [r for r in caplog.records if r.name == "memopop.connector.site_hook"]
    assert len(hook_logs) >= 2  # one per attempt
    for record in caplog.records:
        text = record.getMessage()
        assert SITE_KEY not in text
        assert not any(sig in text or sig.removeprefix("sha256=") in text for sig in signatures)
    attempt = hook_logs[0].getMessage()
    assert "test-firm" in attempt and deal in attempt and "503" in attempt

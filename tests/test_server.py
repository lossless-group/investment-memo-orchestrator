"""Targeted unit tests for the FastAPI sidecar.

These don't run `generate_memo()` — that's a 15-45 minute LLM-driven workflow.
They cover the parts of `src/server/` that are tricky or security-sensitive:
log-line splitting, event bus replay, path-traversal guard, request validation,
and the unknown-job 404 path.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.server.app import app, resolve_artifact_path, scaffold_firm_deal_dir
from src.server.events import JobEventBus, LogSink
from src.server.log_persistence import persist_job_logs
from src.server.milestones import MilestoneExtractor
from src.server.models import CreateMemoRequest


# --- HTTP-shape tests via TestClient (lifespan handles the registry setup) ---


def test_create_memo_request_rejects_empty_body():
    """POST /memos with `{}` should fail Pydantic validation with a 422 + detail."""
    with TestClient(app) as client:
        response = client.post("/memos", json={})
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body
        # Must mention the missing required field by name.
        flat = str(body["detail"])
        assert "company_name" in flat


def test_get_unknown_job_returns_404():
    """GET /memos/{nonexistent} returns the dispatcher's 'job not found' shape."""
    with TestClient(app) as client:
        response = client.get("/memos/does-not-exist")
        assert response.status_code == 404
        assert response.json() == {"detail": "job not found"}


# --- LogSink: line-splitting behavior ---


class _StubBus:
    """Captures published events without needing an asyncio loop."""

    def __init__(self):
        self.events: list[dict] = []

    def publish(self, event: dict) -> None:
        self.events.append(event)


def test_log_sink_splits_on_newlines():
    """Multi-line writes must produce one event per complete line."""
    bus = _StubBus()
    sink = LogSink(bus)  # type: ignore[arg-type]

    sink.write("alpha\nbeta\ngamma\n")

    lines = [e["line"] for e in bus.events if e["type"] == "log"]
    assert lines == ["alpha", "beta", "gamma"]


def test_log_sink_buffers_partial_line_until_flush():
    """A trailing partial (no newline) stays in the buffer until flush()."""
    bus = _StubBus()
    sink = LogSink(bus)  # type: ignore[arg-type]

    sink.write("alpha\nbeta")  # 'beta' is a partial line — no newline yet
    lines_before = [e["line"] for e in bus.events]
    assert lines_before == ["alpha"]

    sink.flush()
    lines_after = [e["line"] for e in bus.events]
    assert lines_after == ["alpha", "beta"]


# --- JobEventBus: backlog replay for late subscribers ---


@pytest.mark.asyncio
async def test_event_bus_replays_backlog_to_late_subscribers():
    """A subscriber arriving after publishes must see the backlog, then live tail."""
    loop = asyncio.get_running_loop()
    bus = JobEventBus(loop)

    # Publish 3 events before any subscriber exists.
    bus.publish({"type": "status", "status": "queued"})
    bus.publish({"type": "log", "line": "starting"})
    bus.publish({"type": "log", "line": "researching"})

    # Subscribe and pull the backlog non-blockingly with a small timeout.
    received: list[dict] = []

    async def consume():
        async for event in bus.subscribe():
            received.append(event)
            if len(received) == 4:  # 3 backlog + 1 live = stop
                return

    consumer_task = asyncio.create_task(consume())

    # Tiny yield so the subscriber registers before the live publish.
    await asyncio.sleep(0.01)
    bus.publish({"type": "log", "line": "writing"})

    await asyncio.wait_for(consumer_task, timeout=2.0)

    assert len(received) == 4
    assert received[0]["status"] == "queued"
    assert received[1]["line"] == "starting"
    assert received[2]["line"] == "researching"
    assert received[3]["line"] == "writing"


# --- Path-traversal guard on artifact endpoint ---


def test_milestone_extractor_recognizes_known_prints():
    """Real-shaped agent prints map to structured milestones with correct stages."""
    extractor = MilestoneExtractor()

    cases = [
        (
            "📁 Created new output directory: output/Stripe-v0.0.1 (v0.0.1)",
            "start",
            "Run started",
        ),
        (
            "🔍 PERPLEXITY SECTION RESEARCH (PARALLEL)",
            "research",
            "Researching sections",
        ),
        (
            "  ✓ [03] Market Context: 18 citations",
            "research",
            "Researched: Market Context",
        ),
        (
            "✅ SECTION RESEARCH COMPLETE (PARALLEL)",
            "research",
            "Section research done",
        ),
        (
            "  [4/10] Team",
            "writing",
            "Drafting: Team",
        ),
        (
            "✅ All 10 sections complete using outline: direct-investment",
            "writing",
            "All 10 sections drafted",
        ),
        (
            "✓ Reassembled final draft: 12345 words",
            "assembly",
            "Final draft assembled",
        ),
    ]

    for line, expected_stage, expected_label in cases:
        m = extractor.process(line)
        assert m is not None, f"No milestone matched: {line!r}"
        assert m["type"] == "milestone"
        assert m["stage"] == expected_stage, f"Wrong stage for {line!r}"
        assert m["label"] == expected_label, f"Wrong label for {line!r}"


def test_milestone_extractor_dedupes_static_milestones():
    """A repeat of a parameterless print (e.g., from a summary block) doesn't refire."""
    extractor = MilestoneExtractor()
    line = "✅ SECTION RESEARCH COMPLETE (PARALLEL)"
    first = extractor.process(line)
    second = extractor.process(line)
    assert first is not None
    assert second is None  # deduped


def test_milestone_extractor_ignores_unmatched_lines():
    """Garden-variety log lines without a known pattern produce no milestone."""
    extractor = MilestoneExtractor()
    assert extractor.process("INFO: starting up") is None
    assert extractor.process("Some random debug line") is None
    assert extractor.process("") is None


def test_scaffold_firm_deal_dir_writes_config(tmp_path, monkeypatch):
    """A firm-scoped POST creates `io/{firm}/deals/{deal}/inputs/deal.json` so the
    orchestrator's `resolve_deal_context()` finds it instead of falling back to legacy."""
    monkeypatch.setenv("MEMO_IO_ROOT", str(tmp_path / "io"))
    request = CreateMemoRequest(
        company_name="ChromaDB",
        investment_type="direct",
        memo_mode="consider",
        firm="alpha-partners",
        company_url="https://chromadb.com",
        outline_name="standard-direct-investment",
    )

    scaffold_firm_deal_dir(request)

    deal_json = tmp_path / "io" / "alpha-partners" / "deals" / "ChromaDB" / "inputs" / "deal.json"
    assert deal_json.exists(), f"Expected {deal_json} to be created"

    import json as _json
    config = _json.loads(deal_json.read_text())
    assert config["type"] == "direct"
    assert config["mode"] == "consider"
    assert config["url"] == "https://chromadb.com"
    assert config["outline"] == "standard-direct-investment"


def test_scaffold_firm_deal_dir_preserves_existing_config(tmp_path, monkeypatch):
    """A pre-existing config (e.g., from CLI use) must not be overwritten."""
    monkeypatch.setenv("MEMO_IO_ROOT", str(tmp_path / "io"))
    deal_json = (
        tmp_path
        / "io"
        / "alpha-partners"
        / "deals"
        / "ChromaDB"
        / "inputs"
        / "deal.json"
    )
    deal_json.parent.mkdir(parents=True)
    original = '{"type": "direct", "mode": "justify", "notes": "hand-curated"}\n'
    deal_json.write_text(original)

    request = CreateMemoRequest(
        company_name="ChromaDB",
        investment_type="direct",
        memo_mode="consider",  # different from existing 'justify'
        firm="alpha-partners",
    )
    scaffold_firm_deal_dir(request)

    assert deal_json.read_text() == original, "Existing config was overwritten"


def test_scaffold_firm_deal_dir_skipped_without_firm(tmp_path, monkeypatch):
    """Legacy (non-firm) runs must not create any io/ scaffolding."""
    monkeypatch.setenv("MEMO_IO_ROOT", str(tmp_path / "io"))
    request = CreateMemoRequest(
        company_name="ChromaDB",
        investment_type="direct",
        memo_mode="consider",
        # firm omitted
    )
    scaffold_firm_deal_dir(request)
    assert not (tmp_path / "io").exists(), "io/ should not be created without a firm"


def test_persist_job_logs_writes_run_dir_and_global_mirror(tmp_path, monkeypatch):
    """Happy path: both `{output_dir}/server-log.{jsonl,txt}` and the global mirror
    under `.logs/runs/` are written, with the JSONL containing every event."""
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "io" / "alpha-partners" / "deals" / "ChromaDB" / "outputs" / "ChromaDB-v0.0.1"
    out.mkdir(parents=True)

    events = [
        {"type": "status", "ts": "2026-05-01T18:00:00Z", "status": "queued"},
        {"type": "status", "ts": "2026-05-01T18:00:01Z", "status": "running"},
        {"type": "log", "ts": "2026-05-01T18:00:02Z", "line": "📁 Created new output directory: ..."},
        {
            "type": "milestone",
            "ts": "2026-05-01T18:00:02Z",
            "stage": "research",
            "level": "success",
            "label": "Section research done",
        },
        {"type": "complete", "ts": "2026-05-01T18:30:00Z", "output_dir": str(out), "version": "v0.0.1"},
    ]

    written = persist_job_logs(
        job_id="abc123",
        company_name="ChromaDB",
        output_dir=str(out),
        version="v0.0.1",
        events=events,
    )

    # Run-dir pair exists.
    run_jsonl = out / "server-log.jsonl"
    run_txt = out / "server-log.txt"
    assert run_jsonl.exists(), "server-log.jsonl missing in output dir"
    assert run_txt.exists(), "server-log.txt missing in output dir"

    # JSONL has one event per line, structurally identical.
    parsed = [__import__("json").loads(l) for l in run_jsonl.read_text().splitlines() if l]
    assert len(parsed) == len(events)
    assert parsed[3]["type"] == "milestone"
    assert parsed[3]["label"] == "Section research done"

    # Plain text has milestone rendered with the ◆ marker.
    txt = run_txt.read_text()
    assert "◆ [research] Section research done" in txt
    assert "▸ status: queued" in txt
    assert "✓ complete" in txt

    # Global mirror exists with the conventional filename.
    global_jsonl = tmp_path / ".logs" / "runs" / "abc123__ChromaDB-v0.0.1.jsonl"
    global_txt = tmp_path / ".logs" / "runs" / "abc123__ChromaDB-v0.0.1.txt"
    assert global_jsonl.exists()
    assert global_txt.exists()
    assert global_jsonl.read_text() == run_jsonl.read_text()

    # The returned dict points at all four paths.
    assert "run_jsonl" in written and "global_jsonl" in written


def test_persist_job_logs_writes_global_only_when_no_output_dir(tmp_path, monkeypatch):
    """Early failures (no output_dir) still leave a global trail under .logs/runs."""
    monkeypatch.chdir(tmp_path)
    events = [
        {"type": "status", "ts": "2026-05-01T18:00:00Z", "status": "running"},
        {
            "type": "error",
            "ts": "2026-05-01T18:00:01Z",
            "message": "ANTHROPIC_API_KEY not set",
            "traceback": "Traceback (most recent call last):\n  File ...\nValueError: ...",
        },
    ]
    written = persist_job_logs(
        job_id="early1",
        company_name="Stripe",
        output_dir=None,
        version=None,
        events=events,
    )

    # Run-dir paths absent.
    assert "run_jsonl" not in written
    assert "run_txt" not in written

    # Global mirror is the only trail and contains the traceback.
    global_txt = tmp_path / ".logs" / "runs" / "early1__Stripe.txt"
    assert global_txt.exists()
    text = global_txt.read_text()
    assert "✗ error: ANTHROPIC_API_KEY not set" in text
    assert "Traceback" in text


def test_persist_job_logs_sanitizes_unsafe_company_names(tmp_path, monkeypatch):
    """Company names with slashes / colons / spaces don't blow up the global filename."""
    monkeypatch.chdir(tmp_path)
    written = persist_job_logs(
        job_id="dangerz",
        company_name="Acme/Co: ../etc/passwd",
        output_dir=None,
        version=None,
        events=[{"type": "log", "ts": "2026-05-01T18:00:00Z", "line": "hello"}],
    )
    # Should land in .logs/runs with all unsafe chars replaced.
    assert (tmp_path / ".logs" / "runs").exists()
    files = sorted((tmp_path / ".logs" / "runs").iterdir())
    assert any(p.name.startswith("dangerz__") for p in files)
    # No path-traversal happened.
    assert not (tmp_path / "etc" / "passwd").exists()


def test_version_manager_never_overwrites_existing_dir(tmp_path):
    """A version directory present on disk must force the next version higher,
    even if it isn't recorded in versions.json (manual moves, lost registry,
    crashed-before-record runs)."""
    from src.versioning import VersionManager

    firm = "alpha-partners"
    deals = tmp_path / "io" / firm / "deals" / "ChromaDB" / "outputs"
    deals.mkdir(parents=True)

    # Existing version on disk; nothing in versions.json yet.
    (deals / "ChromaDB-v0.0.1").mkdir()

    vm = VersionManager(firm=firm, io_root=tmp_path / "io")
    next_v = vm.get_next_version("ChromaDB")

    assert str(next_v) == "v0.0.2", f"Expected v0.0.2 (disk had v0.0.1), got {next_v}"


def test_version_manager_takes_max_of_disk_and_registry(tmp_path):
    """When both disk and versions.json have records, the next version must
    bump above the higher of the two."""
    from src.versioning import VersionManager

    firm = "alpha-partners"
    deals = tmp_path / "io" / firm / "deals" / "ChromaDB" / "outputs"
    deals.mkdir(parents=True)
    (deals / "ChromaDB-v0.0.1").mkdir()
    (deals / "ChromaDB-v0.0.3").mkdir()  # higher than the registry

    versions_file = tmp_path / "io" / firm / "versions.json"
    versions_file.write_text(
        json.dumps(
            {
                "ChromaDB": {
                    "latest_version": "v0.0.2",
                    "history": [{"version": "v0.0.2", "timestamp": "2026-01-01"}],
                }
            }
        )
    )

    vm = VersionManager(firm=firm, io_root=tmp_path / "io")
    next_v = vm.get_next_version("ChromaDB")

    assert str(next_v) == "v0.0.4", f"Expected v0.0.4 (disk max v0.0.3 wins), got {next_v}"


def test_version_manager_first_run_is_v001(tmp_path):
    """No prior history anywhere → first run gets v0.0.1."""
    from src.versioning import VersionManager

    vm = VersionManager(firm="alpha-partners", io_root=tmp_path / "io")
    assert str(vm.get_next_version("BrandNewCo")) == "v0.0.1"


def test_artifact_path_traversal_rejected(tmp_path):
    """resolve_artifact_path must reject `../...` that escapes the output dir."""
    out = tmp_path / "job-output"
    out.mkdir()
    (out / "result.md").write_text("# memo\n")

    # Legit subpath resolves successfully.
    safe = resolve_artifact_path(out, "result.md")
    assert safe == (out / "result.md").resolve()

    # Path traversal attempts must raise HTTPException(400).
    for evil in ["../../../etc/passwd", "../secrets.txt", "/etc/passwd"]:
        with pytest.raises(HTTPException) as exc_info:
            resolve_artifact_path(out, evil)
        assert exc_info.value.status_code == 400
        assert "escapes" in exc_info.value.detail

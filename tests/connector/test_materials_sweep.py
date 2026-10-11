"""The stale-materials sweep (a plan 4 follow-up, built in plan 2).

A material could stay ``queued`` forever, so ``materials_pending`` never
reached zero, in two ways: an upload link that expired unused, and a server
restart while a link was being fetched or a file extracted (jobs run in the
process, so a restart drops them). The sweep marks such a material
``skipped`` with ``material_unreadable`` and a reason. It runs on startup (the
app's lifespan) and lazily when ``list_deals`` or ``next_step`` reads a deal.

Not spec IDs: the spec already promises that materials never block; these pin
the mechanism. Server modules are imported inside the tests.
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from src.connector.app import build_app
from src.connector.materials import uploads

from .conftest import BASE_URL, call, deal_json, new_deal


def pipeline():
    return importlib.import_module("src.connector.materials.pipeline")


def state_of(ws, deal: str) -> dict:
    return json.loads(deal_json(ws, deal).read_text())


def record(ws, deal: str, material_id: str) -> dict:
    (found,) = [m for m in state_of(ws, deal)["materials"] if m["material_id"] == material_id]
    return found


def pending(ws, deal: str) -> int:
    (row,) = [d for d in call(ws, "list_deals")["deals"] if d["deal"] == deal]
    return row["materials_pending"]


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def plant_in_flight(ws, deal: str, material_id: str, added: datetime) -> None:
    """A link material whose background job was running when the server stopped."""
    state = state_of(ws, deal)
    state["materials"].append(
        {
            "material_id": material_id,
            "kind": "deck",
            "status": "queued",
            "source": "link",
            "title": "https://example.org/deck.pdf",
            "link": "https://example.org/deck.pdf",
            "added_at": iso(added),
        }
    )
    deal_json(ws, deal).write_text(json.dumps(state, indent=2))


def awaiting_upload(ws, deal: str) -> str:
    body = call(ws, "add_materials", deal=deal, items=[{"kind": "deck", "filename": "deck.pdf"}])
    return body["accepted"][0]["material_id"]


# ------------------------------------------------------------------ expired uploads


def test_an_upload_link_that_expires_unused_becomes_a_skip(ws, monkeypatch):
    deal = new_deal(ws)
    mid = awaiting_upload(ws, deal)
    assert pending(ws, deal) == 1

    later = uploads.now() + uploads.TTL_SECONDS + pipeline().UPLOAD_GRACE_SECONDS + 1
    monkeypatch.setattr(uploads, "now", lambda: later)

    assert pending(ws, deal) == 0
    rec = record(ws, deal, mid)
    assert rec["status"] == "skipped"
    assert "expired" in rec["error"]
    (skip,) = state_of(ws, deal)["skips"]
    assert skip["code"] == "material_unreadable"
    assert skip["material_id"] == mid
    assert "expired" in skip["reason"]


def test_an_upload_link_still_inside_its_hour_is_left_queued(ws, monkeypatch):
    deal = new_deal(ws)
    mid = awaiting_upload(ws, deal)
    soon = uploads.now() + uploads.TTL_SECONDS - 60
    monkeypatch.setattr(uploads, "now", lambda: soon)
    assert pending(ws, deal) == 1
    assert record(ws, deal, mid)["status"] == "queued"
    assert state_of(ws, deal)["skips"] == []


def test_next_step_reads_the_deal_and_sweeps_it_too(ws, monkeypatch):
    deal = new_deal(ws)
    mid = awaiting_upload(ws, deal)
    later = uploads.now() + uploads.TTL_SECONDS + pipeline().UPLOAD_GRACE_SECONDS + 1
    monkeypatch.setattr(uploads, "now", lambda: later)

    body = call(ws, "next_step", deal=deal)
    assert record(ws, deal, mid)["status"] == "skipped"
    assert [s["code"] for s in body["skipped_since_last_call"]] == ["material_unreadable"]


# ------------------------------------------------------------------ jobs lost to a restart


def test_a_job_older_than_its_deadline_is_skipped_when_the_deal_is_read(ws):
    deal = new_deal(ws)
    old = datetime.now(UTC) - timedelta(seconds=pipeline().PROCESSING_DEADLINE_SECONDS + 60)
    plant_in_flight(ws, deal, "mat-0000000000000001", old)
    plant_in_flight(ws, deal, "mat-0000000000000002", datetime.now(UTC))

    assert pending(ws, deal) == 1
    assert record(ws, deal, "mat-0000000000000001")["status"] == "skipped"
    assert record(ws, deal, "mat-0000000000000002")["status"] == "queued"


def test_startup_skips_jobs_a_restart_dropped(settings, ws, jwks_transport):
    deal = new_deal(ws)
    plant_in_flight(ws, deal, "mat-0000000000000003", datetime.now(UTC))
    awaiting = awaiting_upload(ws, deal)

    with TestClient(build_app(settings, http_transport=jwks_transport), base_url=BASE_URL):
        pass  # entering the lifespan is the startup

    rec = record(ws, deal, "mat-0000000000000003")
    assert rec["status"] == "skipped"
    assert "restart" in rec["error"]
    # An upload link still inside its hour can still be used after a restart.
    assert record(ws, deal, awaiting)["status"] == "queued"
    (skip,) = state_of(ws, deal)["skips"]
    assert skip["code"] == "material_unreadable"


def test_sweep_all_covers_every_firm(settings, ws):
    other = importlib.import_module("src.connector.workspace").open_workspace(
        settings, "other-firm"
    )
    a, b = new_deal(ws), new_deal(other)
    plant_in_flight(ws, a, "mat-00000000000000a1", datetime.now(UTC))
    plant_in_flight(other, b, "mat-00000000000000b1", datetime.now(UTC))

    assert pipeline().sweep_all(settings, restarted=True) == 2
    assert record(ws, a, "mat-00000000000000a1")["status"] == "skipped"
    assert record(other, b, "mat-00000000000000b1")["status"] == "skipped"
    assert pipeline().sweep_all(settings, restarted=True) == 0  # idempotent


def test_a_job_that_finishes_after_the_sweep_does_not_undo_the_skip(ws):
    deal = new_deal(ws)
    plant_in_flight(ws, deal, "mat-0000000000000004", datetime.now(UTC))
    pipeline().sweep_deal(ws, deal, restarted=True)

    pipeline().mark_ready(ws, deal, "mat-0000000000000004", "late text")
    assert record(ws, deal, "mat-0000000000000004")["status"] == "skipped"
    assert len(state_of(ws, deal)["skips"]) == 1

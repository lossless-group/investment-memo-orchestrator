"""Deals: create_new_deal and list_deals (CONN-DEAL-01 to CONN-DEAL-05)."""

from __future__ import annotations

import pytest

from src.connector.errors import ConnectorError
from src.connector.workspace import open_workspace

from .conftest import SECTIONS, TEMPLATE, call, deal_json, new_deal


@pytest.mark.spec("CONN-DEAL-01")
def test_create_new_deal_uses_the_templates_sections(ws, settings):
    body = call(
        ws,
        "create_new_deal",
        company="Fixture Co",
        url="https://www.fixture.co/about",
        template=TEMPLATE,
        stage="Seed",
    )
    assert body["created"] is True
    assert body["deal"] == "fixture-co"
    assert body["template"] == TEMPLATE
    assert [s["key"] for s in body["sections"]] == SECTIONS
    assert [s["name"] for s in body["sections"]] == ["Overview", "Market", "Team"]
    assert deal_json(ws, "fixture-co").is_file()

    listed = call(ws, "list_deals")["deals"]
    assert [(d["deal"], d["company"], d["stage"], d["template"]) for d in listed] == [
        ("fixture-co", "Fixture Co", "Seed", TEMPLATE)
    ]

    # Without a url the slug comes from the name; without a template, the firm's default.
    named = call(ws, "create_new_deal", company="Acme Robotics")
    assert named["deal"] == "acme-robotics"
    assert named["template"] == TEMPLATE

    # A firm with no configured default gets direct-early-stage-12Ps from templates/outlines.
    plain = open_workspace(settings, "other-firm")
    (plain.root / "firm.json").write_text("{}")
    default = call(plain, "create_new_deal", company="Default Co")
    assert default["template"] == "direct-early-stage-12Ps"
    assert len(default["sections"]) == 10


@pytest.mark.spec("CONN-DEAL-02")
def test_creating_the_same_company_twice_returns_the_existing_deal(ws):
    first = call(
        ws, "create_new_deal", company="Fixture Co", url="https://fixture.co", template=TEMPLATE
    )
    before = deal_json(ws, first["deal"]).read_bytes()
    for again in (
        {"company": "Fixture Co", "url": "https://fixture.co", "template": TEMPLATE},
        {"company": "Fixture Co", "url": "https://fixture.co/"},
        {"company": "fixture co"},
        {"company": "Fixture Co Inc", "url": "http://www.fixture.co"},
    ):
        body = call(ws, "create_new_deal", **again)
        assert body["created"] is False, again
        assert body["deal"] == first["deal"], again
        assert [s["key"] for s in body["sections"]] == SECTIONS
    assert [d["deal"] for d in call(ws, "list_deals")["deals"]] == [first["deal"]]
    assert sorted(p.name for p in (ws.root / "deals").iterdir()) == [first["deal"]]
    assert deal_json(ws, first["deal"]).read_bytes() == before


@pytest.mark.spec("CONN-DEAL-03")
def test_unknown_template_is_template_not_found(ws):
    for template in ("no-such-template", "../../etc/passwd", "direct-early-stage-12Ps.yaml"):
        with pytest.raises(ConnectorError) as raised:
            call(ws, "create_new_deal", company="Acme", template=template)
        assert (raised.value.kind, raised.value.code) == ("invalid", "template_not_found"), template
        assert raised.value.next
    assert call(ws, "list_deals")["deals"] == []


@pytest.mark.spec("CONN-DEAL-04")
def test_list_deals_pages_with_a_cursor_and_caps_the_limit(ws):
    names = [f"Company {i:03d}" for i in range(105)]
    for name in names:
        call(ws, "create_new_deal", company=name)

    first = call(ws, "list_deals")
    assert len(first["deals"]) == 20  # the default limit
    assert first["next_cursor"]

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        args = {"limit": 30}
        if cursor:
            args["cursor"] = cursor
        page = call(ws, "list_deals", **args)
        pages += 1
        seen += [d["deal"] for d in page["deals"]]
        cursor = page.get("next_cursor")
        if not cursor:
            break
    assert pages == 4
    assert len(seen) == len(set(seen)) == 105

    capped = call(ws, "list_deals", limit=500)
    assert len(capped["deals"]) == 100
    assert capped["next_cursor"]

    with pytest.raises(ConnectorError) as raised:
        call(ws, "list_deals", limit=0)
    assert raised.value.code == "validation_failed"
    with pytest.raises(ConnectorError) as raised:
        call(ws, "list_deals", cursor="not-a-cursor")
    assert raised.value.code == "validation_failed"


@pytest.mark.spec("CONN-DEAL-05")
def test_list_deals_shows_phase_pending_materials_and_skips(settings):
    settings.disabled_steps = {"materials.brief"}
    ws = open_workspace(settings, "test-firm")
    deal = new_deal(ws)

    # Materials arrive in phase 4; their record shape in deal.json is fixed here.
    def add_materials(state):
        state["materials"] = [
            {"material_id": "mat-ready01", "kind": "notes", "status": "ready"},
            {"material_id": "mat-queued1", "kind": "deck", "status": "queued"},
        ]

    ws.update_deal(deal, add_materials)

    step = call(ws, "next_step", deal=deal)
    assert step["step_id"] == "research.section"
    assert [s["step_id"] for s in step["skipped_since_last_call"]] == ["materials.brief"]
    assert step["skipped_since_last_call"][0]["code"] == "step_disabled"

    (row,) = call(ws, "list_deals")["deals"]
    assert row["deal"] == deal
    assert row["phase"] == "research"
    assert row["materials_pending"] == 1
    assert row["next_step_hint"]
    assert [(s["step_id"], s["code"]) for s in row["skips"]] == [
        ("materials.brief", "step_disabled")
    ]
    assert row["updated_at"]

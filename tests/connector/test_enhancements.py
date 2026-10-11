"""Enhancements and skips (CONN-ENH-01 to CONN-ENH-03), plus the skip Claude
declares itself through ``submit_artifact``."""

from __future__ import annotations

import pytest

from src.connector.config import ConnectorSettings
from src.connector.errors import ConnectorError
from src.connector.registry import load_registry

from .conftest import SECTIONS, call, deal_json, new_deal
from .fake_claude import Direct, FakeClaude
from .fixtures import canned

#: Every optional step in the registry (Claude steps and the server step list).
OPTIONAL_STEPS = [s.id for s in load_registry().steps if not s.required]

#: compile's optional server steps. Written out rather than imported, so a
#: compile module that fails to import fails these tests instead of hiding them;
#: each test checks the list still matches the pipeline.
COMPILE_OPTIONAL = ["compile.spacing", "compile.toc", "compile.deck_images", "compile.diagrams"]


def _subset(expected: dict, items: list[dict]) -> bool:
    return any(all(item.get(k) == v for k, v in expected.items()) for item in items)


def _add_ready_material(ws, deal: str) -> None:
    """A synthetic ready material, so materials.brief applies (phase 4 adds real ones)."""
    with ws.transaction() as tx:
        tx.write_text(f"deals/{deal}/materials/mat-fixturenotes.md", "Synthetic notes.\n")

    def add(state):
        state["materials"].append(
            {"material_id": "mat-fixturenotes", "kind": "notes", "status": "ready"}
        )

    ws.update_deal(deal, add)


def _assert_pipeline_matches():
    from src.connector.compile import pipeline

    assert COMPILE_OPTIONAL == [s.id for s in pipeline.STAGES if not s.required]


@pytest.mark.spec("CONN-ENH-01")
def test_enhancements_are_handed_out_in_registry_order_once_every_section_is_drafted(ws):
    registry = load_registry()
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    walk = fake.walk(deal, compile=False)

    expected = []
    for step in registry.steps:
        if step.phase == "enhance" and step.runs_on == "claude":
            expected += (
                [(step.id, s) for s in SECTIONS] if step.scope == "section" else [(step.id, None)]
            )
    assert [s.split(".")[0] for s, _ in expected] == ["enhance"] * len(expected)
    orders = [registry.step(s).order for s, _ in expected]
    assert orders == sorted(orders)

    handed = walk.handed_out
    enhancements = [h for h in handed if h[0].startswith("enhance.")]
    assert enhancements == expected
    last_draft = max(i for i, h in enumerate(handed) if h[0] == "draft.section")
    first_enhancement = handed.index(expected[0])
    assert first_enhancement == last_draft + 1, "an enhancement came before every draft"

    # Each enhancement reads the section as it now stands: the citations step
    # sees the tables version, not the draft it replaced.
    by_key = {(s["step_id"], s["section"]): s for s in walk.steps}
    citations = by_key[("enhance.citations", SECTIONS[0])]
    ids = {i["artifact_id"] for i in citations["inputs"]}
    assert f"enhance.tables:{SECTIONS[0]}" in ids
    assert f"draft.section:{SECTIONS[0]}" not in ids
    assert f"research.section:{SECTIONS[0]}" in ids
    summaries = by_key[("enhance.summaries", None)]
    ids = {i["artifact_id"] for i in summaries["inputs"]}
    assert {f"enhance.fact_check:{s}" for s in SECTIONS} <= ids
    for step in walk.steps:
        if step["phase"] == "enhance":
            assert "skip" in step["instruction"] and "submit_artifact" in step["instruction"]

    done = call(ws, "next_step", deal=deal)
    assert done["done"] is True and done["compile_ready"] is True


@pytest.mark.spec("CONN-ENH-02")
@pytest.mark.parametrize("step_id", OPTIONAL_STEPS + COMPILE_OPTIONAL)
def test_disabling_any_optional_step_skips_it_and_the_memo_still_compiles(
    ws, settings, client, step_id
):
    _assert_pipeline_matches()
    # The ops switch, read the way production reads it (MEMOPOP_DISABLED_STEPS).
    settings.disabled_steps = ConnectorSettings.from_env(
        {"MEMOPOP_DISABLED_STEPS": f" {step_id} ,"}
    ).disabled_steps
    assert settings.disabled_steps == {step_id}

    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    if step_id == "materials.brief":
        _add_ready_material(ws, deal)
    walk = fake.walk(deal)

    assert step_id not in {s for s, _ in walk.handed_out}, f"{step_id} was handed out"
    expected_skip = {"step_id": step_id, "code": "step_disabled"}
    report = walk.compiled["report"]
    assert _subset(expected_skip, report["skipped"]), report
    assert step_id not in report["enhancements_run"]
    if not step_id.startswith("compile."):
        step = load_registry().step(step_id)
        count = len(SECTIONS) if step.scope == "section" else 1
        reported = [s for s in walk.reported_skips if s["step_id"] == step_id]
        assert len(reported) == count, walk.reported_skips
        assert all(s["code"] == "step_disabled" and s["reason"] for s in reported)

    (listed,) = call(ws, "list_deals")["deals"]
    assert _subset(expected_skip, listed["skips"]), listed["skips"]

    page = client.get(walk.compiled["html_url"])
    assert page.status_code == 200
    for name, _ in canned.SECTIONS.values():
        assert name in page.text
    assert client.get(walk.compiled["pdf_url"]).content.startswith(b"%PDF")


@pytest.mark.spec("CONN-ENH-03")
@pytest.mark.parametrize("stage", COMPILE_OPTIONAL)
def test_an_optional_server_step_that_raises_is_skipped_and_the_flow_continues(
    ws, client, monkeypatch, stage
):
    _assert_pipeline_matches()
    from src.connector.compile import pipeline

    def boom(ctx):
        raise RuntimeError("synthetic failure in an optional server step")

    monkeypatch.setitem(pipeline.STAGE_IMPLS, stage, boom)
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    walk = fake.walk(deal)

    expected_skip = {"step_id": stage, "section": None, "code": "step_failed"}
    report = walk.compiled["report"]
    assert _subset(expected_skip, report["skipped"]), report
    page = client.get(walk.compiled["html_url"])
    assert page.status_code == 200
    for name, _ in canned.SECTIONS.values():
        assert name in page.text

    (listed,) = call(ws, "list_deals")["deals"]
    assert _subset(expected_skip, listed["skips"])
    after = call(ws, "next_step", deal=deal)
    assert after["done"] is True
    assert _subset(expected_skip, after["skipped_since_last_call"])
    # Reported once, not on every call.
    assert call(ws, "next_step", deal=deal)["skipped_since_last_call"] == []


def test_a_required_server_step_that_raises_blocks_compile(ws, monkeypatch):
    """Not a spec ID: the counterpart of CONN-ENH-03; required steps never skip."""
    from src.connector.compile import pipeline

    def boom(ctx):
        raise RuntimeError("synthetic failure in a required server step")

    required = [s.id for s in pipeline.STAGES if s.required]
    assert "compile.citations" in required
    monkeypatch.setitem(pipeline.STAGE_IMPLS, "compile.citations", boom)
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, compile=False)
    with pytest.raises(ConnectorError) as raised:
        call(ws, "compile", deal=deal)
    assert raised.value.kind == "down"
    assert not (ws.root / "deals" / deal / "compiled").exists()


# ------------------------------------------------------------------ Claude's own skip
# The spec (§Deal state) adds `submit_artifact` with `skip: true` and a reason in
# plan 5 but gives it no test ID; these tests hold it to that contract.


def _walk_to(ws, step_id: str):
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    walk = fake.walk(deal, until=lambda s: s["step_id"] == step_id, compile=False)
    return deal, walk.stopped_at


def test_claude_skips_an_optional_step_with_a_reason_and_the_flow_moves_on(ws):
    deal, step = _walk_to(ws, "enhance.tables")
    reason = "The section has no figures worth putting in a table."
    body = call(
        ws,
        "submit_artifact",
        deal=deal,
        step_id="enhance.tables",
        section=step["section"],
        skip=True,
        reason=reason,
    )
    assert body["skipped"] is True
    assert body["advanced"] is True
    assert body["artifact_id"] is None and body["version"] is None
    assert not (ws.root / "deals" / deal / "enhancements" / "enhance.tables").exists()

    following = call(ws, "next_step", deal=deal)
    assert (following["step_id"], following["section"]) == ("enhance.tables", SECTIONS[1])
    (reported,) = following["skipped_since_last_call"]
    assert reported == {
        "step_id": "enhance.tables",
        "section": SECTIONS[0],
        "code": "step_skipped",
        "reason": reason,
    }
    (listed,) = call(ws, "list_deals")["deals"]
    assert reported in listed["skips"]

    # Skipping again is refused: the step is no longer handed out.
    with pytest.raises(ConnectorError) as raised:
        call(
            ws,
            "submit_artifact",
            deal=deal,
            step_id="enhance.tables",
            section=SECTIONS[0],
            skip=True,
            reason=reason,
        )
    assert raised.value.code == "step_out_of_order"


def test_a_skip_needs_an_optional_handed_out_step_and_a_reason(ws):
    deal = new_deal(ws)
    first = call(ws, "next_step", deal=deal)
    before = deal_json(ws, deal).read_bytes()
    cases = [
        # A required step can't be skipped.
        (
            {
                "step_id": "research.section",
                "section": first["section"],
                "skip": True,
                "reason": "No sources.",
            },
            "validation_failed",
        ),
        # A skip needs a reason.
        (
            {"step_id": "research.section", "section": first["section"], "skip": True},
            "validation_failed",
        ),
        # A skip carries no content, and content is required without one.
        ({"step_id": "research.section", "section": first["section"]}, "validation_failed"),
        # An optional step that hasn't been handed out can't be skipped.
        (
            {"step_id": "enhance.one_pager", "skip": True, "reason": "Not needed."},
            "step_out_of_order",
        ),
    ]
    for args, code in cases:
        with pytest.raises(ConnectorError) as raised:
            call(ws, "submit_artifact", deal=deal, **args)
        assert raised.value.code == code, args
        assert raised.value.next
    deal2, step = _walk_to(ws, "enhance.one_pager")
    with pytest.raises(ConnectorError) as raised:
        call(
            ws,
            "submit_artifact",
            deal=deal2,
            step_id="enhance.one_pager",
            skip=True,
            reason="Not needed.",
            content=canned.one_pager(),
        )
    assert raised.value.code == "validation_failed"
    assert deal_json(ws, deal).read_bytes() == before

"""Revisions: reopen sections of a finished memo, redo them, recompile (CONN-REV-01 to 10)."""

from __future__ import annotations

import json

import pytest

from src.connector.errors import ConnectorError

from .conftest import call
from .fake_claude import Direct, FakeClaude
from .fixtures import canned

ANGLE = "We have new market research from a 2026 survey; weight the market sizing by it."
SECTION_ENHANCEMENTS = ["enhance.tables", "enhance.citations", "enhance.fact_check"]


def compiled(ws) -> str:
    """fixture-co walked to the end and compiled once (HTML only, for speed)."""
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, formats=["html"])
    return deal


def revised(text: str, note: str = "Revised for the 2026 survey.") -> str:
    """The canned text with one revised paragraph, kept ahead of its citation list."""
    marker = "### Citations"
    paragraph = f"{note} The synthetic survey revises the store count upward.[^1]\n\n"
    if marker in text:
        head, _, tail = text.partition(marker)
        return f"{head}{paragraph}{marker}{tail}"
    return text + "\n\n" + paragraph


def walk_revision(ws, deal: str, *, change: bool = True, max_steps: int = 50) -> list[dict]:
    """Do every step next_step hands out until done; return the steps handed out."""
    steps = []
    for _ in range(max_steps):
        step = call(ws, "next_step", deal=deal)
        if step["done"]:
            return steps
        steps.append(step)
        content = canned.for_step(step["step_id"], step["section"])
        args = {
            "deal": deal,
            "step_id": step["step_id"],
            "content": revised(content) if change else content,
        }
        if step["section"] is not None:
            args["section"] = step["section"]
        if step["needs_partner"]:
            args |= {"partner_approved": True, "partner_notes": "Approved by the colleague."}
        call(ws, "submit_artifact", **args)
    raise AssertionError("the revision did not finish")


def deal_state(ws, deal: str) -> dict:
    return json.loads((ws.root / "deals" / deal / "deal.json").read_text())


def code_of(fn) -> str:
    with pytest.raises(ConnectorError) as err:
        fn()
    return err.value.code


@pytest.mark.spec("CONN-REV-01")
def test_a_research_revision_walks_the_section_then_the_deal_summaries(ws):
    deal = compiled(ws)
    body = call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE)
    assert body["sections"] == ["02-market"]
    assert body["start"] == "research"

    steps = walk_revision(ws, deal)
    handed = [(s["step_id"], s["section"]) for s in steps]
    assert handed[:2] == [("research.section", "02-market"), ("draft.section", "02-market")]
    assert {h for h in handed[2:]} <= (
        {(e, "02-market") for e in SECTION_ENHANCEMENTS}
        | {("enhance.summaries", None), ("enhance.one_pager", None)}
    )
    assert ("enhance.summaries", None) in handed and ("enhance.one_pager", None) in handed
    assert all(section in ("02-market", None) for _, section in handed), handed
    for step in steps:
        assert step["revision"]["angle"] == ANGLE
        assert step["instruction"].startswith("This is a revision")
    research = steps[0]
    assert "research.section:02-market" in [i["artifact_id"] for i in research["inputs"]]


@pytest.mark.spec("CONN-REV-02")
def test_revision_materials_reach_every_reopened_step(ws):
    deal = compiled(ws)
    added = call(
        ws,
        "add_materials",
        deal=deal,
        items=[{"kind": "other", "text": "2026 survey: 21,400 stores."}],
    )
    mid = added["accepted"][0]["material_id"]
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE, material_ids=[mid])
    steps = walk_revision(ws, deal)
    assert steps
    for step in steps:
        assert f"material:{mid}" in [i["artifact_id"] for i in step["inputs"]], step["step_id"]
        assert step["revision"]["material_ids"] == [mid]


@pytest.mark.spec("CONN-REV-03")
def test_a_draft_revision_does_not_redo_research(ws):
    deal = compiled(ws)
    call(
        ws,
        "start_revision",
        deal=deal,
        sections=["Team"],
        angle="Lead with the founders' distributor years.",
        start="draft",
    )
    handed = [(s["step_id"], s["section"]) for s in walk_revision(ws, deal)]
    assert handed[0] == ("draft.section", "03-team")
    assert ("research.section", "03-team") not in handed


@pytest.mark.spec("CONN-REV-04")
def test_compile_closes_the_revision_with_the_next_label(ws):
    deal = compiled(ws)
    first = deal_state(ws, deal)["compiled"]["label"]
    call(ws, "start_revision", deal=deal, sections=["02-market", "03-team"], angle=ANGLE)
    walk_revision(ws, deal)
    body = call(ws, "compile", deal=deal, formats=["html"])
    assert body["label"] == "v0.0.2" and first == "v0.0.1"
    state = deal_state(ws, deal)
    assert state["revision"] is None
    closed = state["revisions"][-1]
    assert closed["status"] == "compiled"
    assert closed["sections"] == ["02-market", "03-team"]
    assert closed["compiled_label"] == "v0.0.2"


@pytest.mark.spec("CONN-REV-05")
def test_one_open_revision_at_a_time_and_no_compile_mid_revision(ws):
    deal = compiled(ws)
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE)
    assert (
        code_of(lambda: call(ws, "start_revision", deal=deal, sections=["03-team"], angle="x" * 20))
        == "revision_open"
    )
    assert (
        code_of(lambda: call(ws, "compile", deal=deal, formats=["html"])) == "revision_incomplete"
    )
    walk_revision(ws, deal)
    assert call(ws, "compile", deal=deal, formats=["html"])["ok"] is True


@pytest.mark.spec("CONN-REV-06")
def test_cancel_restores_the_section_and_leaves_the_deal_done(ws):
    deal = compiled(ws)
    before = call(ws, "get_artifact", deal=deal, artifact_id="draft.section:02-market")
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE)
    walk_revision(ws, deal)
    changed = call(ws, "get_artifact", deal=deal, artifact_id="draft.section:02-market")
    assert changed["text"] != before["text"]

    body = call(ws, "cancel_revision", deal=deal)
    assert "draft.section:02-market" in body["restored"]
    after = call(ws, "get_artifact", deal=deal, artifact_id="draft.section:02-market")
    assert after["text"] == before["text"]
    assert after["version"] > changed["version"]
    assert call(ws, "next_step", deal=deal)["done"] is True
    state = deal_state(ws, deal)
    assert state["revision"] is None and state["revisions"][-1]["status"] == "cancelled"
    assert code_of(lambda: call(ws, "cancel_revision", deal=deal)) == "no_open_revision"


@pytest.mark.spec("CONN-REV-07")
def test_only_drafted_known_sections_can_be_revised(ws):
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, until=lambda s: s["step_id"] == "draft.section", compile=False)
    assert (
        code_of(
            lambda: call(ws, "start_revision", deal=deal, sections=["01-overview"], angle=ANGLE)
        )
        == "section_not_drafted"
    )
    other = FakeClaude(Direct(ws)).create(company="Other Co", url="https://other.co")
    FakeClaude(Direct(ws)).walk(other, formats=["html"])
    assert (
        code_of(lambda: call(ws, "start_revision", deal=other, sections=["99-nope"], angle=ANGLE))
        == "validation_failed"
    )


@pytest.mark.spec("CONN-REV-08")
def test_unchanged_resubmission_still_finishes_the_step(ws):
    deal = compiled(ws)
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE)
    steps = walk_revision(ws, deal, change=False)
    assert len(steps) <= 7, [s["step_id"] for s in steps]
    assert call(ws, "next_step", deal=deal)["done"] is True


@pytest.mark.spec("CONN-REV-09")
def test_labels_continue_the_local_numbering(ws):
    deal = compiled(ws)
    assert deal_state(ws, deal)["compiled"]["label"] == "v0.0.1"
    again = call(ws, "compile", deal=deal, formats=["html"])
    assert again["label"] == "v0.0.1", "an unchanged recompile keeps its label"

    other = FakeClaude(Direct(ws)).create(company="Imported Co", url="https://imported.co")
    FakeClaude(Direct(ws)).walk(other, compile=False)

    def mark_imported(state):
        state["imported_from"] = {"path": "humain/deals/ImportedCo", "version": "ImportedCo-v0.2.2"}

    ws.update_deal(other, mark_imported)
    assert call(ws, "compile", deal=other, formats=["html"])["label"] == "v0.2.3"


@pytest.mark.spec("CONN-REV-10")
def test_list_deals_shows_the_memo_version_and_an_open_revision(ws):
    deal = compiled(ws)
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE)
    row = next(d for d in call(ws, "list_deals")["deals"] if d["deal"] == deal)
    assert row["memo_version"] == "v0.0.1"
    assert row["revision"]["sections"] == ["02-market"]
    assert row["revision"]["angle"] == ANGLE

"""The rewrite step and the revision draft (CONN-STEP-11, CONN-STEP-12).

Spec §Where an edit goes (Plan 9), "Who does the rewrite, for now": editing the
research and rewriting the section are two separate tasks, and the rewrite
works from exactly two inputs, the research file and the current section
draft, with no knowledge of its own and no web research.
"""

from __future__ import annotations

import json

import pytest

from src.connector import flow

from .conftest import call
from .fake_claude import Direct, FakeClaude
from .fixtures import canned

#: The line both writing steps carry, word for word.
NO_OUTSIDE_KNOWLEDGE = (
    "Use no knowledge of your own and do no web research: write only from your inputs."
)
REVISER = "src/agents/section_reviser.py"
ANGLE = "We have new market research from a 2026 survey; weight the market sizing by it."


def compiled(ws) -> str:
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, formats=["html"])
    return deal


def deal_state(ws, deal: str) -> dict:
    return json.loads((ws.root / "deals" / deal / "deal.json").read_text())


def rewrite_step(registry):
    steps = [s for s in registry.steps if s.source_agent == REVISER]
    assert len(steps) == 1, [s.id for s in steps]
    return steps[0]


@pytest.mark.spec("CONN-STEP-11")
def test_a_rewrite_step_reads_only_the_research_and_the_current_draft(registry):
    step = rewrite_step(registry)
    assert step.runs_on == "claude"
    assert step.scope == "section"
    assert step.phase == "draft"
    assert sorted(step.reads) == sorted(["research.section:@section", "section.current:@section"])
    assert step.produces and step.produces.kind == "section"
    text = step.instruction_text()
    assert NO_OUTSIDE_KNOWLEDGE in text
    assert "web research" in text and "submit_artifact" in text


@pytest.mark.spec("CONN-STEP-11")
def test_the_rewrite_step_runs_only_when_a_revision_reopens_it(ws, registry):
    step = rewrite_step(registry)
    deal = compiled(ws)
    state = deal_state(ws, deal)
    assert not any(
        k.startswith(step.id + ":") for k in state["artifacts"]
    ), "a memo's first walk must never hand out the rewrite step"
    current = flow.current_section_key(registry, state, "03-team")

    # The revision mechanics a light edit path opens: reopen only the rewrite. A
    # material given to the revision is not one of its inputs: new evidence goes
    # into the research first.
    added = call(ws, "add_materials", deal=deal, items=[{"kind": "other", "text": "2026 survey."}])
    mid = added["accepted"][0]["material_id"]
    call(
        ws,
        "start_revision",
        deal=deal,
        sections=["03-team"],
        angle=ANGLE,
        start="draft",
        material_ids=[mid],
    )

    def reopen_rewrite(s):
        s["revision"]["baseline"] = {f"{step.id}:03-team": {"version": 0, "seq": 0, "copy": None}}

    ws.update_deal(deal, reopen_rewrite)
    handed = call(ws, "next_step", deal=deal)
    assert (handed["step_id"], handed["section"]) == (step.id, "03-team")
    ids = sorted(i["artifact_id"] for i in handed["inputs"])
    assert ids == sorted(["research.section:03-team", current]), ids
    assert NO_OUTSIDE_KNOWLEDGE in handed["instruction"]
    assert handed["instruction"].startswith("This is a revision")
    assert "new materials" not in handed["instruction"]

    body = call(
        ws,
        "submit_artifact",
        deal=deal,
        step_id=step.id,
        section="03-team",
        content=canned.tables("03-team"),
    )
    assert body["ok"] is True
    after = deal_state(ws, deal)
    assert flow.current_section_key(registry, after, "03-team") == f"{step.id}:03-team"
    assert call(ws, "next_step", deal=deal)["done"] is True


@pytest.mark.spec("CONN-STEP-12")
def test_a_research_revision_hands_the_draft_the_current_text_and_the_line(ws, registry):
    deal = compiled(ws)
    current = flow.current_section_key(registry, deal_state(ws, deal), "02-market")
    # The current draft is the enhanced text, not the first draft.section save.
    assert current is not None and current != "draft.section:02-market", current
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE, start="research")

    research = call(ws, "next_step", deal=deal)
    assert research["step_id"] == "research.section"
    call(
        ws,
        "submit_artifact",
        deal=deal,
        step_id="research.section",
        section="02-market",
        content=canned.research("02-market"),
        partner_approved=True,
        partner_notes="Approved by the colleague.",
    )
    draft = call(ws, "next_step", deal=deal)
    assert (draft["step_id"], draft["section"]) == ("draft.section", "02-market")
    ids = [i["artifact_id"] for i in draft["inputs"]]
    assert current in ids, ids
    assert "research.section:02-market" in ids
    assert NO_OUTSIDE_KNOWLEDGE in draft["instruction"]

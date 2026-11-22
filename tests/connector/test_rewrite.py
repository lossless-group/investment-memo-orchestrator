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


def submit(ws, deal: str, step: dict, content: str | None = None) -> dict:
    args = {
        "deal": deal,
        "step_id": step["step_id"],
        "content": content or canned.for_step(step["step_id"], step["section"]),
    }
    if step["section"] is not None:
        args["section"] = step["section"]
    if step["needs_partner"]:
        args |= {"partner_approved": True, "partner_notes": "Approved by the colleague."}
    return call(ws, "submit_artifact", **args)


@pytest.mark.spec("CONN-STEP-11")
def test_a_rewrite_step_reads_only_the_research_and_the_current_draft(registry):
    step = rewrite_step(registry)
    assert step.runs_on == "claude"
    assert step.scope == "section"
    assert step.phase == "draft"
    assert step.revision_only is True
    assert sorted(step.reads) == sorted(["research.section:@section", "section.current:@section"])
    assert step.produces and step.produces.kind == "section"
    text = step.instruction_text()
    assert NO_OUTSIDE_KNOWLEDGE in text
    assert "web research" in text and "submit_artifact" in text


@pytest.mark.spec("CONN-STEP-11")
def test_a_draft_revision_hands_out_the_rewrite_with_exactly_its_inputs(ws, registry):
    step = rewrite_step(registry)
    deal = compiled(ws)
    state = deal_state(ws, deal)
    assert not any(
        k.startswith(step.id + ":") for k in state["artifacts"]
    ), "a memo's first walk must never hand out the rewrite step"
    current = flow.current_section_key(registry, state, "03-team")

    # A material given to the revision is not one of the rewrite's inputs: new
    # evidence reaches it only through the research.
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
    handed = call(ws, "next_step", deal=deal)
    assert (handed["step_id"], handed["section"]) == (step.id, "03-team")
    ids = sorted(i["artifact_id"] for i in handed["inputs"])
    assert ids == sorted(["research.section:03-team", current]), ids
    instruction = handed["instruction"]
    assert instruction.startswith("This is a revision")
    assert instruction.index(ANGLE) < instruction.index("# Rewrite"), "the request leads"
    assert NO_OUTSIDE_KNOWLEDGE in instruction
    assert "new materials" not in instruction

    assert submit(ws, deal, handed, canned.tables("03-team"))["ok"] is True
    after = deal_state(ws, deal)
    assert flow.current_section_key(registry, after, "03-team") == f"{step.id}:03-team"


@pytest.mark.spec("CONN-STEP-11")
def test_a_research_revision_rewrites_from_the_new_research(ws, registry):
    step = rewrite_step(registry)
    deal = compiled(ws)
    current = flow.current_section_key(registry, deal_state(ws, deal), "02-market")
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle=ANGLE, start="research")

    research = call(ws, "next_step", deal=deal)
    assert research["step_id"] == "research.section"
    submit(ws, deal, research, canned.research("02-market") + "\nRevised for the survey.\n")
    version = deal_state(ws, deal)["artifacts"]["research.section:02-market"]["version"]

    handed = call(ws, "next_step", deal=deal)
    assert (handed["step_id"], handed["section"]) == (step.id, "02-market")
    inputs = {i["artifact_id"]: i for i in handed["inputs"]}
    assert sorted(inputs) == sorted(["research.section:02-market", current]), sorted(inputs)
    assert inputs["research.section:02-market"]["version"] == version
    assert handed["instruction"].startswith("This is a revision")
    assert NO_OUTSIDE_KNOWLEDGE in handed["instruction"]


@pytest.mark.spec("CONN-STEP-12")
def test_a_first_draft_carries_the_line_and_does_not_read_the_current_text(ws, registry):
    assert not any(r.startswith("section.current") for r in registry.step("draft.section").reads)
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    for _ in range(20):
        step = call(ws, "next_step", deal=deal)
        if step["step_id"] == "draft.section":
            break
        submit(ws, deal, step)
    else:
        raise AssertionError("draft.section was never handed out")
    assert step["revision"] is None
    assert NO_OUTSIDE_KNOWLEDGE in step["instruction"]

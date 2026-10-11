"""Steps: next_step, submit_artifact, get_artifact, and transport parity
(CONN-STEP-01 to CONN-STEP-09)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.connector.app import build_app
from src.connector.errors import ConnectorError

from .conftest import BASE_URL, SECTIONS, TEMPLATE, call, deal_json, new_deal, rest
from .fixtures import canned


def submit(ws, deal: str, step: dict, content: str | None = None, **kw) -> dict:
    section = step.get("section")
    if content is None:
        content = canned.research(section) if step["step_id"] == "research.section" else canned.draft(section)
    return call(ws, "submit_artifact", deal=deal, step_id=step["step_id"], section=section, content=content, **kw)


def approve_all_research(ws, deal: str) -> None:
    for _ in SECTIONS:
        step = call(ws, "next_step", deal=deal)
        assert step["step_id"] == "research.section"
        submit(ws, deal, step, partner_approved=True)


@pytest.mark.spec("CONN-STEP-01")
def test_a_new_deal_starts_with_research_for_the_first_section(ws):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    assert step["step_id"] == "research.section"
    assert step["phase"] == "research"
    assert step["section"] == SECTIONS[0]
    assert step["needs_partner"] is True
    assert "Fixture Co" in step["instruction"]
    assert "Overview" in step["instruction"]
    assert "submit_artifact" in step["instruction"]
    assert step["produces"]["kind"]
    assert step["produces"]["checks"]
    assert step["progress"]["done"] == 0
    assert step["progress"]["total"] > len(SECTIONS) * 2
    assert step["skipped_since_last_call"] == []
    assert isinstance(step["inputs"], list)


@pytest.mark.spec("CONN-STEP-02")
def test_drafting_before_research_is_approved_is_refused(ws):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)

    def draft_first_section():
        return call(
            ws,
            "submit_artifact",
            deal=deal,
            step_id="draft.section",
            section=SECTIONS[0],
            content=canned.draft(SECTIONS[0]),
        )

    with pytest.raises(ConnectorError) as raised:
        draft_first_section()
    assert (raised.value.kind, raised.value.code) == ("invalid", "research_not_approved")

    # Research submitted but not yet approved by the partner: still refused.
    body = submit(ws, deal, step, partner_approved=False)
    assert body["advanced"] is False
    with pytest.raises(ConnectorError) as raised:
        draft_first_section()
    assert raised.value.code == "research_not_approved"
    assert not (ws.root / "deals" / deal / "sections" / f"{SECTIONS[0]}.md").exists()

    # Until approved, next_step keeps handing out the same research, with the draft attached.
    again = call(ws, "next_step", deal=deal)
    assert (again["step_id"], again["section"]) == ("research.section", SECTIONS[0])
    assert any(i["artifact_id"] == f"research.section:{SECTIONS[0]}" for i in again["inputs"])


@pytest.mark.spec("CONN-STEP-03")
def test_failed_checks_list_every_failure_and_save_nothing(ws):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    before = deal_json(ws, deal).read_bytes()
    with pytest.raises(ConnectorError) as raised:
        submit(ws, deal, step, content="Too short, and no citations.", partner_approved=True)
    err = raised.value
    assert (err.kind, err.code) == ("invalid", "checks_failed")
    failed = {f["name"] for f in err.details["failures"]}
    assert {"min_words", "has_citations"} <= failed
    for failure in err.details["failures"]:
        assert failure["detail"]
    assert deal_json(ws, deal).read_bytes() == before
    assert not (ws.root / "deals" / deal / "research" / f"{SECTIONS[0]}.md").exists()

    dangling = canned.research(SECTIONS[0]).replace("[^2]: 2025", "[^9]: 2025")
    with pytest.raises(ConnectorError) as raised:
        submit(ws, deal, step, content=dangling, partner_approved=True)
    assert "citations_resolve" in {f["name"] for f in raised.value.details["failures"]}


@pytest.mark.spec("CONN-STEP-04")
def test_identical_resubmission_is_a_no_op(ws):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    first = submit(ws, deal, step, partner_approved=True)
    assert first["version"] == 1
    assert all(c["passed"] for c in first["checks"])
    artifact = ws.root / "deals" / deal / "research" / f"{SECTIONS[0]}.md"
    state_before = deal_json(ws, deal).read_bytes()
    file_before = (artifact.read_bytes(), artifact.stat().st_mtime_ns)

    second = submit(ws, deal, step, partner_approved=True)
    assert second["version"] == first["version"]
    assert second["artifact_id"] == first["artifact_id"]
    assert deal_json(ws, deal).read_bytes() == state_before
    assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == file_before

    changed = submit(ws, deal, step, content=canned.research(SECTIONS[0]) + "\nOne more line.\n", partner_approved=True)
    assert changed["version"] == 2


@pytest.mark.spec("CONN-STEP-05")
def test_an_accepted_artifact_moves_next_step_on(ws):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    body = submit(ws, deal, step, partner_approved=True)
    assert body["advanced"] is True
    assert body["next_hint"]
    following = call(ws, "next_step", deal=deal)
    assert (following["step_id"], following["section"]) == ("research.section", SECTIONS[1])
    assert following["progress"]["done"] == 1

    for _ in SECTIONS[1:]:
        submit(ws, deal, call(ws, "next_step", deal=deal), partner_approved=True)
    draft = call(ws, "next_step", deal=deal)
    assert (draft["step_id"], draft["section"], draft["phase"]) == ("draft.section", SECTIONS[0], "draft")
    research_input = f"research.section:{SECTIONS[0]}"
    assert research_input in [i["artifact_id"] for i in draft["inputs"]]

    for _ in SECTIONS:
        step = call(ws, "next_step", deal=deal)
        assert step["step_id"] == "draft.section"
        assert submit(ws, deal, step)["advanced"] is True
    enhancement = call(ws, "next_step", deal=deal)
    assert enhancement["phase"] == "enhance"


@pytest.mark.spec("CONN-STEP-06")
def test_a_new_session_resumes_at_the_same_step(settings, jwks_transport):
    def session():
        return TestClient(build_app(settings, http_transport=jwks_transport), base_url=BASE_URL)

    with session() as first:
        deal = rest(first, "create_new_deal", {"company": "Fixture Co", "template": TEMPLATE}).json()["deal"]
        step = rest(first, "next_step", {"deal": deal}).json()
        rest(
            first,
            "submit_artifact",
            {
                "deal": deal,
                "step_id": step["step_id"],
                "section": step["section"],
                "content": canned.research(step["section"]),
                "partner_approved": True,
            },
        )
        expected = rest(first, "next_step", {"deal": deal}).json()
        assert rest(first, "next_step", {"deal": deal}).json() == expected

    with session() as second:
        resumed = rest(second, "next_step", {"deal": deal}).json()
    assert resumed == expected
    assert (resumed["step_id"], resumed["section"]) == ("research.section", SECTIONS[1])


@pytest.mark.spec("CONN-STEP-07")
def test_long_artifacts_page_and_no_result_exceeds_150k(ws):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    long_text = canned.long_research(250_000)
    body = submit(ws, deal, step, content=long_text, partner_approved=True)
    artifact_id = body["artifact_id"]

    pages = []
    offset = 0
    while True:
        page = call(ws, "get_artifact", deal=deal, artifact_id=artifact_id, offset=offset)
        assert len(json.dumps(page)) <= 150_000
        assert len(page["text"]) <= 100_000
        pages.append(page["text"])
        if page.get("next_offset") is None:
            break
        offset = page["next_offset"]
    assert len(pages) == 3
    assert "".join(pages) == long_text

    # The other sections' research, then the first draft, whose input is the long file.
    for _ in SECTIONS[1:]:
        submit(ws, deal, call(ws, "next_step", deal=deal), content=long_text, partner_approved=True)
    for tool, args in (
        ("next_step", {"deal": deal}),
        ("list_deals", {}),
        ("get_artifact", {"deal": deal, "artifact_id": artifact_id}),
    ):
        result = call(ws, tool, **args)
        assert len(json.dumps(result)) <= 150_000, tool
    draft = call(ws, "next_step", deal=deal)
    (research,) = [i for i in draft["inputs"] if i["artifact_id"] == f"research.section:{SECTIONS[0]}"]
    assert research.get("truncated") is True
    assert research.get("next_offset")


@pytest.mark.spec("CONN-STEP-08")
def test_mcp_and_rest_return_the_same_body(client, mcp):
    created = rest(client, "create_new_deal", {"company": "Fixture Co", "template": TEMPLATE})
    deal = created.json()["deal"]
    assert mcp.call("create_new_deal", {"company": "Fixture Co", "template": TEMPLATE})["structuredContent"] == {
        **created.json(),
        "created": False,
    }
    step = rest(client, "next_step", {"deal": deal}).json()
    submitted = rest(
        client,
        "submit_artifact",
        {
            "deal": deal,
            "step_id": step["step_id"],
            "section": step["section"],
            "content": canned.research(step["section"]),
            "partner_approved": True,
        },
    ).json()
    calls = [
        ("list_deals", {}),
        ("list_deals", {"limit": 1}),
        ("next_step", {"deal": deal}),
        ("get_artifact", {"deal": deal, "artifact_id": submitted["artifact_id"]}),
        ("next_step", {"deal": "no-such-deal"}),
        ("get_artifact", {"deal": deal, "artifact_id": "research.section:99-nope"}),
        ("compile", {"deal": deal}),
    ]
    for tool, args in calls:
        over_rest = rest(client, tool, dict(args)).json()
        over_mcp = mcp.call(tool, args)["structuredContent"]
        assert over_mcp == over_rest, tool


@pytest.mark.spec("CONN-STEP-09")
def test_submitting_a_step_not_yet_handed_out_is_out_of_order(ws):
    deal = new_deal(ws)
    call(ws, "next_step", deal=deal)  # hands out research for the first section only
    cases = [
        ("research.section", SECTIONS[1], canned.research(SECTIONS[1])),
        ("enhance.tables", SECTIONS[0], canned.draft(SECTIONS[0])),
        ("materials.brief", None, canned.research(SECTIONS[0])),
    ]
    before = deal_json(ws, deal).read_bytes()
    for step_id, section, content in cases:
        with pytest.raises(ConnectorError) as raised:
            call(ws, "submit_artifact", deal=deal, step_id=step_id, section=section, content=content, partner_approved=True)
        assert (raised.value.kind, raised.value.code) == ("invalid", "step_out_of_order"), step_id
        assert raised.value.next
    assert deal_json(ws, deal).read_bytes() == before

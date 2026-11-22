"""Edit tools for finished memos (CONN-EDIT-01 to CONN-EDIT-06).

edit_section changes a section's text without reopening anything; compile
refuses to overwrite a final that was edited outside the sections; edit_final
edits the final and carries the change back into its section; get_outline and
edit_outline change the outline for one memo, or for the firm without touching
any deal.
"""

from __future__ import annotations

import json

import pytest
import yaml

from src.connector import flow
from src.connector.errors import ConnectorError
from src.connector.registry import load_registry
from src.connector.templates import load_sections

from .conftest import SECTIONS, TEMPLATE, call
from .fake_claude import Direct, FakeClaude

MARKET_PHRASE = "a fragmented market of roughly twenty thousand stores"
TEAM_PHRASE = "where they saw stock counts take whole weekends"


def compiled(ws, company: str = "Fixture Co", url: str = "https://fixture.co") -> str:
    """A deal walked to the end and compiled once (HTML only, for speed)."""
    fake = FakeClaude(Direct(ws))
    deal = fake.create(company=company, url=url)
    fake.walk(deal, formats=["html"])
    return deal


def deal_state(ws, deal: str) -> dict:
    return json.loads((ws.root / "deals" / deal / "deal.json").read_text())


def section_text(ws, deal: str, section: str) -> tuple[str, str, int]:
    """(artifact id, text, version) of the section as it now stands."""
    state = deal_state(ws, deal)
    key = flow.current_section_key(load_registry(), state, section)
    record = state["artifacts"][key]
    return key, (ws.root / "deals" / deal / record["path"]).read_text(), record["version"]


def final_text(ws, deal: str) -> str:
    state = deal_state(ws, deal)
    return (ws.root / "deals" / deal / state["artifacts"]["compile.assemble"]["path"]).read_text()


def error_of(fn) -> ConnectorError:
    with pytest.raises(ConnectorError) as err:
        fn()
    return err.value


# ------------------------------------------------------------------ edit_section


@pytest.mark.spec("CONN-EDIT-01")
def test_edit_section_saves_a_new_version_and_leaves_research_alone(ws):
    deal = compiled(ws)
    research_path = ws.root / "deals" / deal / "research" / "02-market.md"
    research_before = research_path.read_text()
    research_version = deal_state(ws, deal)["artifacts"]["research.section:02-market"]["version"]
    key, before, version = section_text(ws, deal, "02-market")
    assert MARKET_PHRASE in before

    body = call(
        ws,
        "edit_section",
        deal=deal,
        section="Market",
        edits=[{"old": MARKET_PHRASE, "new": "a scattered market of about twenty thousand stores"}],
    )
    assert body["ok"] is True
    assert body["section"] == "02-market"
    assert body["artifact_id"] == key
    assert body["version"] == version + 1

    _, after, now = section_text(ws, deal, "02-market")
    assert now == version + 1
    assert "a scattered market of about twenty thousand stores" in after
    assert MARKET_PHRASE not in after

    state = deal_state(ws, deal)
    assert state["revision"] is None, "edit_section must not open a revision"
    assert research_path.read_text() == research_before
    assert state["artifacts"]["research.section:02-market"]["version"] == research_version

    # A whole new text works too, and also makes a new version.
    whole = after.replace("Independent hardware retail", "Independent hardware retailing")
    again = call(ws, "edit_section", deal=deal, section="2", text=whole)
    assert again["version"] == version + 2
    assert section_text(ws, deal, "02-market")[1] == whole

    # An old string that matches nowhere, or more than once, is refused by name.
    missing = error_of(
        lambda: call(
            ws,
            "edit_section",
            deal=deal,
            section="02-market",
            edits=[{"old": "words that are not in the section", "new": "x"}],
        )
    )
    assert missing.code == "validation_failed"
    assert "words that are not in the section" in json.dumps(missing.details)
    twice = error_of(
        lambda: call(
            ws, "edit_section", deal=deal, section="02-market", edits=[{"old": "[^1]", "new": "x"}]
        )
    )
    assert twice.code == "validation_failed"
    assert "[^1]" in json.dumps(twice.details)
    assert section_text(ws, deal, "02-market")[2] == version + 2, "a refused edit saves nothing"

    # While a revision is open on the section, edit_section refuses.
    call(ws, "start_revision", deal=deal, sections=["02-market"], angle="Reweight the market.")
    blocked = error_of(
        lambda: call(
            ws,
            "edit_section",
            deal=deal,
            section="02-market",
            edits=[{"old": "Independent hardware retailing", "new": "Hardware retail"}],
        )
    )
    assert blocked.code == "revision_open"


@pytest.mark.spec("CONN-EDIT-02")
def test_two_section_edits_both_reach_the_next_compile(ws):
    deal = compiled(ws)
    call(
        ws,
        "edit_section",
        deal=deal,
        section="02-market",
        edits=[{"old": MARKET_PHRASE, "new": "a market edited once by the partner"}],
    )
    call(
        ws,
        "edit_section",
        deal=deal,
        section="03-team",
        edits=[{"old": TEAM_PHRASE, "new": "where they watched stock counts eat whole weekends"}],
    )
    body = call(ws, "compile", deal=deal, formats=["html"])
    assert body["version"] == 2
    memo = final_text(ws, deal)
    assert "a market edited once by the partner" in memo
    assert "where they watched stock counts eat whole weekends" in memo


# ------------------------------------------------------------------ the compile guard


@pytest.mark.spec("CONN-EDIT-03")
def test_compile_refuses_a_final_edited_outside_the_sections(ws):
    deal = compiled(ws)
    path = ws.root / "deals" / deal / "compiled" / "1" / "memo.md"
    text = path.read_text()
    assert MARKET_PHRASE in text
    path.write_text(text.replace(MARKET_PHRASE, "a hand-edited market nobody carried back"))

    err = error_of(lambda: call(ws, "compile", deal=deal, formats=["html"]))
    assert err.code == "final_has_untracked_edits"
    assert err.kind == "invalid"
    differences = err.details["differences"]
    assert len(differences) == 1, differences
    assert differences[0]["section"] == "02-market"
    assert "hand-edited market" in json.dumps(differences[0])
    assert "edit_final" in err.next
    assert path.read_text() != text, "a refused compile writes nothing"

    body = call(ws, "compile", deal=deal, formats=["html"], discard_untracked=True)
    assert body["ok"] is True
    assert "hand-edited market" not in final_text(ws, deal)
    assert MARKET_PHRASE in final_text(ws, deal)


# ------------------------------------------------------------------ edit_final


@pytest.mark.spec("CONN-EDIT-04")
def test_edit_final_reaches_the_section_and_the_next_compile_reproduces_it(ws):
    deal = compiled(ws)
    _, _, section_version = section_text(ws, deal, "02-market")
    new = "a market the partner edited in the final"

    body = call(
        ws,
        "edit_final",
        deal=deal,
        edits=[{"old": MARKET_PHRASE, "new": new}],
        formats=["html"],
    )
    assert body["ok"] is True
    assert body["version"] == 2
    assert body["label"] == "v0.0.2"
    assert body["html_url"]
    assert new in final_text(ws, deal), "the partner sees the change now"
    carried = body["carried"]
    assert [c["section"] for c in carried] == ["02-market"]

    _, text, version = section_text(ws, deal, "02-market")
    assert version == section_version + 1
    assert new in text and MARKET_PHRASE not in text

    again = call(ws, "compile", deal=deal, formats=["html"])
    assert again["ok"] is True
    assert again["version"] == 2, "the sections reproduce the edited final exactly"
    assert new in final_text(ws, deal)


@pytest.mark.spec("CONN-EDIT-04")
def test_edit_final_refuses_an_edit_it_cannot_place(ws):
    deal = compiled(ws)
    memo = final_text(ws, deal)
    # From the end of the Overview into the Market heading: two sections.
    start = memo.index("## Market")
    spanning = memo[start - 40 : start + 12]
    err = error_of(
        lambda: call(ws, "edit_final", deal=deal, edits=[{"old": spanning, "new": "joined"}])
    )
    assert err.code == "edit_not_placed"
    assert err.details["edit"] == 0
    assert final_text(ws, deal) == memo, "a refused edit changes nothing"
    assert deal_state(ws, deal)["compiled"]["version"] == 1


# ------------------------------------------------------------------ outlines


@pytest.mark.spec("CONN-EDIT-05")
def test_an_outline_edit_changes_only_this_deal_and_shows_in_next_step(ws):
    deal = compiled(ws)
    other = FakeClaude(Direct(ws)).create(company="Other Co", url="https://other.co")
    other_before = deal_state(ws, other)

    body = call(
        ws,
        "edit_outline",
        deal=deal,
        edits=[
            {
                "op": "add_section",
                "name": "Competition",
                "after": "Market",
                "description": "Who else serves these stores, and how they win.",
                "guiding_questions": ["Who are the three closest competitors?"],
            }
        ],
    )
    assert body["ok"] is True
    added = body["added"]
    assert len(added) == 1
    new_key = added[0]

    state = deal_state(ws, deal)
    keys = [s["key"] for s in state["sections"]]
    assert keys == ["01-overview", "02-market", new_key, "03-team"]
    assert state["template"] != TEMPLATE, "the deal points at its own pinned copy"
    assert load_sections(ws, state["template"])[2]["name"] == "Competition"

    # The other deal and the firm's outline are untouched.
    assert deal_state(ws, other)["sections"] == other_before["sections"]
    assert deal_state(ws, other)["template"] == TEMPLATE
    assert [s["key"] for s in load_sections(ws, TEMPLATE)] == SECTIONS

    outline = call(ws, "get_outline", deal=deal)
    assert outline["pinned"] is True
    assert [s["key"] for s in outline["sections"]] == keys

    step = call(ws, "next_step", deal=deal)
    assert step["step_id"] == "research.section"
    assert step["section"] == new_key


@pytest.mark.spec("CONN-EDIT-06")
def test_an_outline_edit_for_the_firm_lists_the_deals_and_changes_none(ws):
    deal = compiled(ws)
    other = FakeClaude(Direct(ws)).create(company="Other Co", url="https://other.co")
    before = {d: deal_state(ws, d) for d in (deal, other)}
    question = "What share of stores already use inventory software?"

    body = call(
        ws,
        "edit_outline",
        deal=deal,
        apply_to="firm",
        edits=[
            {
                "op": "update_section",
                "section": "Market",
                "guiding_questions": [
                    "How large is the market today, with a dated source?",
                    question,
                ],
            }
        ],
    )
    assert body["ok"] is True
    assert body["template"] == TEMPLATE
    assert sorted(d["deal"] for d in body["deals_using"]) == sorted([deal, other])

    firm_outline = ws.root / "templates" / "outlines" / f"{TEMPLATE}.yaml"
    market = yaml.safe_load(firm_outline.read_text())["sections"][1]
    assert question in market["guiding_questions"]
    assert [s["key"] for s in load_sections(ws, TEMPLATE)] == SECTIONS, "keys stay stable"

    for d, state in before.items():
        now = deal_state(ws, d)
        assert now["sections"] == state["sections"], f"{d} changed"
        assert now["template"] == state["template"]

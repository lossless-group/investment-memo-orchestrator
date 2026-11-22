"""Hex-code citation keys (CONN-HEX-01 to CONN-HEX-03).

Every section numbers its sources from 1, so a numbered key means something only
inside its own section. A key derived from the source (``source_key()``) is the
same key wherever that source is cited. See
context-v/plans/Hex-Code-Citations-and-a-Repair-Tool.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.connector.errors import ConnectorError

from .conftest import SECTIONS, call
from .fake_claude import Direct, FakeClaude
from .fixtures import canned

STEPS = Path(__file__).resolve().parents[2] / "src" / "connector" / "steps"
SURVEY_URL = "https://example.org/fixture/survey"
_DEFINITION = re.compile(r"^\[\^([^\]\s]+)\]: (.+)$", re.MULTILINE)
_INLINE = re.compile(r"\[\^([^\]\s]+)\](?!:)")


def source_key(definition: str) -> str:
    from src.citation_keys import source_key as key

    return key(definition)


def assign_keys(definitions: dict[str, str]) -> dict[str, str]:
    from src.citation_keys import assign_keys as assign

    return assign(definitions)


def hexed(text: str) -> str:
    """``text`` with its numbered keys replaced by the keys ``source_key()`` gives."""
    mapping = assign_keys(dict(_DEFINITION.findall(text)))
    return re.sub(r"\[\^([^\]\s]+)\]", lambda m: f"[^{mapping.get(m.group(1), m.group(1))}]", text)


def _research_approved(ws, deal: str, content_for) -> dict:
    step = call(ws, "next_step", deal=deal)
    for _ in SECTIONS:
        assert step["step_id"] == "research.section"
        call(
            ws,
            "submit_artifact",
            deal=deal,
            step_id="research.section",
            section=step["section"],
            content=content_for(step["section"]),
            partner_approved=True,
        )
        step = call(ws, "next_step", deal=deal)
    # Steps between research and drafting (research.sources) are walked as usual.
    walk = FakeClaude(Direct(ws)).walk(
        deal, until=lambda s: s["step_id"] == "draft.section", compile=False
    )
    return walk.stopped_at


def _compile_drafts(ws, deal: str, step: dict, drafts: dict[str, str]) -> str:
    for _ in SECTIONS:
        assert step["step_id"] == "draft.section"
        call(
            ws,
            "submit_artifact",
            deal=deal,
            step_id="draft.section",
            section=step["section"],
            content=drafts[step["section"]],
        )
        step = call(ws, "next_step", deal=deal)
    call(ws, "compile", deal=deal, formats=["html"])
    return call(ws, "get_artifact", deal=deal, artifact_id="compile.assemble")["text"]


def _claim_key(memo: str, claim: str) -> str:
    cited = re.search(re.escape(claim) + r"[^\[]*\[\^([^\]\s]+)\]", memo)
    assert cited, claim
    return cited.group(1)


@pytest.mark.spec("CONN-HEX-01")
def test_one_source_cited_by_two_sections_compiles_to_one_hex_key(ws):
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    # Research written the new way: every key is the source's hex key, and the
    # submission check accepts it.
    step = _research_approved(ws, deal, lambda s: hexed(canned.research(s)))

    # The overview cites the survey as [^1] and the market as [^2]: two local
    # keys for one source.
    memo = _compile_drafts(ws, deal, step, canned.conflicting_drafts())
    body, _, block = memo.partition("### Citations")
    definitions = _DEFINITION.findall(block)

    survey = next(d for _, d in definitions if SURVEY_URL in d)
    key = source_key(survey)
    assert _claim_key(body, "Overview claim from the survey.") == key
    assert _claim_key(body, "Market claim from the survey.") == key
    assert [k for k, _ in definitions].count(key) == 1, "one definition for one source"
    assert sum(SURVEY_URL in d for _, d in definitions) == 1


@pytest.mark.spec("CONN-HEX-02")
def test_numbered_drafts_are_accepted_and_compile_to_hex_keys(ws):
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    step = _research_approved(ws, deal, canned.research)

    # Numbered keys, the way every memo was written before hex keys: accepted.
    memo = _compile_drafts(ws, deal, step, canned.conflicting_drafts())
    body, _, block = memo.partition("### Citations")
    definitions = dict(_DEFINITION.findall(block))

    assert len(definitions) == 4
    for key, definition in definitions.items():
        assert key == source_key(definition), f"[^{key}] is not the hex key of {definition[:60]}"
    for claim, url in canned.CONFLICTING_CLAIMS.items():
        assert url in definitions[_claim_key(body, claim)], claim
    assert set(_INLINE.findall(body)) == set(definitions)


@pytest.mark.spec("CONN-HEX-02")
def test_a_hex_key_that_does_not_match_its_source_is_named(ws):
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    step = call(ws, "next_step", deal=deal)
    assert step["step_id"] == "research.section"

    research = hexed(canned.research(step["section"]))
    definitions = dict(_DEFINITION.findall(research))
    right = next(k for k, d in definitions.items() if SURVEY_URL in d)
    # A plausible slip: the key of a different source, written against this one.
    wrong = source_key(
        "2025, Mar 03. [Other](https://example.org/fixture/somewhere-else). Fixture Press."
    )
    assert wrong != right
    mismatched = research.replace(f"[^{right}]", f"[^{wrong}]")

    with pytest.raises(ConnectorError) as raised:
        call(
            ws,
            "submit_artifact",
            deal=deal,
            step_id="research.section",
            section=step["section"],
            content=mismatched,
            partner_approved=True,
        )
    assert raised.value.code == "checks_failed"
    details = " ".join(f["detail"] for f in raised.value.details["failures"])
    assert f"[^{wrong}]" in details
    assert right in details, "the check says which key the source gives"

    # The same research with the right keys is accepted.
    call(
        ws,
        "submit_artifact",
        deal=deal,
        step_id="research.section",
        section=step["section"],
        content=research,
        partner_approved=True,
    )


@pytest.mark.spec("CONN-HEX-03")
def test_research_and_draft_instructions_ask_for_hex_keys(ws):
    numbered = re.compile(r"\[\^(\d+|n|N)\]")
    for step_id in ("research.section", "draft.section", "draft.rewrite"):
        text = (STEPS / f"{step_id}.md").read_text()
        assert not numbered.search(
            text
        ), f"{step_id} still shows a numbered key: {numbered.search(text).group(0)}"
        assert "hex" in text.lower(), f"{step_id} does not ask for hex keys"

    for step_id in ("research.section", "draft.section"):
        text = (STEPS / f"{step_id}.md").read_text().lower()
        # How a key is made: from the source's link, hashed, base 36, six characters.
        assert "sha256" in text or "sha-256" in text, step_id
        assert "base 36" in text or "base36" in text, step_id

    # And the rendered instruction Claude receives says the same.
    deal = FakeClaude(Direct(ws)).create()
    step = call(ws, "next_step", deal=deal)
    assert step["step_id"] == "research.section"
    assert not numbered.search(step["instruction"])
    assert "hex" in step["instruction"].lower()

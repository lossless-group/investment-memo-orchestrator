"""Tests for the membership gate inside remove_invalid_sources.

Loop ticket 3 of `context-v/loops/Frontloaded-Source-Approval-Loop.md`.

The predicate under test is the one the whole plan turns on: a URL is
citable iff it *resolves* AND *was approved*. Everything that already
existed in this agent answers only the first half.

No network calls — `validate_url` is monkeypatched throughout.
"""

import os
from pathlib import Path

import pytest

from src.agents import remove_invalid_sources as ris
from src.agents.remove_invalid_sources import (
    UNAPPROVED,
    _partition_unapproved,
    enforcement_mode,
)
from src.curation import approved_urls, load_sources_md


# --------------------------------------------------------------------------
# enforcement_mode
# --------------------------------------------------------------------------

@pytest.mark.parametrize("env,expected", [
    (None, "flag"),
    ("", "flag"),
    ("flag", "flag"),
    ("FLAG", "flag"),
    ("  enforce  ", "enforce"),
    ("off", "off"),
    ("nonsense", "flag"),      # never silently disables
    ("true", "flag"),          # a truthy-looking value must not mean "off"
])
def test_enforcement_mode_parsing(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("MEMOPOP_SOURCE_ENFORCEMENT", raising=False)
    else:
        monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", env)
    assert enforcement_mode() == expected


def test_unrecognized_mode_fails_closed_not_open(monkeypatch):
    """A typo must not turn enforcement off.

    'flag' still surfaces the leak; 'off' hides it. A misconfiguration
    should degrade to visible, not to silent.
    """
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "enfroce")  # typo
    assert enforcement_mode() != "off"


# --------------------------------------------------------------------------
# _partition_unapproved
# --------------------------------------------------------------------------

def _approved_set(tmp_path, urls):
    inputs = tmp_path / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(f"  - url: {u}" for u in urls)
    (inputs / "Sources.md").write_text(f"---\nmode: codified\nsources:\n{lines}\n---\n")
    return approved_urls(load_sources_md(inputs))


def test_live_fabrication_is_caught(tmp_path):
    """The exact failure the incident report named.

    example.com returns HTTP 200 with a real body — it passes every
    reachability check in the ladder. Only membership catches it.
    """
    approved = _approved_set(tmp_path, ["https://www.iea.org/reports/real"])
    cited = {
        "https://www.iea.org/reports/real",
        "https://example.com/fabricated-placeholder",
    }
    unapproved = _partition_unapproved(cited, approved)
    assert unapproved == {"https://example.com/fabricated-placeholder"}


def test_url_drift_does_not_falsely_flag(tmp_path):
    """A legitimate citation must not be flagged over cosmetic drift.

    If this regressed, the gate would delete good citations — worse than
    the problem it fixes.
    """
    approved = _approved_set(tmp_path, ["https://example.org/report"])
    cited = {
        "https://www.example.org/report/",
        "http://example.org/report?utm_source=x",
        "https://example.org/report#s2",
    }
    assert _partition_unapproved(cited, approved) == set()


def test_wrong_entity_real_article_is_caught(tmp_path):
    """A real, live article about the wrong company is still unapproved.

    This is the Sava case: correct, well-cited data about a different
    entity. Reachability says fine; membership says no.
    """
    approved = _approved_set(tmp_path, ["https://techcrunch.com/2026/01/right-co"])
    cited = {"https://techcrunch.com/2019/08/different-co-series-a"}
    assert len(_partition_unapproved(cited, approved)) == 1


# --------------------------------------------------------------------------
# Agent-level behavior
# --------------------------------------------------------------------------

@pytest.fixture
def deal(tmp_path, monkeypatch):
    """A minimal firm-scoped deal on disk, with one section file.

    Everything is under tmp_path — no canonical or firm-private data is
    written. cwd is moved so find_deal_inputs_dir's relative
    `io/<firm>/deals/<deal>/inputs` convention resolves here.
    """
    firm, company = "test-firm", "TestCo"
    inputs = tmp_path / "io" / firm / "deals" / company / "inputs"
    inputs.mkdir(parents=True)
    inputs.write_text if False else None

    output_dir = tmp_path / "out" / f"{company}-v0.0.1"
    (output_dir / "2-sections").mkdir(parents=True)
    (output_dir / "1-research").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "src.utils.get_output_dir_from_state", lambda state: output_dir, raising=False
    )
    monkeypatch.setattr(
        ris, "get_latest_output_dir", lambda *a, **k: output_dir, raising=False
    )
    return {
        "inputs": inputs,
        "output_dir": output_dir,
        "state": {"company_name": company, "firm": firm},
    }


def _write_codified(inputs: Path, urls):
    lines = "\n".join(f"  - url: {u}\n    title: 'T'" for u in urls)
    (inputs / "Sources.md").write_text(f"---\nmode: codified\nsources:\n{lines}\n---\n")


def _write_section(output_dir: Path, url_by_num: dict):
    """Write a section file in the pipeline's real citation format.

    Definitions are BLANK-LINE separated, matching what
    `citation_assembly.format_citation_block` emits and what real memos on
    disk contain. Packing definitions onto consecutive lines instead
    exposes an unrelated pre-existing fragility in definition removal
    (a line-start `[^N]:` gets stripped as an inline ref, orphaning its
    text onto the previous line) — a real bug, but not this gate's, and
    not one a fixture should be smuggling into these assertions.
    """
    body = "\n".join(f"Claim {n}.[^{n}]" for n in url_by_num)
    defs = "\n\n".join(
        f"[^{n}]: 2026, Jan 01. [T]({u}). Pub. Published: 2026-01-01 | Updated: N/A"
        for n, u in url_by_num.items()
    )
    (output_dir / "2-sections" / "01-overview.md").write_text(
        f"## Overview\n\n{body}\n\n---\n\n### Citations\n\n{defs}\n"
    )


def test_flag_mode_reports_but_does_not_remove(deal, monkeypatch, capsys):
    """Default mode makes the leak visible without touching prose."""
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "flag")
    monkeypatch.setattr(ris, "validate_url", lambda url, timeout=8: (url, 200, "OK"))

    _write_codified(deal["inputs"], ["https://good.test/a"])
    _write_section(deal["output_dir"], {
        1: "https://good.test/a",
        2: "https://example.com/fabricated",
    })

    ris.remove_invalid_sources_agent(deal["state"])

    out = capsys.readouterr().out
    assert "Membership check" in out
    assert "flagging (not removing)" in out
    section = (deal["output_dir"] / "2-sections" / "01-overview.md").read_text()
    # Nothing removed in flag mode — the fabricated citation is still there.
    assert "example.com/fabricated" in section


def test_enforce_mode_removes_the_unapproved_citation(deal, monkeypatch):
    """The claim the plan turns on, end to end.

    Note the agent moves citation *definitions* out of section files and
    into the assembled final draft (PASS 2 strips defs, preserving inline
    IDs). So the section is checked for inline markers and the final
    draft for URLs — checking the section for a URL would always fail.
    """
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "enforce")
    monkeypatch.setattr(ris, "validate_url", lambda url, timeout=8: (url, 200, "OK"))

    _write_codified(deal["inputs"], ["https://good.test/a"])
    _write_section(deal["output_dir"], {
        1: "https://good.test/a",
        2: "https://example.com/fabricated",
    })

    ris.remove_invalid_sources_agent(deal["state"])

    section = (deal["output_dir"] / "2-sections" / "01-overview.md").read_text()
    assert "[^1]" in section, "approved citation's inline marker was wrongly removed"
    assert "[^2]" not in section, "unapproved citation's inline marker survived"

    # The redaction worksheet is excluded on purpose — it is *supposed* to
    # name every dropped URL (asserted separately below).
    drafts = [
        p for p in deal["output_dir"].glob("*.md")
        if p.name != "redacted-hallucinations.md"
    ]
    assert drafts, "no final draft assembled"
    final = "\n".join(p.read_text() for p in drafts)
    assert "good.test/a" in final, "approved URL missing from final draft"
    assert "example.com/fabricated" not in final, "unapproved URL reached final draft"


def test_dropped_url_is_recorded_for_the_analyst(deal, monkeypatch):
    """A membership drop must be visible, never silent.

    An unapproved citation usually means the writer had a claim it could
    not source from the approved set — that is signal the analyst needs,
    not noise to swallow. The plan makes worksheet visibility a
    requirement of the feature, so it is tested as one.
    """
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "enforce")
    monkeypatch.setattr(ris, "validate_url", lambda url, timeout=8: (url, 200, "OK"))

    _write_codified(deal["inputs"], ["https://good.test/a"])
    _write_section(deal["output_dir"], {
        1: "https://good.test/a",
        2: "https://example.com/fabricated",
    })

    ris.remove_invalid_sources_agent(deal["state"])

    worksheet = deal["output_dir"] / "redacted-hallucinations.md"
    assert worksheet.exists(), "no analyst worksheet written"
    assert "example.com/fabricated" in worksheet.read_text(), \
        "dropped URL was removed silently — analyst has no record of it"


def test_non_codified_deal_is_untouched(deal, monkeypatch, capsys):
    """The regression that matters most.

    Everything here is gated on is_codified(). A deal without codified
    mode must behave exactly as it did before this feature existed.
    """
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "enforce")
    monkeypatch.setattr(ris, "validate_url", lambda url, timeout=8: (url, 200, "OK"))

    (deal["inputs"] / "Sources.md").write_text(
        "---\nmode: search\nsources:\n  - url: https://good.test/a\n---\n"
    )
    _write_section(deal["output_dir"], {
        1: "https://good.test/a",
        2: "https://anything.test/b",
    })

    ris.remove_invalid_sources_agent(deal["state"])

    section = (deal["output_dir"] / "2-sections" / "01-overview.md").read_text()
    assert "anything.test/b" in section
    assert "good.test/a" in section
    assert "NOT in the analyst's approved set" not in capsys.readouterr().out


def test_no_sources_md_at_all_is_untouched(deal, monkeypatch):
    """No Sources.md → legacy behavior, never "everything is unapproved"."""
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "enforce")
    monkeypatch.setattr(ris, "validate_url", lambda url, timeout=8: (url, 200, "OK"))

    _write_section(deal["output_dir"], {1: "https://anything.test/b"})
    ris.remove_invalid_sources_agent(deal["state"])

    section = (deal["output_dir"] / "2-sections" / "01-overview.md").read_text()
    assert "anything.test/b" in section


def test_off_mode_disables_the_check(deal, monkeypatch, capsys):
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "off")
    monkeypatch.setattr(ris, "validate_url", lambda url, timeout=8: (url, 200, "OK"))

    _write_codified(deal["inputs"], ["https://good.test/a"])
    _write_section(deal["output_dir"], {
        1: "https://good.test/a",
        2: "https://example.com/fabricated",
    })

    ris.remove_invalid_sources_agent(deal["state"])
    assert "Membership check" not in capsys.readouterr().out


def test_recovery_is_not_attempted_for_unapproved_urls(deal, monkeypatch):
    """Recovering a fabrication would launder it into a live URL.

    An unapproved URL that is also dead must never reach the recovery
    pass — otherwise Tavily finds *something*, the swap happens, and the
    result passes every downstream check.
    """
    monkeypatch.setenv("MEMOPOP_SOURCE_ENFORCEMENT", "enforce")

    def fake_validate(url, timeout=8):
        return (url, 404, "Not Found") if "dead" in url else (url, 200, "OK")

    monkeypatch.setattr(ris, "validate_url", fake_validate)

    seen = {}

    def fake_recovery(invalid_urls, *a, **k):
        seen["candidates"] = set(invalid_urls)
        return set(), []

    monkeypatch.setattr(ris, "_run_recovery_pass", fake_recovery)

    _write_codified(deal["inputs"], ["https://good.test/dead-but-approved"])
    _write_section(deal["output_dir"], {
        1: "https://good.test/dead-but-approved",
        2: "https://example.com/dead-and-unapproved",
    })

    ris.remove_invalid_sources_agent(deal["state"])

    assert "https://good.test/dead-but-approved" in seen["candidates"], \
        "an approved-but-drifted URL must still be offered to recovery"
    assert "https://example.com/dead-and-unapproved" not in seen["candidates"], \
        "an unapproved URL must never be recovered"


def test_unapproved_verdict_code_is_distinct():
    """UNAPPROVED must not collide with any reachability code."""
    from src.agents.remove_invalid_sources import (
        HALLUCINATION_PATTERN, PAYWALL_STUB, SOFT_404_BODY, VERIFIED_GATED,
    )
    codes = [HALLUCINATION_PATTERN, SOFT_404_BODY, PAYWALL_STUB, VERIFIED_GATED]
    assert UNAPPROVED not in codes

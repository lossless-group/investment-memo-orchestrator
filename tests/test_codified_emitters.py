"""Tests for closing the URL emitters in codified mode (loop ticket 4).

Two agents can introduce sources after the codified researcher has
finished obeying the approved set:

  * `citation_enrichment` — exists to ask Perplexity for NEW sources.
    Full no-op in codified mode.
  * `fact_corrector` — inserts the `source_url` the verifier proposed.
    Keeps correcting facts; the out-of-set URL is stripped.

`fact_verifier` is deliberately NOT gated: it only reports a proposed
source, it never writes one into prose. The corrector is the injection
point, so that is where the filter belongs.
"""

import json
from pathlib import Path

import pytest

from src.agents import citation_enrichment as ce
from src.agents import fact_corrector as fc


@pytest.fixture
def deal(tmp_path, monkeypatch):
    firm, company = "test-firm", "TestCo"
    inputs = tmp_path / "io" / firm / "deals" / company / "inputs"
    inputs.mkdir(parents=True)
    output_dir = tmp_path / "out" / f"{company}-v0.0.1"
    (output_dir / "2-sections").mkdir(parents=True)
    (output_dir / "1-research").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "src.utils.get_output_dir_from_state", lambda state: output_dir, raising=False
    )
    return {
        "inputs": inputs,
        "output_dir": output_dir,
        "state": {"company_name": company, "firm": firm},
    }


def _codify(inputs: Path, urls):
    lines = "\n".join(f"  - url: {u}\n    title: 'T'" for u in urls)
    (inputs / "Sources.md").write_text(f"---\nmode: codified\nsources:\n{lines}\n---\n")


# --------------------------------------------------------------------------
# citation_enrichment
# --------------------------------------------------------------------------

def test_enrichment_is_a_noop_in_codified_mode(deal, monkeypatch, capsys):
    """The agent must not even reach its Perplexity setup."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "sk-should-never-be-used")

    def explode(*a, **k):  # pragma: no cover - must not run
        raise AssertionError("citation_enrichment called out to Perplexity in codified mode")

    monkeypatch.setattr("openai.OpenAI", explode, raising=False)

    _codify(deal["inputs"], ["https://good.test/a"])
    result = ce.citation_enrichment_agent(deal["state"])

    assert "codified mode" in " ".join(result["messages"]).lower()
    assert "skipped" in capsys.readouterr().out.lower()


def test_enrichment_still_runs_when_not_codified(deal, monkeypatch):
    """The broad-search path must be unaffected.

    Without an API key the agent returns its own 'no key' message — the
    point is that it got *past* the codified guard to reach that check.
    """
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    (deal["inputs"] / "Sources.md").write_text(
        "---\nmode: search\nsources:\n  - url: https://good.test/a\n---\n"
    )
    result = ce.citation_enrichment_agent(deal["state"])
    msg = " ".join(result["messages"]).lower()
    assert "codified" not in msg
    assert "perplexity api key" in msg


def test_enrichment_still_runs_with_no_sources_file(deal, monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    result = ce.citation_enrichment_agent(deal["state"])
    assert "codified" not in " ".join(result["messages"]).lower()


# --------------------------------------------------------------------------
# fact_corrector
# --------------------------------------------------------------------------

def _write_verified(output_dir: Path, claims):
    (output_dir / "4-fact-check-verified.json").write_text(
        json.dumps({"claims_to_correct": claims})
    )


def _claims():
    return [
        {
            "section": "01-overview",
            "original_claim": "ARR was $58M",
            "correct_value": "ARR was $3M",
            "source_url": "https://example.com/fabricated",
            "source_title": "Fabricated",
            "source_date": "2026-01-01",
        },
        {
            "section": "01-overview",
            "original_claim": "Founded 2019",
            "correct_value": "Founded 2020",
            "source_url": "https://good.test/a",
            "source_title": "Good",
            "source_date": "2026-01-01",
        },
    ]


def test_strip_removes_only_the_unapproved_source(deal):
    """The correction survives; only its unapproved source is removed.

    Dropping the claim outright would discard a correct fact fix over a
    sourcing problem — the fix stands on the approved corpus instead.
    """
    _codify(deal["inputs"], ["https://good.test/a"])
    claims = _claims()

    assert fc.strip_unapproved_sources(claims, deal["state"]) == 1

    fabricated, good = claims
    assert fabricated["source_url"] is None
    assert fabricated["source_stripped_reason"] == "not in approved source set"
    assert fabricated["correct_value"] == "ARR was $3M", "the correction was lost"
    assert good["source_url"] == "https://good.test/a", "approved source was stripped"
    assert len(claims) == 2, "a claim was dropped, not just its URL"


def test_strip_leaves_approved_urls_alone(deal):
    _codify(deal["inputs"], ["https://good.test/a", "https://example.com/fabricated"])
    claims = _claims()
    assert fc.strip_unapproved_sources(claims, deal["state"]) == 0
    assert all(c["source_url"] for c in claims)


def test_strip_is_a_noop_when_not_codified(deal):
    """The broad-search path must be untouched."""
    (deal["inputs"] / "Sources.md").write_text(
        "---\nmode: search\nsources:\n  - url: https://good.test/a\n---\n"
    )
    claims = _claims()
    assert fc.strip_unapproved_sources(claims, deal["state"]) == 0
    assert claims[0]["source_url"] == "https://example.com/fabricated"


def test_strip_is_a_noop_with_no_sources_file(deal):
    claims = _claims()
    assert fc.strip_unapproved_sources(claims, deal["state"]) == 0
    assert claims[0]["source_url"] == "https://example.com/fabricated"


def test_corrector_reports_the_strip(deal, monkeypatch, capsys):
    """End to end through the agent, stopping at its own API-key check."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        "src.utils.get_output_dir_from_state", lambda s: deal["output_dir"], raising=False
    )
    _codify(deal["inputs"], ["https://good.test/a"])
    _write_verified(deal["output_dir"], _claims())

    fc.fact_corrector_agent(deal["state"])

    assert "stripped 1 out-of-set source URL" in capsys.readouterr().out

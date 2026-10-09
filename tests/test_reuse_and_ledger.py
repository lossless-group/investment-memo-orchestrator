"""
Reuse gates and the search ledger.

Spec: context-v/specs/Reuse-and-Augment-Research-Across-Runs.md
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import research_ledger as rl
from src.agents import codified_section_researcher as csr
from src.curation.sources_md import SourceEntry


# ── Search ledger ───────────────────────────────────────────────────────────

def test_ttl_is_short_for_volatile_queries_and_long_otherwise(monkeypatch):
    monkeypatch.delenv("MEMOPOP_SEARCH_TTL_DAYS", raising=False)
    assert rl.ttl_days_for("Lambda Series E valuation") == rl.VOLATILE_TTL_DAYS
    assert rl.ttl_days_for("Lambda founders background") == rl.STABLE_TTL_DAYS


def test_cached_search_answers_from_ledger_within_ttl(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMOPOP_REFRESH_SEARCHES", raising=False)
    ledger = rl.ResearchLedger(tmp_path / rl.LEDGER_NAME)
    calls = []

    def search():
        calls.append(1)
        return [{"title": "t", "url": "https://a.example", "content": "c"}]

    first = rl.cached_search({}, "company_research", "Acme founders", "tavily", search, ledger=ledger)
    second = rl.cached_search({}, "company_research", "  acme   FOUNDERS ", "tavily", search, ledger=ledger)
    assert first == second
    assert len(calls) == 1, "a repeated query within its TTL must not search again"
    assert (tmp_path / rl.LEDGER_MD_NAME).exists()


def test_expired_and_refreshed_searches_run_again(tmp_path, monkeypatch):
    ledger = rl.ResearchLedger(tmp_path / rl.LEDGER_NAME)
    ledger.record("company_research", "Acme funding round", "tavily", [])
    ledger.entries[0]["searched_at"] = (datetime.now() - timedelta(days=30)).isoformat()
    assert ledger.lookup("company_research", "Acme funding round") is None  # 7-day TTL

    ledger.record("company_research", "Acme founders", "tavily", [])
    monkeypatch.setenv("MEMOPOP_REFRESH_SEARCHES", "1")
    assert ledger.lookup("company_research", "Acme founders") is None


# ── Section research gate ───────────────────────────────────────────────────

SECTION = SimpleNamespace(name="Fundraising Round", filename="06-fundraising-round.md")
IDX = 6


def _setup(tmp_path, prior_urls, prior_text=None):
    """A deal with a prior version (v0.0.1) whose section research was built from prior_urls."""
    outputs = tmp_path / "outputs"
    prior = outputs / "Deal-v0.0.1" / "1-research"
    prior.mkdir(parents=True)
    current = outputs / "Deal-v0.0.2" / "1-research"
    current.mkdir(parents=True)
    name = csr.research_filename_for(IDX, SECTION)
    (prior / name).write_text(prior_text or "# Fundraising Round — Research\n\nPrior findings.\n")
    fetched = {u: {"markdown": f"content of {u}"} for u in prior_urls}
    fps = {name: csr._section_fingerprint([SourceEntry(url=u) for u in prior_urls], fetched)}
    (prior / csr.FINGERPRINTS_NAME).write_text(json.dumps(fps))
    state = {"output_dir": str(outputs / "Deal-v0.0.2"), "frame": None}
    return current, state, name


def _run(current, state, urls, synth_calls):
    fetched = {u: {"markdown": f"content of {u}"} for u in urls}
    usable = [SourceEntry(url=u) for u in urls]

    def synthesize(research_dir, idx, section, entries, fetched_, state_):
        synth_calls.append([e.url for e in entries])
        (Path(research_dir) / csr.research_filename_for(idx, section)).write_text(
            "# New\n\nFindings from " + ", ".join(e.url for e in entries) + "\n"
        )

    prior_fps = csr._load_prior_fingerprints(current, state)
    fps = dict(prior_fps)
    decision = csr._reuse_or_augment(current, IDX, SECTION, usable, fetched, state, synthesize, prior_fps, fps)
    return decision, fps


def test_unchanged_sources_reuse_the_prior_research_with_no_synthesis(tmp_path):
    current, state, name = _setup(tmp_path, ["https://a", "https://b"])
    calls = []
    decision, _ = _run(current, state, ["https://a", "https://b"], calls)
    assert decision == "reused"
    assert calls == []
    assert (current / name).read_text() == (current.parent.parent / "Deal-v0.0.1" / "1-research" / name).read_text()


def test_added_sources_are_synthesized_alone_and_appended(tmp_path):
    current, state, name = _setup(tmp_path, ["https://a"])
    calls = []
    decision, fps = _run(current, state, ["https://a", "https://new"], calls)
    assert decision == "augmented"
    assert calls == [["https://new"]], "only the net-new source is synthesized"
    text = (current / name).read_text()
    assert "Prior findings." in text, "existing research must survive"
    assert "frame=augment" in text and "Findings from https://new" in text
    assert set(fps[name]) == {"https://a", "https://new"}


def test_removed_source_regenerates_the_section(tmp_path):
    current, state, _ = _setup(tmp_path, ["https://a", "https://b"])
    decision, _ = _run(current, state, ["https://a"], [])
    assert decision == "synthesize"


def test_frame_reuse_is_a_hard_skip(tmp_path):
    current, state, name = _setup(tmp_path, ["https://a"])
    directive = SimpleNamespace(research="reuse", researches=False)
    state["frame"] = SimpleNamespace(directive_for=lambda filename: directive, slug="f")
    calls = []
    decision, _ = _run(current, state, ["https://a", "https://new"], calls)
    assert decision == "skipped"
    assert calls == [], "a frame's research: reuse must never re-synthesize"
    assert "Prior findings." in (current / name).read_text()


def test_fresh_bypasses_every_gate(tmp_path):
    current, state, _ = _setup(tmp_path, ["https://a"])
    state["fresh"] = True
    decision, _ = _run(current, state, ["https://a"], [])
    assert decision == "synthesize"


def test_legacy_prior_without_fingerprint_treats_cited_sources_as_covered(tmp_path):
    current, state, name = _setup(tmp_path, [], prior_text="# R\n\nSee [^1].\n\n[^1]: https://a\n")
    (tmp_path / "outputs" / "Deal-v0.0.1" / "1-research" / csr.FINGERPRINTS_NAME).unlink()
    calls = []
    decision, _ = _run(current, state, ["https://a", "https://b"], calls)
    assert decision == "augmented"
    assert calls == [["https://b"]]

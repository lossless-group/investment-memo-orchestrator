"""
Tests for the per-section revision gate.

The gate is the whole product here. A revision that improves an argument while
quietly dropping two citations and a revenue figure is worse than no revision,
because the loss is invisible in the prose — it reads *better*. So what is
tested is not that the model writes well, but that a rewrite which drops
something is caught, itemised, and refused.

The session that produced this saw both failure modes for real: revise_summaries
took the Executive Summary from 2 citations to 0 with nothing said, and the
first live revision here dropped a quoted span and was made to put it back.
"""

import json
from pathlib import Path

import pytest

import src.agents.section_reviser as sr
from src.agents.section_reviser import Losses, Preservation, revise_section
from src.llm_provider import LLMResponse

SECTION = """## 6. Opportunity

The standalone block covers 5.8M policies [^1] and the company projects
$100M+ ARR at a $60-80K blended ACV [^2]. Management called it "the one place
where incentives align" [^3].
"""


def _respond(monkeypatch, *texts):
    """Script complete() with successive drafts."""
    calls = []

    def fake(prompt, **kwargs):
        calls.append(prompt)
        return LLMResponse(text=texts[min(len(calls) - 1, len(texts) - 1)], provider="cli")

    monkeypatch.setattr(sr, "complete", fake)
    return calls


@pytest.fixture
def section(tmp_path):
    d = tmp_path / "2-sections"
    d.mkdir()
    p = d / "06-opportunity.md"
    p.write_text(SECTION)
    return p


# --- what counts as "preserved" -----------------------------------------


def test_preservation_captures_citations_figures_and_quotes():
    keep = Preservation.of(SECTION)
    assert keep.citations == {"1", "2", "3"}
    assert any("5.8" in f for f in keep.figures), "a bare scaled count must be protected"
    assert any("100" in f for f in keep.figures)
    assert any("incentives align" in q for q in keep.quotes), (
        "a quote that wraps across lines is still a quote"
    )


def test_bare_scaled_counts_are_protected_unlike_grounding():
    """grounding._FIGURE_PATTERN requires $, a comma group, or a % sign, so
    "5.8M policies" and "2-5X throughput" were invisible to it. Those are
    exactly the stats a memo turns on."""
    keep = Preservation.of("The block is 5.8M policies and throughput is 2-5X [^1].")
    assert any("5.8" in f for f in keep.figures)
    assert any("2-5" in f for f in keep.figures)


def test_figures_in_the_citation_list_are_not_treated_as_claims():
    """Dates and page numbers in the reference list are not statistics."""
    with_refs = SECTION + "\n### Citations\n\n[^1]: 2026, Aug 03. Something. p. 1,234\n"
    assert Preservation.of(with_refs).figures == Preservation.of(SECTION).figures


def test_rephrasing_a_figure_still_counts_as_kept():
    """A revision may re-punctuate a number it keeps; deleting is the offence."""
    before = Preservation.of('Revenue hit $5,900,000 [^1].')
    after = Preservation.of('Revenue reached $5,900,000 in the period [^1].')
    assert not sr._compare(before, after).any


def test_dropping_a_citation_is_a_loss():
    before = Preservation.of(SECTION)
    after = Preservation.of(SECTION.replace("[^2]", ""))
    losses = sr._compare(before, after)
    assert losses.citations == ["2"]
    assert losses.any


def test_dropping_a_figure_is_a_loss():
    before = Preservation.of(SECTION)
    after = Preservation.of(SECTION.replace("$100M+", "substantial"))
    assert sr._compare(before, after).figures


# --- the gate ------------------------------------------------------------


def test_clean_revision_is_written(section, monkeypatch):
    revised = SECTION.replace("## 6. Opportunity", "## 6. Opportunity").replace(
        "The standalone block", "Long-term care first. The standalone block")
    _respond(monkeypatch, revised)
    result = revise_section(section, "lead with LTC")
    assert result.accepted
    assert "Long-term care first" in section.read_text()


def test_a_lossy_revision_is_never_written(section, monkeypatch):
    lossy = "## 6. Opportunity\n\nThe block is large and the company is ambitious.\n"
    _respond(monkeypatch, lossy, lossy)  # fails twice
    result = revise_section(section, "tighten", max_attempts=2)
    assert not result.accepted
    assert section.read_text() == SECTION, "the original must survive a failed gate"
    assert "rejected" in result.reason


def test_the_correction_names_what_was_dropped_and_shows_the_draft(section, monkeypatch):
    lossy = "## 6. Opportunity\n\nThe standalone block covers 5.8M policies [^1].\n"
    clean = SECTION.replace("The standalone", "Leading with carriers: the standalone")
    calls = _respond(monkeypatch, lossy, clean)

    result = revise_section(section, "tighten", max_attempts=2)

    assert result.accepted, "the corrected second attempt should be accepted"
    correction = calls[1]
    assert "[^2]" in correction and "[^3]" in correction, "lost markers must be itemised"
    assert "YOUR PREVIOUS DRAFT" in correction, (
        "the model cannot 'keep what was correct' about a draft it cannot see"
    )


def test_one_attempt_means_no_correction_round(section, monkeypatch):
    lossy = "## 6. Opportunity\n\nNothing survives.\n"
    calls = _respond(monkeypatch, lossy)
    result = revise_section(section, "x", max_attempts=1)
    assert not result.accepted
    assert len(calls) == 1


def test_a_failed_model_call_leaves_the_section_alone(section, monkeypatch):
    monkeypatch.setattr(
        sr, "complete",
        lambda prompt, **kw: LLMResponse(text="", provider="cli", error="429"),
    )
    result = revise_section(section, "x")
    assert not result.accepted
    assert "429" in result.reason
    assert section.read_text() == SECTION


# --- the archive ---------------------------------------------------------


def test_archive_records_every_attempt_and_the_verdict(section, monkeypatch):
    lossy = "## 6. Opportunity\n\nThe standalone block covers 5.8M policies [^1].\n"
    clean = SECTION.replace("The standalone", "Carriers first: the standalone")
    _respond(monkeypatch, lossy, clean)

    result = revise_section(section, "lead with carriers", max_attempts=2)
    a = result.archive_dir

    assert (a / "before.md").read_text() == SECTION
    assert (a / "angle.md").read_text().strip() == "lead with carriers"
    assert (a / "attempt-1.md").exists() and (a / "attempt-2.md").exists()
    assert (a / "accepted.md").exists()

    report = json.loads((a / "report.json").read_text())
    assert report["accepted"] is True
    assert report["attempts"][0]["lost_citations"] == ["2", "3"]
    assert report["attempts"][1]["lost_citations"] == []


def test_a_rejection_is_archived_without_an_accepted_file(section, monkeypatch):
    lossy = "## 6. Opportunity\n\nGone.\n"
    _respond(monkeypatch, lossy, lossy)
    result = revise_section(section, "x", max_attempts=2)
    a = result.archive_dir
    assert not (a / "accepted.md").exists()
    assert json.loads((a / "report.json").read_text())["accepted"] is False


def test_archive_is_a_subdirectory_so_assembly_cannot_glob_it(section, monkeypatch):
    """Assembly does sections_dir.glob("*.md"), non-recursive. A sibling archive
    file would be concatenated into the memo."""
    _respond(monkeypatch, SECTION)
    result = revise_section(section, "x")
    assembled = sorted(p.name for p in section.parent.glob("*.md"))
    assert assembled == ["06-opportunity.md"], f"archive leaked into assembly: {assembled}"
    assert result.archive_dir.is_relative_to(section.parent / "_revisions")


# --- no new facts --------------------------------------------------------


def test_the_prompt_forbids_new_facts_and_offers_a_gap_marker(section, monkeypatch):
    calls = _respond(monkeypatch, SECTION)
    revise_section(section, "add the 2027 forecast")
    prompt = calls[0]
    assert "no research tool" in prompt
    assert "REVISION-GAP:" in prompt, (
        "a request the section cannot support needs a way to say so that is not "
        "an invented fact"
    )


def test_unresolved_markers_are_called_out_for_preservation(tmp_path, monkeypatch):
    d = tmp_path / "2-sections"; d.mkdir()
    p = d / "07-risks.md"
    p.write_text('## 7. Risks\n\n<needs-source claim="ARR" />\n\nRevenue was $1M [^1].\n')
    calls = _respond(monkeypatch, p.read_text())
    revise_section(p, "sharpen")
    assert "needs-source" in calls[0]


# --- operator notes must not reach the memo ------------------------------


def test_gap_lines_are_lifted_out_of_the_prose(section, monkeypatch):
    """REVISION-GAP is the model telling the operator the section cannot support
    the angle. It is meta-commentary about the revision, and AGENTS.md §6 says
    the reader does not know a revision happened."""
    revised = (
        "## 6. Opportunity\n\n"
        "The standalone block covers 5.8M policies [^1] and the company projects\n"
        "$100M+ ARR at a $60-80K blended ACV [^2]. Management called it \"the one place\n"
        "where incentives align\" [^3].\n\n"
        "REVISION-GAP: no carrier-side figures exist in this section.\n"
    )
    _respond(monkeypatch, revised)
    result = revise_section(section, "lead with carriers")

    assert result.accepted
    written = section.read_text()
    assert "REVISION-GAP" not in written, "an operator note shipped into the memo"
    assert result.gaps == ["no carrier-side figures exist in this section."]


def test_a_gap_line_cannot_satisfy_a_preservation_check(section, monkeypatch):
    """A gap line naming a figure would otherwise 'preserve' a figure the prose
    actually deleted."""
    cheating = (
        "## 6. Opportunity\n\nThe block is large [^1][^2][^3].\n\n"
        "REVISION-GAP: could not place 5.8M policies or $100M+ ARR or "
        '"the one place where incentives align".\n'
    )
    _respond(monkeypatch, cheating, cheating)
    result = revise_section(section, "tighten", max_attempts=2)
    assert not result.accepted, "figures named only in a gap line are still lost"
    assert section.read_text() == SECTION


def test_gaps_are_archived_for_follow_up(section, monkeypatch):
    revised = SECTION + "\nREVISION-GAP: the carrier pilot has no named counterparty.\n"
    _respond(monkeypatch, revised)
    result = revise_section(section, "x")
    assert (result.archive_dir / "gaps.md").exists()
    assert "named counterparty" in (result.archive_dir / "gaps.md").read_text()
    assert "named counterparty" in json.loads(
        (result.archive_dir / "report.json").read_text())["gaps"][0]

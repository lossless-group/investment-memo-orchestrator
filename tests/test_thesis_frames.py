"""
Tests for thesis frames — the loader, the directive vocabulary, and the prompt
blocks the agents inject.

The property these tests exist to defend, above all others:

    A run with no frame must behave exactly as it did before frames existed.

Every injection point returns an empty string for a None frame, and the guards
are written so that silence in a frame file means "don't touch it". Those are
the assertions that keep this feature from changing anyone's output until they
ask for it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.frame_context import evidence_paths, research_block, writer_block
from src.frame_loader import (
    FrameError,
    frames_dir_for,
    list_frames,
    load_frame,
    parse_frame,
    validate_against_outline,
)
from src.schemas.frame_schema import SectionDirective

MINIMAL = {
    "name": "Test Frame",
    "slug": "test-frame",
    "stance": "re-sequencing",
    "premise": "The carrier becomes the lead customer.",
    "affects": {
        "01-executive-summary.md": {"research": "extend", "prose": "rewrite"},
        "09-funding-terms.md": {"research": "reuse", "prose": "unchanged"},
    },
}

OUTLINE_SECTIONS = [
    "01-executive-summary.md", "02-origins.md", "03-opening.md", "04-organization.md",
    "05-offering.md", "06-opportunity.md", "07-risks.md", "08-scorecard-summary.md",
    "09-funding-terms.md", "10-closing-assessment.md",
]


def write_frame(tmp_path: Path, data: dict, *, firm="testfirm", deal="TestDeal", slug="test-frame") -> Path:
    d = frames_dir_for(firm, deal, root=tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return p


# --- Parsing -----------------------------------------------------------------

class TestParse:
    def test_minimal_frame_parses(self):
        f = parse_frame(MINIMAL)
        assert f.name == "Test Frame"
        assert f.stance == "re-sequencing"
        assert f.directive_for("01-executive-summary.md").research == "extend"

    def test_premise_is_required(self):
        data = {k: v for k, v in MINIMAL.items() if k != "premise"}
        with pytest.raises(FrameError, match="premise"):
            parse_frame(data)

    def test_name_is_required(self):
        data = {k: v for k, v in MINIMAL.items() if k != "name"}
        with pytest.raises(FrameError, match="name"):
            parse_frame(data)

    def test_unknown_stance_rejected(self):
        with pytest.raises(FrameError, match="stance"):
            parse_frame({**MINIMAL, "stance": "sideways"})

    def test_unknown_research_directive_rejected(self):
        data = {**MINIMAL, "affects": {"01-executive-summary.md": {"research": "obliterate", "prose": "rewrite"}}}
        with pytest.raises(FrameError, match="research"):
            parse_frame(data)

    def test_unknown_prose_directive_rejected(self):
        data = {**MINIMAL, "affects": {"01-executive-summary.md": {"research": "extend", "prose": "yolo"}}}
        with pytest.raises(FrameError, match="prose"):
            parse_frame(data)

    def test_bare_string_is_prose_shorthand_with_additive_research(self):
        """`05-offering.md: amend` should mean {extend, amend} — a frame that names
        a section almost always has new evidence for it."""
        f = parse_frame({**MINIMAL, "affects": {"05-offering.md": "amend"}})
        d = f.directive_for("05-offering.md")
        assert (d.research, d.prose) == ("extend", "amend")

    def test_bare_unchanged_does_not_trigger_research(self):
        f = parse_frame({**MINIMAL, "affects": {"09-funding-terms.md": "unchanged"}})
        d = f.directive_for("09-funding-terms.md")
        assert (d.research, d.prose) == ("reuse", "unchanged")
        assert d.is_inert

    def test_slug_derived_from_name_when_absent(self):
        f = parse_frame({k: v for k, v in MINIMAL.items() if k != "slug"})
        assert f.slug == "test-frame"

    def test_evidence_accepts_string_or_mapping(self):
        f = parse_frame({**MINIMAL, "evidence": ["a.md", {"path": "b.md", "note": "n"}]})
        assert evidence_paths(f) == ["a.md", "b.md"]
        assert f.evidence[1].note == "n"

    def test_evidence_without_path_rejected(self):
        with pytest.raises(FrameError, match="path"):
            parse_frame({**MINIMAL, "evidence": [{"note": "no path"}]})


# --- Defaults: silence must be safe -----------------------------------------

class TestDefaults:
    def test_section_absent_from_affects_is_inert(self):
        f = parse_frame(MINIMAL)
        d = f.directive_for("06-opportunity.md")
        assert d.is_inert
        assert not d.researches and not d.writes

    def test_directive_default_is_reuse_unchanged(self):
        d = SectionDirective()
        assert (d.research, d.prose) == ("reuse", "unchanged")

    def test_sections_in_scope_excludes_inert(self):
        f = parse_frame(MINIMAL)
        assert f.sections_in_scope() == ["01-executive-summary.md"]


# --- Outline validation ------------------------------------------------------

class TestOutlineValidation:
    def test_valid_frame_passes(self):
        validate_against_outline(parse_frame(MINIMAL), OUTLINE_SECTIONS)

    def test_unknown_section_in_affects_rejected(self):
        f = parse_frame({**MINIMAL, "affects": {"99-nonexistent.md": "rewrite"}})
        with pytest.raises(FrameError, match="99-nonexistent"):
            validate_against_outline(f, OUTLINE_SECTIONS)

    def test_on_disk_drift_is_rejected_not_silently_accepted(self):
        """v0.0.3 wrote `07-risks--what-could-go-wrong.md`; the outline declares
        `07-risks.md`. A frame keying off the on-disk name must fail loudly."""
        f = parse_frame({**MINIMAL, "affects": {"07-risks--what-could-go-wrong.md": "amend"}})
        with pytest.raises(FrameError, match="outline"):
            validate_against_outline(f, OUTLINE_SECTIONS)

    def test_unknown_section_in_questions_rejected(self):
        f = parse_frame({**MINIMAL, "questions": {"99-nope.md": ["q?"]}})
        with pytest.raises(FrameError, match="99-nope"):
            validate_against_outline(f, OUTLINE_SECTIONS)


# --- Loading from disk -------------------------------------------------------

class TestLoad:
    def test_round_trip(self, tmp_path):
        write_frame(tmp_path, MINIMAL)
        f = load_frame("test-frame", firm="testfirm", deal="TestDeal",
                       outline_filenames=OUTLINE_SECTIONS, root=tmp_path)
        assert f.name == "Test Frame"
        assert f.source_path is not None

    def test_missing_frame_lists_what_is_available(self, tmp_path):
        write_frame(tmp_path, MINIMAL, slug="only-this-one")
        with pytest.raises(FrameError, match="only-this-one"):
            load_frame("absent", firm="testfirm", deal="TestDeal", root=tmp_path)

    def test_list_frames_empty_when_no_directory(self, tmp_path):
        assert list_frames("nofirm", "NoDeal", root=tmp_path) == []

    def test_list_frames_finds_them(self, tmp_path):
        write_frame(tmp_path, MINIMAL, slug="a")
        write_frame(tmp_path, MINIMAL, slug="b")
        assert list_frames("testfirm", "TestDeal", root=tmp_path) == ["a", "b"]


# --- Prompt blocks -----------------------------------------------------------

class TestPromptBlocks:
    """The no-frame case is the contract. Everything else is additive."""

    def test_no_frame_yields_empty_blocks(self):
        assert research_block(None, "01-executive-summary.md") == ""
        assert writer_block(None, "01-executive-summary.md") == ""
        assert evidence_paths(None) == []

    def test_inert_section_yields_empty_blocks(self):
        f = parse_frame(MINIMAL)
        assert research_block(f, "09-funding-terms.md") == ""
        assert writer_block(f, "09-funding-terms.md") == ""

    def test_section_absent_from_frame_yields_empty_blocks(self):
        f = parse_frame(MINIMAL)
        assert research_block(f, "06-opportunity.md") == ""
        assert writer_block(f, "06-opportunity.md") == ""

    def test_research_block_states_additivity(self):
        f = parse_frame(MINIMAL)
        block = research_block(f, "01-executive-summary.md")
        assert "ADDITIVE" in block
        assert "not regathering" in block or "not being replaced" in block

    def test_refresh_asks_for_contradictions_not_just_additions(self):
        f = parse_frame({**MINIMAL, "affects": {"03-opening.md": {"research": "refresh", "prose": "rewrite"}}})
        block = research_block(f, "03-opening.md")
        assert "REFRESHED" in block and "contradicts" in block

    def test_caveats_reach_both_blocks(self):
        """A qualification that reaches only the prose can be stripped by the next
        assembly; one that reaches research is durable."""
        caveat = "Phases 1-2 are proposed and under executive review."
        f = parse_frame({**MINIMAL, "caveats": [caveat]})
        assert caveat in research_block(f, "01-executive-summary.md")
        assert caveat in writer_block(f, "01-executive-summary.md")

    def test_frame_questions_are_additive_to_outline_questions(self):
        f = parse_frame({**MINIMAL, "questions": {"01-executive-summary.md": ["How large is the block?"]}})
        block = research_block(f, "01-executive-summary.md")
        assert "How large is the block?" in block
        assert "IN ADDITION TO" in block
        assert "never instead of them" in block

    def test_writer_block_carries_the_directive(self):
        f = parse_frame({**MINIMAL, "affects": {"05-offering.md": {"research": "extend", "prose": "amend"}}})
        block = writer_block(f, "05-offering.md")
        assert "amend" in block
        assert "MINIMUM change" in block

    def test_re_sequencing_stance_forbids_calling_it_a_pivot(self):
        f = parse_frame(MINIMAL)
        assert "not a pivot" in writer_block(f, "01-executive-summary.md")

    def test_replacement_stance_omits_the_re_sequencing_note(self):
        f = parse_frame({**MINIMAL, "stance": "replacement"})
        assert "not a pivot" not in writer_block(f, "01-executive-summary.md")

    def test_directive_notes_reach_the_writer(self):
        f = parse_frame({**MINIMAL,
                         "affects": {"05-offering.md": "amend"},
                         "directive_notes": {"05-offering.md": "Keep the clinician prose."}})
        assert "Keep the clinician prose." in writer_block(f, "05-offering.md")


# --- The shipped ProfileHealth frame ----------------------------------------

class TestProfileHealthFrame:
    """The first real frame. Guards the properties the memo depends on."""

    @pytest.fixture
    def frame(self):
        path = Path("io/humain/deals/ProfileHealth/frames/ltc-carrier-b2b2c.yaml")
        if not path.exists():
            pytest.skip("ProfileHealth frame not present (private submodule)")
        return load_frame("ltc-carrier-b2b2c", firm="humain", deal="ProfileHealth")

    def test_validates_against_the_real_outline(self, frame):
        outline_path = Path("templates/outlines/direct-early-stage-12Ps.yaml")
        if not outline_path.exists():
            pytest.skip("outline not present")
        sections = [s["filename"] for s in yaml.safe_load(outline_path.read_text())["sections"]]
        validate_against_outline(frame, sections)

    def test_funding_terms_prose_is_protected(self, frame):
        """Section 9 carries a hand-written per-instrument SAFE transcription.
        `prose: unchanged` is the only thing standing between it and the writer."""
        d = frame.directive_for("09-funding-terms.md")
        assert d.prose == "unchanged"
        assert d.is_inert

    def test_research_is_additive_everywhere_it_runs(self, frame):
        for name, d in frame.affects.items():
            assert d.research in ("extend", "reuse", "refresh"), name
            if d.research == "reuse":
                continue
            assert d.research == "extend", f"{name} regathers rather than extends"

    def test_proposed_revenue_caveat_is_present(self, frame):
        joined = " ".join(frame.caveats).lower()
        assert "proposed" in joined and "not contracted" in joined

    def test_stance_is_re_sequencing(self, frame):
        assert frame.stance == "re-sequencing"

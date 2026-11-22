"""Appended research blocks must not reuse footnote keys (CONN-HEX-04 to CONN-HEX-08).

When a run reuses a prior version's research and appends new sources under
`## Added from N new sources`, the appended block used to number its footnotes
from 1 again, so one research file defined [^1] twice for two sources and
assembly (last definition wins) linked the reused block's footnotes to the
appended block's sources. See
context-v/issues/Appended-Research-Blocks-Reuse-Footnote-Keys.md.

Every fixture here is synthetic.
"""

from __future__ import annotations

import re

import pytest

from src.agents.citation_assembly import assemble_citations, extract_citation_definitions
from src.citation_keys import source_key
from src.citation_repair import definitions_with_duplicates, prose, repair_memo, scan
from src.final_draft import get_final_draft_path
from src.research_append import append_augmentation, write_or_append_research

SITE = "https://example.com/company-site"
NEWS = "https://example.net/news-story"
DECK = "https://example.org/pitch-deck"
REVIEW = "https://example.edu/literature-review"

DEF_SITE = f"2026, Nov 01. [Company site]({SITE}). Company."
DEF_NEWS = f"2026, Nov 02. [News story]({NEWS}). Newsroom."
DEF_DECK = f"2026, Nov 03. [Pitch deck]({DECK}). Company."
DEF_REVIEW = f"2026, Nov 04. [Literature review]({REVIEW}). Journal."

PRIOR = (
    "# Overview research\n\nWebsite fact.[^1] News fact.[^2]\n\n"
    f"### Citations\n\n[^1]: {DEF_SITE}\n\n[^2]: {DEF_NEWS}\n"
)
NEW = (
    "# New research\n\nDeck fact.[^1] Review fact.[^2]\n\n"
    f"### Citations\n\n[^1]: {DEF_DECK}\n\n[^2]: {DEF_REVIEW}\n"
)
KEY = r"[a-zA-Z0-9_-]+"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _legacy_research(block_one: str, block_two: str) -> str:
    """A research file as the old append wrote it: both blocks numbered from 1."""
    return (
        f"# Research\n\nOld findings.\n\n### Citations\n\n{block_one}\n\n***\n\n"
        "<!-- research-block: frame=augment run=Company-v0.0.2 appended=2026-11-01 -->\n\n"
        f"## Added from 2 new sources\n\n### New research\n\nNew findings.\n\n### Citations\n\n{block_two}\n"
    )


OVERVIEW_RESEARCH = _legacy_research(
    f"[^1]: {DEF_SITE}\n\n[^2]: {DEF_NEWS}", f"[^1]: {DEF_DECK}\n\n[^2]: {DEF_REVIEW}"
)
TEAM_RESEARCH = _legacy_research(
    f"[^1]: {DEF_SITE}\n\n[^3]: {DEF_NEWS}", f"[^1]: {DEF_DECK}\n\n[^2]: {DEF_REVIEW}"
)

# Two parts: the reused text, then a part drafted from the appended block.
OVERVIEW_SECTION = (
    "## Overview\n\nWebsite says A.[^1] News says B.[^2]\n\n"
    "### Added from 2 new sources\n\nDeck says C.[^1] Review says D.[^2]\n"
)
# One part, redrafted from the combined file: [^3] is only in block one, [^2]
# only in block two, and [^1] means a different source in each.
TEAM_SECTION = "## Team\n\nBio one.[^3] Bio two.[^2] Bio three.[^1]\n"


def _legacy_version(tmp_path, *, overview_memo_line="Website says A.[^1] News says B.[^2]"):
    vd = tmp_path / "io" / "firm" / "deals" / "Company" / "outputs" / "Company-v0.0.2"
    _write(vd / "1-research" / "01-overview-research.md", OVERVIEW_RESEARCH)
    _write(vd / "1-research" / "02-team-research.md", TEAM_RESEARCH)
    _write(vd / "2-sections" / "01-overview.md", OVERVIEW_SECTION)
    _write(vd / "2-sections" / "02-team.md", TEAM_SECTION)
    # What the last-definition-wins assembler wrote: every [^1] is the deck,
    # every [^2] the review.
    _write(
        vd / "7-Company-v0.0.2.md",
        "# Company Memo\n\n## Executive Summary\n\nSummary.[^3]\n\n"
        f"## Overview\n\n{overview_memo_line}\n\n"
        "### Added from 2 new sources\n\nDeck says C.[^1] Review says D.[^2]\n\n"
        "## Team\n\nBio one.[^3] Bio two.[^2] Bio three.[^1]\n\n"
        "***\n\n### Citations\n\n"
        f"[^1]: {DEF_DECK}\n\n[^2]: {DEF_REVIEW}\n\n[^3]: {DEF_NEWS}\n",
    )
    return vd


def _defs(text):
    return dict(re.findall(rf"^\[\^({KEY})\]: (.*)$", text, re.M))


def _key_after(text, claim):
    return re.search(re.escape(claim) + rf"\[\^({KEY})\]", text).group(1)


# ---------------------------------------------------------------- CONN-HEX-04


@pytest.mark.spec("CONN-HEX-04")
def test_augmentation_defines_each_key_once_and_keeps_the_reused_block(tmp_path):
    path = tmp_path / "01-overview-research.md"
    path.write_text(PRIOR)
    assert append_augmentation(path, NEW, run_version="v0.0.2", new_sources=2) == "appended"
    text = path.read_text()

    keys = [k for k, _ in definitions_with_duplicates(text)]
    assert len(keys) == len(set(keys)) == 4
    assert text.startswith(PRIOR.rstrip())  # the reused block is untouched
    defs = _defs(text)
    assert defs[source_key(DEF_DECK)] == DEF_DECK
    assert defs[source_key(DEF_REVIEW)] == DEF_REVIEW
    assert f"Deck fact.[^{source_key(DEF_DECK)}]" in text


@pytest.mark.spec("CONN-HEX-04")
def test_frame_extension_defines_each_key_once(tmp_path):
    class Directive:
        research = "extend"
        researches = True

    class Frame:
        slug = "angle"
        name = "Angle"

        def directive_for(self, _filename):
            return Directive()

    path = tmp_path / "06-opportunity-research.md"
    path.write_text(PRIOR)
    action = write_or_append_research(
        path, NEW, frame=Frame(), section_filename="06-opportunity.md", run_version="v0.0.2"
    )
    assert action == "appended"
    keys = [k for k, _ in definitions_with_duplicates(path.read_text())]
    assert len(keys) == len(set(keys)) == 4


@pytest.mark.spec("CONN-HEX-04")
def test_appended_source_already_in_the_reused_block_is_not_defined_twice(tmp_path):
    path = tmp_path / "01-overview-research.md"
    path.write_text(PRIOR)
    again = f"# New\n\nSite again.[^1] Deck.[^2]\n\n### Citations\n\n[^1]: {DEF_SITE}\n\n[^2]: {DEF_DECK}\n"
    append_augmentation(path, again, run_version="v0.0.2", new_sources=2)
    text = path.read_text()
    keys = [k for k, _ in definitions_with_duplicates(text)]
    assert len(keys) == len(set(keys))
    assert extract_citation_definitions(text)[_key_after(text, "Site again.")].startswith(DEF_SITE)


@pytest.mark.spec("CONN-HEX-04")
def test_section_citing_both_blocks_links_each_footnote_to_its_own_source(tmp_path):
    out = tmp_path / "Company-v0.0.2"
    research = out / "1-research" / "01-overview-research.md"
    _write(research, PRIOR)
    append_augmentation(research, NEW, run_version="v0.0.2", new_sources=2)
    deck_key = source_key(DEF_DECK)
    _write(
        out / "2-sections" / "01-overview.md",
        f"## Overview\n\nWebsite says A.[^1] Deck says C.[^{deck_key}]\n",
    )

    assemble_citations(out, state={})
    final = get_final_draft_path(out).read_text()
    defs = extract_citation_definitions(final)
    assert SITE in defs[_key_after(final, "Website says A.")]
    assert DECK in defs[_key_after(final, "Deck says C.")]


# ---------------------------------------------------------------- CONN-HEX-05


def _assemble_legacy(tmp_path):
    vd = _legacy_version(tmp_path)
    (vd / "7-Company-v0.0.2.md").unlink()
    result = assemble_citations(vd, state={})
    return vd, result, get_final_draft_path(vd).read_text()


@pytest.mark.spec("CONN-HEX-05")
def test_assembly_resolves_each_part_against_its_own_block(tmp_path):
    _, _, final = _assemble_legacy(tmp_path)
    defs = extract_citation_definitions(final)
    assert SITE in defs[_key_after(final, "Website says A.")]
    assert NEWS in defs[_key_after(final, "News says B.")]
    assert DECK in defs[_key_after(final, "Deck says C.")]
    assert REVIEW in defs[_key_after(final, "Review says D.")]


@pytest.mark.spec("CONN-HEX-05")
def test_assembly_refuses_only_the_conflicting_key_in_a_one_part_section(tmp_path):
    vd, result, final = _assemble_legacy(tmp_path)
    defs = extract_citation_definitions(final)
    assert NEWS in defs[_key_after(final, "Bio one.")]
    assert REVIEW in defs[_key_after(final, "Bio two.")]
    # [^1] means the site in one block and the deck in the other: left
    # unlinked and reported, never silently given the last block's source.
    assert _key_after(final, "Bio three.") not in defs
    refused = result["citation_assembly"]["refused_keys"]
    assert any("02-team" in r and "[^1]" in r for r in refused)
    assert not any("01-overview" in r for r in refused)
    # Section files on disk keep their keys; disambiguation is in memory.
    assert (vd / "2-sections" / "02-team.md").read_text() == TEAM_SECTION


# ---------------------------------------------------------------- CONN-HEX-06


@pytest.mark.spec("CONN-HEX-06")
def test_repair_matches_each_section_part_to_its_research_block(tmp_path):
    result = repair_memo(_legacy_version(tmp_path))
    text = result.text
    defs = _defs(text)

    assert defs[_key_after(text, "Website says A.")] == DEF_SITE
    assert defs[_key_after(text, "News says B.")] == DEF_NEWS
    assert defs[_key_after(text, "Deck says C.")] == DEF_DECK
    assert defs[_key_after(text, "Review says D.")] == DEF_REVIEW
    overview = next(r for r in result.report["regions"] if r["section"] == "01-overview")
    assert overview["status"] == "repaired"
    assert prose(text) == prose(result.original)


@pytest.mark.spec("CONN-HEX-06")
def test_repair_refuses_only_conflicting_keys_in_a_one_part_section(tmp_path):
    result = repair_memo(_legacy_version(tmp_path))
    text = result.text
    defs = _defs(text)

    assert defs[_key_after(text, "Bio one.")] == DEF_NEWS
    assert defs[_key_after(text, "Bio two.")] == DEF_REVIEW
    # The refused marker keeps its key and the definition it had.
    assert _key_after(text, "Bio three.") == "1"
    assert defs["1"] == DEF_DECK
    team = next(r for r in result.report["regions"] if r["section"] == "02-team")
    assert team["status"] == "partial"
    assert team["repaired"] == 2
    assert sum(team["refused"].values()) == 1
    assert any("differently" in reason for reason in team["refused"])
    assert result.report["counts"]["repaired"] >= 6
    assert prose(text) == prose(result.original)


# ---------------------------------------------------------------- CONN-HEX-07


EDITED_LINE = "Website says A, reworded.[^1] News says B.[^2] A claim added later.[^1]"


@pytest.mark.spec("CONN-HEX-07")
def test_repair_pairs_markers_only_on_lines_identical_to_the_section_file(tmp_path):
    # A marker added after assembly breaks the region's one-for-one pairing,
    # so markers are paired line by line, and only on unedited lines.
    result = repair_memo(_legacy_version(tmp_path, overview_memo_line=EDITED_LINE))
    text = result.text
    defs = _defs(text)

    # The edited line keeps its markers as they were.
    assert EDITED_LINE in text
    # The untouched lines of the same region are still repaired.
    assert defs[_key_after(text, "Deck says C.")] == DEF_DECK
    assert defs[_key_after(text, "Review says D.")] == DEF_REVIEW
    overview = next(r for r in result.report["regions"] if r["section"] == "01-overview")
    assert overview["status"] == "partial"
    assert overview["repaired"] == 2
    assert overview["refused"] == {"line edited after assembly": 3}
    assert prose(text) == prose(result.original)


@pytest.mark.spec("CONN-HEX-07")
def test_repair_still_pairs_a_whole_region_whose_markers_pair_one_for_one(tmp_path):
    # Reworded prose with every marker where it was: the region still pairs
    # one for one with the section file, as it did before line pairing.
    vd = _legacy_version(tmp_path, overview_memo_line="Website reworded.[^1] News says B.[^2]")
    result = repair_memo(vd)
    overview = next(r for r in result.report["regions"] if r["section"] == "01-overview")
    assert overview["status"] == "repaired"
    assert _defs(result.text)[_key_after(result.text, "Website reworded.")] == DEF_SITE


# ---------------------------------------------------------------- CONN-HEX-08


@pytest.mark.spec("CONN-HEX-08")
def test_scan_reports_appended_blocks_apart_from_collapsed_keys(tmp_path, capsys):
    vd = _legacy_version(tmp_path)
    collapsed = tmp_path / "io" / "firm" / "deals" / "Other" / "outputs" / "Other-v0.0.1"
    _write(
        collapsed / "1-research" / "01-overview-research.md",
        f"# R\n\n[^1]: {DEF_SITE}\n[^1]: {DEF_NEWS}\n",
    )
    _write(collapsed / "2-sections" / "01-overview.md", "## Overview\n\nClaim.[^1]\n")
    _write(
        collapsed / "7-Other-v0.0.1.md",
        f"# Memo\n\n## Overview\n\nClaim.[^1]\n\n[^1]: {DEF_NEWS}\n",
    )

    rows = {row.memo.parent: row for row in scan(tmp_path / "io")}
    assert rows[vd].appended == ["01-overview-research.md", "02-team-research.md"]
    assert rows[vd].collapsed == []
    assert rows[collapsed].collapsed == ["01-overview-research.md"]
    assert rows[collapsed].appended == []

    from cli.repair_citations import main

    assert main(["--scan", str(tmp_path / "io")]) == 0
    out = capsys.readouterr().out
    assert "appended blocks" in out and "collapsed keys" in out

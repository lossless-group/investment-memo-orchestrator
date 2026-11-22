"""Hex citation keys in the local pipeline and the exports.

See context-v/plans/Hex-Code-Citations-and-a-Repair-Tool.md, Part 2. The
connector side is CONN-HEX-01..03 in tests/connector/test_hex_citations.py.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agents.citation_assembly import assemble_citations, extract_citation_definitions
from src.agents.codified_section_researcher import _synthesize_raw
from src.citation_keys import source_key
from src.curation.sources_md import SourceEntry
from src.final_draft import get_final_draft_path

REPO = Path(__file__).resolve().parents[1]
SURVEY = "https://example.org/survey"
CENSUS = "https://example.org/census"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_raw_codified_research_keys_each_source_by_its_url(tmp_path):
    section = SimpleNamespace(name="Market", filename="02-market.md")
    matching = [SourceEntry(url=SURVEY), SourceEntry(url=CENSUS)]
    fetched = {SURVEY: {"title": "Survey", "markdown": "Survey text."}, CENSUS: {"title": "Census"}}
    _synthesize_raw(tmp_path, 2, section, matching, fetched, {})

    research = (tmp_path / "02-market-research.md").read_text()
    definitions = extract_citation_definitions(research)
    assert set(definitions) == {source_key(f"({SURVEY})"), source_key(f"({CENSUS})")}
    assert f"## Source [^{source_key(SURVEY)}]: Survey" in research
    assert not re.search(r"\[\^\d\]", research)


def test_assembly_keeps_hex_research_and_converts_numbered_sections(tmp_path):
    out = tmp_path / "Co-v0.0.1"
    survey = f"2026, Nov 01. [Survey]({SURVEY}). A."
    census = f"2026, Nov 02. [Census]({CENSUS}). B."
    hex_survey, hex_census = source_key(survey), source_key(census)
    # New run: research and section both use hex keys.
    _write(out / "1-research" / "01-a-research.md", f"A fact. [^{hex_survey}]\n\n[^{hex_survey}]: {survey}\n")
    _write(out / "2-sections" / "01-a.md", f"## A\n\nThe a claim. [^{hex_survey}]\n")
    # Old run: numbered keys, the survey under a different local number.
    _write(
        out / "1-research" / "02-b-research.md",
        f"B facts. [^1] [^2]\n\n[^1]: {census}\n\n[^2]: {survey}\n",
    )
    _write(out / "2-sections" / "02-b.md", "## B\n\nThe census claim. [^1] The survey claim. [^2]\n")

    result = assemble_citations(out, state={})
    final = get_final_draft_path(out).read_text()
    definitions = extract_citation_definitions(final)

    assert list(definitions) == [hex_survey, hex_census], "one key per source, first-cited order"
    assert f"The a claim. [^{hex_survey}]" in final
    assert f"The census claim. [^{hex_census}]" in final
    assert f"The survey claim. [^{hex_survey}]" in final
    assert result["citation_assembly"]["research_mismatches"] == []


def test_restore_uncited_footnotes_reads_hex_definitions():
    sys.path.insert(0, str(REPO / "cli" / "utils"))
    try:
        from restore_uncited_footnotes import add_uncited_footnotes
    finally:
        sys.path.pop(0)
    md = "A claim. [^3vdxyl]\n\n[^3vdxyl]: [Cited](https://a.example)\n\n[^9zz0ab]: [Background](https://b.example)\n"
    html = (
        '<p>A claim.<a href="#fn1" class="footnote-ref" id="fnref1"><sup>1</sup></a></p>'
        '<section id="footnotes" class="footnotes"><hr /><ol>\n'
        '<li id="fn1"><p>Cited</p></li>\n</ol></section>'
    )
    out = add_uncited_footnotes(html, md)
    assert '<li id="fn2"><p><a href="https://b.example">Background</a></p></li>' in out
    assert out.count("<li id=") == 2


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")
def test_pandoc_numbers_hex_footnotes_in_first_cited_order():
    md = (
        "First. [^zz9abc]\n\nSecond. [^3vdxyl]\n\n"
        "[^3vdxyl]: Defined first, cited second.\n\n[^zz9abc]: Defined second, cited first.\n"
    )
    html = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "html"], input=md, capture_output=True, text=True, check=True
    ).stdout
    notes = re.findall(r'<li id="fn(\d+)"><p>([^<]+)', html)
    assert notes == [("1", "Defined second, cited first."), ("2", "Defined first, cited second.")]

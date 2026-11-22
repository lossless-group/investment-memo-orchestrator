"""Citation keys are local to each section in final assembly.

Each section's research file numbers its sources from 1, so two sections can
both cite [^25] for different sources. See
context-v/issues/Final-Draft-Citations-Collide-Across-Sections.md.
"""
import re

from src.agents.citation_assembly import assemble_citations, extract_citation_definitions
from src.final_draft import get_final_draft_path

OVERVIEW_URL = "https://example.com/overview-source"
FLAGS_URL = "https://example.org/flags-source"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _memo(tmp_path, *, flags_research=True):
    out = tmp_path / "Company-v0.0.1"
    _write(
        out / "1-research" / "01-overview-research.md",
        "# Overview research\n\nOverview fact.[^25]\n\n"
        f"[^25]: 2026, Nov 01. [Overview source]({OVERVIEW_URL}). Publisher A.\n",
    )
    if flags_research:
        _write(
            out / "1-research" / "02-flags-research.md",
            "# Flags research\n\nFlags fact.[^25]\n\n"
            f"[^25]: 2026, Nov 02. [Flags source]({FLAGS_URL}). Publisher B.\n",
        )
    _write(out / "2-sections" / "01-overview.md", "## Overview\n\nThe overview claim.[^25]\n")
    _write(out / "2-sections" / "02-flags.md", "## Flags\n\nThe flags claim.[^25]\n")
    return out


def _url_cited_by(final, claim):
    number = re.search(re.escape(claim) + r"\[\^(\w+)\]", final).group(1)
    return extract_citation_definitions(final)[number]


def test_each_section_links_to_its_own_research_source(tmp_path):
    out = _memo(tmp_path)
    assemble_citations(out, state={})
    final = get_final_draft_path(out).read_text()

    assert OVERVIEW_URL in _url_cited_by(final, "The overview claim.")
    assert FLAGS_URL in _url_cited_by(final, "The flags claim.")
    assert len(extract_citation_definitions(final)) == 2


def test_guard_warns_when_a_definition_is_not_in_the_sections_research(tmp_path, capsys):
    out = _memo(tmp_path)
    # The flags section carries its own definition for [^25], pointing at the
    # overview's source, which the flags research never cited.
    _write(
        out / "2-sections" / "02-flags.md",
        "## Flags\n\nThe flags claim.[^25]\n\n"
        f"[^25]: [Overview source]({OVERVIEW_URL}). Publisher A.\n",
    )
    result = assemble_citations(out, state={})
    warnings = result["citation_assembly"]["research_mismatches"]
    assert len(warnings) == 1
    assert "02-flags.md" in warnings[0] and "[^25]" in warnings[0]
    assert "02-flags.md" in capsys.readouterr().out


def test_guard_is_quiet_when_every_definition_matches(tmp_path):
    out = _memo(tmp_path)
    result = assemble_citations(out, state={})
    assert result["citation_assembly"]["research_mismatches"] == []


def test_section_without_research_file_uses_an_unambiguous_definition(tmp_path):
    out = _memo(tmp_path, flags_research=False)
    assemble_citations(out, state={})
    final = get_final_draft_path(out).read_text()
    # Only one research file defines [^25], so the fallback is unambiguous.
    assert OVERVIEW_URL in _url_cited_by(final, "The flags claim.")


def test_section_without_research_file_leaves_an_ambiguous_key_undefined(tmp_path):
    out = _memo(tmp_path)
    _write(out / "2-sections" / "03-extra.md", "## Extra\n\nThe extra claim.[^25]\n")
    result = assemble_citations(out, state={})
    final = get_final_draft_path(out).read_text()
    number = re.search(r"The extra claim\.\[\^(\w+)\]", final).group(1)
    assert number not in extract_citation_definitions(final)
    assert result["citation_assembly"]["missing_definitions"] == 1

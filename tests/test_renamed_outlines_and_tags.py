"""Regressions from the first TerraFirma run (2026-10-06).

Four defects, each silent until a deal hit it:
  - the default outlines were renamed but the loader still named the old files
  - aggregator tags for '&' sections never matched the section name
  - a prose `key_hires` string was searched on LinkedIn a letter at a time
  - the httpx fallback dropped every PDF source
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from src import outline_loader
from src.curation.fetch import _fetch_via_httpx
from src.curation.sources_md import SourceEntry, SourcesMd, _normalize_tag, sources_for_section


@pytest.fixture(autouse=True)
def _clear_outline_cache():
    outline_loader._outline_cache.clear()
    yield
    outline_loader._outline_cache.clear()


@pytest.mark.parametrize("investment_type", ["direct", "fund"])
def test_default_outline_files_exist(investment_type):
    outline = outline_loader.load_outline(investment_type)
    assert outline.sections


@pytest.mark.parametrize("old,new", sorted(outline_loader.RENAMED_OUTLINES.items()))
def test_pre_rename_outline_names_still_resolve(old, new):
    assert (outline_loader.get_templates_dir() / f"{new}.yaml").exists()
    outline = outline_loader.load_custom_outline(old, "direct")
    assert outline.sections


@pytest.mark.parametrize("tag", ["technology--product", "Technology & Product", "technology_and_product"])
def test_ampersand_section_tags_normalize_together(tag):
    assert _normalize_tag(tag) == "technology-product"


def test_aggregator_tag_matches_ampersand_section():
    sm = SourcesMd(
        mode="codified", deal="d", firm="f",
        sources=[SourceEntry(url="https://a.example/x", sections=["risks--mitigations"])],
        body="", raw_frontmatter={}, source_path=Path("Sources.md"),
    )
    assert len(sources_for_section(sm, "Risks & Mitigations")) == 1
    assert sources_for_section(sm, "Team") == []


def test_key_hires_string_is_not_split_into_letters():
    from src.agents import socials_enrichment

    state = {
        "company_name": "Acme",
        "research": {"company": {}, "team": {"founders": [], "key_hires": "Seasoned leaders"}},
    }
    with patch.object(socials_enrichment, "find_company_social_profiles", return_value={}), \
         patch.object(socials_enrichment, "find_team_linkedin_profiles") as find_team, \
         patch("src.utils.get_output_dir_from_state", side_effect=FileNotFoundError):
        socials_enrichment.socials_enrichment_agent(state)
    find_team.assert_not_called()


def test_httpx_fallback_reads_pdf():
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Operators are hard to hire.")
    pdf_bytes = doc.tobytes()

    response = MagicMock(status_code=200, content=pdf_bytes, headers={"content-type": "application/pdf"})
    with patch("src.curation.fetch.httpx.get", return_value=response):
        result = _fetch_via_httpx("https://a.example/survey.pdf")

    assert result and "Operators are hard to hire." in result["markdown"]
    assert result["via"] == "httpx-pdf"

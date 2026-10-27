"""Section breaks are `***`; `---` survives only as the opening frontmatter delimiter."""

from src.md_breaks import BREAK_LINE_RE, normalize_section_breaks
from src.research_append import append_augmentation


def test_paragraph_above_dash_rule_cannot_become_a_heading():
    text = "Humain Fund I invested $200,000.\n---\n\n## Next"
    out = normalize_section_breaks(text)
    assert out == "Humain Fund I invested $200,000.\n\n***\n\n## Next"


def test_frontmatter_is_left_alone():
    text = "---\ntitle: x\n---\n\nBody\n\n---\n\nMore"
    out = normalize_section_breaks(text)
    assert out.startswith("---\ntitle: x\n---\n")
    assert out.endswith("Body\n\n***\n\nMore")


def test_code_fences_and_tables_are_left_alone():
    text = "```yaml\n---\nkey: v\n---\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    assert normalize_section_breaks(text) == text


def test_existing_star_breaks_are_kept():
    text = "Para\n\n***\n\nPara"
    assert normalize_section_breaks(text) == text


def test_reader_regex_accepts_both_spellings():
    assert BREAK_LINE_RE.match("---") and BREAK_LINE_RE.match("***")
    assert not BREAK_LINE_RE.match("|---|---|")


def test_augmentation_writes_star_break(tmp_path):
    path = tmp_path / "01-overview.md"
    path.write_text("# Overview\n\nPrior findings.\n")
    assert append_augmentation(path, "# New\n\nMore.\n---\nTail", run_version="v0.0.2", new_sources=3) == "appended"
    text = path.read_text()
    assert "\n---" not in text
    assert "Prior findings.\n\n***\n\n<!-- research-block:" in text

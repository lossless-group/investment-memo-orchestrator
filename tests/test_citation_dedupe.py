"""One definition per source in an assembled memo.

See context-v/issues/Dataroom-Citations-Duplicate-In-Consolidated-Block.md.
"""
import re

from src.citation_keys import source_key
from src.agents.citation_assembly import (
    consolidate_citations,
    extract_citation_definitions,
    merge_duplicate_definitions,
)

PROFORMA = "file:///deal/inputs/20261109_cap%20table%20proforma%20v2.xlsx"


def test_file_links_with_different_publisher_text_share_one_key():
    a = f"Pro forma claim.[^3]\n\n[^3]: 2026, Nov 09. [Pro forma]({PROFORMA}). New Silicon Corporation.\n"
    b = f"Same doc.[^7]\n\n[^7]: 2026, Nov 09. [Pro forma]({PROFORMA}). Company-prepared spreadsheet.\n"
    bodies, block, stats = consolidate_citations([a, b])
    assert stats["sources"] == 1
    # One key per source: the source's hex key, in both sections and the block.
    key = source_key(f"[Pro forma]({PROFORMA})")
    assert bodies[0].strip().endswith(f"[^{key}]") and bodies[1].strip().endswith(f"[^{key}]")
    assert list(extract_citation_definitions(block)) == [key]


def test_encoded_and_decoded_links_match():
    a = "X.[^1]\n\n[^1]: [Doc](https://example.org/%7Euser/report/)\n"
    b = "Y.[^1]\n\n[^1]: [Doc](https://example.org/~user/report)\n"
    _, _, stats = consolidate_citations([a, b])
    assert stats["sources"] == 1


def test_merge_duplicate_definitions_in_assembled_memo():
    memo = (
        "# Memo\n\nFirst.[^1] Second.[^2] Third.[^3] Again.[^2]\n\n"
        "### Citations\n\n"
        f"[^1]: [Deck](file:///deal/deck.pdf). NSC.\n\n"
        f"[^2]: [Pro forma]({PROFORMA}). NSC.\n\n"
        f"[^3]: [Pro forma]({PROFORMA}). Company spreadsheet.\n\n"
        "## Background Sources\n\n- something\n"
    )
    out, merged = merge_duplicate_definitions(memo)
    assert merged == 1
    definitions = extract_citation_definitions(out)
    assert sorted(definitions) == ["1", "2"]
    assert "Third.[^2]" in out and "Again.[^2]" in out
    assert out.index("### Citations") < out.index("[^1]: [Deck]") < out.index("## Background Sources")


def test_merge_is_a_no_op_without_duplicates():
    memo = "A.[^1] B.[^2]\n\n[^1]: [One](https://a.example)\n\n[^2]: [Two](https://b.example)\n"
    out, merged = merge_duplicate_definitions(memo)
    assert merged == 0
    assert re.findall(r"\[\^(\d+)\]:", out) == ["1", "2"]

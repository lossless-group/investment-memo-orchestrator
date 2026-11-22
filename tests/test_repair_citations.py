"""The citation repair tool and the hex keys it writes.

Memos assembled before the fix in
context-v/issues/Final-Draft-Citations-Collide-Across-Sections.md link most
citations to another section's source, because each section's research numbers
its sources from 1 and the old assembler treated keys as global. The repair
re-derives each section's markers from its own research file, writes hex keys
from source_key() (LFM rule 2), and refuses any region it cannot prove.

Every fixture here is synthetic. See
context-v/plans/Hex-Code-Citations-and-a-Repair-Tool.md, Part 1.
"""

import json
import re

import pytest

from src import citation_keys
from src.citation_keys import assign_keys, source_key
from src import citation_repair
from src.citation_repair import find_memo, prose, repair_memo, scan

URL_A = "https://example.com/a-source"
URL_B = "https://example.org/b-source"
URL_C = "https://example.net/c-source"

DEF_A = f"2026, Nov 01. [Source A]({URL_A}). Publisher A."
DEF_B = f"2026, Nov 02. [Source B]({URL_B}). Publisher B."
DEF_C = f"2026, Nov 03. [Source C]({URL_C}). Publisher C."

KEY_RE = r"[a-zA-Z0-9_-]+"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _memo_text(flags_body="Flag one.[^1] Flag two.[^2]"):
    # What the pre-fix assembler wrote: one global numbering, so the flags
    # section's [^1] and [^2] link to the overview's sources.
    return (
        "# Company Memo\n\n"
        "## Executive Summary\n\nSummary claim.[^1]\n\n"
        "## Overview\n\nClaim one.[^1] Claim two.[^2]\n\n"
        f"## Flags\n\n{flags_body}\n\n"
        "## Closing Assessment\n\nClosing claim.[^2]\n\n"
        "***\n\n### Citations\n\n"
        f"[^1]: {DEF_A}\n\n"
        f"[^2]: {DEF_B}\n"
    )


def _version(tmp_path, *, flags_research=None, flags_body=None, name="Company-v0.0.1"):
    vd = tmp_path / "io" / "firm" / "deals" / "Company" / "outputs" / name
    _write(vd / "1-research" / "01-overview-research.md", f"# Overview research\n\n[^1]: {DEF_A}\n[^2]: {DEF_B}\n")
    _write(
        vd / "1-research" / "02-flags-research.md",
        flags_research or f"# Flags research\n\n[^1]: {DEF_C}\n[^2]: {DEF_A}\n",
    )
    _write(vd / "2-sections" / "01-overview.md", "## Overview\n\nClaim one.[^1] Claim two.[^2]\n")
    _write(vd / "2-sections" / "02-flags.md", "## Flags\n\nFlag one.[^1] Flag two.[^2]\n")
    kwargs = {"flags_body": flags_body} if flags_body else {}
    _write(vd / f"7-{name}.md", _memo_text(**kwargs))
    return vd


def _defs(text):
    return dict(re.findall(rf"^\[\^({KEY_RE})\]: (.*)$", text, re.M))


def _key_after(text, claim):
    return re.search(re.escape(claim) + rf"\[\^({KEY_RE})\]", text).group(1)


def _region(text, heading, next_heading):
    return text[text.index(heading) : text.index(next_heading)]


# ------------------------------------------------------------- source_key


def test_source_key_is_six_base36_characters_and_stable():
    key = source_key(DEF_A)
    assert re.fullmatch(r"[0-9a-z]{6}", key)
    assert source_key(DEF_A) == key
    # Same link, different date, title and publisher: same source, same key.
    assert source_key(f"2025-01-01. [Another title]({URL_A}). Someone else.") == key
    # The link is percent-decoded, lowercased, and loses its trailing slash.
    assert source_key("2026. [x](https://Example.com/a%2Dsource/)") == key
    assert source_key(DEF_B) != key


def test_source_key_without_a_link_uses_the_text_without_its_date():
    one = source_key("2026, Nov 01. Interview with the founder,   on pricing.")
    two = source_key("2025, Mar 04. interview with the founder, on pricing.")
    assert one == two
    assert re.fullmatch(r"[0-9a-z]{6}", one)


def test_deck_and_dataroom_keys_are_plain_keys():
    # Decided for both branches (plan, 748ace9): no deck- or dr- prefixes.
    deck = source_key("2025. [Company Pitch Deck](internal-document). Company Materials.")
    dataroom = source_key("2025. [Cap table](file:///deals/acme/dataroom/cap-table.xlsx). Dataroom.")
    assert re.fullmatch(r"[0-9a-z]{6}", deck)
    assert re.fullmatch(r"[0-9a-z]{6}", dataroom)


def test_assign_keys_gives_one_key_per_source():
    keys = assign_keys({"1": DEF_A, "2": DEF_B, "x": f"2024. [Again]({URL_A}/)."})
    assert keys["1"] == keys["x"] == source_key(DEF_A)
    assert keys["2"] == source_key(DEF_B)


def test_assign_keys_widens_both_keys_to_eight_on_a_collision(monkeypatch):
    real = citation_keys._key

    def forced(identity, length=citation_keys.SHORT):
        # A and B share their first six characters; C does not.
        if identity in (URL_A, URL_B):
            return ("abcdef" + ("11" if identity == URL_A else "22") + "zzzz")[:length]
        return real(identity, length)

    monkeypatch.setattr(citation_keys, "_key", forced)
    keys = assign_keys({"1": DEF_A, "2": DEF_B, "3": DEF_C})
    assert keys["1"] == "abcdef11"
    assert keys["2"] == "abcdef22"
    assert len(keys["3"]) == 6


# ------------------------------------------------------------- repair


def test_collided_memo_is_repaired_to_hex_with_prose_unchanged(tmp_path):
    vd = _version(tmp_path)
    result = repair_memo(vd)
    text = result.text

    assert result.changed
    statuses = {r["section"]: r["status"] for r in result.report["regions"]}
    assert statuses == {"01-overview": "repaired", "02-flags": "repaired"}

    defs = _defs(text)
    assert defs[_key_after(text, "Claim one.")] == DEF_A
    assert defs[_key_after(text, "Claim two.")] == DEF_B
    assert defs[_key_after(text, "Flag one.")] == DEF_C  # was linked to A
    assert URL_A in defs[_key_after(text, "Flag two.")]  # was linked to B
    # Hex keys only, one definition per source, in first-cited order.
    assert list(defs) == [source_key(DEF_A), source_key(DEF_B), source_key(DEF_C)]
    assert prose(text) == prose(result.original)
    assert "***\n\n### Citations" in text


def test_collapsed_key_region_is_refused_and_left_byte_identical(tmp_path):
    # The older bug: the research file defines one key several times, so a
    # local key no longer names one source.
    vd = _version(tmp_path, flags_research=f"# Flags research\n\n[^1]: {DEF_C}\n[^1]: {DEF_A}\n[^2]: {DEF_B}\n")
    result = repair_memo(vd)
    flags = next(r for r in result.report["regions"] if r["section"] == "02-flags")

    assert flags["status"] == "unrepairable"
    assert "more than once" in flags["reason"]
    assert _region(result.text, "## Flags", "## Closing") == _region(result.original, "## Flags", "## Closing")
    # The kept numeric keys still resolve.
    defs = _defs(result.text)
    assert defs["1"] == DEF_A and defs["2"] == DEF_B
    # The overview was still repaired.
    assert _key_after(result.text, "Claim one.") == source_key(DEF_A)


def test_region_edited_after_assembly_is_refused(tmp_path):
    vd = _version(tmp_path, flags_body="Flag one.[^1] Flag two.[^2] A sentence added later.[^1]")
    result = repair_memo(vd)
    flags = next(r for r in result.report["regions"] if r["section"] == "02-flags")

    assert flags["status"] == "unrepairable"
    assert "marker count" in flags["reason"]
    assert _region(result.text, "## Flags", "## Closing") == _region(result.original, "## Flags", "## Closing")


def test_executive_summary_keeps_its_source_in_hex_and_is_reported_unverified(tmp_path):
    vd = _version(tmp_path)
    result = repair_memo(vd)
    defs = _defs(result.text)

    assert _key_after(result.text, "Summary claim.") == source_key(DEF_A)
    assert defs[_key_after(result.text, "Closing claim.")] == DEF_B
    headings = [h for u in result.report["unverified"] for h in u["headings"]]
    assert "## Executive Summary" in headings
    assert "## Closing Assessment" in headings


def test_nothing_repairable_leaves_the_memo_unchanged(tmp_path):
    vd = _version(tmp_path)
    for f in (vd / "1-research").glob("*.md"):
        f.unlink()
    result = repair_memo(vd)
    assert not result.changed
    assert result.text == result.original


def test_two_finished_memos_require_naming_one(tmp_path):
    vd = _version(tmp_path)
    _write(vd / "7-Company-v0.0.2.md", _memo_text())
    with pytest.raises(ValueError, match="--memo"):
        find_memo(vd)
    assert find_memo(vd, "7-Company-v0.0.2.md").name == "7-Company-v0.0.2.md"


# ------------------------------------------------------------- the CLI


def test_dry_run_writes_nothing(tmp_path):
    from cli.repair_citations import main

    vd = _version(tmp_path)
    before = {p: p.read_bytes() for p in vd.rglob("*") if p.is_file()}
    assert main([str(vd)]) == 0
    after = {p: p.read_bytes() for p in vd.rglob("*") if p.is_file()}
    assert before == after


def test_write_repairs_in_place_and_keeps_a_backup(tmp_path):
    from cli.repair_citations import main

    vd = _version(tmp_path)
    memo = vd / "7-Company-v0.0.1.md"
    original = memo.read_text()

    assert main([str(vd), "--write"]) == 0
    assert (vd / "7-Company-v0.0.1.md.bak").read_text() == original
    assert _key_after(memo.read_text(), "Flag one.") == source_key(DEF_C)
    report = json.loads((vd / "repair-report.json").read_text())
    assert report["result"] == "repaired"


def test_prose_guard_refuses_to_write(tmp_path, monkeypatch):
    from cli.repair_citations import main

    vd = _version(tmp_path)
    memo = vd / "7-Company-v0.0.1.md"
    original = memo.read_text()
    real = citation_repair.repair_memo

    def tampered(*args, **kwargs):
        result = real(*args, **kwargs)
        result.text = result.text.replace("Claim one.", "Claim one, reworded.")
        return result

    monkeypatch.setattr(citation_repair, "repair_memo", tampered)
    assert main([str(vd), "--write"]) == 1
    assert memo.read_text() == original
    assert not (vd / "7-Company-v0.0.1.md.bak").exists()


# ------------------------------------------------------------- the scan


def test_scan_reports_cross_section_links_and_flags_duplicate_deals(tmp_path):
    vd = _version(tmp_path)
    dup = tmp_path / "io" / "firm" / "portfolio" / "Company" / "outputs" / vd.name
    dup.parent.mkdir(parents=True)
    import shutil

    shutil.copytree(vd, dup)

    rows = scan(tmp_path / "io")
    assert len(rows) == 2
    for row in rows:
        # Flags' [^2] links to B, which only the overview's research cites.
        assert row.wrong >= 1 and row.checked == 4
        assert row.duplicate_of

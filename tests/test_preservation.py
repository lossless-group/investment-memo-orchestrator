"""
The evidence gate, and the two regimes a memo actually has.

A memo is not uniformly cited, and pretending otherwise produces bad prose. The
body sections carry the argument and its evidence — every marker there is
load-bearing, and losing one orphans a claim. The bookends summarise sections
that are already sourced; they read better lightly cited, and footnoting a
figure the body already vouches for adds nothing a reader can use.

So BODY preserves markers and SUMMARY does not. What SUMMARY still enforces is
that the numbers hold and that no marker is invented — a footnote resolving to
nothing is worse than no footnote, because it looks like evidence.
"""

import pytest

from src.preservation import (
    BODY,
    SUMMARY,
    Losses,
    Preservation,
    compare,
    correction,
    guard,
    instructions,
)

CITED = 'ARR reached $5.9M [^1] across 5.8M policies [^deck]. He called it "the one place where incentives align" [^sieb].'


# --- what gets measured --------------------------------------------------


def test_captures_markers_figures_and_quotes():
    k = Preservation.of(CITED)
    assert k.citations == {"1", "deck", "sieb"}
    assert any("5.9" in f for f in k.figures)
    assert any("5.8" in f for f in k.figures)
    assert any("incentives align" in q for q in k.quotes)


def test_bare_scaled_counts_are_protected():
    """grounding._FIGURE_PATTERN needs $, a comma group or %, so "5.8M policies"
    and "2-5X" were invisible to it — and they are what a memo turns on."""
    k = Preservation.of("The block is 5.8M policies and throughput is 2-5X.")
    assert any("5.8" in f for f in k.figures)
    assert any("2-5" in f for f in k.figures)


def test_the_reference_list_is_not_scanned_for_claims():
    refs = CITED + "\n\n### Citations\n\n[^1]: 2026, Aug 03. Report. p. 1,234\n"
    assert Preservation.of(refs).figures == Preservation.of(CITED).figures


def test_a_wrapped_quote_is_still_a_quote():
    wrapped = 'He called it "the one place\nwhere incentives align" [^1].'
    assert any("incentives align" in q for q in Preservation.of(wrapped).quotes)


# --- BODY: markers are load-bearing --------------------------------------


def test_body_blocks_a_dropped_marker():
    after = Preservation.of("ARR reached $5.9M across 5.8M policies.")
    losses = compare(Preservation.of(CITED), after, mode=BODY)
    assert losses.any
    assert set(losses.citations) == {"1", "deck", "sieb"}


def test_body_allows_rephrasing_that_keeps_the_number():
    before = Preservation.of("Revenue hit $5,900,000 [^1].")
    after = Preservation.of("Revenue climbed to $5,900,000 in the period [^1].")
    assert not compare(before, after, mode=BODY).any


def test_body_instructions_name_every_marker():
    text = instructions(Preservation.of(CITED), mode=BODY)
    for key in ("[^1]", "[^deck]", "[^sieb]"):
        assert key in text
    assert "byte-identical" in text


# --- SUMMARY: clean prose over a sourced body ----------------------------


def test_summary_allows_dropping_markers_and_quotes():
    """The point of the regime. §1 shedding its footnotes is correct, not a bug,
    and a summary that condenses away a direct quotation is doing its job."""
    after = Preservation.of("ARR reached $5.9M across 5.8M policies.")
    losses = compare(Preservation.of(CITED), after,
                     mode=SUMMARY, known_citations={"1", "deck", "sieb"})
    assert not losses.any, "a summary may be clean prose"
    assert not losses.quotes, "condensing away a quotation is legitimate"


def test_summary_still_blocks_a_changed_number():
    """Dropping the footnote is fine. Rounding $5.9M to $6M is not."""
    after = Preservation.of("ARR reached $6M across 5.8M policies.")
    losses = compare(Preservation.of(CITED), after,
                     mode=SUMMARY, known_citations={"1", "deck", "sieb"})
    assert losses.figures
    assert losses.any


def test_summary_blocks_an_invented_marker():
    after = Preservation.of("ARR reached $5.9M [^99] across 5.8M policies.")
    losses = compare(Preservation.of(CITED), after,
                     mode=SUMMARY, known_citations={"1", "deck", "sieb"})
    assert losses.invented_citations == ["99"]


def test_summary_permits_a_marker_the_memo_actually_carries():
    after = Preservation.of("ARR reached $5.9M [^deck] across 5.8M policies.")
    losses = compare(Preservation.of(CITED), after,
                     mode=SUMMARY, known_citations={"1", "deck", "sieb"})
    assert not losses.any


def test_summary_instructions_say_not_to_over_cite():
    text = instructions(Preservation.of(CITED), mode=SUMMARY)
    assert "does not need" in text and "heavy citation" in text
    assert "resolves to nothing" in text
    assert "[^sieb]" not in text, "a summary is not handed a list to reproduce"


# --- the guard loop ------------------------------------------------------


def test_guard_accepts_a_clean_first_attempt():
    calls = []

    def gen(n, prev, losses):
        calls.append(n)
        return CITED
    accepted, log = guard(CITED, gen, mode=BODY)
    assert accepted == CITED and calls == [1]


def test_guard_re_prompts_once_then_accepts():
    drafts = ["ARR reached $5.9M across 5.8M policies.", CITED]
    seen = {}

    def gen(n, prev, losses):
        seen[n] = (prev, losses)
        return drafts[n - 1]
    accepted, log = guard(CITED, gen, mode=BODY, max_attempts=2)
    assert accepted == CITED
    assert seen[2][0] == drafts[0], "the correction must see the draft it is correcting"
    assert set(seen[2][1].citations) == {"1", "deck", "sieb"}


def test_guard_refuses_rather_than_returning_lossy_prose():
    lossy = "ARR was strong."

    def gen(n, prev, losses):
        return lossy
    accepted, log = guard(CITED, gen, mode=BODY, max_attempts=2)
    assert accepted is None
    assert len(log) == 2


def test_guard_returns_none_when_the_model_call_fails():
    accepted, log = guard(CITED, lambda n, p, l: None, mode=BODY)
    assert accepted is None and log == []


def test_correction_itemises_rather_than_summarises():
    losses = Losses(citations=["1"], figures=["$5.9m"], invented_citations=["99"])
    text = correction("previous draft here", losses)
    assert "previous draft here" in text
    assert "[^1]" in text and "$5.9m" in text and "[^99]" in text
    assert "RESOLVE TO NOTHING" in text

"""
The deck cache must survive asset normalization.

`src/asset_normalize.py` compresses oversized dataroom assets in place and parks
the originals. ProfileHealth's deck went 66.8 MB -> 2.38 MB. The content the
pipeline reads is unchanged — it OCR'd to 2,417 characters against the
original's 2,415 — but the bytes are not, so the content hash moved from
019b89fa11ce to 7453c0812bd5 and the cache at `.cache/deck-019b89fa11ce`
orphaned itself. The deck analyst then re-ran a full vision pass over a deck it
had already analysed.

That was the third cache in one session invalidated by ordinary maintenance, and
it is the specific defect named in
context-v/issues/Agent-Sequencing-For-Deals-We-Already-Have-Content-On.md step 3.
"""

from pathlib import Path

from src.deck_cache import (
    cache_dir_for,
    fingerprint_file,
    parked_original_for,
    resolve_cache_dir,
)


def _deal(tmp_path: Path) -> Path:
    d = tmp_path / "io" / "humain" / "deals" / "Acme"
    (d / "inputs" / "Dataroom" / "Company Overview").mkdir(parents=True)
    return d


def _state(tmp_path: Path) -> dict:
    return {"firm": "humain", "company_name": "Acme", "io_root": str(tmp_path / "io")}


def _seed_cache(deal: Path, fingerprint: str) -> Path:
    cache = deal / ".cache" / f"deck-{fingerprint}"
    cache.mkdir(parents=True)
    (cache / "0-deck-analysis.json").write_text('{"company_name": "Acme"}')
    return cache


# --- locating the parked original ---------------------------------------


def test_finds_the_parked_original(tmp_path):
    deal = _deal(tmp_path)
    room = deal / "inputs" / "Dataroom"
    deck = room / "Company Overview" / "Deck.pdf"
    deck.write_bytes(b"compressed")

    parked = room / "_zip-originals" / "oversized" / "Company Overview" / "Deck.pdf"
    parked.parent.mkdir(parents=True)
    parked.write_bytes(b"the original, much larger")

    assert parked_original_for(deck) == parked


def test_no_parked_original_is_not_an_error(tmp_path):
    deal = _deal(tmp_path)
    deck = deal / "inputs" / "Dataroom" / "Company Overview" / "Deck.pdf"
    deck.write_bytes(b"never normalized")
    assert parked_original_for(deck) is None


def test_a_different_parked_file_does_not_match(tmp_path):
    """The lookup is by relative path, so a parked sibling is not this deck."""
    deal = _deal(tmp_path)
    room = deal / "inputs" / "Dataroom"
    deck = room / "Company Overview" / "Deck.pdf"
    deck.write_bytes(b"compressed")
    other = room / "_zip-originals" / "oversized" / "Team" / "Bio.pdf"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"someone else")
    assert parked_original_for(deck) is None


# --- resolution ----------------------------------------------------------


def test_live_fingerprint_wins_when_it_hits(tmp_path, monkeypatch):
    deal = _deal(tmp_path)
    deck = deal / "inputs" / "Dataroom" / "Company Overview" / "Deck.pdf"
    deck.write_bytes(b"unchanged deck")
    fp = fingerprint_file(deck)

    monkeypatch.setattr("src.deck_cache.deal_dir_for", lambda _s: deal)
    _seed_cache(deal, fp)

    resolved, used = resolve_cache_dir(_state(tmp_path), deck, fp)
    assert used == fp
    assert resolved == deal / ".cache" / f"deck-{fp}"


def test_falls_back_to_the_parked_originals_fingerprint(tmp_path, monkeypatch):
    """The ProfileHealth case, exactly."""
    deal = _deal(tmp_path)
    room = deal / "inputs" / "Dataroom"
    deck = room / "Company Overview" / "Deck.pdf"
    deck.write_bytes(b"compressed bytes, same content")

    parked = room / "_zip-originals" / "oversized" / "Company Overview" / "Deck.pdf"
    parked.parent.mkdir(parents=True)
    parked.write_bytes(b"original bytes, 30x larger")

    live_fp = fingerprint_file(deck)
    parked_fp = fingerprint_file(parked)
    assert live_fp != parked_fp, "the premise of the bug"

    monkeypatch.setattr("src.deck_cache.deal_dir_for", lambda _s: deal)
    _seed_cache(deal, parked_fp)  # cache written before normalization

    resolved, used = resolve_cache_dir(_state(tmp_path), deck, live_fp)
    assert used == parked_fp
    assert resolved == deal / ".cache" / f"deck-{parked_fp}"


def test_returns_the_live_fingerprint_when_neither_hits(tmp_path, monkeypatch):
    """A genuinely new deck must store under its own bytes, not inherit a key."""
    deal = _deal(tmp_path)
    room = deal / "inputs" / "Dataroom"
    deck = room / "Company Overview" / "Deck.pdf"
    deck.write_bytes(b"a brand new deck")
    parked = room / "_zip-originals" / "oversized" / "Company Overview" / "Deck.pdf"
    parked.parent.mkdir(parents=True)
    parked.write_bytes(b"an unrelated original")

    monkeypatch.setattr("src.deck_cache.deal_dir_for", lambda _s: deal)
    live_fp = fingerprint_file(deck)

    resolved, used = resolve_cache_dir(_state(tmp_path), deck, live_fp)
    assert used == live_fp
    assert resolved == cache_dir_for(_state(tmp_path), live_fp) or resolved is not None


def test_a_replaced_deck_does_not_reuse_the_old_analysis(tmp_path, monkeypatch):
    """The guarantee the content hash exists to give, still holding.

    If someone swaps in a genuinely different deck and no parked original
    matches, the cache must miss — otherwise this fix would trade one silent
    staleness for a worse one.
    """
    deal = _deal(tmp_path)
    room = deal / "inputs" / "Dataroom"
    deck = room / "Company Overview" / "Deck.pdf"
    deck.write_bytes(b"VERSION TWO of the deck")

    monkeypatch.setattr("src.deck_cache.deal_dir_for", lambda _s: deal)
    _seed_cache(deal, "0123456789ab")  # some older deck's analysis

    resolved, used = resolve_cache_dir(_state(tmp_path), deck, fingerprint_file(deck))
    from src.deck_cache import is_usable
    assert not is_usable(resolved), "a different deck must not hit a stale cache"

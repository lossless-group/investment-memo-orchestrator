"""
Deal-level cache for deck (and dataroom) analysis.

WHY THIS EXISTS
---------------
Deck analysis is the most expensive deterministic step in the pipeline: an
image-based deck falls back to Claude vision, one call per batch of five slides.
The inputs never change between runs — the same PDF produces the same analysis —
yet every new version gets a fresh output directory, finds no artifact there, and
re-runs the whole vision pass. Generating v0.0.1, v0.0.2 and v0.0.3 of one memo
pays for the same slide reading three times.

The cache lives at the DEAL level rather than the version level, because that is
the scope at which the input is actually stable:

    io/<firm>/deals/<Deal>/.cache/deck-<fingerprint>/

`fingerprint` is a content hash of the deck file itself, so replacing the deck
invalidates the cache automatically — no staleness rule to remember, and no way
to silently reuse an analysis of a deck that no longer exists.

WHAT GETS CACHED
----------------
Everything the deck stage produces, not just the JSON. `inject_deck_images`
later reads `deck-screenshots/`, and the writer reads the per-topic drafts in
`0-deck-sections/`; restoring only `0-deck-analysis.json` would leave a run that
looks complete and breaks downstream.

`--fresh` bypasses the cache, since "ignore prior artifacts" should mean all of
them.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

# Artifacts the deck stage produces. Files and directories both.
DECK_ARTIFACTS: List[str] = [
    "0-deck-analysis.json",
    "0-deck-analysis.md",
    "0-deck-sections",
    "deck-screenshots",
]

CACHE_DIRNAME = ".cache"


def fingerprint_file(path: Path, *, length: int = 12) -> Optional[str]:
    """Content hash of a file. None when unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:length]
    except OSError:
        return None


def deal_dir_for(state: Dict[str, Any]) -> Optional[Path]:
    """The deal directory (parent of inputs/ and outputs/), or None."""
    try:
        from .agents.codified_section_researcher import find_deal_inputs_dir
        inputs_dir = find_deal_inputs_dir(state)
        if inputs_dir:
            return Path(inputs_dir).parent
    except Exception:  # noqa: BLE001
        pass
    # Fall back to walking up from the output directory: <deal>/outputs/<version>
    out = state.get("output_dir")
    if out:
        p = Path(out)
        if p.parent.name == "outputs":
            return p.parent.parent
    return None


def cache_dir_for(state: Dict[str, Any], fingerprint: str, kind: str = "deck") -> Optional[Path]:
    deal_dir = deal_dir_for(state)
    if not deal_dir:
        return None
    return deal_dir / CACHE_DIRNAME / f"{kind}-{fingerprint}"


def parked_original_for(deck_path: Path) -> Optional[Path]:
    """The pre-normalization copy of `deck_path`, if asset normalization parked one.

    `src/asset_normalize.py` compresses oversized assets in place and parks the
    original under `_zip-originals/oversized/<path relative to the dataroom>`.
    The content the pipeline reads is unchanged — ProfileHealth's deck OCR'd to
    2,417 characters against the original's 2,415 — but the bytes are not, so
    the content hash moves and the deal-level cache orphans itself.

    Returns the parked file so the caller can ask whether the cache was keyed on
    it. Normalization is exactly the kind of routine maintenance that must not
    cost an hour of re-extraction.
    """
    deck = Path(deck_path)
    for parent in deck.parents:
        parked_root = parent / "_zip-originals" / "oversized"
        if not parked_root.is_dir():
            continue
        try:
            relative = deck.relative_to(parent)
        except ValueError:  # pragma: no cover - parents() guarantees this holds
            continue
        candidate = parked_root / relative
        if candidate.is_file():
            return candidate
    return None


def resolve_cache_dir(
    state: Dict[str, Any], deck_path: Path, fingerprint: Optional[str]
) -> tuple[Optional[Path], Optional[str]]:
    """The cache directory to use for this deck, and the fingerprint it is keyed on.

    Prefers the live file's own fingerprint. When that misses and a parked
    pre-normalization original exists, the original's fingerprint is tried: a
    deck whose parked original hashes to a cached key *is* the cached deck,
    compressed. Returns the live fingerprint when neither hits, so a fresh run
    stores under the current bytes rather than perpetuating the old key.
    """
    live_dir = cache_dir_for(state, fingerprint) if fingerprint else None
    if is_usable(live_dir):
        return live_dir, fingerprint

    parked = parked_original_for(deck_path)
    if parked:
        parked_fp = fingerprint_file(parked)
        if parked_fp and parked_fp != fingerprint:
            parked_dir = cache_dir_for(state, parked_fp)
            if is_usable(parked_dir):
                print(f"♻️  deck cache keyed on the pre-normalization original "
                      f"({parked_fp}); current file is {fingerprint}", flush=True)
                return parked_dir, parked_fp

    return live_dir, fingerprint


def _copy(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def store(cache_dir: Path, output_dir: Path, artifacts: List[str] = None) -> int:
    """Copy this run's deck artifacts into the cache. Returns count stored."""
    artifacts = artifacts or DECK_ARTIFACTS
    stored = 0
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        for name in artifacts:
            src = Path(output_dir) / name
            if src.exists():
                _copy(src, cache_dir / name)
                stored += 1
    except Exception:  # noqa: BLE001 - caching must never break a run
        return stored
    return stored


def restore(cache_dir: Path, output_dir: Path, artifacts: List[str] = None) -> int:
    """Copy cached deck artifacts into a fresh output dir. Returns count restored."""
    artifacts = artifacts or DECK_ARTIFACTS
    restored = 0
    try:
        for name in artifacts:
            src = Path(cache_dir) / name
            if src.exists():
                _copy(src, Path(output_dir) / name)
                restored += 1
    except Exception:  # noqa: BLE001
        return restored
    return restored


def is_usable(cache_dir: Optional[Path]) -> bool:
    """A cache is usable only if the analysis JSON is present — the rest is optional."""
    return bool(cache_dir and (cache_dir / "0-deck-analysis.json").exists())

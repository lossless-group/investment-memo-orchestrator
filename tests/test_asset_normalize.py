"""
Tests for dataroom asset normalization.

Size is not only a storage problem. A 162MB scanned PDF is rendered and OCR'd on
every run, from a document carrying far more image data than OCR can use —
measured on the real file, `gs -dPDFSETTINGS=/ebook` gives 162MB -> 16.1MB while
the pipeline's own extractor OCRs 2,415 chars against 2,417.

The invariant these tests defend: nothing is ever destroyed, and the dataroom is
never left without an asset. The original is parked in the gitignored
`_zip-originals/`, and every failure path leaves the source in place.

Compression tools are stubbed; what is under test is the thresholds, the
worth-it rule, the parking, and the failure handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import asset_normalize
from src.asset_normalize import (
    IMAGE_THRESHOLD_BYTES,
    MAX_RATIO,
    PDF_THRESHOLD_BYTES,
    normalize_asset,
    normalize_dataroom_assets,
)


def make_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def stub_compress(monkeypatch, ratio: float = 0.1, succeed: bool = True):
    def fake(source, destination, *a, **k):
        if not succeed:
            return False
        destination.write_bytes(b"y" * max(1, int(source.stat().st_size * ratio)))
        return True
    monkeypatch.setattr(asset_normalize, "_compress_pdf", fake)
    monkeypatch.setattr(asset_normalize, "_compress_image", fake)


class TestThresholds:
    def test_small_pdf_is_left_alone(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        f = make_file(tmp_path / "d" / "small.pdf", 1024)
        r = normalize_asset(f, tmp_path / "d")
        assert r.action == "skipped" and r.reason == "under threshold"

    def test_large_pdf_is_normalized(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        f = make_file(tmp_path / "d" / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        assert normalize_asset(f, tmp_path / "d").action == "normalized"

    def test_large_image_is_normalized(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        f = make_file(tmp_path / "d" / "scan.jpeg", IMAGE_THRESHOLD_BYTES + 1)
        assert normalize_asset(f, tmp_path / "d").action == "normalized"

    def test_unsupported_type_is_skipped(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        f = make_file(tmp_path / "d" / "sheet.xlsx", PDF_THRESHOLD_BYTES + 1)
        assert normalize_asset(f, tmp_path / "d").reason == "not a normalizable type"


class TestWorthItRule:
    def test_marginal_saving_is_rejected(self, tmp_path, monkeypatch):
        """A 5% saving is not worth moving a file for."""
        stub_compress(monkeypatch, ratio=MAX_RATIO + 0.1)
        f = make_file(tmp_path / "d" / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        r = normalize_asset(f, tmp_path / "d")
        assert r.action == "skipped" and "not worth it" in r.reason
        assert f.exists() and f.stat().st_size == PDF_THRESHOLD_BYTES + 1

    def test_real_saving_is_taken(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch, ratio=0.1)
        f = make_file(tmp_path / "d" / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        r = normalize_asset(f, tmp_path / "d")
        assert r.action == "normalized" and r.saved_pct > 80


class TestNothingIsDestroyed:
    """The load-bearing property. An operator must always be able to get the
    original back, and the dataroom must never lose an asset."""

    def test_original_is_parked_not_deleted(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        root = tmp_path / "Dataroom"
        f = make_file(root / "Team" / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        r = normalize_asset(f, root)
        parked = root / "_zip-originals" / "oversized" / "Team" / "big.pdf"
        assert r.original_parked == parked
        assert parked.exists() and parked.stat().st_size == PDF_THRESHOLD_BYTES + 1

    def test_tree_position_is_preserved_when_parking(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        root = tmp_path / "Dataroom"
        f = make_file(root / "Corporate Docs" / "SAFEs" / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        normalize_asset(f, root)
        assert (root / "_zip-originals" / "oversized" / "Corporate Docs" / "SAFEs" / "big.pdf").exists()

    def test_normalized_file_takes_the_original_path(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        root = tmp_path / "Dataroom"
        f = make_file(root / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        normalize_asset(f, root)
        assert f.exists() and f.stat().st_size < PDF_THRESHOLD_BYTES

    def test_failed_compression_leaves_the_source_in_place(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch, succeed=False)
        root = tmp_path / "Dataroom"
        f = make_file(root / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        r = normalize_asset(f, root)
        assert r.action == "failed"
        assert f.exists() and f.stat().st_size == PDF_THRESHOLD_BYTES + 1
        assert not (root / "_zip-originals").exists()

    def test_no_staging_leftovers(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        root = tmp_path / "Dataroom"
        f = make_file(root / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        normalize_asset(f, root)
        assert not list(root.glob("*.normalized"))

    def test_dry_run_changes_nothing(self, tmp_path, monkeypatch):
        stub_compress(monkeypatch)
        root = tmp_path / "Dataroom"
        f = make_file(root / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        r = normalize_asset(f, root, dry_run=True)
        assert r.action == "normalized" and r.reason == "dry run"
        assert f.stat().st_size == PDF_THRESHOLD_BYTES + 1
        assert not (root / "_zip-originals").exists()


class TestSweep:
    def test_zip_originals_is_never_walked(self, tmp_path, monkeypatch):
        """Originals live there; recompressing them defeats keeping them."""
        stub_compress(monkeypatch)
        root = tmp_path / "Dataroom"
        make_file(root / "_zip-originals" / "oversized" / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        assert normalize_dataroom_assets(root) == []

    def test_idempotent_by_construction(self, tmp_path, monkeypatch):
        """A normalized file is under the threshold next pass, so it is skipped."""
        stub_compress(monkeypatch)
        root = tmp_path / "Dataroom"
        make_file(root / "big.pdf", PDF_THRESHOLD_BYTES + 1)
        assert len(normalize_dataroom_assets(root)) == 1
        assert normalize_dataroom_assets(root) == []

    def test_missing_dataroom_is_a_no_op(self, tmp_path):
        assert normalize_dataroom_assets(tmp_path / "absent") == []

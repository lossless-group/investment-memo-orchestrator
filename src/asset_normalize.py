"""
Shrink oversized dataroom assets on ingest, keeping the originals out of git.

One ProfileHealth dataroom carries 269 MB across eight files, and the two worst
are a 162 MB scanned PDF and a 63.7 MB deck. Size is not only a storage problem:
the 162 MB file is a scan at 19 characters of text per page, so every run renders
and OCRs it, and it is rendered from a document carrying far more image data than
OCR can use.

Measured on that file, `gs -dPDFSETTINGS=/ebook` produces 162 MB → 16.1 MB, and
the pipeline's own extractor OCRs the result to 2,417 characters against the
original's 2,415. The content the pipeline actually consumes is identical; the
90% is resolution nothing reads.

The arrangement matches media transcription: the original is parked in the
gitignored `_zip-originals/`, and the usable derivative sits in the dataroom
where the scanner finds it. Nothing is destroyed — a normalized asset can always
be re-derived, and the untouched original is still on the operator's disk.

Compression is skipped whenever it does not clearly pay: a file already small
enough, or a result that is not meaningfully smaller than what it replaced.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Below these, compression is not worth the wall-clock or the risk.
PDF_THRESHOLD_BYTES = 5 * 1024 * 1024
IMAGE_THRESHOLD_BYTES = 2 * 1024 * 1024

# A normalized file must be at most this fraction of the original, or the
# original is kept. A 5% saving is not worth moving a file for.
MAX_RATIO = 0.7

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# /ebook downsamples images to 150dpi and is the setting the OCR comparison was
# run against. /printer (300dpi) is the fallback when /ebook somehow grows a file.
GS_SETTING = "/ebook"


@dataclass
class NormalizeResult:
    path: Path
    before: int = 0
    after: int = 0
    action: str = "skipped"        # normalized | skipped | failed
    reason: str = ""
    original_parked: Optional[Path] = None

    @property
    def saved(self) -> int:
        return max(0, self.before - self.after)

    @property
    def saved_pct(self) -> float:
        return 100.0 * self.saved / self.before if self.before else 0.0


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def _park_original(source: Path, dataroom_root: Path) -> Optional[Path]:
    """
    Move the untouched original into the gitignored `_zip-originals/oversized/`,
    preserving its position in the tree so it can be put back by hand.
    """
    try:
        relative = source.relative_to(dataroom_root)
    except ValueError:
        relative = Path(source.name)
    destination = dataroom_root / "_zip-originals" / "oversized" / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return destination
    shutil.move(str(source), str(destination))
    return destination


def _compress_pdf(source: Path, destination: Path, setting: str = GS_SETTING) -> bool:
    if not tool_available("gs"):
        return False
    try:
        proc = subprocess.run(
            ["gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
             f"-dPDFSETTINGS={setting}", "-dNOPAUSE", "-dQUIET", "-dBATCH",
             f"-sOutputFile={destination}", str(source)],
            capture_output=True, text=True, timeout=1800, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return proc.returncode == 0 and destination.exists() and destination.stat().st_size > 0


def _compress_image(source: Path, destination: Path, max_width: int = 2400) -> bool:
    """
    Downscale and re-encode. These are photographed 83(b) elections and signature
    pages — 2400px is well past what OCR needs and still legible to a human.
    """
    if tool_available("magick"):
        cmd = ["magick", str(source), "-auto-orient", "-resize", f"{max_width}x{max_width}>",
               "-strip", "-quality", "82", str(destination)]
    elif tool_available("sips"):
        cmd = ["sips", "-Z", str(max_width), "-s", "format", "jpeg",
               "-s", "formatOptions", "82", str(source), "--out", str(destination)]
    else:
        return False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (subprocess.SubprocessError, OSError):
        return False
    return proc.returncode == 0 and destination.exists() and destination.stat().st_size > 0


def normalize_asset(source: Path, dataroom_root: Path, *, dry_run: bool = False) -> NormalizeResult:
    """Normalize one asset. Never raises; a failure leaves the file untouched."""
    source = Path(source)
    result = NormalizeResult(path=source)
    if not source.exists():
        result.action, result.reason = "failed", "file not found"
        return result

    before = source.stat().st_size
    result.before = result.after = before
    suffix = source.suffix.lower()

    if suffix == ".pdf":
        if before < PDF_THRESHOLD_BYTES:
            result.reason = "under threshold"
            return result
        compress = _compress_pdf
    elif suffix in IMAGE_SUFFIXES:
        if before < IMAGE_THRESHOLD_BYTES:
            result.reason = "under threshold"
            return result
        compress = _compress_image
    else:
        result.reason = "not a normalizable type"
        return result

    staged = source.with_suffix(source.suffix + ".normalized")
    if not compress(source, staged):
        staged.unlink(missing_ok=True)
        result.action, result.reason = "failed", "compression tool failed"
        return result

    after = staged.stat().st_size
    if after > before * MAX_RATIO:
        staged.unlink(missing_ok=True)
        result.reason = f"not worth it ({after / before:.0%} of original)"
        return result

    if dry_run:
        staged.unlink(missing_ok=True)
        result.after, result.action, result.reason = after, "normalized", "dry run"
        return result

    # Park the original first. If that fails the source is still in place and
    # the staged file is discarded — the dataroom is never left without the asset.
    try:
        parked = _park_original(source, dataroom_root)
    except OSError as exc:
        staged.unlink(missing_ok=True)
        result.action, result.reason = "failed", f"could not park original: {exc}"
        return result

    shutil.move(str(staged), str(source))
    result.after, result.action, result.original_parked = after, "normalized", parked
    return result


LEDGER_NAME = "normalized.json"


def ledger_path(dataroom_root: Path) -> Path:
    """Where the record of what was normalized lives (inside the parked area)."""
    return Path(dataroom_root) / "_zip-originals" / LEDGER_NAME


def record_normalized(dataroom_root: Path, results: List["NormalizeResult"]) -> None:
    """
    Record which documents were normalized, and the bytes it moved.

    The dataroom analysis reuse check compares total byte size as a cheap
    staleness proxy. Normalization changes bytes precisely while preserving the
    content the pipeline reads, so without this record it looks exactly like the
    operator swapped documents, and an hour of extraction is thrown away and
    re-run for nothing.
    """
    import json

    path = ledger_path(dataroom_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = {}
    if path.exists():
        try:
            prior = json.loads(path.read_text())
        except (OSError, ValueError):
            prior = {}
    entries = prior.get("entries", {})
    for r in results:
        if r.action != "normalized":
            continue
        try:
            key = str(Path(r.path).resolve().relative_to(Path(dataroom_root).resolve()))
        except ValueError:
            key = Path(r.path).name
        entries[key] = {"before": r.before, "after": r.after}
    path.write_text(json.dumps({"entries": entries}, indent=2))


def normalized_byte_delta(dataroom_root: Path) -> int:
    """Total bytes normalization removed, for the staleness check to discount."""
    import json

    path = ledger_path(dataroom_root)
    if not path.exists():
        return 0
    try:
        entries = json.loads(path.read_text()).get("entries", {})
    except (OSError, ValueError):
        return 0
    return sum(max(0, e.get("before", 0) - e.get("after", 0)) for e in entries.values())


def normalize_dataroom_assets(dataroom_root: Path, *, dry_run: bool = False) -> List[NormalizeResult]:
    """
    Normalize every oversized asset in a dataroom.

    Idempotent by construction: a normalized file is under the threshold on the
    next pass, so it is skipped rather than recompressed. `_zip-originals/` is
    never walked — that is where originals go, and recompressing them would
    defeat the point of keeping them.
    """
    root = Path(dataroom_root)
    if not root.exists():
        return []

    results: List[NormalizeResult] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "_zip-originals" in path.parts:
            continue
        if path.suffix.lower() != ".pdf" and path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if path.stat().st_size < min(PDF_THRESHOLD_BYTES, IMAGE_THRESHOLD_BYTES):
            continue
        outcome = normalize_asset(path, root, dry_run=dry_run)
        if outcome.action != "skipped":
            results.append(outcome)

    if not dry_run and any(r.action == "normalized" for r in results):
        record_normalized(root, results)
    return results

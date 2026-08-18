#!/usr/bin/env python3
"""
Slim a startup's deck into something small enough to serve and readable enough
to trust — and emit BOTH artifacts a DidiDecks deal slide needs:

  1. <out>/pages/NN.jpg   — one image per page, for Play-UI slides
  2. <out>/<slug>.pdf     — a rebuilt, compressed PDF for download

Accepts either input shape:
  --pdf <file>        a real PDF (rendered at --dpi via Poppler, PyMuPDF fallback)
  --images <dir>      a folder of page images (screenshots, exports)

Settings inherit deck_analyst.py's settled judgment: 150 DPI render, JPEG
quality 85 with optimize=True. See
ai-labs/context-v/plans/Quick-Slides-Assembly-to-Demo-Deal-Coverage.md

Usage:
  uv run python scripts/slim_deck.py --images ~/Desktop/deck-folder \\
      --slug impulse-labs --out ../../../dididecks-ai/client-sites/lossless-decks/public/decks
"""

import argparse
import glob
import os
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

# Inherited from src/agents/deck_analyst.py — do not drift these without a reason.
DEFAULT_DPI = 150
DEFAULT_QUALITY = 85
DEFAULT_MAX_WIDTH = 1600  # ~150 DPI across a 10.6" slide; retina screenshots are 2-3x this


def render_pdf_pages(pdf_path: Path, dpi: int) -> list[Image.Image]:
    """PDF -> PIL images. Poppler path first (higher quality), PyMuPDF fallback."""
    try:
        from pdf2image import convert_from_path

        return convert_from_path(str(pdf_path), dpi=dpi)
    except Exception as exc:  # Poppler missing or failed
        print(f"  pdf2image unavailable ({exc}); falling back to PyMuPDF", file=sys.stderr)
        doc = fitz.open(str(pdf_path))
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        out = []
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            out.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return out


def load_image_dir(images_dir: Path) -> list[Image.Image]:
    """Folder of page images -> PIL images, sorted by filename."""
    exts = ("png", "jpg", "jpeg", "webp", "tif", "tiff")
    files: list[str] = []
    for e in exts:
        files.extend(glob.glob(str(images_dir / f"*.{e}")))
        files.extend(glob.glob(str(images_dir / f"*.{e.upper()}")))
    files = sorted(set(files))
    if not files:
        raise SystemExit(f"No page images found in {images_dir}")
    print(f"  {len(files)} page images found")
    return [Image.open(f) for f in files]


def detect_chrome_box(images: list[Image.Image]) -> tuple[int, int, int, int] | None:
    """
    Screenshots of a deck viewer (DocSend, Drive, a browser) carry the viewer's
    own chrome — toolbars, page counters, nav arrows, the viewer's avatar. That
    chrome is not the founder's deck and must not ship inside it.

    Detects the slide rectangle by finding the dark chrome bars top and bottom,
    then the bright slide edges left and right. Returns a box only when EVERY
    page agrees — a unanimous box means real chrome, a disagreeing one means we
    are guessing, and we would rather crop nothing than crop content.
    """
    import numpy as np

    boxes = set()
    for im in images:
        a = np.asarray(im.convert("RGB")).astype(float).mean(axis=2)
        h, w = a.shape
        rows = a.mean(axis=1)
        dark = np.where(rows < 90)[0]
        top_d = dark[dark < h * 0.25]
        bot_d = dark[dark > h * 0.75]
        top = int(top_d.max()) + 1 if len(top_d) else 0
        bot = int(bot_d.min()) if len(bot_d) else h

        colm = a[top + 20 : bot - 20].mean(axis=0)
        bright = np.where(colm > 150)[0]
        left, right = (int(bright.min()), int(bright.max()) + 1) if len(bright) else (0, w)
        boxes.add((left, top, right, bot))

    if len(boxes) != 1:
        print(f"  chrome crop: pages disagree ({len(boxes)} boxes) — skipping crop")
        return None

    box = boxes.pop()
    if box == (0, 0, images[0].width, images[0].height):
        return None
    print(f"  chrome crop: {box} -> {box[2]-box[0]}x{box[3]-box[1]} (unanimous across {len(images)} pages)")
    return box


def normalize(img: Image.Image, max_width: int) -> Image.Image:
    """Flatten alpha onto white and downscale to max_width. JPEG has no alpha."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    if img.width > max_width:
        h = round(img.height * max_width / img.width)
        img = img.resize((max_width, h), Image.LANCZOS)
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", type=Path)
    src.add_argument("--images", type=Path)
    ap.add_argument("--slug", required=True, help="deal slug; names the output dir and PDF")
    ap.add_argument("--out", type=Path, required=True, help="output root (e.g. public/decks)")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    ap.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    ap.add_argument("--max-width", type=int, default=DEFAULT_MAX_WIDTH)
    ap.add_argument(
        "--crop-chrome",
        action="store_true",
        help="detect and strip viewer chrome (DocSend/browser toolbars) from screenshots",
    )
    args = ap.parse_args()

    print(f"Slimming '{args.slug}' (dpi={args.dpi}, quality={args.quality}, max_width={args.max_width})")

    if args.pdf:
        source_bytes = args.pdf.stat().st_size
        pages = render_pdf_pages(args.pdf, args.dpi)
    else:
        source_bytes = sum(
            f.stat().st_size for f in args.images.iterdir() if f.is_file()
        )
        pages = load_image_dir(args.images)

    out_dir: Path = args.out / args.slug
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    crop_box = detect_chrome_box(pages) if args.crop_chrome else None

    # ── 1. page JPEGs (Play-UI slides) ────────────────────────────────────
    jpg_paths: list[Path] = []
    for i, img in enumerate(pages, start=1):
        if crop_box:
            img = img.crop(crop_box)
        img = normalize(img, args.max_width)
        p = pages_dir / f"{i:02d}.jpg"
        img.save(p, "JPEG", quality=args.quality, optimize=True)
        jpg_paths.append(p)

    pages_bytes = sum(p.stat().st_size for p in jpg_paths)

    # ── 2. rebuilt PDF (download) ─────────────────────────────────────────
    # PyMuPDF is already in the lockfile — no img2pdf/Ghostscript needed.
    doc = fitz.open()
    for p in jpg_paths:
        with Image.open(p) as im:
            w, h = im.size
        page = doc.new_page(width=w, height=h)
        page.insert_image(fitz.Rect(0, 0, w, h), filename=str(p))
    pdf_out = out_dir / f"{args.slug}.pdf"
    doc.save(str(pdf_out), deflate=True, garbage=4)
    doc.close()

    pdf_bytes = pdf_out.stat().st_size
    mb = lambda b: b / 1_000_000
    print(f"\n  pages   : {len(jpg_paths)}")
    print(f"  source  : {mb(source_bytes):7.1f} MB")
    print(f"  jpegs   : {mb(pages_bytes):7.1f} MB  ({pages_bytes/source_bytes:.1%} of source)")
    print(f"  pdf     : {mb(pdf_bytes):7.1f} MB  ({pdf_bytes/source_bytes:.1%} of source)")
    print(f"\n  -> {out_dir}")


if __name__ == "__main__":
    main()

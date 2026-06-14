"""Capture a DocSend deck to a single PDF.

DocSend protects decks behind a JavaScript canvas/img viewer that disables
print and right-click-save. This script drives a headless Chromium via
Playwright to navigate the deck page-by-page, screenshot each slide at its
native pixel ratio, and assemble the screenshots into a PDF that the
existing `deck_analyst.py` agent can consume.

LIMITATION: Decks gated by an NDA (eSignature required, not just an email
form) cannot be captured by this script and shouldn't be — bypassing an
NDA would be a contractual violation. For those decks, take screenshots
manually inside an authenticated browser and stitch them with PyMuPDF
(see `apps/memopop-orchestrator/io/alpha-jwc/deals/Panthalassa-Deck-Series-C/`
for a worked example).

Supports two URL shapes:
  - Direct-share link: https://docsend.com/view/{deck}/d/{page}
    No email gate; pages are addressable directly.
  - Standard link:     https://docsend.com/view/{deck}
    May require an email gate (--email flag).

Usage:
    python cli/capture_docsend.py \\
        --url https://docsend.com/view/fwxwedp3jy4rbez9/d/kqfvrpqf4qvupbxk \\
        --out io/alpha-jwc/deals/Panthalassa-Deck-Series-C/inputs/Panthalassa-deck.pdf

    # With email gate
    python cli/capture_docsend.py --url <url> --out <pdf> --email you@firm.com

    # Limit pages (for testing)
    python cli/capture_docsend.py --url <url> --out <pdf> --max-pages 3

    # Keep intermediate PNGs alongside the PDF
    python cli/capture_docsend.py --url <url> --out <pdf> --keep-pngs
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF — already a project dep
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright


VIEWPORT = {"width": 1600, "height": 1100}
DEVICE_SCALE_FACTOR = 2  # Retina; bumps fidelity without bloating like Apple-screen screenshots
# A real Chrome UA — default Playwright UA contains "HeadlessChrome" which
# CloudFront WAF (in front of docsend.com) blocks with an HTML error page.
REAL_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
SLIDE_SELECTORS = [
    # Current DocSend (verified 2026-06-09): img with classes "preso-view page-view"
    # served from CloudFront with an elaine-request-id in the src. The "error-view"
    # variant is a fallback placeholder and must be excluded.
    "img.preso-view.page-view[src*='elaine-request-id']",
    "img.preso-view.page-view:not(.error-view)",
    # Older DOM shapes — kept as fallbacks
    "img.page-view__img",
    "canvas.page-view__canvas",
    "div.preso-view img",
    "div[class*=page-view] img",
]
NEXT_BUTTON_SELECTORS = [
    "button[aria-label='Next page']",
    "button.next-button",
    "div.next-page",
]
PAGE_COUNT_SELECTORS = [
    # Current DocSend (verified 2026-06-09): "<current> / <total>" inside
    # div.toolbar-page-indicator
    "div.toolbar-page-indicator",
    "[class*='toolbar-page-indicator']",
    # Older DOM shapes
    "span.toolbar__page-count",
    "div[class*=page-count]",
    "span[class*=total-pages]",
]


def find_slide_element(page: Page):
    for sel in SLIDE_SELECTORS:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=3000)
            return loc, sel
        except PWTimeout:
            continue
    return None, None


def detect_total_pages(page: Page) -> int | None:
    for sel in PAGE_COUNT_SELECTORS:
        try:
            text = page.locator(sel).first.inner_text(timeout=1500).strip()
            # Formats: "1 / 24", "1 of 24", "24". The current-page-vs-total
            # ordering is "current / total", so we want the larger integer
            # (or the only one if the indicator just shows "24").
            digits = [int(t.strip()) for t in text.replace("of", "/").split("/") if t.strip().isdigit()]
            if digits:
                return max(digits)
        except (PWTimeout, Exception):
            continue
    return None


def advance(page: Page) -> bool:
    for sel in NEXT_BUTTON_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=500) and btn.is_enabled():
                btn.click()
                return True
        except (PWTimeout, Exception):
            continue
    # Keyboard fallback — most viewers honor ArrowRight
    page.keyboard.press("ArrowRight")
    return True


SUBMIT_BUTTON_SELECTORS = [
    "button[type=submit]",
    "button:has-text('Continue')",
    "button:has-text('Submit')",
]


def _click_submit(page: Page) -> None:
    for sel in SUBMIT_BUTTON_SELECTORS:
        try:
            page.locator(sel).first.click(timeout=2000)
            return
        except (PWTimeout, Exception):
            continue


EMAIL_GATE_SELECTORS = [
    # DocSend's link_auth_form is the actual gate. Scope to it first because
    # the page often also contains a hidden feedback widget with input[type=email].
    "form#new_link_auth_form input[type=email]",
    "input[name='link_auth_form[email]']",
    "input[type=email]:visible",
    "input[type=email]",
]
PASSCODE_GATE_SELECTORS = [
    # DocSend renders the passcode as type=text (not type=password). Try the
    # named field first, then a password fallback for other gate variants.
    "input[name='link_auth_form[passcode]']",
    "form#new_link_auth_form input[type=text]",
    "input[type=password]",
]


def _fill_first_present(page: Page, selectors: list[str], value: str, timeout: int) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.fill(value)
            return True
        except (PWTimeout, Exception):
            continue
    return False


def handle_gate(page: Page, email: str | None, passcode: str | None) -> None:
    # DocSend gates come in shapes that include:
    #   1. email only (input[type=email] + submit)
    #   2. email + passcode on the same form (both inputs + submit) — passcode
    #      is rendered as input[type=text] inside form#new_link_auth_form
    #   3. email first → submit → passcode appears in a second stage → submit
    if not email and not passcode:
        return

    # Stage 1: fill whatever inputs are visible now, submit
    if email:
        _fill_first_present(page, EMAIL_GATE_SELECTORS, email, timeout=4000)
    if passcode:
        _fill_first_present(page, PASSCODE_GATE_SELECTORS, passcode, timeout=1500)
    _click_submit(page)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass

    # Stage 2: if a passcode field now appears (two-stage flow), fill + submit
    if passcode and _fill_first_present(page, PASSCODE_GATE_SELECTORS, passcode, timeout=3000):
        _click_submit(page)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass


def capture(url: str, out_pdf: Path, email: str | None, passcode: str | None, max_pages: int | None, keep_pngs: bool) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    png_dir = out_pdf.with_suffix("")
    png_dir.mkdir(parents=True, exist_ok=True)

    captured: list[Path] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=DEVICE_SCALE_FACTOR,
            user_agent=REAL_USER_AGENT,
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        )
        # Hide the navigator.webdriver flag that betrays automation to bot detectors
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()

        print(f"  → navigating {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)

        if email or passcode:
            handle_gate(page, email, passcode)

        slide, slide_sel = find_slide_element(page)
        if slide is None:
            raise RuntimeError(
                "Could not locate a DocSend slide element. The viewer DOM may have changed — "
                f"update SLIDE_SELECTORS in {__file__}."
            )
        print(f"  → slide selector: {slide_sel}")

        total = detect_total_pages(page)
        if total:
            print(f"  → detected {total} pages")
        else:
            print("  → page count not detected, will stop on duplicate frame")

        # DocSend uses a carousel that pre-mounts neighbor slides, so picking
        # "the first matching img" reliably returns slide 1 forever. Instead,
        # screenshot the carousel container's bounding box per page and rely on
        # the toolbar indicator to confirm advance happened.
        carousel = None
        for sel in ["div.carousel", "div.js-viewer", "div.viewer"]:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=2000)
                box = loc.bounding_box()
                if box and box["width"] > 100:
                    carousel = (sel, loc)
                    print(f"  → carousel selector: {sel}  bbox={box}")
                    break
            except (PWTimeout, Exception):
                continue

        def current_page_num() -> int | None:
            for sel in PAGE_COUNT_SELECTORS:
                try:
                    text = page.locator(sel).first.inner_text(timeout=1000).strip()
                    digits = [int(t.strip()) for t in text.replace("of", "/").split("/") if t.strip().isdigit()]
                    if digits:
                        return min(digits)  # current is the smaller of "<current> / <total>"
                except (PWTimeout, Exception):
                    continue
            return None

        seen_hashes: set[bytes] = set()
        idx = 0
        while True:
            idx += 1
            if max_pages and idx > max_pages:
                break
            if total and idx > total:
                break

            # Wait until the toolbar shows the expected page number (or just
            # settle if we can't read it) before capturing.
            if idx > 1:
                deadline = time.time() + 8
                while time.time() < deadline:
                    cur = current_page_num()
                    if cur == idx:
                        break
                    time.sleep(0.2)
                else:
                    print(f"  ! toolbar never advanced to {idx}, stopping")
                    break
            time.sleep(0.6)  # let the image swap and any fade settle

            png_path = png_dir / f"slide-{idx:03d}.png"
            if carousel:
                box = carousel[1].bounding_box()
                if not box:
                    print(f"  ! carousel bbox unavailable for slide {idx}, stopping")
                    break
                page.screenshot(
                    path=str(png_path),
                    clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]},
                )
            else:
                # Fallback to the original slide-element screenshot if no carousel found
                slide = page.locator(slide_sel).first
                try:
                    slide.wait_for(state="visible", timeout=10000)
                except PWTimeout:
                    print(f"  ! slide {idx} did not appear in time, stopping")
                    break
                slide.screenshot(path=str(png_path))

            data = png_path.read_bytes()
            sig = data[-512:]  # cheap dedupe — last 512B of PNG differs even slightly
            if sig in seen_hashes and not total:
                print(f"  → slide {idx} duplicate of prior frame, treating as end-of-deck")
                png_path.unlink()
                break
            seen_hashes.add(sig)

            captured.append(png_path)
            print(f"    captured slide {idx} ({len(data) // 1024} KB)")

            if total and idx >= total:
                break

            advance(page)
            time.sleep(0.4)

        browser.close()

    if not captured:
        raise RuntimeError("No slides captured.")

    print(f"  → assembling {len(captured)} slides into PDF")
    doc = fitz.open()
    for png in captured:
        img = fitz.open(png)
        rect = img[0].rect
        pdf_bytes = img.convert_to_pdf()
        img.close()
        single = fitz.open("pdf", pdf_bytes)
        doc.insert_pdf(single)
        single.close()
    doc.save(str(out_pdf), garbage=4, deflate=True)
    doc.close()

    if not keep_pngs:
        for png in captured:
            png.unlink()
        try:
            png_dir.rmdir()
        except OSError:
            pass

    size_kb = out_pdf.stat().st_size // 1024
    print(f"✓ {out_pdf}  ({len(captured)} pages, {size_kb} KB)")


def main() -> int:
    p = argparse.ArgumentParser(description="Capture a DocSend deck to PDF via headless Chromium.")
    p.add_argument("--url", required=True, help="DocSend share URL (view/... or view/.../d/...)")
    p.add_argument("--out", required=True, type=Path, help="Output PDF path")
    p.add_argument("--email", help="Email for the gate, if the link requires one")
    p.add_argument("--passcode", help="Passcode for the gate, if the link requires one (in addition to or instead of email)")
    p.add_argument("--max-pages", type=int, help="Stop after N pages (for testing)")
    p.add_argument("--keep-pngs", action="store_true", help="Keep per-slide PNGs alongside the PDF")
    args = p.parse_args()

    try:
        capture(args.url, args.out, args.email, args.passcode, args.max_pages, args.keep_pngs)
    except Exception as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

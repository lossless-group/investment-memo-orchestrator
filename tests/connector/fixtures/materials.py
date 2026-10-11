"""Synthetic materials for the materials tests: PDFs generated in the test, never copied.

The two-page deck is fixture-co's (spec §Fixtures): invented text about an
invented company, made with PyMuPDF at test time so no real deck ever enters the
repo. ``large_pdf`` makes a many-page file for the time-budget test.
"""

from __future__ import annotations

DECK_PAGES = [
    (
        "Fixture Co: inventory counts by camera",
        "Fixture Co sells a phone app that counts hardware store stock from photos.",
        "Synthetic deck page one. No real company, no client data.",
    ),
    (
        "Traction and the ask",
        "Forty pilot stores in the synthetic Midwest; raising a synthetic seed round.",
        "Synthetic deck page two. Every number here is invented for tests.",
    ),
]

#: A phrase from each page, to find in the extracted text.
PAGE_MARKERS = ["inventory counts by camera", "Traction and the ask"]


def two_page_pdf() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for lines in DECK_PAGES:
        page = doc.new_page()
        y = 72
        for line in lines:
            page.insert_text((72, y), line, fontsize=11)
            y += 24
    data = doc.tobytes()
    doc.close()
    return data


def large_pdf(pages: int = 400) -> bytes:
    """A deck big enough that extracting it inline would be noticeably slow.

    About 1 MB and 300,000 characters: large, but under the 400,000-character
    cap on extracted text, so the last page's text must come through.
    """
    import pymupdf

    doc = pymupdf.open()
    filler = "Synthetic filler line for the large-file test; it describes nothing real. "
    for number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 72), f"Large synthetic deck, page {number}", fontsize=11)
        for row in range(10):
            page.insert_text((72, 100 + row * 20), filler, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data

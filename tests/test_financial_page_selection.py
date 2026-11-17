"""
The financial extractor picks pages by signal, not a prefix of the text.

An audited statement is front-loaded with prose and back-loaded with numbers.
Sending the first 8,000 characters sent the cover and the directors' statement
and nothing else. See context-v/issues/Financial-Extractor-Reads-Only-The-Cover-Pages.md
"""

from src.agents.dataroom.extractors.financial_extractor import _select_financial_pages


def _page(number, text, tables=None):
    return {"number": number, "text": text, "tables": tables or []}


PROSE = "The directors present their statement to the members together with the audited financial statements. " * 40
BALANCE_SHEET = (
    "STATEMENT OF FINANCIAL POSITION As at 31 December 2025\n"
    "Cash and cash equivalents 3,256,259 2,104,551\n"
    "Total assets 6,912,004 5,001,223\n"
    "Borrowings 3,453,388 2,950,000\n"
)
CASH_FLOW = "STATEMENT OF CASH FLOWS\nNet cash used in operating activities (1,640,271) (1,402,118)\n"


def test_statement_pages_survive_a_long_prose_front():
    pages = [_page(1, "Company Registration No. 2019 Annual Report")]
    pages += [_page(n, PROSE) for n in range(2, 9)]
    pages += [_page(9, BALANCE_SHEET, [[["Cash", "3,256,259"]]]), _page(10, CASH_FLOW)]
    pages += [_page(n, PROSE) for n in range(11, 20)]

    content, tables = _select_financial_pages(pages, budget=6000)

    assert "--- Page 1 ---" in content          # entity and period context kept
    assert "3,256,259" in content               # the balance sheet is sent
    assert "1,640,271" in content               # and the cash flow
    assert tables == [[["Cash", "3,256,259"]]]  # tables follow the chosen pages
    assert len(content) <= 6000 + 200           # within budget, page labels aside


def test_pages_stay_in_document_order():
    pages = [_page(1, "Cover"), _page(2, CASH_FLOW), _page(3, PROSE * 3), _page(4, BALANCE_SHEET)]
    content, _ = _select_financial_pages(pages, budget=1000)
    assert content.index("--- Page 2 ---") < content.index("--- Page 4 ---")


def test_a_short_document_is_sent_whole():
    pages = [_page(1, "Two Year Pro-forma"), _page(2, "Opex 240,000 per month")]
    content, _ = _select_financial_pages(pages)
    assert "--- Page 1 ---" in content and "--- Page 2 ---" in content


def test_merge_takes_the_latest_year_as_base_and_keeps_every_year():
    from src.agents.dataroom.extractors.financial_extractor import _merge_financial_extractions

    # Folder order puts FY2023 first; it must not become the base.
    fy23 = {"source_file": "AFS FY2023.pdf", "currency": "SGD", "cash_position": 1_000,
            "net_income": {"2022": -100, "2023": -200}, "notes": ["fy23 note"]}
    fy25 = {"source_file": "AFS FY2025.pdf", "currency": "SGD", "cash_position": 3_256_259,
            "net_income": {"2024": -1_556_469, "2025": -2_173_533}, "notes": ["fy25 note"]}
    fy24 = {"source_file": "AFS FY2024.pdf", "currency": "SGD", "cash_position": 2_000,
            "net_income": {"2023": -210, "2024": -2_710_000}, "notes": []}

    merged = _merge_financial_extractions([fy23, fy25, fy24])

    assert merged["cash"] == 3_256_259
    assert merged["net_income"] == {"2022": -100, "2023": -210,
                                    "2024": -1_556_469, "2025": -2_173_533}
    assert "fy25 note" in merged["extraction_notes"]
    assert "[AFS FY2023.pdf] fy23 note" in merged["extraction_notes"]

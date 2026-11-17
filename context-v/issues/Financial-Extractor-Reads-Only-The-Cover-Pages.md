---
title: "The Financial Extractor Reads Only the Cover Pages"
lede: "Audited financial statements run 30 to 60 pages, and the extractor hands the model the first 8,000 characters. That is the cover, the contents page and the directors' statement. The balance sheet, the cash flow and the notes never reach it, so a dataroom with five years of audited accounts comes back with no financial figures at all."
date_authored_initial_draft: 2026-11-13
date_authored_current_draft: 2026-11-13
date_authored_final_draft: null
date_first_published: null
date_last_updated: 2026-11-13
at_semantic_version: 0.0.0.1
usage_index: 1
publish: false
category: Specification
date_created: 2026-11-13
date_modified: 2026-11-13
tags: [Dataroom, Extraction, Financials, Truncation, Audited-Statements]
authors:
  - Michael Staton
augmented_with:
  - "Claude Code on Claude Opus 5.5"
status: Resolved
severity: High
type: Issues
---

# The Financial Extractor Reads Only the Cover Pages

## What happened

A dataroom-only run on a deal with five years of audited statements (FY2021 to FY2025, each audited with a clean opinion) produced a `3-financial-analysis.md` with **no key metrics**. The model said so itself, twice:

> "The content you provided appears to be incomplete - it only includes the cover pages and statement by directors, but cuts off before the actual financial statem…"

and the extraction notes read "Only cover pages, statement by directors, and partial auditor's report visible."

Cash, the loss for the year, shareholder loans and the going-concern note were all in the documents. None reached the model.

## Why

`src/agents/dataroom/extractors/financial_extractor.py`, in `_extract_financials_with_llm`:

```python
content_truncated = content[:8000] if len(content) > 8000 else content
```

`extract_from_pdf` reads every page, then this line keeps the first 8,000 characters. The tables are capped the same way: the first 3 tables, 30 rows each, which for an audited statement are tables from the front matter.

Measured on the deal that surfaced this:

| Document | Pages | Characters | First 8,000 chars end at | First primary statement |
|---|---|---|---|---|
| AFS FY2025 | 31 | 59,685 | page 6 | page 9 |
| AFS FY2024 | 58 | 92,630 | page 9 | page 11 |
| AFS FY2023 | 32 | 62,130 | page 8 | page 11 |

An audited statement is front-loaded with prose (directors' statement, auditor's report) and back-loaded with numbers. Truncating from the start is close to the worst possible choice for this document type.

## Fix direction

Select pages, not a prefix. Score each page for financial-statement signal (statement headings, figure density, notes on borrowings, convertibles, going concern and subsequent events), always keep the first page for entity and period context, and fill a character budget with the highest-scoring pages in their original order, each labelled with its page number. Take tables from the selected pages rather than the first three in the file.

The prompt also showed `"currency": "USD"` as its example, which invites a model to label Singapore-dollar statements as USD. It should ask for the currency the document reports in.

## Fix (2026-11-13)

- `extract_from_pdf` keeps each page with its own tables. `_select_financial_pages` keeps page 1, then the highest-scoring pages within `FINANCIAL_CONTENT_BUDGET` (40,000 characters), in document order, labelled `--- Page N ---`. Tables come from the chosen pages only (up to 12, 40 rows each).
- The prompt asks for the document's own currency and no conversion, says a gap in page numbers is not missing data, and asks for loans, convertibles, SAFEs, going concern and subsequent events in `notes`. `max_tokens` rose from 3,000 to 4,000.
- `tests/test_financial_page_selection.py` covers selection, ordering and the short-document path.

Checked on the FY2025 statement that surfaced this: it now returns SGD, cash of 3,256,259, the 2024 and 2025 losses, convertible notes of 3,453,388 with their maturity and extension, the restatement, the buyback and the going-concern basis. All match a hand read.

Still loose: the model files employee benefits under `ga_expenses` and consultancy under `sales_marketing_expenses`, and it derives `runway_months` from operating cash burn alone, ignoring capitalised development spend. Treat those fields as hints, not figures.

## Second finding: the merge keeps one document and drops the rest

`_merge_financial_extractions` takes `actuals[0]` as the base and reads every figure from it. Every other document contributes only a `Source:` line. Documents arrive in folder order, so with five audited years the record kept FY2023 (the first file by name) and discarded FY2024 and FY2025, the two that matter most. Fixing the page selection alone would still have produced a stale cash figure.

Fix: order actual-period extractions by the latest period they report (falling back to the year in the filename), take the latest as the base for point-in-time figures (cash, burn, runway, balance sheet, currency), merge each time series across all of them with newer documents winning a shared period, and keep every document's notes, labelled with its source.

## Related

- `context-v/issue-resolution/Extractors-Masked-Their-Own-LLM-Failures.md`: the same extractor, an earlier failure mode

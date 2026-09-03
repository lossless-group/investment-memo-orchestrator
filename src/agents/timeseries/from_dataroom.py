"""
Dataroom extraction → Observations → the transcriber.

The missing middle. Extractors already produce numbers against periods; the
transcriber already writes the grid. Nothing joined them, so every run so far
needed a hand-written adapter.

This transcribes. It does not compute, and it does not guess a period a document
did not state — an unanchored figure is dropped and the reason is recorded, which
is a better outcome than placing it on a grid it cannot honestly occupy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .periods import parse_period
from .transcriber import Observation, TimeSeriesTranscriber

# Financial fields that are series: {period: value}
_SERIES_FIELDS = ("revenue", "arr", "mrr", "gross_margin", "operating_expenses",
                  "net_income", "ebitda", "headcount")


def _one(source: str) -> str:
    """
    Extractors set `document_source` to a comma-joined list of every document
    they read. The transcriber's contract is one file per source document, so a
    joined string would silently merge three documents into one file. Take the
    first and say so in `source_detail`.
    """
    return (source or "").split(",")[0].strip() or "unknown"


def transcribe_dataroom(
    company: str,
    output_dir,
    extraction_results: Dict[str, Any],
    fiscal_year_start_month: Optional[int] = None,
    incorporation_date: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Write the company's stated series to ``<output_dir>/timeseries/``.

    Returns ``(summary, trace)`` — the transcriber's own summary, and a list of
    what was dropped and why, which is the more useful half on a thin dataroom.
    """
    trace: List[str] = []
    t = TimeSeriesTranscriber(company, output_dir,
                              fiscal_year_start_month=fiscal_year_start_month)

    # The charter is the strongest origin evidence there is, and month 01 belongs
    # to the company rather than to whichever document happens to state the
    # earliest number.
    if incorporation_date:
        period = parse_period(str(incorporation_date))
        if period:
            t.offer_origin("incorporation", period, "deal configuration",
                           f"incorporation_date {incorporation_date} as configured")
        else:
            trace.append(f"incorporation_date {incorporation_date!r} is not a date — ignored")

    fin = extraction_results.get("financials") or {}
    unit = fin.get("currency") or None
    src = _one(fin.get("document_source", ""))
    joined = (fin.get("document_source") or "").count(",")
    if joined:
        trace.append(f"financials: document_source names {joined + 1} documents; "
                     f"attributed to the first ({src})")

    for metric in _SERIES_FIELDS:
        series = fin.get(metric)
        if not isinstance(series, dict):
            continue
        for raw, value in series.items():
            period = parse_period(str(raw))
            if period is None:
                trace.append(f"financials.{metric}: {raw!r} is not a period — DROPPED")
                continue
            if value is None:
                continue
            t.add([Observation(period=period, metric=metric, value=float(value),
                               unit=unit, basis="actual", source_document=src,
                               source_detail=f"{metric} stated for {raw}")])

    # Projections arrive as {metric: {period: value}} or {period: {metric: value}},
    # and frequently as "Year 1"…"Year 4" — relative to an anchor no document
    # states. Those are dropped rather than pinned to a guessed start year.
    for outer, inner in (fin.get("projections") or {}).items():
        if not isinstance(inner, dict):
            continue
        for key, value in inner.items():
            metric, raw = (outer, key) if parse_period(str(key)) else (key, outer)
            period = parse_period(str(raw))
            if period is None:
                trace.append(f"projection {metric} {raw!r}: relative to an unstated "
                             f"anchor — DROPPED, no period can be evidenced")
                continue
            if value is None:
                continue
            t.add([Observation(period=period, metric=str(metric), value=float(value),
                               unit=unit, basis="projection", source_document=src,
                               source_detail=f"projection for {raw}")])

    # The cap table is holder-period, not company-period: its own file, its own
    # dimensions, joined on the count when someone wants it.
    cap = extraction_results.get("cap_table") or {}
    as_of = parse_period(str(cap.get("as_of_date"))) if cap.get("as_of_date") else None
    if cap and as_of is None:
        trace.append(f"cap table: as_of_date {cap.get('as_of_date')!r} gives no period — DROPPED")
    elif as_of:
        cap_src = _one(cap.get("document_source", "cap_table"))
        t.declare_source_date(cap_src, as_of.first_day)
        for holder in cap.get("shareholders") or []:
            if not isinstance(holder, dict):
                continue
            for field, unit_ in (("shares", "shares"), ("ownership_percentage", "pct")):
                v = holder.get(field)
                if v is None:
                    continue
                t.add([Observation(
                    period=as_of, metric=field, value=float(v), unit=unit_,
                    basis="actual",
                    dimensions={"holder": str(holder.get("name", "?")),
                                "security_class": str(holder.get("share_class", "?"))},
                    source_document=cap_src, source_detail="cap table row")])

        for safe in cap.get("safes") or []:
            if not isinstance(safe, dict):
                continue
            for field in ("amount_invested", "valuation_cap", "discount_rate"):
                v = safe.get(field)
                if v is None:
                    continue
                t.add([Observation(
                    period=as_of, metric=field, value=float(v),
                    unit=unit if field != "discount_rate" else "pct",
                    basis="actual",
                    dimensions={"holder": str(safe.get("investor_name", "?"))},
                    source_document=cap_src, source_detail="SAFE schedule row")])

    # An executed instrument dates the company's first financing.
    for doc in extraction_results.get("legal_docs") or []:
        if not isinstance(doc, dict) or not doc.get("is_executed"):
            continue
        raw = doc.get("effective_date") or doc.get("document_date")
        period = parse_period(str(raw)) if raw else None
        if period:
            t.offer_origin("first_financing_close", period,
                           _one(doc.get("document_source", "")),
                           "earliest executed instrument")

    if not t.observations:
        trace.append("nothing stated against a period — no grid written")
        return {"company": company, "files": [], "note": "no observations"}, trace

    return t.write(), trace

"""
Company Timeline — the origin, and the counts derived from it

One company, one origin, every series indexed from it.

**The origin belongs to the company, not to the document.** This is the single
thing most easily got wrong and the whole reason the count exists. A spreadsheet
beginning January 2024 does not restart at ``01``; with a February 2023 origin it
lands at ``month_count`` 12. That is what lets two spreadsheets covering
different spans, a deck's chart, and a board pack's KPI table describe the same
company at the same offsets — matched on the count rather than reconciled by
hand.

Three parallel grids, all from the same origin, each beginning at the period that
*contains* it so calendar alignment survives: a February origin sits inside
2023-Q1, and that quarter is ``quarter_count`` 01.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from .periods import Period

# How an origin was established, best evidence first.
ORIGIN_BASES = (
    "incorporation",          # a charter or certificate — verifiable, comparable
    "founding_claim",         # stated on a deck; the company's own claim
    "first_financing_close",  # earliest executed instrument
    "earliest_data_point",    # earliest period any series states
)

_CONFIDENCE_BY_BASIS = {
    "incorporation": "high",
    "founding_claim": "medium",
    "first_financing_close": "medium",
    "earliest_data_point": "medium",
}


@dataclass
class Origin:
    """Month 01, and the evidence that put it there."""

    year: int
    month: int
    basis: str
    confidence: str = "medium"
    source_document: Optional[str] = None
    detail: Optional[str] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def year_month(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def quarter(self) -> int:
        return (self.month - 1) // 3 + 1

    def as_yaml_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.year_month,
            "origin_basis": self.basis,
            "origin_confidence": self.confidence,
            "origin_evidence": {
                "source_document": self.source_document,
                "detail": self.detail,
            },
            "alternatives_considered": self.alternatives,
            "notes": self.notes,
        }


@dataclass
class Timeline:
    """
    A company's timeline: one origin, and the count arithmetic that follows.

    Fiscal years shift only the quarterly and annual grids. Months are months;
    the monthly grid is unaffected by a fiscal calendar.
    """

    origin: Origin
    fiscal_year_start_month: Optional[int] = None   # None means calendar

    # --- counts -----------------------------------------------------------

    def month_count(self, period: Period) -> int:
        """1-based month index from the origin. Can be <= 0 before it."""
        return ((period.year - self.origin.year) * 12
                + (period.first_day.month - self.origin.month) + 1)

    def quarter_count(self, period: Period) -> int:
        """1-based quarter index, counting from the quarter containing the origin."""
        q = period.quarter or ((period.first_day.month - 1) // 3 + 1)
        return (period.year - self.origin.year) * 4 + (q - self.origin.quarter) + 1

    def year_count(self, period: Period) -> int:
        return period.year - self.origin.year + 1

    def count_for(self, period: Period) -> int:
        """The count matching the period's own grain."""
        if period.grain == "annual":
            return self.year_count(period)
        if period.grain == "quarterly":
            return self.quarter_count(period)
        return self.month_count(period)

    # --- calendar columns -------------------------------------------------

    def columns_for(self, period: Period) -> Dict[str, Any]:
        """
        Every time column for one period, ISO throughout.

        Deliberately redundant. Each column exists because something downstream
        wants it as a column rather than an expression — `half_id` groups a chart
        axis, `quarter_id` joins to quarterly financials, `year` and `month` sort
        in a spreadsheet without parsing. A reader with a CSV and no code can do
        all of it.
        """
        month = period.first_day.month
        quarter = period.quarter or ((month - 1) // 3 + 1)
        half = 1 if quarter <= 2 else 2
        day = period.day or 1

        # Every count and date part is a zero-padded string. Unpadded values sort
        # lexically as 1, 10, 11, 12, 2, 3 in every spreadsheet and naive join,
        # silently reordering a series while the chart still looks fine.
        columns: Dict[str, Any] = {
            "month_count": f"{self.month_count(period):02d}",
            "quarter_count": f"{self.quarter_count(period):02d}",
            "year_count": f"{self.year_count(period):02d}",
            "date": period.iso_date or f"{period.year:04d}-{month:02d}-{day:02d}",
            "YYYY": f"{period.year:04d}",
            "HH": f"H{half}",
            "QQ": f"Q{quarter}",
            "MM": f"{month:02d}",
            "DD": f"{day:02d}",
            "FM": self.fiscal_month(period),
            "year_month": f"{period.year:04d}-{month:02d}",
            "year_quarter": f"{period.year:04d}-Q{quarter}",
            "year_half": f"{period.year:04d}-H{half}",
            "quarter_id": f"{period.year:04d}Q{quarter}",     # prior-art spelling
            "half_id": f"{period.year:04d}H{half}",           # prior-art spelling
            "timeframe_id": (f"{period.year:04d}-H{half}-Q{quarter}-"
                             f"{self.month_count(period):02d}"),
        }

        # Drop columns finer than the period's own grain rather than inventing
        # precision the source never stated. A half is finer than a year, so an
        # annual row does not claim one.
        if period.grain == "annual":
            for key in ("month_count", "quarter_count", "date", "year_month",
                        "year_quarter", "quarter_id", "QQ", "MM", "DD", "FM",
                        "timeframe_id", "year_half", "half_id", "HH"):
                columns[key] = None
        elif period.grain == "quarterly":
            for key in ("month_count", "date", "year_month",
                        "MM", "DD", "FM", "timeframe_id"):
                columns[key] = None

        return columns

    def fiscal_month(self, period: Period) -> Optional[str]:
        """
        The month's ordinal position within the fiscal year, zero-padded.

        One column, not a fiscal calendar. With an April start, April is ``01``
        and the following March is ``12``. Fiscal quarter is ``ceil(FM/3)`` and
        fiscal year follows from ``FM`` and ``YYYY`` — both are the analyst's to
        compute, not this agent's to assert.

        Null on a calendar year, or when no fiscal start has been established.
        """
        if not self.fiscal_year_start_month:
            return None
        offset = (period.first_day.month - self.fiscal_year_start_month) % 12
        return f"{offset + 1:02d}"

    # --- density ----------------------------------------------------------

    def month_range(self, last: Period) -> List[Period]:
        """
        Every month from the origin through ``last``, with no gaps.

        Density is what makes lag operators correct. ``pct_change(12)`` means
        "the row twelve above"; one skipped month shifts every comparison after
        it and the result still looks plausible. Callers fill the missing ones
        with null values and ``is_gap_fill``.
        """
        periods: List[Period] = []
        year, month = self.origin.year, self.origin.month
        end = (last.year, last.first_day.month)
        while (year, month) <= end:
            periods.append(Period(year=year, month=month, grain="monthly",
                                  raw=f"{year:04d}-{month:02d}"))
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return periods

    def quarter_range(self, last: Period) -> List[Period]:
        """Every quarter from the origin's own quarter through ``last``."""
        periods: List[Period] = []
        year = self.origin.year
        quarter = (self.origin.month - 1) // 3 + 1
        end_q = last.quarter or ((last.first_day.month - 1) // 3 + 1)
        while (year, quarter) <= (last.year, end_q):
            periods.append(Period(year=year, quarter=quarter, grain="quarterly",
                                  raw=f"{year:04d}-Q{quarter}"))
            quarter += 1
            if quarter > 4:
                year, quarter = year + 1, 1
        return periods

    def year_range(self, last: Period) -> List[Period]:
        """Every year from the origin's own year through ``last``."""
        return [Period(year=y, grain="annual", raw=str(y))
                for y in range(self.origin.year, last.year + 1)]

    def range_for(self, last: Period, grain: str) -> List[Period]:
        """The dense span for whichever grid is being written."""
        if grain == "annual":
            return self.year_range(last)
        if grain == "quarterly":
            return self.quarter_range(last)
        return self.month_range(last)


# =============================================================================
# Establishing an origin
# =============================================================================

def establish_origin(
    candidates: Sequence[Dict[str, Any]],
) -> Optional[Origin]:
    """
    Choose the company's origin from everything the archive offers.

    Args:
        candidates: Dicts of ``{basis, period, source_document, detail}`` where
            ``period`` is a Period. Anything the extractors could evidence.

    The rule: take the **earliest** period, because month 01 is the earliest
    month the archive can evidence. Where two candidates name the same month,
    prefer the stronger basis — a charter over a deck's claim.

    An incorporation date earlier than the first data point still wins on
    earliness, and that is intended: a company incorporated in 2019 whose
    earliest data is 2023 has 2023 landing at ``month_count`` 46, which says
    plainly that three and a half years are undocumented.
    """
    usable = [c for c in candidates if c.get("period")]
    if not usable:
        return None

    def rank(candidate: Dict[str, Any]):
        period: Period = candidate["period"]
        basis = candidate.get("basis", "earliest_data_point")
        strength = ORIGIN_BASES.index(basis) if basis in ORIGIN_BASES else len(ORIGIN_BASES)
        return (period.first_day, strength)

    ordered = sorted(usable, key=rank)
    chosen = ordered[0]

    # A company cannot have a period before it existed. An annual figure for the
    # year of incorporation begins on 1 January and so sorts earlier than a
    # February charter — but it is a statement about the year containing
    # incorporation, not evidence of earlier existence. Where a coarser period
    # merely *contains* the incorporation date, the charter wins; where a source
    # genuinely evidences activity before it, earliest still wins and the
    # divergence stays visible in `alternatives_considered`.
    incorporations = [c for c in usable if c.get("basis") == "incorporation"]
    if incorporations and chosen.get("basis") != "incorporation":
        inc = min(incorporations, key=lambda c: c["period"].first_day)
        inc_day = inc["period"].first_day
        if chosen["period"].first_day <= inc_day <= chosen["period"].last_day:
            chosen = inc
            ordered = [inc] + [c for c in ordered if c is not inc]
    period: Period = chosen["period"]
    basis = chosen.get("basis", "earliest_data_point")

    origin = Origin(
        year=period.year,
        month=period.first_day.month,
        basis=basis,
        confidence=_CONFIDENCE_BY_BASIS.get(basis, "low"),
        source_document=chosen.get("source_document"),
        detail=chosen.get("detail") or f"parsed from {period.raw!r}",
        alternatives=[
            {
                "basis": c.get("basis"),
                "date": c["period"].year_month or str(c["period"].year),
                "source": c.get("source_document"),
            }
            for c in ordered[1:]
        ],
    )

    if period.ambiguous:
        origin.confidence = "low"
        origin.notes.append(
            f"origin parsed from an ambiguous date form ({period.raw!r}); "
            f"verify before relying on any count"
        )

    return origin

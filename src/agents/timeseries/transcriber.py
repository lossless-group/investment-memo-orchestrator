"""
Time-Series Transcriber

The agent that owns the grid. Extractors hand it observations; it establishes the
company's origin, computes the counts, and writes tidy CSVs.

It exists so the convention lives in one place. A financial extractor, a KPI
extractor, a cap-table extractor, and a chart collector all produce numbers over
time, and if each writes its own files they will each get the convention slightly
wrong in a different way — a different origin, a different date format, a
different idea of what a row is. Handing observations to one agent makes that
impossible.

What it does NOT do is analysis. It writes collected data in a shape that makes
analysis easy: no reconciliation, no filling, no metric-name mapping, no derived
metrics. Those are judgments, they belong where a person can see and revise them,
and doing any of them here would make an inference indistinguishable from a
source's own claim.

The rules it enforces live in
``context-v/Use-Tidyverse-Conventions-to-Normalize-Timeseries-Data-Across-Files.md``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import yaml

from .periods import Period, parse_period
from .timeline import Origin, Timeline, establish_origin

AGENT_SIGNATURE = "time-series_transcriber"

# How a value came to be known. Never lost — plotting a projection as history is
# the worst failure available to this system.
BASES = ("actual", "projection", "restated", "chart_read")

# Column order. Time first, then the observation, then provenance — so a person
# opening the CSV sees when, then what, then where it came from.
TIME_COLUMNS = [
    "month_count", "quarter_count", "year_count",
    "date", "YYYY", "HH", "QQ", "MM", "DD", "FM",
    "year_month", "year_quarter", "year_half",
    "quarter_id", "half_id", "timeframe_id",
]
OBSERVATION_COLUMNS = ["metric", "value", "unit", "basis"]
# No `is_rolled_up`: nothing here is rolled up. Derived rows are the
# data-analyst agent's output, in the analyst's own directory.
PROVENANCE_COLUMNS = [
    "is_gap_fill", "source_document", "source_detail", "source_raw_period",
]

# The three grids the spec defines. A daily period is a monthly-grid observation
# that happens to know its day — it does not get a grid of its own, and the day it
# states survives in `date`, `DD`, and `source_raw_period`.
_GRID_GRAIN = {"daily": "monthly"}


def grid_grain(grain: str) -> str:
    """Which of the three grids a stated periodicity is written to."""
    return _GRID_GRAIN.get(grain, grain)


# Counts finer than a grid's own grain are meaningless on it.
_DROP_BY_GRAIN = {
    "quarterly": {"month_count", "date", "year_month", "MM", "DD", "FM", "timeframe_id"},
    "annual": {"month_count", "quarter_count", "date", "year_month", "year_quarter",
               "quarter_id", "QQ", "MM", "DD", "FM", "timeframe_id",
               "year_half", "half_id", "HH"},
}


@dataclass
class Observation:
    """
    One number, at one period, from one document.

    This is the unit every extractor emits. A spreadsheet column produces one per
    month; a chart with a time axis produces one per plotted point; a single
    statistic on a slide produces exactly one. The source is provenance, not
    structure.
    """

    period: Period
    metric: str                      # as the SOURCE names it — never normalized
    value: Optional[float]
    unit: Optional[str] = None
    basis: str = "actual"
    dimensions: Dict[str, str] = field(default_factory=dict)   # holder, product, department…
    source_document: str = ""
    source_detail: str = ""
    is_gap_fill: bool = False


@dataclass
class SeriesFile:
    """One written CSV and what a reader needs to know about it."""

    path: Path
    grain: str
    rows: int
    metrics: List[str]
    gaps: int
    ambiguous_periods: int
    source_document: str


class TimeSeriesTranscriber:
    """Transcribes one company's stated series onto the grids. Computes nothing."""

    def __init__(
        self,
        company: str,
        output_dir: str | Path,
        *,
        fiscal_year_start_month: Optional[int] = None,
    ) -> None:
        self.company = company
        self.output_dir = Path(output_dir)
        self.fiscal_year_start_month = fiscal_year_start_month
        self.observations: List[Observation] = []
        self.origin_candidates: List[Dict[str, Any]] = []
        self.timeline: Optional[Timeline] = None
        # Set by callers who know a source document's own date. Without one the
        # file is named `undated_…` rather than given a stamp it cannot support.
        self.source_dates: Dict[str, date] = {}
        self.undated_sources: List[str] = []

    # --- collection -------------------------------------------------------

    def add(self, observations: Iterable[Observation]) -> None:
        """Take observations from an extractor. Order does not matter."""
        for obs in observations:
            if obs.period is None:
                continue
            self.observations.append(obs)

    def offer_origin(
        self, basis: str, period: Optional[Period],
        source_document: str = "", detail: str = "",
    ) -> None:
        """
        Offer evidence of when the company began.

        A legal extractor offers an incorporation date; a deck offers a founding
        claim. The earliest offer wins, so an extractor should offer whatever it
        can evidence and let this agent choose.
        """
        if period:
            self.origin_candidates.append({
                "basis": basis, "period": period,
                "source_document": source_document, "detail": detail,
            })

    def declare_source_date(self, source_document: str, when: date) -> None:
        """
        Tell the analyst when a source document is from.

        Preferred over the ``YYYYMMDD_`` filename prefix, because a caller that
        opened the workbook may have read an as-of date the filename never had.
        Without either, the file is named ``undated_…`` and listed as such —
        never given a plausible-looking stamp it cannot support.
        """
        self.source_dates[source_document] = when

    # --- writing ----------------------------------------------------------

    def write(self) -> Dict[str, Any]:
        """
        Establish the origin, index everything, and write the files.

        Returns a summary; raises nothing for an empty corpus — a company with no
        numbers gets a timeline saying so, which is more useful than an error.
        """
        if not self.observations and not self.origin_candidates:
            return {"company": self.company, "files": [], "note": "no observations collected"}

        # The earliest period any observation states is always an origin
        # candidate, so a company with data but no filings still gets an origin.
        earliest = min((o.period for o in self.observations),
                       key=lambda p: p.first_day, default=None)
        if earliest:
            self.offer_origin("earliest_data_point", earliest,
                              source_document=next(
                                  (o.source_document for o in self.observations
                                   if o.period is earliest), ""),
                              detail=f"earliest period observed ({earliest.raw!r})")

        origin = establish_origin(self.origin_candidates)
        if origin is None:
            return {"company": self.company, "files": [],
                    "note": "no origin could be established; no counts emitted"}

        self.timeline = Timeline(origin, self.fiscal_year_start_month)
        series_dir = self.output_dir / "timeseries"
        series_dir.mkdir(parents=True, exist_ok=True)

        # One file per (source document, grid, dimension shape). Splitting on
        # source is what keeps a file equal to what one document said, and what
        # makes juxtaposition a concat rather than a reconciliation.
        grouped: Dict[tuple, List[Observation]] = {}
        for obs in self.observations:
            key = (obs.source_document, grid_grain(obs.period.grain),
                   tuple(sorted(obs.dimensions)))
            grouped.setdefault(key, []).append(obs)

        written: List[SeriesFile] = []
        for (source, grain, dims), rows in sorted(grouped.items()):
            written.append(self._write_series(series_dir, source, grain, list(dims), rows))

        self._write_timeline(origin)
        self._write_readme(series_dir, written)

        return {
            "company": self.company,
            "origin": origin.year_month,
            "origin_basis": origin.basis,
            "origin_confidence": origin.confidence,
            "files": [str(f.path) for f in written],
            "observations": len(self.observations),
            "gap_rows": sum(f.gaps for f in written),
            "undated_sources": sorted(set(self.undated_sources)),
        }

    def _write_series(
        self, series_dir: Path, source: str, grain: str,
        dimensions: List[str], observations: List[Observation],
    ) -> SeriesFile:
        """Write one tidy long CSV."""
        assert self.timeline is not None

        columns = (
            [c for c in TIME_COLUMNS if c not in _DROP_BY_GRAIN.get(grain, set())]
            + dimensions + OBSERVATION_COLUMNS + PROVENANCE_COLUMNS
        )

        count_column = {"annual": "year_count", "quarterly": "quarter_count"}.get(
            grain, "month_count")

        rows: List[Dict[str, Any]] = []
        for obs in observations:
            record = self.timeline.columns_for(obs.period)
            record.update({d: obs.dimensions.get(d, "") for d in dimensions})
            record.update({
                "metric": obs.metric,
                "value": obs.value,
                "unit": obs.unit,
                "basis": obs.basis,
                "is_gap_fill": obs.is_gap_fill,
                "source_document": obs.source_document,
                "source_detail": obs.source_detail,
                "source_raw_period": obs.period.raw,
            })
            row = {c: record.get(c) for c in columns}
            row["_n"] = self.timeline.count_for(obs.period)
            rows.append(row)

        # Density. Every period from count 01 to the last one with data gets a
        # row, so `month_count` is an index and not merely a label: pct_change(12)
        # means "the row twelve above", and one skipped period shifts every
        # comparison after it while still looking plausible.
        gaps = 0
        last = max(observations, key=lambda o: o.period.first_day).period
        # Compare and sort on the integer count, never the padded string:
        # "100" sorts before "99" lexically.
        present = {r["_n"] for r in rows}
        for period in self.timeline.range_for(last, grain):
            count = self.timeline.count_for(period)
            if count in present:
                continue
            gaps += 1
            record = self.timeline.columns_for(period)
            record.update({d: "" for d in dimensions})
            record.update({
                "metric": None, "value": None, "unit": None, "basis": None,
                "is_gap_fill": True,
                "source_document": source, "source_detail": "",
                "source_raw_period": None,
            })
            row = {c: record.get(c) for c in columns}
            row["_n"] = count
            rows.append(row)

        rows.sort(key=lambda r: (r["_n"], str(r.get("metric") or "")))

        path = series_dir / self._filename(source, grain, dimensions)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        return SeriesFile(
            path=path, grain=grain, rows=len(rows),
            metrics=sorted({o.metric for o in observations}),
            gaps=gaps,
            ambiguous_periods=sum(1 for o in observations if o.period.ambiguous),
            source_document=source,
        )

    def _filename(self, source: str, grain: str, dimensions: List[str]) -> str:
        """
        ``YYYYMMDD_Company_Thing--Qualifier--Grain.csv``.

        The date is the **source document's** date: whatever the caller declared
        via ``declare_source_date``, else the ``YYYYMMDD_`` prefix the archive
        rename put on the filename. Two projection files a year apart then sort
        beside each other and their divergence is visible from the listing alone.

        A source with neither is named ``undated_…`` and reported in the run
        summary and the README. It used to be stamped ``00000000``, which sorts
        like a date, reads like a date, and is not one.
        """
        import re

        stem = Path(source).stem if source else "Unknown"
        declared = self.source_dates.get(source)
        if declared:
            stamp = declared.strftime("%Y%m%d")
        else:
            stamp_match = re.match(r"(\d{8})", stem)
            if stamp_match:
                stamp = stamp_match.group(1)
            else:
                stamp = "undated"
                self.undated_sources.append(source)

        thing = re.sub(r"^\d{8}_", "", stem)
        thing = re.sub(rf"^{re.escape(self.company)}_", "", thing) or "Series"
        thing = re.sub(r"[^A-Za-z0-9-]+", "-", thing).strip("-")[:60] or "Series"

        # A source already named for its grain must not gain a second one:
        # "…Financials--Quarterly" + "--Quarterly" reads as a mistake.
        grain_tag = grain.capitalize()
        if thing.lower().endswith(grain_tag.lower()):
            thing = thing[: -len(grain_tag)].rstrip("-")

        if dimensions:
            pretty = "-".join(
                "".join(part.capitalize() for part in d.split("_")) for d in dimensions
            )
            dimension_tag = f"--By-{pretty}"
        else:
            dimension_tag = ""

        return f"{stamp}_{self.company}_{thing}{dimension_tag}--{grain_tag}.csv"

    def _write_timeline(self, origin: Origin) -> None:
        payload = {
            "company": self.company,
            **origin.as_yaml_dict(),
            "fiscal_year_start_month": self.fiscal_year_start_month,
            "established_by": AGENT_SIGNATURE,
            "established_on": date.today().isoformat(),
        }
        (self.output_dir / "timeline.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    def _write_readme(self, series_dir: Path, files: Sequence[SeriesFile]) -> None:
        """
        What a CSV cannot carry: which periods are gaps, which rows were rolled
        up, and which document fed each file.
        """
        assert self.timeline is not None
        origin = self.timeline.origin

        lines = [
            f"# Time series — {self.company}",
            "",
            f"Origin (`{'month_count'} 01`): **{origin.year_month}**, "
            f"from {origin.basis} ({origin.confidence} confidence).",
            "",
            "Every file below indexes from that same origin, so a period in one "
            "file carries the same count as the same period in another. Join on "
            "the count.",
            "",
            "These are collected observations, not a model. Nothing is "
            "reconciled: where two documents disagree about a period, both are "
            "present and the divergence is the finding.",
            "",
            "| File | Grain | Rows | Metrics | Gaps | Ambiguous dates |",
            "|---|---|---|---|---|---|",
        ]
        for f in files:
            metrics = ", ".join(f.metrics[:5]) + ("…" if len(f.metrics) > 5 else "")
            lines.append(
                f"| `{f.path.name}` | {f.grain} | {f.rows} | {metrics} | "
                f"{f.gaps} | {f.ambiguous_periods} |"
            )

        lines += [
            "",
            "`Gaps` counts rows carrying `is_gap_fill: true` — periods no source "
            "described, written as null rows so the count stays an index. A "
            "missing row would be a wrong answer; a visible null row is a known "
            "gap.",
        ]

        # Metrics are named as their source names them and are never renamed, so
        # a reader filtering on one label can silently miss the same series under
        # another. "Total Revenue" in a historical sheet and "Revenue" in the
        # forecast beside it is the ordinary case, not an exotic one. Naming the
        # asymmetry is this file's job; deciding the two are the same thing is
        # not — see context-v/reminders/Normalize-Labels-Gradually.md.
        by_grain: Dict[str, List[SeriesFile]] = {}
        for f in files:
            by_grain.setdefault(f.grain, []).append(f)

        asymmetric = []
        for grain, group in sorted(by_grain.items()):
            if len(group) < 2:
                continue
            for f in group:
                elsewhere = set().union(*(set(o.metrics) for o in group if o is not f))
                only_here = sorted(set(f.metrics) - elsewhere)
                if only_here:
                    asymmetric.append((grain, f, only_here, len(set(f.metrics) & elsewhere)))

        if asymmetric:
            lines += [
                "", "## Metrics that are not in every file of a grain", "",
                "Each metric is named as its own source named it. Filtering a "
                "concatenated frame on one label can therefore return a partial "
                "series without erroring — a historical sheet saying "
                "`Total Revenue` beside a forecast saying `Revenue` is the "
                "ordinary case, not an exotic one.", "",
                "`shared` counts labels this file has in common with its siblings "
                "at the same grain. A file sharing none of them is probably just "
                "a different subject; a file sharing many and diverging on a few "
                "is where a partial filter hides.", "",
            ]
            for grain, f, only_here, shared_n in asymmetric:
                shown = ", ".join(f"`{m}`" for m in only_here[:12])
                more = f" …and {len(only_here) - 12} more" if len(only_here) > 12 else ""
                lines.append(
                    f"- **{grain}** · `{f.path.name}` — {shared_n} shared; "
                    f"only here: {shown}{more}")

        if self.undated_sources:
            lines += [
                "", "## Undated sources", "",
                "These documents stated no date and none was declared for them, "
                "so their files are named `undated_…` and do not sort into the "
                "archive's chronology. A date is not invented for them.", "",
            ]
            for src in sorted(set(self.undated_sources)):
                lines.append(f"- `{src}`")

        flagged = [f for f in files if f.ambiguous_periods]
        if flagged:
            lines += ["", "## Ambiguous dates", "",
                      "Periods parsed from a form that could mean two dates — a "
                      "two-digit year, or a slash form with no column to settle "
                      "day-first from. `source_raw_period` holds what the "
                      "document said.", ""]
            for f in flagged:
                lines.append(f"- `{f.path.name}` — {f.ambiguous_periods} row(s)")

        if origin.notes:
            lines += ["", "## Origin notes", ""] + [f"- {n}" for n in origin.notes]

        lines += ["", "## Reading these", "",
                  "```python", "import pandas as pd, glob",
                  "df = pd.concat([pd.read_csv(f).assign(file=f) "
                  "for f in glob.glob('*--Monthly.csv')])", "",
                  "# wide, for a chart",
                  "df.pivot(index=['month_count','year_month'], columns='metric', values='value')",
                  "", "# juxtapose two documents on the same metric",
                  "df[df.metric=='revenue'].pivot(index='month_count', "
                  "columns='source_document', values='value')", "```", ""]

        (series_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")

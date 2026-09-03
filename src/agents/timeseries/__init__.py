"""
Time-Series Transcriber

Owns the company timeline and the tidy grid every numeric series lands on.

Extractors do not write time series themselves. They emit ``Observation``
records and offer origin evidence; this package establishes one origin per
company, indexes each stated period against it, and writes the files.

It **transcribes**. It performs no arithmetic — no roll-up, no fill, no
conversion, no derived metric. A computed number has no document to point back
to, and once written it is indistinguishable from a transcribed one. Roll-ups
and reconciliation belong to the data-analyst agent, which reads these files and
writes elsewhere.

The conventions are stated in
``context-v/Use-Tidyverse-Conventions-to-Normalize-Timeseries-Data-Across-Files.md``.
"""

from .periods import Period, parse_period, parse_period_series, infer_day_first
from .timeline import Origin, Timeline, establish_origin, ORIGIN_BASES
from .transcriber import Observation, TimeSeriesTranscriber, BASES

__all__ = [
    "Period", "parse_period", "parse_period_series", "infer_day_first",
    "Origin", "Timeline", "establish_origin", "ORIGIN_BASES",
    "Observation", "TimeSeriesTranscriber", "BASES",
]

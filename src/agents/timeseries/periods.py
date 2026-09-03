"""
Period Parsing — any source format in, ISO 8601 out

Source documents spell periods every way there is. A spreadsheet header reads
``Feb-23``, a deck axis reads ``Q1'24``, a board pack reads ``2/1/2023``, an
audited statement reads ``FY2024``. None of those forms may survive into a
written file.

**This is disambiguation, not tidiness.** ``03-04-2023`` is March 4th to an
American and April 3rd to everyone else, and a two-digit year loses its century.
Whoever reads the output later has no access to the workbook it came from, so
anything written has to already be unambiguous.

Every parse records the string it came from. The source's spelling is not data —
but *which* string produced a period is provenance, and a reader needs it to
check an ambiguous parse rather than trust it.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

# Grains, coarsest last. A period knows which grid it belongs on.
GRAINS = ("daily", "monthly", "quarterly", "annual")


@dataclass(frozen=True)
class Period:
    """One parsed period: what it is, how coarse, and what text produced it."""

    year: int
    month: Optional[int] = None       # None at annual grain
    day: Optional[int] = None         # None above daily grain
    quarter: Optional[int] = None     # set at quarterly grain
    grain: str = "monthly"
    raw: str = ""                     # the source string, verbatim
    ambiguous: bool = False           # true when the form could mean two dates

    # --- ISO renderings. These are the only forms that reach a file. ---

    @property
    def year_month(self) -> Optional[str]:
        return f"{self.year:04d}-{self.month:02d}" if self.month else None

    @property
    def iso_date(self) -> Optional[str]:
        if not self.month:
            return None
        return f"{self.year:04d}-{self.month:02d}-{(self.day or 1):02d}"

    @property
    def year_quarter(self) -> str:
        q = self.quarter or ((self.month - 1) // 3 + 1 if self.month else 1)
        return f"{self.year:04d}-Q{q}"

    @property
    def year_half(self) -> str:
        q = self.quarter or ((self.month - 1) // 3 + 1 if self.month else 1)
        return f"{self.year:04d}-H{1 if q <= 2 else 2}"

    @property
    def last_day(self) -> date:
        """Final day of the period. Lets a caller ask whether a date falls inside it."""
        import calendar

        if self.grain == "annual":
            return date(self.year, 12, 31)
        if self.grain == "quarterly":
            end_month = (self.quarter or 1) * 3
            return date(self.year, end_month, calendar.monthrange(self.year, end_month)[1])
        month = self.month or 1
        if self.grain == "daily" and self.day:
            return date(self.year, month, self.day)
        return date(self.year, month, calendar.monthrange(self.year, month)[1])

    @property
    def first_day(self) -> date:
        """First day of the period, for arithmetic against an origin."""
        if self.grain == "annual":
            return date(self.year, 1, 1)
        if self.grain == "quarterly":
            return date(self.year, ((self.quarter or 1) - 1) * 3 + 1, 1)
        return date(self.year, self.month or 1, self.day or 1)


# =============================================================================
# Month names
# =============================================================================

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTHS.update({"sept": 9})


def _year(value: str) -> int:
    """
    Expand a two-digit year.

    A pivot is unavoidable here and it is a guess. 70 is the conventional break
    and it is recorded as ambiguity by the caller, not hidden.
    """
    n = int(value)
    if n >= 100:
        return n
    return 1900 + n if n >= 70 else 2000 + n


# =============================================================================
# Patterns, most specific first
# =============================================================================
#
# Order matters. "Q1 2024" must be tried before anything that would read the
# digits as a month, and a four-digit year must be tried before a two-digit one.

_PATTERNS: List[Tuple[str, str]] = [
    # --- Quarterly ---
    (r"^(?:FY)?(\d{4})[-\s]?Q([1-4])$", "yq"),          # 2024-Q1, FY2024Q1
    (r"^Q([1-4])[-\s']?(\d{2,4})$", "qy"),               # Q1 2024, Q1'24
    (r"^(\d{4})Q([1-4])$", "yq"),                        # 2024Q1
    # --- Annual ---
    (r"^(?:FY|CY)?(\d{4})$", "y"),                       # 2024, FY2024
    # --- Monthly, ISO ---
    (r"^(\d{4})-(\d{1,2})$", "ym"),                      # 2023-02
    # --- Daily, ISO ---
    (r"^(\d{4})-(\d{1,2})-(\d{1,2})$", "ymd"),           # 2023-02-01
    # --- Month names ---
    (r"^([A-Za-z]{3,9})\.?[-\s'](\d{2,4})$", "My"),      # Feb-23, February 2023
    (r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", "Mdy"),   # Feb 1, 2023
    (r"^(\d{1,2})[-\s]([A-Za-z]{3,9})\.?[-\s](\d{2,4})$", "dMy"),  # 1-Feb-23
    (r"^(\d{4})[-\s]([A-Za-z]{3,9})$", "yM"),            # 2023-Feb
    # --- Slash forms. Ambiguous by construction; see below. ---
    (r"^(\d{1,2})/(\d{4})$", "my"),                      # 2/2023
    (r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", "mdy"),         # 2/1/2023
    (r"^(\d{4})/(\d{1,2})$", "ym"),                      # 2023/02
]


def parse_period(raw: str, prefer_day_first: bool = False) -> Optional[Period]:
    """
    Parse one period string. Returns None when nothing recognizable is there.

    Args:
        raw: The source string, e.g. a spreadsheet header or an axis label.
        prefer_day_first: Read ``d/m/y`` rather than ``m/d/y`` for slash forms.
            A document is internally consistent, so this belongs to the
            document, not to the value — see ``infer_day_first``.
    """
    if not raw:
        return None

    text = re.sub(r"\s+", " ", str(raw)).strip().strip(",;")
    text = re.sub(r"^(?:as of|period ending|month(?: of)?|ending)\s+", "", text, flags=re.I)
    if not text:
        return None

    for pattern, shape in _PATTERNS:
        m = re.match(pattern, text, re.IGNORECASE)
        if not m:
            continue
        built = _build(m, shape, text, prefer_day_first)
        if built:
            return built
    return None


def _build(m: re.Match, shape: str, raw: str, day_first: bool) -> Optional[Period]:
    g = m.groups()
    try:
        if shape == "y":
            return Period(year=_year(g[0]), grain="annual", raw=raw,
                          ambiguous=len(g[0]) == 2)
        if shape == "yq":
            return Period(year=_year(g[0]), quarter=int(g[1]), grain="quarterly", raw=raw)
        if shape == "qy":
            return Period(year=_year(g[1]), quarter=int(g[0]), grain="quarterly", raw=raw,
                          ambiguous=len(g[1]) == 2)
        if shape == "ym":
            return Period(year=_year(g[0]), month=int(g[1]), grain="monthly", raw=raw)
        if shape == "ymd":
            return Period(year=_year(g[0]), month=int(g[1]), day=int(g[2]),
                          grain="daily", raw=raw)
        if shape == "My":
            month = _MONTHS.get(g[0].lower())
            if not month:
                return None
            return Period(year=_year(g[1]), month=month, grain="monthly", raw=raw,
                          ambiguous=len(g[1]) == 2)
        if shape == "yM":
            month = _MONTHS.get(g[1].lower())
            return Period(year=_year(g[0]), month=month, grain="monthly", raw=raw) if month else None
        if shape == "Mdy":
            month = _MONTHS.get(g[0].lower())
            if not month:
                return None
            return Period(year=int(g[2]), month=month, day=int(g[1]), grain="daily", raw=raw)
        if shape == "dMy":
            month = _MONTHS.get(g[1].lower())
            if not month:
                return None
            return Period(year=_year(g[2]), month=month, day=int(g[0]), grain="daily",
                          raw=raw, ambiguous=len(g[2]) == 2)
        if shape == "my":
            return Period(year=_year(g[1]), month=int(g[0]), grain="monthly", raw=raw)
        if shape == "mdy":
            # The genuinely dangerous case. 03/04/2023 is March 4th or April 3rd
            # depending on where the document was written, and nothing in the
            # string says which.
            a, b = int(g[0]), int(g[1])
            month, day = (b, a) if day_first else (a, b)
            if not (1 <= month <= 12):
                month, day = day, month          # only one reading is valid
            elif a <= 12 and b <= 12 and a != b:
                return Period(year=_year(g[2]), month=month, day=day, grain="daily",
                              raw=raw, ambiguous=True)
            return Period(year=_year(g[2]), month=month, day=day, grain="daily", raw=raw,
                          ambiguous=len(g[2]) == 2)
    except (ValueError, TypeError):
        return None
    return None


def infer_day_first(samples: List[str]) -> bool:
    """
    Decide a document's slash convention from all of its date strings together.

    One ``03/04/2023`` is unresolvable. A column also containing ``13/04/2023``
    is not: 13 cannot be a month, so the document is day-first, and every other
    value in it should be read the same way. Deciding once per document beats
    guessing per value.
    """
    day_first_evidence = month_first_evidence = 0
    for sample in samples:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/\d{2,4}$", str(sample).strip())
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 >= b:
            day_first_evidence += 1
        elif b > 12 >= a:
            month_first_evidence += 1
    return day_first_evidence > month_first_evidence


def parse_period_series(samples: List[str]) -> List[Optional[Period]]:
    """Parse a whole column, settling the slash convention once for all of it."""
    day_first = infer_day_first(samples)
    return [parse_period(s, prefer_day_first=day_first) for s in samples]

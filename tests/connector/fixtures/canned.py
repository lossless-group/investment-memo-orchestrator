"""Canned artifacts for fixture-co: one research file and one draft per section.

Synthetic text only. It describes no real company and carries no client data;
it is just long enough, and cited enough, to pass the checks the research and
draft steps declare.
"""

from __future__ import annotations

SECTIONS = {
    "01-overview": (
        "Overview",
        "Fixture Co sells inventory software to independent hardware stores across the "
        "Midwest. Its product replaces spreadsheets with a phone app that counts stock by camera.",
    ),
    "02-market": (
        "Market",
        "Independent hardware retail in the United States is a fragmented market of roughly "
        "twenty thousand stores, most of them run without dedicated inventory software.",
    ),
    "03-team": (
        "Team",
        "The founders met while running operations at a regional distributor, where they saw "
        "stock counts take whole weekends and still come out wrong.",
    ),
}

_FILLER = (
    "The synthetic figures in this fixture exist only to exercise the connector. They "
    "describe no real company, cite no real report, and carry no client data. Each "
    "paragraph is long enough to pass the length checks that the research and draft steps "
    "declare, and each claim carries an inline citation in the house format, with the "
    "citation list at the end."
)

_CITATIONS = """### Citations

[^1]: 2025, Jan 08. [Synthetic Retail Survey](https://example.org/fixture/survey). Fixture Press. Published: 2025-01-08 | Updated: N/A

[^2]: 2025, Mar 03. [Synthetic Industry Note](https://example.org/fixture/note). Fixture Press. Published: 2025-03-03 | Updated: N/A
"""


def research(section: str) -> str:
    """A research file for ``section`` that passes the research checks."""
    name, lede = SECTIONS[section]
    return (
        f"## {name}: research\n\n{lede} [^1]\n\n{_FILLER} [^2]\n\n"
        "Partners asked for dated numbers, so every figure names its year. In 2025 the "
        "synthetic store count was stable, and adoption of inventory tools grew modestly. "
        "[^1] [^2]\n\n" + _CITATIONS
    )


def draft(section: str) -> str:
    """A section draft for ``section`` that passes the draft checks."""
    name, lede = SECTIONS[section]
    return (
        f"## {name}\n\n{lede} [^1]\n\n{_FILLER} [^2]\n\n"
        "For the memo, the point is simple: the opportunity is real, the evidence is "
        "dated, and the next step is to test the claims with the founders. [^1]\n\n" + _CITATIONS
    )


def long_research(chars: int) -> str:
    """A research file of at least ``chars`` characters that still passes its checks."""
    body = research("01-overview")
    paragraph = (_FILLER + " [^1]\n\n") * 10
    while len(body) < chars:
        body = paragraph + body
    return body

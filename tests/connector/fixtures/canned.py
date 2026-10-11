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


# ------------------------------------------------------------------ plan 5: the rest of the flow

#: Markers the compiled memo is searched for, one per enhancement folded into it.
TABLE_MARKER = "Synthetic store count by year"
SCORECARD_MARKER = "Scorecard"
SUMMARY_MARKER = "Revised overview: the evidence now supports a first meeting."


def sources() -> str:
    """research.sources: the deduplicated source list."""
    return (
        "## Sources\n\n- Synthetic Retail Survey (Fixture Press, 2025-01-08), cited by Overview, "
        "Market, and Team.\n- Synthetic Industry Note (Fixture Press, 2025-03-03), cited by "
        "Overview, Market, and Team.\n"
    )


def tables(section: str) -> str:
    """enhance.tables: the whole section, with a table added."""
    name, lede = SECTIONS[section]
    table = (
        f"| {TABLE_MARKER} | Stores | Source |\n|---|---|---|\n"
        "| 2024 | 19,800 | [^1] |\n| 2025 | 20,100 | [^2] |\n"
    )
    return (
        f"## {name}\n\n{lede} [^1]\n\n{table}\n{_FILLER} [^2]\n\n"
        "For the memo, the point is simple: the opportunity is real, the evidence is "
        "dated, and the next step is to test the claims with the founders. [^1]\n\n" + _CITATIONS
    )


def diagrams() -> str:
    """enhance.diagrams: the market-sizing data the server draws."""
    return (
        '## Market sizing\n\n```yaml\nsection: 02-market\ntam: "$4B"\nsam: "$1.2B"\n'
        'som: "$90M"\ntam_growth: "6% CAGR"\nyear: 2025\n```\n\n'
        "All three figures are stated in the Market section, citing the synthetic survey.\n"
    )


def scorecard() -> str:
    """enhance.scorecard."""
    return (
        f"## {SCORECARD_MARKER}\n\n| Dimension | Score (1-5) | Evidence |\n|---|---|---|\n"
        "| Problem | 4 | Stock counts take whole weekends and still come out wrong. |\n"
        "| Market | 3 | Twenty thousand fragmented stores, most without inventory software. |\n"
        "| People | 3 | Founders ran operations at a regional distributor. |\n\n"
        "Overall: 3.3 of 5, a first meeting is warranted but the evidence is thin.\n\n"
        "### Diligence questions\n\n- How many stores pay today, and what do they pay?\n"
        "- How accurate is the camera count against a manual count?\n"
        "- Which distributor relationships carry over to the company?\n"
    )


def summaries() -> str:
    """enhance.summaries: the bookend section rewritten under its exact heading."""
    return (
        f"## Overview\n\n{SUMMARY_MARKER} Fixture Co sells inventory software to independent "
        "hardware stores. [^1] The synthetic survey dates every figure, and the market note "
        "agrees on its size. [^2] The team knows the problem first hand, the market is large "
        "and underserved, and the open questions are about paying customers and count "
        "accuracy, which a first meeting can settle. [^1]\n\n" + _CITATIONS
    )


def one_pager() -> str:
    """enhance.one_pager."""
    return (
        "# Fixture Co, one page\n\n**What it does.** Inventory software for independent "
        "hardware stores: a phone app that counts stock by camera.\n\n**Market.** Roughly twenty "
        "thousand stores in the United States, most without inventory software.\n\n**Team.** "
        "Founders from operations at a regional distributor.\n\n**Risks.** Paying customers and "
        "count accuracy are unproven.\n\n**Recommendation.** Take a first meeting and test "
        "the claims with the founders against a manual count.\n"
    )


def brief() -> str:
    """materials.brief."""
    return (
        "## Brief\n\nThe partner's notes say Fixture Co sells inventory software to "
        "independent hardware stores and counts stock by camera. [^deck]\n\n"
        "[^deck]: The partner's notes.\n"
    )


def for_step(step_id: str, section: str | None) -> str:
    """The canned artifact a scripted client submits for any Claude step."""
    per_section = {
        "research.section": research,
        "draft.section": draft,
        "enhance.tables": tables,
        "enhance.citations": draft,
        "enhance.fact_check": draft,
    }
    per_deal = {
        "materials.brief": brief,
        "research.sources": sources,
        "enhance.diagrams": diagrams,
        "enhance.scorecard": scorecard,
        "enhance.summaries": summaries,
        "enhance.one_pager": one_pager,
    }
    if step_id in per_section:
        return per_section[step_id](section)
    return per_deal[step_id]()


def conflicting_drafts() -> dict[str, str]:
    """Drafts whose local citation numbers collide across sections (CONN-CMP-04).

    Section 1's [^1] and section 2's [^2] are the same source; section 2's [^1]
    and section 3's [^1] are different sources from everything else.
    """
    survey = "2025, Jan 08. [Synthetic Retail Survey](https://example.org/fixture/survey). Fixture Press. Published: 2025-01-08 | Updated: N/A"
    note = "2025, Mar 03. [Synthetic Industry Note](https://example.org/fixture/note). Fixture Press. Published: 2025-03-03 | Updated: N/A"
    census = "2024, Jun 01. [Synthetic Store Census](https://example.org/fixture/census). Fixture Press. Published: 2024-06-01 | Updated: N/A"
    profile = "2025, May 20. [Synthetic Founder Profile](https://example.org/fixture/profile). Fixture Press. Published: 2025-05-20 | Updated: N/A"

    def body(name: str, claims: list[tuple[str, str]], defs: dict[str, str]) -> str:
        lines = [f"## {name}", ""]
        for text, key in claims:
            lines += [f"{text} {_FILLER} [^{key}]", ""]
        lines += ["### Citations", ""]
        lines += [f"[^{k}]: {v}" for k, v in defs.items()]
        return "\n".join(lines) + "\n"

    return {
        "01-overview": body(
            "Overview",
            [("Overview claim from the survey.", "1"), ("Overview claim from the note.", "2")],
            {"1": survey, "2": note},
        ),
        "02-market": body(
            "Market",
            [("Market claim from the census.", "1"), ("Market claim from the survey.", "2")],
            {"1": census, "2": survey},
        ),
        "03-team": body(
            "Team",
            [("Team claim from the profile.", "1"), ("Team claim from the note.", "note")],
            {"1": profile, "note": note},
        ),
    }


#: Which source URL each claim in conflicting_drafts() must still cite after compile.
CONFLICTING_CLAIMS = {
    "Overview claim from the survey.": "https://example.org/fixture/survey",
    "Overview claim from the note.": "https://example.org/fixture/note",
    "Market claim from the census.": "https://example.org/fixture/census",
    "Market claim from the survey.": "https://example.org/fixture/survey",
    "Team claim from the profile.": "https://example.org/fixture/profile",
    "Team claim from the note.": "https://example.org/fixture/note",
}

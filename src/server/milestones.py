"""Pattern-matches log lines into structured milestone events.

The orchestrator's agents print emoji-tagged status messages as they progress
(`🔍 PERPLEXITY SECTION RESEARCH`, `✅ SECTION RESEARCH COMPLETE`,
`[3/10] Market Context`, etc.). For end users, the raw stdout is too noisy —
they want a polished "what's happening" timeline. This module reads each
emitted log line and, when it matches a known pattern, emits a `milestone`
event with structured fields that the UI can render as a milestone card.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Optional

# Stage identifiers — the UI groups milestones into these buckets.
STAGE_START = "start"
STAGE_DECK = "deck_analysis"
STAGE_RESEARCH = "research"
STAGE_COMPETITIVE = "competitive"
STAGE_WRITING = "writing"
STAGE_ENRICHMENT = "enrichment"
STAGE_ASSEMBLY = "assembly"
STAGE_VALIDATION = "validation"
STAGE_ARTIFACTS = "artifacts"
STAGE_COMPLETE = "complete"

# Level: 'info' (in progress), 'success' (stage done), 'warning', 'error'.


@dataclass
class _Pattern:
    regex: re.Pattern
    stage: str
    level: str
    label: str  # may use {0}, {1} placeholders for capture groups
    detail: Optional[str] = None  # ditto


def _format(template: str, m: re.Match) -> str:
    """Substitute {0}, {1}, ... with regex capture groups."""
    out = template
    for i, group in enumerate(m.groups()):
        out = out.replace(f"{{{i}}}", group if group is not None else "")
    return out


# Order matters: more specific patterns first when in doubt.
_PATTERNS: list[_Pattern] = [
    # --- Pipeline start ---
    _Pattern(
        re.compile(r"📁 Created new output directory: (.+?)(?: \(.+\))?$"),
        STAGE_START,
        "success",
        "Run started",
        "Output directory: {0}",
    ),
    _Pattern(
        re.compile(r"📌 Using forced version: (.+)$"),
        STAGE_START,
        "info",
        "Using version {0}",
    ),
    _Pattern(
        re.compile(r"🧹 Fresh run: starting from clean slate"),
        STAGE_START,
        "info",
        "Fresh run — ignoring prior artifacts",
    ),
    # --- Deck analysis ---
    _Pattern(
        re.compile(r"✓ Extracted (\d+) screenshots"),
        STAGE_DECK,
        "info",
        "Extracted {0} pitch deck slides",
    ),
    _Pattern(
        re.compile(r"✓ Merged analysis complete: (\S+) pages analyzed"),
        STAGE_DECK,
        "success",
        "Pitch deck parsed",
        "{0} pages analyzed",
    ),
    _Pattern(
        re.compile(r"✓ Embedded screenshots in (\d+) section"),
        STAGE_DECK,
        "info",
        "Embedded slides in {0} sections",
    ),
    # --- Research ---
    _Pattern(
        re.compile(r"🔍 PERPLEXITY SECTION RESEARCH"),
        STAGE_RESEARCH,
        "info",
        "Researching sections",
    ),
    _Pattern(
        re.compile(r"✓ \[(\d+)\] (.+?): (\d+) citations?$"),
        STAGE_RESEARCH,
        "info",
        "Researched: {1}",
        "{2} citations",
    ),
    _Pattern(
        re.compile(r"✅ SECTION RESEARCH COMPLETE"),
        STAGE_RESEARCH,
        "success",
        "Section research done",
    ),
    # --- Competitive landscape ---
    _Pattern(
        re.compile(r"🔍 Researching competitive landscape for (.+?)\.\.\."),
        STAGE_COMPETITIVE,
        "info",
        "Mapping competitive landscape",
    ),
    _Pattern(
        re.compile(r"🎯 Evaluating (\d+) candidate competitors"),
        STAGE_COMPETITIVE,
        "info",
        "Evaluating {0} competitors",
    ),
    _Pattern(
        re.compile(r"✓ Evaluation complete: (\d+) direct, (\d+) indirect"),
        STAGE_COMPETITIVE,
        "success",
        "Competitors classified",
        "{0} direct, {1} indirect",
    ),
    # --- Writing ---
    _Pattern(
        re.compile(r"📝 Writing memo sections"),
        STAGE_WRITING,
        "info",
        "Drafting memo",
    ),
    _Pattern(
        re.compile(r"\s*\[(\d+)/(\d+)\]\s+(.+?)$"),
        STAGE_WRITING,
        "info",
        "Drafting: {2}",
        "Section {0} of {1}",
    ),
    _Pattern(
        re.compile(r"✅ All (\d+) sections complete"),
        STAGE_WRITING,
        "success",
        "All {0} sections drafted",
    ),
    # --- Enrichment ---
    _Pattern(
        re.compile(r"🔗 Enriching links section-by-section"),
        STAGE_ENRICHMENT,
        "info",
        "Adding contextual links",
    ),
    _Pattern(
        re.compile(r"✓ Link enrichment complete: (\d+) total links"),
        STAGE_ENRICHMENT,
        "success",
        "{0} contextual links added",
    ),
    _Pattern(
        re.compile(r"✓ Team section enriched with (\d+) LinkedIn"),
        STAGE_ENRICHMENT,
        "success",
        "Team enriched with {0} LinkedIn profiles",
    ),
    _Pattern(
        re.compile(r"📊 Generating tables for"),
        STAGE_ENRICHMENT,
        "info",
        "Generating data tables",
    ),
    _Pattern(
        re.compile(r"✓ Table generation complete: (\d+) tables inserted into (\d+) sections"),
        STAGE_ENRICHMENT,
        "success",
        "{0} tables across {1} sections",
    ),
    _Pattern(
        re.compile(r"✓ Diagram generation complete: (\d+) diagram"),
        STAGE_ENRICHMENT,
        "success",
        "{0} diagrams generated",
    ),
    _Pattern(
        re.compile(r"✅ Injected (\d+) screenshot.+? into (\d+) section"),
        STAGE_ENRICHMENT,
        "success",
        "{0} pitch slides into {1} sections",
    ),
    _Pattern(
        re.compile(r"✓ Added (\d+) citations \(total: (\d+)\)"),
        STAGE_ENRICHMENT,
        "info",
        "+{0} citations",
        "Section total: {1}",
    ),
    _Pattern(
        re.compile(r"✓ Memo header saved"),
        STAGE_ENRICHMENT,
        "info",
        "Memo header rendered",
    ),
    # --- Assembly ---
    _Pattern(
        re.compile(r"✓ TOC (?:is accurate|created|regenerated|present|valid|updated)"),
        STAGE_ASSEMBLY,
        "success",
        "Table of contents ready",
    ),
    _Pattern(
        re.compile(r"✓ Reassembled final draft: (\d+) words"),
        STAGE_ASSEMBLY,
        "success",
        "Final draft assembled",
        "{0} words",
    ),
    # --- Validation ---
    _Pattern(
        re.compile(r"🔍 VALIDATION GATE 1: Cleaning research citations"),
        STAGE_VALIDATION,
        "info",
        "Validating research citations",
    ),
    _Pattern(
        re.compile(r"✓ All research citations are valid"),
        STAGE_VALIDATION,
        "success",
        "All research citations valid",
    ),
    _Pattern(
        re.compile(r"📝 Removing (\d+) invalid citations"),
        STAGE_VALIDATION,
        "warning",
        "Removing {0} invalid citations",
    ),
    _Pattern(
        re.compile(r"🔍 FACT CHECKING MEMO SECTIONS"),
        STAGE_VALIDATION,
        "info",
        "Fact-checking claims",
    ),
    _Pattern(
        re.compile(r"✅ All sections passed fact-check"),
        STAGE_VALIDATION,
        "success",
        "All claims verified",
    ),
    _Pattern(
        re.compile(r"⚠️  (\d+) sections require revision"),
        STAGE_VALIDATION,
        "warning",
        "{0} sections need revision",
    ),
    _Pattern(
        re.compile(r"📊 Scorecard Evaluator: Evaluating (.+)$"),
        STAGE_VALIDATION,
        "info",
        "Running scorecard for {0}",
    ),
    _Pattern(
        re.compile(r"✅ Scorecard evaluation complete"),
        STAGE_VALIDATION,
        "success",
        "Scorecard complete",
    ),
    _Pattern(
        re.compile(r"🧹 INTERNAL COMMENTS SANITIZER"),
        STAGE_VALIDATION,
        "info",
        "Sanitizing internal comments",
    ),
    _Pattern(
        re.compile(r"✅ SANITIZATION COMPLETE"),
        STAGE_VALIDATION,
        "success",
        "Internal comments removed",
    ),
    # --- Artifacts ---
    _Pattern(
        re.compile(r"✓ Content slots saved"),
        STAGE_ARTIFACTS,
        "info",
        "One-pager content extracted",
    ),
    _Pattern(
        re.compile(r"✓ Scorecard navigator inserted \((\d+) dimensions"),
        STAGE_ARTIFACTS,
        "success",
        "Scorecard navigator inserted",
        "{0} dimensions",
    ),
]


class MilestoneExtractor:
    """Stateful extractor: feed it lines, get back milestone dicts when matched."""

    def __init__(self) -> None:
        # We dedupe milestones with no capture groups so duplicate prints
        # (`✅ All sections passed fact-check` may appear in summary blocks)
        # don't fire twice.
        self._seen_static: set[str] = set()

    def process(self, line: str) -> Optional[dict]:
        for pat in _PATTERNS:
            m = pat.regex.search(line)
            if not m:
                continue

            label = _format(pat.label, m) if "{" in pat.label else pat.label
            detail = _format(pat.detail, m) if pat.detail and "{" in pat.detail else pat.detail

            # Dedupe non-parameterized milestones.
            if not m.groups():
                if pat.label in self._seen_static:
                    return None
                self._seen_static.add(pat.label)

            return {
                "type": "milestone",
                "id": uuid.uuid4().hex[:10],
                "stage": pat.stage,
                "level": pat.level,
                "label": label,
                "detail": detail,
            }
        return None

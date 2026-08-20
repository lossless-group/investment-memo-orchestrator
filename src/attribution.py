"""
Subject attribution for quantitative claims.

THE FAILURE THIS EXISTS FOR
---------------------------
A memo can pass every check the pipeline has and still be wrong about who a
number belongs to. On TrustedRouter v0.0.2 the Executive Summary was about to
report a "$113 million raise; $1.3 billion valuation; Series B" for a company
raising $1.5M on a $30M cap. Every one of those figures was:

  - retrieved by a real search (provenance ✓)
  - from a live, reputable URL (liveness ✓)
  - correctly cited in the research file it came from (citation ✓)
  - factually true (accuracy ✓)

...and about OpenRouter, whose Series B the competitive section discusses.

Nothing in the anti-hallucination stack catches this, because it is not a
hallucination. Provenance answers "did a retriever return this?"; verification
answers "is this true?". Neither asks "is this about the company the memo is
about?" — and codified mode makes the exposure *worse*, since a curated
competitive corpus is dense with other companies' numbers.

WHAT THIS MODULE DOES
---------------------
Classifies the subject of a sentence as one of:

  self       — names the memo's company
  <name>     — names a known competitor and not the company
  none       — names no entity at all (safe: usually "The company raised...")
  ambiguous  — names some other capitalized entity we cannot resolve

`none` and `self` are treated as attributable to the subject; a competitor name
is not. This is a heuristic over sentences, not coreference resolution: a
sentence like "It raised $113 million" naming nobody will still read as `none`.
It is a large improvement, not a guarantee, and the honest long-term fix is
attribution at write time rather than extraction after.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# Capitalized tokens that are not entity names. Without this, "Series B" and
# month names read as "some other company" and suppress legitimate sentences.
NOT_A_COMPANY = {
    "Series", "Seed", "SAFE", "The", "A", "An", "AI", "API", "LLM", "TEE",
    "Published", "Updated", "Title", "URL", "Source", "Sources", "Citations",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December", "Executive", "Summary",
    "Risks", "Opportunity", "Organization", "Offering", "Origins", "Opening",
    "Funding", "Terms", "Closing", "Assessment", "Scorecard", "Recommendation",
    "TAM", "SAM", "SOM", "ARR", "MRR", "CAGR", "YoY", "MoM", "GTM", "SaaS",
    "CEO", "CTO", "CFO", "VP", "IPO", "LP", "GP", "VC", "US", "EU", "UK",
}

# Claim patterns worth attributing. Numbers without these markers are usually
# prose, not claims about the subject's business.
CLAIM_PATTERNS = [
    (r"\$[\d.,]+\s*(?:[KMB]|million|billion|trillion)?", "financial"),
    (r"\b\d+(?:\.\d+)?%", "percentage"),
    (r"\b[\d,]+\s+(?:customers?|users?|employees?|seats?|tokens?)", "volume"),
    (r"\b\d+(?:\.\d+)?x\b", "multiple"),
]


def sentences(text: str):
    """Split into sentences, keeping it cheap and punctuation-tolerant."""
    for chunk in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        c = chunk.strip()
        if c:
            yield c


def _subject_tokens(company_name: str) -> set:
    return {t.lower() for t in re.findall(r"[A-Za-z]+", company_name or "") if len(t) > 2}


def subject_of(
    sentence: str, company_name: str, competitors: Optional[List[str]] = None
) -> Tuple[str, Optional[str]]:
    """Classify a sentence's subject. Returns (kind, entity_name_or_None).

    kind ∈ {"self", "competitor", "none", "ambiguous"}
    """
    subj = _subject_tokens(company_name)
    low = sentence.lower()

    if any(t in low for t in subj):
        return "self", company_name

    for comp in competitors or []:
        c = comp.strip()
        if c and len(c) > 2 and c.lower() in low:
            return "competitor", c

    # Only consider capitalized tokens that are NOT sentence-initial: "This",
    # "Token" and "Revenue" are capitalized by grammar, not by being names, and
    # treating them as entities flagged 30 of 41 claims on the first real run.
    body = sentence
    for lead in re.finditer(r"(?:^|[.!?]\s+|\|\s*|[-–—]\s*)([A-Z][A-Za-z0-9.\-]*)", sentence):
        body = body.replace(lead.group(1), " ", 1)

    others = [
        w for w in re.findall(r"\b[A-Z][A-Za-z0-9.\-]{2,}\b", body)
        if w not in NOT_A_COMPANY and w.lower() not in subj
        and not w.isupper()          # acronyms: CTO, ARR, TEE — roles/metrics, not firms
    ]
    if not others:
        return "none", None
    return "ambiguous", others[0]


def attribution_filter(
    content: str, company_name: str, competitors: Optional[List[str]] = None
) -> str:
    """Keep only sentences plausibly about the subject company."""
    if not company_name:
        return content
    kept = [
        s for s in sentences(content)
        if subject_of(s, company_name, competitors)[0] in ("self", "none")
    ]
    return "\n".join(kept)


def has_claim(sentence: str) -> Optional[str]:
    """Return the claim type if the sentence carries a quantitative claim."""
    for pattern, kind in CLAIM_PATTERNS:
        if re.search(pattern, sentence):
            return kind
    return None


def audit_claims(
    content: str, company_name: str, competitors: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Every quantitative claim, with its resolved subject.

    Callers decide what to do with `kind`; this only reports.
    """
    findings: List[Dict[str, Any]] = []
    for sent in sentences(content):
        claim_type = has_claim(sent)
        if not claim_type:
            continue
        kind, entity = subject_of(sent, company_name, competitors)
        findings.append({
            "sentence": " ".join(sent.split())[:400],
            "claim_type": claim_type,
            "subject_kind": kind,
            "subject": entity,
        })
    return findings


def known_competitors(state) -> List[str]:
    """Competitor names from the competitive-evaluation artifact, if present."""
    names: List[str] = []
    try:
        from .utils import get_output_dir_from_state
        path = get_output_dir_from_state(state) / "1-competitive-evaluation.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text())

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in ("name", "company", "competitor") and isinstance(v, str):
                        names.append(v)
                    else:
                        walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
    except Exception:  # noqa: BLE001 - auditing must never break a run
        return []
    return sorted({n.strip() for n in names if n and len(n.strip()) > 2})

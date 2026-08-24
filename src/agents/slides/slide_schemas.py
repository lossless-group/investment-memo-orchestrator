"""
Slide Type Vocabulary and Content Schemas

The keystone of the stenographer. Three consumers depend on what is defined
here, and each needs something different from the same file:

- **Corpus search** needs ``slide_type`` to be a small closed vocabulary. Free
  tags cannot answer "every team slide across the portfolio"; a controlled
  field can.
- **Deck rebuilding** needs the content of a slide to arrive in a shape that
  maps onto components. A ``team`` slide's people must be a list of people, not
  a bag of strings that happens to contain names.
- **Memo generation** needs to know which fields are verbatim claims worth
  citing and which are the stenographer's own inference.

A single universal schema would satisfy none of them — flattening a founder and
a TAM figure into the same node loses exactly the structure all three want. So
each slide type carries its own shape, with a generic fallback for slides that
genuinely fit nothing.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set


# =============================================================================
# Slide type vocabulary
# =============================================================================

# Grouped by narrative function. The groups are for humans reading this file;
# only the leaf strings are ever written to a document.
SLIDE_TYPES: Dict[str, str] = {
    # --- Framing ---
    "cover": "Title slide — company name, tagline, sometimes date and round",
    "agenda": "What this deck will cover",
    "divider": "Section break carrying little content of its own",
    # --- The argument ---
    "problem": "The problem being solved, usually with evidence of its size",
    "solution": "How the company answers the problem",
    "product": "What the product is and does",
    "technology": "The technical approach, architecture, or science",
    "how_it_works": "Mechanism walk-through, often a diagram",
    "differentiation": "Why this approach beats the alternatives",
    # --- The market ---
    "market_sizing": "TAM / SAM / SOM or equivalent quantification",
    "market_landscape": "Map of the space, categories, or value chain",
    "competition": "Named competitors, feature or positioning comparison",
    "business_model": "How revenue is earned",
    "pricing": "Price points, tiers, unit economics",
    "go_to_market": "Distribution and customer acquisition strategy",
    # --- Evidence ---
    "traction": "Growth, adoption, revenue to date",
    "metrics": "Operating KPIs presented as a dashboard",
    "customers": "Named customers, logos, or pipeline",
    "case_study": "One customer or deployment in depth",
    "validation": "Press, awards, publications, regulatory milestones",
    "testimonial": "A quote from a customer, investor, or authority",
    # --- The people ---
    "team": "Founders and executives",
    "advisors": "Advisory board, scientific advisors, board members",
    "investors": "Existing backers",
    "hiring_plan": "Roles to be filled with this capital",
    # --- Forward ---
    "roadmap": "Sequenced plan of what gets built when",
    "milestones": "Discrete achievements, past or promised",
    "vision": "The long-horizon ambition",
    "operating_model": "How the company runs itself — org design, process, values, "
                       "strategy frameworks. Common in long-form reading decks and "
                       "appendices, absent from most pitch decks",
    # --- The numbers ---
    "financials": "Historical financial statements",
    "projections": "Forward financial model",
    "cap_table": "Ownership structure",
    "funding_ask": "Amount sought and the terms",
    "use_of_funds": "How the raise will be spent",
    "fund_terms": "Terms of the investing vehicle itself — SPV fees, carry, minimums",
    # --- Risk and close ---
    "risks": "Risks and mitigations",
    "ip_strategy": "Patents, freedom to operate, trade secrets",
    "contact": "Closing slide with contact details",
    "appendix": "Supporting material past the main narrative",
    "other": "Fits none of the above — content captured generically",
}

# NOTE: there is deliberately no "these slide types are always firm-authored"
# set here. An earlier draft had one containing `fund_terms`, which was both dead
# code and wrong: a company's own deck routinely states the terms of the round it
# is raising, and those are the company's claims — checkable, and worth checking.
# MeridianAI's own deck says "Seed round $15mm | SAFE post-money cap $120mm | 15%
# discount", which reconciles against the executed SAFE. Authorship is a property
# of the deck, not of the slide type; the stenographer takes it from
# `authored_by` and nothing infers it from `slide_type`.


def is_valid_slide_type(value: str) -> bool:
    return value in SLIDE_TYPES


def slide_type_prompt_block() -> str:
    """The vocabulary rendered for a model prompt, one line per type."""
    return "\n".join(f"- {name}: {desc}" for name, desc in SLIDE_TYPES.items())


# =============================================================================
# Shared content fragments
# =============================================================================

# Nearly every slide has a title and often a subtitle. Keeping this one shape
# everywhere means a rebuild template can render a heading without knowing the
# slide type, and a corpus query can read titles across the whole portfolio.
TITLE_ROW = {
    "titleTxt": "str — the heading, verbatim",
    "subtitleTxt": "str|null — the subheading, verbatim",
    "eyebrowTxt": "str|null — kicker or category label above the title, verbatim",
}

_PERSON = {
    "fullName": "str",
    "currentTitle": "str|null — role as printed on the slide",
    "blurb": "str|null — the descriptive line, verbatim",
    "priorAffiliations": "list[str] — organizations named, in the order printed",
    "credentials": "list[str] — degrees or honors named",
    "imagePresent": "bool — whether a headshot appears",
}

_METRIC = {
    "label": "str — verbatim label",
    "valueTxt": "str — verbatim value as printed, e.g. '$1.3T', '17'",
    "value": "number|null — parsed numeric, null when not cleanly parseable",
    "unit": "str|null — 'USD', 'users', 'years', '%'",
    "period": "str|null — the period it covers, if stated",
}


# =============================================================================
# Per-type content schemas
# =============================================================================

# Each entry describes the JSON the stenographer must emit for that slide type.
# Values are human-readable type descriptions rather than JSON Schema: they go
# straight into the model prompt, where a plain description outperforms a formal
# schema for this kind of shape-following.
CONTENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "cover": {
        "titleRow": TITLE_ROW,
        "companyName": "str",
        "dateTxt": "str|null — any date printed on the slide, verbatim",
        "roundTxt": "str|null — e.g. 'Seed', 'Series A', verbatim",
        "presenter": "str|null",
    },
    "team": {
        "titleRow": TITLE_ROW,
        "executivesRow": [_PERSON],
        "advisorsRow": [_PERSON],
        "teamStatement": "str|null — any framing sentence about the team, verbatim",
    },
    "advisors": {
        "titleRow": TITLE_ROW,
        "advisorsRow": [_PERSON],
    },
    "investors": {
        "titleRow": TITLE_ROW,
        "investors": [{
            "name": "str",
            "type": "str|null — 'fund', 'angel', 'strategic', 'accelerator'",
            "blurb": "str|null — verbatim",
            "logoPresent": "bool",
        }],
    },
    "market_sizing": {
        "titleRow": TITLE_ROW,
        "sizing": [{
            "tier": "str — 'TAM', 'SAM', 'SOM', or the label used on the slide",
            "valueTxt": "str — verbatim, e.g. '$1.3T'",
            "value": "number|null — parsed to base units",
            "basis": "str|null — what the figure counts, verbatim",
            "sourceTxt": "str|null — any citation printed on the slide, verbatim",
        }],
        "growthRate": "str|null — CAGR or equivalent, verbatim",
    },
    "competition": {
        "titleRow": TITLE_ROW,
        "axes": "list[str]|null — axis labels if this is a 2x2 or matrix",
        "competitors": [{
            "name": "str",
            "positioning": "str|null — verbatim",
            "category": "str|null — the group it is placed in on the slide",
            "attributes": "dict|null — feature-comparison cells, verbatim",
        }],
        "ourPosition": "str|null — how the company places itself, verbatim",
    },
    "traction": {
        "titleRow": TITLE_ROW,
        "metrics": [_METRIC],
        "timeSeries": "list[{period, label, valueTxt, value}]|null — chart data if legible",
        "narrativeTxt": "str|null — framing sentence, verbatim",
    },
    "metrics": {
        "titleRow": TITLE_ROW,
        "metrics": [_METRIC],
    },
    "customers": {
        "titleRow": TITLE_ROW,
        "customers": [{
            "name": "str",
            "segment": "str|null",
            "status": "str|null — 'live', 'pilot', 'LOI', as printed",
            "logoPresent": "bool",
        }],
    },
    "funding_ask": {
        "titleRow": TITLE_ROW,
        "askTxt": "str|null — the amount sought, verbatim",
        "askValue": "number|null",
        "instrument": "str|null — 'SAFE', 'Series A Preferred', verbatim",
        "terms": "dict|null — cap, discount, valuation, price, each verbatim",
        "closingTxt": "str|null — closing date as printed",
    },
    "fund_terms": {
        "titleRow": TITLE_ROW,
        "tiers": [{
            "commitmentTxt": "str — verbatim band, e.g. '<$1M'",
            "adminFeeTxt": "str|null",
            "carryTxt": "str|null",
            "appliesTo": "str|null — e.g. 'Fund I LPs'",
        }],
        "minimums": "dict|null — {audience: amountTxt}, verbatim",
        "closingTxt": "str|null",
    },
    "use_of_funds": {
        "titleRow": TITLE_ROW,
        "allocations": [{
            "category": "str — verbatim",
            "shareTxt": "str|null — verbatim percentage or amount",
            "share": "number|null",
            "note": "str|null — verbatim",
        }],
    },
    "roadmap": {
        "titleRow": TITLE_ROW,
        "phases": [{
            "label": "str — verbatim phase name",
            "periodTxt": "str|null — verbatim timing",
            "items": "list[str] — verbatim bullets",
            "status": "str|null — 'complete', 'in progress', 'planned', if indicated",
        }],
    },
    "milestones": {
        "titleRow": TITLE_ROW,
        "milestones": [{
            "label": "str — verbatim",
            "dateTxt": "str|null — verbatim",
            "achieved": "bool|null",
        }],
    },
    "financials": {
        "titleRow": TITLE_ROW,
        "lineItems": [{
            "label": "str — verbatim",
            "byPeriod": "dict — {period: valueTxt}, verbatim as printed",
        }],
        "periods": "list[str] — column headers in order",
    },
    "projections": {
        "titleRow": TITLE_ROW,
        "lineItems": [{"label": "str", "byPeriod": "dict"}],
        "periods": "list[str]",
        "assumptions": "list[str] — verbatim",
    },
    "problem": {
        "titleRow": TITLE_ROW,
        "problemStatements": "list[str] — verbatim, one per distinct claim",
        "evidence": [_METRIC],
        "quote": "str|null — verbatim quotation if the slide leads with one",
        "quoteAttribution": "str|null — verbatim",
    },
    "solution": {
        "titleRow": TITLE_ROW,
        "solutionStatements": "list[str] — verbatim",
        "pillars": [{"label": "str", "description": "str|null"}],
    },
    "product": {
        "titleRow": TITLE_ROW,
        "capabilities": [{"label": "str", "description": "str|null"}],
        "screenshotPresent": "bool",
    },
    "technology": {
        "titleRow": TITLE_ROW,
        "claims": "list[str] — verbatim technical claims",
        "components": [{"label": "str", "description": "str|null"}],
        "comparisons": "list[{against, dimension, claimTxt}]|null",
    },
    "testimonial": {
        "titleRow": TITLE_ROW,
        "quotes": [{
            "quoteTxt": "str — verbatim, including punctuation",
            "attribution": "str|null — verbatim name",
            "attributionTitle": "str|null — verbatim role and organization",
        }],
    },
    "validation": {
        "titleRow": TITLE_ROW,
        "items": [{
            "label": "str — verbatim",
            "kind": "str|null — 'press', 'award', 'publication', 'regulatory', 'patent'",
            "sourceTxt": "str|null — verbatim",
            "dateTxt": "str|null",
        }],
    },
    "ip_strategy": {
        "titleRow": TITLE_ROW,
        "claims": "list[str] — verbatim",
        "filings": "list[{label, status, dateTxt}]|null",
    },
    "operating_model": {
        "titleRow": TITLE_ROW,
        "framework": "str|null — the framework's name, verbatim",
        "pillars": [{
            "label": "str — verbatim",
            "description": "str|null — verbatim",
            "items": "list[str] — verbatim bullets under this pillar",
        }],
        "tracks": "list[str]|null — parallel workstreams named on the slide, verbatim",
    },
    "risks": {
        "titleRow": TITLE_ROW,
        "risks": [{"risk": "str — verbatim", "mitigation": "str|null — verbatim"}],
    },
    "contact": {
        "titleRow": TITLE_ROW,
        "contacts": [{
            "fullName": "str",
            "role": "str|null",
            "organization": "str|null",
            "email": "str|null",
            "phone": "str|null",
        }],
    },
}

# Slides that fit no schema still need capturing. The generic shape preserves
# reading order and region structure so a rebuild has something to work with,
# even though the corpus cannot query it semantically.
GENERIC_SCHEMA: Dict[str, Any] = {
    "titleRow": TITLE_ROW,
    "regions": [{
        "regionLabel": "str — a name for this area, e.g. 'left column', 'footer band'",
        "elementType": "str — 'text' | 'bullets' | 'table' | 'chart' | 'image' | 'quote' | 'logos'",
        "textLines": "list[str] — every line of text in the region, verbatim, in reading order",
        "tableRows": "list[list[str]]|null — verbatim cells if this is a table",
        "description": "str|null — what a chart or image depicts, when text cannot carry it",
    }],
}


def schema_for(slide_type: str) -> Dict[str, Any]:
    """Content schema for a slide type, falling back to the generic shape."""
    return CONTENT_SCHEMAS.get(slide_type, GENERIC_SCHEMA)


def schema_is_generic(slide_type: str) -> bool:
    return slide_type not in CONTENT_SCHEMAS


# =============================================================================
# Layout vocabulary
# =============================================================================

# Structure and rendering pattern are separate facts. "3-rows, masonry" conflates
# how many bands the slide has with how their contents are arranged, and a
# rebuild needs to read them independently.
LAYOUT_PATTERNS: Dict[str, str] = {
    "single": "One block of content filling the slide",
    "stacked": "Rows in a simple vertical sequence",
    "columns": "Content split into equal vertical columns",
    "masonry": "Cards of uneven height packed into a grid",
    "grid": "Regular grid of equal cells",
    "table": "Ruled table with headers",
    "chart": "Dominated by a single chart or graph",
    "diagram": "Dominated by a flow or architecture diagram",
    "matrix": "Two-axis positioning plot",
    "timeline": "Horizontal or vertical time sequence",
    "split": "Two unequal panes, typically image beside text",
    "full_bleed": "Edge-to-edge image or color field with overlaid text",
    "quote": "A single quotation set as the whole slide",
}


def layout_prompt_block() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in LAYOUT_PATTERNS.items())


# =============================================================================
# Validation
# =============================================================================

def validate_slide_record(record: Dict[str, Any]) -> List[str]:
    """
    Check a stenographer record for problems, returning human-readable messages.

    Deliberately returns warnings rather than raising. A slide that transcribes
    imperfectly is still worth keeping — what must not happen is that it gets
    filed as if it were clean.
    """
    problems: List[str] = []

    slide_type = record.get("slide_type")
    if not slide_type:
        problems.append("slide_type is missing")
    elif not is_valid_slide_type(slide_type):
        # Not an error. The vocabulary exists to make a corpus coherent, not to
        # refuse content that does not fit it — a deck that genuinely does
        # something new should be able to say so, and forcing it to "other"
        # throws the observation away. A proposed type is recorded and surfaced
        # for promotion; see propose_slide_type().
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", slide_type):
            problems.append(
                f"proposed slide_type '{slide_type}' is not a usable identifier — "
                f"needs to be lower_snake_case"
            )
        else:
            problems.append(
                f"slide_type '{slide_type}' is a new type, not yet in the canon — "
                f"review and promote it, or map it to an existing type"
            )

    layout = record.get("layout_pattern")
    if layout and layout not in LAYOUT_PATTERNS:
        problems.append(f"layout_pattern '{layout}' is not in the vocabulary")

    fidelity = record.get("transcription_fidelity")
    if fidelity not in ("verbatim", "partial", "illegible", None):
        problems.append(f"transcription_fidelity '{fidelity}' is not a recognized value")

    content = record.get("content")
    if not isinstance(content, dict) or not content:
        problems.append("content block is empty — the slide was not transcribed")
    else:
        title_row = content.get("titleRow")
        if not isinstance(title_row, dict) or not title_row.get("titleTxt"):
            # Dividers and full-bleed images legitimately have no title.
            if slide_type not in ("divider", "cover", "other"):
                problems.append("no titleTxt captured — verify against the slide image")

    if not record.get("core_message"):
        problems.append("core_message is missing")

    return problems


# =============================================================================
# Type shortlisting
# =============================================================================

# Keywords that suggest a slide type, scored against the text layer. This is a
# cheap local pre-pass whose only job is to decide which schemas are worth
# putting in the prompt: sending all 25 would cost more tokens than the slide,
# and sending only the generic one means the model never sees the typed shape it
# is meant to fill. The model still chooses the final type and may pick one that
# was not shortlisted.
_TYPE_CUES: Dict[str, List[str]] = {
    "team": ["founder", "ceo", "cto", "coo", "our team", "leadership", "co-founder", "phd"],
    "advisors": ["advisor", "advisory board", "board of advisors", "scientific advisor"],
    "investors": ["investors", "backed by", "our backers", "cap table", "seed investors"],
    "market_sizing": ["tam", "sam", "som", "market size", "billion", "trillion", "addressable"],
    "competition": ["competitive", "competitor", "landscape", "vs.", "versus", "alternatives"],
    "traction": ["traction", "growth", "arr", "mrr", "users", "customers", "revenue", "pipeline"],
    "metrics": ["kpi", "metrics", "dashboard", "retention", "churn", "cac", "ltv"],
    "customers": ["customers", "logos", "clients", "partners", "deployments"],
    "problem": ["problem", "the challenge", "pain", "today", "broken", "inefficient"],
    "solution": ["solution", "we solve", "our approach", "how we", "introducing"],
    "product": ["product", "platform", "features", "capabilities", "demo"],
    "technology": ["technology", "architecture", "algorithm", "model", "patent", "research"],
    "roadmap": ["roadmap", "milestones", "timeline", "phase", "next steps", "q1", "q2"],
    "milestones": ["milestones", "achieved", "completed", "shipped"],
    "financials": ["p&l", "income statement", "balance sheet", "gross margin", "ebitda"],
    "projections": ["projections", "forecast", "model", "fy20", "fy21", "fy22", "assumptions"],
    "funding_ask": ["raising", "the ask", "seeking", "round", "safe", "pre-money", "post-money",
                    "valuation", "discount", "deal terms", "offering"],
    "use_of_funds": ["use of funds", "use of proceeds", "allocation", "spend"],
    "fund_terms": ["carry", "admin fee", "management fee", "commitment", "spv terms",
                   "minimum commitment", "lps"],
    "cap_table": ["ownership", "fully diluted", "shares outstanding", "option pool"],
    "testimonial": ['"', "quote", "said", "—", "testimonial"],
    "validation": ["press", "award", "featured in", "published", "nature", "fda", "patent granted"],
    "ip_strategy": ["patent", "ip strategy", "freedom to operate", "uspto", "trade secret"],
    "risks": ["risk", "mitigation", "challenges", "what could go wrong"],
    "contact": ["thank you", "contact", "@", "let's talk", "questions"],
    "cover": ["confidential", "presentation", "pitch deck"],
    "vision": ["vision", "our mission", "the future", "long term"],
    "go_to_market": ["go-to-market", "gtm", "distribution", "sales motion", "channel"],
    "operating_model": ["values", "imperatives", "measures", "systems", "operating model",
                        "org design", "how we work", "culture", "pmo", "project management",
                        "business strategy", "technology strategy", "guiding principles"],
    "business_model": ["business model", "revenue model", "how we make money", "pricing"],
}


def rank_slide_types(text: str, top_n: int = 4) -> List[str]:
    """
    Shortlist the slide types a page most likely is, best first.

    Always includes ``other`` last so the generic shape is available when nothing
    matches. Scoring is deliberately crude — this only narrows which schemas go
    into the prompt, and a wrong shortlist costs a generic transcription rather
    than a wrong answer.
    """
    lowered = (text or "").lower()
    if not lowered.strip():
        return ["cover", "divider", "other"]

    scored: List[tuple] = []
    for slide_type, cues in _TYPE_CUES.items():
        hits = sum(1 for cue in cues if cue in lowered)
        if hits:
            scored.append((hits, slide_type))

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    shortlist = [slide_type for _, slide_type in scored[:top_n]]
    if "other" not in shortlist:
        shortlist.append("other")
    return shortlist


def schemas_prompt_block(slide_types: List[str]) -> str:
    """Render the content schemas for a shortlist, ready to drop into a prompt."""
    import json as _json

    blocks: List[str] = []
    for slide_type in slide_types:
        schema = schema_for(slide_type)
        label = slide_type if slide_type in CONTENT_SCHEMAS else f"{slide_type} (generic shape)"
        blocks.append(f'--- if slide_type is "{label}" ---\n'
                      + _json.dumps(schema, indent=2, ensure_ascii=False))
    return "\n\n".join(blocks)


# =============================================================================
# Extending the vocabulary
# =============================================================================

# Where proposed types accrete. Kept beside the slide documents rather than in
# code, because a proposal is an observation about a corpus, and the person who
# decides whether it becomes canon is looking at that corpus, not at this file.
PROPOSALS_FILENAME = "_proposed-slide-types.yaml"


def propose_slide_type(
    proposals_path: "Path",
    slide_type: str,
    rationale: str,
    slide_uid: str,
    today: str,
) -> None:
    """
    Record a slide type the stenographer coined because nothing fit.

    The taxonomy is a coherence aid. Its value is that a corpus query for "every
    team slide" returns every team slide — which requires most slides to land on
    shared names, not that every slide does. When a deck genuinely does something
    the vocabulary cannot express, coining a name preserves the observation;
    forcing it to ``other`` destroys it, and eight slides of organizational
    design filed as ``other`` is a taxonomy gap reported as noise.

    Proposals accumulate with an occurrence count. One sighting is an oddity;
    the same coined type appearing across several decks is a type the canon is
    missing.
    """
    from pathlib import Path

    import yaml

    proposals_path = Path(proposals_path)
    data = {"proposals": []}
    if proposals_path.exists():
        data = yaml.safe_load(proposals_path.read_text(encoding="utf-8")) or data

    existing = next(
        (p for p in data["proposals"] if p.get("type") == slide_type), None
    )
    if existing:
        existing["occurrences"] = existing.get("occurrences", 1) + 1
        existing.setdefault("seen_in", []).append(slide_uid)
        existing["last_seen"] = today
    else:
        data["proposals"].append({
            "type": slide_type,
            "status": "proposed",       # proposed | promoted | mapped | rejected
            "rationale": rationale,
            "first_seen": today,
            "last_seen": today,
            "occurrences": 1,
            "seen_in": [slide_uid],
            "maps_to": None,            # set when a reviewer folds it into an existing type
        })

    proposals_path.parent.mkdir(parents=True, exist_ok=True)
    proposals_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

"""
Competitive Landscape Evaluator Agent.

Screens each candidate competitor for actual relevance, classifies them as
direct/indirect/adjacent/not-a-competitor, runs gap analysis, and produces
a validated competitor list the writer can trust.

Runs immediately after the researcher, still in the research phase.
Does NOT trigger rewrites — produces cleaned data + paper trail artifact.

See context-v/Introducing-a-Competitive-Landscape-Research-and-Evaluation-System.md
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ..state import MemoState
from ..utils import get_output_dir_from_state


EVALUATION_PROMPT = """You are a skeptical competitive analyst. Your job is to CHALLENGE whether
each candidate is actually a competitor of {company_name}.

Company being analyzed:
- Name: {company_name}
- Description: {description}
- Stage: {stage}
- Product/Market: {market_category}

Evaluate EACH candidate below against these four criteria:

| Criterion | Question |
|-----------|----------|
| Same customer segment | Do they sell to the same buyer persona? |
| Substitutability | Could a customer choose one instead of the other? |
| Same budget line | Would they compete for the same dollar in a customer's budget? |
| Market overlap | Are they in the same geographic/vertical markets? |

Classification rules:
- "direct_competitor": High on 3-4 criteria. A customer would genuinely evaluate both.
- "indirect_competitor": High on 2 criteria. Competes for attention or budget but different approach.
- "adjacent": High on only 1 criterion. Same industry but not really competing.
- "not_a_competitor": High on 0 criteria. Incorrectly identified.

CANDIDATES TO EVALUATE:
{candidates_json}

IMPORTANT:
- Be SKEPTICAL. Your completion bias should find problems, not justify inclusion.
- A company in the same broad industry is NOT automatically a competitor.
- Companies with different product forms (software vs supplement, platform vs tool) are usually indirect at best.
- If you're unsure, classify as "adjacent" not "direct_competitor".

Return valid JSON:
{{
    "evaluations": [
        {{
            "name": "Company Name",
            "classification": "direct_competitor|indirect_competitor|adjacent|not_a_competitor",
            "evaluation_reasoning": "1-2 sentences explaining why",
            "same_customer": true/false,
            "substitutable": true/false,
            "comparable_pricing": true/false,
            "comparable_features": true/false,
            "overlapping_value_propositions": true/false,
            "market_overlap": true/false
        }}
    ],
    "gaps_identified": "Description of any obvious competitor types that are MISSING from this list",
    "gap_queries": ["query 1 to find missing competitors", "query 2"]
}}
"""

GAP_SEARCH_PROMPT = """You are looking for competitors of {company_name} that were MISSED in the initial research.

Company: {company_name}
Description: {description}

Gap identified: {gap_description}

The initial research found these competitors but may have missed others:
{existing_names}

Search query: "{query}"

Find companies that fill the identified gap. Return JSON:
{{
    "competitors": [
        {{
            "name": "Company Name",
            "description": "What they do",
            "website": "https://...",
            "founded": "2020",
            "funding_total": "$5M",
            "funding_stage": "Seed",
            "notable_investors": [],
            "employee_count": null,
            "online_presence": {{}},
            "key_differentiator": "How they approach the market",
            "overlap_description": "Why they compete with {company_name}",
            "classification": "direct_competitor|indirect_competitor",
            "evaluation_reasoning": "Why this is a real competitor"
        }}
    ]
}}

Only include companies that actually exist. Do not fabricate data.
"""


def _extract_market_category(state: MemoState) -> str:
    """Extract market category context for evaluation."""
    parts = []
    deck = state.get("deck_analysis")
    if deck:
        for key in ("product_description", "solution_description", "business_model"):
            if deck.get(key):
                parts.append(str(deck[key]))
    description = state.get("company_description", "")
    if description:
        parts.append(description)
    return "; ".join(parts[:2]) if parts else "technology startup"


def _evaluate_candidates(
    candidates: List[Dict],
    company_name: str,
    description: str,
    stage: str,
    market_category: str,
    perplexity_client,
) -> tuple:
    """Evaluate all candidates and identify gaps. Returns (evaluations, gap_description, gap_queries)."""

    # Prepare condensed candidate info for the prompt
    condensed = []
    for c in candidates:
        condensed.append({
            "name": c.get("name", "Unknown"),
            "description": c.get("description", ""),
            "key_differentiator": c.get("key_differentiator", ""),
            "overlap_description": c.get("overlap_description", ""),
            "funding_total": c.get("funding_total"),
            "from_deck": c.get("from_deck", False),
            "from_dataroom": c.get("from_dataroom", False),
        })

    prompt = EVALUATION_PROMPT.format(
        company_name=company_name,
        description=description or "N/A",
        stage=stage or "Early-stage",
        market_category=market_category,
        candidates_json=json.dumps(condensed, indent=2),
    )

    try:
        response = perplexity_client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {"role": "system", "content": "You are a skeptical competitive analyst. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=6000,
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"```(?:json)?\s*", "", content)
        content = re.sub(r"```\s*$", "", content)

        result = json.loads(content)
        evaluations = result.get("evaluations", [])
        gap_desc = result.get("gaps_identified", "")
        gap_queries = result.get("gap_queries", [])

        return evaluations, gap_desc, gap_queries

    except Exception as e:
        print(f"    Warning: Evaluation failed: {e}")
        # Fallback: classify all as "indirect" so nothing is lost
        evaluations = []
        for c in candidates:
            evaluations.append({
                "name": c.get("name", "Unknown"),
                "classification": "indirect_competitor",
                "evaluation_reasoning": "Could not evaluate — defaulting to indirect",
                "same_customer": False,
                "substitutable": False,
                "comparable_pricing": False,
                "comparable_features": False,
                "overlapping_value_propositions": False,
                "market_overlap": True,
            })
        return evaluations, "", []


def _search_for_gaps(
    gap_description: str,
    gap_queries: List[str],
    company_name: str,
    description: str,
    existing_names: List[str],
    perplexity_client,
) -> List[Dict]:
    """Search for competitors missed in initial research."""
    found = []

    for query in gap_queries[:2]:  # Max 2 gap queries
        prompt = GAP_SEARCH_PROMPT.format(
            company_name=company_name,
            description=description or "N/A",
            gap_description=gap_description,
            existing_names=", ".join(existing_names),
            query=query,
        )

        try:
            response = perplexity_client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": "You are a competitive analyst. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=3000,
                temperature=0.2,
            )
            content = response.choices[0].message.content.strip()
            content = re.sub(r"```(?:json)?\s*", "", content)
            content = re.sub(r"```\s*$", "", content)

            result = json.loads(content)
            competitors = result.get("competitors", [])

            for c in competitors:
                name = c.get("name", "").strip().lower()
                if name and name not in [n.lower() for n in existing_names]:
                    c["source_queries"] = [f"gap_analysis: {query}"]
                    c["source_urls"] = []
                    c["from_deck"] = False
                    c["from_dataroom"] = False
                    found.append(c)

        except Exception as e:
            print(f"    Warning: Gap search failed for '{query[:50]}...': {e}")

    return found


def _merge_evaluation_with_candidate(
    candidate: Dict,
    evaluation: Dict,
) -> Dict:
    """Merge evaluation results with original candidate data."""
    merged = dict(candidate)
    merged["classification"] = evaluation.get("classification", "indirect_competitor")
    merged["evaluation_reasoning"] = evaluation.get("evaluation_reasoning", "")
    merged["same_customer"] = evaluation.get("same_customer", False)
    merged["substitutable"] = evaluation.get("substitutable", False)
    merged["comparable_pricing"] = evaluation.get("comparable_pricing", False)
    merged["comparable_features"] = evaluation.get("comparable_features", False)
    merged["overlapping_value_propositions"] = evaluation.get("overlapping_value_propositions", False)
    merged["market_overlap"] = evaluation.get("market_overlap", False)
    merged.setdefault("complete_investor_list", merged.get("notable_investors", []))
    return merged


def _save_evaluation_artifact(
    output_dir: Path,
    evaluated: List[Dict],
    removed: List[Dict],
    gap_additions: List[str],
    company_name: str,
    summary: str,
):
    """Save competitive evaluation artifact."""
    lines = [
        f"# Competitive Landscape Evaluation: {company_name}",
        f"",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Total evaluated**: {len(evaluated) + len(removed)}",
        f"**Retained**: {len(evaluated)}",
        f"**Removed**: {len(removed)}",
        f"**Added via gap analysis**: {len(gap_additions)}",
        f"",
        f"## Summary",
        f"",
        summary,
        f"",
    ]

    # Direct competitors
    direct = [c for c in evaluated if c.get("classification") == "direct_competitor"]
    if direct:
        lines.append("## Direct Competitors")
        lines.append("")
        lines.append("| Company | Founded | Funding | Stage | Key Differentiator |")
        lines.append("|---------|---------|---------|-------|--------------------|")
        for c in direct:
            name = c.get("name", "Unknown")
            website = c.get("website", "")
            name_cell = f"[{name}]({website})" if website else name
            lines.append(
                f"| {name_cell} | {c.get('founded', '—')} | {c.get('funding_total', '—')} "
                f"| {c.get('funding_stage', '—')} | {c.get('key_differentiator', '—')} |"
            )
        lines.append("")
        for c in direct:
            lines.append(f"**{c.get('name')}**: {c.get('evaluation_reasoning', '')}")
            lines.append("")

    # Indirect competitors
    indirect = [c for c in evaluated if c.get("classification") == "indirect_competitor"]
    if indirect:
        lines.append("## Indirect Competitors")
        lines.append("")
        lines.append("| Company | Founded | Funding | Approach | Why Indirect |")
        lines.append("|---------|---------|---------|----------|--------------|")
        for c in indirect:
            name = c.get("name", "Unknown")
            website = c.get("website", "")
            name_cell = f"[{name}]({website})" if website else name
            lines.append(
                f"| {name_cell} | {c.get('founded', '—')} | {c.get('funding_total', '—')} "
                f"| {c.get('key_differentiator', '—')} | {c.get('evaluation_reasoning', '—')} |"
            )
        lines.append("")

    # Adjacent
    adjacent = [c for c in evaluated if c.get("classification") == "adjacent"]
    if adjacent:
        lines.append("## Adjacent Companies")
        lines.append("")
        for c in adjacent:
            lines.append(f"- **{c.get('name')}**: {c.get('evaluation_reasoning', '')}")
        lines.append("")

    # Removed
    if removed:
        lines.append("## Removed as Non-Competitors")
        lines.append("")
        lines.append("| Company | Reason for Removal |")
        lines.append("|---------|-------------------|")
        for r in removed:
            lines.append(f"| {r.get('name', 'Unknown')} | {r.get('reasoning', '—')} |")
        lines.append("")

    # Gap analysis
    if gap_additions:
        lines.append("## Gap Analysis Additions")
        lines.append("")
        lines.append(f"The following competitors were found during gap analysis: {', '.join(gap_additions)}")
        lines.append("")

    content = "\n".join(lines)
    (output_dir / "1-competitive-evaluation.md").write_text(content)

    # Save structured JSON
    (output_dir / "1-competitive-evaluation.json").write_text(json.dumps({
        "evaluated_competitors": evaluated,
        "removed": removed,
        "gap_additions": gap_additions,
        "summary": summary,
        "generated_at": datetime.now().isoformat(),
    }, indent=2, ensure_ascii=False, default=str))


def competitive_landscape_evaluator(state: MemoState) -> Dict[str, Any]:
    """
    Competitive Landscape Evaluator Agent.

    Screens each candidate competitor against relevance criteria, classifies them,
    identifies gaps, and produces a validated competitor list.

    Args:
        state: Current memo state with competitive_candidates

    Returns:
        State update with competitive_landscape
    """
    company_name = state["company_name"]
    description = state.get("company_description", "")
    stage = state.get("company_stage", "")

    # Check for candidates
    candidates_data = state.get("competitive_candidates")
    if not candidates_data:
        print("⊘ Competitive evaluation skipped — no candidates to evaluate")
        return {
            "messages": ["Competitive evaluation skipped — no candidates from researcher"]
        }

    candidates = candidates_data.get("candidates", [])
    if not candidates:
        print("⊘ Competitive evaluation skipped — empty candidate list")
        return {
            "messages": ["Competitive evaluation skipped — empty candidate list"]
        }

    # Check for Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        print("Warning: PERPLEXITY_API_KEY not set, skipping competitive evaluation")
        return {
            "messages": ["Competitive evaluation skipped — no Perplexity API key"]
        }

    print(f"\n🎯 Evaluating {len(candidates)} candidate competitors for {company_name}...")

    from openai import OpenAI
    perplexity_client = OpenAI(
        api_key=perplexity_key,
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }
    )

    market_category = _extract_market_category(state)

    # Get output directory
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        output_dir = None

    # --- Phase 1: Evaluate all candidates ---

    evaluations, gap_description, gap_queries = _evaluate_candidates(
        candidates=candidates,
        company_name=company_name,
        description=description,
        stage=stage,
        market_category=market_category,
        perplexity_client=perplexity_client,
    )

    # Build a lookup from evaluations by name
    eval_by_name = {}
    for e in evaluations:
        eval_by_name[e.get("name", "").strip().lower()] = e

    # Merge evaluations with original candidate data
    evaluated_competitors = []
    removed = []

    for candidate in candidates:
        name = candidate.get("name", "").strip()
        eval_data = eval_by_name.get(name.lower(), {})

        if not eval_data:
            # No evaluation returned for this candidate — keep as indirect
            eval_data = {
                "classification": "indirect_competitor",
                "evaluation_reasoning": "Not evaluated — defaulting to indirect",
                "same_customer": False,
                "substitutable": False,
                "comparable_pricing": False,
                "comparable_features": False,
                "overlapping_value_propositions": False,
                "market_overlap": True,
            }

        classification = eval_data.get("classification", "indirect_competitor")

        if classification == "not_a_competitor":
            removed.append({
                "name": name,
                "reasoning": eval_data.get("evaluation_reasoning", ""),
            })
            print(f"  ✗ {name}: removed (not a competitor)")
        else:
            merged = _merge_evaluation_with_candidate(candidate, eval_data)
            evaluated_competitors.append(merged)
            symbol = {"direct_competitor": "●", "indirect_competitor": "◐", "adjacent": "○"}.get(classification, "?")
            print(f"  {symbol} {name}: {classification}")

    # --- Phase 2: Gap analysis ---

    gap_additions = []
    if gap_description and gap_queries:
        print(f"\n  Gap analysis: {gap_description[:80]}...")
        existing_names = [c.get("name", "") for c in evaluated_competitors]

        gap_results = _search_for_gaps(
            gap_description=gap_description,
            gap_queries=gap_queries,
            company_name=company_name,
            description=description,
            existing_names=existing_names,
            perplexity_client=perplexity_client,
        )

        for gr in gap_results:
            name = gr.get("name", "Unknown")
            gr.setdefault("classification", "indirect_competitor")
            gr.setdefault("evaluation_reasoning", "Found via gap analysis")
            gr.setdefault("same_customer", False)
            gr.setdefault("substitutable", False)
            gr.setdefault("comparable_pricing", False)
            gr.setdefault("comparable_features", False)
            gr.setdefault("overlapping_value_propositions", False)
            gr.setdefault("market_overlap", True)
            gr.setdefault("complete_investor_list", gr.get("notable_investors", []))
            evaluated_competitors.append(gr)
            gap_additions.append(name)
            print(f"  + {name}: added via gap analysis ({gr.get('classification')})")

    # --- Build results ---

    direct_names = [c["name"] for c in evaluated_competitors if c.get("classification") == "direct_competitor"]
    indirect_names = [c["name"] for c in evaluated_competitors if c.get("classification") == "indirect_competitor"]

    # Determine confidence
    if len(direct_names) >= 3 and len(candidates) >= 5:
        confidence = "high"
    elif len(direct_names) >= 1:
        confidence = "medium"
    else:
        confidence = "low"

    summary = (
        f"Identified {len(direct_names)} direct and {len(indirect_names)} indirect competitors "
        f"for {company_name}. Removed {len(removed)} non-competitors. "
        f"{'Added ' + str(len(gap_additions)) + ' via gap analysis. ' if gap_additions else ''}"
        f"Confidence: {confidence}."
    )

    print(f"\n✓ Evaluation complete: {len(direct_names)} direct, {len(indirect_names)} indirect, "
          f"{len(removed)} removed, {len(gap_additions)} added via gap analysis")

    # Save artifacts
    if output_dir:
        _save_evaluation_artifact(
            output_dir, evaluated_competitors, removed, gap_additions, company_name, summary
        )
        print(f"  Artifacts saved to {output_dir}/")

    competitive_landscape = {
        "evaluated_competitors": evaluated_competitors,
        "direct_competitors": direct_names,
        "indirect_competitors": indirect_names,
        "removed_as_non_competitors": removed,
        "added_via_gap_analysis": gap_additions,
        "evaluation_summary": summary,
        "confidence": confidence,
    }

    return {
        "competitive_landscape": competitive_landscape,
        "messages": [
            f"Competitive evaluation: {len(direct_names)} direct, {len(indirect_names)} indirect, {len(removed)} removed",
            f"Gap analysis added {len(gap_additions)} previously missed competitors" if gap_additions else "No gaps identified",
        ],
    }

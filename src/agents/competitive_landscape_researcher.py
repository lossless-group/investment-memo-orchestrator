"""
Competitive Landscape Researcher Agent.

Discovers candidate competitors through multi-query web research using Perplexity
Sonar Pro. Produces a broad initial list with structured data for each candidate.

Runs in the research phase, after section_research, before the evaluator.
Source priority: dataroom → deck → web research.

See context-v/Introducing-a-Competitive-Landscape-Research-and-Evaluation-System.md
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state import MemoState
from ..utils import get_output_dir_from_state


QUERY_GENERATION_PROMPT = """You are a competitive intelligence analyst. Given information about a company,
generate exactly 5 search queries that would help find their actual competitors.

Company: {company_name}
Description: {description}
Stage: {stage}
Market Category: {market_category}

IMPORTANT:
- Be SPECIFIC. "metabolic health companies" is too broad. "enzyme supplement startups" is better.
- Vary your angles: direct competitor queries, product-type queries, alternative-seeking queries.
- Include the company name in at least one query.
- Focus on finding companies at a similar stage and in the same niche.

{user_variants_section}

Return a JSON array of exactly 5 search query strings. No other text.
"""

COMPETITOR_EXTRACTION_PROMPT = """You are a competitive intelligence analyst researching competitors for {company_name}.

Company description: {description}

Search query: "{query}"

Based on your knowledge and search results, identify companies that could be competitors.
For EACH company found, provide structured data.

IMPORTANT:
- Only include companies that actually exist
- Do NOT fabricate funding amounts, employee counts, or URLs
- If you don't know a data point, use null
- Include the source URL where you found information about each company

Return valid JSON:
{{
    "competitors": [
        {{
            "name": "Company Name",
            "description": "What they do (1-2 sentences)",
            "website": "https://...",
            "founded": "2020",
            "funding_total": "$10M",
            "funding_stage": "Series A",
            "notable_investors": ["Investor 1", "Investor 2"],
            "employee_count": "50-100",
            "online_presence": {{
                "linkedin": "https://linkedin.com/company/...",
                "crunchbase": "https://crunchbase.com/organization/...",
                "twitter": "https://twitter.com/..."
            }},
            "key_differentiator": "How they approach the market",
            "overlap_description": "Why they might compete with {company_name}"
        }}
    ]
}}

When capturing online presence, use these exact keys when the profile is found:
  crunchbase, pitchbook, linkedin, twitter, github, website, traxcn,
  brandfetch, producthunt, figma, dribbble, angellist, glassdoor,
  capterra, g2, trustpilot, techcrunch_profile, ycombinator

For platforms not in this list, use a lowercase snake_case key.
Only include profiles you actually find with valid URLs. Do not guess or fabricate profile URLs.
"""


def _extract_market_category(state: MemoState) -> str:
    """Extract a specific market category from available state data."""
    parts = []

    deck = state.get("deck_analysis")
    if deck:
        if deck.get("product_description"):
            parts.append(deck["product_description"])
        if deck.get("business_model"):
            parts.append(deck["business_model"])

    research = state.get("research")
    if research and isinstance(research, dict):
        market = research.get("market", {})
        if isinstance(market, dict):
            for key in ("category", "description", "sector"):
                if market.get(key):
                    parts.append(str(market[key]))

    description = state.get("company_description", "")
    if description:
        parts.append(description)

    return "; ".join(parts[:3]) if parts else "technology startup"


def _get_deck_competitors(state: MemoState) -> List[Dict[str, Any]]:
    """Extract competitor names mentioned in the deck."""
    competitors = []
    deck = state.get("deck_analysis")
    if not deck:
        return competitors

    competitive = deck.get("competitive_landscape", "")
    if competitive and isinstance(competitive, str):
        competitors.append({
            "source": "deck",
            "raw_text": competitive,
        })

    return competitors


def _get_dataroom_competitors(state: MemoState) -> List[Dict[str, str]]:
    """Extract competitor data from dataroom analysis."""
    competitors = []
    dataroom = state.get("dataroom_analysis")
    if not dataroom or not isinstance(dataroom, dict):
        return competitors

    competitive_data = dataroom.get("competitive_data", {})
    if isinstance(competitive_data, dict):
        for name, details in competitive_data.items():
            entry = {"name": name, "from_dataroom": True}
            if isinstance(details, dict):
                entry.update(details)
            elif isinstance(details, str):
                entry["description"] = details
            competitors.append(entry)

    return competitors


def _generate_queries(
    company_name: str,
    description: str,
    stage: str,
    market_category: str,
    search_variants: List[str],
    perplexity_client,
) -> List[str]:
    """Generate search queries using LLM, supplemented with user variants."""
    user_variants_section = ""
    if search_variants:
        user_variants_section = (
            f"The user has suggested these search terms as particularly relevant:\n"
            + "\n".join(f"- {v}" for v in search_variants)
            + "\n\nIncorporate these into your queries where useful, but still generate 5 total queries."
        )

    prompt = QUERY_GENERATION_PROMPT.format(
        company_name=company_name,
        description=description or "N/A",
        stage=stage or "Early-stage",
        market_category=market_category,
        user_variants_section=user_variants_section,
    )

    try:
        response = perplexity_client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {"role": "system", "content": "Return ONLY a JSON array of strings. No other text."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1000,
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        # Parse JSON array
        content = re.sub(r"```(?:json)?\s*", "", content)
        content = re.sub(r"```\s*$", "", content)
        queries = json.loads(content)
        if isinstance(queries, list):
            return [q for q in queries if isinstance(q, str)][:5]
    except Exception as e:
        print(f"    Warning: Query generation failed: {e}")

    # Fallback: generate basic queries
    return [
        f"competitors of {company_name}",
        f"{description or company_name} startups",
        f"companies similar to {company_name}",
        f"alternatives to {company_name}",
        f"{market_category} companies {stage or ''}".strip(),
    ]


def _search_for_competitors(
    query: str,
    company_name: str,
    description: str,
    perplexity_client,
) -> List[Dict[str, Any]]:
    """Execute a single search query and extract competitor candidates."""
    prompt = COMPETITOR_EXTRACTION_PROMPT.format(
        company_name=company_name,
        description=description or "N/A",
        query=query,
    )

    try:
        response = perplexity_client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {"role": "system", "content": "You are a competitive intelligence analyst. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"```(?:json)?\s*", "", content)
        content = re.sub(r"```\s*$", "", content)

        # Try to parse JSON
        result = json.loads(content)
        if isinstance(result, dict) and "competitors" in result:
            return result["competitors"]
        elif isinstance(result, list):
            return result
    except json.JSONDecodeError:
        # Try to find JSON in response
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, dict) and "competitors" in result:
                    return result["competitors"]
            except json.JSONDecodeError:
                pass
    except Exception as e:
        print(f"    Warning: Search failed for query '{query[:50]}...': {e}")

    return []


def _deduplicate_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate candidates by name, merging data from multiple sources."""
    seen = {}
    for c in candidates:
        name = c.get("name", "").strip().lower()
        if not name:
            continue

        if name in seen:
            existing = seen[name]
            # Merge source queries
            existing.setdefault("source_queries", [])
            existing["source_queries"].extend(c.get("source_queries", []))
            # Merge source URLs
            existing.setdefault("source_urls", [])
            existing["source_urls"].extend(c.get("source_urls", []))
            # Fill in missing fields
            for key, val in c.items():
                if key not in existing or not existing[key]:
                    existing[key] = val
        else:
            seen[name] = c

    return list(seen.values())


def _save_research_artifact(output_dir: Path, candidates: List[Dict], queries: List[str], company_name: str):
    """Save competitive research artifact to 1-competitive-research.md."""
    lines = [
        f"# Competitive Landscape Research: {company_name}",
        f"",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Queries executed**: {len(queries)}",
        f"**Candidates found**: {len(candidates)}",
        f"",
        f"## Search Queries",
        f"",
    ]
    for i, q in enumerate(queries, 1):
        lines.append(f"{i}. `{q}`")
    lines.append("")

    lines.append("## Candidate Competitors")
    lines.append("")

    for c in candidates:
        name = c.get("name", "Unknown")
        lines.append(f"### {name}")
        lines.append(f"")
        if c.get("description"):
            lines.append(f"**Description**: {c['description']}")
        if c.get("website"):
            lines.append(f"**Website**: {c['website']}")
        if c.get("founded"):
            lines.append(f"**Founded**: {c['founded']}")
        if c.get("funding_total"):
            lines.append(f"**Funding**: {c['funding_total']} ({c.get('funding_stage', 'N/A')})")
        if c.get("key_differentiator"):
            lines.append(f"**Key Differentiator**: {c['key_differentiator']}")
        if c.get("overlap_description"):
            lines.append(f"**Overlap**: {c['overlap_description']}")
        if c.get("from_deck"):
            lines.append(f"**Source**: Mentioned in pitch deck")
        if c.get("from_dataroom"):
            lines.append(f"**Source**: From dataroom analysis")
        lines.append(f"**Found via**: {', '.join(c.get('source_queries', []))}")
        lines.append("")

    content = "\n".join(lines)
    artifact_path = output_dir / "1-competitive-research.md"
    artifact_path.write_text(content)

    # Also save structured JSON
    json_path = output_dir / "1-competitive-research.json"
    json_path.write_text(json.dumps({
        "queries": queries,
        "candidates": candidates,
        "generated_at": datetime.now().isoformat(),
    }, indent=2, ensure_ascii=False, default=str))


def competitive_landscape_researcher(state: MemoState) -> Dict[str, Any]:
    """
    Competitive Landscape Researcher Agent.

    Discovers candidate competitors through multi-query web research.
    Source priority: dataroom → deck → web research.

    Args:
        state: Current memo state

    Returns:
        State update with competitive_candidates
    """
    company_name = state["company_name"]
    description = state.get("company_description", "")
    stage = state.get("company_stage", "")

    # Check for Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        print("Warning: PERPLEXITY_API_KEY not set, skipping competitive landscape research")
        return {
            "messages": ["Competitive landscape research skipped — no Perplexity API key"]
        }

    print(f"\n🔍 Researching competitive landscape for {company_name}...")

    # Initialize Perplexity client
    from openai import OpenAI
    perplexity_client = OpenAI(
        api_key=perplexity_key,
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }
    )

    # Get output directory
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("  Warning: No output directory found")
        output_dir = None

    # --- Phase 1: Gather pre-existing competitor data ---

    all_candidates = []

    # Dataroom competitors (highest priority)
    dataroom_competitors = _get_dataroom_competitors(state)
    if dataroom_competitors:
        print(f"  Found {len(dataroom_competitors)} competitors from dataroom")
        for dc in dataroom_competitors:
            dc["from_dataroom"] = True
            dc["from_deck"] = False
            dc.setdefault("source_queries", ["dataroom"])
            dc.setdefault("source_urls", [])
            all_candidates.append(dc)

    # Deck competitors
    deck_competitors = _get_deck_competitors(state)
    if deck_competitors:
        print(f"  Found competitive context from pitch deck")
        # These are raw text, not structured — they'll be enriched by search

    # Known competitors from user config
    known = state.get("known_competitors", []) or []
    if known:
        print(f"  User-provided known competitors: {', '.join(known)}")
        for name in known:
            all_candidates.append({
                "name": name,
                "description": "",
                "from_deck": False,
                "from_dataroom": False,
                "source_queries": ["user_provided"],
                "source_urls": [],
            })

    # --- Phase 2: Generate and execute search queries ---

    market_category = _extract_market_category(state)
    search_variants = state.get("search_variants", []) or []

    queries = _generate_queries(
        company_name=company_name,
        description=description,
        stage=stage,
        market_category=market_category,
        search_variants=search_variants,
        perplexity_client=perplexity_client,
    )

    print(f"  Executing {len(queries)} search queries:")
    for i, q in enumerate(queries, 1):
        print(f"    {i}. {q}")

    for query in queries:
        results = _search_for_competitors(
            query=query,
            company_name=company_name,
            description=description,
            perplexity_client=perplexity_client,
        )
        for r in results:
            # Skip the subject company itself
            if r.get("name", "").lower().strip() == company_name.lower().strip():
                continue
            r["source_queries"] = [query]
            r.setdefault("source_urls", [])
            r.setdefault("from_deck", False)
            r.setdefault("from_dataroom", False)
            all_candidates.append(r)
        print(f"    → Found {len(results)} candidates")

    # --- Phase 3: Deduplicate ---

    candidates = _deduplicate_candidates(all_candidates)
    print(f"\n  Total unique candidates after dedup: {len(candidates)}")

    # --- Save artifacts ---

    if output_dir:
        _save_research_artifact(output_dir, candidates, queries, company_name)
        print(f"  Artifacts saved to {output_dir}/")

    # --- Build state update ---

    competitive_research = {
        "candidates": candidates,
        "queries_executed": queries,
        "total_candidates_found": len(candidates),
        "sources_consulted": len(queries),
        "search_variants_used": search_variants,
    }

    return {
        "competitive_candidates": competitive_research,
        "messages": [
            f"Competitive landscape research: found {len(candidates)} candidate competitors from {len(queries)} queries"
        ],
    }

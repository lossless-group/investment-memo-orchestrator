#!/usr/bin/env python3
"""
CLI tool for scoring an existing memo against a scorecard.

Usage:
    # Firm-scoped (recommended):
    python cli/score_memo.py --firm hypernova --deal Aalo --scorecard hypernova-early-stage-12Ps
    python cli/score_memo.py --firm hypernova --deal Aalo --version v0.0.5

    # Legacy:
    python cli/score_memo.py "Company Name" --scorecard hypernova-early-stage-12Ps
    python cli/score_memo.py output/Sava-v0.0.2 --scorecard hypernova-early-stage-12Ps
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.scorecard_loader import (
    load_scorecard,
    ScorecardDefinition,
    DimensionDefinition,
    get_percentile_label,
    get_score_label,
)
from src.utils import get_latest_output_dir
from src.paths import resolve_deal_context, get_latest_output_dir_for_deal, DealContext


def find_output_dir(company_or_path: str) -> Path:
    """
    Find the output directory for a company or use provided path.

    Args:
        company_or_path: Company name or direct path to output directory

    Returns:
        Path to output directory
    """
    path = Path(company_or_path)

    # If it's a directory path, use it directly
    if path.is_dir():
        return path

    # Otherwise, try to find by company name
    try:
        return get_latest_output_dir(company_or_path)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Could not find output directory for: {company_or_path}\n"
            f"Tried: {path} and output/{company_or_path}-*"
        )


def load_sections(output_dir: Path) -> Dict[str, str]:
    """
    Load all section files from the output directory.

    Args:
        output_dir: Path to output directory

    Returns:
        Dict mapping section filename to content
    """
    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        raise FileNotFoundError(f"Sections directory not found: {sections_dir}")

    sections = {}
    for section_file in sorted(sections_dir.glob("*.md")):
        sections[section_file.stem] = section_file.read_text()

    return sections


def load_research(output_dir: Path) -> Dict[str, Any]:
    """Load research data if available."""
    research_file = output_dir / "1-research.json"
    if research_file.exists():
        return json.loads(research_file.read_text())
    return {}


def load_state(output_dir: Path) -> Dict[str, Any]:
    """Load state snapshot if available."""
    state_file = output_dir / "state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {}


def get_section_for_dimension(dimension_id: str, sections: Dict[str, str]) -> str:
    """
    Map a dimension to its relevant section content.

    For 12Ps, the mapping is:
    - persona, pain, proposition -> 02-origins or 04-team
    - problem, possibility, positioning -> 03-market-context or 03-opening
    - people, process, product -> 04-team or 04-organization, 05-technology
    - potential, progress, plan -> 06-traction, 07-funding, 09-investment-thesis

    This function searches across all sections for relevant content.
    """
    # Build a combined text from all sections for searching
    all_content = "\n\n".join(sections.values())

    # For now, return all content - the LLM will extract what's relevant
    # In a more sophisticated version, we could do targeted extraction
    return all_content[:15000]  # Limit to ~15k chars


def score_dimension(
    dimension: DimensionDefinition,
    section_content: str,
    research: Dict[str, Any],
    company_name: str,
    model
) -> Dict[str, Any]:
    """
    Score a single dimension using LLM.

    Args:
        dimension: The dimension to score
        section_content: Relevant section content
        research: Research data
        company_name: Company name
        model: LLM model instance

    Returns:
        Dict with score, evidence, improvements
    """
    # Build rubric text
    rubric_text = "\n".join([
        f"  {score}: {desc}"
        for score, desc in sorted(dimension.scoring_rubric.levels.items(), reverse=True)
    ])

    # Build questions text
    questions_text = "\n".join([
        f"  - {q}"
        for q in dimension.evaluation_guidance.questions[:5]
    ])

    # Build evidence sources text
    evidence_text = "\n".join([
        f"  - {e}"
        for e in dimension.evaluation_guidance.evidence_sources[:5]
    ])

    # Build red flags text
    red_flags_text = "\n".join([
        f"  - {r}"
        for r in dimension.evaluation_guidance.red_flags[:5]
    ])

    prompt = f"""You are evaluating the "{dimension.name}" dimension for {company_name} using the 12Ps investment scorecard.

DIMENSION: {dimension.name} (#{dimension.number})
GROUP: {dimension.group}

DEFINITION:
{dimension.full_description}

EVALUATION QUESTIONS:
{questions_text}

EVIDENCE SOURCES TO LOOK FOR:
{evidence_text}

RED FLAGS:
{red_flags_text}

SCORING RUBRIC (1-5 scale):
{rubric_text}

===== MEMO CONTENT =====
{section_content[:12000]}
========================

Based on the memo content above, evaluate this dimension:

1. SCORE (1-5): What score does the evidence support based on the rubric?
2. EVIDENCE: What specific evidence from the memo supports this score? (2-3 sentences)
3. IMPROVEMENTS: What would make this score higher? (2-3 specific items)

Respond in JSON format:
{{
  "score": <1-5>,
  "evidence": "<summary of evidence supporting the score>",
  "improvements": ["<improvement 1>", "<improvement 2>", "<improvement 3>"]
}}

JSON Response:"""

    response = model.invoke(prompt)
    content = response.content.strip()

    # Extract JSON from response
    try:
        # Try to find JSON in the response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content)

        # Validate score is in range
        score = int(result.get("score", 3))
        score = max(1, min(5, score))
        result["score"] = score

        return result
    except (json.JSONDecodeError, ValueError) as e:
        print(f"      ⚠️  Failed to parse LLM response, using default score 3")
        return {
            "score": 3,
            "evidence": "Unable to parse evaluation response",
            "improvements": ["Evaluation needs manual review"]
        }


def generate_scorecard_markdown(
    company_name: str,
    scorecard: ScorecardDefinition,
    results: Dict[str, Dict[str, Any]]
) -> str:
    """
    Generate the scorecard markdown output.

    Args:
        company_name: Company name
        scorecard: Scorecard definition
        results: Dimension results {dimension_id: {score, evidence, improvements}}

    Returns:
        Markdown string
    """
    lines = []
    lines.append(f"# {company_name} 12Ps Scorecard Evaluation")
    lines.append("")
    lines.append(f"**Company**: {company_name}")
    lines.append(f"**Scorecard**: {scorecard.metadata.name}")
    lines.append(f"**Date**: {datetime.now().strftime('%B %d, %Y')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Calculate group averages
    group_scores = {}
    for group in scorecard.dimension_groups:
        group_dims = group.dimensions or group.synthesis_of or []
        scores = [results[d]["score"] for d in group_dims if d in results]
        if scores:
            group_scores[group.group_id] = sum(scores) / len(scores)

    # Overall score
    all_scores = [r["score"] for r in results.values()]
    overall_score = sum(all_scores) / len(all_scores) if all_scores else 0

    lines.append("## Scorecard Summary")
    lines.append("")
    lines.append("| Group | Dimensions | Avg Score |")
    lines.append("|-------|-----------|-----------|")
    for group in scorecard.dimension_groups:
        dim_names = ", ".join([
            scorecard.dimensions[d].name
            for d in (group.dimensions or group.synthesis_of or [])
            if d in scorecard.dimensions
        ])
        avg = group_scores.get(group.group_id, 0)
        lines.append(f"| {group.name} | {dim_names} | {avg:.1f}/5 |")
    lines.append("")
    lines.append(f"**Overall Score: {overall_score:.1f}/5**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Detailed sections by group
    for group in scorecard.dimension_groups:
        lines.append(f"## {group.name}")
        lines.append("")
        lines.append(f"*\"{group.description}\"*")
        lines.append("")

        # Group scorecard table
        dim_ids = group.dimensions or group.synthesis_of or []
        if dim_ids:
            headers = [scorecard.dimensions[d].name for d in dim_ids if d in scorecard.dimensions]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join(["------" for _ in headers]) + "|")

            # Scores row
            scores = [f"**{results[d]['score']}/5**" for d in dim_ids if d in results]
            lines.append("| " + " | ".join(scores) + " |")

            # Percentiles row
            percentiles = [
                get_percentile_label(scorecard, results[d]["score"])
                for d in dim_ids if d in results
            ]
            lines.append("| " + " | ".join(percentiles) + " |")
            lines.append("")

        # Individual dimension details
        for dim_id in dim_ids:
            if dim_id not in scorecard.dimensions or dim_id not in results:
                continue

            dim = scorecard.dimensions[dim_id]
            result = results[dim_id]

            lines.append(f"### {dim.number}. {dim.name} — **{result['score']}/5** ({get_score_label(scorecard, result['score'])})")
            lines.append("")
            lines.append(f"**{dim.short_description}**")
            lines.append("")
            lines.append(f"**Evidence**: {result['evidence']}")
            lines.append("")
            lines.append("**What Could Make This Score Higher**:")
            for improvement in result.get("improvements", []):
                lines.append(f"- {improvement}")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Summary sections
    lines.append("## Key Findings")
    lines.append("")

    # Strengths (4+)
    strengths = [(d, r) for d, r in results.items() if r["score"] >= 4]
    if strengths:
        lines.append("### Standout Strengths (Scores of 4+)")
        lines.append("")
        for dim_id, result in strengths:
            dim = scorecard.dimensions[dim_id]
            lines.append(f"- **{dim.name} ({result['score']}/5)**: {result['evidence'][:100]}...")
        lines.append("")

    # Concerns (1-2)
    concerns = [(d, r) for d, r in results.items() if r["score"] <= 2]
    if concerns:
        lines.append("### Areas of Concern (Scores of 1-2)")
        lines.append("")
        for dim_id, result in concerns:
            dim = scorecard.dimensions[dim_id]
            lines.append(f"- **{dim.name} ({result['score']}/5)**: {result['evidence'][:100]}...")
        lines.append("")

    # Overall
    lines.append(f"## Overall Score: {overall_score:.1f}/5")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Score an existing memo against a scorecard"
    )
    parser.add_argument(
        "company",
        nargs="?",
        help="Company name or path to output directory. Optional if --firm and --deal are provided."
    )
    parser.add_argument(
        "--firm",
        help="Firm name for firm-scoped IO (e.g., 'hypernova'). Uses io/{firm}/deals/{deal}/"
    )
    parser.add_argument(
        "--deal",
        help="Deal name when using --firm. Required if --firm is provided."
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.1'). If not specified, uses latest."
    )
    parser.add_argument(
        "--scorecard",
        default="hypernova-early-stage-12Ps",
        help="Scorecard name (default: hypernova-early-stage-12Ps)"
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: {output_dir}/5-scorecard/12Ps-scorecard.md)"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        help="Model to use for evaluation"
    )

    args = parser.parse_args()

    # Check for MEMO_DEFAULT_FIRM environment variable if --firm not provided
    if not args.firm:
        args.firm = os.environ.get("MEMO_DEFAULT_FIRM")
        if args.firm:
            print(f"📌 Using MEMO_DEFAULT_FIRM: {args.firm}")

    # Validate arguments
    if args.firm and not args.deal:
        print("❌ --deal is required when --firm is provided")
        sys.exit(1)

    if not args.firm and not args.company:
        print("❌ Either provide a company name/path or use --firm and --deal")
        sys.exit(1)

    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    # Find output directory
    deal_name = args.deal or args.company
    output_dir = None

    if args.firm:
        print(f"\n📂 Finding output for firm: {args.firm}, deal: {args.deal}")
        ctx = resolve_deal_context(args.deal, firm=args.firm)

        if not ctx.outputs_dir or not ctx.outputs_dir.exists():
            print(f"❌ Outputs directory not found for {args.firm}/{args.deal}")
            print(f"   Expected: {ctx.outputs_dir}")
            sys.exit(1)

        if args.version:
            output_dir = ctx.get_version_output_dir(args.version)
        else:
            try:
                output_dir = get_latest_output_dir_for_deal(ctx)
            except FileNotFoundError as e:
                print(f"❌ {e}")
                sys.exit(1)
    else:
        print(f"\n📂 Finding output directory for: {args.company}")
        try:
            output_dir = find_output_dir(args.company)
        except FileNotFoundError as e:
            print(f"❌ {e}")
            sys.exit(1)

    print(f"   Found: {output_dir}")

    # Load scorecard
    print(f"\n📊 Loading scorecard: {args.scorecard}")
    try:
        scorecard = load_scorecard(args.scorecard)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Load memo sections
    print(f"\n📄 Loading memo sections...")
    try:
        sections = load_sections(output_dir)
        print(f"   Loaded {len(sections)} sections")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Load research and state
    research = load_research(output_dir)
    state = load_state(output_dir)
    company_name = state.get("company_name", args.company)

    # Initialize LLM
    from langchain_anthropic import ChatAnthropic
    model = ChatAnthropic(
        model=args.model,
        api_key=api_key,
        temperature=0.3,  # Lower temperature for consistent scoring
        max_tokens=1000
    )

    # Score each dimension
    print(f"\n🎯 Scoring {len(scorecard.dimensions)} dimensions...")
    results = {}

    for dim_id, dimension in scorecard.dimensions.items():
        print(f"   [{dimension.number}/12] {dimension.name}...", end=" ", flush=True)

        section_content = get_section_for_dimension(dim_id, sections)
        result = score_dimension(
            dimension=dimension,
            section_content=section_content,
            research=research,
            company_name=company_name,
            model=model
        )
        results[dim_id] = result
        print(f"{result['score']}/5")

    # Generate output
    print(f"\n📝 Generating scorecard output...")
    markdown = generate_scorecard_markdown(company_name, scorecard, results)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        scorecard_dir = output_dir / "5-scorecard"
        scorecard_dir.mkdir(exist_ok=True)
        output_path = scorecard_dir / "12Ps-scorecard.md"

    # Write markdown
    output_path.write_text(markdown)
    print(f"   ✓ Saved: {output_path}")

    # Write JSON
    json_path = output_path.with_suffix(".json")
    json_output = {
        "scorecard_name": args.scorecard,
        "company": company_name,
        "date": datetime.now().isoformat(),
        "overall_score": sum(r["score"] for r in results.values()) / len(results),
        "dimensions": results
    }
    json_path.write_text(json.dumps(json_output, indent=2))
    print(f"   ✓ Saved: {json_path}")

    # Print summary
    overall = json_output["overall_score"]
    print(f"\n✅ Scorecard complete!")
    print(f"   Overall Score: {overall:.1f}/5")
    print(f"   Strengths: {sum(1 for r in results.values() if r['score'] >= 4)}")
    print(f"   Concerns: {sum(1 for r in results.values() if r['score'] <= 2)}")


if __name__ == "__main__":
    main()

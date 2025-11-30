"""
Scorecard Evaluator Agent - Scores memo sections against scorecard dimensions.

This agent evaluates completed memo sections and produces dimension scores
using a loaded scorecard definition (e.g., 12Ps framework).

It runs AFTER sections are written and validated, producing a comprehensive
scorecard evaluation with scores, evidence, and improvement suggestions.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from langchain_anthropic import ChatAnthropic

from ..state import MemoState, ScorecardResults, DimensionScore
from ..scorecard_loader import (
    load_scorecard,
    ScorecardDefinition,
    DimensionDefinition,
    get_percentile_label,
    get_score_label,
)
from ..utils import get_latest_output_dir


def load_sections_from_dir(output_dir: Path) -> Dict[str, str]:
    """
    Load all section files from the output directory.

    Args:
        output_dir: Path to output directory

    Returns:
        Dict mapping section filename (stem) to content
    """
    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        raise FileNotFoundError(f"Sections directory not found: {sections_dir}")

    sections = {}
    for section_file in sorted(sections_dir.glob("*.md")):
        sections[section_file.stem] = section_file.read_text()

    return sections


def get_all_section_content(sections: Dict[str, str], max_chars: int = 15000) -> str:
    """
    Combine all sections into a single text block.

    Args:
        sections: Dict of section content
        max_chars: Maximum characters to return

    Returns:
        Combined section content
    """
    all_content = "\n\n---\n\n".join([
        f"## {name}\n\n{content}"
        for name, content in sorted(sections.items())
    ])
    return all_content[:max_chars]


def score_dimension(
    dimension: DimensionDefinition,
    section_content: str,
    company_name: str,
    model: ChatAnthropic
) -> DimensionScore:
    """
    Score a single dimension using LLM.

    Args:
        dimension: The dimension to score
        section_content: Relevant section content
        company_name: Company name
        model: LLM model instance

    Returns:
        DimensionScore with score, percentile, evidence, improvements
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

    # Invoke with retry logic
    import time
    from anthropic import InternalServerError, RateLimitError

    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            response = model.invoke(prompt)
            content = response.content.strip()
            break
        except (InternalServerError, RateLimitError) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                print(f"      ⚠️  API error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                time.sleep(wait_time)
            else:
                print(f"      ❌ API error after {max_retries} attempts")
                return DimensionScore(
                    score=3,
                    percentile="Top 50%",
                    evidence="Unable to evaluate due to API error",
                    improvements=["Evaluation needs manual review"]
                )

    # Extract JSON from response
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content)

        # Validate and clamp score
        score = int(result.get("score", 3))
        score = max(1, min(5, score))

        return DimensionScore(
            score=score,
            percentile=get_percentile_label_simple(score),
            evidence=result.get("evidence", "No evidence provided"),
            improvements=result.get("improvements", [])
        )
    except (json.JSONDecodeError, ValueError) as e:
        print(f"      ⚠️  Failed to parse LLM response, using default score 3")
        return DimensionScore(
            score=3,
            percentile="Top 50%",
            evidence="Unable to parse evaluation response",
            improvements=["Evaluation needs manual review"]
        )


def get_percentile_label_simple(score: int) -> str:
    """Simple percentile mapping without needing scorecard."""
    mapping = {
        5: "Top 5%",
        4: "Top 10-25%",
        3: "Top 50%",
        2: "Bottom 50%",
        1: "Bottom 25%"
    }
    return mapping.get(score, f"Score {score}")


def generate_diligence_questions(
    scorecard: ScorecardDefinition,
    results: Dict[str, DimensionScore]
) -> List[str]:
    """
    Generate diligence questions based on low-scoring dimensions.

    Args:
        scorecard: Scorecard definition
        results: Dimension scores

    Returns:
        List of diligence questions
    """
    questions = []

    for dim_id, score in results.items():
        if score["score"] <= 2 and dim_id in scorecard.dimensions:
            dim = scorecard.dimensions[dim_id]
            # Add first 2 evaluation questions for low-scoring dimensions
            for q in dim.evaluation_guidance.questions[:2]:
                questions.append(f"[{dim.name}] {q}")

    return questions[:7]  # Limit to 7 questions


def save_scorecard_artifacts(
    output_dir: Path,
    company_name: str,
    scorecard: ScorecardDefinition,
    results: Dict[str, DimensionScore],
    overall_score: float,
    group_scores: Dict[str, float],
    strengths: List[str],
    concerns: List[str],
    diligence_questions: List[str]
) -> None:
    """
    Save scorecard artifacts to output directory.

    Args:
        output_dir: Output directory path
        company_name: Company name
        scorecard: Scorecard definition
        results: Dimension scores
        overall_score: Overall average score
        group_scores: Group average scores
        strengths: High-scoring dimension IDs
        concerns: Low-scoring dimension IDs
        diligence_questions: Generated questions
    """
    scorecard_dir = output_dir / "5-scorecard"
    scorecard_dir.mkdir(exist_ok=True)

    # Generate markdown
    lines = []
    lines.append(f"# {company_name} 12Ps Scorecard Evaluation")
    lines.append("")
    lines.append(f"**Company**: {company_name}")
    lines.append(f"**Scorecard**: {scorecard.metadata.name}")
    lines.append(f"**Date**: {datetime.now().strftime('%B %d, %Y')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary table
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

    # Detailed sections
    for group in scorecard.dimension_groups:
        lines.append(f"## {group.name}")
        lines.append("")
        lines.append(f"*\"{group.description}\"*")
        lines.append("")

        dim_ids = group.dimensions or group.synthesis_of or []
        if dim_ids:
            # Scorecard table
            headers = [scorecard.dimensions[d].name for d in dim_ids if d in scorecard.dimensions]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join(["------" for _ in headers]) + "|")

            scores = [f"**{results[d]['score']}/5**" for d in dim_ids if d in results]
            lines.append("| " + " | ".join(scores) + " |")

            percentiles = [results[d]["percentile"] for d in dim_ids if d in results]
            lines.append("| " + " | ".join(percentiles) + " |")
            lines.append("")

        # Dimension details
        for dim_id in dim_ids:
            if dim_id not in scorecard.dimensions or dim_id not in results:
                continue

            dim = scorecard.dimensions[dim_id]
            result = results[dim_id]

            lines.append(f"### {dim.number}. {dim.name} — **{result['score']}/5**")
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

    # Key findings
    lines.append("## Key Findings")
    lines.append("")

    if strengths:
        lines.append("### Standout Strengths (Scores of 4+)")
        lines.append("")
        for dim_id in strengths:
            if dim_id in scorecard.dimensions and dim_id in results:
                dim = scorecard.dimensions[dim_id]
                result = results[dim_id]
                lines.append(f"- **{dim.name} ({result['score']}/5)**: {result['evidence'][:100]}...")
        lines.append("")

    if concerns:
        lines.append("### Areas of Concern (Scores of 1-2)")
        lines.append("")
        for dim_id in concerns:
            if dim_id in scorecard.dimensions and dim_id in results:
                dim = scorecard.dimensions[dim_id]
                result = results[dim_id]
                lines.append(f"- **{dim.name} ({result['score']}/5)**: {result['evidence'][:100]}...")
        lines.append("")

    if diligence_questions:
        lines.append("### Critical Questions for Diligence")
        lines.append("")
        for q in diligence_questions:
            lines.append(f"- {q}")
        lines.append("")

    lines.append(f"## Overall Score: {overall_score:.1f}/5")

    # Save markdown
    md_path = scorecard_dir / "12Ps-scorecard.md"
    md_path.write_text("\n".join(lines))
    print(f"   ✓ Saved: {md_path}")

    # Save JSON
    json_output = {
        "scorecard_name": scorecard.metadata.scorecard_id,
        "company": company_name,
        "date": datetime.now().isoformat(),
        "overall_score": overall_score,
        "group_scores": group_scores,
        "dimensions": {
            dim_id: {
                "score": score["score"],
                "percentile": score["percentile"],
                "evidence": score["evidence"],
                "improvements": score.get("improvements", [])
            }
            for dim_id, score in results.items()
        },
        "strengths": strengths,
        "concerns": concerns,
        "diligence_questions": diligence_questions
    }

    json_path = scorecard_dir / "12Ps-scorecard.json"
    json_path.write_text(json.dumps(json_output, indent=2))
    print(f"   ✓ Saved: {json_path}")


def scorecard_evaluator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Scorecard Evaluator Agent - Scores memo against scorecard dimensions.

    This agent runs after validation to produce a comprehensive scorecard
    evaluation with dimension scores, evidence, and improvement suggestions.

    Args:
        state: Current memo state

    Returns:
        Updated state with scorecard_results populated
    """
    company_name = state["company_name"]
    scorecard_name = state.get("scorecard_name")

    # Skip if no scorecard specified
    if not scorecard_name:
        print("\n📊 Scorecard Evaluator: No scorecard specified, skipping")
        return {
            "messages": ["Scorecard evaluation skipped (no scorecard specified)"]
        }

    print(f"\n📊 Scorecard Evaluator: Evaluating {company_name}")
    print(f"   Scorecard: {scorecard_name}")

    # Load scorecard
    try:
        scorecard = load_scorecard(scorecard_name)
    except FileNotFoundError as e:
        print(f"   ❌ Scorecard not found: {e}")
        return {
            "messages": [f"Scorecard evaluation failed: {e}"]
        }

    # Find output directory
    try:
        output_dir = get_latest_output_dir(company_name)
    except FileNotFoundError as e:
        print(f"   ❌ Output directory not found: {e}")
        return {
            "messages": [f"Scorecard evaluation failed: {e}"]
        }

    # Load sections
    try:
        sections = load_sections_from_dir(output_dir)
        print(f"   Loaded {len(sections)} sections")
    except FileNotFoundError as e:
        print(f"   ❌ Sections not found: {e}")
        return {
            "messages": [f"Scorecard evaluation failed: {e}"]
        }

    # Initialize LLM
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("   ❌ ANTHROPIC_API_KEY not set")
        return {
            "messages": ["Scorecard evaluation failed: API key not set"]
        }

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0.3,  # Lower temperature for consistent scoring
        max_tokens=1000
    )

    # Get all section content for evaluation
    all_content = get_all_section_content(sections)

    # Score each dimension
    print(f"\n   Scoring {len(scorecard.dimensions)} dimensions...")
    results: Dict[str, DimensionScore] = {}

    for dim_id, dimension in scorecard.dimensions.items():
        print(f"   [{dimension.number}/12] {dimension.name}...", end=" ", flush=True)

        result = score_dimension(
            dimension=dimension,
            section_content=all_content,
            company_name=company_name,
            model=model
        )
        results[dim_id] = result
        print(f"{result['score']}/5")

    # Calculate group scores
    group_scores = {}
    for group in scorecard.dimension_groups:
        group_dims = group.dimensions or group.synthesis_of or []
        scores = [results[d]["score"] for d in group_dims if d in results]
        if scores:
            group_scores[group.group_id] = sum(scores) / len(scores)

    # Calculate overall score
    all_scores = [r["score"] for r in results.values()]
    overall_score = sum(all_scores) / len(all_scores) if all_scores else 0

    # Identify strengths and concerns
    strengths = [d for d, r in results.items() if r["score"] >= 4]
    concerns = [d for d, r in results.items() if r["score"] <= 2]

    # Generate diligence questions
    diligence_questions = generate_diligence_questions(scorecard, results)

    # Save artifacts
    print(f"\n   Saving scorecard artifacts...")
    save_scorecard_artifacts(
        output_dir=output_dir,
        company_name=company_name,
        scorecard=scorecard,
        results=results,
        overall_score=overall_score,
        group_scores=group_scores,
        strengths=strengths,
        concerns=concerns,
        diligence_questions=diligence_questions
    )

    # Build state results
    scorecard_results = ScorecardResults(
        scorecard_name=scorecard_name,
        overall_score=overall_score,
        dimensions=results,
        groups=group_scores,
        strengths=strengths,
        concerns=concerns,
        diligence_questions=diligence_questions
    )

    print(f"\n✅ Scorecard evaluation complete!")
    print(f"   Overall Score: {overall_score:.1f}/5")
    print(f"   Strengths: {len(strengths)} dimensions")
    print(f"   Concerns: {len(concerns)} dimensions")

    return {
        "scorecard_results": scorecard_results,
        "messages": [f"Scorecard evaluation complete: {overall_score:.1f}/5 overall ({len(strengths)} strengths, {len(concerns)} concerns)"]
    }

#!/usr/bin/env python3
"""
Standalone memo evaluation tool.

Evaluates the quality of each section in a memo, providing:
1. Per-section quality scores (0-10)
2. Fact-checking (claims vs citations)
3. Specific issues and improvement suggestions
4. Overall memo quality assessment

Usage:
    python -m cli.evaluate_memo "Sava"
    python -m cli.evaluate_memo "Sava" --version v0.0.2
    python -m cli.evaluate_memo output/Sava-v0.0.2
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from anthropic import Anthropic

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename
from src.versioning import VersionManager


@dataclass
class SectionEvaluation:
    """Evaluation result for a single section."""
    section_name: str
    filename: str
    word_count: int
    citation_count: int

    # Quality scores (0-10)
    content_depth: float
    specificity: float  # Uses concrete numbers vs vague language
    citation_quality: float  # Claims are properly cited
    analytical_tone: float  # Balanced, not promotional

    overall_score: float

    # Issues and suggestions
    strengths: List[str]
    issues: List[str]
    suggestions: List[str]

    # Fact-check summary
    total_claims: int
    cited_claims: int
    uncited_claims: int
    suspicious_claims: List[str]


@dataclass
class MemoEvaluation:
    """Complete memo evaluation."""
    company_name: str
    version: str
    timestamp: str

    total_words: int
    total_citations: int

    section_evaluations: List[SectionEvaluation]

    overall_score: float
    grade: str  # A, B, C, D, F

    top_issues: List[str]
    priority_improvements: List[str]


def count_citations(content: str) -> int:
    """Count inline citations in content."""
    return len(re.findall(r'\[\^\d+\]', content))


def extract_claims(content: str) -> List[Dict[str, Any]]:
    """Extract factual claims that should be cited."""
    claims = []

    # Patterns indicating factual claims
    patterns = {
        "metric": r'\b(\d+[KMB]?|[\d,]+)\s+(ARR|MRR|customers?|users?|revenue|MAU|DAU|employees?)',
        "financial": r'\$[\d,]+[KMB]?',
        "percentage": r'\b\d+(\.\d+)?%\b',
        "market_size": r'\$[\d.]+\s*(billion|million|trillion|B|M|T)',
        "growth": r'\b\d+%\s+(MoM|YoY|growth|CAGR)',
        "date_claim": r'\b(founded|launched|raised|acquired|grew)\s+in\s+20\d{2}',
        "funding": r'\$([\d.]+[KMB])\s+(seed|Series [A-Z]|raised|round|valuation)',
    }

    sentences = re.split(r'(?<=[.!?])\s+', content)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Skip sentences that acknowledge missing data
        if any(phrase in sentence.lower() for phrase in [
            'not available', 'not disclosed', 'not publicly', 'no data'
        ]):
            continue

        for claim_type, pattern in patterns.items():
            if re.search(pattern, sentence, re.IGNORECASE):
                has_citation = bool(re.search(r'\[\^\d+\]', sentence))
                claims.append({
                    "text": sentence[:150] + "..." if len(sentence) > 150 else sentence,
                    "type": claim_type,
                    "cited": has_citation
                })
                break

    return claims


def evaluate_section_with_llm(
    section_name: str,
    section_content: str,
    company_name: str,
    client: Anthropic,
    console: Console
) -> Dict[str, Any]:
    """Use Claude to evaluate section quality."""

    prompt = f"""Evaluate this investment memo section for {company_name}.

SECTION: {section_name}

CONTENT:
{section_content}

Evaluate on these criteria (score each 0-10):

1. **Content Depth** (0-10): Does the section provide substantive analysis with specific details?
   - 0-3: Thin, generic content that could apply to any company
   - 4-6: Basic coverage with some specifics
   - 7-8: Good depth with relevant details
   - 9-10: Exceptional depth with unique insights

2. **Specificity** (0-10): Uses concrete numbers, names, and data vs vague language?
   - 0-3: Heavy use of vague terms ("significant", "many", "growing rapidly")
   - 4-6: Mix of specific and vague
   - 7-8: Mostly specific with clear metrics
   - 9-10: Precise throughout with quantified claims

3. **Citation Quality** (0-10): Are factual claims properly cited?
   - 0-3: Major claims uncited, possible hallucinations
   - 4-6: Some citations but gaps
   - 7-8: Most claims cited
   - 9-10: Comprehensive sourcing

4. **Analytical Tone** (0-10): Balanced, objective analysis vs promotional language?
   - 0-3: Promotional, one-sided, uses superlatives
   - 4-6: Mostly balanced with some bias
   - 7-8: Professional and objective
   - 9-10: Rigorous analytical voice throughout

Return JSON:
{{
  "content_depth": 7.0,
  "specificity": 6.5,
  "citation_quality": 8.0,
  "analytical_tone": 7.5,
  "strengths": ["Specific strength 1", "Specific strength 2"],
  "issues": ["Specific issue 1", "Specific issue 2"],
  "suggestions": ["Actionable suggestion 1", "Actionable suggestion 2"]
}}

Be rigorous. High scores (8+) should be rare. Identify specific examples from the content."""

    response = client.messages.create(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse response
    content = response.content[0].text

    try:
        # Try direct JSON parse
        return json.loads(content)
    except json.JSONDecodeError:
        # Extract from markdown code block
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            return json.loads(content[json_start:json_end].strip())
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            return json.loads(content[json_start:json_end].strip())
        else:
            raise ValueError(f"Could not parse evaluation response: {content[:200]}")


def evaluate_section(
    section_file: Path,
    company_name: str,
    client: Anthropic,
    console: Console
) -> SectionEvaluation:
    """Evaluate a single section."""

    with open(section_file) as f:
        content = f.read()

    # Basic metrics
    word_count = len(content.split())
    citation_count = count_citations(content)

    # Extract and analyze claims
    claims = extract_claims(content)
    cited_claims = [c for c in claims if c["cited"]]
    uncited_claims = [c for c in claims if not c["cited"]]

    # Get LLM evaluation
    section_name = section_file.stem.split('-', 1)[1].replace('-', ' ').title() if '-' in section_file.stem else section_file.stem

    llm_eval = evaluate_section_with_llm(
        section_name=section_name,
        section_content=content,
        company_name=company_name,
        client=client,
        console=console
    )

    # Calculate overall score (weighted average)
    overall = (
        llm_eval["content_depth"] * 0.3 +
        llm_eval["specificity"] * 0.25 +
        llm_eval["citation_quality"] * 0.25 +
        llm_eval["analytical_tone"] * 0.2
    )

    return SectionEvaluation(
        section_name=section_name,
        filename=section_file.name,
        word_count=word_count,
        citation_count=citation_count,
        content_depth=llm_eval["content_depth"],
        specificity=llm_eval["specificity"],
        citation_quality=llm_eval["citation_quality"],
        analytical_tone=llm_eval["analytical_tone"],
        overall_score=round(overall, 1),
        strengths=llm_eval.get("strengths", []),
        issues=llm_eval.get("issues", []),
        suggestions=llm_eval.get("suggestions", []),
        total_claims=len(claims),
        cited_claims=len(cited_claims),
        uncited_claims=len(uncited_claims),
        suspicious_claims=[c["text"] for c in uncited_claims[:3]]  # Top 3
    )


def get_grade(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 9.0:
        return "A"
    elif score >= 8.0:
        return "A-"
    elif score >= 7.5:
        return "B+"
    elif score >= 7.0:
        return "B"
    elif score >= 6.5:
        return "B-"
    elif score >= 6.0:
        return "C+"
    elif score >= 5.5:
        return "C"
    elif score >= 5.0:
        return "C-"
    elif score >= 4.0:
        return "D"
    else:
        return "F"


def resolve_artifact_dir(company_or_path: str, version: Optional[str] = None) -> Path:
    """Resolve to artifact directory from company name or direct path."""

    path = Path(company_or_path)

    # Direct path
    if path.exists() and path.is_dir():
        return path

    # Company name - find in output/
    output_dir = Path("output")
    safe_name = sanitize_filename(company_or_path)

    if version:
        target = output_dir / f"{safe_name}-{version}"
        if target.exists():
            return target
        raise FileNotFoundError(f"Version not found: {target}")

    # Find latest version
    matches = sorted(output_dir.glob(f"{safe_name}-v*"), reverse=True)
    if matches:
        return matches[0]

    raise FileNotFoundError(f"No output found for: {company_or_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate memo section quality",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli.evaluate_memo "Sava"
  python -m cli.evaluate_memo "Sava" --version v0.0.2
  python -m cli.evaluate_memo output/Sava-v0.0.2
        """
    )
    parser.add_argument("company_or_path", help="Company name or path to artifact directory")
    parser.add_argument("--version", "-v", help="Specific version (e.g., v0.0.2)")
    parser.add_argument("--output", "-o", help="Save evaluation JSON to file")
    parser.add_argument("--brief", "-b", action="store_true", help="Brief output (scores only)")

    args = parser.parse_args()

    console = Console()

    # Resolve artifact directory
    try:
        artifact_dir = resolve_artifact_dir(args.company_or_path, args.version)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    sections_dir = artifact_dir / "2-sections"
    if not sections_dir.exists():
        console.print(f"[red]Error:[/red] No sections directory found at {sections_dir}")
        sys.exit(1)

    # Extract company name and version from directory
    dir_name = artifact_dir.name
    parts = dir_name.rsplit("-v", 1)
    company_name = parts[0].replace("-", " ")
    version = f"v{parts[1]}" if len(parts) == 2 else "unknown"

    console.print(Panel(
        f"[bold]Evaluating Memo Quality[/bold]\n\n"
        f"Company: {company_name}\n"
        f"Version: {version}\n"
        f"Path: {artifact_dir}",
        title="Memo Evaluation"
    ))

    # Initialize Anthropic client
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = Anthropic(api_key=api_key)

    # Get section files
    section_files = sorted(sections_dir.glob("*.md"))

    if not section_files:
        console.print("[red]Error:[/red] No section files found")
        sys.exit(1)

    console.print(f"\n[cyan]Evaluating {len(section_files)} sections...[/cyan]\n")

    # Evaluate each section
    evaluations = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        for section_file in section_files:
            section_name = section_file.stem.split('-', 1)[1].replace('-', ' ').title() if '-' in section_file.stem else section_file.stem
            task = progress.add_task(f"Evaluating: {section_name}...", total=None)

            try:
                evaluation = evaluate_section(
                    section_file=section_file,
                    company_name=company_name,
                    client=client,
                    console=console
                )
                evaluations.append(evaluation)
                progress.remove_task(task)

                # Show inline result
                score_color = "green" if evaluation.overall_score >= 7 else "yellow" if evaluation.overall_score >= 5 else "red"
                console.print(f"  [{score_color}]{evaluation.overall_score:.1f}[/{score_color}] {section_name} ({evaluation.word_count} words, {evaluation.citation_count} citations)")

            except Exception as e:
                progress.remove_task(task)
                console.print(f"  [red]Error evaluating {section_name}: {e}[/red]")

    # Calculate overall metrics
    total_words = sum(e.word_count for e in evaluations)
    total_citations = sum(e.citation_count for e in evaluations)
    overall_score = sum(e.overall_score for e in evaluations) / len(evaluations) if evaluations else 0
    grade = get_grade(overall_score)

    # Collect top issues across all sections
    all_issues = []
    for e in evaluations:
        for issue in e.issues:
            all_issues.append(f"[{e.section_name}] {issue}")

    # Collect priority improvements (from lowest-scoring sections)
    sorted_evals = sorted(evaluations, key=lambda x: x.overall_score)
    priority_improvements = []
    for e in sorted_evals[:3]:  # Bottom 3 sections
        if e.suggestions:
            priority_improvements.append(f"[{e.section_name}] {e.suggestions[0]}")

    # Create complete evaluation
    memo_eval = MemoEvaluation(
        company_name=company_name,
        version=version,
        timestamp=datetime.now().isoformat(),
        total_words=total_words,
        total_citations=total_citations,
        section_evaluations=evaluations,
        overall_score=round(overall_score, 1),
        grade=grade,
        top_issues=all_issues[:10],
        priority_improvements=priority_improvements
    )

    # Display results
    console.print("\n" + "="*70)
    console.print("[bold]EVALUATION SUMMARY[/bold]")
    console.print("="*70)

    # Score table
    table = Table(title="Section Scores")
    table.add_column("Section", style="cyan")
    table.add_column("Words", justify="right")
    table.add_column("Citations", justify="right")
    table.add_column("Depth", justify="right")
    table.add_column("Specificity", justify="right")
    table.add_column("Citations", justify="right")
    table.add_column("Tone", justify="right")
    table.add_column("Overall", justify="right", style="bold")

    for e in evaluations:
        score_style = "green" if e.overall_score >= 7 else "yellow" if e.overall_score >= 5 else "red"
        table.add_row(
            e.section_name[:25],
            str(e.word_count),
            str(e.citation_count),
            f"{e.content_depth:.1f}",
            f"{e.specificity:.1f}",
            f"{e.citation_quality:.1f}",
            f"{e.analytical_tone:.1f}",
            f"[{score_style}]{e.overall_score:.1f}[/{score_style}]"
        )

    console.print(table)

    # Overall summary
    grade_color = "green" if grade.startswith("A") or grade.startswith("B") else "yellow" if grade.startswith("C") else "red"

    console.print(f"\n[bold]Overall Score:[/bold] [{grade_color}]{overall_score:.1f}/10 ({grade})[/{grade_color}]")
    console.print(f"[bold]Total Words:[/bold] {total_words:,}")
    console.print(f"[bold]Total Citations:[/bold] {total_citations}")

    if not args.brief:
        # Top issues
        if memo_eval.top_issues:
            console.print("\n[bold red]Top Issues:[/bold red]")
            for issue in memo_eval.top_issues[:5]:
                console.print(f"  • {issue}")

        # Priority improvements
        if memo_eval.priority_improvements:
            console.print("\n[bold yellow]Priority Improvements:[/bold yellow]")
            for improvement in memo_eval.priority_improvements:
                console.print(f"  • {improvement}")

        # Lowest scoring sections
        console.print("\n[bold]Sections Needing Most Work:[/bold]")
        for e in sorted_evals[:3]:
            console.print(f"  • {e.section_name} ({e.overall_score:.1f}/10)")

    console.print("="*70)

    # Save evaluation if requested
    output_path = args.output or (artifact_dir / "evaluation.json")

    # Convert to dict for JSON serialization
    eval_dict = {
        "company_name": memo_eval.company_name,
        "version": memo_eval.version,
        "timestamp": memo_eval.timestamp,
        "total_words": memo_eval.total_words,
        "total_citations": memo_eval.total_citations,
        "overall_score": memo_eval.overall_score,
        "grade": memo_eval.grade,
        "top_issues": memo_eval.top_issues,
        "priority_improvements": memo_eval.priority_improvements,
        "section_evaluations": [asdict(e) for e in memo_eval.section_evaluations]
    }

    with open(output_path, "w") as f:
        json.dump(eval_dict, f, indent=2)

    console.print(f"\n[green]✓ Evaluation saved:[/green] {output_path}")

    # Return exit code based on score
    sys.exit(0 if overall_score >= 6.0 else 1)


if __name__ == "__main__":
    main()

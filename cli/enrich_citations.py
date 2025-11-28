#!/usr/bin/env python3
"""
Citation Enrichment CLI Tool.

Adds inline citations to a section WITHOUT rewriting the content.
Uses Perplexity Sonar Pro to find authoritative sources for existing claims.

This is different from improve_section.py which rewrites content.
This tool ONLY adds citations to support existing text.

Usage:
    python -m cli.enrich_citations "Sava" "Market Context"
    python -m cli.enrich_citations "Sava" "Market Context" --version v0.0.2
    python -m cli.enrich_citations output/Sava-v0.0.2 "Market Context"
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from openai import OpenAI

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename
from src.agents.citation_enrichment import enrich_section_with_citations, CITATION_ENRICHMENT_SYSTEM_PROMPT


# Section name to filename mapping
SECTION_MAP = {
    "Executive Summary": "01-executive-summary.md",
    "Business Overview": "02-business-overview.md",
    "Market Context": "03-market-context.md",
    "Team": "04-team.md",
    "Technology & Product": "05-technology--product.md",
    "Traction & Milestones": "06-traction--milestones.md",
    "Funding & Terms": "07-funding--terms.md",
    "Risks & Mitigations": "08-risks--mitigations.md",
    "Investment Thesis": "09-investment-thesis.md",
    "Recommendation": "10-recommendation.md",
    # Fund template sections
    "GP Background & Track Record": "02-gp-background--track-record.md",
    "Fund Strategy & Thesis": "03-fund-strategy--thesis.md",
    "Portfolio Construction": "04-portfolio-construction.md",
    "Value Add & Differentiation": "05-value-add--differentiation.md",
    "Track Record Analysis": "06-track-record-analysis.md",
    "Fee Structure & Economics": "07-fee-structure--economics.md",
    "LP Base & References": "08-lp-base--references.md",
}


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


def get_section_file(sections_dir: Path, section_name: str) -> Path:
    """Get the section file path."""
    filename = SECTION_MAP.get(section_name)
    if not filename:
        raise ValueError(f"Unknown section: {section_name}. Valid sections: {list(SECTION_MAP.keys())}")

    section_file = sections_dir / filename
    if not section_file.exists():
        raise FileNotFoundError(f"Section file not found: {section_file}")

    return section_file


def count_citations(content: str) -> int:
    """Count inline citations in content."""
    import re
    return len(re.findall(r'\[\^\d+\]', content))


def main():
    parser = argparse.ArgumentParser(
        description="Enrich a section with citations (without rewriting)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli.enrich_citations "Sava" "Market Context"
  python -m cli.enrich_citations "Sava" "Market Context" --version v0.0.2
  python -m cli.enrich_citations output/Sava-v0.0.2 "Market Context"

This tool adds citations to existing content without changing the narrative.
For content rewrites, use improve_section.py instead.
        """
    )
    parser.add_argument("company_or_path", help="Company name or path to artifact directory")
    parser.add_argument("section", help="Section name (e.g., 'Market Context', 'Team')")
    parser.add_argument("--version", "-v", help="Specific version (e.g., v0.0.2)")
    parser.add_argument("--no-reassemble", action="store_true", help="Skip reassembly of final draft")

    args = parser.parse_args()

    console = Console()

    # Check for Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        console.print("[red]Error:[/red] PERPLEXITY_API_KEY not set in environment")
        sys.exit(1)

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

    # Extract company name from directory
    dir_name = artifact_dir.name
    import re
    match = re.match(r'^(.+?)-v\d+\.\d+\.\d+$', dir_name)
    company_name = match.group(1).replace('-', ' ') if match else args.company_or_path

    # Get section file
    try:
        section_file = get_section_file(sections_dir, args.section)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Citation Enrichment[/bold]\n\n"
        f"Company: {company_name}\n"
        f"Section: {args.section}\n"
        f"Path: {artifact_dir}",
        title="Enrich Citations"
    ))

    # Read current section
    with open(section_file) as f:
        original_content = f.read()

    original_citations = count_citations(original_content)
    console.print(f"\n[dim]Current citations: {original_citations}[/dim]")
    console.print(f"[dim]Word count: {len(original_content.split())}[/dim]\n")

    # Initialize Perplexity client
    perplexity_client = OpenAI(
        api_key=perplexity_key,
        base_url="https://api.perplexity.ai"
    )

    console.print("[cyan]Enriching with citations via Perplexity Sonar Pro...[/cyan]")
    console.print("[dim](This preserves your content and only adds citation markers)[/dim]\n")

    # Enrich section
    enriched_content = enrich_section_with_citations(
        section_content=original_content,
        section_name=args.section,
        company_name=company_name,
        perplexity_client=perplexity_client
    )

    new_citations = count_citations(enriched_content)

    # Save enriched section
    with open(section_file, 'w') as f:
        f.write(enriched_content)

    console.print(f"[green]✓ Saved enriched section:[/green] {section_file}")
    console.print(f"  Citations: {original_citations} → {new_citations} (+{new_citations - original_citations})")

    # Reassemble final draft
    if not args.no_reassemble:
        console.print("\n[bold]Reassembling final draft...[/bold]")
        from cli.assemble_draft import assemble_final_draft
        final_path = assemble_final_draft(artifact_dir, console)
        console.print(f"[green]✓ Final draft updated:[/green] {final_path}")

    console.print("\n[bold green]Done![/bold green]")
    console.print(f"\nNext steps:")
    console.print(f"  1. Review section: {section_file}")
    console.print(f"  2. Export to HTML: python -m cli.export_branded {artifact_dir}/4-final-draft.md --brand hypernova --mode dark")


if __name__ == "__main__":
    main()

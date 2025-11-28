#!/usr/bin/env python3
"""
Improve or complete a specific section of an investment memo using Perplexity Sonar Pro.

USAGE: Always run with venv Python:
    .venv/bin/python improve-section.py "Company" "Section Name"

Or activate venv first:
    source .venv/bin/activate && python improve-section.py "Company" "Section Name"

This script allows targeted improvement of individual memo sections without
regenerating the entire memo. It uses Perplexity Sonar Pro for:
- Real-time research and fact-checking
- Automatic citation addition (Obsidian-style [^1], [^2])
- Quality source selection (TechCrunch, Crunchbase, industry reports)
- Section improvement without separate citation enrichment step

Features:
- Complete missing sections from scratch
- Improve existing sections with better data and sources
- Add inline citations automatically during improvement
- Automatically reassemble final draft after improvement

Usage:
    python improve-section.py "Avalanche" "Team"
    python improve-section.py "Avalanche" "Technology & Product" --version v0.0.1
    python improve-section.py output/Avalanche-v0.0.1 "Market Context"

Requirements:
    - PERPLEXITY_API_KEY must be set in .env file
    - Existing artifact directory with sections
"""

import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from src.state import MemoState
from src.artifacts import sanitize_filename, save_section_artifact
from src.versioning import VersionManager


# Section mappings (name -> file number and filename)
SECTION_MAP = {
    "Executive Summary": (1, "01-executive-summary.md"),
    "Business Overview": (2, "02-business-overview.md"),
    "Market Context": (3, "03-market-context.md"),
    "Team": (4, "04-team.md"),
    "Technology & Product": (5, "05-technology--product.md"),
    "Traction & Milestones": (6, "06-traction--milestones.md"),
    "Funding & Terms": (7, "07-funding--terms.md"),
    "Risks & Mitigations": (8, "08-risks--mitigations.md"),
    "Investment Thesis": (9, "09-investment-thesis.md"),
    "Recommendation": (10, "10-recommendation.md"),
    # Fund template sections
    "GP Background & Track Record": (2, "02-gp-background--track-record.md"),
    "Fund Strategy & Thesis": (3, "03-fund-strategy--thesis.md"),
    "Portfolio Construction": (4, "04-portfolio-construction.md"),
    "Value Add & Differentiation": (5, "05-value-add--differentiation.md"),
    "Track Record Analysis": (6, "06-track-record-analysis.md"),
    "Fee Structure & Economics": (7, "07-fee-structure--economics.md"),
    "LP Base & References": (8, "08-lp-base--references.md"),
}


def load_artifacts(artifact_dir: Path) -> dict:
    """Load existing artifacts from directory."""
    console = Console()

    artifacts = {
        "state": None,
        "research": None,
        "sections": {},
        "validation": None,
    }

    # Load state.json
    state_file = artifact_dir / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            artifacts["state"] = json.load(f)
        console.print(f"[green]✓ Loaded state.json[/green]")
    else:
        console.print(f"[yellow]⚠ No state.json found[/yellow]")

    # Load research
    research_file = artifact_dir / "1-research.json"
    if research_file.exists():
        with open(research_file) as f:
            artifacts["research"] = json.load(f)
        console.print(f"[green]✓ Loaded research data[/green]")
    else:
        console.print(f"[yellow]⚠ No research data found[/yellow]")

    # Load existing sections
    sections_dir = artifact_dir / "2-sections"
    if sections_dir.exists():
        for section_file in sections_dir.glob("*.md"):
            with open(section_file) as f:
                artifacts["sections"][section_file.name] = f.read()
        console.print(f"[green]✓ Loaded {len(artifacts['sections'])} existing sections[/green]")
    else:
        console.print(f"[yellow]⚠ No sections directory found[/yellow]")

    # Load validation
    validation_file = artifact_dir / "3-validation.json"
    if validation_file.exists():
        with open(validation_file) as f:
            artifacts["validation"] = json.load(f)
        console.print(f"[green]✓ Loaded validation data[/green]")

    return artifacts


def improve_section_with_sonar_pro(
    section_name: str,
    artifacts: dict,
    artifact_dir: Path,
    console: Console,
    custom_instructions: str = ""
) -> str:
    """Use Perplexity Sonar Pro to improve section with real-time research and citations."""
    from openai import OpenAI

    # Get the section info
    if section_name not in SECTION_MAP:
        console.print(f"[red]Error: Unknown section '{section_name}'[/red]")
        console.print(f"[yellow]Available sections:[/yellow]")
        for name in sorted(SECTION_MAP.keys()):
            console.print(f"  - {name}")
        sys.exit(1)

    section_num, section_file = SECTION_MAP[section_name]

    # Check if section exists
    existing_content = artifacts["sections"].get(section_file, "")
    is_new = not existing_content or existing_content.strip() == ""

    action = "Creating" if is_new else "Improving"
    console.print(f"\n[bold cyan]{action} section:[/bold cyan] {section_name}")

    # Get state info
    state = artifacts.get("state", {})
    company_name = state.get("company_name", "Unknown Company")
    investment_type = state.get("investment_type", "direct")
    memo_mode = state.get("memo_mode", "consider")
    research_data = artifacts.get("research", {})

    # Get disambiguation context from state (loaded from company data file)
    company_description = state.get("company_description", "")
    company_url = state.get("company_url", "")
    research_notes = state.get("research_notes", "")

    # Build disambiguation block if we have identifying info
    disambiguation_context = ""
    if company_description or company_url:
        disambiguation_context = f"""
CRITICAL - ENTITY DISAMBIGUATION:
There may be multiple companies named "{company_name}". You MUST research the CORRECT company:

"""
        if company_description:
            disambiguation_context += f"COMPANY DESCRIPTION: {company_description}\n"
        if company_url:
            # Extract domain for easier matching
            domain = company_url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            disambiguation_context += f"OFFICIAL WEBSITE: {company_url}\n"
            disambiguation_context += f"DOMAIN TO MATCH: {domain}\n"
        if research_notes:
            disambiguation_context += f"RESEARCH NOTES: {research_notes}\n"

        disambiguation_context += f"""
DISAMBIGUATION RULES:
1. ONLY use sources that reference THIS specific company (website: {company_url or 'see description'})
2. If you find data for a DIFFERENT company with the same name, DISCARD IT
3. When citing funding/revenue/metrics, verify the source mentions the correct company
4. If unsure whether data is about the right company, state "Data not verified for this entity"
5. Cross-reference with company website ({company_url}) to confirm you have the right entity
"""

    # Load template
    if investment_type == "fund":
        template_file = Path("templates/memo-template-fund.md")
    else:
        template_file = Path("templates/memo-template-direct.md")

    with open(template_file) as f:
        template_content = f.read()

    # Load style guide
    with open("templates/style-guide.md") as f:
        style_guide = f.read()

    # Build context from other sections
    other_sections_context = ""
    if artifacts["sections"]:
        other_sections_context = "\n\n## OTHER SECTIONS (for context):\n\n"
        for filename, content in sorted(artifacts["sections"].items()):
            if filename != section_file:
                other_sections_context += f"### {filename}\n{content[:500]}...\n\n"

    # Build prompt with citation instructions
    if is_new:
        task_description = f"""Create a comprehensive '{section_name}' section for the investment memo."""
    else:
        task_description = f"""Improve the existing '{section_name}' section by:
1. Adding more specific details and metrics from authoritative sources
2. Finding and citing quality sources for all factual claims
3. Removing vague or speculative language ("could potentially", "might be", etc.)
4. Strengthening the analysis with concrete evidence

EXISTING SECTION CONTENT:
{existing_content}

Your task is to significantly improve this section, keeping what's good and fixing what's weak."""

    prompt = f"""You are improving the '{section_name}' section for an investment memo about {company_name}.

INVESTMENT TYPE: {investment_type.upper()}
MEMO MODE: {memo_mode.upper()} ({'retrospective justification' if memo_mode == 'justify' else 'prospective analysis'})
{disambiguation_context}

TEMPLATE GUIDANCE:
{template_content}

STYLE GUIDE:
{style_guide}

RESEARCH DATA AVAILABLE:
{json.dumps(research_data, indent=2)}

{other_sections_context}

TASK:
{task_description}
{f'''
CUSTOM INSTRUCTIONS FROM USER:
{custom_instructions}
''' if custom_instructions else ''}
REQUIREMENTS:
- Follow the template structure and style guide
- Use specific metrics and data from authoritative sources
- Add inline citations [^1], [^2], [^3] for ALL factual claims
- Use Obsidian-style citations with proper spacing
- Match the tone and depth of high-quality VC memos
- Be analytical, not promotional or dismissive
- For {memo_mode} mode: {'justify why we invested (recommendation: COMMIT)' if memo_mode == 'justify' else 'objectively assess whether to invest'}

CITATION REQUIREMENTS (CRITICAL):
- Place citations AFTER punctuation: "text. [^1]" NOT "text[^1]."
- Always include ONE SPACE before each citation: "text. [^1] [^2]"
- Use quality sources:
  * Company websites, blogs, press releases
  * TechCrunch, The Information, Sifted, Protocol, Axios
  * Crunchbase, PitchBook (for funding data)
  * SEC filings, investor letters
  * Industry analyst reports (Gartner, CB Insights, McKinsey)
  * Bloomberg, Reuters, WSJ, FT (for news)
- Include comprehensive Citations section at end

CITATION FORMAT:
[^1]: YYYY, MMM DD. [Source Title](https://full-url-here.com). Publisher Name. Published: YYYY-MM-DD | Updated: YYYY-MM-DD

Write ONLY the section content (no section header, it will be added automatically).
Include a complete Citations section at the end with all sources.

IMPROVED SECTION CONTENT:
"""

    # Call Perplexity Sonar Pro
    console.print("[dim]Calling Perplexity Sonar Pro for real-time research and citations...[/dim]")

    # Use default_headers to set User-Agent (bypasses Cloudflare)
    perplexity_client = OpenAI(
        api_key=os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    response = perplexity_client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": prompt}]
    )

    improved_content = response.choices[0].message.content

    # Save the improved section
    save_section_artifact(artifact_dir, section_num, section_name, improved_content)

    console.print(f"[green]✓ Saved improved section to:[/green] {artifact_dir}/2-sections/{section_file}")

    return improved_content


def reassemble_final_draft(artifact_dir: Path, console: Console) -> Path:
    """Reassemble 4-final-draft.md from all section files."""
    console.print("\n[bold]Reassembling final draft...[/bold]")

    content = ""

    # Load header if exists (contains company trademark)
    header_file = artifact_dir / "header.md"
    if header_file.exists():
        with open(header_file) as f:
            content = f.read() + "\n"
        console.print("[dim]  • Included header.md (company trademark)[/dim]")

    # Load sections in order
    sections_dir = artifact_dir / "2-sections"
    section_files = sorted(sections_dir.glob("*.md"))

    console.print(f"[dim]  • Loading {len(section_files)} sections...[/dim]")

    for section_file in section_files:
        with open(section_file) as f:
            content += f.read() + "\n\n"

    # Save final draft
    final_draft = artifact_dir / "4-final-draft.md"
    with open(final_draft, "w") as f:
        f.write(content.strip())

    console.print(f"[green]✓ Final draft reassembled:[/green] {final_draft}")

    return final_draft


def main():
    """Main entry point."""
    console = Console()

    # Load environment
    load_dotenv()

    if not os.getenv("PERPLEXITY_API_KEY"):
        console.print("[bold red]Error:[/bold red] PERPLEXITY_API_KEY not set")
        console.print("[yellow]This script requires Perplexity Sonar Pro for real-time research and citations.[/yellow]")
        console.print("[yellow]Set PERPLEXITY_API_KEY in your .env file.[/yellow]")
        sys.exit(1)

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Improve or complete a specific section of an investment memo"
    )
    parser.add_argument(
        "target",
        help="Company name (e.g., 'Bear-AI') or path to artifact directory"
    )
    parser.add_argument(
        "section",
        help="Section name (e.g., 'Team', 'Market Context', 'Technology & Product')"
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.1'). If not specified, uses latest."
    )
    parser.add_argument(
        "--message", "-m",
        help="Custom instructions to pass to the improvement agent (e.g., 'Reference the deck sections and cite them')"
    )

    args = parser.parse_args()

    # Determine artifact directory
    target_path = Path(args.target)

    if target_path.exists() and target_path.is_dir():
        # Direct path to artifact directory
        artifact_dir = target_path
    else:
        # Company name - find latest version
        safe_name = sanitize_filename(args.target)
        output_dir = Path("output")

        if args.version:
            artifact_dir = output_dir / f"{safe_name}-{args.version}"
        else:
            # Find latest version
            version_mgr = VersionManager(output_dir)
            if safe_name not in version_mgr.versions_data:
                console.print(f"[red]Error: No versions found for '{args.target}'[/red]")
                sys.exit(1)

            latest_version = version_mgr.versions_data[safe_name]["latest_version"]
            artifact_dir = output_dir / f"{safe_name}-{latest_version}"

    if not artifact_dir.exists():
        console.print(f"[red]Error: Artifact directory not found:[/red] {artifact_dir}")
        sys.exit(1)

    console.print(Panel(f"[bold cyan]Improving Section: {args.section}[/bold cyan]\n"
                       f"[dim]Artifact directory: {artifact_dir}[/dim]"))

    # Load artifacts
    console.print("\n[bold]Loading existing artifacts...[/bold]")
    artifacts = load_artifacts(artifact_dir)

    # Show custom message if provided
    if args.message:
        console.print(f"\n[bold yellow]Custom instructions:[/bold yellow] {args.message}")

    # Improve section with Perplexity Sonar Pro
    console.print()
    improved_content = improve_section_with_sonar_pro(
        args.section,
        artifacts,
        artifact_dir,
        console,
        custom_instructions=args.message or ""
    )

    # Automatically reassemble final draft
    final_draft = reassemble_final_draft(artifact_dir, console)

    # Show preview
    console.print("\n" + "="*80)
    console.print(Panel("[bold green]Section Improved Successfully[/bold green]"))
    console.print("\n[bold]Preview (first 500 chars):[/bold]")
    console.print(improved_content[:500] + "...\n")

    # Count citations
    import re
    citation_count = len(re.findall(r'\[\^\d+\]', improved_content))
    console.print(f"[bold cyan]Citations added:[/bold cyan] {citation_count}")

    console.print(f"\n[bold cyan]Next steps:[/bold cyan]")
    console.print(f"1. Review the improved section in: {artifact_dir}/2-sections/")
    console.print(f"2. View complete memo: {final_draft}")
    console.print(f"3. Export to HTML: python export-branded.py {final_draft} --brand hypernova")
    console.print(f"4. Improve another section: python improve-section.py \"{args.target}\" \"<section name>\"")


if __name__ == "__main__":
    main()

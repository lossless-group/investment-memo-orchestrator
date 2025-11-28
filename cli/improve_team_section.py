#!/usr/bin/env python3
"""
Improve the Team section using structured, sequential research.

USAGE: Always run with venv Python:
    .venv/bin/python cli/improve_team_section.py "Company"

Or activate venv first:
    source .venv/bin/activate && python -m cli.improve_team_section "Company"

This script uses a FOCUSED, SEQUENTIAL research approach for team research:

PHASE 1: Primary Sources (get names and titles)
    - LinkedIn Company Page → /people section for employee list
    - Company Website → /team, /about, /about-us pages for official bios

PHASE 2: Individual Deep Dives (only AFTER we have names)
    - For each team member: search for prior companies, publications, talks, press

PHASE 3: Synthesis
    - Combine all research into comprehensive Team section with citations

This approach avoids the "spray and pray" problem where generic searches return
irrelevant or wrong-company information.

Requirements:
    - PERPLEXITY_API_KEY must be set in .env file
    - Existing artifact directory with sections
"""

import os
import sys
import json
import argparse
import re
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.artifacts import sanitize_filename, save_section_artifact
from src.versioning import VersionManager


def get_perplexity_client():
    """Create Perplexity client with proper headers."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
    )


def search_perplexity(client, query: str, console: Console) -> str:
    """Execute a single Perplexity search and return the response."""
    console.print(f"[dim]  → Searching: {query[:80]}...[/dim]")

    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": query}]
    )

    return response.choices[0].message.content


def phase1_primary_sources(
    client,
    company_name: str,
    company_url: str,
    company_description: str,
    console: Console
) -> Dict[str, str]:
    """
    Phase 1: Research primary sources for team member names and titles.

    Sources:
    1. LinkedIn Company Page - /people section
    2. Company Website - /team, /about pages
    """
    console.print("\n[bold cyan]Phase 1: Primary Source Research[/bold cyan]")
    results = {}

    # Extract domain for LinkedIn search
    domain = ""
    if company_url:
        domain = company_url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

    # 1. LinkedIn Company Page
    linkedin_query = f"""Search for the LinkedIn company page for "{company_name}" ({domain}).

TASK: Find the company's LinkedIn page and list ALL employees/team members visible.

For each person found, provide:
- Full name
- Current title at {company_name}
- LinkedIn profile URL (if visible)

IMPORTANT DISAMBIGUATION:
- Company website: {company_url}
- Description: {company_description}
- ONLY include people who work at THIS company, not similarly-named companies

Return a structured list of team members with their titles and LinkedIn URLs."""

    results["linkedin"] = search_perplexity(client, linkedin_query, console)

    # 2. Company Website Team/About Page
    website_query = f"""Search the website {company_url} for team information.

Look for pages like:
- {company_url}/team
- {company_url}/about
- {company_url}/about-us
- {company_url}/people
- {company_url}/leadership

For each team member found, extract:
- Full name
- Title/role
- Background/bio summary
- Any notable credentials (education, prior companies, achievements)

IMPORTANT: Only extract information from {company_url} - do not use other sources.

Return a structured summary of all team members with their bios."""

    results["website"] = search_perplexity(client, website_query, console)

    return results


def extract_team_members(phase1_results: Dict[str, str], console: Console) -> List[Dict[str, str]]:
    """
    Parse Phase 1 results to extract team member names and basic info.
    Returns list of dicts with name, title, and any URLs found.
    """
    console.print("\n[bold cyan]Extracting team member names...[/bold cyan]")

    # Use Perplexity to parse and consolidate the results
    client = get_perplexity_client()

    extraction_query = f"""Given these research results about a company's team, extract a consolidated list of team members.

LINKEDIN RESEARCH:
{phase1_results.get('linkedin', 'No data')}

WEBSITE RESEARCH:
{phase1_results.get('website', 'No data')}

TASK: Create a JSON array of team members. For each person, include:
- "name": Full name
- "title": Current title
- "linkedin_url": LinkedIn URL if found (or null)
- "bio_snippet": Brief bio if available (or null)

Return ONLY valid JSON array, no other text. Example format:
[
  {{"name": "John Doe", "title": "CEO & Co-founder", "linkedin_url": "https://linkedin.com/in/johndoe", "bio_snippet": "Former VP at Google"}},
  {{"name": "Jane Smith", "title": "CTO", "linkedin_url": null, "bio_snippet": "PhD from MIT"}}
]

Deduplicate entries - if same person appears in both sources, merge their info.
Focus on founding team, executives, and key hires. Skip advisors unless prominently featured."""

    response = search_perplexity(client, extraction_query, console)

    # Try to parse JSON from response
    try:
        # Find JSON array in response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            team_members = json.loads(json_match.group())
            console.print(f"[green]✓ Extracted {len(team_members)} team members[/green]")
            for member in team_members:
                console.print(f"  • {member.get('name', 'Unknown')} - {member.get('title', 'Unknown role')}")
            return team_members
    except json.JSONDecodeError:
        console.print("[yellow]⚠ Could not parse team member JSON, using raw text[/yellow]")

    # Fallback: return empty list and let Phase 2 work with raw text
    return []


def phase2_individual_research(
    client,
    team_members: List[Dict[str, str]],
    company_name: str,
    company_url: str,
    console: Console
) -> Dict[str, str]:
    """
    Phase 2: Deep dive research on each individual team member.

    For each person, search for:
    - Prior companies and roles
    - Education background
    - Publications, talks, or notable work
    - Press mentions
    - Industry recognition
    """
    console.print("\n[bold cyan]Phase 2: Individual Deep Dive Research[/bold cyan]")
    results = {}

    if not team_members:
        console.print("[yellow]⚠ No team members extracted, doing general team search[/yellow]")

        general_query = f"""Research the founding team and key executives at {company_name} ({company_url}).

For each team member, find:
1. Full name and current title
2. Professional background (prior companies, roles)
3. Education (degrees, institutions)
4. Notable achievements or credentials
5. Relevant domain expertise

IMPORTANT: Only research people who work at {company_name} (website: {company_url}).

Provide detailed background on each person with citations."""

        results["general"] = search_perplexity(client, general_query, console)
        return results

    # Research each team member individually
    for member in team_members[:6]:  # Limit to top 6 to avoid excessive API calls
        name = member.get("name", "Unknown")
        title = member.get("title", "")

        console.print(f"\n[dim]Researching: {name} ({title})[/dim]")

        individual_query = f"""Research {name}, {title} at {company_name}.

Find information about:
1. Professional background before {company_name}:
   - Prior companies and roles
   - Career progression
   - Industry experience

2. Education:
   - Degrees and institutions
   - Notable academic achievements

3. Public presence:
   - Published articles or research
   - Conference talks or podcasts
   - Press interviews or quotes
   - Social media presence (Twitter/X notable posts)

4. Industry recognition:
   - Awards or honors
   - Board positions
   - Advisory roles

IMPORTANT DISAMBIGUATION:
- This person works at {company_name} ({company_url})
- Current title: {title}
- If you find multiple people with this name, only include info for the person at {company_name}

Provide detailed findings with source citations."""

        results[name] = search_perplexity(client, individual_query, console)

    return results


def phase3_synthesize_section(
    client,
    phase1_results: Dict[str, str],
    phase2_results: Dict[str, str],
    team_members: List[Dict[str, str]],
    company_name: str,
    company_description: str,
    existing_section: str,
    deck_team_content: str,
    console: Console
) -> str:
    """
    Phase 3: Synthesize all research into a polished Team section.
    """
    console.print("\n[bold cyan]Phase 3: Synthesizing Team Section[/bold cyan]")

    # Prepare context
    phase1_text = "\n\n".join([f"### {k}\n{v}" for k, v in phase1_results.items()])
    phase2_text = "\n\n".join([f"### {k}\n{v}" for k, v in phase2_results.items()])
    team_list = json.dumps(team_members, indent=2) if team_members else "See research above"

    synthesis_query = f"""Write a comprehensive Team section for an investment memo about {company_name}.

COMPANY CONTEXT:
{company_description}

TEAM MEMBERS IDENTIFIED:
{team_list}

PHASE 1 RESEARCH (Primary Sources - LinkedIn & Website):
{phase1_text}

PHASE 2 RESEARCH (Individual Deep Dives):
{phase2_text}

{f'''EXISTING SECTION (for reference - improve upon this):
{existing_section}''' if existing_section else ''}

{f'''PITCH DECK TEAM SECTION (treat as primary source, cite it):
{deck_team_content}''' if deck_team_content else ''}

REQUIREMENTS:
1. Write in professional investment memo style
2. Lead with founder/CEO, then other C-suite, then key hires
3. For each person include:
   - Name, title, LinkedIn URL (if known)
   - Professional background and relevant experience
   - Education credentials
   - Why they're qualified for this role
   - Domain expertise relevant to the company's mission

4. Include a "Team Assessment" subsection at the end analyzing:
   - Team completeness (any key gaps?)
   - Founder-market fit
   - Prior startup experience
   - Domain expertise depth
   - Working relationship history (have they worked together before?)

5. CITATIONS (CRITICAL):
   - Use Obsidian-style: [^1], [^2], etc.
   - Place citations AFTER punctuation: "text. [^1]"
   - Include complete Citations section at end
   - Format: [^1]: YYYY, MMM DD. [Title](URL). Publisher. Published: YYYY-MM-DD | Updated: N/A
   - Cite the pitch deck if you use information from it

6. Be analytical, not promotional
   - Note gaps or concerns honestly
   - Highlight strengths with evidence
   - Compare to what you'd want to see at this stage

Write the complete Team section now:"""

    response = search_perplexity(client, synthesis_query, console)
    return response


def load_artifacts(artifact_dir: Path, console: Console) -> dict:
    """Load existing artifacts from directory."""
    artifacts = {
        "state": None,
        "research": None,
        "sections": {},
        "deck_team": None,
    }

    # Load state.json
    state_file = artifact_dir / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            artifacts["state"] = json.load(f)
        console.print(f"[green]✓ Loaded state.json[/green]")

    # Load existing sections
    sections_dir = artifact_dir / "2-sections"
    if sections_dir.exists():
        for section_file in sections_dir.glob("*.md"):
            with open(section_file) as f:
                artifacts["sections"][section_file.name] = f.read()
        console.print(f"[green]✓ Loaded {len(artifacts['sections'])} existing sections[/green]")

    # Load deck team section if exists
    deck_team_file = artifact_dir / "0-deck-sections" / "04-team.md"
    if deck_team_file.exists():
        with open(deck_team_file) as f:
            artifacts["deck_team"] = f.read()
        console.print(f"[green]✓ Loaded deck team section[/green]")

    return artifacts


def reassemble_final_draft(artifact_dir: Path, console: Console) -> Path:
    """
    Reassemble 4-final-draft.md using the canonical assembly tool.

    Delegates to cli.assemble_draft which handles:
    - Citation renumbering and consolidation
    - Table of Contents generation
    """
    from cli.assemble_draft import assemble_final_draft as canonical_assemble

    console.print("\n[bold]Reassembling final draft...[/bold]")
    return canonical_assemble(artifact_dir, console)


def main():
    """Main entry point."""
    console = Console()

    # Load environment
    load_dotenv()

    if not os.getenv("PERPLEXITY_API_KEY"):
        console.print("[bold red]Error:[/bold red] PERPLEXITY_API_KEY not set")
        sys.exit(1)

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Improve Team section with structured, sequential research"
    )
    parser.add_argument(
        "target",
        help="Company name (e.g., 'Sava') or path to artifact directory"
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.1'). If not specified, uses latest."
    )

    args = parser.parse_args()

    # Determine artifact directory
    target_path = Path(args.target)

    if target_path.exists() and target_path.is_dir():
        artifact_dir = target_path
    else:
        safe_name = sanitize_filename(args.target)
        output_dir = Path("output")

        if args.version:
            artifact_dir = output_dir / f"{safe_name}-{args.version}"
        else:
            version_mgr = VersionManager(output_dir)
            if safe_name not in version_mgr.versions_data:
                console.print(f"[red]Error: No versions found for '{args.target}'[/red]")
                sys.exit(1)

            latest_version = version_mgr.versions_data[safe_name]["latest_version"]
            artifact_dir = output_dir / f"{safe_name}-{latest_version}"

    if not artifact_dir.exists():
        console.print(f"[red]Error: Artifact directory not found:[/red] {artifact_dir}")
        sys.exit(1)

    console.print(Panel(
        f"[bold cyan]Improving Team Section with Sequential Research[/bold cyan]\n"
        f"[dim]Artifact directory: {artifact_dir}[/dim]"
    ))

    # Load artifacts
    console.print("\n[bold]Loading existing artifacts...[/bold]")
    artifacts = load_artifacts(artifact_dir, console)

    # Get company info
    state = artifacts.get("state", {})
    company_name = state.get("company_name", "Unknown Company")
    company_url = state.get("company_url", "")
    company_description = state.get("company_description", "")

    console.print(f"\n[bold]Company:[/bold] {company_name}")
    console.print(f"[bold]Website:[/bold] {company_url or 'Not specified'}")

    # Get existing team section
    existing_section = artifacts["sections"].get("04-team.md", "")
    deck_team_content = artifacts.get("deck_team", "")

    # Initialize Perplexity client
    client = get_perplexity_client()

    # PHASE 1: Primary Sources
    phase1_results = phase1_primary_sources(
        client, company_name, company_url, company_description, console
    )

    # Extract team members from Phase 1
    team_members = extract_team_members(phase1_results, console)

    # PHASE 2: Individual Deep Dives
    phase2_results = phase2_individual_research(
        client, team_members, company_name, company_url, console
    )

    # PHASE 3: Synthesize Section
    improved_content = phase3_synthesize_section(
        client,
        phase1_results,
        phase2_results,
        team_members,
        company_name,
        company_description,
        existing_section,
        deck_team_content,
        console
    )

    # Add section header if not present
    if not improved_content.strip().startswith("# Team"):
        improved_content = "# Team\n\n" + improved_content

    # Save the improved section
    section_file = artifact_dir / "2-sections" / "04-team.md"
    with open(section_file, "w") as f:
        f.write(improved_content)
    console.print(f"\n[green]✓ Saved improved Team section to:[/green] {section_file}")

    # Reassemble final draft
    final_draft = reassemble_final_draft(artifact_dir, console)

    # Show summary
    console.print("\n" + "=" * 80)
    console.print(Panel("[bold green]Team Section Improved Successfully[/bold green]"))

    # Count citations
    citation_count = len(re.findall(r'\[\^\d+\]', improved_content))
    console.print(f"\n[bold cyan]Citations added:[/bold cyan] {citation_count}")
    console.print(f"[bold cyan]Team members found:[/bold cyan] {len(team_members)}")

    # Preview
    console.print("\n[bold]Preview (first 600 chars):[/bold]")
    console.print(improved_content[:600] + "...\n")

    console.print(f"\n[bold cyan]Next steps:[/bold cyan]")
    console.print(f"1. Review improved section: {section_file}")
    console.print(f"2. View complete memo: {final_draft}")
    console.print(f"3. Export: python export-branded.py {final_draft} --brand hypernova")


if __name__ == "__main__":
    main()

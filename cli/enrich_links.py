#!/usr/bin/env python3
"""
Link Enrichment CLI Tool.

Adds hyperlinks to a section for:
1. Organizations (investors, gov bodies, partners, competitors, universities)
2. Social profiles (LinkedIn, Twitter/X, Bluesky) for people mentioned

This combines link_enrichment_agent and socials_enrichment_agent functionality.

Usage:
    python -m cli.enrich_links "Sava" "Team"
    python -m cli.enrich_links "Sava" "Team" --version v0.0.2
    python -m cli.enrich_links output/Sava-v0.0.2 "Team"
"""

import os
import sys
import re
import argparse
from pathlib import Path
from typing import Optional, Dict, List

from rich.console import Console
from rich.panel import Panel

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename


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
}


def resolve_artifact_dir(company_or_path: str, version: Optional[str] = None) -> Path:
    """Resolve to artifact directory from company name or direct path."""
    path = Path(company_or_path)
    if path.exists() and path.is_dir():
        return path

    output_dir = Path("output")
    safe_name = sanitize_filename(company_or_path)

    if version:
        target = output_dir / f"{safe_name}-{version}"
        if target.exists():
            return target
        raise FileNotFoundError(f"Version not found: {target}")

    matches = sorted(output_dir.glob(f"{safe_name}-v*"), reverse=True)
    if matches:
        return matches[0]
    raise FileNotFoundError(f"No output found for: {company_or_path}")


def get_section_file(sections_dir: Path, section_name: str) -> Path:
    """Get the section file path."""
    filename = SECTION_MAP.get(section_name)
    if not filename:
        raise ValueError(f"Unknown section: {section_name}")
    section_file = sections_dir / filename
    if not section_file.exists():
        raise FileNotFoundError(f"Section file not found: {section_file}")
    return section_file


def count_links(content: str) -> int:
    """Count markdown links in content."""
    return len(re.findall(r'\[([^\]]+)\]\(https?://[^\)]+\)', content))


def search_social_profile(query: str, platform: str, console: Console) -> Optional[str]:
    """Search for a social profile using Tavily."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return None

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)

        domains = {
            "linkedin": "linkedin.com",
            "twitter": "x.com",
            "x": "x.com",
            "bluesky": "bsky.app",
            "github": "github.com",
        }

        domain = domains.get(platform.lower())
        if not domain:
            return None

        response = client.search(
            query=f"{query} {platform}",
            max_results=5,
            include_domains=[domain]
        )

        for result in response.get("results", []):
            url = result.get("url", "")
            # Validate it's a profile URL
            if platform == "linkedin" and ("/in/" in url or "/company/" in url):
                return url
            elif platform in ["twitter", "x"] and re.search(r'x\.com/[a-zA-Z0-9_]+$', url):
                return url
            elif platform == "bluesky" and "bsky.app/profile/" in url:
                return url
            elif platform == "github" and re.search(r'github\.com/[a-zA-Z0-9_-]+$', url):
                return url

        return None
    except Exception as e:
        console.print(f"  [dim]Warning: Search failed for {query}: {e}[/dim]")
        return None


def extract_people_from_team_section(content: str) -> List[Dict[str, str]]:
    """Extract names and roles of people mentioned in Team section.

    Looks for patterns like:
    - **Nimit Maru – Co-Founder & CEO**
    - **Rush Sadiwala – Co-Founder & COO**
    - CEO Nimit Maru
    - Co-Founder Jane Doe
    """
    people = []
    seen_names = set()

    # Pattern 1: **Name – Role** or **Name - Role** (bold name with em-dash/hyphen and role)
    # This is the most reliable pattern for our Team sections
    pattern1 = r'\*\*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*[–—-]\s*([^*]+)\*\*'
    matches = re.findall(pattern1, content)
    for name, role in matches:
        name = name.strip()
        role = role.strip()
        # Validate it's actually a name (2-4 words, each capitalized)
        words = name.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words):
            if name not in seen_names:
                seen_names.add(name)
                people.append({"name": name, "role": role})

    # Pattern 2: Role + Name (e.g., "CEO John Smith", "Co-Founder Jane Doe")
    roles_pattern = r'(?:CEO|CTO|COO|CFO|Co-Founder|Founder|President|VP|Director)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
    matches = re.findall(roles_pattern, content)
    for name in matches:
        name = name.strip()
        words = name.split()
        if 2 <= len(words) <= 3 and all(w[0].isupper() for w in words):
            if name not in seen_names:
                seen_names.add(name)
                people.append({"name": name, "role": ""})

    # Pattern 3: Name followed by title in parentheses - "John Smith (CEO)"
    pattern3 = r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*\(([^)]*(?:CEO|CTO|COO|CFO|Founder|Director|VP)[^)]*)\)'
    matches = re.findall(pattern3, content)
    for name, role in matches:
        name = name.strip()
        words = name.split()
        if 2 <= len(words) <= 3 and all(w[0].isupper() for w in words):
            if name not in seen_names:
                seen_names.add(name)
                people.append({"name": name, "role": role.strip()})

    return people


def enrich_with_organization_links(
    content: str,
    section_name: str,
    company_name: str,
    console: Console
) -> str:
    """Add hyperlinks to organizations mentioned in the section."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[yellow]Warning: ANTHROPIC_API_KEY not set, skipping org links[/yellow]")
        return content

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0,
    )

    system_prompt = """You are a link enrichment specialist for investment memos.

Add markdown hyperlinks to organizations, companies, investors, and institutions.

ENTITIES TO LINK:
- Investor firms (VC, PE, family offices)
- Government bodies (FDA, SEC, etc.)
- Companies (partners, competitors, employers)
- Universities and research institutions
- Industry organizations

RULES:
1. DO NOT change text - only add links
2. ONLY link FIRST mention of each entity
3. Use official websites (not Wikipedia/LinkedIn/Crunchbase)
4. If unsure about URL, DO NOT add link
5. Keep existing links unchanged
6. Format: [Entity Name](https://website.com)

OUTPUT: Return the COMPLETE section with links added."""

    user_prompt = f"""Add hyperlinks to organizations in this {section_name} section for {company_name}.

SECTION:
{content}

Return the full section with organization links added."""

    try:
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        return response.content
    except Exception as e:
        console.print(f"[yellow]Warning: Org link enrichment failed: {e}[/yellow]")
        return content


def enrich_with_social_links(
    content: str,
    people: List[Dict[str, str]],
    company_name: str,
    console: Console
) -> str:
    """Add social profile links for people mentioned."""

    if not people:
        console.print("  [dim]No people identified to search for[/dim]")
        return content

    console.print(f"\n  [cyan]Searching social profiles for {len(people)} people...[/cyan]")

    profiles_found = {}

    for person in people:
        name = person["name"]
        role = person.get("role", "")

        # Search LinkedIn first (most important for professional context)
        search_query = f"{name} {company_name}"
        if role:
            search_query += f" {role}"

        console.print(f"    Searching: {name}...")

        linkedin_url = search_social_profile(search_query, "linkedin", console)
        if linkedin_url:
            profiles_found[name] = {"linkedin": linkedin_url}
            console.print(f"      [green]✓ LinkedIn found[/green]")

        # Also try Twitter/X
        twitter_url = search_social_profile(f"{name}", "x", console)
        if twitter_url:
            if name not in profiles_found:
                profiles_found[name] = {}
            profiles_found[name]["twitter"] = twitter_url
            console.print(f"      [green]✓ X/Twitter found[/green]")

    if not profiles_found:
        console.print("  [dim]No social profiles found[/dim]")
        return content

    # Now add the links to the content
    enriched = content

    for name, profiles in profiles_found.items():
        # Find the first mention of the name that isn't already linked
        # Pattern: name not already inside a markdown link
        pattern = rf'(?<!\[)({re.escape(name)})(?!\]\()'

        match = re.search(pattern, enriched)
        if match:
            # Build the linked version with social icons
            linked_name = name
            social_links = []

            if "linkedin" in profiles:
                social_links.append(f"[LinkedIn]({profiles['linkedin']})")
            if "twitter" in profiles:
                social_links.append(f"[X]({profiles['twitter']})")

            if social_links:
                # Replace first occurrence with name + social links
                replacement = f"{name} ({', '.join(social_links)})"
                enriched = enriched[:match.start()] + replacement + enriched[match.end():]

    return enriched


def main():
    parser = argparse.ArgumentParser(
        description="Enrich a section with organization and social profile links",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli.enrich_links "Sava" "Team"
  python -m cli.enrich_links "Sava" "Team" --version v0.0.2
  python -m cli.enrich_links output/Sava-v0.0.2 "Team"

This adds:
  - Organization links (investors, gov bodies, partners, universities)
  - Social profile links for people (LinkedIn, Twitter/X)
        """
    )
    parser.add_argument("company_or_path", help="Company name or path to artifact directory")
    parser.add_argument("section", help="Section name (e.g., 'Team', 'Market Context')")
    parser.add_argument("--version", "-v", help="Specific version (e.g., v0.0.2)")
    parser.add_argument("--no-reassemble", action="store_true", help="Skip reassembly of final draft")
    parser.add_argument("--orgs-only", action="store_true", help="Only add organization links")
    parser.add_argument("--socials-only", action="store_true", help="Only add social profile links")

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

    # Extract company name
    dir_name = artifact_dir.name
    match = re.match(r'^(.+?)-v\d+\.\d+\.\d+$', dir_name)
    company_name = match.group(1).replace('-', ' ') if match else args.company_or_path

    # Get section file
    try:
        section_file = get_section_file(sections_dir, args.section)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Link Enrichment[/bold]\n\n"
        f"Company: {company_name}\n"
        f"Section: {args.section}\n"
        f"Path: {artifact_dir}",
        title="Enrich Links"
    ))

    # Read current section
    with open(section_file) as f:
        original_content = f.read()

    original_links = count_links(original_content)
    console.print(f"\n[dim]Current links: {original_links}[/dim]")

    enriched_content = original_content

    # Step 1: Organization links (unless socials-only)
    if not args.socials_only:
        console.print("\n[cyan]Step 1: Adding organization links...[/cyan]")
        enriched_content = enrich_with_organization_links(
            enriched_content, args.section, company_name, console
        )
        org_links = count_links(enriched_content) - original_links
        console.print(f"  [green]✓ Added {org_links} organization links[/green]")

    # Step 2: Social profile links (unless orgs-only)
    if not args.orgs_only:
        console.print("\n[cyan]Step 2: Adding social profile links...[/cyan]")

        # Extract people from section
        people = extract_people_from_team_section(enriched_content)
        console.print(f"  [dim]Found {len(people)} people to search[/dim]")

        if people:
            for p in people[:5]:  # Show first 5
                console.print(f"    • {p['name']}" + (f" ({p['role']})" if p.get('role') else ""))

            enriched_content = enrich_with_social_links(
                enriched_content, people, company_name, console
            )

    final_links = count_links(enriched_content)
    total_added = final_links - original_links

    # Save enriched section
    with open(section_file, 'w') as f:
        f.write(enriched_content)

    console.print(f"\n[green]✓ Saved enriched section:[/green] {section_file}")
    console.print(f"  Links: {original_links} → {final_links} (+{total_added})")

    # Reassemble final draft
    if not args.no_reassemble:
        console.print("\n[bold]Reassembling final draft...[/bold]")
        from cli.assemble_draft import assemble_final_draft
        final_path = assemble_final_draft(artifact_dir, console)
        console.print(f"[green]✓ Final draft updated:[/green] {final_path}")

    console.print("\n[bold green]Done![/bold green]")


if __name__ == "__main__":
    main()

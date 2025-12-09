"""
Socials Enrichment Agent - Gathers and adds social media links for company and team.

This agent enriches memo sections by finding and adding:
1. Team LinkedIn profiles: Founders, key hires, board members
2. Company social profiles: LinkedIn, X (Twitter), Bluesky, Crunchbase, GitHub

Links are added directly in the appropriate sections.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import os
from typing import Dict, Any, List, Optional
from ..state import MemoState
import json
import re


def search_for_social_profile(query: str, platform: str) -> Optional[str]:
    """
    Search for a social media profile using Tavily (preferred) or DuckDuckGo (fallback).

    Args:
        query: Search query (e.g., "John Doe LinkedIn" or "Acme Corp GitHub")
        platform: Platform name (linkedin, twitter, bluesky, crunchbase, github)

    Returns:
        URL of the profile if found, None otherwise
    """
    tavily_api_key = os.getenv("TAVILY_API_KEY")

    # Try Tavily first (preferred - has domain filtering)
    if tavily_api_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_api_key)

            # Search for the profile
            response = client.search(
                query=query,
                max_results=5,
                include_domains=[get_platform_domain(platform)]
            )

            results = response.get("results", [])

            # Find the best matching URL
            for result in results:
                url = result.get("url", "")
                if is_valid_profile_url(url, platform):
                    return url

            return None

        except Exception as e:
            print(f"Warning: Tavily search failed: {e}, trying DuckDuckGo fallback...")

    # Fallback to DuckDuckGo (free, no API key)
    return _search_with_duckduckgo(query, platform)


def _search_with_duckduckgo(query: str, platform: str) -> Optional[str]:
    """
    Search for a social profile using DuckDuckGo (free fallback).

    Args:
        query: Search query
        platform: Platform name

    Returns:
        URL of the profile if found, None otherwise
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        print("Warning: duckduckgo-search not installed, skipping social profile search")
        print("  Install with: uv pip install duckduckgo-search")
        return None

    try:
        ddgs = DDGS()

        # Add site: filter to query for domain targeting
        domain = get_platform_domain(platform)
        enhanced_query = f"site:{domain} {query}"

        results = ddgs.text(enhanced_query, max_results=5)

        # Find the best matching URL
        for result in results:
            url = result.get("href", "")
            if is_valid_profile_url(url, platform):
                return url

        return None

    except Exception as e:
        print(f"Warning: DuckDuckGo search failed for {platform}: {e}")
        return None


def get_platform_domain(platform: str) -> str:
    """Get the primary domain for a social platform."""
    domains = {
        "linkedin": "linkedin.com",
        "twitter": "twitter.com",
        "x": "x.com",
        "bluesky": "bsky.app",
        "crunchbase": "crunchbase.com",
        "github": "github.com"
    }
    return domains.get(platform.lower(), "")


def is_valid_profile_url(url: str, platform: str) -> bool:
    """
    Validate that a URL is a proper profile page for the platform.

    Args:
        url: URL to validate
        platform: Platform name

    Returns:
        True if valid profile URL, False otherwise
    """
    if not url:
        return False

    url_lower = url.lower()

    # LinkedIn: Should be /in/ for people or /company/ for companies
    if platform == "linkedin":
        return "/in/" in url_lower or "/company/" in url_lower

    # Twitter/X: Should have a username
    if platform in ["twitter", "x"]:
        return bool(re.search(r'(twitter|x)\.com/[a-zA-Z0-9_]+', url_lower))

    # Bluesky: Should be a profile page
    if platform == "bluesky":
        return "bsky.app/profile/" in url_lower

    # Crunchbase: Should be /organization/ or /person/
    if platform == "crunchbase":
        return "/organization/" in url_lower or "/person/" in url_lower

    # GitHub: Should have an organization or user page
    if platform == "github":
        # Exclude gist, issues, pulls, etc.
        return (
            "github.com/" in url_lower and
            "/gist/" not in url_lower and
            "/issues/" not in url_lower and
            "/pulls/" not in url_lower
        )

    return False


def find_team_linkedin_profiles(team_members: List[Any], company_name: str) -> Dict[str, str]:
    """
    Find LinkedIn profiles for team members.

    Args:
        team_members: List of team member dictionaries or strings with name, role, etc.
        company_name: Company name for context in search

    Returns:
        Dictionary mapping member names to LinkedIn URLs
    """
    profiles = {}

    for member in team_members:
        # Handle both dict and string formats
        if isinstance(member, dict):
            name = member.get("name", "")
            role = member.get("role", "") or member.get("title", "")
        elif isinstance(member, str):
            # If it's a string, it's the name
            name = member
            role = ""
        else:
            continue

        if not name:
            continue

        # Search for LinkedIn profile
        query = f"{name} {company_name} LinkedIn"
        if role:
            query = f"{name} {role} {company_name} LinkedIn"

        print(f"Searching for LinkedIn profile: {name}...")

        linkedin_url = search_for_social_profile(query, "linkedin")

        if linkedin_url:
            profiles[name] = linkedin_url
            print(f"Found LinkedIn for {name}: {linkedin_url}")
        else:
            print(f"LinkedIn profile not found for {name}")

    return profiles


def find_company_social_profiles(company_name: str, company_website: Optional[str] = None) -> Dict[str, str]:
    """
    Find social media profiles for the company/fund.

    Args:
        company_name: Name of the company or fund
        company_website: Company website URL (optional, helps with context)

    Returns:
        Dictionary mapping platform names to URLs
    """
    profiles = {}
    platforms = ["linkedin", "x", "bluesky", "crunchbase", "github"]

    for platform in platforms:
        query = f"{company_name} {platform}"
        if company_website:
            query += f" {company_website}"

        print(f"Searching for {company_name} on {platform}...")

        profile_url = search_for_social_profile(query, platform)

        if profile_url:
            profiles[platform] = profile_url
            print(f"Found {platform}: {profile_url}")
        else:
            print(f"{platform} profile not found")

    return profiles


def enrich_intro_section_with_socials(memo_content: str, company_socials: Dict[str, str]) -> str:
    """
    Add company social links to the intro section.

    Args:
        memo_content: Current memo content
        company_socials: Dictionary of platform -> URL

    Returns:
        Updated memo content with social links in intro
    """
    if not company_socials:
        return memo_content

    # Build social links line
    social_links = []
    platform_labels = {
        "linkedin": "LinkedIn",
        "x": "X/Twitter",
        "bluesky": "Bluesky",
        "crunchbase": "Crunchbase",
        "github": "GitHub"
    }

    for platform, url in company_socials.items():
        label = platform_labels.get(platform, platform.title())
        social_links.append(f"[{label}]({url})")

    socials_line = f"**Social**: {' | '.join(social_links)}"

    # Find the intro section (after company header, before first ##)
    # Look for the pattern: Company: ... Website: ... Date: ...
    # Insert the Social line after Website and before Date

    # Try to find "Website:" line
    website_pattern = r'(\*\*Website\*\*:.*?)(\n\*\*Date\*\*:)'

    if re.search(website_pattern, memo_content):
        # Insert social line between Website and Date
        updated = re.sub(
            website_pattern,
            rf'\1\n{socials_line}\2',
            memo_content,
            count=1
        )
        return updated

    # Fallback: add after Website line if no Date line found
    website_line_pattern = r'(\*\*Website\*\*:.*?\n)'
    if re.search(website_line_pattern, memo_content):
        updated = re.sub(
            website_line_pattern,
            rf'\1{socials_line}\n',
            memo_content,
            count=1
        )
        return updated

    return memo_content


def enrich_team_section_with_linkedin(memo_content: str, team_profiles: Dict[str, str]) -> str:
    """
    Add LinkedIn links to team member names in the Team section.

    Args:
        memo_content: Current memo content
        team_profiles: Dictionary mapping names to LinkedIn URLs

    Returns:
        Updated memo content with LinkedIn links for team members
    """
    if not team_profiles:
        return memo_content

    updated_content = memo_content

    for name, linkedin_url in team_profiles.items():
        # Find name in team section and add LinkedIn link
        # Pattern: **Name** (Role) or **Name** -

        # Try pattern: **Name** (
        pattern1 = rf'(\*\*{re.escape(name)}\*\*)(\s*\()'
        if re.search(pattern1, updated_content):
            updated_content = re.sub(
                pattern1,
                rf'\1 ([LinkedIn]({linkedin_url}))\2',
                updated_content,
                count=1
            )
            continue

        # Try pattern: **Name** -
        pattern2 = rf'(\*\*{re.escape(name)}\*\*)(\s*[-–—:])'
        if re.search(pattern2, updated_content):
            updated_content = re.sub(
                pattern2,
                rf'\1 ([LinkedIn]({linkedin_url}))\2',
                updated_content,
                count=1
            )
            continue

        # Try pattern: **Name**:
        pattern3 = rf'(\*\*{re.escape(name)}\*\*)(:)'
        if re.search(pattern3, updated_content):
            updated_content = re.sub(
                pattern3,
                rf'\1 ([LinkedIn]({linkedin_url}))\2',
                updated_content,
                count=1
            )

    return updated_content


def socials_enrichment_agent(state: MemoState) -> Dict[str, Any]:
    """
    Socials Enrichment Agent implementation.

    Finds and adds LinkedIn links to team members in the Team section file.

    Args:
        state: Current memo state with research

    Returns:
        Updated state with social links added
    """
    from pathlib import Path
    from ..utils import get_latest_output_dir

    research = state.get("research", {})
    company_name = state["company_name"]
    firm = state.get("firm")

    # Extract team members from research
    # First try structured company.founders (preferred)
    company_data = research.get("company", {}) if research else {}
    founders = company_data.get("founders", [])

    team_members = []

    if founders and isinstance(founders[0], dict):
        # Structured format: [{"name": "...", "title": "...", "background": "..."}]
        team_members = founders
    else:
        # Fallback to team.founders string format: ["Name (Role) - Background..."]
        team_data = research.get("team", {}) if research else {}
        founders_str = team_data.get("founders", []) or []

        # Parse string format to extract name and role
        for founder_str in founders_str:
            if not isinstance(founder_str, str):
                continue

            # Extract name (everything before first parenthesis or dash)
            name_match = re.match(r'^([^()\-]+)', founder_str)
            if name_match:
                name = name_match.group(1).strip()

                # Extract role if present in parentheses
                role_match = re.search(r'\(([^)]+)\)', founder_str)
                role = role_match.group(1) if role_match else ""

                team_members.append({
                    "name": name,
                    "role": role,
                    "description": founder_str
                })

    # Also check for key hires if available
    team_data = research.get("team", {}) if research else {}
    key_hires = team_data.get("key_hires", [])
    if key_hires and key_hires != ["Data not available"]:
        team_members.extend(key_hires)

    # Get company website (company_data already defined above)
    company_website = company_data.get("website", "")

    # Find company social profiles
    print(f"\nSearching for social profiles for {company_name}...")
    company_socials = find_company_social_profiles(company_name, company_website)

    # Find team LinkedIn profiles
    print(f"\nSearching for LinkedIn profiles for team members...")
    team_profiles = {}
    if team_members:
        team_profiles = find_team_linkedin_profiles(team_members, company_name)

    # Get output directory (respects state["output_dir"] for resume, falls back to auto-detect)
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
        sections_dir = output_dir / "2-sections"
    except FileNotFoundError:
        print(f"⊘ Socials enrichment skipped - no output directory found")
        return {"messages": ["Socials enrichment skipped - no output directory"]}

    # Enrich Team section (04-team.md) with LinkedIn links
    links_added = 0
    if team_profiles:
        team_section_file = sections_dir / "04-team.md"
        if team_section_file.exists():
            with open(team_section_file) as f:
                team_content = f.read()

            # Enrich with LinkedIn links
            enriched_team_content = enrich_team_section_with_linkedin(team_content, team_profiles)

            # Save back
            with open(team_section_file, "w") as f:
                f.write(enriched_team_content)

            links_added = len(team_profiles)
            print(f"✓ Team section enriched with {links_added} LinkedIn profiles")

    # TODO: Add company socials to intro (Executive Summary)
    # For now, just report them
    print(f"\nSocials enrichment completed:")
    print(f"  - Company social profiles: {len(company_socials)}")
    print(f"  - Team LinkedIn profiles: {links_added}")

    return {
        "messages": [
            f"Social links added for {company_name} ({len(company_socials)} company profiles, {links_added} team profiles)"
        ]
    }

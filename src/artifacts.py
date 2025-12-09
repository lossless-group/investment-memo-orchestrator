"""
Artifact trail utilities for saving intermediate outputs during memo generation.

This module provides functions to save structured and human-readable artifacts
at each stage of the workflow, enabling transparency and targeted improvements.
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


def sanitize_filename(name: str) -> str:
    """
    Convert company name to safe filename.

    Args:
        name: Company name to sanitize

    Returns:
        Safe filename string
    """
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    return safe_name.replace(' ', '-')


def create_artifact_directory(
    company_name: str,
    version: str,
    firm: str = None,
    io_root: Path = None
) -> Path:
    """
    Create artifact trail directory structure.

    Supports both firm-scoped and legacy directory structures:
    - Firm-scoped: io/{firm}/deals/{company}/outputs/{company}-{version}/
    - Legacy: output/{company}-{version}/

    Args:
        company_name: Name of the company
        version: Version string (e.g., "v0.0.1")
        firm: Optional firm name for firm-scoped outputs
        io_root: Optional IO root directory override

    Returns:
        Path to the artifact directory
    """
    from .paths import resolve_deal_context, create_output_dir_for_deal

    # If firm is provided, use firm-scoped structure
    if firm:
        ctx = resolve_deal_context(company_name, firm=firm, io_root=io_root)
        return create_output_dir_for_deal(ctx, version)

    # Legacy structure
    safe_name = sanitize_filename(company_name)
    output_dir = Path("output") / f"{safe_name}-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create sections subdirectory
    sections_dir = output_dir / "2-sections"
    sections_dir.mkdir(exist_ok=True)

    return output_dir


def save_deck_analysis_artifacts(
    company_name: str,
    deck_analysis: Dict[str, Any],
    section_drafts: Dict[str, str],
    firm: str = None
) -> None:
    """
    Save deck analysis artifacts with 0- prefix.

    Args:
        company_name: Name of the company
        deck_analysis: Deck analysis data
        section_drafts: Initial section drafts from deck
        firm: Optional firm name for firm-scoped outputs
    """
    from .versioning import VersionManager
    from .paths import resolve_deal_context

    # Get or create output directory - firm-aware
    if firm:
        ctx = resolve_deal_context(company_name, firm=firm)
        version_mgr = VersionManager(ctx.outputs_dir.parent if ctx.outputs_dir else Path("output"), firm=firm)
    else:
        version_mgr = VersionManager(Path("output"))

    safe_name = sanitize_filename(company_name)
    version = version_mgr.get_next_version(safe_name)
    output_dir = create_artifact_directory(company_name, version, firm=firm)

    # Save structured JSON
    with open(output_dir / "0-deck-analysis.json", "w") as f:
        json.dump(deck_analysis, f, indent=2, ensure_ascii=False)

    # Save human-readable summary
    summary = format_deck_analysis_summary(deck_analysis)
    with open(output_dir / "0-deck-analysis.md", "w") as f:
        f.write(summary)

    # Save initial section drafts to 0-deck-sections/ (separate from final 2-sections/)
    # These will be fed to Perplexity researcher as citable input
    deck_sections_dir = output_dir / "0-deck-sections"
    deck_sections_dir.mkdir(exist_ok=True)

    for filename, content in section_drafts.items():
        with open(deck_sections_dir / filename, "w") as f:
            f.write(f"<!-- DRAFT FROM DECK ANALYSIS - Cite as [Company Pitch Deck] -->\n\n{content}")

    print(f"Deck analysis artifacts saved: {len(section_drafts)} initial sections created to 0-deck-sections/")


def load_existing_section_drafts(company_name: str, firm: str = None) -> Dict[str, str]:
    """
    Load any existing section drafts from artifacts.

    Args:
        company_name: Name of the company
        firm: Optional firm name for firm-scoped outputs

    Returns:
        Dictionary mapping section filenames to content
    """
    from .versioning import VersionManager
    from .paths import resolve_deal_context

    safe_name = sanitize_filename(company_name)

    # Get version manager - firm-aware
    if firm:
        ctx = resolve_deal_context(company_name, firm=firm)
        version_mgr = VersionManager(ctx.outputs_dir.parent if ctx.outputs_dir else Path("output"), firm=firm)
    else:
        version_mgr = VersionManager(Path("output"))

    # Get the latest version for this company
    if safe_name not in version_mgr.versions_data:
        return {}

    latest_version = version_mgr.versions_data[safe_name]["latest_version"]

    # Get output directory - firm-aware
    if firm:
        output_dir = ctx.get_version_output_dir(latest_version)
    else:
        output_dir = Path("output") / f"{safe_name}-{latest_version}"

    sections_dir = output_dir / "2-sections"

    if not sections_dir.exists():
        return {}

    drafts = {}
    for section_file in sections_dir.glob("*.md"):
        with open(section_file) as f:
            drafts[section_file.name] = f.read()

    return drafts


def format_deck_analysis_summary(deck_analysis: Dict[str, Any]) -> str:
    """
    Create human-readable deck analysis summary.

    Args:
        deck_analysis: Deck analysis data

    Returns:
        Markdown formatted summary
    """
    md = "# Deck Analysis Summary\n\n"
    md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    md += f"**Company**: {deck_analysis.get('company_name', 'N/A')}\n\n"
    md += f"**Pages**: {deck_analysis.get('deck_page_count', 'N/A')}\n\n"
    md += "---\n\n"

    md += "## Key Information Extracted\n\n"

    # Business
    md += "### Business\n\n"
    md += f"- **Tagline**: {deck_analysis.get('tagline', 'Not mentioned')}\n"
    md += f"- **Problem**: {deck_analysis.get('problem_statement', 'Not mentioned')}\n"
    md += f"- **Solution**: {deck_analysis.get('solution_description', 'Not mentioned')}\n"
    md += f"- **Business Model**: {deck_analysis.get('business_model', 'Not mentioned')}\n\n"

    # Market
    if deck_analysis.get('market_size'):
        md += "### Market\n\n"
        md += f"```json\n{json.dumps(deck_analysis.get('market_size', {}), indent=2)}\n```\n\n"

    # Traction
    if deck_analysis.get('traction_metrics'):
        md += "### Traction\n\n"
        md += f"```json\n{json.dumps(deck_analysis.get('traction_metrics', []), indent=2)}\n```\n\n"

    # Team
    if deck_analysis.get('team_members'):
        md += "### Team\n\n"
        md += f"```json\n{json.dumps(deck_analysis.get('team_members', []), indent=2)}\n```\n\n"

    # Funding
    md += "### Funding\n\n"
    md += f"- **Ask**: {deck_analysis.get('funding_ask', 'Not mentioned')}\n"
    if deck_analysis.get('use_of_funds'):
        md += f"- **Use of Funds**: {json.dumps(deck_analysis.get('use_of_funds', []))}\n"
    md += "\n"

    # Go-to-Market & Competition
    if deck_analysis.get('go_to_market') and deck_analysis.get('go_to_market') != 'Not mentioned':
        md += "### Go-to-Market\n\n"
        md += f"{deck_analysis.get('go_to_market')}\n\n"

    if deck_analysis.get('competitive_landscape') and deck_analysis.get('competitive_landscape') != 'Not mentioned':
        md += "### Competitive Landscape\n\n"
        md += f"{deck_analysis.get('competitive_landscape')}\n\n"

    # Extraction notes
    if deck_analysis.get('extraction_notes'):
        md += "## Extraction Notes\n\n"
        for note in deck_analysis.get('extraction_notes', []):
            md += f"- {note}\n"
        md += "\n"

    # Screenshots
    if deck_analysis.get('screenshots'):
        md += "## Extracted Screenshots\n\n"
        md += f"**Total**: {len(deck_analysis['screenshots'])} visual pages captured\n\n"

        # Group by category
        screenshots_by_category = {}
        for screenshot in deck_analysis['screenshots']:
            category = screenshot.get('category', 'general')
            if category not in screenshots_by_category:
                screenshots_by_category[category] = []
            screenshots_by_category[category].append(screenshot)

        for category, screenshots in screenshots_by_category.items():
            md += f"### {category.title()}\n\n"
            for ss in screenshots:
                md += f"- **Page {ss['page_number']}**: {ss.get('description', 'No description')}\n"
                md += f"  - File: `{ss['path']}`\n"
                md += f"  - Dimensions: {ss.get('width', '?')}x{ss.get('height', '?')}px\n"
            md += "\n"

    return md


def save_research_artifacts(output_dir: Path, research_data: Dict[str, Any]) -> None:
    """
    Save research artifacts (JSON and markdown summary).

    Args:
        output_dir: Directory to save artifacts
        research_data: Research data from research agent
    """
    # Save structured JSON
    with open(output_dir / "1-research.json", "w") as f:
        json.dump(research_data, f, indent=2, ensure_ascii=False)

    # Save human-readable markdown summary
    summary = format_research_summary(research_data)
    with open(output_dir / "1-research.md", "w") as f:
        f.write(summary)


def format_research_summary(research_data: Dict[str, Any]) -> str:
    """
    Format research data as human-readable markdown.

    Args:
        research_data: Research data from research agent

    Returns:
        Markdown formatted summary
    """
    md = "# Research Summary\n\n"
    md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    md += "---\n\n"

    # Company overview
    if "company_overview" in research_data:
        md += "## Company Overview\n\n"
        overview = research_data["company_overview"]
        for key, value in overview.items():
            if key != "sources":
                md += f"**{key.replace('_', ' ').title()}**: {value}\n\n"

        if "sources" in overview and overview["sources"]:
            md += "**Sources**:\n"
            for source in overview["sources"]:
                if isinstance(source, dict):
                    md += f"- [{source.get('title', 'Source')}]({source.get('url', '#')})\n"
                else:
                    md += f"- {source}\n"
            md += "\n"

    # Funding
    if "funding" in research_data:
        md += "## Funding & Investors\n\n"
        funding = research_data["funding"]
        for key, value in funding.items():
            if key != "sources" and not isinstance(value, list):
                md += f"**{key.replace('_', ' ').title()}**: {value}\n\n"

        if "rounds" in funding and isinstance(funding["rounds"], list):
            md += "**Funding Rounds**:\n"
            for round_info in funding["rounds"]:
                md += f"- {round_info}\n"
            md += "\n"

        if "investors" in funding and isinstance(funding["investors"], list):
            md += "**Investors**:\n"
            for investor in funding["investors"]:
                md += f"- {investor}\n"
            md += "\n"

        if "sources" in funding and funding["sources"]:
            md += "**Sources**:\n"
            for source in funding["sources"]:
                if isinstance(source, dict):
                    md += f"- [{source.get('title', 'Source')}]({source.get('url', '#')})\n"
                else:
                    md += f"- {source}\n"
            md += "\n"

    # Team
    if "team" in research_data:
        md += "## Team\n\n"
        team = research_data["team"]

        if "founders" in team and isinstance(team["founders"], list):
            md += "**Founders**:\n"
            for founder in team["founders"]:
                if isinstance(founder, dict):
                    name = founder.get("name", "Unknown")
                    title = founder.get("title", "")
                    background = founder.get("background", "")
                    linkedin = founder.get("linkedin_url", "")

                    md += f"- **{name}**"
                    if linkedin:
                        md += f" ([LinkedIn]({linkedin}))"
                    if title:
                        md += f" - {title}"
                    md += "\n"
                    if background:
                        md += f"  - {background}\n"
                else:
                    md += f"- {founder}\n"
            md += "\n"

        if "sources" in team and team["sources"]:
            md += "**Sources**:\n"
            for source in team["sources"]:
                if isinstance(source, dict):
                    md += f"- [{source.get('title', 'Source')}]({source.get('url', '#')})\n"
                else:
                    md += f"- {source}\n"
            md += "\n"

    # Recent news
    if "recent_news" in research_data:
        md += "## Recent News & Developments\n\n"
        news = research_data["recent_news"]

        if "highlights" in news and isinstance(news["highlights"], list):
            for highlight in news["highlights"]:
                md += f"- {highlight}\n"
            md += "\n"

        if "sources" in news and news["sources"]:
            md += "**Sources**:\n"
            for source in news["sources"]:
                if isinstance(source, dict):
                    md += f"- [{source.get('title', 'Source')}]({source.get('url', '#')})\n"
                else:
                    md += f"- {source}\n"
            md += "\n"

    # Web search metadata
    if "web_search_metadata" in research_data:
        md += "---\n\n"
        md += "## Search Metadata\n\n"
        metadata = research_data["web_search_metadata"]
        md += f"**Provider**: {metadata.get('provider', 'Unknown')}\n\n"
        md += f"**Queries Executed**: {metadata.get('queries_count', 0)}\n\n"
        md += f"**Total Results**: {metadata.get('total_results', 0)}\n\n"

    return md


def save_section_artifact(output_dir: Path, section_number: int,
                          section_name: str, content: str) -> None:
    """
    Save individual section to artifacts.

    Args:
        output_dir: Directory to save artifacts
        section_number: Section number (1-10)
        section_name: Name of the section
        content: Section content
    """
    sections_dir = output_dir / "2-sections"
    filename = f"{section_number:02d}-{sanitize_filename(section_name).lower()}.md"

    with open(sections_dir / filename, "w") as f:
        f.write(f"# {section_name}\n\n")
        f.write(content)


def save_validation_artifacts(output_dir: Path, validation_data: Dict[str, Any]) -> None:
    """
    Save validation artifacts (JSON and markdown report).

    Args:
        output_dir: Directory to save artifacts
        validation_data: Validation data from validator agent
    """
    # Save structured JSON
    with open(output_dir / "3-validation.json", "w") as f:
        json.dump(validation_data, f, indent=2, ensure_ascii=False)

    # Save human-readable markdown report
    report = format_validation_report(validation_data)
    with open(output_dir / "3-validation.md", "w") as f:
        f.write(report)


def format_validation_report(validation_data: Dict[str, Any]) -> str:
    """
    Format validation data as human-readable markdown report.

    Args:
        validation_data: Validation data from validator agent

    Returns:
        Markdown formatted report
    """
    md = "# Validation Report\n\n"
    md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    # Overall score
    overall_score = validation_data.get("overall_score", 0.0)
    md += f"## Overall Score: {overall_score}/10\n\n"

    # Determine status
    if overall_score >= 8.0:
        status = "✅ **APPROVED** - Ready for finalization"
        color = "green"
    elif overall_score >= 6.0:
        status = "⚠️ **NEEDS REVISION** - Improvements recommended"
        color = "yellow"
    else:
        status = "❌ **SIGNIFICANT ISSUES** - Major revision required"
        color = "red"

    md += f"{status}\n\n"
    md += "---\n\n"

    # Section-by-section feedback
    if "section_scores" in validation_data:
        md += "## Section Scores\n\n"
        for section_name, section_data in validation_data.get("section_scores", {}).items():
            score = section_data.get("score", 0.0)
            md += f"### {section_name}: {score}/10\n\n"

            if "issues" in section_data and section_data["issues"]:
                md += "**Issues**:\n"
                for issue in section_data["issues"]:
                    md += f"- {issue}\n"
                md += "\n"

            if "suggestions" in section_data and section_data["suggestions"]:
                md += "**Suggestions**:\n"
                for suggestion in section_data["suggestions"]:
                    md += f"- {suggestion}\n"
                md += "\n"

    # Overall issues and suggestions
    full_memo_validation = validation_data.get("full_memo", {})

    if "issues" in full_memo_validation and full_memo_validation["issues"]:
        md += "## Overall Issues\n\n"
        for issue in full_memo_validation["issues"]:
            md += f"- {issue}\n"
        md += "\n"

    if "suggestions" in full_memo_validation and full_memo_validation["suggestions"]:
        md += "## Overall Suggestions\n\n"
        for suggestion in full_memo_validation["suggestions"]:
            md += f"- {suggestion}\n"
        md += "\n"

    return md


def save_fact_check_artifacts(output_dir: Path, fact_check_data: Dict[str, Any]) -> None:
    """
    Save fact-check artifacts (JSON and markdown report).

    Args:
        output_dir: Directory to save artifacts
        fact_check_data: Fact-check data from fact_checker agent
    """
    # Save structured JSON
    with open(output_dir / "4-fact-check.json", "w") as f:
        json.dump(fact_check_data, f, indent=2, ensure_ascii=False)

    # Save human-readable markdown report
    report = format_fact_check_report(fact_check_data)
    with open(output_dir / "4-fact-check.md", "w") as f:
        f.write(report)


def format_fact_check_report(fact_check_data: Dict[str, Any]) -> str:
    """
    Format fact-check data as human-readable markdown report.

    Args:
        fact_check_data: Fact-check data from fact_checker agent

    Returns:
        Markdown formatted report
    """
    md = "# Fact-Check Report\n\n"
    md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    summary = fact_check_data.get("summary", {})
    overall_score = summary.get("overall_score", 0.0)
    total_claims = summary.get("total_claims", 0)
    verified_claims = summary.get("verified_claims", 0)
    sections_flagged = summary.get("sections_flagged", 0)
    strictness = summary.get("strictness", "high")

    md += f"## Overall Score: {overall_score:.0%}\n\n"
    md += f"**Strictness**: {strictness.upper()}\n"
    md += f"**Total Claims**: {total_claims}\n"
    md += f"**Verified (with citations)**: {verified_claims}\n"
    md += f"**Sections Flagged**: {sections_flagged}\n\n"

    # Determine status
    if fact_check_data.get("overall_pass", False):
        status = "✅ **PASSED** - All claims sourced"
    else:
        status = f"⚠️ **REVIEW REQUIRED** - {sections_flagged} sections need attention"

    md += f"{status}\n\n"
    md += "---\n\n"

    # Section-by-section results
    if "fact_check_results" in fact_check_data:
        md += "## Section Results\n\n"
        for section_data in fact_check_data.get("fact_check_results", []):
            section_name = section_data.get("section", "Unknown")
            total = section_data.get("total_claims", 0)
            verified = section_data.get("verified_claims", 0)
            score = section_data.get("score", 0.0)
            requires_rewrite = section_data.get("requires_rewrite", False)

            status_icon = "❌" if requires_rewrite else "✅"
            md += f"### {status_icon} {section_name}\n\n"
            md += f"- **Score**: {score:.0%}\n"
            md += f"- **Claims**: {verified}/{total} verified\n"

            if requires_rewrite:
                md += f"- **Status**: ⚠️ Requires review\n"

                critical_issues = section_data.get("critical_issues", [])
                if critical_issues:
                    md += f"\n**Critical Issues** ({len(critical_issues)}):\n"
                    for issue in critical_issues[:5]:  # Show first 5
                        md += f"- {issue[:150]}...\n"

            md += "\n"

    # Sections to rewrite
    sections_to_rewrite = fact_check_data.get("sections_to_rewrite", [])
    if sections_to_rewrite:
        md += "## Sections Requiring Revision\n\n"
        for section in sections_to_rewrite:
            section_display = section.replace('-', ' ').title()
            md += f"- {section_display}\n"
        md += "\n"
        md += "**Recommendation**: Use `improve-section.py` to add citations or remove unsourced claims.\n\n"

    return md


# =============================================================================
# FINAL DRAFT UTILITIES - Re-exported from src/final_draft.py
# =============================================================================
# These are re-exported here for backwards compatibility.
# For new code, import directly from src.final_draft instead.

from .final_draft import (
    get_final_draft_filename,
    get_final_draft_path,
    find_final_draft,
    final_draft_exists,
    read_final_draft,
    write_final_draft,
    save_final_draft,
    find_all_final_drafts,
    is_final_draft_file,
)


def save_state_snapshot(output_dir: Path, state: Dict[str, Any]) -> None:
    """
    Save complete workflow state for debugging.

    Args:
        output_dir: Directory to save artifacts
        state: Complete workflow state
    """
    # Filter out non-serializable data
    serializable_state = {
        k: v for k, v in state.items()
        if k not in ["messages"] and not callable(v)
    }

    with open(output_dir / "state.json", "w") as f:
        json.dump(serializable_state, f, indent=2, default=str, ensure_ascii=False)

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


def create_artifact_directory(company_name: str, version: str) -> Path:
    """
    Create artifact trail directory structure.

    Args:
        company_name: Name of the company
        version: Version string (e.g., "v0.0.1")

    Returns:
        Path to the artifact directory
    """
    safe_name = sanitize_filename(company_name)
    output_dir = Path("output") / f"{safe_name}-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create sections subdirectory
    sections_dir = output_dir / "2-sections"
    sections_dir.mkdir(exist_ok=True)

    return output_dir


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


def save_final_draft(output_dir: Path, content: str) -> None:
    """
    Save final assembled memo.

    Args:
        output_dir: Directory to save artifacts
        content: Final memo content
    """
    with open(output_dir / "4-final-draft.md", "w") as f:
        f.write(content)


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

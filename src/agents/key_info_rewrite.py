"""
Key Information Rewrite Agent.

This agent applies YAML-based corrections to investment memo sections,
handling factual corrections, incomplete information, and narrative shaping.
"""

import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
from anthropic import Anthropic
from rich.console import Console

from src.corrections import CorrectionObject, CorrectionsConfig
from src.versioning import VersionManager
from src.artifacts import sanitize_filename


# Initialize Anthropic client
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def apply_correction_to_section(
    section_file: Path,
    correction: CorrectionObject,
    company_name: str,
    console: Console
) -> Tuple[str, int]:
    """
    Apply single correction to a section file.

    Args:
        section_file: Path to section markdown file
        correction: CorrectionObject with correction details
        company_name: Company name for context
        console: Rich console for output

    Returns:
        Tuple of (corrected_content, instances_corrected)
    """
    with open(section_file) as f:
        original_content = f.read()

    # Build correction prompt
    prompt = build_correction_prompt(
        original_content=original_content,
        correction=correction,
        company_name=company_name
    )

    # Call Claude for correction
    console.print(f"  [dim]Processing: {section_file.name}...[/dim]")

    response = anthropic_client.messages.create(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )

    corrected_content = response.content[0].text

    # Count changes (rough estimate)
    instances_corrected = count_correction_instances(original_content, corrected_content, correction)

    return corrected_content, instances_corrected


def build_correction_prompt(
    original_content: str,
    correction: CorrectionObject,
    company_name: str
) -> str:
    """Build LLM prompt for applying correction."""

    prompt = f"""You are correcting an investment memo section for {company_name}.

CORRECTION TYPE: {correction.type.upper()}

"""

    # Add correction-specific instructions
    if correction.inaccurate_info:
        prompt += f"""INACCURATE INFORMATION TO CORRECT:
{correction.inaccurate_info}

CORRECT INFORMATION:
{correction.correct_info}

"""

    if correction.incomplete_info:
        prompt += f"""INCOMPLETE - MISSING INFORMATION:
{correction.incomplete_info}

ADDITIONAL INFORMATION TO ADD:
{correction.additional_info}

"""

    if correction.narrative_comments:
        prompt += f"""NARRATIVE SHAPING GUIDANCE:
{chr(10).join(f"• {comment}" for comment in correction.narrative_comments)}

"""

    if correction.sources:
        prompt += f"""SOURCES FOR REFERENCE:
{chr(10).join(f"• {source}" for source in correction.sources)}

"""

    prompt += f"""CURRENT SECTION CONTENT:
{original_content}

TASK:
1. Apply factual corrections (replace inaccurate → correct information)
2. Add missing information where incomplete
3. Follow narrative shaping guidance for tone and framing
4. Preserve ALL existing citations (do not remove or modify them)
5. Add NEW citations [^X] for newly added facts (use sources provided above)
6. Maintain all formatting (headers, lists, emphasis)
7. Do NOT change content unrelated to this correction

CRITICAL REQUIREMENTS:
- If factual claims become unsupported after correction, flag with [NEEDS CITATION]
- Maintain analytical tone (not promotional or dismissive)
- Preserve section structure
- Return ONLY the corrected section content

CORRECTED SECTION:
"""

    return prompt


def count_correction_instances(
    original: str,
    corrected: str,
    correction: CorrectionObject
) -> int:
    """
    Estimate number of correction instances applied.

    This is a rough heuristic based on content changes.
    """
    if correction.type == "narrative":
        # For narrative, count substantial changes
        return 1 if len(corrected) != len(original) else 0

    # For factual corrections, count instances of incorrect info replaced
    if correction.inaccurate_info and correction.correct_info:
        # Simple heuristic: count occurrences of correct info in new content
        # that weren't in original
        return corrected.lower().count(correction.correct_info.lower()[:20]) if correction.correct_info else 0

    return 1  # Default


def apply_corrections_to_memo(
    corrections_config: CorrectionsConfig,
    artifact_dir: Path,
    console: Console,
    preview: bool = False
) -> Dict[str, Any]:
    """
    Apply all corrections to memo, creating new version or modifying in-place.

    Args:
        corrections_config: Parsed corrections configuration
        artifact_dir: Source artifact directory
        console: Rich console for output
        preview: If True, show changes without saving

    Returns:
        Dictionary with correction results and statistics
    """
    console.print(f"\n[bold]Applying {len(corrections_config.corrections)} correction(s)...[/bold]")

    # Determine output directory
    if corrections_config.output_mode == "new_version":
        output_dir = create_new_version_directory(artifact_dir, console)
    else:
        output_dir = artifact_dir
        if not preview:
            console.print("[yellow]⚠️  In-place mode: Will overwrite existing files[/yellow]")

    # Track changes
    changes = []
    sections_modified = set()
    total_instances = 0

    # Process each correction
    for i, correction in enumerate(corrections_config.corrections, 1):
        console.print(f"\n[cyan]Correction {i}/{len(corrections_config.corrections)}[/cyan] ({correction.type})")

        # Get affected sections
        if correction.type == "narrative":
            affected_sections = [correction.section]
        else:
            affected_sections = correction.affected_sections

        correction_instances = 0

        # Apply to each affected section
        for section_name in affected_sections:
            section_file = find_section_file(output_dir / "2-sections", section_name)

            if not section_file:
                console.print(f"  [yellow]⚠️  Section not found: {section_name}[/yellow]")
                continue

            # Apply correction
            corrected_content, instances = apply_correction_to_section(
                section_file=section_file,
                correction=correction,
                company_name=corrections_config.company,
                console=console
            )

            if not preview:
                # Save corrected section
                with open(section_file, "w") as f:
                    f.write(corrected_content)

            console.print(f"    ✓ {section_name} ({instances} change(s))")

            sections_modified.add(section_name)
            correction_instances += instances

        total_instances += correction_instances

        # Track change
        changes.append({
            "correction_type": correction.type,
            "sections_affected": affected_sections,
            "instances_corrected": correction_instances,
            "summary": get_correction_summary_text(correction)
        })

    # Reassemble final draft
    if not preview:
        console.print(f"\n[bold]Reassembling final draft...[/bold]")
        final_draft = reassemble_final_draft(output_dir, console)

        # Save corrections log
        log_path = save_corrections_log(
            output_dir=output_dir,
            source_version=artifact_dir.name if corrections_config.output_mode == "new_version" else artifact_dir.name,
            output_version=output_dir.name,
            output_mode=corrections_config.output_mode,
            corrections_file=corrections_config.company,
            changes=changes,
            sections_modified=len(sections_modified),
            total_instances=total_instances
        )

        console.print(f"[green]✓ Corrections log saved:[/green] {log_path}")

    # Return results
    return {
        "output_dir": output_dir,
        "sections_modified": len(sections_modified),
        "total_instances": total_instances,
        "changes": changes,
        "preview": preview
    }


def create_new_version_directory(source_dir: Path, console: Console) -> Path:
    """
    Create new version directory by copying source and incrementing version.

    Args:
        source_dir: Source artifact directory (e.g., output/Avalanche-v0.0.3)
        console: Rich console for output

    Returns:
        Path to new version directory
    """
    # Parse version
    dir_name = source_dir.name
    parts = dir_name.rsplit("-v", 1)

    if len(parts) != 2:
        raise ValueError(f"Invalid version directory format: {dir_name}")

    base_name, version_str = parts

    # Increment version
    version_parts = version_str.split(".")
    patch = int(version_parts[2]) + 1
    new_version = f"{version_parts[0]}.{version_parts[1]}.{patch}"
    new_dir_name = f"{base_name}-v{new_version}"

    # Create new directory
    new_dir = source_dir.parent / new_dir_name

    if new_dir.exists():
        console.print(f"[yellow]⚠️  Version {new_version} already exists, overwriting...[/yellow]")
        shutil.rmtree(new_dir)

    console.print(f"[cyan]📦 Creating new version:[/cyan] v{new_version}")

    # Copy all artifacts from source
    shutil.copytree(source_dir, new_dir)

    console.print(f"  [dim]✓ Copied artifacts from {source_dir.name}[/dim]")

    return new_dir


def find_section_file(sections_dir: Path, section_name: str) -> Path | None:
    """
    Find section file by section name.

    Args:
        sections_dir: Directory containing section files
        section_name: Section name to find

    Returns:
        Path to section file or None if not found
    """
    # Section name mappings (same as improve-section.py)
    section_map = {
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
        # Fund template
        "GP Background & Track Record": "02-gp-background--track-record.md",
        "Fund Strategy & Thesis": "03-fund-strategy--thesis.md",
        "Portfolio Construction": "04-portfolio-construction.md",
        "Value Add & Differentiation": "05-value-add--differentiation.md",
        "Track Record Analysis": "06-track-record-analysis.md",
        "Fee Structure & Economics": "07-fee-structure--economics.md",
        "LP Base & References": "08-lp-base--references.md",
    }

    filename = section_map.get(section_name)
    if not filename:
        return None

    section_file = sections_dir / filename
    return section_file if section_file.exists() else None


def reassemble_final_draft(artifact_dir: Path, console: Console) -> Path:
    """
    Reassemble 4-final-draft.md using the canonical assembly tool.

    Delegates to cli.assemble_draft which handles:
    - Citation renumbering and consolidation
    - Table of Contents generation

    Args:
        artifact_dir: Artifact directory
        console: Rich console for output

    Returns:
        Path to final draft file
    """
    from cli.assemble_draft import assemble_final_draft as canonical_assemble

    return canonical_assemble(artifact_dir, console)


def save_corrections_log(
    output_dir: Path,
    source_version: str,
    output_version: str,
    output_mode: str,
    corrections_file: str,
    changes: List[Dict],
    sections_modified: int,
    total_instances: int
) -> Path:
    """
    Save corrections log JSON for audit trail.

    Args:
        output_dir: Output directory
        source_version: Source version name
        output_version: Output version name
        output_mode: "new_version" or "in_place"
        corrections_file: Name of corrections file
        changes: List of change dictionaries
        sections_modified: Number of sections modified
        total_instances: Total correction instances

    Returns:
        Path to corrections log file
    """
    log_data = {
        "source_version": source_version,
        "output_version": output_version,
        "output_mode": output_mode,
        "corrections_applied": len(changes),
        "sections_modified": sections_modified,
        "total_instances_corrected": total_instances,
        "timestamp": datetime.now().isoformat(),
        "corrections_file": corrections_file,
        "changes": changes
    }

    log_file = output_dir / "corrections-log.json"
    with open(log_file, "w") as f:
        json.dump(log_data, f, indent=2)

    return log_file


def get_correction_summary_text(correction: CorrectionObject) -> str:
    """Generate summary text for a correction."""
    if correction.type == "inaccurate":
        return f"Corrected: {correction.inaccurate_info[:50]}... → {correction.correct_info[:50]}..."
    elif correction.type == "incomplete":
        return f"Added: {correction.additional_info[:80]}..."
    elif correction.type == "narrative":
        return f"Improved narrative in {correction.section}"
    elif correction.type == "mixed":
        parts = []
        if correction.inaccurate_info:
            parts.append("corrected inaccuracies")
        if correction.incomplete_info:
            parts.append("added missing info")
        if correction.narrative_comments:
            parts.append("improved narrative")
        return ", ".join(parts).capitalize()
    return "Unknown correction"

#!/usr/bin/env python3
"""
Assemble Final Draft from Section Files.

This is the CANONICAL tool for rebuilding 4-final-draft.md from 2-sections/.
All CLI tools that modify sections should call this after their changes.

USAGE:
    python -m cli.assemble_draft "Company"
    python -m cli.assemble_draft "Company" --version v0.0.2
    python -m cli.assemble_draft output/Company-v0.0.2

This tool ensures formatting integrity by:
1. Loading header.md (company trademark) if exists
2. Loading all sections from 2-sections/ in order
3. Renumbering citations globally ([^1], [^2]... sequentially)
4. Consolidating all citation references into ONE block at document end
5. Generating/updating Table of Contents with anchor links
6. Saving the polished 4-final-draft.md

Can be called programmatically:
    from cli.assemble_draft import assemble_final_draft
    final_path = assemble_final_draft(artifact_dir, console)
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename
from src.versioning import VersionManager
from src.agents.citation_enrichment import renumber_citations_globally
from src.agents.toc_generator import extract_headers, generate_toc_markdown, insert_toc_after_header


def assemble_final_draft(
    artifact_dir: Path,
    console: Optional[Console] = None,
    verbose: bool = True
) -> Path:
    """
    Assemble 4-final-draft.md from section files with full polish.

    This is the canonical assembly function. It ensures:
    - Citations are renumbered globally (no collisions)
    - All citation references consolidated at document end
    - Table of Contents is present and accurate

    Args:
        artifact_dir: Path to artifact directory (e.g., output/Sava-v0.0.2)
        console: Optional Rich console for styled output
        verbose: Whether to print progress messages

    Returns:
        Path to the saved 4-final-draft.md file
    """
    if console is None:
        console = Console()

    def log(msg: str, style: str = "dim"):
        if verbose:
            console.print(f"[{style}]  • {msg}[/{style}]")

    sections_dir = artifact_dir / "2-sections"
    if not sections_dir.exists():
        raise FileNotFoundError(f"Sections directory not found: {sections_dir}")

    # Step 1: Load header if exists (company trademark)
    header_content = ""
    header_file = artifact_dir / "header.md"
    if header_file.exists():
        with open(header_file) as f:
            header_content = f.read() + "\n"
        log("Loaded header.md (company trademark)")

    # Step 2: Load all sections in order
    section_files = sorted(sections_dir.glob("*.md"))
    log(f"Loading {len(section_files)} sections...")

    sections_data = []
    for section_file in section_files:
        # Parse filename: 01-executive-summary.md → (1, "Executive Summary", content)
        filename = section_file.stem
        parts = filename.split("-", 1)
        section_num = int(parts[0])
        section_name = parts[1].replace("--", " & ").replace("-", " ").title()

        with open(section_file) as f:
            section_content = f.read()

        sections_data.append((section_num, section_name, section_content))

    # Step 3 & 4: Renumber citations globally and consolidate references
    log("Renumbering citations globally...")
    consolidated_content = renumber_citations_globally(sections_data)

    # Combine header + content
    content = header_content + consolidated_content

    # Step 5: Generate/update Table of Contents
    # First, remove any existing TOC to prevent duplication
    content = remove_existing_toc(content)

    headers = extract_headers(content)
    if headers:
        log("Generating Table of Contents...")
        toc = generate_toc_markdown(headers)
        content = insert_toc_after_header(content, toc)
        h2_count = sum(1 for h in headers if h[0] == 2)
        h3_count = sum(1 for h in headers if h[0] == 3)
        log(f"TOC: {h2_count} sections, {h3_count} subsections")

    # Step 6: Save final draft
    final_draft = artifact_dir / "4-final-draft.md"
    with open(final_draft, "w") as f:
        f.write(content.strip())

    console.print(f"[green]✓ Final draft assembled:[/green] {final_draft}")

    return final_draft


def remove_existing_toc(content: str) -> str:
    """
    Remove existing Table of Contents to prevent duplication.

    Finds the TOC section (## Table of Contents) and removes it
    up to the next ## header or significant content.
    """
    import re

    # Pattern: ## Table of Contents followed by list items until next ## header
    toc_pattern = r'## Table of Contents\n(?:[ \t]*-[^\n]*\n)*\n*'
    content = re.sub(toc_pattern, '', content)

    return content


def resolve_artifact_dir(target: str, version: Optional[str] = None) -> Path:
    """
    Resolve artifact directory from company name or path.

    Args:
        target: Company name or direct path to artifact directory
        version: Optional version string (e.g., 'v0.0.2', 'latest')

    Returns:
        Path to artifact directory
    """
    target_path = Path(target)

    # Direct path provided
    if target_path.exists() and target_path.is_dir():
        return target_path

    # Company name - resolve via version manager
    safe_name = sanitize_filename(target)
    output_dir = Path("output")

    if version:
        artifact_dir = output_dir / f"{safe_name}-{version}"
    else:
        # Find latest version
        version_mgr = VersionManager(output_dir)
        if safe_name not in version_mgr.versions_data:
            raise ValueError(f"No versions found for '{target}'")

        latest_version = version_mgr.versions_data[safe_name]["latest_version"]
        artifact_dir = output_dir / f"{safe_name}-{latest_version}"

    if not artifact_dir.exists():
        raise FileNotFoundError(f"Artifact directory not found: {artifact_dir}")

    return artifact_dir


def main():
    """CLI entry point."""
    console = Console()

    parser = argparse.ArgumentParser(
        description="Assemble final draft from section files with citation renumbering and TOC"
    )
    parser.add_argument(
        "target",
        help="Company name (e.g., 'Sava') or path to artifact directory"
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.2'). If not specified, uses latest."
    )

    args = parser.parse_args()

    try:
        artifact_dir = resolve_artifact_dir(args.target, args.version)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(Panel(
        f"[bold cyan]Assembling Final Draft[/bold cyan]\n"
        f"[dim]Artifact directory: {artifact_dir}[/dim]"
    ))

    try:
        final_draft = assemble_final_draft(artifact_dir, console)

        # Show summary
        with open(final_draft) as f:
            content = f.read()

        import re
        citation_count = len(set(re.findall(r'\[\^(\d+)\]', content)))
        word_count = len(content.split())

        console.print(f"\n[bold cyan]Summary:[/bold cyan]")
        console.print(f"  Words: {word_count:,}")
        console.print(f"  Citations: {citation_count}")
        console.print(f"\n[bold cyan]Next steps:[/bold cyan]")
        console.print(f"  View: {final_draft}")
        console.print(f"  Export: python export-branded.py {final_draft} --brand hypernova")

    except Exception as e:
        console.print(f"[red]Error assembling draft:[/red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Correct crucial information in investment memos using YAML correction files.

This script applies YAML-based corrections to investment memos, handling:
- Inaccurate information (factual corrections)
- Incomplete information (adding missing facts)
- Narrative shaping (tone and framing improvements)
- Mixed corrections (combination of above)

USAGE:
    python rewrite-key-info.py --corrections data/Avalanche-corrections.yaml
    python rewrite-key-info.py --corrections data/Avalanche-corrections.yaml --verify-sources
    python rewrite-key-info.py --corrections data/Avalanche-corrections.yaml --preview

Requirements:
    - ANTHROPIC_API_KEY must be set in .env file
    - Existing artifact directory with sections
    - Valid corrections YAML file
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.corrections import load_corrections_yaml, get_correction_summary
from src.agents.key_info_rewrite import apply_corrections_to_memo
from src.versioning import VersionManager
from src.artifacts import sanitize_filename


def main():
    """Main entry point."""
    console = Console()

    # Load environment
    load_dotenv()

    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set")
        console.print("[yellow]Set ANTHROPIC_API_KEY in your .env file.[/yellow]")
        sys.exit(1)

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Apply YAML-based corrections to investment memos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python rewrite-key-info.py --corrections data/Avalanche-corrections.yaml

  # Preview changes without saving
  python rewrite-key-info.py --corrections data/Avalanche-corrections.yaml --preview

  # Override output mode (force in-place)
  python rewrite-key-info.py --corrections data/Avalanche-corrections.yaml --output-mode in_place

  # Use specific source version
  python rewrite-key-info.py --corrections data/Avalanche-corrections.yaml --source-version v0.0.2
        """
    )
    parser.add_argument(
        "--corrections",
        required=True,
        help="Path to corrections YAML file"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview changes without saving (dry run)"
    )
    parser.add_argument(
        "--output-mode",
        choices=["new_version", "in_place"],
        help="Override YAML output_mode setting"
    )
    parser.add_argument(
        "--source-version",
        help="Override YAML source_version (e.g., 'latest', 'v0.0.3')"
    )
    parser.add_argument(
        "--source-path",
        help="Direct path to source artifact directory (bypasses version resolution)"
    )

    args = parser.parse_args()

    # Load corrections YAML
    corrections_file = Path(args.corrections)
    if not corrections_file.exists():
        console.print(f"[red]Error: Corrections file not found:[/red] {corrections_file}")
        sys.exit(1)

    console.print(Panel(
        f"[bold cyan]Key Information Rewrite[/bold cyan]\n"
        f"[dim]Corrections file: {corrections_file}[/dim]",
        expand=False
    ))

    try:
        corrections_config = load_corrections_yaml(corrections_file)
    except ValueError as e:
        console.print(f"[red]Error: Invalid corrections YAML:[/red] {e}")
        sys.exit(1)

    # Apply CLI overrides
    if args.output_mode:
        corrections_config.output_mode = args.output_mode
        console.print(f"[yellow]Override:[/yellow] output_mode = {args.output_mode}")

    if args.source_version:
        corrections_config.source_version = args.source_version
        console.print(f"[yellow]Override:[/yellow] source_version = {args.source_version}")

    # Display corrections summary
    console.print(f"\n[bold]Corrections Summary:[/bold]")
    console.print(f"  Company: {corrections_config.company}")
    console.print(f"  Source version: {corrections_config.source_version}")
    console.print(f"  Output mode: {corrections_config.output_mode}")
    console.print(f"  Total corrections: {len(corrections_config.corrections)}")

    if args.preview:
        console.print(f"  [yellow]Mode: PREVIEW (no changes will be saved)[/yellow]")

    # Show corrections table
    table = Table(title="\nCorrections to Apply", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("Type", style="cyan")
    table.add_column("Summary", style="white")
    table.add_column("Sections", style="green")

    for i, correction in enumerate(corrections_config.corrections, 1):
        summary = get_correction_summary(correction)
        if correction.type == "narrative":
            sections = correction.section
        else:
            sections = f"{len(correction.affected_sections)} section(s)"

        table.add_row(str(i), correction.type, summary, sections)

    console.print(table)

    # Determine artifact directory
    if args.source_path:
        artifact_dir = Path(args.source_path)
        if not artifact_dir.exists():
            console.print(f"[red]Error: Source path not found:[/red] {artifact_dir}")
            sys.exit(1)
    else:
        # Resolve version
        artifact_dir = resolve_artifact_directory(
            company_name=corrections_config.company,
            source_version=corrections_config.source_version,
            console=console
        )

    if not artifact_dir:
        sys.exit(1)

    console.print(f"\n[bold]Source artifact directory:[/bold] {artifact_dir}")

    # Validate sections directory exists
    sections_dir = artifact_dir / "2-sections"
    if not sections_dir.exists():
        console.print(f"[red]Error: Sections directory not found:[/red] {sections_dir}")
        sys.exit(1)

    # Warn for in_place mode
    if corrections_config.output_mode == "in_place" and not args.preview:
        console.print("\n[bold yellow]⚠️  WARNING: In-place mode will overwrite existing files![/bold yellow]")
        console.print("[yellow]Original content will be lost. Use --preview to see changes first.[/yellow]")

        response = input("\nContinue? [y/N]: ")
        if response.lower() != "y":
            console.print("[dim]Cancelled.[/dim]")
            sys.exit(0)

    # Apply corrections
    try:
        result = apply_corrections_to_memo(
            corrections_config=corrections_config,
            artifact_dir=artifact_dir,
            console=console,
            preview=args.preview
        )
    except Exception as e:
        console.print(f"\n[red]Error applying corrections:[/red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Display results
    console.print("\n" + "=" * 80)
    console.print(Panel(
        "[bold green]Corrections Applied Successfully[/bold green]"
        if not args.preview else
        "[bold cyan]Preview Complete (No Changes Saved)[/bold cyan]",
        expand=False
    ))

    console.print(f"\n[bold cyan]Summary:[/bold cyan]")
    if corrections_config.output_mode == "new_version" and not args.preview:
        console.print(f"  Source version: {artifact_dir.name}")
        console.print(f"  Output version: {result['output_dir'].name} [green](NEW)[/green]")
    else:
        console.print(f"  Version: {artifact_dir.name} {'(MODIFIED IN-PLACE)' if not args.preview else '(PREVIEW ONLY)'}")

    console.print(f"  Corrections applied: {len(corrections_config.corrections)}")
    console.print(f"  Sections modified: {result['sections_modified']}")
    console.print(f"  Total instances: {result['total_instances']}")

    if not args.preview:
        console.print(f"\n[bold cyan]Next steps:[/bold cyan]")
        console.print(f"  1. Review corrections: {result['output_dir']}/2-sections/")
        console.print(f"  2. View final draft: {result['output_dir']}/4-final-draft.md")
        if corrections_config.output_mode == "new_version":
            console.print(f"  3. Compare versions: diff {artifact_dir}/4-final-draft.md {result['output_dir']}/4-final-draft.md")
        console.print(f"  4. Export to HTML: python export-branded.py {result['output_dir']}/4-final-draft.md")


def resolve_artifact_directory(
    company_name: str,
    source_version: str,
    console: Console
) -> Path | None:
    """
    Resolve artifact directory from company name and version.

    Args:
        company_name: Company name
        source_version: Version string ("latest", "v0.0.3", or path)
        console: Rich console for output

    Returns:
        Path to artifact directory or None if not found
    """
    output_dir = Path("output")

    # Check if source_version is a path
    if "/" in source_version or "\\" in source_version:
        artifact_dir = Path(source_version)
        if artifact_dir.exists():
            return artifact_dir
        else:
            console.print(f"[red]Error: Path not found:[/red] {artifact_dir}")
            return None

    # Resolve company name
    safe_name = sanitize_filename(company_name)

    # Find version
    version_mgr = VersionManager(output_dir)

    if safe_name not in version_mgr.versions_data:
        console.print(f"[red]Error: No versions found for '{company_name}'[/red]")
        console.print(f"[yellow]Available companies:[/yellow]")
        for comp in sorted(version_mgr.versions_data.keys()):
            console.print(f"  • {comp}")
        return None

    # Resolve version
    if source_version == "latest":
        version = version_mgr.versions_data[safe_name]["latest_version"]
        console.print(f"[dim]Resolved 'latest' to {version}[/dim]")
    else:
        version = source_version
        # Validate version exists by checking history
        available_versions = [v["version"] for v in version_mgr.versions_data[safe_name]["history"]]
        if version not in available_versions:
            console.print(f"[red]Error: Version '{version}' not found for '{company_name}'[/red]")
            console.print(f"[yellow]Available versions:[/yellow]")
            for v in sorted(available_versions):
                console.print(f"  • {v}")
            return None

    artifact_dir = output_dir / f"{safe_name}-{version}"

    if not artifact_dir.exists():
        console.print(f"[red]Error: Artifact directory not found:[/red] {artifact_dir}")
        return None

    return artifact_dir


if __name__ == "__main__":
    main()

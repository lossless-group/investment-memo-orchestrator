#!/usr/bin/env python3
"""
Sanitize Commentary CLI

Extracts LLM process commentary from memo sections and moves it to
a separate internal notes folder, leaving clean, shareable content.

Usage:
    python cli/sanitize_commentary.py "Company Name"
    python cli/sanitize_commentary.py "Company Name" --version v0.0.1
    python cli/sanitize_commentary.py --firm hypernova --deal Blinka
    python cli/sanitize_commentary.py output/Company-v0.0.1

This addresses the inherent LLM tendency to include meta-commentary like:
- "Let me search for..."
- "Note: Unable to find..."
- "If you have the actual content, please share..."

The extracted commentary is preserved in 2-sections-internal/ for internal
review, while the main sections become clean and shareable.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.agents.internal_comments_sanitizer import sanitize_memo, extract_commentary
from src.utils import get_latest_output_dir
from src.artifacts import sanitize_filename


def main():
    console = Console()

    parser = argparse.ArgumentParser(
        description="Extract LLM process commentary from memo sections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Sanitize latest version
    python cli/sanitize_commentary.py "Avalanche"

    # Sanitize specific version
    python cli/sanitize_commentary.py "Avalanche" --version v0.0.3

    # Firm-scoped deal
    python cli/sanitize_commentary.py --firm hypernova --deal Blinka

    # Direct path to output directory
    python cli/sanitize_commentary.py output/Avalanche-v0.0.1

    # Preview mode (show what would be extracted without modifying)
    python cli/sanitize_commentary.py "Avalanche" --preview
        """
    )

    parser.add_argument(
        "company_or_path",
        nargs="?",
        help="Company name or direct path to output directory"
    )
    parser.add_argument(
        "--firm",
        type=str,
        help="Firm name for firm-scoped IO (e.g., 'hypernova')"
    )
    parser.add_argument(
        "--deal",
        type=str,
        help="Deal name (alternative to positional argument)"
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Specific version to sanitize (e.g., v0.0.1)"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview what would be extracted without modifying files"
    )
    parser.add_argument(
        "--reassemble",
        action="store_true",
        default=True,
        help="Reassemble final draft after sanitization (default: True)"
    )
    parser.add_argument(
        "--no-reassemble",
        action="store_true",
        help="Skip reassembling final draft"
    )

    args = parser.parse_args()

    # Determine company name and output directory
    company_name = args.deal or args.company_or_path
    firm = args.firm

    if not company_name:
        console.print("[bold red]Error:[/bold red] Please provide a company/deal name or path")
        parser.print_help()
        sys.exit(1)

    # Check if it's a direct path
    if Path(company_name).exists() and Path(company_name).is_dir():
        output_dir = Path(company_name)
        # Extract company name from path
        company_name = output_dir.name.rsplit('-v', 1)[0]
        console.print(f"[dim]Using direct path: {output_dir}[/dim]")
    else:
        # Resolve output directory
        try:
            if args.version:
                safe_name = sanitize_filename(company_name)
                if firm:
                    from src.paths import resolve_deal_context
                    ctx = resolve_deal_context(company_name, firm=firm)
                    output_dir = ctx.outputs_dir / f"{safe_name}-{args.version}"
                else:
                    output_dir = Path("output") / f"{safe_name}-{args.version}"
            else:
                output_dir = get_latest_output_dir(company_name, firm=firm)
        except FileNotFoundError:
            console.print(f"[bold red]Error:[/bold red] No output directory found for '{company_name}'")
            sys.exit(1)

    if not output_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Output directory not found: {output_dir}")
        sys.exit(1)

    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        console.print(f"[bold red]Error:[/bold red] Sections directory not found: {sections_dir}")
        sys.exit(1)

    # Display header
    console.print()
    console.print(Panel(
        f"[bold cyan]COMMENTARY SANITIZER[/bold cyan]\n\n"
        f"Company: {company_name}\n"
        f"Directory: {output_dir}\n"
        f"Mode: {'Preview' if args.preview else 'Sanitize'}",
        expand=False
    ))
    console.print()

    if args.preview:
        # Preview mode - just show what would be extracted
        console.print("[bold yellow]PREVIEW MODE[/bold yellow] - No files will be modified\n")

        section_files = sorted(sections_dir.glob("*.md"))
        total_items = 0

        for section_file in section_files:
            content = section_file.read_text()
            clean_content, extracted_notes, extraction_log = extract_commentary(content)

            if extraction_log:
                console.print(f"[bold]{section_file.name}[/bold] - {len(extraction_log)} items to extract:")
                for item in extraction_log[:5]:  # Show first 5
                    preview = item.get('preview', '')[:60]
                    category = item.get('category', 'unknown')
                    console.print(f"  [{category}] {preview}...")
                if len(extraction_log) > 5:
                    console.print(f"  ... and {len(extraction_log) - 5} more")
                console.print()
                total_items += len(extraction_log)
            else:
                console.print(f"[dim]{section_file.name} - Clean (no commentary)[/dim]")

        console.print()
        console.print(f"[bold]Total items to extract: {total_items}[/bold]")
        console.print()
        console.print("[dim]Run without --preview to sanitize files[/dim]")

    else:
        # Actual sanitization
        try:
            result = sanitize_memo(company_name, firm=firm, version=args.version)
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            sys.exit(1)

        # Display results
        table = Table(title="Sanitization Results", show_header=True, header_style="bold cyan")
        table.add_column("Section", style="cyan")
        table.add_column("Items Extracted", justify="right")
        table.add_column("Status")

        for r in result['results']:
            items = r['items_extracted'] if r['had_commentary'] else 0
            status = "✓ Extracted" if r['had_commentary'] else "Clean"
            style = "yellow" if r['had_commentary'] else "green"
            table.add_row(r['file'], str(items), f"[{style}]{status}[/{style}]")

        console.print(table)
        console.print()

        # Summary
        console.print(f"[bold green]✓ Sanitization complete[/bold green]")
        console.print(f"  Sections processed: {result['sections_processed']}")
        console.print(f"  Sections with commentary: {result['sections_with_commentary']}")

        if result['sections_with_commentary'] > 0:
            console.print(f"\n[bold]Internal notes saved to:[/bold]")
            console.print(f"  Per-section: {result['internal_notes_dir']}/")
            if result['consolidated_notes']:
                console.print(f"  Consolidated: {result['consolidated_notes']}")

        # Reassemble final draft
        if not args.no_reassemble and result['sections_with_commentary'] > 0:
            console.print(f"\n[bold]Reassembling final draft...[/bold]")
            try:
                from cli.assemble_draft import assemble_final_draft
                assemble_final_draft(Path(result['output_dir']), console=None, verbose=False)
                console.print(f"  [green]✓[/green] {result['output_dir']}/4-final-draft.md")
            except Exception as e:
                console.print(f"  [yellow]⚠️[/yellow] Could not reassemble: {e}")

        console.print()
        console.print("[dim]Internal notes contain process commentary useful for internal review.[/dim]")
        console.print("[dim]Main sections are now clean and shareable externally.[/dim]")


if __name__ == "__main__":
    main()

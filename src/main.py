"""
Main entry point for the Investment Memo Orchestrator.

Run this script to generate an investment memo for a company.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
import json

from .workflow import generate_memo
from .versioning import VersionManager, format_version_history


def main():
    """Main execution function."""
    console = Console()

    # Load environment variables
    load_dotenv()

    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set in environment")
        console.print("Please set it in .env file or environment variables")
        sys.exit(1)

    # Get company name from command line or prompt
    if len(sys.argv) > 1:
        company_name = " ".join(sys.argv[1:])
    else:
        company_name = console.input("\n[bold cyan]Enter company name:[/bold cyan] ")

    if not company_name.strip():
        console.print("[bold red]Error:[/bold red] Company name cannot be empty")
        sys.exit(1)

    console.print(f"\n[bold green]Starting memo generation for:[/bold green] {company_name}\n")

    # Run workflow with progress indicators
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating investment memo...", total=None)

            # Generate memo
            final_state = generate_memo(company_name)

            progress.update(task, description="[bold green]✓ Memo generation complete!")

        # Display results
        console.print("\n" + "="*80 + "\n")
        console.print(Panel("[bold cyan]WORKFLOW SUMMARY[/bold cyan]", expand=False))

        # Show messages
        messages = final_state.get("messages", [])
        for msg in messages:
            console.print(f"  • {msg}")

        # Show validation score
        score = final_state.get("overall_score", 0.0)
        score_color = "green" if score >= 8 else "yellow" if score >= 6 else "red"
        console.print(f"\n[bold]Validation Score:[/bold] [{score_color}]{score}/10[/{score_color}]")

        # Show validation feedback if available
        validation = final_state.get("validation_results", {}).get("full_memo", {})
        if validation:
            issues = validation.get("issues", [])
            suggestions = validation.get("suggestions", [])

            if issues:
                console.print("\n[bold yellow]Issues Identified:[/bold yellow]")
                for issue in issues:
                    console.print(f"  • {issue}")

            if suggestions:
                console.print("\n[bold cyan]Suggestions:[/bold cyan]")
                for suggestion in suggestions:
                    console.print(f"  • {suggestion}")

        # Get the memo content (either finalized or draft)
        final_memo = final_state.get("final_memo")
        draft_sections = final_state.get("draft_sections", {})
        memo_content = final_memo or draft_sections.get("full_memo", {}).get("content")

        # Save to file regardless of validation status
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        # Sanitize filename
        safe_name = "".join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '-')

        # Initialize version manager
        version_mgr = VersionManager(output_dir)

        # Get next version number
        version = version_mgr.get_next_version(safe_name)

        if memo_content:
            # Determine file suffix based on status
            is_finalized = final_memo is not None
            file_suffix = "memo" if is_finalized else "draft"
            output_file = output_dir / f"{safe_name}-{version}-{file_suffix}.md"

            with open(output_file, "w") as f:
                f.write(memo_content)

            # Record version
            version_mgr.record_version(
                safe_name,
                version,
                score,
                str(output_file),
                is_finalized=is_finalized
            )

            # Display the memo
            console.print("\n" + "="*80 + "\n")
            title = f"GENERATED MEMO {version}" if is_finalized else f"DRAFT MEMO {version} (Needs Review)"
            color = "green" if is_finalized else "yellow"
            console.print(Panel(f"[bold {color}]{title}[/bold {color}]", expand=False))
            console.print("\n")
            md = Markdown(memo_content)
            console.print(md)

            status_msg = "Memo saved to" if is_finalized else "Draft saved to"
            console.print(f"\n[bold green]✓ {status_msg}:[/bold green] {output_file}")

            # Save full state as JSON for debugging
            state_file = output_dir / f"{safe_name}-{version}-state.json"
            with open(state_file, "w") as f:
                # Convert state to serializable format
                serializable_state = {
                    k: v for k, v in final_state.items()
                    if k not in ["messages"]  # Skip messages, already shown
                }
                json.dump(serializable_state, f, indent=2, default=str)

            console.print(f"[dim]Full state saved to: {state_file}[/dim]")

            # Show version history
            history = version_mgr.get_version_history(safe_name)
            if len(history) > 1:
                console.print(f"\n[bold cyan]Version History:[/bold cyan]")
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Version", style="cyan")
                table.add_column("Score", justify="right")
                table.add_column("Status")
                table.add_column("Date")

                for entry in history[-5:]:  # Show last 5 versions
                    status_icon = "✓" if entry["is_finalized"] else "⚠"
                    score_color = "green" if entry["validation_score"] >= 8 else "yellow" if entry["validation_score"] >= 6 else "red"
                    table.add_row(
                        entry["version"],
                        f"[{score_color}]{entry['validation_score']}/10[/{score_color}]",
                        status_icon,
                        entry["timestamp"][:10]
                    )
                console.print(table)

            if not is_finalized:
                console.print("\n[bold yellow]⚠ This is a draft requiring human review before finalization[/bold yellow]")
                console.print("[dim]Run again to create the next version (auto-increments patch)[/dim]")

        else:
            console.print("\n[bold red]✗ No memo content generated[/bold red]")

    except Exception as e:
        console.print(f"\n[bold red]Error during memo generation:[/bold red]")
        console.print(f"{str(e)}")
        import traceback
        console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()

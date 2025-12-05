"""
Main entry point for the Investment Memo Orchestrator.

Run this script to generate an investment memo for a company.
"""

import os
import sys
import argparse
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
from .utils import get_latest_output_dir
from .artifacts import sanitize_filename


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

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate investment memos using multi-agent AI orchestration"
    )
    parser.add_argument(
        "company_name",
        nargs="?",
        help="Name of the company to analyze"
    )
    parser.add_argument(
        "--type",
        dest="investment_type",
        choices=["direct", "fund"],
        default="direct",
        help="Type of investment: 'direct' for startup investments, 'fund' for LP commitments (default: direct)"
    )
    parser.add_argument(
        "--mode",
        dest="memo_mode",
        choices=["consider", "justify"],
        default="consider",
        help="Memo mode: 'consider' for prospective analysis, 'justify' for retrospective justification (default: consider)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint if available (skips completed agents)"
    )
    parser.add_argument(
        "--version",
        type=str,
        dest="resume_version",
        help="Specific version to resume (e.g., v0.0.3). Only used with --resume."
    )
    parser.add_argument(
        "--firm",
        type=str,
        help="Firm name for firm-scoped IO (e.g., 'hypernova'). Uses io/{firm}/deals/{deal}/ structure."
    )
    parser.add_argument(
        "--deal",
        type=str,
        help="Deal name (alternative to positional company_name argument)"
    )

    args = parser.parse_args()

    # Get company/deal name from args or prompt
    # Priority: --deal flag > positional argument > prompt
    if args.deal:
        company_name = args.deal
    elif args.company_name:
        company_name = args.company_name
    else:
        company_name = console.input("\n[bold cyan]Enter company/deal name:[/bold cyan] ")

    if not company_name.strip():
        console.print("[bold red]Error:[/bold red] Company/deal name cannot be empty")
        sys.exit(1)

    # Get firm from args or environment
    firm = args.firm
    if not firm:
        firm = os.getenv("MEMO_DEFAULT_FIRM")

    # RESUME MODE: If --resume flag is set, use resume workflow
    if args.resume:
        from pathlib import Path as PathLib

        # Find output directory (firm-aware)
        try:
            if args.resume_version:
                output_dir = PathLib("output") / f"{sanitize_filename(company_name)}-{args.resume_version}"
            else:
                output_dir = get_latest_output_dir(company_name, firm=firm)

            if not output_dir or not output_dir.exists():
                raise FileNotFoundError()
        except FileNotFoundError:
            console.print(f"[bold red]Error:[/bold red] No artifacts found for '{company_name}'")
            console.print(f"\nSearched in: output/{sanitize_filename(company_name)}-*")
            console.print("\nRun the normal workflow first:")
            console.print(f"  python -m src.main \"{company_name}\"")
            sys.exit(1)

        # Delegate to resume script
        console.print(f"[bold cyan]Resume mode enabled[/bold cyan]")
        console.print(f"Found artifacts: {output_dir}\n")

        # Import and run resume functions
        import subprocess
        result = subprocess.run(
            [sys.executable, "resume-from-last-interruption.py", company_name] +
            (["--version", args.resume_version] if args.resume_version else []),
            cwd=Path(__file__).parent.parent
        )
        sys.exit(result.returncode)

    # Load company/deal data using new path resolution
    # Priority: io/{firm}/deals/{deal}/ > data/{deal}.json
    from .paths import resolve_deal_context, load_deal_config

    deal_ctx = resolve_deal_context(company_name, firm=firm)

    # Display path resolution result
    if not deal_ctx.is_legacy:
        console.print(f"[bold green]Using firm-scoped IO:[/bold green] {deal_ctx.firm}")
        console.print(f"[dim]Deal directory: {deal_ctx.deal_dir}[/dim]")
        # Update firm variable if it was auto-detected
        if not firm:
            firm = deal_ctx.firm
    else:
        if firm:
            console.print(f"[bold yellow]Warning:[/bold yellow] Firm '{firm}' specified but deal not found in io/{firm}/deals/")
            console.print(f"[dim]Falling back to legacy: data/{company_name}.json[/dim]")
        else:
            console.print(f"[dim]Using legacy paths: data/{company_name}.json[/dim]")

    # Initialize company data variables
    deck_path = None
    company_description = None
    company_url = None
    company_stage = None
    research_notes = None
    disambiguation_excludes = []
    company_trademark_light = None
    company_trademark_dark = None
    outline_name = None
    scorecard_name = None

    # Default to CLI arguments
    investment_type = args.investment_type
    memo_mode = args.memo_mode

    if deal_ctx.exists():
        try:
            company_data = load_deal_config(deal_ctx)

            # Load deck path (resolve relative to deal directory if firm-scoped)
            deck_path = company_data.get("deck")
            if deck_path and not deal_ctx.is_legacy:
                # Deck path is relative to deal directory in firm-scoped mode
                resolved_deck = deal_ctx.deal_dir / deck_path
                if resolved_deck.exists():
                    deck_path = str(resolved_deck)
                else:
                    # Maybe it's already an absolute path or relative to project root
                    if not Path(deck_path).exists():
                        console.print(f"[dim]Resolving deck relative to deal dir: {resolved_deck}[/dim]")

            # Load additional company context
            company_description = company_data.get("description")
            company_url = company_data.get("url")
            company_stage = company_data.get("stage")
            research_notes = company_data.get("notes")

            # Load disambiguation exclusion list (URLs of wrong entities)
            disambiguation_raw = company_data.get("disambiguation", [])
            disambiguation_excludes = []
            if disambiguation_raw:
                for url in disambiguation_raw:
                    # Extract domain from URL
                    if url:
                        domain = url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/").split("/")[0]
                        if domain:
                            disambiguation_excludes.append(domain)
                if disambiguation_excludes:
                    console.print(f"[bold yellow]Disambiguation excludes:[/bold yellow] {', '.join(disambiguation_excludes)}")

            # Load company trademark paths (light and dark mode)
            company_trademark_light = company_data.get("trademark_light")
            company_trademark_dark = company_data.get("trademark_dark")

            # Load custom outline name if present
            outline_name = company_data.get("outline")
            if outline_name:
                console.print(f"[bold green]Custom outline:[/bold green] {outline_name}")

            # Load scorecard name if present
            scorecard_name = company_data.get("scorecard")
            if scorecard_name:
                console.print(f"[bold green]Scorecard:[/bold green] {scorecard_name}")

            # Read type and mode from JSON if present
            json_type = company_data.get("type", "").lower()
            json_mode = company_data.get("mode", "").lower()

            # Map JSON values to internal values
            if json_type in ["direct", "direct investment"]:
                investment_type = "direct"
                console.print(f"[bold cyan]Investment type from config:[/bold cyan] Direct Investment")
            elif json_type in ["fund", "lp", "fund commitment", "lp commitment"]:
                investment_type = "fund"
                console.print(f"[bold cyan]Investment type from config:[/bold cyan] Fund Commitment")

            if json_mode in ["consider", "prospective"]:
                memo_mode = "consider"
                console.print(f"[bold cyan]Memo mode from config:[/bold cyan] Prospective Analysis")
            elif json_mode in ["justify", "retrospective"]:
                memo_mode = "justify"
                console.print(f"[bold cyan]Memo mode from config:[/bold cyan] Retrospective Justification")

            # Validate deck path
            if deck_path:
                deck_file = Path(deck_path)
                if deck_file.exists():
                    console.print(f"[bold green]Found pitch deck:[/bold green] {deck_file.name}")
                else:
                    console.print(f"[bold yellow]Warning:[/bold yellow] Deck specified but not found: {deck_path}")
                    deck_path = None

            # Display loaded context
            if company_description:
                console.print(f"[bold green]Company context:[/bold green] {company_description[:80]}...")
            if company_url:
                console.print(f"[bold green]Company URL:[/bold green] {company_url}")
            if company_stage:
                console.print(f"[bold green]Stage:[/bold green] {company_stage}")
            if research_notes:
                console.print(f"[bold green]Research focus:[/bold green] {research_notes[:80]}...")

        except Exception as e:
            console.print(f"[bold yellow]Warning:[/bold yellow] Could not load deal config: {e}")

    # Display configuration
    type_label = "Direct Investment" if investment_type == "direct" else "Fund Commitment"
    mode_label = "Prospective Analysis" if memo_mode == "consider" else "Retrospective Justification"

    console.print(f"\n[bold green]Starting memo generation for:[/bold green] {company_name}")
    console.print(f"[bold cyan]Type:[/bold cyan] {type_label}")
    console.print(f"[bold cyan]Mode:[/bold cyan] {mode_label}")
    if deck_path:
        console.print(f"[bold cyan]Deck:[/bold cyan] Analyzing pitch deck first")
    console.print()

    # Run workflow with progress indicators
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating investment memo...", total=None)

            # Generate memo (pass all company context including firm)
            final_state = generate_memo(
                company_name,
                investment_type,
                memo_mode,
                firm=firm,
                deck_path=deck_path,
                company_description=company_description,
                company_url=company_url,
                company_stage=company_stage,
                research_notes=research_notes,
                disambiguation_excludes=disambiguation_excludes,
                company_trademark_light=company_trademark_light,
                company_trademark_dark=company_trademark_dark,
                outline_name=outline_name,
                scorecard_name=scorecard_name
            )

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

        # Show scorecard results if available
        scorecard_results = final_state.get("scorecard_results")
        if scorecard_results:
            sc_score = scorecard_results.get("overall_score", 0)
            sc_strengths = len(scorecard_results.get("strengths", []))
            sc_concerns = len(scorecard_results.get("concerns", []))
            sc_color = "green" if sc_score >= 4 else "yellow" if sc_score >= 3 else "red"
            console.print(f"[bold]Scorecard Score:[/bold] [{sc_color}]{sc_score:.1f}/5[/{sc_color}] ({sc_strengths} strengths, {sc_concerns} concerns)")

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

        # Sanitize filename
        safe_name = sanitize_filename(company_name)

        # Initialize version manager (firm-scoped or legacy)
        if firm and not deal_ctx.is_legacy:
            version_mgr = VersionManager(firm=firm)
            output_base = deal_ctx.outputs_dir
        else:
            output_base = Path("output")
            version_mgr = VersionManager(output_dir=output_base)

        output_base.mkdir(parents=True, exist_ok=True)

        # Get next version number
        version = version_mgr.get_next_version(safe_name)

        if memo_content:
            # Determine file suffix based on status
            is_finalized = final_memo is not None
            file_suffix = "memo" if is_finalized else "draft"

            # Get version output directory
            version_output_dir = deal_ctx.get_version_output_dir(str(version)) if not deal_ctx.is_legacy else output_base / f"{safe_name}-{version}"
            version_output_dir.mkdir(parents=True, exist_ok=True)

            output_file = version_output_dir / f"{safe_name}-{version}-{file_suffix}.md"

            with open(output_file, "w") as f:
                f.write(memo_content)

            # Record version with relative path
            relative_path = version_mgr.get_relative_file_path(safe_name, version, f"{safe_name}-{version}-{file_suffix}.md")
            version_mgr.record_version(
                safe_name,
                version,
                score,
                relative_path,
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
            # Uses canonical location: state.json inside version directory
            state_file = version_output_dir / "state.json"
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

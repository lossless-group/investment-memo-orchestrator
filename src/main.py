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
        dest="set_version",
        help="Force a specific version (e.g., v0.1.0). With --resume, resumes that version. Without --resume, creates a new run at that version."
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start from a clean slate: ignore prior artifacts and research, generate everything from scratch."
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
            if args.set_version:
                safe_name = sanitize_filename(company_name)
                if firm:
                    output_dir = PathLib(f"io/{firm}/deals/{company_name}/outputs/{safe_name}-{args.set_version}")
                else:
                    output_dir = PathLib("output") / f"{safe_name}-{args.set_version}"
            else:
                output_dir = get_latest_output_dir(company_name, firm=firm)

            if not output_dir or not output_dir.exists():
                raise FileNotFoundError()
        except FileNotFoundError:
            if firm:
                search_path = f"io/{firm}/deals/{company_name}/outputs/"
            else:
                search_path = f"output/{sanitize_filename(company_name)}-*"
            console.print(f"[bold red]Error:[/bold red] No artifacts found for '{company_name}'")
            console.print(f"\nSearched in: {search_path}")
            console.print("\nRun the normal workflow first:")
            console.print(f"  python -m src.main \"{company_name}\"" + (f" --firm {firm}" if firm else ""))
            sys.exit(1)

        # Delegate to resume script
        console.print(f"[bold cyan]Resume mode enabled[/bold cyan]")
        console.print(f"Found artifacts: {output_dir}\n")

        # Import and run resume functions
        import subprocess
        resume_cmd = [sys.executable, "cli/resume_from_interruption.py"]
        if firm:
            resume_cmd += ["--firm", firm, "--deal", company_name]
        else:
            resume_cmd += [company_name]
        if args.set_version:
            resume_cmd += ["--version", args.set_version]
        result = subprocess.run(resume_cmd, cwd=Path(__file__).parent.parent)
        sys.exit(result.returncode)

    # Load company/deal data using new path resolution
    # Priority: io/{firm}/deals/{deal}/ > data/{deal}.json
    from .paths import resolve_deal_context, load_deal_config

    deal_ctx = resolve_deal_context(company_name, firm=firm)

    # Display path resolution result
    if not deal_ctx.is_legacy:
        console.print(f"[bold green]Using firm-scoped IO:[/bold green] {deal_ctx.firm}")
        console.print(f"[dim]Deal directory: {deal_ctx.deal_dir}[/dim]")
        # ALWAYS use the firm from deal context (auto-detection may have found it elsewhere)
        if deal_ctx.firm and deal_ctx.firm != firm:
            if firm:
                console.print(f"[dim]Note: Overriding default firm '{firm}' with detected firm '{deal_ctx.firm}'[/dim]")
            firm = deal_ctx.firm
    else:
        if firm:
            console.print(f"[bold yellow]Warning:[/bold yellow] Firm '{firm}' specified but deal not found in io/{firm}/deals/")
            console.print(f"[dim]Falling back to legacy: data/{company_name}.json[/dim]")
        else:
            console.print(f"[dim]Using legacy paths: data/{company_name}.json[/dim]")

    # Initialize company data variables
    dataroom_path = None
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
    search_variants = None
    known_competitors = None

    # Default to CLI arguments
    investment_type = args.investment_type
    memo_mode = args.memo_mode

    if deal_ctx.exists():
        try:
            company_data = load_deal_config(deal_ctx)

            # Load dataroom path (resolve relative to deal directory if firm-scoped)
            dataroom_path = company_data.get("dataroom")
            if dataroom_path and not deal_ctx.is_legacy:
                resolved_dataroom = deal_ctx.deal_dir / dataroom_path
                if resolved_dataroom.exists():
                    dataroom_path = str(resolved_dataroom)
                elif deal_ctx.inputs_dir:
                    resolved_dataroom = deal_ctx.inputs_dir / dataroom_path
                    if resolved_dataroom.exists():
                        dataroom_path = str(resolved_dataroom)
            if dataroom_path and not Path(dataroom_path).exists():
                console.print(f"[bold yellow]Warning:[/bold yellow] Dataroom specified but not found: {dataroom_path}")
                dataroom_path = None

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
            # Resolve relative to deal directory in firm-scoped mode
            company_trademark_light = company_data.get("trademark_light")
            company_trademark_dark = company_data.get("trademark_dark")

            if not deal_ctx.is_legacy:
                # Resolve trademark paths relative to deal directory
                if company_trademark_light and not Path(company_trademark_light).exists():
                    resolved_light = deal_ctx.deal_dir / company_trademark_light
                    if resolved_light.exists():
                        company_trademark_light = str(resolved_light)
                if company_trademark_dark and not Path(company_trademark_dark).exists():
                    resolved_dark = deal_ctx.deal_dir / company_trademark_dark
                    if resolved_dark.exists():
                        company_trademark_dark = str(resolved_dark)

            # Load custom outline name if present
            outline_name = company_data.get("outline")
            if outline_name:
                console.print(f"[bold green]Custom outline:[/bold green] {outline_name}")

            # Load scorecard name if present
            scorecard_name = company_data.get("scorecard")
            if scorecard_name:
                console.print(f"[bold green]Scorecard:[/bold green] {scorecard_name}")

            # Load competitive research hints
            search_variants = company_data.get("search_variants")
            if search_variants:
                console.print(f"[bold green]Search variants:[/bold green] {len(search_variants)} custom queries")
            known_competitors = company_data.get("known_competitors")
            if known_competitors:
                console.print(f"[bold green]Known competitors:[/bold green] {', '.join(known_competitors)}")

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

            # Display dataroom info
            if dataroom_path:
                dataroom_dir = Path(dataroom_path)
                file_count = sum(1 for _ in dataroom_dir.rglob("*") if _.is_file())
                console.print(f"[bold green]Found dataroom:[/bold green] {dataroom_dir.name} ({file_count} files)")

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
    if args.set_version:
        console.print(f"[bold cyan]Version:[/bold cyan] {args.set_version} (forced)")
    if args.fresh:
        console.print(f"[bold cyan]Fresh:[/bold cyan] Starting from clean slate (ignoring prior artifacts)")
    if dataroom_path:
        console.print(f"[bold cyan]Dataroom:[/bold cyan] Analyzing dataroom first")
    if deck_path:
        console.print(f"[bold cyan]Deck:[/bold cyan] Analyzing pitch deck")
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
                force_version=args.set_version,
                fresh=args.fresh,
                dataroom_path=dataroom_path,
                deck_path=deck_path,
                company_description=company_description,
                company_url=company_url,
                company_stage=company_stage,
                research_notes=research_notes,
                disambiguation_excludes=disambiguation_excludes,
                company_trademark_light=company_trademark_light,
                company_trademark_dark=company_trademark_dark,
                outline_name=outline_name,
                scorecard_name=scorecard_name,
                search_variants=search_variants,
                known_competitors=known_competitors
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

        # Fallback: read from the final draft file on disk if state doesn't have content.
        # This handles the human_review path where agents wrote section files but
        # didn't populate final_memo or draft_sections in state.
        if not memo_content:
            version_output_dir_check = Path(final_state.get("output_dir", ""))
            if version_output_dir_check.exists():
                from .final_draft import read_final_draft
                try:
                    memo_content = read_final_draft(version_output_dir_check)
                    if memo_content:
                        console.print(f"[dim]Loaded memo content from final draft file on disk[/dim]")
                except Exception:
                    pass

        # Sanitize filename
        safe_name = sanitize_filename(company_name)

        # Use the output directory created by the workflow (stored in state)
        version_output_dir = Path(final_state.get("output_dir", ""))

        # Initialize version manager for recording (firm-scoped or legacy)
        if firm and not deal_ctx.is_legacy:
            version_mgr = VersionManager(firm=firm)
        else:
            version_mgr = VersionManager(output_dir=Path("output"))

        # Extract version from the output directory name (e.g., "Company-v0.0.3" -> "v0.0.3")
        from .versioning import MemoVersion
        import re
        version_match = re.search(r'(v\d+\.\d+\.\d+)', version_output_dir.name)
        if version_match:
            version = MemoVersion.from_string(version_match.group(1))
        else:
            version = version_mgr.get_current_version(safe_name)

        if memo_content:
            # Determine status
            is_finalized = final_memo is not None

            version_output_dir.mkdir(parents=True, exist_ok=True)

            # Final draft uses canonical path from final_draft module
            # The pipeline agents already create this file via citation_enrichment/assemble_draft
            from .final_draft import get_final_draft_path
            final_draft_file = get_final_draft_path(version_output_dir)

            # If the pipeline created the file, it's the canonical version
            # Otherwise, write the memo content as the final draft
            if not final_draft_file.exists() and memo_content:
                with open(final_draft_file, "w") as f:
                    f.write(memo_content)

            # Record version with the new canonical filename
            from .final_draft import get_final_draft_filename
            relative_path = version_mgr.get_relative_file_path(safe_name, version, get_final_draft_filename(version_output_dir))
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
            console.print(f"\n[bold green]✓ {status_msg}:[/bold green] {final_draft_file}")

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

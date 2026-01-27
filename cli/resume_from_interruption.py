"""
Resume workflow from last interruption.

This script detects the last successful checkpoint and resumes memo generation
from that point, avoiding redundant API calls and wasted time.

Usage:
    # Firm-scoped (recommended):
    python cli/resume_from_interruption.py --firm emerge --deal CoachCube
    python cli/resume_from_interruption.py --firm hypernova --deal Blinka --version v0.0.3

    # Legacy (direct path):
    python cli/resume_from_interruption.py "CompanyName"
    python cli/resume_from_interruption.py "CompanyName" --version v0.0.3
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.state import MemoState, create_initial_state
from src.utils import get_latest_output_dir
from src.artifacts import sanitize_filename
from src.paths import resolve_deal_context, get_latest_output_dir_for_deal, load_deal_config, DealContext


def detect_resume_point(output_dir: Path) -> str:
    """
    Detect which agent to resume from based on existing artifacts.

    Args:
        output_dir: Path to artifact directory (e.g., output/Company-v0.0.1/)

    Returns:
        Agent name to resume from:
        - "complete": Workflow already finished
        - "start": No checkpoints found, start from beginning
        - Agent name: Resume from this agent (e.g., "cite", "validate")

    Workflow order (from workflow.py):
        deck_analyst → research → section_research → cite → cleanup_research → draft →
        inject_deck_images → enrich_trademark → enrich_socials → enrich_links →
        enrich_visualizations → toc → revise_summaries → cleanup_sections →
        assemble_citations → validate_citations → fact_check → validate →
        scorecard → integrate_scorecard → finalize
    """
    # Check in reverse order (later checkpoints first)

    # Check if fully complete
    state_json = output_dir / "state.json"
    if state_json.exists() and _is_valid_json(state_json):
        try:
            with open(state_json) as f:
                state = json.load(f)
            if state.get("final_memo"):
                return "complete"  # Already done
        except (json.JSONDecodeError, KeyError):
            pass

    # Check for scorecard (runs after validate)
    scorecard_dir = output_dir / "5-scorecard"
    if scorecard_dir.exists() and list(scorecard_dir.glob("*.md")):
        return "integrate_scorecard"  # Resume at scorecard integration

    # Check validation
    validation_json = output_dir / "3-validation.json"
    if validation_json.exists() and _is_valid_json(validation_json):
        try:
            with open(validation_json) as f:
                validation = json.load(f)
            if validation.get("overall_score") is not None:
                return "scorecard"  # Resume at scorecard (after validate)
            if validation.get("fact_check_results"):
                return "validate"  # Resume at validation
            if validation.get("citation_validation"):
                return "fact_check"  # Resume at fact-checking
        except (json.JSONDecodeError, KeyError):
            pass

    # Check for final draft (assembled)
    from src.final_draft import find_final_draft
    final_draft = find_final_draft(output_dir)
    if final_draft and final_draft.stat().st_size > 100:
        return "validate_citations"  # Final draft exists, resume at validation

    # Check enrichment stages
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        sections = list(sections_dir.glob("*.md"))
        if len(sections) >= 10:  # All sections exist
            # Check link enrichment (look for markdown links in ANY section)
            sample_sections = list(sections_dir.glob("0[2-6]*.md"))  # Any section 02-06
            has_links = False
            for section_file in sample_sections:
                if section_file.exists():
                    content = section_file.read_text()
                    # Check for markdown links (excluding citations)
                    if "](http" in content and "[^" not in content.split("](http")[0][-5:]:
                        has_links = True
                        break

            if has_links:
                # Links exist, check what's next
                # After enrich_links comes: enrich_visualizations → toc → revise_summaries →
                # cleanup_sections → assemble_citations
                return "toc"  # Resume at TOC (skips visualization which is disabled)

            # Check for socials enrichment - look for team/organization section
            team_sections = list(sections_dir.glob("04-*.md"))
            for team_section in team_sections:
                if team_section.exists():
                    content = team_section.read_text()
                    if "linkedin.com/in/" in content:
                        return "enrich_links"  # Resume at link enrichment

            # Check for trademark
            header = output_dir / "header.md"
            if header.exists():
                return "enrich_socials"  # Resume at socials enrichment

            return "inject_deck_images"  # Resume at deck image injection (after draft)

        # Sections incomplete
        return "draft"  # Resume at drafting

    # Check for 1-research/ directory (section-specific Perplexity research)
    research_dir = output_dir / "1-research"
    if research_dir.exists() and list(research_dir.glob("*-research.md")):
        # Section research exists, resume at cite (enrichment on research)
        return "cite"

    # Check for 1-research.json (basic research, no section research yet)
    research_json = output_dir / "1-research.json"
    if research_json.exists() and _is_valid_json(research_json):
        # Basic research exists but no section research
        # Check if section_research should run or skip to draft
        # If no PERPLEXITY_API_KEY, skip section_research and go to draft
        import os
        if os.getenv("PERPLEXITY_API_KEY"):
            return "section_research"  # Resume at section research
        else:
            return "draft"  # Skip to draft (no Perplexity key)

    # Check deck analysis
    deck_analysis_json = output_dir / "0-deck-analysis.json"
    if deck_analysis_json.exists() and _is_valid_json(deck_analysis_json):
        return "research"  # Resume at research

    # No checkpoints - start from beginning
    return "start"


def reconstruct_state_from_artifacts(
    company_name: str,
    output_dir: Path,
    investment_type: Optional[str] = None,
    memo_mode: Optional[str] = None,
    ctx: Optional[DealContext] = None
) -> MemoState:
    """
    Rebuild MemoState from saved artifacts.

    Args:
        company_name: Name of the company
        output_dir: Path to artifact directory
        investment_type: Override investment type (optional)
        memo_mode: Override memo mode (optional)
        ctx: DealContext for firm-scoped path resolution (optional)

    Returns:
        Reconstructed MemoState ready for resumption
    """
    deck_path = None
    company_description = None
    company_url = None
    company_stage = None
    research_notes = None
    company_trademark_light = None
    company_trademark_dark = None
    outline_name = None
    scorecard_name = None

    # Defaults
    if investment_type is None:
        investment_type = "direct"
    if memo_mode is None:
        memo_mode = "consider"

    # Load deal config - use firm-scoped path if context available
    company_data = None
    if ctx and ctx.exists():
        try:
            company_data = load_deal_config(ctx)
            print(f"Loaded deal config from: {ctx.deal_json_path}")
        except Exception as e:
            print(f"Warning: Could not load deal config from {ctx.deal_json_path}: {e}")

    # Fall back to legacy path
    if company_data is None:
        data_file = Path(f"data/{company_name}.json")
        if data_file.exists():
            try:
                with open(data_file) as f:
                    company_data = json.load(f)
                print(f"Loaded deal config from: {data_file}")
            except Exception as e:
                print(f"Warning: Could not load company data: {e}")

    if company_data:
        # Load deck path
        deck_path = company_data.get("deck")

        # For firm-scoped, resolve deck path relative to deal directory
        if ctx and ctx.deal_dir and deck_path:
            # Check if it's relative to deal dir
            full_deck_path = ctx.deal_dir / deck_path
            if full_deck_path.exists():
                deck_path = str(full_deck_path)

        # Load additional company context
        company_description = company_data.get("description")
        company_url = company_data.get("url")
        company_stage = company_data.get("stage")
        research_notes = company_data.get("notes")

        # Load company trademark paths
        company_trademark_light = company_data.get("trademark_light")
        company_trademark_dark = company_data.get("trademark_dark")

        # Load outline and scorecard names
        outline_name = company_data.get("outline")
        scorecard_name = company_data.get("scorecard")

        # Read type and mode from JSON if present
        json_type = company_data.get("type", "").lower()
        json_mode = company_data.get("mode", "").lower()

        # Map JSON values to internal values
        if json_type in ["direct", "direct investment"]:
            investment_type = "direct"
        elif json_type in ["fund", "fund commitment"]:
            investment_type = "fund"

        if json_mode in ["consider", "prospective"]:
            memo_mode = "consider"
        elif json_mode in ["justify", "retrospective"]:
            memo_mode = "justify"

        print(f"Loaded company data: type={investment_type}, mode={memo_mode}")

    # Start with fresh state
    # IMPORTANT: Pass firm, outline_name, and scorecard_name so writer uses correct paths
    firm = ctx.firm if ctx else None
    print(f"[DEBUG] About to call create_initial_state for {company_name} (firm={firm})")
    state = create_initial_state(
        company_name=company_name,
        investment_type=investment_type,
        memo_mode=memo_mode,
        firm=firm,
        deck_path=deck_path,
        company_description=company_description,
        company_url=company_url,
        company_stage=company_stage,
        research_notes=research_notes,
        company_trademark_light=company_trademark_light,
        company_trademark_dark=company_trademark_dark,
        outline_name=outline_name,
        scorecard_name=scorecard_name
    )
    print(f"[DEBUG] create_initial_state completed (state firm={state.get('firm')})")

    # Override output directory to use existing one
    state["output_dir"] = str(output_dir)

    # Load deck analysis if exists
    deck_json = output_dir / "0-deck-analysis.json"
    if deck_json.exists() and _is_valid_json(deck_json):
        try:
            with open(deck_json) as f:
                state["deck_analysis"] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load deck analysis: {e}")

    # Load research if exists
    research_json = output_dir / "1-research.json"
    if research_json.exists() and _is_valid_json(research_json):
        try:
            with open(research_json) as f:
                state["research"] = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load research: {e}")

    # Load draft sections if exist (but leave draft_sections empty - sections live in files)
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        # Sections exist on disk, agents will load them as needed
        # Keep draft_sections empty as per new architecture
        state["draft_sections"] = {}

    # Load validation if exists
    validation_json = output_dir / "3-validation.json"
    if validation_json.exists() and _is_valid_json(validation_json):
        try:
            with open(validation_json) as f:
                validation = json.load(f)
            state["validation_results"] = validation.get("validation_results", {})
            state["citation_validation"] = validation.get("citation_validation", {})
            state["overall_score"] = validation.get("overall_score", 0.0)
        except Exception as e:
            print(f"Warning: Could not load validation: {e}")

    # Load final draft if exists using centralized utility
    from src.final_draft import find_final_draft
    final_draft = find_final_draft(output_dir)
    if final_draft:
        try:
            state["final_memo"] = final_draft.read_text()
        except Exception as e:
            print(f"Warning: Could not load final draft: {e}")

    return state


def execute_from_checkpoint(state: MemoState, resume_from: str) -> MemoState:
    """
    Execute agents in sequence starting from resume_from checkpoint.

    Args:
        state: Reconstructed state
        resume_from: Agent name to resume from

    Returns:
        Final state after completion
    """
    from src.agents.research_enhanced import research_agent_enhanced
    from src.agents.perplexity_section_researcher import perplexity_section_researcher_agent
    from src.agents.writer import writer_agent
    from src.agents.inject_deck_images import inject_deck_images_agent
    from src.agents.trademark_enrichment import trademark_enrichment_agent
    from src.agents.socials_enrichment import socials_enrichment_agent
    from src.agents.link_enrichment import link_enrichment_agent
    from src.agents.visualization_enrichment import visualization_enrichment_agent
    from src.agents.citation_enrichment import citation_enrichment_agent
    from src.agents.toc_generator import toc_generator_agent
    from src.agents.revise_summary_sections import revise_summary_sections
    from src.agents.remove_invalid_sources import remove_invalid_sources_agent
    from src.agents.citation_assembly import citation_assembly_agent
    from src.agents.citation_validator import citation_validator_agent
    from src.agents.fact_checker import fact_checker_agent
    from src.agents.validator import validator_agent
    from src.agents.scorecard_evaluator import scorecard_evaluator_agent
    from src.workflow import finalize_memo, human_review, cleanup_research_citations, integrate_scorecard

    # Define agent sequence (matches workflow.py build_workflow() order)
    # Full sequence from workflow.py:
    # deck_analyst → research → section_research → cite → cleanup_research → draft →
    # inject_deck_images → enrich_trademark → enrich_socials → enrich_links →
    # enrich_visualizations → toc → revise_summaries → cleanup_sections →
    # assemble_citations → validate_citations → fact_check → validate →
    # scorecard → integrate_scorecard → finalize
    agent_sequence = [
        ("research", research_agent_enhanced),
        ("section_research", perplexity_section_researcher_agent),
        ("cite", citation_enrichment_agent),
        ("cleanup_research", cleanup_research_citations),
        ("draft", writer_agent),
        ("inject_deck_images", inject_deck_images_agent),
        ("enrich_trademark", trademark_enrichment_agent),
        ("enrich_socials", socials_enrichment_agent),
        ("enrich_links", link_enrichment_agent),
        ("enrich_visualizations", visualization_enrichment_agent),
        ("toc", toc_generator_agent),
        ("revise_summaries", revise_summary_sections),
        ("cleanup_sections", remove_invalid_sources_agent),
        ("assemble_citations", citation_assembly_agent),
        ("validate_citations", citation_validator_agent),
        ("fact_check", fact_checker_agent),
        ("validate", validator_agent),
        ("scorecard", scorecard_evaluator_agent),
        ("integrate_scorecard", integrate_scorecard),
        ("finalize", finalize_memo),
    ]

    # Find starting index
    start_index = next(
        (i for i, (name, _) in enumerate(agent_sequence) if name == resume_from),
        0
    )

    if start_index == 0 and resume_from != "research":
        print(f"Warning: Unknown resume point '{resume_from}', starting from beginning")

    # Execute agents from resume point
    for agent_name, agent_fn in agent_sequence[start_index:]:
        print(f"\n{'='*60}")
        print(f"Running agent: {agent_name}")
        print('='*60)
        try:
            result = agent_fn(state)
            state.update(result)

            # Check if validation failed (needs human review)
            if agent_name == "validate" and state.get("overall_score", 0) < 8.0:
                print("\nValidation score below threshold, entering human review...")
                result = human_review(state)
                state.update(result)
                break

        except Exception as e:
            print(f"Error in agent {agent_name}: {e}")
            raise

    return state


def _is_valid_json(file_path: Path) -> bool:
    """
    Check if a JSON file is valid and complete.

    Args:
        file_path: Path to JSON file

    Returns:
        True if file is valid JSON, False otherwise
    """
    if not file_path.exists():
        return False

    # Check file size (too small = likely corrupted)
    if file_path.stat().st_size < 10:  # Less than 10 bytes
        return False

    # Try parsing
    try:
        with open(file_path) as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, OSError):
        return False


def main():
    """Resume memo generation from last interruption."""
    parser = argparse.ArgumentParser(
        description="Resume memo generation from last checkpoint"
    )
    parser.add_argument(
        "company_name",
        nargs="?",
        help="Company name (legacy mode, or omit if using --firm/--deal)"
    )
    parser.add_argument(
        "--firm",
        type=str,
        help="Firm name (e.g., 'emerge', 'hypernova')"
    )
    parser.add_argument(
        "--deal",
        type=str,
        help="Deal name (e.g., 'CoachCube', 'Blinka')"
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Specific version to resume (e.g., v0.0.3). Defaults to latest."
    )

    args = parser.parse_args()

    # Determine deal name and context
    ctx = None
    company_name = None

    if args.firm and args.deal:
        # Firm-scoped mode
        company_name = args.deal
        ctx = resolve_deal_context(args.deal, firm=args.firm)
        print(f"Using firm-scoped IO: {args.firm}")
        print(f"Deal: {args.deal}")

        if not ctx.exists():
            print(f"❌ Deal config not found: {ctx.deal_json_path}")
            sys.exit(1)

        # Find output directory
        if args.version:
            output_dir = ctx.get_version_output_dir(args.version)
        else:
            try:
                output_dir = get_latest_output_dir_for_deal(ctx)
            except FileNotFoundError as e:
                print(f"❌ {e}")
                print(f"\nRun the normal workflow first:")
                print(f"  python -m src.main \"{args.deal}\" --firm {args.firm}")
                sys.exit(1)

    elif args.company_name:
        # Legacy mode
        company_name = args.company_name

        # Try to auto-detect firm
        ctx = resolve_deal_context(args.company_name)
        if ctx.firm:
            print(f"Auto-detected firm: {ctx.firm}")

        # Find output directory
        if args.version:
            if ctx and ctx.firm:
                output_dir = ctx.get_version_output_dir(args.version)
            else:
                output_dir = Path("output") / f"{sanitize_filename(args.company_name)}-{args.version}"
        else:
            if ctx and ctx.firm:
                try:
                    output_dir = get_latest_output_dir_for_deal(ctx)
                except FileNotFoundError:
                    output_dir = get_latest_output_dir(args.company_name)
            else:
                output_dir = get_latest_output_dir(args.company_name)
    else:
        parser.error("Please provide either --firm/--deal or company_name")
        sys.exit(1)

    if not output_dir or not output_dir.exists():
        print(f"❌ No artifacts found for '{company_name}'")
        if ctx and ctx.firm:
            print(f"\nSearched in: {ctx.outputs_dir}/{sanitize_filename(company_name)}-*")
            print("\nRun the normal workflow first:")
            print(f"  python -m src.main \"{company_name}\" --firm {ctx.firm}")
        else:
            print(f"\nSearched in: output/{sanitize_filename(company_name)}-*")
            print("\nRun the normal workflow first:")
            print(f"  python -m src.main \"{company_name}\"")
        sys.exit(1)

    print(f"Found artifact directory: {output_dir}")

    # Detect resume point
    print("\nDetecting checkpoint...")
    resume_from = detect_resume_point(output_dir)
    print(f"Checkpoint detected: {resume_from}")

    if resume_from == "complete":
        print(f"\n✅ Memo already complete!")
        from src.final_draft import find_final_draft
        final_draft = find_final_draft(output_dir)
        print(f"\nFinal draft: {final_draft}")
        sys.exit(0)

    if resume_from == "start":
        print(f"\n⚠️  No valid checkpoints found in {output_dir}")
        print("\nStarting from scratch instead. Use:")
        if ctx and ctx.firm:
            print(f"  python -m src.main \"{company_name}\" --firm {ctx.firm}")
        else:
            print(f"  python -m src.main \"{company_name}\"")
        sys.exit(1)

    print(f"\n✓ Resuming from checkpoint: {resume_from}")

    # Show what's been completed
    print(f"\nCompleted artifacts:")
    for artifact in sorted(output_dir.glob("*")):
        if artifact.is_file():
            print(f"  ✓ {artifact.name}")
        elif artifact.is_dir() and artifact.name == "2-sections":
            section_count = len(list(artifact.glob("*.md")))
            print(f"  ✓ {artifact.name}/ ({section_count} sections)")
        elif artifact.is_dir() and artifact.name == "1-research":
            research_count = len(list(artifact.glob("*.md")))
            print(f"  ✓ {artifact.name}/ ({research_count} research files)")

    # Reconstruct state
    print(f"\nReconstructing state from artifacts...")
    print(f"Loading company data for: {company_name}")
    state = reconstruct_state_from_artifacts(company_name, output_dir, ctx=ctx)
    print(f"State reconstructed successfully")

    # Execute from checkpoint
    print(f"\nResuming workflow...\n")
    try:
        final_state = execute_from_checkpoint(state, resume_from)

        print(f"\n{'='*60}")
        print("✅ Memo generation complete!")
        print('='*60)
        from src.final_draft import find_final_draft
        final_draft = find_final_draft(output_dir)
        print(f"\nFinal draft: {final_draft}")
        if final_state.get("overall_score"):
            print(f"Quality score: {final_state['overall_score']}/10")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted! Run this script again to resume from the new checkpoint.")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error during resumption: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

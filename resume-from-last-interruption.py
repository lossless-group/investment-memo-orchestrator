"""
Resume workflow from last interruption.

This script detects the last successful checkpoint and resumes memo generation
from that point, avoiding redundant API calls and wasted time.

Usage:
    python resume-from-last-interruption.py "CompanyName"
    python resume-from-last-interruption.py "CompanyName" --version v0.0.3
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from src.state import MemoState, create_initial_state
from src.utils import get_latest_output_dir
from src.artifacts import sanitize_filename


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

    # Check validation
    validation_json = output_dir / "3-validation.json"
    if validation_json.exists() and _is_valid_json(validation_json):
        try:
            with open(validation_json) as f:
                validation = json.load(f)
            if validation.get("overall_score") is not None:
                return "finalize"  # Resume at finalization
            if validation.get("fact_check_results"):
                return "validate"  # Resume at validation
            if validation.get("citation_validation"):
                return "fact_check"  # Resume at fact-checking
        except (json.JSONDecodeError, KeyError):
            pass

    # Check citations
    final_draft = output_dir / "4-final-draft.md"
    if final_draft.exists() and final_draft.stat().st_size > 100:
        try:
            content = final_draft.read_text()
            if "[^1]" in content or "## Citations" in content:
                return "validate_citations"  # Resume at citation validation
        except Exception:
            pass

    # Check enrichment stages
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        sections = list(sections_dir.glob("*.md"))
        if len(sections) >= 10:  # All sections exist
            # Check link enrichment (look for markdown links in sections)
            sample_sections = [sections_dir / "03-market-context.md",
                             sections_dir / "02-business-overview.md"]
            has_links = False
            for section_file in sample_sections:
                if section_file.exists():
                    content = section_file.read_text()
                    # Check for markdown links (excluding citations)
                    if "](http" in content and "[^" not in content.split("](http")[0][-5:]:
                        has_links = True
                        break

            if has_links:
                return "cite"  # Resume at citation enrichment

            # Check for socials enrichment
            team_section = sections_dir / "04-team.md"
            if team_section.exists():
                content = team_section.read_text()
                if "linkedin.com/in/" in content:
                    return "enrich_links"  # Resume at link enrichment

            # Check for trademark
            header = output_dir / "header.md"
            if header.exists():
                return "enrich_socials"  # Resume at socials enrichment

            return "enrich_trademark"  # Resume at trademark enrichment

        # Sections incomplete
        return "draft"  # Resume at drafting

    # Check research
    research_json = output_dir / "1-research.json"
    if research_json.exists() and _is_valid_json(research_json):
        return "draft"  # Resume at drafting (section research was removed)

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
    memo_mode: Optional[str] = None
) -> MemoState:
    """
    Rebuild MemoState from saved artifacts.

    Args:
        company_name: Name of the company
        output_dir: Path to artifact directory
        investment_type: Override investment type (optional)
        memo_mode: Override memo mode (optional)

    Returns:
        Reconstructed MemoState ready for resumption
    """
    # Start with fresh state (loads company data JSON)
    print(f"[DEBUG] About to call create_initial_state for {company_name}")
    state = create_initial_state(company_name, investment_type, memo_mode)
    print("[DEBUG] create_initial_state completed")

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

    # Load final draft if exists
    final_draft = output_dir / "4-final-draft.md"
    if final_draft.exists():
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
    from src.agents.writer import writer_agent
    from src.agents.trademark_enrichment import trademark_enrichment_agent
    from src.agents.socials_enrichment import socials_enrichment_agent
    from src.agents.link_enrichment import link_enrichment_agent
    from src.agents.visualization_enrichment import visualization_enrichment_agent
    from src.agents.citation_enrichment import citation_enrichment_agent
    from src.agents.citation_validator import citation_validator_agent
    from src.agents.validator import validator_agent
    from src.workflow import finalize_memo, human_review

    # Define agent sequence (matches workflow order)
    agent_sequence = [
        ("research", research_agent_enhanced),
        ("draft", writer_agent),
        ("enrich_trademark", trademark_enrichment_agent),
        ("enrich_socials", socials_enrichment_agent),
        ("enrich_links", link_enrichment_agent),
        ("enrich_visualizations", visualization_enrichment_agent),
        ("cite", citation_enrichment_agent),
        ("validate_citations", citation_validator_agent),
        ("validate", validator_agent),
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
        help="Company name (must match existing artifacts)"
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Specific version to resume (e.g., v0.0.3). Defaults to latest."
    )

    args = parser.parse_args()

    # Find output directory
    if args.version:
        output_dir = Path("output") / f"{sanitize_filename(args.company_name)}-{args.version}"
    else:
        # Find latest version
        output_dir = get_latest_output_dir(args.company_name)

    if not output_dir or not output_dir.exists():
        print(f"❌ No artifacts found for '{args.company_name}'")
        print(f"\nSearched in: output/{sanitize_filename(args.company_name)}-*")
        print("\nRun the normal workflow first:")
        print(f"  python -m src.main \"{args.company_name}\"")
        sys.exit(1)

    print(f"Found artifact directory: {output_dir}")

    # Detect resume point
    print("\nDetecting checkpoint...")
    resume_from = detect_resume_point(output_dir)
    print(f"Checkpoint detected: {resume_from}")

    if resume_from == "complete":
        print(f"\n✅ Memo already complete!")
        print(f"\nFinal draft: {output_dir / '4-final-draft.md'}")
        sys.exit(0)

    if resume_from == "start":
        print(f"\n⚠️  No valid checkpoints found in {output_dir}")
        print("\nStarting from scratch instead. Use:")
        print(f"  python -m src.main \"{args.company_name}\"")
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

    # Reconstruct state
    print(f"\nReconstructing state from artifacts...")
    print(f"Loading company data for: {args.company_name}")
    state = reconstruct_state_from_artifacts(args.company_name, output_dir)
    print(f"State reconstructed successfully")

    # Execute from checkpoint
    print(f"\nResuming workflow...\n")
    try:
        final_state = execute_from_checkpoint(state, resume_from)

        print(f"\n{'='*60}")
        print("✅ Memo generation complete!")
        print('='*60)
        print(f"\nFinal draft: {output_dir / '4-final-draft.md'}")
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

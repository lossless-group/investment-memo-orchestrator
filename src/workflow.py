"""
LangGraph workflow orchestration for investment memo generation.

This module defines the supervisor pattern that coordinates the Research,
Writer, and Validator agents through a state graph.

IMPORTANT: Citation validation happens at TWO points to prevent hallucination propagation:

1. AFTER section_research, BEFORE writer (cleanup_research node):
   - Validates citations in 1-research/ files
   - Removes hallucinated/404 URLs BEFORE writer sees them
   - Prevents false information from entering draft narrative

2. AFTER revise_summaries, BEFORE assembly (cleanup_sections node):
   - Validates citations in 2-sections/ files
   - Catches any new hallucinations from citation enrichment
   - Ensures clean citations before final assembly

This two-gate approach ensures hallucinations are killed at the source.
"""

from langgraph.graph import StateGraph, END
from typing import Literal as LiteralType, Dict, Any

import os
from pathlib import Path
from .state import MemoState
from .agents.researcher import research_agent
from .agents.research_enhanced import research_agent_enhanced
from .agents.deck_analyst import deck_analyst_agent
from .agents.perplexity_section_researcher import perplexity_section_researcher_agent
from .agents.writer import writer_agent
from .agents.trademark_enrichment import trademark_enrichment_agent
from .agents.socials_enrichment import socials_enrichment_agent
from .agents.link_enrichment import link_enrichment_agent
from .agents.visualization_enrichment import visualization_enrichment_agent
from .agents.citation_enrichment import citation_enrichment_agent
from .agents.toc_generator import toc_generator_agent
from .agents.revise_summary_sections import revise_summary_sections
from .agents.inject_deck_images import inject_deck_images_agent
from .agents.citation_validator import citation_validator_agent
from .agents.remove_invalid_sources import (
    remove_invalid_sources_agent,
    validate_url,
    extract_citation_urls,
    remove_invalid_citations_from_directory,
    reorder_directory_citations,
    INVALID_HTTP_CODES,
    HALLUCINATION_PATTERNS,
)
from .agents.citation_assembly import citation_assembly_agent
from .agents.fact_checker import fact_checker_agent
from .agents.validator import validator_agent
from .agents.scorecard_evaluator import scorecard_evaluator_agent
from .artifacts import sanitize_filename, save_final_draft, save_state_snapshot
from .versioning import VersionManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import re


def cleanup_research_citations(state: MemoState) -> Dict[str, Any]:
    """
    Validate and clean citations in 1-research/ files BEFORE the writer sees them.

    This is the FIRST validation gate - it runs after section_research but before
    the writer agent. This prevents hallucinated citations from ever entering
    the draft narrative.

    Process:
    1. Collect all citation URLs from 1-research/ files
    2. Validate URLs in parallel (HTTP HEAD requests)
    3. Remove invalid citations (404s, hallucination patterns)
    4. Reorder remaining citations to eliminate gaps

    Args:
        state: Current memo state

    Returns:
        Updated state with cleanup results
    """
    from .utils import get_latest_output_dir

    company_name = state["company_name"]
    firm = state.get("firm")

    print(f"\n🔍 VALIDATION GATE 1: Cleaning research citations for {company_name}...")
    print(f"   (This runs BEFORE writer to prevent hallucination propagation)")

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        return {
            "messages": ["Research cleanup skipped: no output directory found"]
        }

    research_dir = output_dir / "1-research"

    if not research_dir.exists():
        print("  ⚠️  No 1-research/ directory found, skipping")
        return {
            "messages": ["Research cleanup skipped: no research directory"]
        }

    # Collect all citation URLs from research files
    citation_urls: Dict[str, str] = {}
    for f in research_dir.glob("*.md"):
        content = f.read_text()
        citations = extract_citation_urls(content)
        citation_urls.update(citations)

    if not citation_urls:
        print("  No citations found in research files")
        return {
            "messages": ["Research cleanup: no citations found"]
        }

    print(f"  Found {len(citation_urls)} citations to validate")

    # Validate URLs in parallel
    invalid_citations = set()
    valid_citations = set()
    potentially_valid = set()

    print(f"  Validating URLs...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_citation = {
            executor.submit(validate_url, url): (num, url)
            for num, url in citation_urls.items()
        }

        for future in as_completed(future_to_citation):
            num, url = future_to_citation[future]
            try:
                _, http_code, status = future.result()

                if http_code == -1:  # Hallucination pattern
                    invalid_citations.add(num)
                    print(f"    ❌ [^{num}]: Hallucination - {url[:50]}...")
                elif http_code in INVALID_HTTP_CODES:
                    invalid_citations.add(num)
                    print(f"    ❌ [^{num}]: HTTP {http_code} - {url[:50]}...")
                elif http_code in {401, 403, 429, 500, 502, 503}:
                    potentially_valid.add(num)
                elif http_code == 0:
                    potentially_valid.add(num)
                else:
                    valid_citations.add(num)

            except Exception as e:
                print(f"    ⚠️  [^{num}]: Error - {e}")
                potentially_valid.add(num)

    print(f"  Results: {len(valid_citations)} valid, {len(potentially_valid)} uncertain, {len(invalid_citations)} invalid")

    if not invalid_citations:
        print("  ✓ All research citations are valid")
        return {
            "messages": [f"Research validation: {len(valid_citations)} valid, 0 removed"]
        }

    # PASS 1: Remove invalid citations
    print(f"\n  📝 Removing {len(invalid_citations)} invalid citations from research...")
    research_removed = remove_invalid_citations_from_directory(research_dir, invalid_citations)
    if research_removed:
        print(f"    ✓ Cleaned {research_removed} research files")

    # PASS 2: Reorder citations to eliminate gaps
    print(f"  🔢 Reordering citations...")
    research_reordered = reorder_directory_citations(research_dir)
    if research_reordered:
        print(f"    ✓ Reordered {research_reordered} files")

    remaining = len(citation_urls) - len(invalid_citations)
    summary = f"Research cleanup: removed {len(invalid_citations)} invalid, {remaining} remaining"
    print(f"\n  ✅ {summary}")
    print(f"  ✅ Writer will now receive CLEAN research data")

    return {
        "messages": [summary],
        "research_cleanup": {
            "total": len(citation_urls),
            "valid": len(valid_citations),
            "uncertain": len(potentially_valid),
            "removed": len(invalid_citations),
            "remaining": remaining
        }
    }


def should_continue(state: MemoState) -> LiteralType["finalize", "human_review"]:
    """
    Determine next step after validation.

    Args:
        state: Current memo state with validation results

    Returns:
        "finalize" if validation passed (score >= 8)
        "human_review" if validation failed or needs revision
    """
    overall_score = state.get("overall_score", 0.0)

    # If score is high enough (8+), finalize
    if overall_score >= 8.0:
        return "finalize"

    # Otherwise, send to human review
    # In a future version, we'd add a revision loop here
    return "human_review"


def finalize_memo(state: MemoState) -> dict:
    """
    Finalize the memo for output.

    NOTE: The final draft is already assembled by citation enrichment agent.
    This function verifies the file exists and saves the state snapshot.

    Args:
        state: Current memo state

    Returns:
        Updated state with final_memo set
    """
    from .utils import get_latest_output_dir

    company_name = state["company_name"]
    firm = state.get("firm")

    # Get artifact directory (most recent) - firm-aware
    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        raise FileNotFoundError(f"No output directory found for {company_name}")

    # Load final draft content (handles new and legacy naming)
    from .final_draft import find_final_draft, read_final_draft
    final_draft_path = find_final_draft(output_dir)
    if not final_draft_path:
        raise FileNotFoundError(f"Final draft not found in {output_dir}. Citation enrichment may have failed.")

    memo_content = read_final_draft(output_dir)

    # Save state snapshot
    try:
        save_state_snapshot(output_dir, state)
        print(f"✓ State snapshot saved")

        print(f"\n🎉 Final draft ready: {final_draft_path}")
        print(f"State snapshot saved to: {output_dir / 'state.json'}")
    except Exception as e:
        print(f"Warning: Could not save final draft artifacts: {e}")

    return {
        "final_memo": memo_content,
        "messages": ["Memo finalized and ready for review"]
    }


def human_review(state: MemoState) -> dict:
    """
    Prepare memo for human review.

    Args:
        state: Current memo state

    Returns:
        Updated state with messages for human reviewer
    """
    from .utils import get_latest_output_dir
    from .paths import resolve_deal_context

    validation = state.get("validation_results", {}).get("full_memo", {})
    score = state.get("overall_score", 0.0)
    issues = validation.get("issues", [])
    suggestions = validation.get("suggestions", [])
    company_name = state["company_name"]
    firm = state.get("firm")

    # Save draft artifacts even when it needs review
    try:
        # Get version manager - firm-aware
        if firm:
            ctx = resolve_deal_context(company_name, firm=firm)
            version_mgr = VersionManager(ctx.outputs_dir.parent if ctx.outputs_dir else Path("output"), firm=firm)
        else:
            version_mgr = VersionManager(Path("output"))

        safe_name = sanitize_filename(company_name)
        version = version_mgr.get_next_version(safe_name)

        # Get artifact directory - firm-aware
        if firm:
            output_dir = ctx.get_version_output_dir(str(version))
        else:
            output_dir = Path("output") / f"{safe_name}-{version}"

        output_dir.mkdir(parents=True, exist_ok=True)

        # Get draft content
        draft = state.get("draft_sections", {}).get("full_memo", {})
        memo_content = draft.get("content", "")

        # Save as draft (not final)
        from .final_draft import write_final_draft, get_final_draft_path
        if memo_content:
            final_draft_path = write_final_draft(output_dir, memo_content)
        else:
            final_draft_path = get_final_draft_path(output_dir)

        # Save state snapshot
        save_state_snapshot(output_dir, state)

        print(f"Draft saved for review to: {final_draft_path}")
        print(f"State snapshot saved to: {output_dir / 'state.json'}")
    except Exception as e:
        print(f"Warning: Could not save draft artifacts: {e}")

    review_message = f"""
MEMO REQUIRES HUMAN REVIEW
Score: {score}/10

Issues identified:
{chr(10).join(f'- {issue}' for issue in issues)}

Suggested improvements:
{chr(10).join(f'- {suggestion}' for suggestion in suggestions)}
"""

    return {
        "messages": [review_message]
    }


def integrate_scorecard(state: MemoState) -> dict:
    """
    Integrate the 12Ps scorecard into section 8 and reassemble final draft.

    The scorecard evaluator generates detailed scores in 5-scorecard/12Ps-scorecard.md,
    but this runs AFTER the writer creates section 8. This function:
    1. Copies the full scorecard to replace section 8
    2. Reassembles the final draft with the integrated scorecard

    Args:
        state: Current memo state

    Returns:
        Updated state with messages
    """
    from .utils import get_latest_output_dir
    from pathlib import Path

    company_name = state["company_name"]
    firm = state.get("firm")

    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        return {"messages": ["Scorecard integration skipped: no output directory"]}

    # Check for scorecard file
    scorecard_dir = output_dir / "5-scorecard"
    scorecard_file = scorecard_dir / "12Ps-scorecard.md"

    if not scorecard_file.exists():
        print("  ⚠️  No 12Ps scorecard found, skipping integration")
        return {"messages": ["Scorecard integration skipped: no scorecard file"]}

    # Find section 8 (scorecard summary section) in 2-sections/
    sections_dir = output_dir / "2-sections"
    section_8_file = None

    for f in sections_dir.glob("08-*.md"):
        section_8_file = f
        break

    if not section_8_file:
        # Try to find any scorecard-related section
        for f in sections_dir.glob("*scorecard*.md"):
            section_8_file = f
            break

    if section_8_file:
        # Replace section 8 with the full scorecard
        scorecard_content = scorecard_file.read_text()
        section_8_file.write_text(scorecard_content)
        print(f"  ✓ Integrated scorecard into {section_8_file.name}")
    else:
        print("  ⚠️  Section 8 not found, creating new scorecard section")
        section_8_file = sections_dir / "08-12ps-scorecard-summary.md"
        scorecard_content = scorecard_file.read_text()
        section_8_file.write_text(scorecard_content)

    # Reassemble final draft using canonical assembly (handles citations + TOC)
    try:
        from cli.assemble_draft import assemble_final_draft
        from rich.console import Console
        console = Console()
        final_draft_path = assemble_final_draft(output_dir, console)
        word_count = final_draft_path.read_text().split()
        print(f"  ✓ Reassembled final draft with citations and TOC: {len(word_count)} words")
        return {"messages": [f"Scorecard integrated into section 8, final draft reassembled ({len(word_count)} words)"]}
    except ImportError:
        # Fallback to basic assembly if cli module not available
        from .final_draft import get_final_draft_path
        final_draft_path = get_final_draft_path(output_dir)

        # Preserve logo/header from existing draft if present
        content = ""
        if final_draft_path.exists():
            existing = final_draft_path.read_text()
            first_line = existing.split('\n')[0]
            if first_line.startswith('!['):
                content = first_line + '\n\n'

        # Assemble all sections in order
        for section_file in sorted(sections_dir.glob("*.md")):
            if section_file.name == "header.md":
                continue
            content += section_file.read_text() + '\n\n'

        final_draft_path.write_text(content)
        print(f"  ✓ Reassembled final draft (basic): {len(content.split())} words")

        return {"messages": [f"Scorecard integrated into section 8, final draft reassembled ({len(content.split())} words)"]}


def router_node(state: MemoState) -> dict:
    """
    Router node that decides whether to analyze deck first.

    Args:
        state: Current memo state

    Returns:
        State with router decision
    """
    return {
        "messages": ["Routing workflow..."]
    }


def should_analyze_deck(state: MemoState) -> str:
    """
    Route to deck analyst if deck exists, otherwise go to research.

    Args:
        state: Current memo state

    Returns:
        Next node to execute ("deck_analyst" or "research")
    """
    deck_path = state.get("deck_path")
    if deck_path and Path(deck_path).exists():
        print("Routing to deck analyst...")
        return "deck_analyst"
    print("Routing to research...")
    return "research"


def build_workflow() -> StateGraph:
    """
    Build the LangGraph workflow for memo generation.

    Returns:
        Compiled StateGraph ready for execution
    """
    # Create the graph
    workflow = StateGraph(MemoState)

    # Choose research agent based on configuration
    use_enhanced_research = os.getenv("USE_WEB_SEARCH", "true").lower() == "true"
    research_fn = research_agent_enhanced if use_enhanced_research else research_agent

    # Add agent nodes
    workflow.add_node("deck_analyst", deck_analyst_agent)  # Deck analyst (always runs, skips if no deck)
    workflow.add_node("research", research_fn)
    workflow.add_node("section_research", perplexity_section_researcher_agent)  # Section-specific research with citations
    workflow.add_node("cleanup_research", cleanup_research_citations)  # GATE 1: Clean research citations BEFORE writer
    workflow.add_node("draft", writer_agent)
    workflow.add_node("inject_deck_images", inject_deck_images_agent)  # Inject screenshots from deck into 2-sections/
    workflow.add_node("enrich_trademark", trademark_enrichment_agent)  # Company trademark insertion
    workflow.add_node("enrich_socials", socials_enrichment_agent)
    workflow.add_node("enrich_links", link_enrichment_agent)
    workflow.add_node("enrich_visualizations", visualization_enrichment_agent)
    workflow.add_node("cite", citation_enrichment_agent)
    workflow.add_node("toc", toc_generator_agent)  # Generate Table of Contents with anchor links
    workflow.add_node("revise_summaries", revise_summary_sections)  # Revise Executive Summary & Closing based on full draft
    workflow.add_node("cleanup_sections", remove_invalid_sources_agent)  # GATE 2: Clean section citations before assembly
    workflow.add_node("assemble_citations", citation_assembly_agent)  # Consolidate and renumber citations
    workflow.add_node("validate_citations", citation_validator_agent)  # Citation accuracy validator
    workflow.add_node("fact_check", fact_checker_agent)  # Fact-checking agent (verify claims vs sources)
    workflow.add_node("validate", validator_agent)
    workflow.add_node("scorecard", scorecard_evaluator_agent)  # 12Ps scorecard evaluation
    workflow.add_node("integrate_scorecard", integrate_scorecard)  # Integrate scorecard into section 8
    workflow.add_node("finalize", finalize_memo)
    workflow.add_node("human_review", human_review)

    # SIMPLIFIED: Always start with deck_analyst (it skips if no deck)
    workflow.set_entry_point("deck_analyst")

    # Define edges (workflow sequence)
    #
    # ANTI-HALLUCINATION ARCHITECTURE:
    # Two validation gates ensure hallucinated citations never propagate:
    #
    # GATE 1 (cleanup_research): After section_research, BEFORE writer
    #   - Validates 1-research/ citations
    #   - Writer receives ONLY clean research data
    #
    # GATE 2 (cleanup_sections): After revise_summaries, BEFORE assembly
    #   - Validates 2-sections/ citations
    #   - Catches any new hallucinations from citation enrichment
    #
    # Full sequence:
    # Deck → Research → Section Research → [GATE 1] → Writer → Inject Deck Images →
    # Enrichment → Citations → TOC → Revise → [GATE 2] → Assembly → Validation →
    # Fact Check → Validate → Scorecard

    workflow.add_edge("deck_analyst", "research")
    workflow.add_edge("research", "section_research")  # Generate section research with citations
    workflow.add_edge("section_research", "cleanup_research")  # GATE 1: Clean research before writer
    workflow.add_edge("cleanup_research", "draft")     # Writer receives CLEAN research
    workflow.add_edge("draft", "inject_deck_images")  # Inject deck screenshots into 2-sections/
    workflow.add_edge("inject_deck_images", "enrich_trademark")  # Then insert company trademark
    workflow.add_edge("enrich_trademark", "enrich_socials")
    workflow.add_edge("enrich_socials", "enrich_links")
    workflow.add_edge("enrich_links", "enrich_visualizations")
    workflow.add_edge("enrich_visualizations", "cite")
    workflow.add_edge("cite", "toc")  # Generate TOC after citations assembled
    workflow.add_edge("toc", "revise_summaries")  # Revise bookend sections based on complete draft
    workflow.add_edge("revise_summaries", "cleanup_sections")  # GATE 2: Clean sections before assembly
    workflow.add_edge("cleanup_sections", "assemble_citations")  # Consolidate and renumber citations
    workflow.add_edge("assemble_citations", "validate_citations")  # Validate assembled citations
    workflow.add_edge("validate_citations", "fact_check")  # Fact-check claims against research sources
    workflow.add_edge("fact_check", "validate")
    workflow.add_edge("validate", "scorecard")  # Run scorecard evaluation after validation
    workflow.add_edge("scorecard", "integrate_scorecard")  # Integrate scorecard into section 8 and reassemble final draft

    # Conditional edge after scorecard integration
    workflow.add_conditional_edges(
        "integrate_scorecard",
        should_continue,
        {
            "finalize": "finalize",
            "human_review": "human_review"
        }
    )

    # Both finalize and human_review end the workflow
    workflow.add_edge("finalize", END)
    workflow.add_edge("human_review", END)

    # Compile and return
    return workflow.compile()


def generate_memo(
    company_name: str,
    investment_type: LiteralType["direct", "fund"] = "direct",
    memo_mode: LiteralType["consider", "justify"] = "consider",
    firm: str = None,
    deck_path: str = None,
    company_description: str = None,
    company_url: str = None,
    company_stage: str = None,
    research_notes: str = None,
    disambiguation_excludes: list = None,
    company_trademark_light: str = None,
    company_trademark_dark: str = None,
    outline_name: str = None,
    scorecard_name: str = None
) -> MemoState:
    """
    Main entry point for generating an investment memo.

    Args:
        company_name: Name of the company to analyze
        investment_type: Type of investment - "direct" for startup, "fund" for LP commitment
        memo_mode: Memo mode - "consider" for prospective, "justify" for retrospective
        firm: Firm name for firm-scoped IO (e.g., "hypernova")
        deck_path: Optional path to pitch deck PDF
        company_description: Brief description of what the company does
        company_url: Company website URL
        company_stage: Investment stage (Seed, Series A, etc.)
        research_notes: Additional research guidance or focus areas
        disambiguation_excludes: List of domains to exclude (wrong entities with similar names)
        company_trademark_light: Path or URL to light mode company logo/trademark
        company_trademark_dark: Path or URL to dark mode company logo/trademark
        outline_name: Custom outline name (e.g., "lpcommit-emerging-manager")
        scorecard_name: Scorecard name for evaluation (e.g., "hypernova-early-stage-12Ps")

    Returns:
        Final state containing research, draft, validation, scorecard evaluation, and final memo
    """
    from .state import create_initial_state

    # Create initial state with all company context
    initial_state = create_initial_state(
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

    # Build and run workflow
    app = build_workflow()
    final_state = app.invoke(initial_state)

    return final_state

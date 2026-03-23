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

# Agent imports — ordered by pipeline sequence:
# Dataroom → Deck → Research → Section Research → Citation Enrichment →
# Cleanup Research → Writer → Inject Deck Images → Enrichment (trademark, socials, links, viz) →
# TOC → Revise Summaries → Cleanup Sections → Assemble Citations →
# Validate Citations → Fact Check → Validate → Scorecard → Integrate Scorecard
from .agents.dataroom import dataroom_agent                                      # 1. Dataroom analysis (skips if no dataroom)
from .agents.deck_analyst import deck_analyst_agent                              # 2. Deck analysis (skips if no deck)
from .agents.researcher import research_agent                                    # 3a. Basic research (fallback)
from .agents.research_enhanced import research_agent_enhanced                    # 3b. Enhanced research with web search
from .agents.perplexity_section_researcher import perplexity_section_researcher_agent  # 4. Section-specific research
from .agents.competitive_landscape_researcher import competitive_landscape_researcher  # 4b. Competitive landscape discovery
from .agents.competitive_landscape_evaluator import competitive_landscape_evaluator    # 4c. Competitive landscape evaluation
from .agents.citation_enrichment import citation_enrichment_agent                # 5. Citation enrichment on research
from .agents.writer import writer_agent                                          # 7. Section-by-section writing
from .agents.inject_deck_images import inject_deck_images_agent                  # 8. Inject deck screenshots
from .agents.trademark_enrichment import trademark_enrichment_agent              # 9. Company trademark insertion
from .agents.socials_enrichment import socials_enrichment_agent                  # 10. LinkedIn profile links
from .agents.link_enrichment import link_enrichment_agent                        # 11. Organization hyperlinks
from .agents.table_generator import table_generator_agent                        # 12. Table generation
from .agents.diagram_generator import diagram_generator_agent                    # 12b. Diagram generation (TAM/SAM/SOM, etc.)
from .agents.visualization_enrichment import visualization_enrichment_agent      # 13. Visualizations (disabled)
from .agents.toc_generator import toc_generator_agent                            # 13. Table of Contents
from .agents.revise_summary_sections import revise_summary_sections              # 14. Revise bookend sections
from .agents.remove_invalid_sources import (                                     # 6/15. Cleanup gates
    remove_invalid_sources_agent,
    validate_url,
    extract_citation_urls,
    remove_invalid_citations_from_directory,
    reorder_directory_citations,
    INVALID_HTTP_CODES,
    HALLUCINATION_PATTERNS,
)
from .agents.citation_assembly import citation_assembly_agent                    # 16. Consolidate citations
from .agents.citation_validator import citation_validator_agent                   # 17. Citation accuracy
from .agents.fact_checker import fact_checker_agent                              # 18. Fact verification
from .agents.validator import validator_agent                                     # 19. Quality scoring
from .agents.scorecard_evaluator import scorecard_evaluator_agent                # 20. Scorecard evaluation
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
    from .utils import get_output_dir_from_state

    company_name = state["company_name"]
    firm = state.get("firm")

    print(f"\n🔍 VALIDATION GATE 1: Cleaning research citations for {company_name}...")
    print(f"   (This runs BEFORE writer to prevent hallucination propagation)")

    # Get output directory from state (created at workflow start)
    try:
        output_dir = get_output_dir_from_state(state)
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
    from .utils import get_output_dir_from_state

    company_name = state["company_name"]
    firm = state.get("firm")

    # Get artifact directory from state (created at workflow start)
    try:
        output_dir = get_output_dir_from_state(state)
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
    from .utils import get_output_dir_from_state

    validation = state.get("validation_results", {}).get("full_memo", {})
    score = state.get("overall_score", 0.0)
    issues = validation.get("issues", [])
    suggestions = validation.get("suggestions", [])
    company_name = state["company_name"]
    firm = state.get("firm")

    # Save draft artifacts even when it needs review
    try:
        # Use output directory from state (created at workflow start)
        output_dir = get_output_dir_from_state(state)

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
    from .utils import get_output_dir_from_state
    from pathlib import Path

    company_name = state["company_name"]
    firm = state.get("firm")

    try:
        output_dir = get_output_dir_from_state(state)
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

    # Add agent nodes (ordered by pipeline sequence)
    workflow.add_node("dataroom", dataroom_agent)  # Dataroom analysis (skips if no dataroom)
    workflow.add_node("deck_analyst", deck_analyst_agent)  # Deck analysis (skips if no deck)
    workflow.add_node("research", research_fn)
    workflow.add_node("section_research", perplexity_section_researcher_agent)  # Section-specific research with citations
    workflow.add_node("competitive_researcher", competitive_landscape_researcher)  # Competitive landscape discovery
    workflow.add_node("competitive_evaluator", competitive_landscape_evaluator)    # Competitive landscape evaluation
    workflow.add_node("cleanup_research", cleanup_research_citations)  # GATE 1: Clean research citations BEFORE writer
    workflow.add_node("draft", writer_agent)
    workflow.add_node("inject_deck_images", inject_deck_images_agent)  # Inject screenshots from deck into 2-sections/
    workflow.add_node("enrich_trademark", trademark_enrichment_agent)  # Company trademark insertion
    workflow.add_node("enrich_socials", socials_enrichment_agent)
    workflow.add_node("enrich_links", link_enrichment_agent)
    workflow.add_node("generate_tables", table_generator_agent)  # Generate markdown tables from structured data + prose
    workflow.add_node("generate_diagrams", diagram_generator_agent)  # Generate visual diagrams (TAM/SAM/SOM, etc.)
    workflow.add_node("enrich_visualizations", visualization_enrichment_agent)
    workflow.add_node("cite", citation_enrichment_agent)
    workflow.add_node("toc", toc_generator_agent)  # TOC generation — runs AFTER assemble_citations creates the final draft
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

    # Entry point: dataroom first (skips if no dataroom path)
    workflow.set_entry_point("dataroom")

    # Define edges (workflow sequence)
    #
    # PRIORITY ORDER FOR INITIAL DATA GATHERING:
    # 1. Dataroom analysis (richest source — full document set)
    # 2. Deck analysis (single pitch deck)
    # 3. Web research (company URL + web search)
    # Each step skips gracefully if its input is not provided.
    #
    # ANTI-HALLUCINATION ARCHITECTURE:
    # Two validation gates ensure hallucinated citations never propagate:
    #
    # GATE 1 (cleanup_research): After citation enrichment, BEFORE writer
    #   - Citation enrichment adds citations to 1-research/ files (preserving existing)
    #   - Cleanup validates ALL citations (existing + new)
    #   - Writer receives ONLY clean research data with validated citations
    #
    # GATE 2 (cleanup_sections): After revise_summaries, BEFORE assembly
    #   - Validates 2-sections/ citations
    #   - Catches any issues from section processing
    #
    # Full sequence:
    # Dataroom → Deck → Research → Section Research → Competitive Researcher →
    # Competitive Evaluator → [CITE on 1-research/] → [GATE 1] → Writer →
    # Inject Deck Images → Enrichment → Revise → [GATE 2] → Assembly → TOC →
    # Validate Citations → Fact Check → Validate → Scorecard → Integrate Scorecard
    # See: context-v/reminders/Ideal-Orchestration-Agent-Workflow.md

    workflow.add_edge("dataroom", "deck_analyst")
    workflow.add_edge("deck_analyst", "research")
    workflow.add_edge("research", "section_research")  # Generate section research with citations
    workflow.add_edge("section_research", "competitive_researcher")  # Discover candidate competitors
    workflow.add_edge("competitive_researcher", "competitive_evaluator")  # Evaluate and classify competitors
    workflow.add_edge("competitive_evaluator", "cite")  # Enrich research with additional citations (preserves existing)
    workflow.add_edge("cite", "cleanup_research")      # GATE 1: Validate ALL citations before writer
    workflow.add_edge("cleanup_research", "draft")     # Writer receives CLEAN, citation-enriched research
    workflow.add_edge("draft", "inject_deck_images")  # Inject deck screenshots into 2-sections/
    workflow.add_edge("inject_deck_images", "enrich_trademark")  # Then insert company trademark
    workflow.add_edge("enrich_trademark", "enrich_socials")
    workflow.add_edge("enrich_socials", "enrich_links")
    workflow.add_edge("enrich_links", "generate_tables")       # Generate tables after links are in place
    workflow.add_edge("generate_tables", "generate_diagrams")       # Generate diagrams after tables
    workflow.add_edge("generate_diagrams", "enrich_visualizations")
    workflow.add_edge("enrich_visualizations", "revise_summaries")  # Revise bookend sections based on complete draft
    workflow.add_edge("revise_summaries", "cleanup_sections")  # GATE 2: Clean sections before assembly
    workflow.add_edge("cleanup_sections", "assemble_citations")  # Consolidate, renumber citations, and CREATE final draft file
    workflow.add_edge("assemble_citations", "toc")  # Generate TOC (runs AFTER assembly creates the final draft)
    workflow.add_edge("toc", "validate_citations")  # Validate assembled citations
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
    force_version: str = None,
    fresh: bool = False,
    dataroom_path: str = None,
    deck_path: str = None,
    company_description: str = None,
    company_url: str = None,
    company_stage: str = None,
    research_notes: str = None,
    disambiguation_excludes: list = None,
    company_trademark_light: str = None,
    company_trademark_dark: str = None,
    outline_name: str = None,
    scorecard_name: str = None,
    search_variants: list = None,
    known_competitors: list = None
) -> MemoState:
    """
    Main entry point for generating an investment memo.

    Args:
        company_name: Name of the company to analyze
        investment_type: Type of investment - "direct" for startup, "fund" for LP commitment
        memo_mode: Memo mode - "consider" for prospective, "justify" for retrospective
        firm: Firm name for firm-scoped IO (e.g., "hypernova")
        force_version: Force a specific version string (e.g., "v0.1.0") instead of auto-incrementing
        fresh: If True, start from a clean slate (ignore prior artifacts/research)
        dataroom_path: Optional path to dataroom directory (richest data source)
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
    from .artifacts import sanitize_filename, create_artifact_directory
    from .versioning import MemoVersion

    # Determine version for this run.
    # --version flag: use the exact version specified
    # --fresh flag (no --version): auto-increment as usual, but start clean
    # Default: auto-increment from versions.json
    safe_name = sanitize_filename(company_name)
    if firm:
        version_mgr = VersionManager(firm=firm)
    else:
        version_mgr = VersionManager(output_dir=Path("output"))

    if force_version:
        # Normalize: ensure it starts with 'v'
        v_str = force_version if force_version.startswith("v") else f"v{force_version}"
        new_version = MemoVersion.from_string(v_str)
        print(f"📌 Using forced version: {new_version}")
    else:
        new_version = version_mgr.get_next_version(safe_name)

    output_dir = create_artifact_directory(company_name, str(new_version), firm=firm)

    if fresh:
        print(f"🧹 Fresh run: starting from clean slate at {new_version}")
        print(f"📁 Created new output directory: {output_dir}")
    else:
        print(f"📁 Created new output directory: {output_dir} ({new_version})")

    # Create initial state with all company context
    initial_state = create_initial_state(
        company_name,
        investment_type,
        memo_mode,
        firm=firm,
        output_dir=str(output_dir),
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

    # Build and run workflow
    app = build_workflow()
    final_state = app.invoke(initial_state, config={"recursion_limit": 50})

    return final_state

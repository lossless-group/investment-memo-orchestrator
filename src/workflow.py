"""
LangGraph workflow orchestration for investment memo generation.

This module defines the supervisor pattern that coordinates the Research,
Writer, and Validator agents through a state graph.
"""

from langgraph.graph import StateGraph, END
from typing import Literal as LiteralType

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
from .agents.citation_validator import citation_validator_agent
from .agents.validator import validator_agent
from .artifacts import sanitize_filename, save_final_draft, save_state_snapshot
from .versioning import VersionManager


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

    # Get artifact directory (most recent)
    try:
        output_dir = get_latest_output_dir(company_name)
        final_draft_path = output_dir / "4-final-draft.md"
    except FileNotFoundError:
        raise FileNotFoundError(f"No output directory found for {company_name}")

    # Verify final draft exists (created by citation enrichment)
    if not final_draft_path.exists():
        raise FileNotFoundError(f"Final draft not found at {final_draft_path}. Citation enrichment may have failed.")

    # Load final draft content
    with open(final_draft_path) as f:
        memo_content = f.read()

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
    validation = state.get("validation_results", {}).get("full_memo", {})
    score = state.get("overall_score", 0.0)
    issues = validation.get("issues", [])
    suggestions = validation.get("suggestions", [])
    company_name = state["company_name"]

    # Save draft artifacts even when it needs review
    try:
        # Get version manager
        version_mgr = VersionManager(Path("output"))
        safe_name = sanitize_filename(company_name)
        version = version_mgr.get_next_version(safe_name)

        # Get artifact directory
        output_dir = Path("output") / f"{safe_name}-{version}"

        # Get draft content
        draft = state.get("draft_sections", {}).get("full_memo", {})
        memo_content = draft.get("content", "")

        # Save as draft (not final)
        if memo_content:
            save_final_draft(output_dir, memo_content)

        # Save state snapshot
        save_state_snapshot(output_dir, state)

        print(f"Draft saved for review to: {output_dir / '4-final-draft.md'}")
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
    workflow.add_node("deck_analyst", deck_analyst_agent)  # NEW: Deck analyst (always runs, skips if no deck)
    workflow.add_node("research", research_fn)
    workflow.add_node("section_research", perplexity_section_researcher_agent)  # NEW: Section-specific research with citations
    workflow.add_node("draft", writer_agent)
    workflow.add_node("enrich_trademark", trademark_enrichment_agent)  # NEW: Company trademark insertion
    workflow.add_node("enrich_socials", socials_enrichment_agent)
    workflow.add_node("enrich_links", link_enrichment_agent)
    workflow.add_node("enrich_visualizations", visualization_enrichment_agent)
    workflow.add_node("cite", citation_enrichment_agent)
    workflow.add_node("validate_citations", citation_validator_agent)  # NEW: Citation accuracy validator
    workflow.add_node("validate", validator_agent)
    workflow.add_node("finalize", finalize_memo)
    workflow.add_node("human_review", human_review)

    # SIMPLIFIED: Always start with deck_analyst (it skips if no deck)
    workflow.set_entry_point("deck_analyst")

    # Define edges (workflow sequence)
    # Deck Analyst → Research → Section Research (Perplexity) → Draft → Trademark → Socials → Links → Visualizations → Citations → Citation Validator → Validate
    workflow.add_edge("deck_analyst", "research")
    workflow.add_edge("research", "section_research")  # NEW: Generate section research with citations
    workflow.add_edge("section_research", "draft")     # Writer polishes section research
    workflow.add_edge("draft", "enrich_trademark")  # NEW: Insert company trademark after drafting
    workflow.add_edge("enrich_trademark", "enrich_socials")
    workflow.add_edge("enrich_socials", "enrich_links")
    workflow.add_edge("enrich_links", "enrich_visualizations")
    workflow.add_edge("enrich_visualizations", "cite")
    workflow.add_edge("cite", "validate_citations")  # NEW: Validate citation accuracy after enrichment
    workflow.add_edge("validate_citations", "validate")

    # Conditional edge after validation
    workflow.add_conditional_edges(
        "validate",
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
    deck_path: str = None,
    company_description: str = None,
    company_url: str = None,
    company_stage: str = None,
    research_notes: str = None,
    company_trademark_light: str = None,
    company_trademark_dark: str = None
) -> MemoState:
    """
    Main entry point for generating an investment memo.

    Args:
        company_name: Name of the company to analyze
        investment_type: Type of investment - "direct" for startup, "fund" for LP commitment
        memo_mode: Memo mode - "consider" for prospective, "justify" for retrospective
        deck_path: Optional path to pitch deck PDF
        company_description: Brief description of what the company does
        company_url: Company website URL
        company_stage: Investment stage (Seed, Series A, etc.)
        research_notes: Additional research guidance or focus areas
        company_trademark_light: Path or URL to light mode company logo/trademark
        company_trademark_dark: Path or URL to dark mode company logo/trademark

    Returns:
        Final state containing research, draft, validation, and final memo
    """
    from .state import create_initial_state

    # Create initial state with all company context
    initial_state = create_initial_state(
        company_name,
        investment_type,
        memo_mode,
        deck_path,
        company_description,
        company_url,
        company_stage,
        research_notes,
        company_trademark_light,
        company_trademark_dark
    )

    # Build and run workflow
    app = build_workflow()
    final_state = app.invoke(initial_state)

    return final_state

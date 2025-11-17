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
from .agents.writer import writer_agent
from .agents.citation_enrichment import citation_enrichment_agent
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

    Args:
        state: Current memo state

    Returns:
        Updated state with final_memo set
    """
    draft = state.get("draft_sections", {}).get("full_memo", {})
    memo_content = draft.get("content", "")
    company_name = state["company_name"]

    # Save final draft artifact
    try:
        # Get version manager
        version_mgr = VersionManager(Path("output"))
        safe_name = sanitize_filename(company_name)
        version = version_mgr.get_next_version(safe_name)

        # Get artifact directory
        output_dir = Path("output") / f"{safe_name}-{version}"

        # Save final draft
        save_final_draft(output_dir, memo_content)

        # Save state snapshot
        save_state_snapshot(output_dir, state)

        print(f"Final draft saved to: {output_dir / '4-final-draft.md'}")
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
    workflow.add_node("research", research_fn)
    workflow.add_node("draft", writer_agent)
    workflow.add_node("cite", citation_enrichment_agent)
    workflow.add_node("validate", validator_agent)
    workflow.add_node("finalize", finalize_memo)
    workflow.add_node("human_review", human_review)

    # Define edges (workflow sequence)
    workflow.add_edge("research", "draft")
    workflow.add_edge("draft", "cite")
    workflow.add_edge("cite", "validate")

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

    # Set entry point
    workflow.set_entry_point("research")

    # Compile and return
    return workflow.compile()


def generate_memo(
    company_name: str,
    investment_type: LiteralType["direct", "fund"] = "direct",
    memo_mode: LiteralType["consider", "justify"] = "consider"
) -> MemoState:
    """
    Main entry point for generating an investment memo.

    Args:
        company_name: Name of the company to analyze
        investment_type: Type of investment - "direct" for startup, "fund" for LP commitment
        memo_mode: Memo mode - "consider" for prospective, "justify" for retrospective

    Returns:
        Final state containing research, draft, validation, and final memo
    """
    from .state import create_initial_state

    # Create initial state
    initial_state = create_initial_state(company_name, investment_type, memo_mode)

    # Build and run workflow
    app = build_workflow()
    final_state = app.invoke(initial_state)

    return final_state

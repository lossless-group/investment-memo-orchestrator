"""
State schema for the investment memo generation workflow.

This module defines the TypedDict structures that LangGraph uses to maintain
state throughout the multi-agent memo generation process.
"""

from typing import TypedDict, Optional, List, Dict, Any, Annotated
from operator import add


class CompanyData(TypedDict, total=False):
    """Basic company information."""
    name: str
    stage: str
    hq_location: str
    website: str
    founders: List[Dict[str, str]]


class ResearchData(TypedDict, total=False):
    """Comprehensive research gathered by Research Agent."""
    company: CompanyData
    market: Dict[str, Any]
    technology: Dict[str, Any]
    team: Dict[str, Any]
    traction: Dict[str, Any]
    funding: Dict[str, Any]
    sources: List[str]


class SectionDraft(TypedDict, total=False):
    """Individual memo section draft."""
    section_name: str
    content: str
    word_count: int
    citations: List[str]


class ValidationFeedback(TypedDict, total=False):
    """Validation results for a specific section."""
    section_name: str
    score: float  # 0-10 scale
    issues: List[str]
    suggestions: List[str]


class MemoState(TypedDict):
    """
    Main state object for the investment memo workflow.

    This state is passed between all agents and updated as the workflow progresses.
    LangGraph manages this state and provides it to each agent in the graph.
    """
    # Input
    company_name: str

    # Research phase
    research: Optional[ResearchData]

    # Writing phase
    draft_sections: Dict[str, SectionDraft]

    # Validation phase
    validation_results: Dict[str, ValidationFeedback]
    overall_score: float

    # Iteration tracking
    revision_count: int

    # Output
    final_memo: Optional[str]

    # Agent messages and intermediate steps (for debugging)
    messages: Annotated[List[str], add]  # Append-only list of agent outputs


def create_initial_state(company_name: str) -> MemoState:
    """
    Create initial state for a new memo generation workflow.

    Args:
        company_name: Name of the company to research and create memo for

    Returns:
        MemoState with initialized values
    """
    return MemoState(
        company_name=company_name,
        research=None,
        draft_sections={},
        validation_results={},
        overall_score=0.0,
        revision_count=0,
        final_memo=None,
        messages=[]
    )

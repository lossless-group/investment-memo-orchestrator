"""
State schema for the investment memo generation workflow.

This module defines the TypedDict structures that LangGraph uses to maintain
state throughout the multi-agent memo generation process.
"""

from typing import TypedDict, Optional, List, Dict, Any, Annotated, Literal
from operator import add


class CitationSource(TypedDict, total=False):
    """
    Citation source metadata for preserving attribution.

    Used to track where information came from during web search and research.
    This enables proper source attribution in the final memo.
    """
    title: str              # Title of the source (e.g., "Crunchbase - Aalo Atomics")
    url: str                # URL of the source
    retrieved: str          # Date retrieved (YYYY-MM-DD format)
    context: str            # Relevant excerpt or context from source
    provider: str           # Search provider that returned this (e.g., "tavily", "perplexity")


class DeckAnalysisData(TypedDict, total=False):
    """Structured data extracted from pitch deck"""
    company_name: str
    tagline: Optional[str]
    problem_statement: Optional[str]
    solution_description: Optional[str]
    product_description: Optional[str]
    business_model: Optional[str]
    market_size: Optional[Dict[str, str]]  # TAM, SAM, SOM
    traction_metrics: Optional[List[Dict[str, str]]]
    team_members: Optional[List[Dict[str, str]]]
    funding_ask: Optional[str]
    use_of_funds: Optional[List[str]]
    competitive_landscape: Optional[str]
    go_to_market: Optional[str]
    milestones: Optional[List[str]]
    deck_page_count: int
    extraction_notes: List[str]  # What info was/wasn't found


class CompanyData(TypedDict, total=False):
    """Basic company information."""
    name: str
    stage: str
    hq_location: str
    website: str
    founders: List[Dict[str, str]]


class ResearchData(TypedDict, total=False):
    """
    Comprehensive research gathered by Research Agent.

    Each subsection (market, technology, team, traction, funding) can contain:
    - Data fields specific to that area
    - A 'sources' list with CitationSource objects for attribution
    - A 'linkedin_url' or other URLs for linking

    Example structure:
    {
        "company": {...},
        "market": {
            "tam": "$23B",
            "sources": [{"title": "Gartner 2024", "url": "...", ...}]
        },
        "team": {
            "founders": [
                {
                    "name": "John Doe",
                    "title": "CEO",
                    "background": "...",
                    "linkedin_url": "https://linkedin.com/in/johndoe"
                }
            ],
            "sources": [...]
        },
        "funding": {
            "total_raised": "$136M",
            "sources": [...]
        },
        "web_search_metadata": {
            "provider": "tavily",
            "queries_count": 4,
            "total_results": 25
        }
    }
    """
    company: CompanyData
    market: Dict[str, Any]
    technology: Dict[str, Any]
    team: Dict[str, Any]
    traction: Dict[str, Any]
    funding: Dict[str, Any]
    sources: List[str]
    web_search_metadata: Dict[str, Any]  # Metadata about web search execution
    company_overview: Dict[str, Any]     # Company overview with sources
    recent_news: Dict[str, Any]          # Recent news with sources


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
    investment_type: Literal["direct", "fund"]  # Type of investment
    memo_mode: Literal["consider", "justify"]  # Memo purpose

    # Deck analysis (NEW)
    deck_path: Optional[str]
    deck_analysis: Optional[DeckAnalysisData]

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


def create_initial_state(
    company_name: str,
    investment_type: Literal["direct", "fund"] = "direct",
    memo_mode: Literal["consider", "justify"] = "consider",
    deck_path: Optional[str] = None
) -> MemoState:
    """
    Create initial state for a new memo generation workflow.

    Args:
        company_name: Name of the company to research and create memo for
        investment_type: Type of investment - "direct" for startup, "fund" for LP commitment
        memo_mode: Memo mode - "consider" for prospective, "justify" for retrospective
        deck_path: Optional path to pitch deck PDF

    Returns:
        MemoState with initialized values
    """
    return MemoState(
        company_name=company_name,
        investment_type=investment_type,
        memo_mode=memo_mode,
        deck_path=deck_path,
        deck_analysis=None,
        research=None,
        draft_sections={},
        validation_results={},
        overall_score=0.0,
        revision_count=0,
        final_memo=None,
        messages=[]
    )

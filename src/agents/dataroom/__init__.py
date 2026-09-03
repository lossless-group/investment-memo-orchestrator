"""
Dataroom Analyzer Agent System

Multi-agent system for analyzing investment datarooms containing
diverse document types (pitch decks, financials, legal docs, etc.)
"""

# Load .env at the package boundary.
#
# Every agent in here reads ANTHROPIC_API_KEY at call time. The pipeline's own
# entry points load .env before importing anything, but these agents are also
# invoked directly -- from a notebook, a one-off script, or another agent -- and
# in that path the key was simply absent. The symptom was not an error at
# startup: extraction proceeded, every model call failed on authentication, and
# each extractor caught its own exception and reported "no data extracted". A
# whole cap-table pass looked like a dataroom with no cap table in it.
#
# Doing this once here rather than in each of seven call sites means a new
# extractor cannot reintroduce it by forgetting.
from dotenv import load_dotenv as _load_dotenv

_load_dotenv()


from .document_scanner import scan_dataroom, get_directory_structure
from .document_classifier import classify_documents
from .dataroom_analyzer import analyze_dataroom, dataroom_agent
from .dataroom_state import (
    DocumentInventoryItem,
    DataroomAnalysis,
    FinancialData,
    CapTableData,
    CompetitiveData,
    TeamData,
    TractionData,
)

__all__ = [
    "analyze_dataroom",
    "dataroom_agent",
    "scan_dataroom",
    "get_directory_structure",
    "classify_documents",
    "DocumentInventoryItem",
    "DataroomAnalysis",
    "FinancialData",
    "CapTableData",
    "CompetitiveData",
    "TeamData",
    "TractionData",
]

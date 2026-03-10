"""
Dataroom Analyzer Agent System

Multi-agent system for analyzing investment datarooms containing
diverse document types (pitch decks, financials, legal docs, etc.)
"""

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

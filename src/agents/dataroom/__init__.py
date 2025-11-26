"""
Dataroom Analyzer Agent System

Multi-agent system for analyzing investment datarooms containing
diverse document types (pitch decks, financials, legal docs, etc.)
"""

from .document_scanner import scan_dataroom, get_directory_structure
from .document_classifier import classify_documents
from .analyzer import analyze_dataroom
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

"""
Scrapers for extracting and converting data from various sources.

These are standalone tools that can be run independently or
integrated into other systems. They are NOT agents - they don't
participate in LangGraph workflows or make LLM-driven decisions.
"""

from .research_pdf import (
    scrape_research_pdf,
    ResearchPDFScraper,
)

__all__ = [
    "scrape_research_pdf",
    "ResearchPDFScraper",
]

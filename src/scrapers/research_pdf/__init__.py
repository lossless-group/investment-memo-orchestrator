"""
Research PDF Scraper - Extracts content and citations from market research PDFs.

This scraper converts research PDFs (from firms like McKinsey, CB Insights,
PitchBook, Gartner) into markdown with properly formatted citations.

Usage:
    from src.scrapers.research_pdf import scrape_research_pdf

    # Simple usage
    result = scrape_research_pdf("path/to/research.pdf")

    # With output directory
    result = scrape_research_pdf("path/to/research.pdf", output_dir="output/parsed/")

CLI Usage:
    python cli/parse_research_pdf.py path/to/research.pdf
"""

from .converter import ResearchPDFScraper, scrape_research_pdf

__all__ = [
    "ResearchPDFScraper",
    "scrape_research_pdf",
]

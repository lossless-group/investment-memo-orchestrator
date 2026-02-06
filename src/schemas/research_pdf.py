"""
Schema definitions for the PDF parser.

These schemas are independent of the memo generation workflow,
allowing the PDF parser to be used as a standalone tool or
integrated into multiple agentic systems.
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal


# Citation format types commonly found in research PDFs
CitationFormat = Literal[
    "footnotes",      # Numbered footnotes at bottom of page
    "endnotes",       # Numbered endnotes at end of document
    "bibliography",   # Author-date style with bibliography
    "bracketed",      # [1], [2], [3] style inline
    "superscript",    # Superscript numbers
    "mixed",          # Multiple formats detected
    "unknown"         # Could not determine format
]


class ParsedCitation(TypedDict, total=False):
    """
    A citation extracted from a PDF and converted to our standard format.

    Our standard format:
    [^1]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD
    """
    # Original citation data from PDF
    original_ref: str           # Original reference marker (e.g., "1", "[1]", "†")
    original_text: str          # Full original citation text from PDF

    # Parsed components
    title: str                  # Parsed title of the source
    author: Optional[str]       # Author or organization name
    date: Optional[str]         # Date in YYYY-MM-DD format (or partial like "2024" or "2024-03")
    date_display: Optional[str] # Date formatted for display (e.g., "Mar 15" or "2024")
    url: Optional[str]          # URL if present in citation
    publication: Optional[str]  # Publication/journal/report name
    citation_type: str          # "report", "article", "book", "website", "press_release", "other"

    # Our formatted output
    our_format: str             # Citation in our standard [^n]: format

    # Metadata
    page_references: List[int]  # Pages where this citation's inline ref appears
    location_in_pdf: str        # "footnote", "endnote", "bibliography", "inline"
    confidence: float           # 0.0-1.0 parsing confidence score
    parsing_notes: List[str]    # Any issues or assumptions made during parsing


class ParsedPDFSection(TypedDict, total=False):
    """A section identified in a parsed PDF."""
    section_id: str             # Slugified identifier (e.g., "executive-summary")
    title: str                  # Section title
    level: int                  # Heading level (1=H1, 2=H2, 3=H3)
    start_page: int             # Page where section starts (1-indexed)
    end_page: int               # Page where section ends (1-indexed)
    content_markdown: str       # Section content converted to markdown
    content_plain: str          # Plain text content (no formatting)
    word_count: int
    has_tables: bool            # Whether section contains tables
    has_figures: bool           # Whether section contains figures/charts
    inline_citations: List[str] # List of citation refs used in this section


class ParsedTable(TypedDict, total=False):
    """A table extracted from a PDF."""
    table_id: str               # Identifier (e.g., "table-1", "page-5-table-2")
    page: int                   # Page where table appears
    caption: Optional[str]      # Table caption if present
    headers: List[str]          # Column headers
    rows: List[List[str]]       # Table data rows
    markdown: str               # Table as markdown
    section_id: Optional[str]   # Which section this table belongs to


class PDFMetadata(TypedDict, total=False):
    """Metadata extracted from PDF properties."""
    title: Optional[str]
    author: Optional[str]
    subject: Optional[str]
    creator: Optional[str]      # Software that created the PDF
    producer: Optional[str]     # Software that produced the PDF
    created_date: Optional[str] # Creation date
    modified_date: Optional[str] # Last modified date
    page_count: int
    file_size_bytes: int


class ParsingStats(TypedDict, total=False):
    """Statistics about the parsing process."""
    method: str                 # "text_extraction" or "vision_ocr"
    text_extracted_chars: int
    images_detected: int
    tables_detected: int
    footnotes_detected: int
    endnotes_detected: int
    bibliography_entries: int
    processing_time_seconds: float
    pages_processed: int
    pages_skipped: int          # Pages that couldn't be processed
    ocr_confidence: Optional[float]  # If OCR was used


class ParsedPDFData(TypedDict, total=False):
    """
    Complete data from a parsed research PDF.

    This is the main output structure saved to disk and used by other tools.
    """
    # Identification
    pdf_id: str                           # Slugified identifier for this PDF
    original_filename: str                # Original file name
    source_path: str                      # Full path to source PDF
    output_dir: str                       # Directory where parsed output is saved

    # Content
    full_markdown: str                    # Complete document as markdown
    sections: List[ParsedPDFSection]      # Document broken into sections
    tables: List[ParsedTable]             # Extracted tables

    # Citations
    citation_format_detected: CitationFormat
    citations: List[ParsedCitation]       # All extracted citations
    citations_markdown: str               # Citation block in our format (for appending)
    unmatched_refs: List[Dict[str, str]]  # Inline refs that couldn't be matched to citations

    # Metadata
    pdf_metadata: PDFMetadata
    parsing_stats: ParsingStats

    # Quality indicators
    parsing_confidence: float             # Overall confidence 0.0-1.0
    warnings: List[str]                   # Issues encountered during parsing

    # Optional LLM-enhanced fields
    key_findings: Optional[List[str]]     # LLM-extracted key insights
    summary: Optional[str]                # LLM-generated summary


class PDFParseResult(TypedDict):
    """
    Result returned by the PDF parser.

    Includes both the parsed data and status information.
    """
    success: bool
    pdf_id: str
    output_dir: str
    data: Optional[ParsedPDFData]         # Full parsed data if successful
    error: Optional[str]                  # Error message if failed
    warnings: List[str]                   # Non-fatal issues

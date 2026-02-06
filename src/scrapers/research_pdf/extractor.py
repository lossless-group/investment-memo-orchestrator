"""
PDF text and structure extraction using PyMuPDF (fitz).

Extracts text, detects document structure, and identifies footnote locations.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass
class ExtractedPage:
    """Data extracted from a single PDF page."""
    page_number: int  # 1-indexed
    text: str
    footnotes: List[Dict[str, Any]]
    has_tables: bool
    has_images: bool
    word_count: int


@dataclass
class DocumentStructure:
    """Document structure detected from PDF."""
    title: Optional[str]
    sections: List[Dict[str, Any]]  # {title, level, start_page, end_page}
    toc_page: Optional[int]
    references_start_page: Optional[int]
    references_end_page: Optional[int]


class PDFExtractor:
    """
    Extracts text, structure, and footnotes from PDF documents.
    """

    def extract(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract all content from a PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dict with extracted content and metadata
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(pdf_path)

        try:
            # Get PDF metadata
            metadata = self._extract_metadata(doc, path)

            # Extract text from all pages
            pages = self._extract_pages(doc)

            # Check if we got meaningful text
            total_text = " ".join(p.text for p in pages)
            is_image_based = len(total_text.strip()) < 1000

            # Detect document structure
            structure = self._detect_structure(doc, pages)

            # Collect all footnotes
            all_footnotes = []
            for page in pages:
                all_footnotes.extend(page.footnotes)

            # Find and extract references section
            references_text = ""
            if structure.references_start_page:
                references_text = self._extract_references_section(
                    pages,
                    structure.references_start_page,
                    structure.references_end_page
                )

            # Extract tables
            tables = self._extract_tables(doc)

            return {
                "metadata": metadata,
                "pages": pages,
                "full_text": total_text,
                "structure": structure,
                "footnotes": all_footnotes,
                "references_text": references_text,
                "tables": tables,
                "is_image_based": is_image_based,
                "page_count": len(doc),
                "word_count": len(total_text.split())
            }

        finally:
            doc.close()

    def _extract_metadata(self, doc: fitz.Document, path: Path) -> Dict[str, Any]:
        """Extract PDF metadata."""
        meta = doc.metadata or {}

        return {
            "title": meta.get("title") or None,
            "author": meta.get("author") or None,
            "subject": meta.get("subject") or None,
            "creator": meta.get("creator") or None,
            "producer": meta.get("producer") or None,
            "created_date": meta.get("creationDate") or None,
            "modified_date": meta.get("modDate") or None,
            "page_count": len(doc),
            "file_size_bytes": path.stat().st_size
        }

    def _extract_pages(self, doc: fitz.Document) -> List[ExtractedPage]:
        """Extract text and structure from each page."""
        pages = []

        for page_num, page in enumerate(doc, 1):
            # Get text with layout preservation
            text = page.get_text("text")

            # Detect footnotes by position
            footnotes = self._extract_page_footnotes(page, page_num)

            # Check for tables and images
            has_tables = self._page_has_tables(page)
            has_images = len(page.get_images()) > 0

            pages.append(ExtractedPage(
                page_number=page_num,
                text=text,
                footnotes=footnotes,
                has_tables=has_tables,
                has_images=has_images,
                word_count=len(text.split())
            ))

        return pages

    def _page_has_tables(self, page: fitz.Page) -> bool:
        """Check if page has tables."""
        try:
            tables = page.find_tables()
            return len(tables.tables) > 0 if hasattr(tables, 'tables') else len(tables) > 0
        except (AttributeError, Exception):
            return False

    def _extract_page_footnotes(self, page: fitz.Page, page_num: int) -> List[Dict[str, Any]]:
        """
        Extract footnotes from a page based on position and formatting.

        Footnotes typically appear at bottom of page with smaller font.
        """
        footnotes = []
        page_height = page.rect.height
        footnote_zone_start = page_height * 0.80  # Bottom 20% of page

        # Get text blocks with position info
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block.get("type") != 0:  # Not a text block
                continue

            bbox = block.get("bbox", [0, 0, 0, 0])
            y_pos = bbox[1]  # Top of block

            # Check if in footnote zone
            if y_pos > footnote_zone_start:
                # Extract text from block
                block_text = self._extract_block_text(block)

                # Check if starts with a reference number
                ref_match = re.match(r'^([¹²³⁴⁵⁶⁷⁸⁹⁰]+|\d+[\.\)])\s*(.+)', block_text, re.DOTALL)
                if ref_match:
                    ref_num = self._normalize_ref_number(ref_match.group(1))

                    footnotes.append({
                        "ref": ref_num,
                        "text": ref_match.group(2).strip(),
                        "page": page_num
                    })

        return footnotes

    def _extract_block_text(self, block: Dict) -> str:
        """Extract text from a PyMuPDF text block."""
        block_text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                block_text += span.get("text", "")
            block_text += "\n"
        return block_text.strip()

    def _normalize_ref_number(self, ref: str) -> str:
        """Convert superscript or formatted ref to plain number."""
        superscript_map = {
            '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
            '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
        }
        ref_num = ''.join(superscript_map.get(c, c) for c in ref)
        return ref_num.rstrip('.)')

    def _detect_structure(self, doc: fitz.Document, pages: List[ExtractedPage]) -> DocumentStructure:
        """
        Detect document structure: sections, TOC, references location.
        """
        sections = []
        toc_page = None
        refs_start = None
        refs_end = None
        title = None

        # Try to get TOC from PDF metadata
        toc = doc.get_toc()
        if toc:
            for level, section_title, page_num in toc:
                sections.append({
                    "title": section_title,
                    "level": level,
                    "start_page": page_num,
                    "end_page": None
                })

        # If no TOC in metadata, detect from content
        if not sections:
            sections = self._detect_sections_from_content(pages)

        # Calculate section end pages
        for i, section in enumerate(sections):
            if i + 1 < len(sections):
                section["end_page"] = sections[i + 1]["start_page"] - 1
            else:
                section["end_page"] = len(pages)

        # Find references section
        refs_start, refs_end = self._find_references_section(sections, pages)

        # Find TOC page
        toc_page = self._find_toc_page(pages)

        # Get document title
        if pages:
            title = self._extract_title_from_page(pages[0])

        return DocumentStructure(
            title=title,
            sections=sections,
            toc_page=toc_page,
            references_start_page=refs_start,
            references_end_page=refs_end
        )

    def _detect_sections_from_content(self, pages: List[ExtractedPage]) -> List[Dict[str, Any]]:
        """
        Detect sections from page content when no TOC is available.
        """
        sections = []

        # Common section heading patterns
        patterns = [
            r'^(\d+\.?\s+[A-Z][A-Za-z\s]+)$',  # Numbered: "1. Introduction"
            r'^([A-Z][A-Z\s]{5,50})$',  # All caps: "INTRODUCTION"
            r'^(Chapter\s+\d+[:\s]+[A-Z][A-Za-z\s]+)$',  # Chapter style
        ]

        for page in pages:
            lines = page.text.split('\n')
            for line in lines:
                line = line.strip()
                if not line or len(line) > 100:
                    continue

                for pattern in patterns:
                    match = re.match(pattern, line)
                    if match:
                        level = 1
                        if re.match(r'^\d+\.\d+', line):
                            level = 2
                        elif re.match(r'^\d+\.\d+\.\d+', line):
                            level = 3

                        sections.append({
                            "title": match.group(1).strip(),
                            "level": level,
                            "start_page": page.page_number,
                            "end_page": None
                        })
                        break

        return sections

    def _find_references_section(
        self,
        sections: List[Dict],
        pages: List[ExtractedPage]
    ) -> Tuple[Optional[int], Optional[int]]:
        """Find the references/bibliography section."""
        refs_keywords = ["references", "bibliography", "works cited", "endnotes", "notes", "sources"]

        # Check sections first
        for section in sections:
            if any(kw in section["title"].lower() for kw in refs_keywords):
                return section["start_page"], section["end_page"]

        # Search page content from end
        for page in reversed(pages):
            text_lower = page.text.lower()
            for keyword in refs_keywords:
                if keyword in text_lower:
                    lines = page.text.split('\n')
                    for line in lines:
                        if keyword in line.lower() and len(line.strip()) < 50:
                            return page.page_number, len(pages)

        return None, None

    def _find_toc_page(self, pages: List[ExtractedPage]) -> Optional[int]:
        """Find the table of contents page."""
        for page in pages[:10]:
            text_lower = page.text.lower()
            if "table of contents" in text_lower or "contents" in text_lower:
                return page.page_number
        return None

    def _extract_title_from_page(self, page: ExtractedPage) -> Optional[str]:
        """Extract document title from first page."""
        lines = page.text.split('\n')

        for line in lines[:10]:
            line = line.strip()
            if len(line) > 20 and len(line) < 200:
                if not re.match(r'^\d', line) and not re.match(r'^page', line.lower()):
                    return line

        return None

    def _extract_references_section(
        self,
        pages: List[ExtractedPage],
        start_page: int,
        end_page: Optional[int]
    ) -> str:
        """Extract text from the references section."""
        end_page = end_page or len(pages)

        text_parts = []
        for page in pages:
            if start_page <= page.page_number <= end_page:
                text_parts.append(page.text)

        return "\n\n".join(text_parts)

    def _extract_tables(self, doc: fitz.Document) -> List[Dict[str, Any]]:
        """
        Extract tables from PDF.
        """
        tables = []

        for page_num, page in enumerate(doc, 1):
            try:
                page_tables = page.find_tables()
                table_list = page_tables.tables if hasattr(page_tables, 'tables') else page_tables

                for i, table in enumerate(table_list):
                    table_data = table.extract()
                    if table_data and len(table_data) > 1:
                        tables.append({
                            "table_id": f"page-{page_num}-table-{i+1}",
                            "page": page_num,
                            "headers": table_data[0] if table_data else [],
                            "rows": table_data[1:] if len(table_data) > 1 else [],
                            "row_count": len(table_data) - 1
                        })
            except (AttributeError, Exception):
                pass

        return tables

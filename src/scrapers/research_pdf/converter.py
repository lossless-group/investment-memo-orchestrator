"""
Main research PDF scraper/converter.

Orchestrates extraction, citation scraping, and markdown conversion.
"""

import json
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from ...schemas.research_pdf import (
    ParsedPDFData,
    PDFParseResult,
    ParsedPDFSection,
    ParsedTable,
    PDFMetadata,
    ParsingStats,
)
from .extractor import PDFExtractor
from .citation_scraper import CitationScraper


class ResearchPDFScraper:
    """
    Scrapes research PDFs and converts to markdown with citations.
    """

    def __init__(self, extract_tables: bool = True):
        """
        Initialize the scraper.

        Args:
            extract_tables: Whether to extract tables from PDF
        """
        self.extract_tables = extract_tables
        self.extractor = PDFExtractor()
        self.citation_scraper = CitationScraper()

    def scrape(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None
    ) -> PDFParseResult:
        """
        Scrape a research PDF and save results.

        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save output (default: same dir as PDF)

        Returns:
            PDFParseResult with scraped data or error
        """
        start_time = time.time()
        warnings = []

        path = Path(pdf_path)
        if not path.exists():
            return PDFParseResult(
                success=False,
                pdf_id="",
                output_dir="",
                data=None,
                error=f"PDF file not found: {pdf_path}",
                warnings=[]
            )

        # Generate PDF ID from filename
        pdf_id = self._slugify(path.stem)

        # Determine output directory
        if output_dir:
            out_path = Path(output_dir) / pdf_id
        else:
            out_path = path.parent / "parsed" / pdf_id
        out_path.mkdir(parents=True, exist_ok=True)

        print(f"Scraping PDF: {path.name}")
        print(f"Output directory: {out_path}")

        try:
            # Step 1: Extract content from PDF
            print("  Extracting content...")
            extracted = self.extractor.extract(pdf_path)

            if extracted["is_image_based"]:
                warnings.append("PDF appears to be image-based; text extraction may be incomplete")

            # Step 2: Scrape citations
            print("  Scraping citations...")
            citations = self.citation_scraper.scrape_citations(
                main_text=extracted["full_text"],
                reference_section=extracted["references_text"],
                footnotes=extracted["footnotes"]
            )
            print(f"    Found {len(citations)} citations")

            # Step 3: Convert to markdown sections
            print("  Converting to markdown...")
            sections = self._create_sections(extracted)

            # Step 4: Create tables list
            tables = []
            if self.extract_tables and extracted.get("tables"):
                tables = self._format_tables(extracted["tables"])
                print(f"    Found {len(tables)} tables")

            # Step 5: Build full markdown
            full_markdown = self._build_full_markdown(
                extracted,
                sections,
                citations
            )

            # Step 6: Build citations markdown block
            citations_markdown = self._build_citations_block(citations)

            # Calculate processing time
            processing_time = time.time() - start_time

            # Build metadata
            pdf_metadata = PDFMetadata(
                title=extracted["metadata"].get("title"),
                author=extracted["metadata"].get("author"),
                subject=extracted["metadata"].get("subject"),
                creator=extracted["metadata"].get("creator"),
                producer=extracted["metadata"].get("producer"),
                created_date=extracted["metadata"].get("created_date"),
                modified_date=extracted["metadata"].get("modified_date"),
                page_count=extracted["page_count"],
                file_size_bytes=extracted["metadata"].get("file_size_bytes", 0)
            )

            # Build parsing stats
            parsing_stats = ParsingStats(
                method="vision_ocr" if extracted["is_image_based"] else "text_extraction",
                text_extracted_chars=len(extracted["full_text"]),
                images_detected=sum(1 for p in extracted["pages"] if p.has_images),
                tables_detected=len(tables),
                footnotes_detected=len(extracted["footnotes"]),
                endnotes_detected=len([c for c in citations if c.get("location_in_pdf") == "endnotes"]),
                bibliography_entries=0,
                processing_time_seconds=processing_time,
                pages_processed=extracted["page_count"],
                pages_skipped=0
            )

            # Calculate overall confidence
            confidence = self._calculate_confidence(extracted, citations)

            # Detect citation format
            citation_format = self.citation_scraper.detect_citation_format(
                extracted["full_text"],
                extracted["references_text"]
            )

            # Build final data structure
            data = ParsedPDFData(
                pdf_id=pdf_id,
                original_filename=path.name,
                source_path=str(path.absolute()),
                output_dir=str(out_path),
                full_markdown=full_markdown,
                sections=sections,
                tables=tables,
                citation_format_detected=citation_format,
                citations=citations,
                citations_markdown=citations_markdown,
                unmatched_refs=[],
                pdf_metadata=pdf_metadata,
                parsing_stats=parsing_stats,
                parsing_confidence=confidence,
                warnings=warnings,
                key_findings=None,
                summary=None
            )

            # Save outputs
            print("  Saving outputs...")
            self._save_outputs(out_path, data)

            print(f"  Done in {processing_time:.1f}s")

            return PDFParseResult(
                success=True,
                pdf_id=pdf_id,
                output_dir=str(out_path),
                data=data,
                error=None,
                warnings=warnings
            )

        except Exception as e:
            import traceback
            return PDFParseResult(
                success=False,
                pdf_id=pdf_id,
                output_dir=str(out_path),
                data=None,
                error=f"Scraping failed: {str(e)}\n{traceback.format_exc()}",
                warnings=warnings
            )

    def _slugify(self, text: str) -> str:
        """Convert text to URL-safe slug."""
        text = text.lower()
        text = re.sub(r'[\s_]+', '-', text)
        text = re.sub(r'[^a-z0-9-]', '', text)
        text = re.sub(r'-+', '-', text)
        text = text.strip('-')
        return text

    def _create_sections(self, extracted: Dict[str, Any]) -> List[ParsedPDFSection]:
        """Create section objects from extracted structure."""
        sections = []
        structure = extracted["structure"]

        if not structure.sections:
            # No sections detected - create one for entire document
            sections.append(ParsedPDFSection(
                section_id="full-document",
                title="Full Document",
                level=1,
                start_page=1,
                end_page=extracted["page_count"],
                content_markdown=self._text_to_markdown(extracted["full_text"]),
                content_plain=extracted["full_text"],
                word_count=extracted["word_count"],
                has_tables=any(p.has_tables for p in extracted["pages"]),
                has_figures=any(p.has_images for p in extracted["pages"]),
                inline_citations=[]
            ))
            return sections

        # Create section for each detected section
        for sect in structure.sections:
            section_text = self._get_section_text(
                extracted["pages"],
                sect["start_page"],
                sect.get("end_page", extracted["page_count"])
            )

            sections.append(ParsedPDFSection(
                section_id=self._slugify(sect["title"]),
                title=sect["title"],
                level=sect["level"],
                start_page=sect["start_page"],
                end_page=sect.get("end_page", extracted["page_count"]),
                content_markdown=self._text_to_markdown(section_text),
                content_plain=section_text,
                word_count=len(section_text.split()),
                has_tables=False,
                has_figures=False,
                inline_citations=self._find_inline_citations(section_text)
            ))

        return sections

    def _get_section_text(self, pages: List, start_page: int, end_page: int) -> str:
        """Extract text for a section by page range."""
        text_parts = []
        for page in pages:
            if start_page <= page.page_number <= end_page:
                text_parts.append(page.text)
        return "\n\n".join(text_parts)

    def _text_to_markdown(self, text: str) -> str:
        """Convert plain text to markdown with basic formatting."""
        lines = text.split('\n')
        md_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                md_lines.append("")
                continue

            # Detect bullet points
            if re.match(r'^[•\-\*]\s+', line):
                md_lines.append(line)
            # Detect numbered lists
            elif re.match(r'^\d+[\.\)]\s+', line):
                md_lines.append(line)
            # Detect potential headings (ALL CAPS, short)
            elif line.isupper() and len(line) < 80:
                md_lines.append(f"\n## {line.title()}\n")
            else:
                md_lines.append(line)

        return "\n".join(md_lines)

    def _clean_markdown_citations(
        self,
        text: str,
        citations: List[Dict[str, Any]]
    ) -> str:
        """
        Clean up markdown text by:
        1. Converting inline citation refs (e.g., "text.10 11 12" -> "text.[^10][^11][^12]")
        2. Removing footnote definition lines from body text

        Args:
            text: Raw markdown text
            citations: List of extracted citations

        Returns:
            Cleaned markdown with proper citation format
        """
        # Get set of known citation ref numbers (as strings)
        known_refs = set()
        for c in citations:
            ref = c.get("original_ref", "")
            if ref:
                known_refs.add(str(ref))

        lines = text.split('\n')
        cleaned_lines = []
        in_footnote_block = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip empty lines in footnote blocks
            if in_footnote_block and not stripped:
                # Check if next non-empty line is still footnotes
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_stripped = lines[j].strip()
                    if next_stripped:
                        # Still in footnotes if next line starts with number+Author pattern
                        if re.match(r'^\d{1,3}[A-Z][a-z]', next_stripped):
                            continue  # Skip this empty line
                        else:
                            in_footnote_block = False
                        break
                if in_footnote_block:
                    continue

            # Detect footnote definition lines: "10Martens CR, et al..." or "1U.S. Food..."
            # Pattern: 1-3 digit number immediately followed by capital letter (no space)
            # Handles: "1U.S. Food..." or "10Martens CR..." or "2Alliance for..."
            footnote_def_match = re.match(r'^(\d{1,3})([A-Z])', stripped)
            if footnote_def_match:
                ref_num = footnote_def_match.group(1)
                rest_of_line = stripped[len(ref_num):]  # Everything after the ref number

                # Verify it's actually a footnote by checking for citation-like content
                is_footnote = (
                    ref_num in known_refs or
                    re.search(r'\d{4}', rest_of_line) or  # Contains year
                    re.search(r'et al\.?', rest_of_line, re.IGNORECASE) or
                    re.search(r'(journal|nature|science|cell|lancet|nejm)', rest_of_line, re.IGNORECASE) or
                    re.search(r'(report|press|company|inc\.|corp\.|llc|fda|administration)', rest_of_line, re.IGNORECASE) or
                    re.search(r'(https?://|www\.)', rest_of_line, re.IGNORECASE) or
                    re.search(r'U\.S\.|FDA|NIH|WHO|CDC', rest_of_line) or  # Government agencies
                    re.search(r'"[^"]+,"', rest_of_line)  # Quoted title pattern
                )

                if is_footnote:
                    in_footnote_block = True
                    continue  # Skip footnote definition line

            # Skip continuation lines of footnotes (lines that don't start with new content patterns)
            if in_footnote_block:
                # Check if this is a continuation of footnote or new body content
                # New body content typically: starts with capital letter word followed by lowercase
                # and is longer than typical short footnote continuations
                if stripped and not re.match(r'^[A-Z][a-z]+\s+[a-z]', stripped):
                    # Still in footnote continuation
                    continue
                elif stripped and len(stripped) > 60 and re.match(r'^[A-Z][a-z]+\s+[a-z]', stripped):
                    # Looks like new body paragraph - exit footnote block
                    in_footnote_block = False
                elif stripped and re.match(r'^\d{1,3}[A-Z]', stripped):
                    # Another footnote definition
                    continue
                elif not stripped:
                    continue

            # Skip standalone page numbers (just a number alone on a line)
            if re.match(r'^\d{1,3}$', stripped):
                continue

            # Convert inline citation refs at end of sentences
            # Pattern: sentence ending punctuation followed by space-separated numbers
            # "tion.10 11 12" -> "tion.[^10][^11][^12]"
            # BUT NOT decimal numbers like "1.5 billion" or "$500.00"

            def replace_end_of_sentence_refs(match):
                """Replace citation refs at end of sentences."""
                before = match.group(1) or ""  # Character before punct (for decimal check)
                punct = match.group(2)  # . or , or ; or :
                numbers_str = match.group(3)
                after = match.string[match.end():match.end()+20] if match.end() < len(match.string) else ""

                # Extract all numbers
                ref_nums = re.findall(r'\d+', numbers_str)

                # Check if this looks like a decimal number (digit before period)
                if before and before.isdigit() and punct == '.':
                    # Check for monetary/unit context that suggests decimal
                    # Look for units like "billion", "million", "%", etc. after
                    if re.match(r'\s*(billion|million|thousand|percent|%|kg|mg|ml|mm|cm|m\b)', after, re.IGNORECASE):
                        return match.group(0)  # It's a decimal with units

                    # Single digit after period is likely decimal if not followed by capital
                    if len(ref_nums) == 1 and len(ref_nums[0]) == 1:
                        # Single digit - likely decimal unless followed by sentence start
                        if not re.match(r'\s*[A-Z]', after):
                            return match.group(0)

                    # If number before period is 1-2 digits (like $1.5, 2.5), likely decimal
                    # unless followed by multiple numbers (citation cluster)
                    if len(ref_nums) == 1 and int(ref_nums[0]) < 10:
                        return match.group(0)  # Single small number after decimal - keep as is

                # Only convert numbers that are known citation refs
                valid_refs = [n for n in ref_nums if n in known_refs]

                if valid_refs:
                    # Format as ". [^n] [^m] [^o] " with:
                    # - one space after punctuation
                    # - one space between refs
                    # - one space after last ref (for following text)
                    refs_formatted = ' '.join(f'[^{n}]' for n in valid_refs)
                    return (before or '') + punct + ' ' + refs_formatted + ' '
                else:
                    return match.group(0)  # Return unchanged

            # Match: optional preceding char + punctuation + numbers (space-separated)
            # Look for patterns like ".10 11 12" or ".10" at end of text segments
            # The (.) before punctuation helps detect decimal numbers
            line = re.sub(
                r'(.)?([.,:;])(\d{1,3}(?:\s+\d{1,3})*)\s*(?=\s|$|[A-Z]|\n)',
                replace_end_of_sentence_refs,
                line
            )

            # Also handle refs after closing parens: ")10 11"
            def replace_after_paren(match):
                paren = match.group(1)
                numbers_str = match.group(2)
                ref_nums = re.findall(r'\d+', numbers_str)
                valid_refs = [n for n in ref_nums if n in known_refs]
                if valid_refs:
                    # Format with space after paren, between refs, and after last ref
                    refs_formatted = ' '.join(f'[^{n}]' for n in valid_refs)
                    return paren + ' ' + refs_formatted + ' '
                return match.group(0)

            line = re.sub(
                r'(\))(\d{1,3}(?:\s+\d{1,3})*)\s*(?=\s|$|[A-Z]|\n)',
                replace_after_paren,
                line
            )

            cleaned_lines.append(line)

        # Remove excessive blank lines
        result = '\n'.join(cleaned_lines)
        result = re.sub(r'\n{4,}', '\n\n\n', result)

        return result

    def _find_inline_citations(self, text: str) -> List[str]:
        """Find inline citation references in text."""
        refs = []

        # Bracketed: [1], [2,3]
        for match in re.finditer(r'\[(\d+(?:,\s*\d+)*)\]', text):
            refs.extend(re.findall(r'\d+', match.group(1)))

        # Superscript
        superscript_map = {
            '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
            '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
        }
        for match in re.finditer(r'[⁰¹²³⁴⁵⁶⁷⁸⁹]+', text):
            ref = ''.join(superscript_map.get(c, c) for c in match.group(0))
            refs.append(ref)

        return list(set(refs))

    def _format_tables(self, raw_tables: List[Dict]) -> List[ParsedTable]:
        """Format extracted tables."""
        tables = []

        for table in raw_tables:
            md_parts = []
            headers = table.get("headers", [])
            rows = table.get("rows", [])

            if headers:
                md_parts.append("| " + " | ".join(str(h) for h in headers) + " |")
                md_parts.append("| " + " | ".join("---" for _ in headers) + " |")

            for row in rows:
                md_parts.append("| " + " | ".join(str(cell) for cell in row) + " |")

            tables.append(ParsedTable(
                table_id=table.get("table_id", f"table-{len(tables)+1}"),
                page=table.get("page", 0),
                caption=None,
                headers=headers,
                rows=rows,
                markdown="\n".join(md_parts)
            ))

        return tables

    def _build_full_markdown(
        self,
        extracted: Dict,
        sections: List[ParsedPDFSection],
        citations: List
    ) -> str:
        """Build complete markdown document with cleaned citations."""
        parts = []

        # Title
        title = extracted["structure"].title or extracted["metadata"].get("title") or "Parsed Document"
        parts.append(f"# {title}\n")

        # Metadata block
        meta = extracted["metadata"]
        if meta.get("author"):
            parts.append(f"**Author:** {meta['author']}")
        if meta.get("created_date"):
            parts.append(f"**Date:** {meta['created_date']}")
        parts.append(f"**Pages:** {extracted['page_count']}")
        parts.append("")

        # Sections - clean each section's content
        if len(sections) == 1 and sections[0]["section_id"] == "full-document":
            content = sections[0]["content_markdown"]
            cleaned = self._clean_markdown_citations(content, citations)
            parts.append(cleaned)
        else:
            for section in sections:
                level = "#" * (section["level"] + 1)
                parts.append(f"\n{level} {section['title']}\n")
                content = section["content_markdown"]
                cleaned = self._clean_markdown_citations(content, citations)
                parts.append(cleaned)

        # Citations block at end
        if citations:
            parts.append("\n\n---\n")
            parts.append("## References\n")
            for citation in citations:
                parts.append(citation.get("our_format", ""))
                parts.append("")  # Blank line between citations

        return "\n".join(parts)

    def _build_citations_block(self, citations: List) -> str:
        """Build standalone citations block in our format."""
        lines = []
        for citation in citations:
            if citation.get("our_format"):
                lines.append(citation["our_format"])
        return "\n\n".join(lines)

    def _calculate_confidence(self, extracted: Dict, citations: List) -> float:
        """Calculate overall scraping confidence score."""
        confidence = 0.5

        if extracted["is_image_based"]:
            confidence -= 0.2

        if extracted["structure"].sections:
            confidence += 0.1
        if extracted["structure"].references_start_page:
            confidence += 0.1

        if citations:
            avg_confidence = sum(c.get("confidence", 0.5) for c in citations) / len(citations)
            confidence += 0.1 * avg_confidence

        meta = extracted["metadata"]
        if meta.get("title"):
            confidence += 0.05
        if meta.get("author"):
            confidence += 0.05

        return min(1.0, max(0.0, confidence))

    def _save_outputs(self, output_dir: Path, data: ParsedPDFData):
        """Save all output files."""
        # Save full markdown
        md_path = output_dir / "content.md"
        md_path.write_text(data["full_markdown"])

        # Save citations JSON
        citations_path = output_dir / "citations.json"
        citations_data = {
            "pdf_source": data["original_filename"],
            "extraction_date": datetime.now().isoformat(),
            "citation_format_detected": data["citation_format_detected"],
            "citations": data["citations"],
            "unmatched_refs": data.get("unmatched_refs", [])
        }
        citations_path.write_text(json.dumps(citations_data, indent=2, default=str))

        # Save citations as markdown
        if data.get("citations_markdown"):
            citations_md_path = output_dir / "citations.md"
            citations_md_path.write_text(data["citations_markdown"])

        # Save metadata
        metadata_path = output_dir / "metadata.json"
        metadata = {
            "original_filename": data["original_filename"],
            "source_path": data["source_path"],
            "pdf_metadata": dict(data["pdf_metadata"]) if data.get("pdf_metadata") else {},
            "parsing_stats": dict(data["parsing_stats"]) if data.get("parsing_stats") else {},
            "structure": {
                "sections": [
                    {
                        "title": s["title"],
                        "level": s["level"],
                        "start_page": s["start_page"],
                        "end_page": s["end_page"]
                    }
                    for s in data["sections"]
                ]
            }
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, default=str))

        # Save full data as JSON
        full_data_path = output_dir / "content.json"
        # Convert TypedDicts to regular dicts for JSON serialization
        data_dict = dict(data)
        data_dict["sections"] = [dict(s) for s in data_dict.get("sections", [])]
        data_dict["tables"] = [dict(t) for t in data_dict.get("tables", [])]
        data_dict["citations"] = [dict(c) for c in data_dict.get("citations", [])]
        if data_dict.get("pdf_metadata"):
            data_dict["pdf_metadata"] = dict(data_dict["pdf_metadata"])
        if data_dict.get("parsing_stats"):
            data_dict["parsing_stats"] = dict(data_dict["parsing_stats"])
        full_data_path.write_text(json.dumps(data_dict, indent=2, default=str))

        # Save individual sections if multiple
        if len(data["sections"]) > 1:
            sections_dir = output_dir / "sections"
            sections_dir.mkdir(exist_ok=True)

            for i, section in enumerate(data["sections"], 1):
                section_path = sections_dir / f"{i:02d}-{section['section_id']}.md"
                # Apply citation cleaning to section content
                cleaned_content = self._clean_markdown_citations(
                    section['content_markdown'],
                    data.get("citations", [])
                )
                section_content = f"# {section['title']}\n\n{cleaned_content}"
                section_path.write_text(section_content)


def scrape_research_pdf(
    pdf_path: str,
    output_dir: Optional[str] = None,
    extract_tables: bool = True
) -> PDFParseResult:
    """
    Convenience function to scrape a research PDF.

    Args:
        pdf_path: Path to PDF file
        output_dir: Optional output directory
        extract_tables: Whether to extract tables

    Returns:
        PDFParseResult with scraped data
    """
    scraper = ResearchPDFScraper(extract_tables=extract_tables)
    return scraper.scrape(pdf_path, output_dir)

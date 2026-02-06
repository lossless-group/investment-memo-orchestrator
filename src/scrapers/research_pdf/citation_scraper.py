"""
Citation scraping and format conversion.

Detects and parses various citation formats found in research PDFs,
converting them to our standard Obsidian-style format.

Our standard format:
[^1]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD
"""

import re
from typing import List, Dict, Any, Optional, Tuple

from ...schemas.research_pdf import ParsedCitation, CitationFormat


# Month mappings for date parsing
MONTH_MAP = {
    'jan': '01', 'january': '01',
    'feb': '02', 'february': '02',
    'mar': '03', 'march': '03',
    'apr': '04', 'april': '04',
    'may': '05',
    'jun': '06', 'june': '06',
    'jul': '07', 'july': '07',
    'aug': '08', 'august': '08',
    'sep': '09', 'sept': '09', 'september': '09',
    'oct': '10', 'october': '10',
    'nov': '11', 'november': '11',
    'dec': '12', 'december': '12',
}

MONTH_ABBREV = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
    '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
    '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}


class CitationScraper:
    """
    Scrapes citations from research PDFs and converts to our standard format.
    """

    def detect_citation_format(self, text: str, footnote_text: str = "") -> CitationFormat:
        """
        Detect the citation format used in a document.

        Args:
            text: Main document text
            footnote_text: Text from footnote/endnote sections

        Returns:
            Detected citation format
        """
        formats_found = []

        # Check for bracketed references [1], [2], [1,2,3]
        if re.search(r'\[\d+(?:,\s*\d+)*\]', text):
            formats_found.append("bracketed")

        # Check for LaTeX-style inline footnotes: number immediately followed by capital letter
        # Pattern: "1U.S. Food" or "2Alliance" at start of line
        latex_footnote_count = len(re.findall(r'(?:^|\n)\d{1,3}[A-Z][a-z]', text))
        if latex_footnote_count >= 3:  # At least 3 to confirm pattern
            formats_found.append("footnotes")

        # Check for superscript-style (numbered refs in footnote area)
        if re.search(r'(?:^|\n)\s*\d+\.\s+[A-Z]', footnote_text):
            formats_found.append("endnotes")

        # Check for footnotes (superscript unicode numbers)
        if re.search(r'(?:^|\n)\s*[¹²³⁴⁵⁶⁷⁸⁹⁰]+\s+', footnote_text):
            formats_found.append("footnotes")

        # Check for bibliography style (Author, Year)
        if re.search(r'\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)', text):
            formats_found.append("bibliography")

        if len(formats_found) == 0:
            return "unknown"
        elif len(formats_found) == 1:
            return formats_found[0]
        else:
            return "mixed"

    def extract_inline_references(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract inline citation references from text.

        Args:
            text: Document text

        Returns:
            List of dicts with ref number and position
        """
        refs = []

        # Bracketed: [1], [2], [1,2,3], [1-3]
        for match in re.finditer(r'\[(\d+(?:[-,]\s*\d+)*)\]', text):
            ref_text = match.group(1)
            if '-' in ref_text:
                start, end = map(int, ref_text.split('-'))
                for i in range(start, end + 1):
                    refs.append({
                        "ref": str(i),
                        "position": match.start(),
                        "original": match.group(0)
                    })
            else:
                for ref_num in re.findall(r'\d+', ref_text):
                    refs.append({
                        "ref": ref_num,
                        "position": match.start(),
                        "original": match.group(0)
                    })

        # Superscript numbers
        superscript_map = {
            '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
            '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'
        }
        for match in re.finditer(r'[⁰¹²³⁴⁵⁶⁷⁸⁹]+', text):
            ref_num = ''.join(superscript_map.get(c, c) for c in match.group(0))
            refs.append({
                "ref": ref_num,
                "position": match.start(),
                "original": match.group(0)
            })

        return refs

    def parse_reference_section(self, text: str) -> List[Dict[str, str]]:
        """
        Parse a references/bibliography section into individual citations.

        Args:
            text: Text from references section

        Returns:
            List of dicts with ref number and raw citation text
        """
        citations = []

        # Pattern 1: Numbered references (1. Citation text or [1] Citation text)
        numbered_pattern = r'(?:^|\n)\s*(?:\[?(\d+)\]?\.?\s+)(.+?)(?=(?:\n\s*\[?\d+\]?\.?\s+)|\Z)'
        for match in re.finditer(numbered_pattern, text, re.DOTALL):
            citations.append({
                "ref": match.group(1),
                "text": match.group(2).strip().replace('\n', ' ')
            })

        # If no numbered refs found, try bullet/dash format
        if not citations:
            bullet_pattern = r'(?:^|\n)\s*[-•]\s+(.+?)(?=(?:\n\s*[-•]\s+)|\Z)'
            for i, match in enumerate(re.finditer(bullet_pattern, text, re.DOTALL), 1):
                citations.append({
                    "ref": str(i),
                    "text": match.group(1).strip().replace('\n', ' ')
                })

        return citations

    def parse_citation_text(self, raw_text: str, ref_num: str = "1") -> ParsedCitation:
        """
        Parse a single citation text into structured components.

        Args:
            raw_text: Raw citation text from PDF
            ref_num: Reference number to assign

        Returns:
            ParsedCitation with parsed components and our format
        """
        text = raw_text.strip()
        parsed = ParsedCitation(
            original_ref=ref_num,
            original_text=text,
            title="",
            author=None,
            date=None,
            date_display=None,
            url=None,
            publication=None,
            citation_type="other",
            our_format="",
            page_references=[],
            location_in_pdf="unknown",
            confidence=0.5,
            parsing_notes=[]
        )

        # Extract URL if present
        url_match = re.search(r'https?://[^\s\)]+', text)
        if url_match:
            parsed["url"] = url_match.group(0).rstrip('.,;')
            parsed["confidence"] += 0.1

        # Extract date
        date_str, date_display = self._extract_date(text)
        if date_str:
            parsed["date"] = date_str
            parsed["date_display"] = date_display
            parsed["confidence"] += 0.15

        # Extract title
        title = self._extract_title(text)
        if title:
            parsed["title"] = title
            parsed["confidence"] += 0.15
        else:
            parsed["title"] = self._fallback_title(text)
            parsed["parsing_notes"].append("Title extracted via fallback method")

        # Extract author/organization
        author = self._extract_author(text)
        if author:
            parsed["author"] = author
            parsed["confidence"] += 0.1

        # Determine citation type
        parsed["citation_type"] = self._determine_type(text, parsed)

        # Generate our standard format
        parsed["our_format"] = self._format_citation(parsed, ref_num)

        # Cap confidence at 1.0
        parsed["confidence"] = min(1.0, parsed["confidence"])

        return parsed

    def _extract_date(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract date from citation text. Returns (YYYY-MM-DD, display_format)."""

        # Full date: March 15, 2024 or 15 March 2024
        full_date = re.search(
            r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})|([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})',
            text
        )
        if full_date:
            if full_date.group(1):  # 15 March 2024 format
                day, month_str, year = full_date.group(1), full_date.group(2), full_date.group(3)
            else:  # March 15, 2024 format
                month_str, day, year = full_date.group(4), full_date.group(5), full_date.group(6)

            month = MONTH_MAP.get(month_str.lower()[:3])
            if month:
                date_str = f"{year}-{month}-{day.zfill(2)}"
                display = f"{MONTH_ABBREV[month]} {day}"
                return date_str, display

        # Month Year: November 2023 or Nov 2023
        month_year = re.search(r'([A-Za-z]+)\s+(\d{4})', text)
        if month_year:
            month_str, year = month_year.group(1), month_year.group(2)
            month = MONTH_MAP.get(month_str.lower()[:3])
            if month:
                date_str = f"{year}-{month}"
                display = f"{MONTH_ABBREV[month]} {year}"
                return date_str, display

        # Year only: (2024) or , 2024
        year_only = re.search(r'[\(,\s](\d{4})[\),\s]', text)
        if year_only:
            year = year_only.group(1)
            if 1990 <= int(year) <= 2030:
                return year, year

        return None, None

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract title from citation text."""

        # Title in quotes
        quoted = re.search(r'["\']([^"\']{10,})["\']', text)
        if quoted:
            return quoted.group(1).strip()

        # Title before period followed by author/publication
        title_pattern = re.search(r'^([^.]{15,})\.\s+(?:[A-Z][a-z]+|[A-Z]{2,})', text)
        if title_pattern:
            return title_pattern.group(1).strip()

        return None

    def _fallback_title(self, text: str) -> str:
        """Generate fallback title from citation text."""
        text = re.sub(r'https?://[^\s]+', '', text)
        text = re.sub(r'\d{4}', '', text)
        text = text.strip().split('.')[0].strip()

        if len(text) > 100:
            text = text[:100] + "..."

        return text if text else "Untitled Source"

    def _extract_author(self, text: str) -> Optional[str]:
        """Extract author or organization from citation text."""

        # Organization patterns
        org_pattern = re.search(
            r'^([A-Z][A-Za-z\s&]+(?:Inc\.|LLC|Ltd\.|Corp\.|Company|Institute|Association))',
            text
        )
        if org_pattern:
            return org_pattern.group(1).strip().rstrip(',.')

        # Author pattern: Last, First
        author_pattern = re.search(r'^([A-Z][a-z]+(?:,\s*[A-Z]\.?)?)', text)
        if author_pattern:
            return author_pattern.group(1).strip()

        # "by Author" pattern
        by_pattern = re.search(r'by\s+([A-Z][A-Za-z\s]+?)(?:\.|,|\()', text)
        if by_pattern:
            return by_pattern.group(1).strip()

        return None

    def _determine_type(self, text: str, parsed: Dict) -> str:
        """Determine citation type based on content."""
        text_lower = text.lower()

        if parsed.get("url"):
            if any(domain in parsed["url"] for domain in ['github.com', 'gitlab.com']):
                return "code_repository"
            if 'arxiv.org' in parsed.get("url", ""):
                return "preprint"
            return "website"

        if any(word in text_lower for word in ['report', 'analysis', 'research', 'study']):
            return "report"
        if any(word in text_lower for word in ['journal', 'proceedings', 'conference']):
            return "article"
        if any(word in text_lower for word in ['press release', 'announcement']):
            return "press_release"
        if 'book' in text_lower or 'isbn' in text_lower:
            return "book"

        return "other"

    def _format_citation(self, parsed: ParsedCitation, ref_num: str) -> str:
        """
        Format citation in our standard format.

        Format: [^n]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: N/A
        """
        parts = [f"[^{ref_num}]: "]

        # Date display
        if parsed.get("date_display"):
            parts.append(f"{parsed['date_display']}. ")
        elif parsed.get("date"):
            parts.append(f"{parsed['date']}. ")
        else:
            parts.append("N/A. ")

        # Title with optional URL
        title = parsed.get("title", "Untitled")
        if parsed.get("url"):
            parts.append(f"[{title}]({parsed['url']})")
        else:
            parts.append(f"[{title}]()")

        # Published/Updated dates
        pub_date = parsed.get("date", "N/A")
        parts.append(f". Published: {pub_date} | Updated: N/A")

        return "".join(parts)

    def extract_latex_footnotes(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract footnotes from LaTeX-generated PDFs where footnotes are
        embedded inline in the extracted text.

        LaTeX footnotes appear as: "1U.S. Food and Drug Administration..."
        where the number is immediately followed by the citation text.

        Args:
            text: Full document text

        Returns:
            List of dicts with ref number and citation text
        """
        footnotes = []
        seen_refs = set()

        # Pattern for LaTeX footnotes: number at start of line followed by
        # author/organization name (capital letter) - but NOT a page number
        # Examples:
        #   1U.S. Food and Drug Administration, "FDA Approves..."
        #   2Alliance for Regenerative Medicine, "Regenerative..."
        #   3Gene Therapy Manufacturing Cost Analysis...
        #   10Martens CR, et al., "Chronic nicotinamide..."

        # Split into lines and look for footnote patterns
        lines = text.split('\n')

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Match: starts with 1-3 digit number, immediately followed by
            # capital letter (author/org name), and the line is substantial
            match = re.match(r'^(\d{1,3})([A-Z][A-Za-z].*)', line)

            if match:
                ref_num = match.group(1)
                citation_start = match.group(2)

                # Skip if this looks like a page number (just digits on a line)
                # or a section number (like "1. Introduction")
                if len(citation_start) < 10:
                    continue

                # Skip years being mistaken for refs (1990-2030)
                if 1990 <= int(ref_num) <= 2030 and len(ref_num) == 4:
                    continue

                # Skip if we've seen this ref already
                if ref_num in seen_refs:
                    continue

                # Build the full citation text - may span multiple lines
                citation_text = citation_start

                # Look ahead for continuation lines (indented or not starting with number)
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        break
                    # Stop if we hit another footnote
                    if re.match(r'^\d{1,3}[A-Z]', next_line):
                        break
                    # Stop if we hit a page number (single number on line)
                    if re.match(r'^\d+$', next_line):
                        break
                    # Stop if we hit a section header
                    if next_line.isupper() and len(next_line) < 80:
                        break
                    citation_text += " " + next_line

                # Clean up the citation text
                citation_text = re.sub(r'\s+', ' ', citation_text).strip()

                # Only include if it looks like a real citation (has year, quotes, or common words)
                if (re.search(r'\d{4}', citation_text) or
                    '"' in citation_text or
                    any(word in citation_text.lower() for word in
                        ['journal', 'report', 'press', 'release', 'et al', 'company', 'inc'])):

                    footnotes.append({
                        "ref": ref_num,
                        "text": citation_text
                    })
                    seen_refs.add(ref_num)

        return footnotes

    def scrape_citations(
        self,
        main_text: str,
        reference_section: str,
        footnotes: List[Dict[str, Any]] = None
    ) -> List[ParsedCitation]:
        """
        Scrape all citations from a PDF document.

        Args:
            main_text: Main document text
            reference_section: Text from references/bibliography section
            footnotes: List of footnotes with page numbers (from position detection)

        Returns:
            List of ParsedCitation objects
        """
        citations = []
        footnotes = footnotes or []

        # First, try to extract LaTeX-style inline footnotes from the text
        latex_footnotes = self.extract_latex_footnotes(main_text)
        if latex_footnotes:
            for fn in latex_footnotes:
                citation = self.parse_citation_text(fn["text"], fn["ref"])
                citation["location_in_pdf"] = "footnote"
                citations.append(citation)

        # Parse reference section (if no LaTeX footnotes found or as supplement)
        if reference_section and not latex_footnotes:
            refs = self.parse_reference_section(reference_section)
            for ref in refs:
                citation = self.parse_citation_text(ref["text"], ref["ref"])
                citation["location_in_pdf"] = "endnotes"
                citations.append(citation)

        # Parse position-detected footnotes (if no LaTeX footnotes found)
        if not latex_footnotes:
            existing_refs = {c["original_ref"] for c in citations}
            for footnote in footnotes:
                if footnote.get("ref") not in existing_refs:
                    citation = self.parse_citation_text(
                        footnote.get("text", ""),
                        footnote.get("ref", "?")
                    )
                    citation["location_in_pdf"] = "footnote"
                    if footnote.get("page"):
                        citation["page_references"] = [footnote["page"]]
                    citations.append(citation)

        # Sort by reference number
        try:
            citations.sort(key=lambda c: int(c.get("original_ref", "0")))
        except ValueError:
            pass  # Keep original order if refs aren't numeric

        return citations

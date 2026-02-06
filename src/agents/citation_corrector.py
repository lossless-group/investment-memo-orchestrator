"""
Citation Corrector Agent

Runs the research PDF scraper then uses an LLM to autocorrect and improve
the parsed citations. This agent:

1. Runs the scraper to extract citations from a PDF
2. Reviews each citation with Claude to fix parsing errors
3. Identifies missing citations from the document text
4. Outputs corrected citations in our standard format

This is an AGENT (uses LLM for decision-making) not a scraper (deterministic).
"""

import json
import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from anthropic import Anthropic

from ..scrapers.research_pdf import scrape_research_pdf
from ..schemas.research_pdf import ParsedCitation, PDFParseResult


# Initialize Anthropic client
def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    return Anthropic(api_key=api_key)


class CitationCorrectorAgent:
    """
    Agent that scrapes PDFs and uses LLM to correct citation parsing errors.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize the citation corrector agent.

        Args:
            model: Claude model to use for corrections
        """
        self.model = model
        self.client = get_anthropic_client()

    def process_pdf(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a PDF: scrape then correct citations.

        Args:
            pdf_path: Path to PDF file
            output_dir: Output directory for results

        Returns:
            Dict with scrape results and corrected citations
        """
        print(f"Processing PDF: {pdf_path}")

        # Step 1: Run the scraper
        print("\n[1/4] Running scraper...")
        scrape_result = scrape_research_pdf(pdf_path, output_dir)

        if not scrape_result["success"]:
            return {
                "success": False,
                "error": f"Scraper failed: {scrape_result['error']}",
                "scrape_result": scrape_result
            }

        scraped_data = scrape_result["data"]
        original_citations = scraped_data.get("citations", [])
        full_text = scraped_data.get("full_markdown", "")

        print(f"    Scraped {len(original_citations)} citations")

        # Step 2: Correct each citation with LLM
        print("\n[2/4] Correcting citations with LLM...")
        corrected_citations = self._correct_citations(original_citations)
        print(f"    Corrected {len(corrected_citations)} citations")

        # Step 3: Find missing citations
        print("\n[3/4] Finding missing citations...")
        missing_citations = self._find_missing_citations(
            full_text,
            corrected_citations
        )
        if missing_citations:
            print(f"    Found {len(missing_citations)} missing citations")
            corrected_citations.extend(missing_citations)

        # Step 4: Save corrected output
        print("\n[4/4] Saving corrected output...")
        output_path = Path(scrape_result["output_dir"])
        self._save_corrected_output(output_path, corrected_citations, scraped_data)

        # Sort by ref number
        try:
            corrected_citations.sort(key=lambda c: int(c.get("original_ref", "0")))
        except ValueError:
            pass

        return {
            "success": True,
            "pdf_path": pdf_path,
            "output_dir": str(output_path),
            "original_citation_count": len(original_citations),
            "corrected_citation_count": len(corrected_citations),
            "missing_found": len(missing_citations) if missing_citations else 0,
            "citations": corrected_citations,
            "scrape_result": scrape_result
        }

    def _correct_citations(
        self,
        citations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to correct parsing errors in each citation.

        Args:
            citations: List of scraped citations

        Returns:
            List of corrected citations
        """
        if not citations:
            return []

        corrected = []

        # Process in batches of 10 for efficiency
        batch_size = 10
        for i in range(0, len(citations), batch_size):
            batch = citations[i:i + batch_size]
            corrected_batch = self._correct_citation_batch(batch)
            corrected.extend(corrected_batch)
            print(f"    Processed {min(i + batch_size, len(citations))}/{len(citations)}")

        return corrected

    def _correct_citation_batch(
        self,
        citations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Correct a batch of citations using LLM."""

        # Build prompt with citations to correct
        citations_text = ""
        for c in citations:
            citations_text += f"""
---
Reference #{c.get('original_ref', '?')}
Original text: {c.get('original_text', '')}
Current parsed title: {c.get('title', '')}
Current parsed author: {c.get('author', '')}
Current parsed date: {c.get('date', '')}
Current parsed URL: {c.get('url', '')}
---
"""

        prompt = f"""You are a citation parser corrector. Review these citations extracted from a PDF and fix any parsing errors.

For each citation, extract:
1. **title**: The actual title of the work (in quotes in the original, or the main subject)
2. **author**: Author name(s) or organization
3. **date**: Publication date in YYYY-MM-DD format (or YYYY-MM or YYYY if day/month unknown)
4. **date_display**: Human-readable date (e.g., "Dec 8, 2023" or "2023")
5. **publication**: Journal, report series, or publisher name
6. **url**: URL if present
7. **citation_type**: One of: article, report, press_release, book, website, preprint, other

Citations to correct:
{citations_text}

Return a JSON array with corrected citations. Each object should have:
- ref: the reference number (string)
- title: corrected title (full title, not truncated)
- author: corrected author/organization
- date: date in YYYY-MM-DD format (or null if unknown)
- date_display: human-readable date (or null)
- publication: publication name (or null)
- url: URL (or null)
- citation_type: type of citation
- original_text: preserve the original text

Return ONLY the JSON array, no other text."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Extract JSON from response
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
                response_text = re.sub(r'\n?```$', '', response_text)

            corrected_data = json.loads(response_text)

            # Merge corrections back into original citations
            corrected_citations = []
            ref_to_correction = {str(c.get("ref", "")): c for c in corrected_data}

            for original in citations:
                ref = str(original.get("original_ref", ""))
                correction = ref_to_correction.get(ref, {})

                corrected = dict(original)  # Start with original
                corrected["title"] = correction.get("title") or original.get("title", "")
                corrected["author"] = correction.get("author") or original.get("author")
                corrected["date"] = correction.get("date") or original.get("date")
                corrected["date_display"] = correction.get("date_display") or original.get("date_display")
                corrected["publication"] = correction.get("publication") or original.get("publication")
                corrected["url"] = correction.get("url") or original.get("url")
                corrected["citation_type"] = correction.get("citation_type") or original.get("citation_type", "other")

                # Regenerate our_format with corrected data
                corrected["our_format"] = self._format_citation(corrected)
                corrected["corrected"] = True

                corrected_citations.append(corrected)

            return corrected_citations

        except Exception as e:
            print(f"    Warning: LLM correction failed for batch: {e}")
            # Return original citations if LLM fails
            return citations

    def _find_missing_citations(
        self,
        full_text: str,
        existing_citations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find citations that were missed by the scraper.

        Args:
            full_text: Full document text
            existing_citations: Already extracted citations

        Returns:
            List of newly found citations
        """
        existing_refs = {str(c.get("original_ref", "")) for c in existing_citations}

        # Find all potential footnote references in the text
        # Look for patterns like ".1 " or ")1 " followed by author names
        potential_refs = set()

        # Pattern: number at start of line followed by capital letter (LaTeX footnotes)
        for match in re.finditer(r'(?:^|\n)(\d{1,3})([A-Z][a-z])', full_text):
            ref = match.group(1)
            if ref not in existing_refs and 1 <= int(ref) <= 200:
                potential_refs.add(ref)

        if not potential_refs:
            return []

        # Use LLM to extract the missing citations
        missing_refs = sorted(potential_refs, key=int)[:20]  # Limit to 20

        prompt = f"""In a PDF document, I found these footnote reference numbers that weren't extracted: {', '.join(missing_refs)}

Here are snippets from the document where these references appear. Find the full citation text for each missing reference.

Document text (first 30000 chars):
{full_text[:30000]}

For each missing reference number, extract the full citation if you can find it.
Return a JSON array with objects containing:
- ref: the reference number
- original_text: the full citation text
- title: extracted title
- author: extracted author
- date: date in YYYY-MM-DD format (or null)
- date_display: human-readable date
- citation_type: type of citation

Return ONLY the JSON array. If you can't find a citation for a reference, don't include it."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
                response_text = re.sub(r'\n?```$', '', response_text)

            found_citations = json.loads(response_text)

            # Format as ParsedCitation
            missing = []
            for c in found_citations:
                citation = {
                    "original_ref": str(c.get("ref", "")),
                    "original_text": c.get("original_text", ""),
                    "title": c.get("title", ""),
                    "author": c.get("author"),
                    "date": c.get("date"),
                    "date_display": c.get("date_display"),
                    "url": c.get("url"),
                    "publication": c.get("publication"),
                    "citation_type": c.get("citation_type", "other"),
                    "page_references": [],
                    "location_in_pdf": "footnote",
                    "confidence": 0.7,
                    "parsing_notes": ["Recovered by LLM from document text"],
                    "corrected": True,
                    "recovered": True
                }
                citation["our_format"] = self._format_citation(citation)
                missing.append(citation)

            return missing

        except Exception as e:
            print(f"    Warning: Finding missing citations failed: {e}")
            return []

    def _format_citation(self, citation: Dict[str, Any]) -> str:
        """Format citation in our standard format."""
        ref = citation.get("original_ref", "?")
        parts = [f"[^{ref}]: "]

        # Date
        if citation.get("date_display"):
            parts.append(f"{citation['date_display']}. ")
        elif citation.get("date"):
            parts.append(f"{citation['date']}. ")
        else:
            parts.append("N/A. ")

        # Title with URL
        title = citation.get("title", "Untitled")
        url = citation.get("url", "")
        parts.append(f"[{title}]({url})")

        # Published date
        pub_date = citation.get("date") or "N/A"
        parts.append(f". Published: {pub_date} | Updated: N/A")

        return "".join(parts)

    def _save_corrected_output(
        self,
        output_dir: Path,
        citations: List[Dict[str, Any]],
        scraped_data: Dict[str, Any]
    ):
        """Save corrected citations to files."""

        # Save corrected citations JSON
        corrected_path = output_dir / "citations-corrected.json"
        corrected_data = {
            "pdf_source": scraped_data.get("original_filename", ""),
            "correction_date": datetime.now().isoformat(),
            "original_count": len(scraped_data.get("citations", [])),
            "corrected_count": len(citations),
            "citations": citations
        }
        corrected_path.write_text(json.dumps(corrected_data, indent=2, default=str))

        # Save corrected citations markdown
        md_path = output_dir / "citations-corrected.md"
        md_lines = ["# Corrected Citations\n"]
        for c in citations:
            md_lines.append(c.get("our_format", ""))
            md_lines.append("")
        md_path.write_text("\n".join(md_lines))

        print(f"    Saved: {corrected_path}")
        print(f"    Saved: {md_path}")


def correct_pdf_citations(
    pdf_path: str,
    output_dir: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514"
) -> Dict[str, Any]:
    """
    Convenience function to scrape and correct citations from a PDF.

    Args:
        pdf_path: Path to PDF file
        output_dir: Output directory
        model: Claude model to use

    Returns:
        Dict with results
    """
    agent = CitationCorrectorAgent(model=model)
    return agent.process_pdf(pdf_path, output_dir)

#!/usr/bin/env python3
"""
CLI tool for scraping research PDFs and correcting citations with LLM.

This runs the scraper first, then uses Claude to:
1. Fix parsing errors in extracted citations
2. Find and recover missing citations
3. Output corrected citations in our standard format

Usage:
    python cli/correct_pdf_citations.py path/to/research.pdf
    python cli/correct_pdf_citations.py path/to/research.pdf --output output/parsed/
    python cli/correct_pdf_citations.py path/to/research.pdf --model claude-sonnet-4-20250514
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.citation_corrector import CitationCorrectorAgent


def main():
    parser = argparse.ArgumentParser(
        description="Scrape PDFs and correct citations with LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Process a single PDF
    python cli/correct_pdf_citations.py data/research/McKinsey-Report.pdf

    # Specify output directory
    python cli/correct_pdf_citations.py report.pdf --output output/parsed/

    # Use a specific model
    python cli/correct_pdf_citations.py report.pdf --model claude-sonnet-4-20250514

Output:
    In addition to standard scraper output, creates:
    - citations-corrected.json   # Corrected citations with full metadata
    - citations-corrected.md     # Citations in our standard format
        """
    )

    parser.add_argument(
        "pdf_path",
        help="Path to PDF file to process"
    )

    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        help="Output directory (default: {pdf_dir}/parsed/)"
    )

    parser.add_argument(
        "--model",
        default="claude-sonnet-4-20250514",
        help="Claude model to use (default: claude-sonnet-4-20250514)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Validate PDF exists
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {args.pdf_path}")
        return 1

    if not pdf_path.suffix.lower() == ".pdf":
        print(f"Error: File is not a PDF: {args.pdf_path}")
        return 1

    print(f"{'='*60}")
    print(f"Citation Corrector Agent")
    print(f"{'='*60}")
    print(f"PDF: {pdf_path.name}")
    print(f"Model: {args.model}")
    print()

    # Run the agent
    try:
        agent = CitationCorrectorAgent(model=args.model)
        result = agent.process_pdf(str(pdf_path), args.output_dir)
    except Exception as e:
        print(f"\nError: {e}")
        return 1

    # Print results
    print(f"\n{'='*60}")
    print("Results")
    print(f"{'='*60}")

    if result["success"]:
        print(f"Status: Success")
        print(f"Output: {result['output_dir']}")
        print(f"Original citations: {result['original_citation_count']}")
        print(f"Corrected citations: {result['corrected_citation_count']}")
        print(f"Missing recovered: {result['missing_found']}")

        print(f"\nFiles created:")
        print(f"  - citations-corrected.json")
        print(f"  - citations-corrected.md")

        # Show sample of corrected citations
        citations = result.get("citations", [])
        if citations:
            print(f"\nSample corrected citations:")
            for c in citations[:3]:
                print(f"  [{c.get('original_ref')}] {c.get('title', '')[:60]}...")
                if c.get("date"):
                    print(f"      Date: {c.get('date')}")
                if c.get("author"):
                    print(f"      Author: {c.get('author')}")

        return 0
    else:
        print(f"Status: Failed")
        print(f"Error: {result.get('error', 'Unknown error')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

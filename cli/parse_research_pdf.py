#!/usr/bin/env python3
"""
CLI tool for scraping research PDFs into markdown with citations.

Converts market research PDFs (McKinsey, CB Insights, PitchBook, Gartner, etc.)
into well-structured markdown with properly formatted citations.

Usage:
    python cli/parse_research_pdf.py path/to/research.pdf
    python cli/parse_research_pdf.py path/to/research.pdf --output output/parsed/
    python cli/parse_research_pdf.py path/to/*.pdf --output output/parsed/

Output:
    Creates a directory with:
    - content.md         Full markdown content
    - content.json       Structured JSON representation
    - citations.json     Extracted citations
    - citations.md       Citations in our standard format
    - metadata.json      PDF metadata and parsing stats
    - sections/          Individual sections (if detected)
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.scrapers.research_pdf import scrape_research_pdf, ResearchPDFScraper


def main():
    parser = argparse.ArgumentParser(
        description="Scrape research PDFs into markdown with citations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Scrape a single PDF (output to same directory)
    python cli/parse_research_pdf.py data/research/McKinsey-Report.pdf

    # Scrape to specific output directory
    python cli/parse_research_pdf.py report.pdf --output output/parsed/

    # Scrape multiple PDFs
    python cli/parse_research_pdf.py data/research/*.pdf --output output/parsed/

    # Skip table extraction (faster)
    python cli/parse_research_pdf.py report.pdf --no-tables

Output Structure:
    output/parsed/{pdf-name}/
    ├── content.md         # Full markdown content
    ├── content.json       # Structured JSON
    ├── citations.json     # Extracted citations
    ├── citations.md       # Citations in our format
    ├── metadata.json      # PDF metadata
    └── sections/          # Individual sections
        """
    )

    parser.add_argument(
        "pdf_paths",
        nargs="+",
        help="Path(s) to PDF file(s) to scrape"
    )

    parser.add_argument(
        "-o", "--output",
        dest="output_dir",
        help="Output directory (default: {pdf_dir}/parsed/)"
    )

    parser.add_argument(
        "--no-tables",
        action="store_true",
        help="Skip table extraction (faster processing)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Process each PDF
    results = []
    for pdf_path in args.pdf_paths:
        path = Path(pdf_path)

        if not path.exists():
            print(f"Error: File not found: {pdf_path}")
            continue

        if not path.suffix.lower() == ".pdf":
            print(f"Warning: Skipping non-PDF file: {pdf_path}")
            continue

        print(f"\n{'='*60}")
        print(f"Processing: {path.name}")
        print(f"{'='*60}")

        result = scrape_research_pdf(
            pdf_path=str(path),
            output_dir=args.output_dir,
            extract_tables=not args.no_tables
        )

        results.append(result)

        if result["success"]:
            print(f"\nSuccess!")
            print(f"  Output: {result['output_dir']}")
            if result["data"]:
                data = result["data"]
                print(f"  Pages: {data['pdf_metadata'].get('page_count', 'N/A')}")
                print(f"  Citations: {len(data.get('citations', []))}")
                print(f"  Sections: {len(data.get('sections', []))}")
                print(f"  Tables: {len(data.get('tables', []))}")
                print(f"  Confidence: {data.get('parsing_confidence', 0):.0%}")

            if result["warnings"]:
                print(f"  Warnings:")
                for warning in result["warnings"]:
                    print(f"    - {warning}")
        else:
            print(f"\nFailed: {result['error']}")

    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    success_count = sum(1 for r in results if r["success"])
    print(f"  Processed: {len(results)} PDF(s)")
    print(f"  Succeeded: {success_count}")
    print(f"  Failed: {len(results) - success_count}")

    if success_count > 0:
        total_citations = sum(
            len(r["data"].get("citations", []))
            for r in results
            if r["success"] and r["data"]
        )
        print(f"  Total citations extracted: {total_citations}")

    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

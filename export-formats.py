#!/usr/bin/env python3
"""
Multi-format memo exporter that preserves citations.

Exports investment memos to multiple formats optimized for citation preservation.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

try:
    import pypandoc
except ImportError:
    print("Error: pypandoc is not installed.")
    print("Please install it with: uv pip install pypandoc")
    sys.exit(1)


def ensure_pandoc_installed():
    """Check if pandoc is installed."""
    try:
        version = pypandoc.get_pandoc_version()
        print(f"Using pandoc version {version}")
    except OSError:
        print("Pandoc not found. Downloading...")
        try:
            pypandoc.download_pandoc()
            version = pypandoc.get_pandoc_version()
            print(f"Pandoc {version} downloaded successfully!")
        except Exception as e:
            print(f"Error downloading pandoc: {e}")
            sys.exit(1)


def convert_to_format(
    input_path: Path,
    output_path: Path,
    format: str,
    extra_args: Optional[List[str]] = None
) -> Path:
    """Convert markdown to specified format with citation preservation."""

    # Format-specific pandoc arguments for better citation handling
    format_args = {
        'docx': [],  # Word format
        'pdf': ['--pdf-engine=wkhtmltopdf'],  # PDF with wkhtmltopdf (more portable)
        'html': ['--standalone', '--embed-resources'],  # Standalone HTML
        'odt': [],  # OpenDocument
    }

    args = format_args.get(format, [])
    if extra_args:
        args.extend(extra_args)

    try:
        pypandoc.convert_file(
            str(input_path),
            format,
            outputfile=str(output_path),
            extra_args=args if args else None
        )
        return output_path
    except Exception as e:
        raise RuntimeError(f"Error converting to {format}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Export investment memos with citation preservation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s memo.md                           # Export to all formats
  %(prog)s memo.md --format pdf              # Export to PDF only
  %(prog)s memo.md --format docx,pdf,html    # Multiple formats
  %(prog)s memo.md -o exports/               # Custom output directory
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        help='Input markdown file'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output directory (default: same as input)'
    )

    parser.add_argument(
        '--format',
        default='docx,pdf,html',
        help='Output formats (comma-separated): docx, pdf, html, odt (default: docx,pdf,html)'
    )

    args = parser.parse_args()

    # Check pandoc
    ensure_pandoc_installed()

    # Validate input
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)

    # Determine output directory
    output_dir = args.output if args.output else args.input.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse formats
    formats = [f.strip() for f in args.format.split(',')]
    valid_formats = ['docx', 'pdf', 'html', 'odt']

    for fmt in formats:
        if fmt not in valid_formats:
            print(f"Warning: Unknown format '{fmt}', skipping")
            formats.remove(fmt)

    if not formats:
        print("Error: No valid formats specified")
        sys.exit(1)

    # Convert to each format
    base_name = args.input.stem
    results = []

    for fmt in formats:
        output_file = output_dir / f"{base_name}.{fmt}"
        try:
            convert_to_format(args.input, output_file, fmt)
            size = output_file.stat().st_size / 1024  # KB
            print(f"✓ {fmt.upper()}: {output_file} ({size:.1f} KB)")
            results.append((fmt, output_file, size))
        except Exception as e:
            print(f"✗ {fmt.upper()}: {e}")

    # Summary
    print(f"\n✓ Exported {len(results)}/{len(formats)} formats successfully")
    print("\nCitation Preservation Guide:")
    print("  • PDF: Full citation preservation with footnotes")
    print("  • HTML: Citations as clickable footnote links")
    print("  • DOCX: Citations as Word endnotes (open in Word to verify)")
    print("  • ODT: Citations as LibreOffice footnotes")


if __name__ == '__main__':
    main()

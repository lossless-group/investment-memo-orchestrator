#!/usr/bin/env python3
"""
Markdown to Word (.docx) Converter

Converts markdown files to Microsoft Word format using pypandoc.
Can convert single files or entire directories.

Usage:
    # Convert a single file
    python md2docx.py output/memo.md

    # Convert all markdown files in a directory
    python md2docx.py output/

    # Specify output directory
    python md2docx.py output/memo.md -o exports/

    # Convert directory and preserve structure
    python md2docx.py output/ -o exports/
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


def ensure_pandoc_installed(auto_install: bool = True):
    """Check if pandoc is installed, download if not available.

    Args:
        auto_install: If True, automatically download pandoc if not found.
                      If False, exit with instructions.
    """
    try:
        version = pypandoc.get_pandoc_version()
        print(f"Using pandoc version {version}")
    except OSError:
        if auto_install:
            print("Pandoc not found. Downloading pandoc...")
            try:
                pypandoc.download_pandoc()
                version = pypandoc.get_pandoc_version()
                print(f"Pandoc {version} downloaded successfully!")
            except Exception as e:
                print(f"Error downloading pandoc: {e}")
                print("Please install pandoc manually: https://pandoc.org/installing.html")
                print("Or install via homebrew: brew install pandoc")
                sys.exit(1)
        else:
            print("Pandoc is not installed on your system.")
            print("Please install pandoc: https://pandoc.org/installing.html")
            print("Or install via homebrew: brew install pandoc")
            sys.exit(1)


def convert_markdown_to_docx(
    input_path: Path,
    output_path: Optional[Path] = None,
    extra_args: Optional[List[str]] = None
) -> Path:
    """
    Convert a single markdown file to Word format.

    Args:
        input_path: Path to the input markdown file
        output_path: Path for the output docx file (optional)
        extra_args: Additional pandoc arguments (optional)

    Returns:
        Path to the created docx file
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not input_path.suffix.lower() in ['.md', '.markdown']:
        raise ValueError(f"Input file must be a markdown file (.md or .markdown): {input_path}")

    # Determine output path
    if output_path is None:
        output_path = input_path.with_suffix('.docx')
    elif output_path.is_dir():
        output_path = output_path / input_path.with_suffix('.docx').name

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Convert using pypandoc
        pypandoc.convert_file(
            str(input_path),
            'docx',
            outputfile=str(output_path),
            extra_args=extra_args
        )
        return output_path
    except Exception as e:
        raise RuntimeError(f"Error converting {input_path}: {e}")


def find_markdown_files(directory: Path, recursive: bool = True) -> List[Path]:
    """
    Find all markdown files in a directory.

    Args:
        directory: Directory to search
        recursive: Whether to search recursively

    Returns:
        List of markdown file paths
    """
    pattern = '**/*.md' if recursive else '*.md'
    md_files = list(directory.glob(pattern))

    # Also check for .markdown extension
    if recursive:
        md_files.extend(directory.glob('**/*.markdown'))
    else:
        md_files.extend(directory.glob('*.markdown'))

    return sorted(md_files)


def main():
    parser = argparse.ArgumentParser(
        description='Convert Markdown files to Word (.docx) format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s memo.md                    # Convert single file to memo.docx
  %(prog)s memo.md -o exports/        # Convert to exports/memo.docx
  %(prog)s output/                    # Convert all .md files in output/
  %(prog)s output/ -o exports/        # Convert all .md files to exports/
  %(prog)s memo.md --toc              # Include table of contents
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        help='Input markdown file or directory'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output file or directory (default: same location as input with .docx extension)'
    )

    parser.add_argument(
        '--no-recursive',
        action='store_true',
        help='Do not search directories recursively'
    )

    parser.add_argument(
        '--toc',
        action='store_true',
        help='Include table of contents in output'
    )

    parser.add_argument(
        '--reference-doc',
        type=Path,
        help='Reference docx file for styling'
    )

    parser.add_argument(
        '--no-auto-install',
        action='store_true',
        help='Do not automatically download pandoc if not installed'
    )

    args = parser.parse_args()

    # Check if pandoc is available
    ensure_pandoc_installed(auto_install=not args.no_auto_install)

    # Build extra pandoc arguments
    extra_args = []
    if args.toc:
        extra_args.append('--toc')
    if args.reference_doc:
        if not args.reference_doc.exists():
            print(f"Error: Reference document not found: {args.reference_doc}")
            sys.exit(1)
        extra_args.append(f'--reference-doc={args.reference_doc}')

    # Determine input files
    input_path = args.input

    if not input_path.exists():
        print(f"Error: Input path not found: {input_path}")
        sys.exit(1)

    # Process files
    if input_path.is_file():
        # Single file conversion
        try:
            output_path = convert_markdown_to_docx(
                input_path,
                args.output,
                extra_args
            )
            print(f"✓ Converted: {input_path} -> {output_path}")
        except Exception as e:
            print(f"✗ Error: {e}")
            sys.exit(1)

    elif input_path.is_dir():
        # Directory conversion
        md_files = find_markdown_files(input_path, recursive=not args.no_recursive)

        if not md_files:
            print(f"No markdown files found in {input_path}")
            sys.exit(0)

        print(f"Found {len(md_files)} markdown file(s)")

        success_count = 0
        error_count = 0

        for md_file in md_files:
            try:
                # Preserve directory structure if output dir is specified
                if args.output:
                    relative_path = md_file.relative_to(input_path)
                    output_file = args.output / relative_path.with_suffix('.docx')
                else:
                    output_file = None

                output_path = convert_markdown_to_docx(
                    md_file,
                    output_file,
                    extra_args
                )
                print(f"✓ Converted: {md_file} -> {output_path}")
                success_count += 1
            except Exception as e:
                print(f"✗ Error converting {md_file}: {e}")
                error_count += 1

        print(f"\nCompleted: {success_count} successful, {error_count} errors")

        if error_count > 0:
            sys.exit(1)

    else:
        print(f"Error: Invalid input path: {input_path}")
        sys.exit(1)


if __name__ == '__main__':
    main()

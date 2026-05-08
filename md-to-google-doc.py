#!/usr/bin/env python3
"""
Export Markdown to Google Docs-Ready Word Format

Creates a branded .docx file optimized for upload to Google Docs.
The file is saved to Desktop (or custom location) for easy manual upload.

Usage:
    # Export to Desktop
    python md-to-google-doc.py output/KearnyJackson_Memo.md

    # Export to custom location
    python md-to-google-doc.py output/Memo.md -o ~/Documents/

    # Open folder after export
    python md-to-google-doc.py output/Memo.md --open
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_desktop_path() -> Path:
    """Get the user's Desktop path."""
    return Path.home() / "Desktop"


def convert_to_branded_docx(
    markdown_path: Path,
    output_path: Path = None,
    open_after: bool = False
) -> Path:
    """
    Convert markdown to branded Word document for Google Docs upload.

    Args:
        markdown_path: Path to input markdown file
        output_path: Path for output (directory or file)
        open_after: Open the output folder after conversion

    Returns:
        Path to created .docx file
    """
    # Validate input
    if not markdown_path.exists():
        print(f"Error: Input file not found: {markdown_path}")
        sys.exit(1)

    if not markdown_path.suffix.lower() in ['.md', '.markdown']:
        print(f"Error: Input must be a markdown file: {markdown_path}")
        sys.exit(1)

    # Determine output path
    if output_path is None:
        output_path = get_desktop_path()

    if output_path.is_dir():
        output_file = output_path / markdown_path.with_suffix('.docx').name
    else:
        output_file = output_path

    # Get reference document path
    reference_doc = Path(__file__).parent / 'templates' / 'hypernova-reference.docx'

    if not reference_doc.exists():
        print(f"Reference document not found. Creating it...")
        create_ref_cmd = [sys.executable, str(Path(__file__).parent / 'create-word-reference.py')]
        subprocess.run(create_ref_cmd, check=True)

    # Convert using md2docx.py
    print(f"\n{'='*60}")
    print(f"Converting: {markdown_path.name}")
    print(f"{'='*60}\n")

    md2docx_script = Path(__file__).parent / 'md2docx.py'
    cmd = [
        sys.executable,
        str(md2docx_script),
        str(markdown_path),
        '--reference-doc', str(reference_doc),
        '-o', str(output_file)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error during conversion:")
        print(result.stderr)
        sys.exit(1)

    # Print result
    print(result.stdout)

    if not output_file.exists():
        print(f"Error: Output file was not created")
        sys.exit(1)

    file_size_mb = output_file.stat().st_size / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"✅ SUCCESS!")
    print(f"{'='*60}")
    print(f"\nBranded Word Document Created:")
    print(f"  Location: {output_file}")
    print(f"  Size:     {file_size_mb:.2f} MB")
    print(f"\n{'='*60}")
    print(f"📤 Next Steps:")
    print(f"{'='*60}")
    print(f"1. Go to: https://drive.google.com")
    print(f"2. Click: 'New' → 'File upload'")
    print(f"3. Upload: {output_file.name}")
    print(f"4. Right-click uploaded file → 'Open with' → 'Google Docs'")
    print(f"5. ✅ Google Docs converts it automatically!")
    print(f"\n💡 Tip: Branding (colors, fonts, styles) will be preserved")
    print(f"   in Google Docs after conversion.\n")

    # Open folder if requested
    if open_after:
        import platform

        folder_path = output_file.parent

        if platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', str(folder_path)])
        elif platform.system() == 'Windows':
            subprocess.run(['explorer', str(folder_path)])
        elif platform.system() == 'Linux':
            subprocess.run(['xdg-open', str(folder_path)])

        print(f"📂 Opened folder: {folder_path}\n")

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Export markdown to Google Docs-ready Word format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s output/Memo.md                    # Export to Desktop
  %(prog)s output/Memo.md -o ~/Documents/    # Custom location
  %(prog)s output/Memo.md --open             # Open folder after export

The generated .docx file has Hypernova branding and is optimized
for manual upload to Google Docs.
        """
    )

    parser.add_argument(
        'input',
        type=Path,
        help='Input markdown file to convert'
    )

    parser.add_argument(
        '-o', '--output',
        type=Path,
        help='Output directory or file path (default: Desktop)'
    )

    parser.add_argument(
        '--open',
        action='store_true',
        help='Open the output folder after conversion'
    )

    args = parser.parse_args()

    # Convert
    convert_to_branded_docx(
        args.input,
        args.output,
        args.open
    )

    return 0


if __name__ == '__main__':
    sys.exit(main())

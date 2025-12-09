#!/usr/bin/env python3
"""
Convert images to PNG with transparency preservation.

Usage:
    python cli/convert_to_png.py <input_file> [--output <output_file>]

Examples:
    python cli/convert_to_png.py logo.avif
    python cli/convert_to_png.py logo.webp --output logo-transparent.png
    python cli/convert_to_png.py logo.svg --background transparent
"""

import argparse
import subprocess
import sys
from pathlib import Path


def convert_to_png(
    input_path: str,
    output_path: str | None = None,
    background: str = "transparent",
    quality: int = 100,
) -> Path:
    """
    Convert an image to PNG with transparency preservation.

    Args:
        input_path: Path to input image (supports: avif, webp, svg, jpg, gif, etc.)
        output_path: Optional output path. Defaults to same name with .png extension.
        background: Background color. Use "transparent" for alpha channel preservation.
        quality: PNG compression quality (0-100, higher = better quality, larger file)

    Returns:
        Path to the output PNG file.
    """
    input_file = Path(input_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine output path
    if output_path:
        output_file = Path(output_path)
    else:
        output_file = input_file.with_suffix(".png")

    # Build ffmpeg command for transparent PNG conversion
    # -y: overwrite output
    # -i: input file
    # -vf format=rgba: ensure RGBA format for transparency
    # -pix_fmt rgba: pixel format with alpha channel
    # -compression_level: PNG compression (0=fast/large, 9=slow/small)

    # Map quality (100 = best) to compression level (0 = best quality)
    compression_level = max(0, min(9, int((100 - quality) / 11)))

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-i", str(input_file),
        "-vf", "format=rgba",  # Convert to RGBA for transparency
        "-compression_level", str(compression_level),
        str(output_file)
    ]

    # For SVG input, we need different handling
    if input_file.suffix.lower() == ".svg":
        # Use ImageMagick for SVG (better SVG support)
        cmd = [
            "magick",
            "-background", "none",  # Transparent background
            "-density", "300",  # High DPI for quality
            str(input_file),
            "-strip",  # Remove metadata
            str(output_file)
        ]

        # Check if ImageMagick is available, fall back to ffmpeg
        try:
            subprocess.run(["magick", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Note: ImageMagick not found, using ffmpeg for SVG (may lose some quality)")
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(input_file),
                "-vf", "format=rgba",
                str(output_file)
            ]

    print(f"Converting: {input_file.name} → {output_file.name}")
    print(f"  Background: {background}")
    print(f"  Quality: {quality}%")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        # Verify output exists and has size
        if output_file.exists():
            size_kb = output_file.stat().st_size / 1024
            print(f"✓ Created: {output_file}")
            print(f"  Size: {size_kb:.1f} KB")

            # Verify transparency was preserved using ffprobe
            probe_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=pix_fmt",
                "-of", "csv=p=0",
                str(output_file)
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            pix_fmt = probe_result.stdout.strip()

            if "rgba" in pix_fmt or "pal8" in pix_fmt:
                print(f"  Transparency: ✓ preserved ({pix_fmt})")
            else:
                print(f"  Transparency: ⚠ may not be preserved ({pix_fmt})")
                print("  Tip: Source image may not have alpha channel")

            return output_file
        else:
            raise RuntimeError(f"Output file was not created: {output_file}")

    except subprocess.CalledProcessError as e:
        print(f"Error during conversion:")
        print(f"  stderr: {e.stderr}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Convert images to PNG with transparency preservation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s logo.avif                    # Convert AVIF to PNG
  %(prog)s logo.webp -o logo-out.png    # Convert with custom output name
  %(prog)s logo.svg --quality 100       # Convert SVG at highest quality

Supported input formats:
  AVIF, WebP, SVG, JPEG, GIF, TIFF, BMP, and most image formats supported by ffmpeg

Note: Requires ffmpeg. For best SVG support, install ImageMagick.
        """
    )

    parser.add_argument(
        "input",
        help="Input image file path"
    )

    parser.add_argument(
        "-o", "--output",
        help="Output PNG file path (default: same name with .png extension)"
    )

    parser.add_argument(
        "-q", "--quality",
        type=int,
        default=100,
        help="Quality level 0-100 (default: 100, highest quality)"
    )

    parser.add_argument(
        "-b", "--background",
        default="transparent",
        help="Background color (default: transparent)"
    )

    args = parser.parse_args()

    try:
        output_path = convert_to_png(
            args.input,
            args.output,
            args.background,
            args.quality
        )
        print(f"\nDone! Output: {output_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

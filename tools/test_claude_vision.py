#!/usr/bin/env python3
"""Test Claude Vision API for image analysis.

Tests three methods of providing images to Claude:
1. URL-based images (remote URLs)
2. Base64-encoded images (from local files)
3. PDF page conversion to images

Run: python tools/test_claude_vision.py
"""

import os
import sys
import base64
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

from anthropic import Anthropic

# Test configuration
TEST_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/1200px-Camponotus_flavomarginatus_ant.jpg"
LOCAL_TEST_IMAGE = "data/test-image.png"  # Will create if doesn't exist


def get_base64_from_url(url: str) -> tuple[str, str]:
    """Download image from URL and convert to base64."""
    # Use headers to avoid 403 from sites like Wikipedia
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    response = httpx.get(url, headers=headers, follow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "image/jpeg")
    media_type = content_type.split(";")[0].strip()

    image_data = base64.standard_b64encode(response.content).decode("utf-8")
    return image_data, media_type


def get_base64_from_file(file_path: str) -> tuple[str, str]:
    """Read local image file and convert to base64."""
    path = Path(file_path)

    # Determine media type from extension
    ext_to_media = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = ext_to_media.get(path.suffix.lower(), "image/png")

    with open(path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    return image_data, media_type


def test_url_image(client: Anthropic) -> bool:
    """Test Claude Vision with URL-based image."""
    print("\n" + "="*60)
    print("TEST 1: URL-based Image")
    print("="*60)
    print(f"Image URL: {TEST_IMAGE_URL[:60]}...")

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": TEST_IMAGE_URL,
                            },
                        },
                        {
                            "type": "text",
                            "text": "What is in this image? Describe it in 1-2 sentences."
                        }
                    ],
                }
            ],
        )

        print(f"\n Response: {message.content[0].text}")
        print(f"\nUsage: {message.usage.input_tokens} input, {message.usage.output_tokens} output tokens")
        print(" URL-based image test PASSED")
        return True

    except Exception as e:
        print(f"\n URL-based image test FAILED")
        print(f"Error: {type(e).__name__}: {e}")
        return False


def test_base64_image(client: Anthropic) -> bool:
    """Test Claude Vision with base64-encoded image."""
    print("\n" + "="*60)
    print("TEST 2: Base64-encoded Image")
    print("="*60)

    try:
        # Download image and encode as base64
        print("Downloading and encoding image...")
        image_data, media_type = get_base64_from_url(TEST_IMAGE_URL)
        print(f"Media type: {media_type}")
        print(f"Base64 length: {len(image_data)} chars")

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "What colors do you see in this image? List the main colors."
                        }
                    ],
                }
            ],
        )

        print(f"\n Response: {message.content[0].text}")
        print(f"\nUsage: {message.usage.input_tokens} input, {message.usage.output_tokens} output tokens")
        print(" Base64 image test PASSED")
        return True

    except Exception as e:
        print(f"\n Base64 image test FAILED")
        print(f"Error: {type(e).__name__}: {e}")
        return False


def test_multiple_images(client: Anthropic) -> bool:
    """Test Claude Vision with multiple images in one request."""
    print("\n" + "="*60)
    print("TEST 3: Multiple Images in Single Request")
    print("="*60)

    # Two different public domain images
    image_urls = [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/300px-Camponotus_flavomarginatus_ant.jpg",
    ]

    try:
        content = []
        for i, url in enumerate(image_urls):
            print(f"Adding image {i+1}: {url[:50]}...")
            content.append({
                "type": "image",
                "source": {
                    "type": "url",
                    "url": url,
                },
            })

        content.append({
            "type": "text",
            "text": "How many images do you see? Briefly describe each one."
        })

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
        )

        print(f"\n Response: {message.content[0].text}")
        print(f"\nUsage: {message.usage.input_tokens} input, {message.usage.output_tokens} output tokens")
        print(" Multiple images test PASSED")
        return True

    except Exception as e:
        print(f"\n Multiple images test FAILED")
        print(f"Error: {type(e).__name__}: {e}")
        return False


def test_local_pdf_page(client: Anthropic) -> bool:
    """Test converting a PDF page to image and analyzing it.

    This simulates what deck_analyst.py would do with pitch deck pages.
    """
    print("\n" + "="*60)
    print("TEST 4: PDF Page Analysis (if pdf2image available)")
    print("="*60)

    try:
        from pdf2image import convert_from_path
        import io

        # Look for PDFs in multiple locations
        pdf_files = []
        search_dirs = [
            Path("data"),
            Path("io"),  # Firm-scoped deals
        ]
        for search_dir in search_dirs:
            if search_dir.exists():
                pdf_files.extend(search_dir.glob("**/*.pdf"))

        if not pdf_files:
            print("  No PDF files found in data/ or io/ directories")
            print("  Skipping PDF test (not a failure)")
            return True

        pdf_path = pdf_files[0]
        print(f"Found PDF: {pdf_path.name}")
        print("Converting first page to image...")

        # Convert first page only
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=150)

        if not images:
            print("  No pages extracted from PDF")
            return False

        # Convert to base64
        img_buffer = io.BytesIO()
        images[0].save(img_buffer, format="PNG")
        img_buffer.seek(0)
        image_data = base64.standard_b64encode(img_buffer.read()).decode("utf-8")

        print(f"Converted to base64 ({len(image_data)} chars)")
        print("Sending to Claude Vision...")

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "This is a slide from a pitch deck. What is the main topic or title of this slide? Describe what you see in 2-3 sentences."
                        }
                    ],
                }
            ],
        )

        print(f"\n Response: {message.content[0].text}")
        print(f"\nUsage: {message.usage.input_tokens} input, {message.usage.output_tokens} output tokens")
        print(" PDF page analysis test PASSED")
        return True

    except ImportError:
        print("  pdf2image not installed")
        print("  Install with: uv pip install pdf2image")
        print("  Also requires poppler: brew install poppler")
        print("  Skipping PDF test (not a failure)")
        return True

    except Exception as e:
        error_name = type(e).__name__
        error_str = str(e).lower()

        # Handle missing poppler gracefully
        if "poppler" in error_str or "pdfinfo" in error_name.lower():
            print(f"  poppler not installed or not in PATH")
            print("  Install with: brew install poppler")
            print("  Skipping PDF test (not a failure)")
            return True

        print(f"\n PDF page analysis test FAILED")
        print(f"Error: {error_name}: {e}")
        return False


def main():
    """Run all Claude Vision tests."""
    print("="*60)
    print("CLAUDE VISION API TEST")
    print("="*60)

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        print("ERROR: No ANTHROPIC_API_KEY found in .env")
        print("Please set your Anthropic API key")
        sys.exit(1)

    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")

    client = Anthropic(api_key=api_key)

    results = []

    # Run tests
    results.append(("URL Image", test_url_image(client)))
    results.append(("Base64 Image", test_base64_image(client)))
    results.append(("Multiple Images", test_multiple_images(client)))
    results.append(("PDF Page", test_local_pdf_page(client)))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "" if result else ""
        print(f"  {status} {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n Claude Vision API is working correctly!")
    else:
        print("\n Some tests failed. Check error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

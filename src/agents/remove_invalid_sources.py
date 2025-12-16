"""
Remove Invalid Sources Agent - Validates citation URLs and removes those that don't exist.

This agent validates and cleans citations in a strict sequence to avoid race conditions:

STEP 1: Identify invalid citations
  - HTTP HEAD validation on all URLs
  - Detect hallucination patterns (example.com, XXXXX, etc.)
  - Build list of citation numbers to remove

STEP 2: Remove invalid citations (ALL files, no renumbering yet)
  - Remove inline references [^N] from body text
  - Remove citation definitions [^N]: ...
  - Files now have GAPS in numbering

STEP 3: Reorder citations (AFTER removal is complete)
  - Call reorder_citations_in_file() on each file
  - Renumbers to eliminate gaps: [^1], [^4], [^5] -> [^1], [^2], [^3]

CRITICAL: Removal and renumbering are SEPARATE passes to avoid:
  - Changing [^4] to [^3] before all [^4] refs are processed
  - Race conditions where a number means different things
  - Corrupted citation references

Can be called:
- As part of workflow: after section_research, BEFORE writer
- Independently via CLI: python -m src.agents.remove_invalid_sources <output_dir>

Runs AFTER: section_research (on 1-research/)
Runs BEFORE: writer
"""

import re
import urllib.request
import urllib.error
import ssl
import time
from typing import Dict, Any, List, Tuple, Set
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..state import MemoState
from ..utils import get_latest_output_dir


# HTTP codes that indicate the URL is definitely invalid (hallucinated)
INVALID_HTTP_CODES = {404, 410}  # Not Found, Gone

# HTTP codes that indicate the URL might be valid but inaccessible
POTENTIALLY_VALID_CODES = {401, 403, 429, 500, 502, 503}  # Auth required, Forbidden, Rate limited, Server errors

# Patterns that indicate obvious hallucinations
HALLUCINATION_PATTERNS = [
    r'example\.com',           # Reserved domain
    r'XXXXX',                  # Obvious placeholder
    r'placeholder',            # Placeholder text
    r'/path/to/',              # Generic path placeholder
    r'\{[^}]+\}',              # Template variables like {article-id}
]


def validate_url(url: str, timeout: int = 8) -> Tuple[str, int, str]:
    """
    Validate a single URL by making an HTTP request.

    Args:
        url: URL to validate
        timeout: Request timeout in seconds

    Returns:
        Tuple of (url, http_code, status_message)
        http_code is 0 for connection errors, -1 for hallucination patterns
    """
    # Check for obvious hallucination patterns first
    for pattern in HALLUCINATION_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return (url, -1, f"Hallucination pattern detected: {pattern}")

    try:
        # Create SSL context that doesn't verify (some sites have cert issues)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            url,
            method='HEAD',  # Use HEAD to avoid downloading full content
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        )

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            return (url, response.getcode(), "OK")

    except urllib.error.HTTPError as e:
        return (url, e.code, f"HTTP {e.code}")

    except urllib.error.URLError as e:
        # Connection failed - could be DNS, network, etc.
        return (url, 0, f"Connection failed: {str(e.reason)[:50]}")

    except Exception as e:
        return (url, 0, f"Error: {str(e)[:50]}")


def extract_citation_urls(content: str) -> Dict[str, str]:
    """
    Extract all citation numbers and their URLs from content.

    Args:
        content: Markdown content with citations

    Returns:
        Dict mapping citation number to URL
    """
    citations = {}

    # Pattern for citation definitions with markdown links
    # [^1]: 2024, Jan 15. [Title](URL). Source. Published: ...
    pattern = r'\[\^(\d+)\]:[^\[]*\[([^\]]+)\]\((https?://[^)]+)\)'

    for match in re.finditer(pattern, content):
        citation_num = match.group(1)
        url = match.group(3)
        citations[citation_num] = url

    # Also check for legacy format with URL at end
    legacy_pattern = r'\[\^(\d+)\]:[^|]+\|\s*URL:\s*(https?://\S+)'
    for match in re.finditer(legacy_pattern, content):
        citation_num = match.group(1)
        url = match.group(2)
        if citation_num not in citations:
            citations[citation_num] = url

    return citations


def remove_citation_references(content: str, citations_to_remove: Set[str]) -> str:
    """
    Remove inline citation references from content.

    Args:
        content: Markdown content with inline citations
        citations_to_remove: Set of citation numbers to remove (as strings)

    Returns:
        Content with specified citations removed
    """
    if not citations_to_remove:
        return content

    # Build pattern to match citations to remove
    # Matches [^1], [^2], etc. including surrounding whitespace and commas
    for num in citations_to_remove:
        # Remove citation with potential leading/trailing punctuation handling
        # Case 1: Citation alone or at end: "text [^1]" or "text. [^1]"
        content = re.sub(rf'\s*\[\^{num}\](?=[\s\.,;:\)\]]|$)', '', content)

        # Case 2: Citation in a list: "[^1], [^2]" -> "[^2]" or "[^1] [^2]" -> "[^2]"
        content = re.sub(rf'\[\^{num}\],?\s*', '', content)

    # Clean up any double spaces or orphaned commas
    content = re.sub(r'  +', ' ', content)
    content = re.sub(r',\s*,', ',', content)
    content = re.sub(r'\s+([.,;:])', r'\1', content)

    return content


def remove_citation_definitions(content: str, citations_to_remove: Set[str]) -> str:
    """
    Remove citation definition lines from content.

    Args:
        content: Markdown content with citation definitions
        citations_to_remove: Set of citation numbers to remove

    Returns:
        Content with citation definitions removed
    """
    lines = content.split('\n')
    filtered_lines = []

    for line in lines:
        # Check if this line is a citation definition to remove
        match = re.match(r'\[\^(\d+)\]:', line)
        if match and match.group(1) in citations_to_remove:
            continue  # Skip this line
        filtered_lines.append(line)

    return '\n'.join(filtered_lines)


def renumber_citations(content: str, old_to_new: Dict[str, str]) -> str:
    """
    Renumber citations based on mapping.

    Args:
        content: Markdown content with citations
        old_to_new: Dict mapping old citation numbers to new ones

    Returns:
        Content with renumbered citations
    """
    if not old_to_new:
        return content

    # Sort by old number descending to avoid conflicts (replace [^10] before [^1])
    for old_num in sorted(old_to_new.keys(), key=int, reverse=True):
        new_num = old_to_new[old_num]
        if old_num != new_num:
            # Replace inline references [^X]
            content = re.sub(rf'\[\^{old_num}\]', f'[^{new_num}]', content)

    return content


def reorder_citations_in_file(file_path: Path) -> bool:
    """
    Reorder citations in a single file to eliminate gaps.

    This function should be called AFTER invalid citations have been removed.
    It renumbers remaining citations to be sequential starting at 1.

    Example: [^1], [^4], [^7] -> [^1], [^2], [^3]

    Args:
        file_path: Path to markdown file

    Returns:
        True if file was modified, False otherwise
    """
    content = file_path.read_text()
    original = content

    # Extract all citation numbers currently in the file (inline refs)
    inline_refs = set(re.findall(r'\[\^(\d+)\](?!:)', content))

    # Extract all citation numbers from definitions
    definitions = set(re.findall(r'^\[\^(\d+)\]:', content, re.MULTILINE))

    # Combine and sort all citation numbers
    all_citations = sorted([int(n) for n in inline_refs | definitions])

    if not all_citations:
        return False  # No citations to reorder

    # Check if already sequential starting at 1
    expected = list(range(1, len(all_citations) + 1))
    if all_citations == expected:
        return False  # Already in order

    # Build renumbering map
    old_to_new: Dict[str, str] = {}
    for new_num, old_num in enumerate(all_citations, 1):
        if old_num != new_num:
            old_to_new[str(old_num)] = str(new_num)

    if not old_to_new:
        return False  # Nothing to renumber

    # Apply renumbering (descending order to avoid conflicts)
    content = renumber_citations(content, old_to_new)

    if content != original:
        file_path.write_text(content)
        return True

    return False


def reorder_directory_citations(directory: Path) -> int:
    """
    Reorder citations in all markdown files in a directory.

    This should be called AFTER remove_invalid_citations has cleaned all files.

    Args:
        directory: Directory containing markdown files

    Returns:
        Number of files that were modified
    """
    if not directory.exists():
        return 0

    modified_count = 0
    for md_file in sorted(directory.glob("*.md")):
        if reorder_citations_in_file(md_file):
            modified_count += 1

    return modified_count


def collect_all_citation_urls(output_dir: Path) -> Dict[str, str]:
    """
    Collect all citation URLs from research and section files.

    Args:
        output_dir: Output directory path

    Returns:
        Dict mapping citation number to URL
    """
    all_citations = {}

    # Collect from 1-research/ files
    research_dir = output_dir / "1-research"
    if research_dir.exists():
        for f in research_dir.glob("*.md"):
            content = f.read_text()
            citations = extract_citation_urls(content)
            all_citations.update(citations)

    # Collect from 2-sections/ files
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        for f in sections_dir.glob("*.md"):
            content = f.read_text()
            citations = extract_citation_urls(content)
            all_citations.update(citations)

    return all_citations


def remove_invalid_citations_from_directory(directory: Path, invalid_citations: Set[str]) -> int:
    """
    Remove invalid citations from all files in a directory.

    IMPORTANT: This function ONLY removes citations. It does NOT renumber.
    Call reorder_directory_citations() AFTER this to fix gaps.

    Args:
        directory: Directory containing markdown files
        invalid_citations: Set of citation numbers to remove

    Returns:
        Number of files updated
    """
    if not directory.exists():
        return 0

    if not invalid_citations:
        return 0

    updated_count = 0

    for md_file in sorted(directory.glob("*.md")):
        content = md_file.read_text()
        original = content

        # Step 1: Remove invalid citation references (inline [^N])
        content = remove_citation_references(content, invalid_citations)

        # Step 2: Remove invalid citation definitions ([^N]: ...)
        content = remove_citation_definitions(content, invalid_citations)

        # NOTE: Do NOT renumber here. File will have gaps.
        # Renumbering happens in a separate pass via reorder_directory_citations()

        if content != original:
            md_file.write_text(content)
            updated_count += 1

    return updated_count


def remove_invalid_citations_from_file(file_path: Path, invalid_citations: Set[str]) -> bool:
    """
    Remove invalid citations from a single file.

    IMPORTANT: This function ONLY removes citations. It does NOT renumber.
    Call reorder_citations_in_file() AFTER this to fix gaps.

    Args:
        file_path: Path to markdown file
        invalid_citations: Set of citation numbers to remove

    Returns:
        True if file was modified, False otherwise
    """
    if not file_path.exists():
        return False

    if not invalid_citations:
        return False

    content = file_path.read_text()
    original = content

    # Remove inline references
    content = remove_citation_references(content, invalid_citations)

    # Remove definitions
    content = remove_citation_definitions(content, invalid_citations)

    if content != original:
        file_path.write_text(content)
        return True

    return False


def remove_invalid_sources_agent(state: MemoState) -> Dict[str, Any]:
    """
    Remove Invalid Sources Agent implementation.

    Validates all citation URLs and removes those that are definitely invalid
    (404, hallucination patterns). Keeps potentially valid URLs (403, 401).

    CRITICAL: This agent uses a strict two-pass approach:

    PASS 1 - REMOVAL (no renumbering):
      - Remove inline refs [^N] from body text
      - Remove definitions [^N]: ...
      - Files now have GAPS in numbering

    PASS 2 - REORDER (after ALL removal is complete):
      - Renumber to eliminate gaps
      - [^1], [^4], [^7] -> [^1], [^2], [^3]

    This separation prevents race conditions where a citation number
    could mean different things during processing.

    Args:
        state: Current memo state

    Returns:
        Updated state with messages about removed citations
    """
    company_name = state["company_name"]
    firm = state.get("firm")

    print(f"\n🔍 Validating citation URLs for {company_name}...")

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        return {
            "messages": ["Remove invalid sources skipped: no output directory found"]
        }

    research_dir = output_dir / "1-research"
    sections_dir = output_dir / "2-sections"

    # Check for at least one directory to process
    if not research_dir.exists() and not sections_dir.exists():
        return {
            "messages": ["Remove invalid sources skipped: no research or sections directory"]
        }

    # Collect all citation URLs from both research and sections
    citation_urls = collect_all_citation_urls(output_dir)

    if not citation_urls:
        print("  No citations found to validate")
        return {
            "messages": ["Remove invalid sources: no citations found"]
        }

    print(f"  Found {len(citation_urls)} unique citations to validate")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: IDENTIFY INVALID CITATIONS
    # ═══════════════════════════════════════════════════════════════════

    invalid_citations: Set[str] = set()
    valid_citations: Set[str] = set()
    potentially_valid: Set[str] = set()
    validation_results: Dict[str, Tuple[int, str]] = {}

    print(f"  Validating URLs (parallel, {min(10, len(citation_urls))} workers)...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_citation = {
            executor.submit(validate_url, url): (num, url)
            for num, url in citation_urls.items()
        }

        for future in as_completed(future_to_citation):
            num, url = future_to_citation[future]
            try:
                _, http_code, status = future.result()
                validation_results[num] = (http_code, status)

                if http_code == -1:  # Hallucination pattern
                    invalid_citations.add(num)
                elif http_code in INVALID_HTTP_CODES:
                    invalid_citations.add(num)
                elif http_code in POTENTIALLY_VALID_CODES:
                    potentially_valid.add(num)
                elif http_code == 0:  # Connection error
                    potentially_valid.add(num)  # Keep but warn
                else:
                    valid_citations.add(num)

            except Exception as e:
                print(f"    Warning: Error validating [^{num}]: {e}")
                potentially_valid.add(num)

    print(f"  Results: {len(valid_citations)} valid, {len(potentially_valid)} uncertain, {len(invalid_citations)} invalid")

    if not invalid_citations:
        print("  ✓ No invalid citations to remove")
        return {
            "messages": [f"Citation validation complete: {len(valid_citations)} valid, {len(potentially_valid)} uncertain, 0 removed"]
        }

    # Log invalid citations
    print(f"\n  🗑️  Removing {len(invalid_citations)} invalid citations:")
    for num in sorted(invalid_citations, key=int):
        code, status = validation_results.get(num, (0, "Unknown"))
        url = citation_urls.get(num, "Unknown URL")
        print(f"    [^{num}]: {status} - {url[:60]}...")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: REMOVE INVALID CITATIONS (NO RENUMBERING YET)
    # Files will have GAPS after this step - that's expected!
    # ═══════════════════════════════════════════════════════════════════

    print(f"\n  📝 PASS 1: Removing invalid citations (no renumbering)...")

    # Remove from 1-research/ files
    if research_dir.exists():
        research_removed = remove_invalid_citations_from_directory(research_dir, invalid_citations)
        if research_removed:
            print(f"    ✓ Removed citations from {research_removed} research files")

    # Remove from 2-sections/ files
    if sections_dir.exists():
        sections_removed = remove_invalid_citations_from_directory(sections_dir, invalid_citations)
        if sections_removed:
            print(f"    ✓ Removed citations from {sections_removed} section files")

    # Remove from header.md if it exists
    header_file = output_dir / "header.md"
    if header_file.exists():
        if remove_invalid_citations_from_file(header_file, invalid_citations):
            print(f"    ✓ Removed citations from header.md")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: REORDER CITATIONS (AFTER ALL REMOVAL IS COMPLETE)
    # This eliminates gaps: [^1], [^4], [^7] -> [^1], [^2], [^3]
    # ═══════════════════════════════════════════════════════════════════

    print(f"\n  🔢 PASS 2: Reordering citations to eliminate gaps...")

    # Reorder in 1-research/ files
    if research_dir.exists():
        research_reordered = reorder_directory_citations(research_dir)
        if research_reordered:
            print(f"    ✓ Reordered citations in {research_reordered} research files")

    # Reorder in 2-sections/ files
    if sections_dir.exists():
        sections_reordered = reorder_directory_citations(sections_dir)
        if sections_reordered:
            print(f"    ✓ Reordered citations in {sections_reordered} section files")

    # Reorder header.md if it exists
    if header_file.exists():
        if reorder_citations_in_file(header_file):
            print(f"    ✓ Reordered citations in header.md")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: REASSEMBLE FINAL DRAFT (if sections exist)
    # ═══════════════════════════════════════════════════════════════════

    if sections_dir.exists():
        print(f"\n  📄 Reassembling final draft...")

        try:
            from cli.assemble_draft import assemble_final_draft
            from rich.console import Console
            console = Console()
            final_draft_path = assemble_final_draft(output_dir, console)
            print(f"  ✓ Final draft reassembled: {final_draft_path.name}")
        except ImportError as e:
            print(f"  ⚠️  Could not import assemble_draft CLI: {e}")
            print(f"  ⚠️  Please run manually: python -m cli.assemble_draft {output_dir}")

    # Calculate remaining citations
    remaining_count = len(citation_urls) - len(invalid_citations)
    summary = f"Removed {len(invalid_citations)} invalid citations, {remaining_count} remaining"
    print(f"\n  ✅ {summary}")

    return {
        "messages": [summary],
        "citation_cleanup": {
            "total_citations": len(citation_urls),
            "valid": len(valid_citations),
            "potentially_valid": len(potentially_valid),
            "removed": len(invalid_citations),
            "removed_citations": list(invalid_citations),
            "remaining": remaining_count
        }
    }


def remove_invalid_sources_standalone(output_dir: Path) -> Dict[str, Any]:
    """
    Standalone function for CLI usage - validates and removes invalid citations.

    This can be called directly on any output directory without needing
    the full workflow state.

    Args:
        output_dir: Path to output directory containing 1-research/ and/or 2-sections/

    Returns:
        Dict with cleanup results
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        print(f"Error: Directory not found: {output_dir}")
        return {"error": "Directory not found"}

    research_dir = output_dir / "1-research"
    sections_dir = output_dir / "2-sections"

    if not research_dir.exists() and not sections_dir.exists():
        print(f"Error: No 1-research/ or 2-sections/ directory found in {output_dir}")
        return {"error": "No content directories found"}

    # Collect all citation URLs
    citation_urls = collect_all_citation_urls(output_dir)

    if not citation_urls:
        print("No citations found to validate")
        return {"message": "No citations found"}

    print(f"Found {len(citation_urls)} unique citations to validate")

    # Validate URLs in parallel
    invalid_citations: Set[str] = set()
    valid_citations: Set[str] = set()
    potentially_valid: Set[str] = set()
    validation_results: Dict[str, Tuple[int, str]] = {}

    print(f"Validating URLs (parallel, {min(10, len(citation_urls))} workers)...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_citation = {
            executor.submit(validate_url, url): (num, url)
            for num, url in citation_urls.items()
        }

        for future in as_completed(future_to_citation):
            num, url = future_to_citation[future]
            try:
                _, http_code, status = future.result()
                validation_results[num] = (http_code, status)

                if http_code == -1:
                    invalid_citations.add(num)
                elif http_code in INVALID_HTTP_CODES:
                    invalid_citations.add(num)
                elif http_code in POTENTIALLY_VALID_CODES:
                    potentially_valid.add(num)
                elif http_code == 0:
                    potentially_valid.add(num)
                else:
                    valid_citations.add(num)

            except Exception as e:
                print(f"  Warning: Error validating [^{num}]: {e}")
                potentially_valid.add(num)

    print(f"Results: {len(valid_citations)} valid, {len(potentially_valid)} uncertain, {len(invalid_citations)} invalid")

    if not invalid_citations:
        print("✓ No invalid citations to remove")
        return {
            "total": len(citation_urls),
            "valid": len(valid_citations),
            "uncertain": len(potentially_valid),
            "removed": 0
        }

    # Log invalid citations
    print(f"\n🗑️  Removing {len(invalid_citations)} invalid citations:")
    for num in sorted(invalid_citations, key=int):
        code, status = validation_results.get(num, (0, "Unknown"))
        url = citation_urls.get(num, "Unknown URL")
        print(f"  [^{num}]: {status} - {url[:60]}...")

    # PASS 1: Remove invalid citations
    print(f"\n📝 PASS 1: Removing invalid citations...")

    if research_dir.exists():
        research_removed = remove_invalid_citations_from_directory(research_dir, invalid_citations)
        if research_removed:
            print(f"  ✓ Removed from {research_removed} research files")

    if sections_dir.exists():
        sections_removed = remove_invalid_citations_from_directory(sections_dir, invalid_citations)
        if sections_removed:
            print(f"  ✓ Removed from {sections_removed} section files")

    header_file = output_dir / "header.md"
    if header_file.exists():
        if remove_invalid_citations_from_file(header_file, invalid_citations):
            print(f"  ✓ Removed from header.md")

    # PASS 2: Reorder citations
    print(f"\n🔢 PASS 2: Reordering citations...")

    if research_dir.exists():
        research_reordered = reorder_directory_citations(research_dir)
        if research_reordered:
            print(f"  ✓ Reordered {research_reordered} research files")

    if sections_dir.exists():
        sections_reordered = reorder_directory_citations(sections_dir)
        if sections_reordered:
            print(f"  ✓ Reordered {sections_reordered} section files")

    if header_file.exists():
        if reorder_citations_in_file(header_file):
            print(f"  ✓ Reordered header.md")

    # Reassemble if sections exist
    if sections_dir.exists():
        print(f"\n📄 Reassembling final draft...")
        try:
            from cli.assemble_draft import assemble_final_draft
            from rich.console import Console
            console = Console()
            final_draft_path = assemble_final_draft(output_dir, console)
            print(f"✓ Final draft reassembled: {final_draft_path.name}")
        except ImportError as e:
            print(f"⚠️  Could not import assemble_draft: {e}")
            print(f"⚠️  Run manually: python -m cli.assemble_draft {output_dir}")

    remaining = len(citation_urls) - len(invalid_citations)
    print(f"\n✅ Removed {len(invalid_citations)} invalid citations, {remaining} remaining")

    return {
        "total": len(citation_urls),
        "valid": len(valid_citations),
        "uncertain": len(potentially_valid),
        "removed": len(invalid_citations),
        "remaining": remaining
    }


# CLI entry point
def main():
    """CLI entry point for standalone citation validation and removal."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.remove_invalid_sources <output_dir>")
        print("Example: python -m src.agents.remove_invalid_sources io/dark-matter/deals/ProfileHealth/outputs/ProfileHealth-v0.0.3")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    result = remove_invalid_sources_standalone(output_dir)

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()

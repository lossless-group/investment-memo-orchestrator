"""
Citation Accuracy Validator Agent - Validates citations for accuracy, accessibility, and date consistency.

This agent runs after citation enrichment to ensure all citations are:
1. Properly formatted
2. Have accessible URLs
3. Have accurate and consistent dates
4. Are not in the future or suspiciously old
"""

import re
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, List, Tuple
from pathlib import Path

from ..state import MemoState


def citation_validator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation Accuracy Validator Agent implementation.

    Validates citations in the drafted memo for accuracy, accessibility, and consistency.

    Args:
        state: Current memo state containing draft_sections with citations

    Returns:
        Updated state with citation_validation_results
    """
    draft_sections = state.get("draft_sections", {})
    if not draft_sections:
        raise ValueError("No draft available. Citation enrichment must run first.")

    company_name = state["company_name"]
    memo_content = draft_sections.get("full_memo", {}).get("content", "")

    if not memo_content:
        raise ValueError("Draft memo content is empty.")

    print(f"Validating citations for {company_name}...")

    # Extract all citations from memo
    citations = extract_citations(memo_content)

    if not citations:
        print("Warning: No citations found in memo")
        return {
            "citation_validation": {
                "total_citations": 0,
                "valid_citations": 0,
                "issues": ["No citations found in memo"],
                "warnings": []
            },
            "messages": ["Citation validation: No citations found"]
        }

    # Validate each citation
    issues = []
    warnings = []
    valid_count = 0
    url_to_citations = {}  # Track URLs to detect duplicates

    for citation_num, citation_text in citations.items():
        citation_issues, url = validate_citation(citation_num, citation_text)

        # Track URLs for duplicate detection
        if url:
            if url not in url_to_citations:
                url_to_citations[url] = []
            url_to_citations[url].append(citation_num)

        if not citation_issues:
            valid_count += 1
        else:
            for issue in citation_issues:
                if issue["severity"] == "error":
                    issues.append(f"[^{citation_num}]: {issue['message']}")
                else:
                    warnings.append(f"[^{citation_num}]: {issue['message']}")

    # Check for duplicate URLs
    duplicate_urls = {url: nums for url, nums in url_to_citations.items() if len(nums) > 1}
    if duplicate_urls:
        for url, citation_nums in duplicate_urls.items():
            warnings.append(
                f"Duplicate URL used in citations {', '.join(f'[^{n}]' for n in citation_nums)}: {url[:80]}..."
            )

    print(f"Citation validation complete: {valid_count}/{len(citations)} valid, "
          f"{len(issues)} errors, {len(warnings)} warnings")

    validation_results = {
        "total_citations": len(citations),
        "valid_citations": valid_count,
        "issues": issues,
        "warnings": warnings
    }

    return {
        "citation_validation": validation_results,
        "messages": [
            f"Citation validation: {valid_count}/{len(citations)} valid, "
            f"{len(issues)} errors, {len(warnings)} warnings"
        ]
    }


def extract_citations(content: str) -> Dict[str, str]:
    """
    Extract all citation references and their text from memo content.

    Args:
        content: Memo content with citations

    Returns:
        Dict mapping citation number to full citation text
    """
    citations = {}

    # Pattern to match citations like:
    # [^1]: 2024, Jan 15. Title - Source. Published: 2024-01-15 | Updated: 2024-01-20 | URL: https://...
    pattern = r'\[\^(\d+)\]:\s*(.+?)(?=\n\[\^|\n\n|\Z)'

    matches = re.findall(pattern, content, re.DOTALL)

    for citation_num, citation_text in matches:
        citations[citation_num] = citation_text.strip()

    return citations


def validate_citation(citation_num: str, citation_text: str) -> Tuple[List[Dict[str, str]], str]:
    """
    Validate a single citation for format, date accuracy, and URL accessibility.

    Args:
        citation_num: Citation number (e.g., "1", "2")
        citation_text: Full citation text

    Returns:
        Tuple of (list of issues found, URL)
    """
    issues = []
    extracted_url = None

    # 1. Check format - support multiple formats:
    # Format A (markdown link): YYYY, MMM DD. [Title](URL). Source. Published: YYYY-MM-DD | Updated: N/A
    # Format A2 (with author): YYYY, MMM DD. Author et al. [Title](URL). Source. Published: YYYY-MM-DD | Updated: N/A
    # Format B (legacy): YYYY, MMM DD. Title. Published: YYYY-MM-DD | Updated: YYYY-MM-DD | URL: https://...

    # Try to extract URL from markdown link first (most common modern format)
    # This handles both [Title](URL) immediately after date and with author names in between
    markdown_url_pattern = r'\[([^\]]+)\]\((https?://[^)]+)\)'
    markdown_match = re.search(markdown_url_pattern, citation_text)

    if markdown_match:
        # Found a markdown link - extract URL and validate date format
        title = markdown_match.group(1)
        extracted_url = markdown_match.group(2)

        # Extract date components
        date_pattern = r'(\d{4}),\s+(\w{3})\s+(\d{1,2})\.'
        date_match = re.search(date_pattern, citation_text)

        # Extract published/updated dates
        pub_pattern = r'Published:\s+(\d{4}-\d{2}-\d{2})\s*\|\s*Updated:\s+(.+?)(?:\s*$|\s*\|)'
        pub_match = re.search(pub_pattern, citation_text)

        if date_match and pub_match:
            display_year, display_month, display_day = date_match.groups()
            published_date, updated_date = pub_match.groups()
        else:
            # Has URL but non-standard date format - warn but accept
            issues.append({
                "severity": "warning",
                "message": "Citation has URL but non-standard date format"
            })
            return issues, extracted_url
    else:
        # No markdown link found - try legacy format with URL at end
        format_b_pattern = r'(\d{4}),\s+(\w{3})\s+(\d{1,2})\.\s+(.+?)\s+Published:\s+(\d{4}-\d{2}-\d{2})\s*\|\s*Updated:\s+(.+?)\s*\|\s*URL:\s*(https?://\S+)'
        match = re.search(format_b_pattern, citation_text)

        if match:
            display_year, display_month, display_day, title, published_date, updated_date, url = match.groups()
            extracted_url = url
        else:
            # Check if it at least has a URL somewhere (relaxed validation)
            url_match = re.search(r'(https?://[^\s\)]+)', citation_text)
            if url_match:
                extracted_url = url_match.group(1)
                # Just warn about format, don't error if we found a URL
                issues.append({
                    "severity": "warning",
                    "message": "Citation format non-standard but URL found"
                })
                return issues, extracted_url
            else:
                issues.append({
                    "severity": "error",
                    "message": "Citation format invalid and no URL found (expected: YYYY, MMM DD. [Title](URL). Source. Published: YYYY-MM-DD | Updated: N/A)"
                })
                return issues, None

    # 2. Check URL presence
    if not extracted_url:
        issues.append({
            "severity": "error",
            "message": "Missing URL in citation"
        })

    # 3. Validate dates
    try:
        # Parse display date
        display_date_str = f"{display_year}-{display_month}-{display_day}"
        display_date = datetime.strptime(display_date_str, "%Y-%b-%d")

        # Parse published date
        published = datetime.strptime(published_date, "%Y-%m-%d")

        # Check if display date matches published date
        if display_date.date() != published.date():
            # Check if it matches updated date instead
            if updated_date != "N/A":
                try:
                    updated = datetime.strptime(updated_date, "%Y-%m-%d")
                    if display_date.date() == updated.date():
                        issues.append({
                            "severity": "warning",
                            "message": f"Display date ({display_date.strftime('%Y-%m-%d')}) uses Updated date instead of Published date ({published_date})"
                        })
                    else:
                        issues.append({
                            "severity": "error",
                            "message": f"Display date ({display_date.strftime('%Y-%m-%d')}) doesn't match Published ({published_date}) or Updated ({updated_date})"
                        })
                except ValueError:
                    issues.append({
                        "severity": "warning",
                        "message": f"Display date ({display_date.strftime('%Y-%m-%d')}) doesn't match Published date ({published_date})"
                    })
            else:
                issues.append({
                    "severity": "warning",
                    "message": f"Display date ({display_date.strftime('%Y-%m-%d')}) doesn't match Published date ({published_date})"
                })

        # Check for future dates
        now = datetime.now()
        if published > now:
            issues.append({
                "severity": "error",
                "message": f"Published date ({published_date}) is in the future"
            })

        # Check for suspiciously old dates (>10 years)
        years_old = (now - published).days / 365.25
        if years_old > 10:
            issues.append({
                "severity": "warning",
                "message": f"Published date ({published_date}) is {int(years_old)} years old - may be outdated"
            })

    except ValueError as e:
        issues.append({
            "severity": "error",
            "message": f"Invalid date format: {str(e)}"
        })

    # 4. Check URL accessibility (optional - can be slow)
    if extracted_url and len(issues) == 0:  # Only check URL if no other issues
        try:
            req = urllib.request.Request(
                extracted_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                status = response.getcode()
                if status != 200:
                    issues.append({
                        "severity": "warning",
                        "message": f"URL returned status {status}"
                    })
        except urllib.error.HTTPError as e:
            issues.append({
                "severity": "warning",
                "message": f"URL not accessible (HTTP {e.code})"
            })
        except urllib.error.URLError:
            issues.append({
                "severity": "warning",
                "message": "URL not accessible (connection failed)"
            })
        except Exception as e:
            # Don't fail validation for URL checks - just warn
            issues.append({
                "severity": "info",
                "message": f"Could not verify URL accessibility: {str(e)}"
            })

    return issues, extracted_url

"""
Revise Summary Sections Agent.

Post-generation agent that rewrites Executive Summary and Closing Assessment
based on the complete final draft content. This agent runs AFTER toc_generator
so it can read the fully assembled memo and ensure the bookend sections
accurately reflect the actual content.

Key behaviors:
- Reads complete 4-final-draft.md
- Extracts key metrics (funding, traction, market) from full content
- Rewrites Executive Summary to reflect actual content (no false hedging)
- Rewrites Closing Assessment with synthesized recommendation
- Triggers reassembly of final draft with revised sections
"""

import re
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

from langchain_anthropic import ChatAnthropic

from ..utils import get_latest_output_dir


# Executive Summary revision prompt
EXEC_SUMMARY_PROMPT = """You are revising the Executive Summary for an investment memo.

You have access to the COMPLETE final memo below. Write a NEW Executive Summary that:

1. ACCURATELY REFLECTS the actual content (not speculation)
2. HIGHLIGHTS A FEW KEY METRICS from the body (funding, traction, market size/TAM)
3. AVOIDS hedging language ("data not available") unless truly warranted
4. PROVIDES clear, confident framing of the opportunity

DO NOT:
- Make excuses for missing data if the data IS present in the memo
- Make excuses in general, just try to write a good summary.
- Use vague language when specific numbers are available
- Add information not present in the memo

Target: {target_words} words

FULL MEMO CONTENT:
{full_memo}

EXTRACTED KEY DATA:
- Funding: {funding}
- Traction: {traction}
- Market: {market}

Write the revised Executive Summary (markdown format, start with "# Executive Summary"):
"""

# Closing Assessment revision prompt
CLOSING_PROMPT = """You are revising the Closing Assessment for an investment memo.

Based on the COMPLETE memo content below, write a final assessment that:

1. SYNTHESIZES the full analysis (not just repeats the summary)
2. WEIGHS strengths against risks based on ACTUAL content
3. PROVIDES concrete next steps or due diligence items
4. GIVES clear recommendation with specific rationale
5. TARGETS around 600 words, and up to three paragraphs.

Investment Mode: {mode}
- "consider": Prospective analysis - recommend PASS/CONSIDER/COMMIT
- "justify": Retrospective justification - explain why we invested

FULL MEMO CONTENT:
{full_memo}

KEY STRENGTHS IDENTIFIED:
{strengths}

KEY RISKS IDENTIFIED:
{risks}

Write the revised Closing Assessment (markdown format, start with "# Closing Assessment"):
"""


def extract_funding_data(content: str) -> str:
    """Extract funding-related information from memo content."""
    funding_patterns = [
        r'\$[\d,.]+[MBK]?\s*(?:million|billion)?\s*(?:round|raise|funding|Series\s*[A-Z]|seed|valuation|cap)',
        r'(?:raising|raised|round of)\s*\$[\d,.]+[MBK]?',
        r'(?:pre-money|post-money)\s*(?:valuation)?\s*(?:of|at)?\s*\$[\d,.]+[MBK]?',
        r'(?:runway|burn rate)\s*(?:of)?\s*[\d]+\s*months?',
        r'SAFE|Series\s*[A-Z]|convertible note',
    ]

    matches = []
    for pattern in funding_patterns:
        found = re.findall(pattern, content, re.IGNORECASE)
        matches.extend(found)

    if matches:
        # Dedupe and return first 5 unique matches
        unique = list(dict.fromkeys(matches))[:5]
        return "; ".join(unique)
    return "No specific funding data found in memo"


def extract_traction_data(content: str) -> str:
    """Extract traction/metrics information from memo content."""
    traction_patterns = [
        r'[\d,]+\+?\s*(?:users|customers|subscribers|members|beta users|waitlist)',
        r'[\d,.]+[MBK]?\s*(?:ARR|MRR|revenue|GMV)',
        r'[\d]+%\s*(?:growth|retention|conversion|churn)',
        r'[\d,]+\s*(?:downloads|installs|signups)',
        r'[\d]+\s*(?:B2B|enterprise|licensing)\s*(?:contracts|deals|partners)',
    ]

    matches = []
    for pattern in traction_patterns:
        found = re.findall(pattern, content, re.IGNORECASE)
        matches.extend(found)

    if matches:
        unique = list(dict.fromkeys(matches))[:5]
        return "; ".join(unique)
    return "No specific traction data found in memo"


def extract_market_data(content: str) -> str:
    """Extract market size/TAM information from memo content."""
    market_patterns = [
        r'\$[\d,.]+[TB]?\s*(?:trillion|billion)?\s*(?:market|TAM|SAM|SOM)',
        r'(?:market|TAM|SAM|SOM)\s*(?:of|at|estimated at)?\s*\$[\d,.]+[TB]?',
        r'[\d]+%\s*(?:CAGR|annual growth|YoY)',
        r'(?:market|industry)\s*(?:projected to|expected to|growing at)',
    ]

    matches = []
    for pattern in market_patterns:
        found = re.findall(pattern, content, re.IGNORECASE)
        matches.extend(found)

    if matches:
        unique = list(dict.fromkeys(matches))[:5]
        return "; ".join(unique)
    return "No specific market data found in memo"


def extract_strengths(content: str) -> str:
    """Extract key strengths mentioned in the memo."""
    # Look for positive indicators
    strength_indicators = [
        r'(?:key strength|competitive advantage|moat|differentiation)[:\s]+([^.]+\.)',
        r'(?:standout|strong|excellent|proven|validated)[^.]*(?:team|product|traction|market)[^.]*\.',
    ]

    matches = []
    for pattern in strength_indicators:
        found = re.findall(pattern, content, re.IGNORECASE)
        matches.extend(found)

    # Also look for 12Ps scores if present
    score_matches = re.findall(r'(?:Problem|Product|People|Potential)[^:]*:\s*(\d+)/5', content)
    if score_matches:
        matches.append(f"12Ps scores: {', '.join(score_matches)}")

    if matches:
        return "; ".join(matches[:5])
    return "See full memo for detailed analysis"


def extract_risks(content: str) -> str:
    """Extract key risks mentioned in the memo."""
    risk_indicators = [
        r'(?:key risk|main risk|primary risk|critical risk)[:\s]+([^.]+\.)',
        r'(?:concern|challenge|weakness|gap)[^.]*\.',
    ]

    matches = []
    for pattern in risk_indicators:
        found = re.findall(pattern, content, re.IGNORECASE)
        matches.extend(found)

    if matches:
        return "; ".join(matches[:5])
    return "See Risks section for detailed analysis"


def find_section_file(sections_dir: Path, keywords: List[str]) -> Optional[Path]:
    """Find a section file matching any of the keywords."""
    for section_file in sections_dir.glob("*.md"):
        filename_lower = section_file.name.lower()
        for keyword in keywords:
            if keyword in filename_lower:
                return section_file
    return None


def reassemble_final_draft(output_dir: Path) -> None:
    """
    Reassemble 4-final-draft.md from all sections after summary revision.

    Preserves:
    - Header (header.md)
    - TOC (from existing final draft)
    - All sections in order
    - Citations block (from existing final draft)
    """
    from ..artifacts import get_final_draft_path
    final_draft_path = get_final_draft_path(output_dir)
    sections_dir = output_dir / "2-sections"

    if not final_draft_path.exists():
        print("  ⚠️  No final draft to reassemble")
        return

    # Load existing to preserve TOC and citations
    existing_content = final_draft_path.read_text()

    # Extract TOC block (starts with "## Table of Contents" and ends before next ## or section)
    toc_match = re.search(
        r'(## Table of Contents\n.*?)(?=\n## (?!Table of Contents)|\n# )',
        existing_content,
        re.DOTALL
    )
    toc_block = toc_match.group(1) if toc_match else ""

    # Extract citations block (starts with [^1]: or similar at the end)
    citations_match = re.search(
        r'(\n\[\^\d+\]:.*?)$',
        existing_content,
        re.DOTALL
    )
    citations_block = citations_match.group(1) if citations_match else ""

    # Build new content
    parts = []

    # 1. Header
    header_path = output_dir / "header.md"
    if header_path.exists():
        parts.append(header_path.read_text().strip())
        parts.append("\n---\n")

    # 2. TOC
    if toc_block:
        parts.append(toc_block.strip())
        parts.append("\n---\n")

    # 3. All sections in order
    section_files = sorted(sections_dir.glob("*.md"))
    for section_file in section_files:
        section_content = section_file.read_text().strip()
        parts.append(section_content)
        parts.append("\n\n---\n")

    # 4. Citations
    if citations_block:
        parts.append(citations_block.strip())

    # Write reassembled content
    final_content = "\n".join(parts)
    final_draft_path.write_text(final_content)

    print(f"  ✓ Reassembled final draft: {final_draft_path.name}")


def revise_summary_sections(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-generation agent that rewrites Executive Summary and Closing Assessment
    based on the complete final draft content.

    This agent runs AFTER toc_generator so it can read the fully assembled memo
    and ensure the bookend sections accurately reflect the actual content.

    Args:
        state: Current memo state

    Returns:
        Updated state with messages about revisions made
    """
    company_name = state["company_name"]
    firm = state.get("firm")
    memo_mode = state.get("memo_mode", "consider")

    # Get target word counts from outline if available
    outline = state.get("outline", {})
    exec_summary_words = 300  # Default
    closing_words = 600  # Default

    if outline and "sections" in outline:
        for section in outline["sections"]:
            if "executive" in section.get("name", "").lower() or "summary" in section.get("name", "").lower():
                word_counts = section.get("word_counts", {})
                exec_summary_words = word_counts.get("ideal", word_counts.get("max", 300))
            if "closing" in section.get("name", "").lower() or "assessment" in section.get("name", "").lower():
                word_counts = section.get("word_counts", {})
                closing_words = word_counts.get("ideal", word_counts.get("max", 600))

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        print("⊘ Summary revision skipped - no output directory found")
        return {"messages": ["Summary revision skipped - no output directory"]}

    from ..artifacts import get_final_draft_path
    final_draft_path = get_final_draft_path(output_dir)
    sections_dir = output_dir / "2-sections"

    if not final_draft_path.exists():
        print("⊘ Summary revision skipped - no final draft found")
        return {"messages": ["Summary revision skipped - no final draft"]}

    if not sections_dir.exists():
        print("⊘ Summary revision skipped - no sections directory")
        return {"messages": ["Summary revision skipped - no sections directory"]}

    print("\n📝 Revising summary sections based on complete memo...")

    # Read the complete final draft
    full_memo = final_draft_path.read_text()

    # Extract key data from the memo
    funding_data = extract_funding_data(full_memo)
    traction_data = extract_traction_data(full_memo)
    market_data = extract_market_data(full_memo)
    strengths = extract_strengths(full_memo)
    risks = extract_risks(full_memo)

    print(f"  📊 Extracted data:")
    print(f"     Funding: {funding_data[:80]}..." if len(funding_data) > 80 else f"     Funding: {funding_data}")
    print(f"     Traction: {traction_data[:80]}..." if len(traction_data) > 80 else f"     Traction: {traction_data}")
    print(f"     Market: {market_data[:80]}..." if len(market_data) > 80 else f"     Market: {market_data}")

    # Initialize LLM
    model = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929")
    llm = ChatAnthropic(model=model, temperature=0.3, max_tokens=4096)

    messages = []

    # Revise Executive Summary
    exec_file = find_section_file(sections_dir, ["executive", "summary", "01-"])
    if exec_file:
        print(f"\n  📝 Revising Executive Summary...")

        exec_prompt = EXEC_SUMMARY_PROMPT.format(
            target_words=exec_summary_words,
            full_memo=full_memo[:50000],  # Limit to avoid token overflow
            funding=funding_data,
            traction=traction_data,
            market=market_data
        )

        try:
            response = llm.invoke(exec_prompt)
            revised_exec = response.content

            # Ensure proper header format
            if not revised_exec.strip().startswith("#"):
                revised_exec = "# Executive Summary\n\n" + revised_exec

            # Save revised section
            exec_file.write_text(revised_exec)
            word_count = len(revised_exec.split())
            print(f"  ✓ Revised Executive Summary ({word_count} words)")
            messages.append(f"Revised Executive Summary ({word_count} words)")

        except Exception as e:
            print(f"  ⚠️  Failed to revise Executive Summary: {e}")
            messages.append(f"Failed to revise Executive Summary: {e}")
    else:
        print("  ⊘ No Executive Summary section found")

    # Revise Closing Assessment
    closing_file = find_section_file(sections_dir, ["closing", "assessment", "recommendation", "10-"])
    if closing_file:
        print(f"\n  📝 Revising Closing Assessment...")

        closing_prompt = CLOSING_PROMPT.format(
            mode=memo_mode,
            full_memo=full_memo[:50000],
            strengths=strengths,
            risks=risks
        )

        try:
            response = llm.invoke(closing_prompt)
            revised_closing = response.content

            # Ensure proper header format
            if not revised_closing.strip().startswith("#"):
                revised_closing = "# Closing Assessment\n\n" + revised_closing

            # Save revised section
            closing_file.write_text(revised_closing)
            word_count = len(revised_closing.split())
            print(f"  ✓ Revised Closing Assessment ({word_count} words)")
            messages.append(f"Revised Closing Assessment ({word_count} words)")

        except Exception as e:
            print(f"  ⚠️  Failed to revise Closing Assessment: {e}")
            messages.append(f"Failed to revise Closing Assessment: {e}")
    else:
        print("  ⊘ No Closing Assessment section found")

    # Reassemble final draft with revised sections
    print("\n  🔄 Reassembling final draft...")
    reassemble_final_draft(output_dir)
    messages.append("Reassembled final draft with revised bookend sections")

    print("\n✓ Summary revision complete")

    return {"messages": messages}


# CLI-compatible function for standalone usage
def revise_summaries_cli(
    company_name: str,
    version: Optional[str] = None,
    firm: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    CLI wrapper for revise_summary_sections.

    Args:
        company_name: Company name
        version: Optional specific version (e.g., "v0.0.4")
        firm: Optional firm name
        dry_run: If True, show what would change without writing

    Returns:
        Result dict with messages
    """
    # Build minimal state
    state = {
        "company_name": company_name,
        "firm": firm,
        "memo_mode": "consider",  # Default, can be overridden if needed
    }

    if dry_run:
        print(f"[DRY RUN] Would revise summary sections for {company_name}")
        try:
            output_dir = get_latest_output_dir(company_name, firm=firm)
            from ..artifacts import get_final_draft_path
            final_draft = get_final_draft_path(output_dir)
            if final_draft.exists():
                content = final_draft.read_text()
                print(f"  Final draft: {len(content)} chars")
                print(f"  Funding data: {extract_funding_data(content)[:100]}...")
                print(f"  Traction data: {extract_traction_data(content)[:100]}...")
                print(f"  Market data: {extract_market_data(content)[:100]}...")
        except Exception as e:
            print(f"  Error: {e}")
        return {"messages": ["Dry run complete"]}

    return revise_summary_sections(state)

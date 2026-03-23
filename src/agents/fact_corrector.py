"""
Fact Corrector Agent - Applies verified corrections to section drafts.

This agent reads the verified fact-check report (4-fact-check-verified.json),
identifies claims that were contradicted or corrected by independent verification,
and uses an LLM to surgically update the section files with accurate information.

Pipeline position: runs AFTER fact_verifier, BEFORE validate.

Produces a corrections log (4-corrections-log.json) for full traceability:
  original claim → verification finding → corrected text → new citation

Does NOT rewrite sections wholesale. Only modifies specific sentences containing
incorrect claims, preserving all surrounding content.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from ..state import MemoState


def _build_correction_prompt(
    section_content: str,
    claims_to_correct: List[Dict[str, Any]],
    company_name: str
) -> str:
    """
    Build a prompt for the LLM to apply surgical corrections to a section.

    The LLM receives the full section and specific claims to fix. It must
    return the corrected section with ONLY the specified claims changed.
    """
    corrections_text = ""
    for i, claim in enumerate(claims_to_correct, 1):
        corrections_text += f"\n{i}. FIND THIS CLAIM:\n"
        corrections_text += f"   \"{claim['original_claim']}\"\n"
        corrections_text += f"   CORRECTION: {claim['correct_value']}\n"
        corrections_text += f"   EVIDENCE: {claim.get('evidence_summary', 'N/A')}\n"
        if claim.get("source_url"):
            corrections_text += f"   SOURCE: [{claim.get('source_title', 'Source')}]({claim['source_url']})\n"
            if claim.get("source_date"):
                corrections_text += f"   DATE: {claim['source_date']}\n"

    return f"""You are editing an investment memo section about {company_name}.

TASK: Apply ONLY the corrections listed below. Do not change anything else.

CORRECTIONS TO APPLY:
{corrections_text}

RULES:
1. Find each claim in the section text and replace it with the corrected information.
2. When adding a new source, add an inline citation [^N] using the NEXT available number
   (check existing citations in the text and use the next integer).
3. Add the citation definition at the end of the section in this format:
   [^N]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD | Updated: N/A
4. Preserve ALL other content exactly as-is. Do not rephrase, reorganize, or "improve" anything.
5. If you cannot locate a claim in the text, skip it — do not force a change.
6. Return the COMPLETE section with corrections applied. No commentary, no explanation.

SECTION CONTENT:
{section_content}"""


def _find_section_file_for_claim(sections_dir: Path, section_name: str) -> Optional[Path]:
    """
    Find the section file that matches a section name from the fact-check report.

    The fact-check report uses display names like "01 Overview" while files
    are named "01-overview.md".
    """
    # Normalize: "01 Overview" -> "01-overview" or "01_overview"
    normalized = section_name.lower().strip()
    # Extract leading number if present
    num_match = re.match(r'^(\d+)\s+', normalized)

    for section_file in sorted(sections_dir.glob("*.md")):
        stem = section_file.stem.lower()
        # Try exact match first
        if normalized.replace(' ', '-') == stem or normalized.replace(' ', '_') == stem:
            return section_file
        # Try number prefix match
        if num_match:
            prefix = num_match.group(1).zfill(2)
            if stem.startswith(prefix):
                return section_file
        # Try fuzzy: check if key words appear
        key_words = [w for w in normalized.split() if len(w) > 3 and not w.isdigit()]
        if key_words and all(w in stem.replace('-', ' ') for w in key_words):
            return section_file

    return None


def fact_corrector_agent(state: MemoState) -> Dict[str, Any]:
    """
    Fact Corrector Agent - Applies verified corrections to section files.

    Reads 4-fact-check-verified.json, extracts claims_to_correct, groups them
    by section, and uses Claude to surgically update each section file.

    Saves a corrections log for traceability.

    Args:
        state: Current memo state

    Returns:
        State updates with correction results
    """
    company_name = state["company_name"]

    # Get output directory
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("⊘ Fact correction skipped - no output directory")
        return {"messages": ["Fact correction skipped - no output directory"]}

    # Load verified fact-check report
    verified_path = output_dir / "4-fact-check-verified.json"
    if not verified_path.exists():
        print("⊘ Fact correction skipped - no 4-fact-check-verified.json")
        return {"messages": ["Fact correction skipped - no verified report"]}

    with open(verified_path) as f:
        verified_data = json.load(f)

    claims_to_correct = verified_data.get("claims_to_correct", [])

    if not claims_to_correct:
        print("✓ No claims need correction")
        return {"messages": ["Fact correction: no claims to correct"]}

    print("\n" + "=" * 70)
    print(f"🔧 CORRECTING {len(claims_to_correct)} VERIFIED CLAIMS")
    print("=" * 70)

    # Group corrections by section
    by_section: Dict[str, List[Dict[str, Any]]] = {}
    for claim in claims_to_correct:
        section = claim.get("section", "Unknown")
        by_section.setdefault(section, []).append(claim)

    # Initialize LLM client (use Anthropic Claude for correction, not Perplexity)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        print("⊘ Fact correction skipped - no ANTHROPIC_API_KEY")
        return {"messages": ["Fact correction skipped - no Anthropic API key"]}

    from anthropic import Anthropic
    client = Anthropic(api_key=anthropic_key)

    sections_dir = output_dir / "2-sections"
    corrections_log = []
    sections_modified = 0

    for section_name, section_claims in by_section.items():
        # Find the section file
        section_file = _find_section_file_for_claim(sections_dir, section_name)
        if not section_file:
            print(f"  ⚠️  Could not find file for section: {section_name}")
            for claim in section_claims:
                corrections_log.append({
                    "section": section_name,
                    "original_claim": claim["original_claim"],
                    "status": "skipped",
                    "reason": "section file not found"
                })
            continue

        print(f"\n  📝 {section_name} ({len(section_claims)} corrections)")

        # Read current section content
        original_content = section_file.read_text(encoding="utf-8")

        # Build correction prompt
        prompt = _build_correction_prompt(original_content, section_claims, company_name)

        try:
            response = client.messages.create(
                model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
                max_tokens=8000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            corrected_content = response.content[0].text

            # Validate: corrected content should be roughly the same length
            # (not a completely different document)
            len_ratio = len(corrected_content) / len(original_content) if original_content else 0
            if len_ratio < 0.5 or len_ratio > 2.0:
                print(f"    ⚠️  Correction produced suspicious length change ({len_ratio:.1f}x), skipping")
                for claim in section_claims:
                    corrections_log.append({
                        "section": section_name,
                        "original_claim": claim["original_claim"],
                        "status": "skipped",
                        "reason": f"LLM output length ratio {len_ratio:.1f}x (expected ~1.0x)"
                    })
                continue

            # Write corrected section
            section_file.write_text(corrected_content, encoding="utf-8")
            sections_modified += 1

            # Log each correction
            for claim in section_claims:
                corrections_log.append({
                    "section": section_name,
                    "section_file": section_file.name,
                    "original_claim": claim["original_claim"],
                    "claim_type": claim.get("claim_type"),
                    "correct_value": claim["correct_value"],
                    "evidence_summary": claim.get("evidence_summary"),
                    "source_url": claim.get("source_url"),
                    "source_title": claim.get("source_title"),
                    "source_date": claim.get("source_date"),
                    "status": "applied",
                    "timestamp": datetime.now().isoformat()
                })
                print(f"    ✓ {claim['original_claim'][:60]}...")
                print(f"      → {claim['correct_value'][:60]}")

        except Exception as e:
            print(f"    ❌ Error correcting {section_name}: {e}")
            for claim in section_claims:
                corrections_log.append({
                    "section": section_name,
                    "original_claim": claim["original_claim"],
                    "status": "error",
                    "reason": str(e)
                })

    # Save corrections log
    log_data = {
        "generated": datetime.now().isoformat(),
        "company": company_name,
        "total_corrections_attempted": len(claims_to_correct),
        "sections_modified": sections_modified,
        "corrections": corrections_log
    }

    log_path = output_dir / "4-corrections-log.json"
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

    # Also save human-readable log
    _save_corrections_report(output_dir / "4-corrections-log.md", log_data)

    applied = sum(1 for c in corrections_log if c["status"] == "applied")
    skipped = sum(1 for c in corrections_log if c["status"] == "skipped")
    errors = sum(1 for c in corrections_log if c["status"] == "error")

    print(f"\n{'=' * 70}")
    print(f"CORRECTION SUMMARY")
    print(f"{'=' * 70}")
    print(f"Applied: {applied} | Skipped: {skipped} | Errors: {errors}")
    print(f"Sections modified: {sections_modified}")
    print(f"Log: {log_path}")
    print(f"{'=' * 70}\n")

    return {
        "messages": [
            f"✓ Fact corrections: {applied} applied, {skipped} skipped, {errors} errors",
            f"  {sections_modified} sections modified, log saved to 4-corrections-log.json"
        ]
    }


def _save_corrections_report(path: Path, log_data: Dict[str, Any]) -> None:
    """Save a human-readable corrections report."""
    md = "# Fact Corrections Log\n\n"
    md += f"**Generated**: {log_data['generated']}\n"
    md += f"**Company**: {log_data['company']}\n"
    md += f"**Corrections attempted**: {log_data['total_corrections_attempted']}\n"
    md += f"**Sections modified**: {log_data['sections_modified']}\n\n"

    md += "## Corrections\n\n"
    for i, correction in enumerate(log_data.get("corrections", []), 1):
        status = correction.get("status", "unknown")
        icon = {"applied": "✓", "skipped": "⚠️", "error": "❌"}.get(status, "?")

        md += f"### {i}. {icon} [{status.upper()}] {correction.get('section', 'Unknown')}\n\n"
        md += f"**Original**: {correction.get('original_claim', 'N/A')}\n\n"

        if status == "applied":
            md += f"**Corrected to**: {correction.get('correct_value', 'N/A')}\n\n"
            md += f"**Evidence**: {correction.get('evidence_summary', 'N/A')}\n\n"
            if correction.get("source_url"):
                title = correction.get("source_title", correction["source_url"])
                md += f"**Source**: [{title}]({correction['source_url']})\n\n"
            md += f"**File**: `{correction.get('section_file', 'N/A')}`\n\n"
        else:
            md += f"**Reason**: {correction.get('reason', 'N/A')}\n\n"

        md += "---\n\n"

    path.write_text(md, encoding="utf-8")

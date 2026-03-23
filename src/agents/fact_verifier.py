"""
Fact Verifier Agent - LLM-powered independent verification of factual claims.

This agent reads the fact-check report (4-fact-check.json) produced by the
mechanical fact_checker, then sends suspicious/unsourced claims to Perplexity
Sonar Pro for independent verification against real-time web sources.

Pipeline position: runs AFTER fact_checker, BEFORE fact_corrector.

Traceability chain:
  fact_checker (extract claims) → fact_verifier (verify via LLM) → fact_corrector (apply fixes)

Each claim gets enriched with:
  - Independent verification result (confirmed / contradicted / unverifiable)
  - Better source URL if found
  - Corrected value if the original was wrong
  - Reasoning from the LLM
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from ..state import MemoState


def _build_verification_prompt(
    claims: List[Dict[str, Any]],
    company_name: str,
    section_name: str
) -> str:
    """
    Build a prompt for Perplexity to verify a batch of claims.

    Args:
        claims: List of claim dicts from fact-check report
        company_name: Company being analyzed
        section_name: Section the claims come from

    Returns:
        Prompt string for Perplexity API
    """
    claims_text = ""
    for i, claim in enumerate(claims, 1):
        claims_text += f"\n{i}. [{claim['type']}] \"{claim['claim']}\"\n"
        claims_text += f"   Current status: {claim['confidence']} | Severity: {claim['severity']}\n"

    return f"""You are a fact-checker verifying claims about {company_name} from an investment memo.

For each claim below, independently verify whether it is accurate using current web sources.

SECTION: {section_name}

CLAIMS TO VERIFY:
{claims_text}

For EACH claim, respond with a JSON object in this exact format:
{{
  "verifications": [
    {{
      "claim_index": 1,
      "original_claim": "the exact claim text",
      "verification_result": "confirmed" | "contradicted" | "corrected" | "unverifiable",
      "correct_value": "the accurate value if different from claim, or null",
      "evidence_summary": "brief explanation of what you found",
      "source_url": "URL of the best source for this claim, or null",
      "source_title": "Title of the source article/page, or null",
      "source_date": "Publication date if available (YYYY-MM-DD), or null",
      "confidence": "high" | "medium" | "low"
    }}
  ]
}}

RULES:
- "confirmed": Claim matches what sources say. Provide the source URL.
- "contradicted": Sources say something materially different. Provide correct_value and source.
- "corrected": Claim is partially right but needs adjustment (e.g., wrong amount, wrong date). Provide correct_value.
- "unverifiable": Cannot find reliable sources to confirm or deny. Do NOT guess.
- Only use sources you can actually cite with a real URL.
- If a claim is about a private company with limited public data, say "unverifiable" — do not fabricate.
- Respond ONLY with the JSON object, no other text."""


def _parse_verification_response(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse Perplexity's verification response into structured data.

    Args:
        response_text: Raw response from Perplexity

    Returns:
        List of verification result dicts
    """
    # Try to extract JSON from the response
    # Perplexity sometimes wraps JSON in markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        response_text = json_match.group(1)

    # Try direct JSON parse
    try:
        parsed = json.loads(response_text)
        return parsed.get("verifications", [])
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        brace_start = response_text.find('{')
        brace_end = response_text.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            try:
                parsed = json.loads(response_text[brace_start:brace_end + 1])
                return parsed.get("verifications", [])
            except json.JSONDecodeError:
                pass

    print("    ⚠️  Could not parse verification response as JSON")
    return []


def _verify_claims_batch(
    claims: List[Dict[str, Any]],
    company_name: str,
    section_name: str,
    perplexity_client
) -> List[Dict[str, Any]]:
    """
    Send a batch of claims to Perplexity for verification.

    Args:
        claims: Claims to verify
        company_name: Company name
        section_name: Section name
        perplexity_client: Perplexity API client

    Returns:
        List of verification results
    """
    prompt = _build_verification_prompt(claims, company_name, section_name)

    try:
        response = perplexity_client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {
                    "role": "system",
                    "content": "You are a rigorous fact-checker. Verify claims using real, current web sources. Never fabricate sources or URLs. If you cannot verify something, say so."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,
            temperature=0.1
        )

        response_text = response.choices[0].message.content
        return _parse_verification_response(response_text)

    except Exception as e:
        print(f"    ❌ Perplexity API error: {e}")
        return []


def fact_verifier_agent(state: MemoState) -> Dict[str, Any]:
    """
    Fact Verifier Agent - Uses Perplexity Sonar Pro to independently verify claims.

    Reads the mechanical fact-check report (4-fact-check.json), identifies claims
    that need verification (unsourced, suspicious, or critical), and sends them
    to Perplexity for independent verification with real-time web sources.

    Saves enriched report to 4-fact-check-verified.json with verification results
    merged into each claim.

    Args:
        state: Current memo state

    Returns:
        State updates with verified fact-check results
    """
    company_name = state["company_name"]

    # Check for Perplexity API key
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        print("⊘ Fact verification skipped - no PERPLEXITY_API_KEY")
        return {"messages": ["Fact verification skipped - no Perplexity API key"]}

    # Get output directory
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("⊘ Fact verification skipped - no output directory")
        return {"messages": ["Fact verification skipped - no output directory"]}

    # Load the fact-check report
    fact_check_path = output_dir / "4-fact-check.json"
    if not fact_check_path.exists():
        print("⊘ Fact verification skipped - no 4-fact-check.json found")
        return {"messages": ["Fact verification skipped - no fact-check report"]}

    with open(fact_check_path) as f:
        fact_check_data = json.load(f)

    print("\n" + "=" * 70)
    print("🔬 VERIFYING CLAIMS VIA PERPLEXITY SONAR PRO")
    print("=" * 70)

    # Initialize Perplexity client
    from openai import OpenAI
    perplexity_client = OpenAI(
        api_key=perplexity_key,
        base_url="https://api.perplexity.ai",
        default_headers={"User-Agent": "InvestmentMemoOrchestrator/1.0"}
    )

    # Collect claims that need verification (skip already-verified ones)
    sections_results = fact_check_data.get("fact_check_results", [])
    total_verified = 0
    total_sent = 0

    for section in sections_results:
        section_name = section.get("section", "Unknown")
        details = section.get("details", [])

        # Filter to claims that need verification
        claims_to_verify = [
            claim for claim in details
            if claim.get("confidence") in ("unsourced", "suspicious")
            and claim.get("severity") in ("critical", "high")
        ]

        if not claims_to_verify:
            print(f"  ✓ {section_name}: no claims need verification")
            continue

        print(f"\n  📋 {section_name}: verifying {len(claims_to_verify)} claims...")
        total_sent += len(claims_to_verify)

        # Send batch to Perplexity (batch by section to keep context)
        verifications = _verify_claims_batch(
            claims_to_verify,
            company_name,
            section_name,
            perplexity_client
        )

        # Merge verification results back into the claim details
        for verification in verifications:
            claim_idx = verification.get("claim_index", 0) - 1  # 0-indexed
            if 0 <= claim_idx < len(claims_to_verify):
                original_claim = claims_to_verify[claim_idx]

                # Find and update this claim in the full details list
                for detail in details:
                    if detail.get("claim") == original_claim.get("claim"):
                        detail["verification"] = {
                            "result": verification.get("verification_result", "unverifiable"),
                            "correct_value": verification.get("correct_value"),
                            "evidence_summary": verification.get("evidence_summary", ""),
                            "source_url": verification.get("source_url"),
                            "source_title": verification.get("source_title"),
                            "source_date": verification.get("source_date"),
                            "llm_confidence": verification.get("confidence", "low")
                        }
                        total_verified += 1

                        result = verification.get("verification_result", "?")
                        symbol = {"confirmed": "✓", "contradicted": "✗", "corrected": "~", "unverifiable": "?"}.get(result, "?")
                        print(f"    {symbol} [{result}] {detail['claim'][:80]}...")
                        if verification.get("correct_value"):
                            print(f"      → Correct: {verification['correct_value']}")
                        break

    # Update summary with verification stats
    fact_check_data["verification_summary"] = {
        "total_claims_sent": total_sent,
        "total_verified": total_verified,
        "verification_model": "sonar-pro",
    }

    # Count verification outcomes
    outcomes = {"confirmed": 0, "contradicted": 0, "corrected": 0, "unverifiable": 0}
    for section in sections_results:
        for detail in section.get("details", []):
            v = detail.get("verification", {})
            result = v.get("result", "")
            if result in outcomes:
                outcomes[result] += 1

    fact_check_data["verification_summary"]["outcomes"] = outcomes

    # Compute claims that need correction (contradicted or corrected with a correct_value)
    claims_to_correct = []
    for section in sections_results:
        section_name = section.get("section", "Unknown")
        for detail in section.get("details", []):
            v = detail.get("verification", {})
            if v.get("result") in ("contradicted", "corrected") and v.get("correct_value"):
                claims_to_correct.append({
                    "section": section_name,
                    "original_claim": detail.get("claim"),
                    "claim_type": detail.get("type"),
                    "correct_value": v.get("correct_value"),
                    "evidence_summary": v.get("evidence_summary"),
                    "source_url": v.get("source_url"),
                    "source_title": v.get("source_title"),
                    "source_date": v.get("source_date"),
                })

    fact_check_data["claims_to_correct"] = claims_to_correct

    # Save enriched report
    verified_path = output_dir / "4-fact-check-verified.json"
    with open(verified_path, "w") as f:
        json.dump(fact_check_data, f, indent=2, ensure_ascii=False)

    # Also save human-readable summary
    verified_md_path = output_dir / "4-fact-check-verified.md"
    _save_verification_report(verified_md_path, fact_check_data, outcomes, claims_to_correct)

    print(f"\n{'=' * 70}")
    print(f"VERIFICATION SUMMARY")
    print(f"{'=' * 70}")
    print(f"Claims verified: {total_verified}/{total_sent}")
    print(f"  Confirmed: {outcomes['confirmed']}")
    print(f"  Contradicted: {outcomes['contradicted']}")
    print(f"  Corrected: {outcomes['corrected']}")
    print(f"  Unverifiable: {outcomes['unverifiable']}")
    if claims_to_correct:
        print(f"\n📝 {len(claims_to_correct)} claims queued for correction")
    print(f"{'=' * 70}\n")

    return {
        "fact_check_results": fact_check_data,
        "messages": [
            f"✓ Verified {total_verified} claims via Perplexity: "
            f"{outcomes['confirmed']} confirmed, {outcomes['contradicted']} contradicted, "
            f"{outcomes['corrected']} corrected, {outcomes['unverifiable']} unverifiable",
            f"  {len(claims_to_correct)} claims queued for correction"
        ]
    }


def _save_verification_report(
    path: Path,
    data: Dict[str, Any],
    outcomes: Dict[str, int],
    claims_to_correct: List[Dict[str, Any]]
) -> None:
    """Save a human-readable markdown verification report."""
    from datetime import datetime

    md = "# Fact Verification Report\n\n"
    md += f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    md += f"**Model**: Perplexity Sonar Pro\n\n"

    md += "## Verification Outcomes\n\n"
    md += f"| Result | Count |\n|--------|-------|\n"
    for result, count in outcomes.items():
        md += f"| {result.title()} | {count} |\n"

    if claims_to_correct:
        md += f"\n## Claims Requiring Correction ({len(claims_to_correct)})\n\n"
        for i, claim in enumerate(claims_to_correct, 1):
            md += f"### {i}. {claim['section']}\n\n"
            md += f"**Original**: {claim['original_claim']}\n\n"
            md += f"**Correct value**: {claim['correct_value']}\n\n"
            md += f"**Evidence**: {claim.get('evidence_summary', 'N/A')}\n\n"
            if claim.get('source_url'):
                title = claim.get('source_title', claim['source_url'])
                md += f"**Source**: [{title}]({claim['source_url']})\n\n"
            md += "---\n\n"

    md += "\n## Per-Section Details\n\n"
    for section in data.get("fact_check_results", []):
        section_name = section.get("section", "Unknown")
        md += f"### {section_name}\n\n"
        for detail in section.get("details", []):
            v = detail.get("verification", {})
            if v:
                result = v.get("result", "not checked")
                md += f"- **[{result}]** {detail['claim'][:100]}\n"
                if v.get("correct_value"):
                    md += f"  - Correct: {v['correct_value']}\n"
                if v.get("source_url"):
                    md += f"  - Source: {v['source_url']}\n"
        md += "\n"

    path.write_text(md, encoding="utf-8")

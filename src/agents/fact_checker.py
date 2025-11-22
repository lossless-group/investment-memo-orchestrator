"""
Fact Checker Agent - Verifies factual claims against research sources.

This agent identifies unsourced claims, hallucinated metrics, and speculative
statements. It flags sections for revision when fabrication is detected.

Implements Tier 2 of the anti-hallucination defense system.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re
import json
from pathlib import Path

from ..state import MemoState
from ..artifacts import save_fact_check_artifacts


@dataclass
class FactCheckResult:
    """Result of fact-checking a single claim."""
    claim: str
    claim_type: str  # "metric", "name", "date", "pricing", "financial"
    is_sourced: bool
    source_citation: Optional[str]
    confidence: str  # "verified", "unsourced", "contradicts_source", "suspicious"
    reasoning: str
    severity: str  # "critical", "high", "medium", "low"
    recommended_action: str  # "remove", "flag_for_review", "request_source", "accept"


@dataclass
class SectionFactCheck:
    """Fact check results for an entire section."""
    section_name: str
    total_claims: int
    verified_claims: int
    unsourced_claims: int
    suspicious_claims: int
    fact_check_results: List[FactCheckResult]
    overall_score: float  # 0-1, where 1 = all claims sourced
    requires_rewrite: bool
    flagged_for_review: List[str]  # List of specific claims


def extract_factual_claims(section_content: str) -> List[Dict[str, Any]]:
    """
    Extract factual claims from section content.

    Returns list of claims with metadata:
    - claim_text: The specific sentence making a claim
    - claim_type: metric|financial|customer_count|pricing|date|partnership
    - specificity: high|medium|low
    """
    claims = []

    # Patterns that indicate factual claims requiring citations
    patterns = {
        "metric": r'\b(\d+[KMB]?|[\d,]+)\s+(ARR|MRR|customers?|users?|revenue|MAU|DAU|employees?)',
        "financial": r'\$[\d,]+[KMB]?',
        "percentage": r'\b\d+(\.\d+)?%\b',
        "growth": r'\b\d+%\s+(MoM|YoY|month[- ]over[- ]month|year[- ]over[- ]year|CAGR|growth)',
        "date": r'\b(20\d{2}|Q[1-4]\s+20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2}\b',
        "customer_name": r'\b(customers? include|clients? include|partnerships? with|backed by|investors? include)\s+[A-Z][a-z]+',
        "pricing": r'\$[\d,]+\s*(per|/)\s*(month|user|seat|year|license|annually)',
        "valuation": r'\$([\d.]+[KMB])\s+(valuation|pre-money|post-money)',
        "runway": r'\b\d+\s+months?\s+(runway|of runway|burn)',
        "team_size": r'\b\d+\s+(person|people|employees?|team members?)',
        "funding_round": r'\$([\d.]+[KMB])\s+(seed|Series [A-Z]|round)',
    }

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', section_content)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Skip sentences that are explicitly stating data unavailability
        if any(phrase in sentence.lower() for phrase in [
            'data not available',
            'not publicly available',
            'not disclosed',
            'not publicly disclosed',
            'information not available',
            'data unavailable'
        ]):
            continue

        for claim_type, pattern in patterns.items():
            if re.search(pattern, sentence, re.IGNORECASE):
                # Check specificity
                has_number = bool(re.search(r'\d', sentence))
                has_currency = '$' in sentence
                has_percentage = '%' in sentence

                specificity = "high" if (has_currency or has_percentage) else ("medium" if has_number else "low")

                claims.append({
                    "claim_text": sentence,
                    "claim_type": claim_type,
                    "specificity": specificity
                })
                break  # One claim type per sentence

    return claims


def verify_claim_against_research(
    claim: Dict[str, Any],
    research_data: Dict[str, Any],
    section_content: str
) -> FactCheckResult:
    """
    Verify a single claim against available research sources.

    Strategy:
    1. Check if claim has inline citation [^N]
    2. If cited, mark as verified
    3. If not cited, search research for supporting evidence
    4. If no evidence found, flag as suspicious
    """
    claim_text = claim["claim_text"]
    claim_type = claim["claim_type"]

    # Check for citation in same sentence or immediately after
    has_citation = bool(re.search(r'\[\^\d+\]', claim_text))

    if has_citation:
        # Extract citation number
        citation_match = re.search(r'\[\^(\d+)\]', claim_text)
        citation_num = citation_match.group(1) if citation_match else None

        return FactCheckResult(
            claim=claim_text,
            claim_type=claim_type,
            is_sourced=True,
            source_citation=f"[^{citation_num}]",
            confidence="verified",
            reasoning="Claim has inline citation to research source",
            severity="low",
            recommended_action="accept"
        )

    # No citation - check if claim content appears in research data
    claim_numbers = re.findall(r'[\d,]+', claim_text)
    claim_lower = claim_text.lower()

    # Convert research data to searchable string
    research_str = json.dumps(research_data).lower() if research_data else ""

    # Check if specific numbers from claim appear in research
    numbers_in_research = all(
        num.replace(',', '') in research_str.replace(',', '')
        for num in claim_numbers
    ) if claim_numbers else False

    # Extract key terms (nouns and numbers) from claim
    key_terms = re.findall(r'\b(?:\d+[\d,]*[KMB]?|\$[\d,]+[KMB]?|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', claim_text)

    terms_in_research = sum(
        1 for term in key_terms
        if term.lower() in research_str
    ) if key_terms else 0

    evidence_ratio = terms_in_research / len(key_terms) if key_terms else 0

    # Decision logic based on claim type and evidence
    if claim_type in ["metric", "financial", "pricing", "valuation", "growth", "funding_round"]:
        # High-risk claim types MUST have citations
        if numbers_in_research and evidence_ratio > 0.5:
            return FactCheckResult(
                claim=claim_text,
                claim_type=claim_type,
                is_sourced=False,
                source_citation=None,
                confidence="unsourced",
                reasoning=f"Specific {claim_type} claim appears in research but lacks citation",
                severity="high",
                recommended_action="request_source"
            )
        else:
            return FactCheckResult(
                claim=claim_text,
                claim_type=claim_type,
                is_sourced=False,
                source_citation=None,
                confidence="suspicious",
                reasoning=f"Specific {claim_type} claim with no citation and no evidence in research - likely hallucinated",
                severity="critical",
                recommended_action="remove"
            )

    # Medium-risk claim types (dates, team size, runway)
    if claim_type in ["date", "team_size", "runway"]:
        if numbers_in_research and evidence_ratio > 0.4:
            return FactCheckResult(
                claim=claim_text,
                claim_type=claim_type,
                is_sourced=False,
                source_citation=None,
                confidence="unsourced",
                reasoning=f"{claim_type.title()} claim appears in research but lacks citation",
                severity="medium",
                recommended_action="request_source"
            )
        else:
            return FactCheckResult(
                claim=claim_text,
                claim_type=claim_type,
                is_sourced=False,
                source_citation=None,
                confidence="suspicious",
                reasoning=f"{claim_type.title()} claim not found in research data",
                severity="high",
                recommended_action="flag_for_review"
            )

    # Lower-risk claim types (customer names, partnerships)
    if evidence_ratio > 0.6:
        return FactCheckResult(
            claim=claim_text,
            claim_type=claim_type,
            is_sourced=False,
            source_citation=None,
            confidence="unsourced",
            reasoning="Claim appears in research but lacks citation",
            severity="medium",
            recommended_action="request_source"
        )

    return FactCheckResult(
        claim=claim_text,
        claim_type=claim_type,
        is_sourced=False,
        source_citation=None,
        confidence="suspicious",
        reasoning="Claim not found in research data",
        severity="high",
        recommended_action="flag_for_review"
    )


def fact_check_section(
    section_name: str,
    section_content: str,
    research_data: Dict[str, Any],
    strictness: str = "high"  # "low", "medium", "high"
) -> SectionFactCheck:
    """
    Fact-check an entire section.

    Args:
        section_name: Name of section (e.g., "Traction & Milestones")
        section_content: The section markdown content
        research_data: Research data with sources
        strictness: How strict to be about citations

    Returns:
        SectionFactCheck with detailed results
    """
    claims = extract_factual_claims(section_content)

    fact_check_results = []
    critical_issues = []

    for claim in claims:
        result = verify_claim_against_research(claim, research_data, section_content)
        fact_check_results.append(result)

        if result.severity == "critical":
            critical_issues.append(result.claim)

    # Calculate score
    verified_count = sum(1 for r in fact_check_results if r.is_sourced)
    total_count = len(fact_check_results)
    score = verified_count / total_count if total_count > 0 else 1.0

    # Determine if rewrite required based on strictness
    strictness_thresholds = {
        "low": 0.4,    # 40% must be sourced
        "medium": 0.6,  # 60% must be sourced
        "high": 0.8     # 80% must be sourced
    }

    threshold = strictness_thresholds.get(strictness, 0.8)

    requires_rewrite = (
        len(critical_issues) > 0 or  # Any critical issues = rewrite
        score < threshold
    )

    return SectionFactCheck(
        section_name=section_name,
        total_claims=total_count,
        verified_claims=verified_count,
        unsourced_claims=total_count - verified_count,
        suspicious_claims=len([r for r in fact_check_results if r.confidence == "suspicious"]),
        fact_check_results=fact_check_results,
        overall_score=score,
        requires_rewrite=requires_rewrite,
        flagged_for_review=critical_issues
    )


def fact_checker_agent(state: MemoState) -> Dict[str, Any]:
    """
    Fact Checker Agent - Validates claims against research sources.

    Workflow:
    1. Load each section file from 2-sections/
    2. Extract factual claims (metrics, financials, dates, names)
    3. Verify each claim against research data
    4. Flag unsourced or suspicious claims
    5. If critical issues found, mark sections for rewrite
    6. Save fact-check report

    Returns:
        State updates with fact_check_results and sections_to_rewrite
    """
    company_name = state["company_name"]
    research_data = state.get("research", {})
    expected_company_url = state.get("company_url")

    print("\n" + "="*70)
    print("🔍 FACT CHECKING MEMO SECTIONS")
    print("="*70)
    print("Purpose: Verify all metrics and claims against research sources")
    print("="*70)

    # ENTITY DISAMBIGUATION CHECK
    # Verify research is about the correct company by comparing URLs
    entity_mismatch_warning = None
    if expected_company_url and research_data:
        research_company_url = research_data.get("company", {}).get("website", "")
        if research_company_url and expected_company_url.lower() not in research_company_url.lower() and research_company_url.lower() not in expected_company_url.lower():
            entity_mismatch_warning = f"""
⚠️  ENTITY MISMATCH DETECTED ⚠️
Expected company URL: {expected_company_url}
Research data URL: {research_company_url}

This suggests the research may be about a DIFFERENT company with the same name.
All sections should be flagged for review.
"""
            print(entity_mismatch_warning)

    # Get output directory
    from ..utils import get_latest_output_dir

    try:
        output_dir = get_latest_output_dir(company_name)
        sections_dir = output_dir / "2-sections"
    except FileNotFoundError:
        print("❌ No output directory found - skipping fact check")
        return {"messages": ["⚠️  Fact checker skipped - no output found"]}

    if not sections_dir.exists():
        print("❌ No sections directory found - skipping fact check")
        return {"messages": ["⚠️  Fact checker skipped - no sections found"]}

    section_files = sorted(sections_dir.glob("*.md"))

    all_results = []
    sections_to_rewrite = []

    # Get strictness from environment or default to high
    import os
    strictness = os.getenv("FACT_CHECK_STRICTNESS", "high")

    print(f"Strictness: {strictness.upper()}")
    print(f"Sections to check: {len(section_files)}\n")

    for section_file in section_files:
        section_name = section_file.stem.replace('-', ' ').title()

        with open(section_file, 'r') as f:
            section_content = f.read()

        print(f"📋 Checking: {section_name}")

        result = fact_check_section(
            section_name=section_name,
            section_content=section_content,
            research_data=research_data,
            strictness=strictness
        )

        all_results.append(result)

        print(f"   Claims found: {result.total_claims}")
        print(f"   ✓ Verified (with citations): {result.verified_claims}")
        print(f"   ⚠️  Unsourced: {result.unsourced_claims}")
        print(f"   🚨 Suspicious: {result.suspicious_claims}")
        print(f"   Score: {result.overall_score:.0%}")

        if result.requires_rewrite:
            sections_to_rewrite.append(section_file.stem)
            print(f"   ❌ REQUIRES REWRITE")

            if result.flagged_for_review:
                print(f"   Critical issues ({len(result.flagged_for_review)}):")
                for claim in result.flagged_for_review[:3]:  # Show first 3
                    print(f"      • {claim[:100]}...")
        else:
            print(f"   ✅ PASSED")

        print()

    # Calculate overall statistics
    total_claims = sum(r.total_claims for r in all_results)
    total_verified = sum(r.verified_claims for r in all_results)
    overall_score = total_verified / total_claims if total_claims > 0 else 1.0

    # If entity mismatch detected, flag ALL sections for rewrite
    if entity_mismatch_warning:
        sections_to_rewrite = [sf.stem for sf in section_files]
        overall_score = 0.0  # Force failure

    # Save fact-check report
    report = {
        "entity_mismatch": entity_mismatch_warning if entity_mismatch_warning else None,
        "fact_check_results": [
            {
                "section": r.section_name,
                "total_claims": r.total_claims,
                "verified_claims": r.verified_claims,
                "unsourced_claims": r.unsourced_claims,
                "suspicious_claims": r.suspicious_claims,
                "score": r.overall_score,
                "requires_rewrite": r.requires_rewrite,
                "critical_issues": r.flagged_for_review,
                "details": [
                    {
                        "claim": fc.claim,
                        "type": fc.claim_type,
                        "sourced": fc.is_sourced,
                        "confidence": fc.confidence,
                        "severity": fc.severity,
                        "action": fc.recommended_action,
                        "reasoning": fc.reasoning
                    }
                    for fc in r.fact_check_results
                ]
            }
            for r in all_results
        ],
        "summary": {
            "total_sections": len(all_results),
            "sections_passed": len(all_results) - len(sections_to_rewrite),
            "sections_flagged": len(sections_to_rewrite),
            "total_claims": total_claims,
            "verified_claims": total_verified,
            "overall_score": overall_score,
            "strictness": strictness
        },
        "sections_to_rewrite": sections_to_rewrite,
        "overall_pass": len(sections_to_rewrite) == 0
    }

    save_fact_check_artifacts(output_dir, report)

    print("="*70)
    print(f"FACT CHECK SUMMARY")
    print("="*70)

    # Show entity mismatch warning first if present
    if entity_mismatch_warning:
        print(entity_mismatch_warning)
        print("="*70)

    print(f"Total claims examined: {total_claims}")
    print(f"Verified (with citations): {total_verified} ({overall_score:.0%})")
    print(f"Sections passed: {len(all_results) - len(sections_to_rewrite)}/{len(all_results)}")

    if sections_to_rewrite:
        print(f"\n⚠️  {len(sections_to_rewrite)} sections require revision:")
        for section in sections_to_rewrite:
            section_display = section.replace('-', ' ').title()
            print(f"   • {section_display}")
        print("\nRecommendation: Review flagged sections for unsourced metrics")
        print("Use improve-section.py to add citations or remove unsourced claims")
    else:
        print(f"\n✅ All sections passed fact-check!")

    print("="*70 + "\n")

    messages = []
    if entity_mismatch_warning:
        messages.append("⚠️  ENTITY MISMATCH DETECTED - Research may be about wrong company!")
    messages.extend([
        f"✓ Fact check complete: {total_verified}/{total_claims} claims verified ({overall_score:.0%})",
        f"  {len(sections_to_rewrite)} sections flagged for review"
    ])

    return {
        "fact_check_results": report,
        "messages": messages
    }

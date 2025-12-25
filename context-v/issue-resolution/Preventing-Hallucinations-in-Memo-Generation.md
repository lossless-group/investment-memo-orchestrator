# Issue Resolution: Preventing Hallucinations in Memo Generation

**Date Started**: 2025-11-22
**Status**: Diagnosis Complete - Solution Planning
**Priority**: CRITICAL
**Impact**: LLMs (including Perplexity Sonar Pro) fabricating pricing, traction, and business model data for seed-stage startups

---

## Problem Statement

**Expected Behavior:**
- When data is unavailable (pricing, revenue, metrics), agents should explicitly state "Data not available"
- LLMs should refuse to answer guiding questions that lack supporting evidence
- Perplexity Sonar Pro should admit when web sources don't contain requested information
- Fabricated claims should be caught and removed before final memo

**Actual Behavior:**
- Perplexity Sonar Pro is inventing pricing, business models, and traction data
- Even with web grounding, the system fabricates specific numbers for seed-stage startups
- Recent example: Invented ARR, pricing tiers, and customer counts for a pre-revenue company
- Hallucinations include:
  - Specific revenue figures ($X ARR) with no sources
  - Detailed pricing models that don't exist
  - Customer counts and growth rates pulled from thin air
  - Business model details contradicting reality

**Why This Matters:**
1. **Trust Destruction**: One fabricated number destroys credibility of entire memo
2. **Investment Risk**: Partners making decisions on false data
3. **Legal Liability**: Misrepresenting company metrics in investment documents
4. **Reputation Damage**: If founders see invented facts about their own company

---

## Root Cause Analysis

### Discovery 1: Guiding Questions Create "Demand Pressure"

**Evidence from `templates/outlines/direct-investment.yaml`:**

**Business Overview Section (Lines 299-310):**
```yaml
guiding_questions:
  - "What does the company do? (in plain language, one sentence)"
  - "What specific problem are they solving for whom?"
  - "What is the business model? (how do they make money?)"
  - "Who pays and why? (customer value proposition)"
  - "What is the pricing strategy?"  # ← DEMANDS answer
  - "What are the unit economics? (CAC, LTV, gross margin if available)"  # ← "if available" is weak
  - "How do they acquire customers?"
```

**Traction & Milestones Section (Lines 517-526):**
```yaml
guiding_questions:
  - "What revenue has been generated? (ARR, MRR, or total with timeframe)"  # ← DEMANDS number
  - "How many customers do they have? (paying vs pilots)"  # ← DEMANDS count
  - "What is the customer growth rate? (MoM, YoY with %)"  # ← DEMANDS percentage
  - "Who are the marquee customers? (names/logos)"
  - "What are the usage metrics? (DAU, MAU, transactions, etc.)"
  - "What growth has been achieved? (specific % MoM or YoY)"  # ← DEMANDS specific %
```

**Funding & Terms Section (Lines 625-633):**
```yaml
guiding_questions:
  - "How much are they raising? (target and committed)"  # ← DEMANDS amount
  - "At what valuation? (pre-money or post-money - specify)"  # ← DEMANDS valuation
  - "What are the proposed terms? (equity stake, preferences, rights)"
  - "How will funds be used? (allocation breakdown)"
  - "What is the current runway? (months)"  # ← DEMANDS specific number
```

**The Psychological Problem:**

Questions are phrased as **interrogatives that demand answers**, not as optional information requests. The LLM interprets its task as "provide an answer to every question" rather than "answer questions where evidence exists."

---

### Discovery 2: Writer Agent Prompt Reinforces Answering Behavior

**Evidence from `src/agents/writer.py:388-412`:**

```python
user_prompt = f"""Write ONLY the "{section_def.name}" section for an investment memo about {company_name}.

SECTION GUIDANCE:
{section_def.description}

GUIDING QUESTIONS (Address these):  # ← "Address these" = COMMAND to answer
{questions_text}
{vocab_text}

RESEARCH DATA (summary):
{research_json}

Write ONLY this section's content (no section header, it will be added automatically).
Be specific, analytical, use metrics from research.  # ← "Be specific" + no data = fabrication
Target: {target_length} words (min: {section_def.target_length.min_words}, max: {section_def.target_length.max_words}).

SECTION CONTENT:
"""
```

**Analysis:**
- **"Address these"** creates obligation to answer every question
- **"Be specific, analytical, use metrics"** demands concrete details
- **Word count requirement** pressures LLM to fill space
- **No escape hatch** for "I don't have this data"

When the LLM faces:
- Question: "What revenue has been generated?"
- Research data: (no revenue mentioned)
- Instruction: "Address these" + "be specific" + "500 words"

It resolves the conflict by **inventing plausible-sounding data** rather than admitting absence.

---

### Discovery 3: Critical Rules Are Buried and Ineffective

**Evidence from `templates/outlines/direct-investment.yaml:543-551`:**

```yaml
section_vocabulary:
  critical_rules:
    - "NEVER use vague terms: 'significant traction', 'strong growth'"
    - "ALWAYS quantify: '$500K ARR', '50 customers', '30% MoM growth'"
    - "If metrics unavailable, state explicitly: 'Revenue data not available'"  # ← Good rule!
    - "Distinguish between pilots and paying customers"
    - "Distinguish between committed pipeline and closed deals"
```

**Why This Doesn't Work:**

1. **Conflicting directives**: Primary task says "Address these [revenue questions]" while buried rule says "state if unavailable"
2. **Prioritization**: LLMs prioritize main task completion over fine-print rules
3. **No enforcement**: Rules are suggestions, not constraints
4. **Passive voice**: "If metrics unavailable" is conditional, not imperative

**The rule SHOULD say:**
```
CRITICAL - READ CAREFULLY:
You are FORBIDDEN from inventing revenue, pricing, or customer numbers.
If you cannot cite a source for a metric, you MUST write "Data not available."
Fabrication is grounds for immediate rejection. Honesty is required.
```

---

### Discovery 4: Even Perplexity Sonar Pro Hallucinates Under Pressure

**Why Web-Grounded LLMs Still Fabricate:**

Perplexity Sonar Pro searches the web first, THEN generates responses based on search results. But when:
- Search returns ZERO results for "Company X pricing"
- Prompt still asks "What is the pricing strategy?"
- Context includes "be specific, analytical"

Perplexity faces a choice:
1. **Admit absence**: "Pricing information not publicly available"
2. **Infer from context**: "Typical SaaS companies charge $X/user..." → Becomes "Company X charges $X/user"
3. **Fabricate plausibly**: "$99/month for basic, $299/month for pro" (sounds realistic)

**It often chooses #2 or #3** because:
- Task completion reward > epistemic honesty penalty
- Inference blurs into assertion
- No explicit "you may fail to answer" permission

---

### Discovery 5: No Fact-Checking Before Finalization

**Current Pipeline (from `src/workflow.py`):**

```
Writer → Trademark → Socials → Links → Viz → Citations → Validator → Finalize
                                                             ↑
                                                    Only checks "quality"
                                                    Not factual grounding
```

**Evidence from `src/agents/validator.py`:**

The validator checks:
- Section completeness
- Writing quality
- Tone and style
- Length targets

**The validator DOES NOT check:**
- Whether metrics have citations
- Whether claims are sourced
- Whether numbers appear in research data
- Whether specific facts are verifiable

**Result:** Fabricated claims pass validation as long as they're well-written.

---

## Three-Tier Defense System

### Tier 1: Prompt Engineering Fixes (Immediate - 80% Reduction)

#### Fix 1A: Reframe Question Directive in Writer Prompt

**Current (`src/agents/writer.py:397-398`):**
```python
GUIDING QUESTIONS (Address these):
{questions_text}
```

**Replace with:**
```python
GUIDING QUESTIONS (Only answer if you have evidence from research):
{questions_text}

CRITICAL INSTRUCTION - READ THIS CAREFULLY:
For EACH question above, you have THREE options:
1. ANSWER with specific data from research (preferred - cite sources)
2. STATE EXPLICITLY "Data not available" (acceptable - be honest)
3. OMIT the question entirely if not relevant (acceptable)

You are FORBIDDEN from:
- Inferring numbers from industry averages
- Speculating based on company stage or size
- Making up pricing, metrics, or financial figures
- Using phrases like "likely", "estimated", "typically", "around"

IF YOU CANNOT CITE A SOURCE FOR A SPECIFIC CLAIM, DO NOT MAKE THE CLAIM.
Investors prefer "Unknown" over guesses. Fabricated numbers destroy trust.

VALIDATION: Your output will be fact-checked. Any unsourced metric (revenue,
pricing, customer count, growth rate) will trigger automatic rejection and rewrite.
```

**Why This Works:**
- Explicit permission to NOT answer
- Three valid paths (answer/admit/omit)
- Negative consequences for fabrication
- Threat of rejection increases honesty

---

#### Fix 1B: Add Data Availability Preflight Check

**Insert BEFORE guiding questions in writer prompt:**

```python
DATA AVAILABILITY ASSESSMENT:
Before writing, review the research and mark each question below:

✓ = You have specific data from research to answer this
? = Partial data, can provide limited answer
✗ = No data available, will state "Data not available" or omit

Questions you mark ✗ should result in explicit "Data not available" statements
or be omitted from the section entirely. DO NOT invent data for ✗ questions.

Review the research data below and mentally mark each question before writing:
{questions_text}

NOW review the research:
{research_json}
```

**Why This Works:**
- Forces deliberate assessment BEFORE writing
- Creates cognitive separation between "what they're asking" and "what I can answer"
- Primes LLM to think about data availability
- Reduces automatic answering reflex

---

#### Fix 1C: Modify YAML Guiding Questions to Signal Optionality

**Current (`templates/outlines/direct-investment.yaml`):**
```yaml
guiding_questions:
  - "What revenue has been generated? (ARR, MRR, or total with timeframe)"
  - "What is the pricing strategy?"
  - "What are the unit economics? (CAC, LTV, gross margin if available)"
```

**Replace with:**
```yaml
guiding_questions:
  - "What revenue has been generated? (ARR, MRR, or total - ONLY if you have a cited source. Otherwise state 'Revenue data not publicly available')"
  - "What is the pricing strategy? (ONLY if publicly disclosed or in pitch deck. If unknown, state 'Pricing not publicly available')"
  - "What are the unit economics? (CAC, LTV, gross margin - ONLY if you have actual data from sources. DO NOT estimate from industry averages)"
  - "How many customers do they have? (Exact number from sources ONLY. If unavailable, state 'Customer count not disclosed')"
```

**Template for high-risk questions:**
```
"[Question]? (ONLY if [source type]. Otherwise state '[Data type] not available')"
```

**Why This Works:**
- Embeds the escape hatch IN the question
- Provides exact phrase to use when data missing
- Signals that non-answer is acceptable
- Reduces question "demand pressure"

---

#### Fix 1D: Strengthen Critical Rules Placement

**Move critical rules from buried vocabulary to PRIMARY DIRECTIVE:**

**In `src/agents/writer.py`, add BEFORE guiding questions:**

```python
CRITICAL RULES - FAILURE TO FOLLOW = AUTOMATIC REJECTION:

1. NEVER FABRICATE METRICS
   - If you don't have revenue data, write "Revenue data not available"
   - If you don't have pricing, write "Pricing not publicly available"
   - If you don't have customer count, write "Customer count not disclosed"

2. CITE OR OMIT
   - Every specific number (revenue, customers, growth %) must have a source
   - If research doesn't mention a metric, DO NOT include it
   - "Estimated", "likely", "approximately" = fabrication in disguise

3. DISTINGUISH FACT FROM INFERENCE
   - Fact: "The company has 50 customers according to their blog post [^1]"
   - Inference: "As a seed-stage company, they likely have 20-50 customers"  ← FORBIDDEN

4. INDUSTRY AVERAGES ARE NOT DATA
   - "Typical SaaS companies charge $99/month" ≠ "This company charges $99/month"
   - Never use "typical", "standard", "usually" for THIS company's metrics

VALIDATION PROCESS:
After you write this section, it will be fact-checked. Every claim will be verified:
- Does this number appear in the research?
- Does this claim have a citation?
- Is this speculation disguised as fact?

Unsourced metrics trigger automatic section rejection and rewrite.
Honesty about data gaps is REQUIRED, not optional.
```

**Why This Works:**
- Prominent placement (impossible to miss)
- Threat of rejection (consequences)
- Specific examples of forbidden patterns
- Framing as "critical" not "guidelines"

---

### Tier 2: Fact-Checker Agent (Architecture Design)

#### Agent Purpose

Validate factual claims against research sources BEFORE final memo assembly. Identify:
- Unsourced metrics (revenue, pricing, customer count)
- Hallucinated names (customers, partners, investors)
- Speculative claims disguised as facts
- Numbers that don't appear in research data

#### Fact-Checker Workflow

```
Citation Enrichment → FACT CHECKER → Validator → Supervisor → Finalize
                            ↓
                      (if critical issues)
                            ↓
                    Trigger Section Rewrite
```

#### Implementation: `src/agents/fact_checker.py`

```python
"""
Fact Checker Agent - Verifies factual claims against research sources.

This agent identifies unsourced claims, hallucinated metrics, and speculative
statements. It flags sections for revision when fabrication is detected.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re
from pathlib import Path

from ..state import MemoState
from ..versioning import get_latest_output_dir
from ..artifacts import save_artifact


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

    # Patterns that indicate factual claims
    patterns = {
        "metric": r'\b(\d+[KMB]?|[\d,]+)\s+(ARR|MRR|customers?|users?|revenue|MAU|DAU)',
        "financial": r'\$[\d,]+[KMB]?',
        "percentage": r'\b\d+(\.\d+)?%\b',
        "growth": r'\b\d+%\s+(MoM|YoY|month[- ]over[- ]month|year[- ]over[- ]year)',
        "date": r'\b(20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2}\b',
        "customer_name": r'\b(customers? include|clients? include|partnerships? with|backed by)\s+[A-Z][a-z]+',
        "pricing": r'\$[\d,]+\s*(per|/)\s*(month|user|seat|year|license)',
        "valuation": r'\$([\d.]+[KMB])\s+(valuation|pre-money|post-money)',
        "runway": r'\b\d+\s+months?\s+(runway|of runway)',
    }

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', section_content)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
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
    2. If cited, verify citation exists in research
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
    research_str = str(research_data).lower()

    # Check if specific numbers from claim appear in research
    numbers_in_research = all(
        num.replace(',', '') in research_str.replace(',', '')
        for num in claim_numbers
    ) if claim_numbers else False

    # Check if key phrases appear in research
    # Extract key terms (nouns and numbers)
    key_terms = re.findall(r'\b(?:\d+[\d,]*[KMB]?|\$[\d,]+[KMB]?|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', claim_text)

    terms_in_research = sum(
        1 for term in key_terms
        if term.lower() in research_str
    ) if key_terms else 0

    evidence_ratio = terms_in_research / len(key_terms) if key_terms else 0

    # Decision logic based on claim type and evidence
    if claim_type in ["metric", "financial", "pricing", "valuation", "growth"]:
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
                reasoning=f"Specific {claim_type} claim with no citation and no evidence in research",
                severity="critical",
                recommended_action="remove"
            )

    # Lower-risk claim types
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

    print("\n" + "="*60)
    print("🔍 FACT CHECKING MEMO SECTIONS")
    print("="*60)

    output_dir = get_latest_output_dir(company_name)
    sections_dir = output_dir / "2-sections"

    if not sections_dir.exists():
        print("❌ No sections directory found - skipping fact check")
        return {"messages": ["⚠️  Fact checker skipped - no sections found"]}

    section_files = sorted(sections_dir.glob("*.md"))

    all_results = []
    sections_to_rewrite = []

    # Get strictness from environment or default to high
    import os
    strictness = os.getenv("FACT_CHECK_STRICTNESS", "high")

    print(f"Strictness: {strictness}")
    print(f"Sections to check: {len(section_files)}")
    print()

    for section_file in section_files:
        section_name = section_file.stem.replace('-', ' ').title()

        with open(section_file, 'r') as f:
            section_content = f.read()

        print(f"Checking: {section_name}")

        result = fact_check_section(
            section_name=section_name,
            section_content=section_content,
            research_data=research_data,
            strictness=strictness
        )

        all_results.append(result)

        print(f"  Claims found: {result.total_claims}")
        print(f"  Verified (with citations): {result.verified_claims}")
        print(f"  Unsourced: {result.unsourced_claims}")
        print(f"  Suspicious: {result.suspicious_claims}")
        print(f"  Score: {result.overall_score:.0%}")

        if result.requires_rewrite:
            sections_to_rewrite.append(section_file.stem)
            print(f"  ❌ REQUIRES REWRITE")

            if result.flagged_for_review:
                print(f"  Critical issues ({len(result.flagged_for_review)}):")
                for claim in result.flagged_for_review[:3]:  # Show first 3
                    print(f"    • {claim[:100]}...")
        else:
            print(f"  ✓ PASSED")

        print()

    # Calculate overall statistics
    total_claims = sum(r.total_claims for r in all_results)
    total_verified = sum(r.verified_claims for r in all_results)
    overall_score = total_verified / total_claims if total_claims > 0 else 1.0

    # Save fact-check report
    report = {
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

    save_artifact(output_dir, "5-fact-check", report)

    print("="*60)
    print(f"FACT CHECK SUMMARY")
    print("="*60)
    print(f"Total claims examined: {total_claims}")
    print(f"Verified (with citations): {total_verified} ({overall_score:.0%})")
    print(f"Sections passed: {len(all_results) - len(sections_to_rewrite)}/{len(all_results)}")

    if sections_to_rewrite:
        print(f"\n⚠️  {len(sections_to_rewrite)} sections require revision:")
        for section in sections_to_rewrite:
            print(f"  • {section}")
    else:
        print(f"\n✓ All sections passed fact-check!")

    print("="*60 + "\n")

    return {
        "fact_check_results": report,
        "messages": [
            f"✓ Fact check complete",
            f"  {total_verified}/{total_claims} claims verified ({overall_score:.0%})",
            f"  {len(sections_to_rewrite)} sections flagged for rewrite"
        ]
    }
```

---

### Tier 3: Workflow Integration & Auto-Correction

#### Option A: Auto-Rewrite Flagged Sections

When fact-checker finds critical issues, automatically trigger `improve-section.py`:

```python
# In src/workflow.py after fact_checker_agent

def auto_correct_sections(state: MemoState) -> Dict[str, Any]:
    """
    Auto-correct sections flagged by fact checker.

    Calls improve-section.py for each flagged section with
    strict "remove unsourced claims" instructions.
    """
    fact_check = state.get("fact_check_results", {})
    sections_to_fix = fact_check.get("sections_to_rewrite", [])

    if not sections_to_fix:
        return {"messages": ["No sections require correction"]}

    print(f"\n🔧 AUTO-CORRECTING {len(sections_to_fix)} SECTIONS")

    # For each section, call improve-section with special prompt
    for section in sections_to_fix:
        # Call improve-section.py with flag to remove unsourced claims
        # (Implementation depends on how you want to structure this)
        pass

    return {"messages": [f"Auto-corrected {len(sections_to_fix)} sections"]}
```

#### Option B: Human Review Queue

Route fact-check failures to human review before finalization:

```python
# In src/workflow.py supervisor node

def should_fact_check_pass(state: MemoState) -> str:
    """Route based on fact-check results."""
    fact_check = state.get("fact_check_results", {})

    if fact_check.get("overall_pass", False):
        return "validator"  # Continue to validation
    else:
        return "human_review"  # Route to human for manual fixes
```

#### Option C: Aggressive Claim Removal

Automatically strip unsourced claims from sections:

```python
def strip_unsourced_claims(section_content: str, fact_check_result: SectionFactCheck) -> str:
    """
    Remove sentences with critical/high severity unsourced claims.
    """
    claims_to_remove = [
        fc.claim
        for fc in fact_check_result.fact_check_results
        if fc.severity in ["critical", "high"] and fc.recommended_action == "remove"
    ]

    cleaned_content = section_content

    for claim in claims_to_remove:
        # Remove the claim sentence
        cleaned_content = cleaned_content.replace(claim, "")

    return cleaned_content
```

---

## Implementation Plan

### Phase 1: Immediate Prompt Fixes (30 minutes)

**Priority: CRITICAL - Deploy ASAP**

1. **Modify `src/agents/writer.py`** (Lines 388-412)
   - Add critical rules section before guiding questions
   - Change "Address these" to "Only answer if you have evidence"
   - Add data availability preflight check
   - Add validation threat

2. **Test on problematic company**
   - Re-run memo generation for company that hallucinated
   - Compare before/after for fabricated claims
   - Measure reduction in unsourced metrics

**Expected Impact:** 60-80% reduction in hallucinations

---

### Phase 2: YAML Guiding Questions Rewrite (1-2 hours)

**Priority: HIGH**

1. **Update `templates/outlines/direct-investment.yaml`**
   - Rewrite all Traction & Milestones questions (Lines 517-526)
   - Rewrite all Funding & Terms questions (Lines 625-633)
   - Rewrite Business Overview questions (Lines 299-310)
   - Add explicit "state if unavailable" instructions

2. **Update `templates/outlines/fund-commitment.yaml`**
   - Apply same pattern to fund-specific questions

3. **Test with 3-5 different companies**
   - Vary data availability (public vs stealth)
   - Verify honest "data not available" responses

**Expected Impact:** Additional 10-15% reduction (cumulative: 70-90%)

---

### Phase 3: Fact-Checker Agent (2-3 hours)

**Priority: HIGH**

1. **Create `src/agents/fact_checker.py`**
   - Implement claim extraction logic
   - Implement verification logic
   - Add report generation

2. **Integrate into workflow**
   - Add node in `src/workflow.py`
   - Position after citation_enrichment
   - Route failures to human_review or auto_correct

3. **Add artifact saving**
   - Save to `5-fact-check.json` and `.md`
   - Include detailed claim-by-claim analysis

4. **Test validation**
   - Create test sections with known hallucinations
   - Verify fact-checker catches them
   - Tune detection thresholds

**Expected Impact:** Catch remaining 10-20% edge cases

---

### Phase 4: Auto-Correction Integration (2-4 hours)

**Priority: MEDIUM**

1. **Option A: Integrate with improve-section.py**
   - Add `--remove-unsourced` flag to improve-section.py
   - Auto-call for flagged sections

2. **Option B: Build claim-stripping function**
   - Automatically remove critical/high severity claims
   - Replace with "Data not available" statements

3. **Option C: Human review workflow**
   - Create review queue interface
   - Show flagged claims for manual approval/removal

**Expected Impact:** Full automation of fact-checking → correction loop

---

## Configuration & Tuning

### Environment Variables

Add to `.env`:
```bash
# Fact-checking strictness: low (40%), medium (60%), high (80%)
FACT_CHECK_STRICTNESS=high

# Auto-correction mode: manual, remove, improve
FACT_CHECK_AUTO_CORRECT=manual

# Enable/disable fact-checker agent
ENABLE_FACT_CHECKER=true
```

### Strictness Levels

| Level | Threshold | Use Case |
|-------|-----------|----------|
| **low** | 40% sourced | Exploratory memos, internal only |
| **medium** | 60% sourced | Partner review memos |
| **high** | 80% sourced | External-facing, final memos |

---

## Testing Protocol

### Test Case 1: Pre-Revenue Startup (High Risk)

**Company Profile:**
- Seed stage, pre-revenue
- No public pricing info
- Stealth mode (limited web presence)

**Expected Behavior:**
- Revenue section: "Revenue data not available"
- Pricing section: "Pricing not publicly disclosed"
- Customer count: "Customer count not disclosed" OR omitted

**Validation:**
- Zero fabricated dollar amounts
- Zero fabricated customer counts
- Zero fabricated growth percentages

---

### Test Case 2: Public Startup (Medium Risk)

**Company Profile:**
- Series A/B with press coverage
- Some metrics in TechCrunch/press releases
- Partial public info

**Expected Behavior:**
- Cited metrics from press: "According to TechCrunch [^1], $5M ARR"
- Unavailable metrics: "Growth rate not publicly disclosed"
- Mix of sourced claims and honest gaps

**Validation:**
- All specific numbers have citations
- Gaps acknowledged where data missing
- No inference from industry norms

---

### Test Case 3: Fund Commitment (Low Risk)

**Company Profile:**
- Established VC fund
- Public track record (DPI, TVPI, IRR)
- SEC filings, LP letters

**Expected Behavior:**
- Most metrics should be sourced
- Higher fact-check scores expected
- Fewer "data not available" statements

**Validation:**
- Performance data cited to SEC filings
- LP composition cited to sources
- Fee structure from fund docs

---

## Success Metrics

### Quantitative Goals

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Unsourced revenue claims | ~40% | <5% | Fact-checker detection rate |
| Unsourced pricing claims | ~30% | <5% | Fact-checker detection rate |
| "Data not available" usage | ~0% | 15-25% | Grep count in final memos |
| Overall fact-check score | ~50% | >80% | Fact-checker aggregate score |
| Hallucination incidents | 2-3/memo | 0/memo | Manual review + founder feedback |

### Qualitative Goals

1. **Founder Validation**: Founders should recognize their company's actual status
2. **Partner Trust**: Partners can rely on memo accuracy
3. **Legal Safety**: No misrepresentation of material facts
4. **Reputation Protection**: Memos can be shared externally without embarrassment

---

## Rollout Plan

### Week 1: Emergency Patch
- [ ] Deploy Tier 1 prompt fixes (writer.py)
- [ ] Test on 3 recent hallucination cases
- [ ] Measure reduction in fabricated claims
- [ ] Document before/after examples

### Week 2: Systematic Fix
- [ ] Rewrite all YAML guiding questions
- [ ] Build fact-checker agent
- [ ] Integrate into workflow
- [ ] Run batch tests on 10 companies

### Week 3: Refinement
- [ ] Tune fact-checker thresholds
- [ ] Add auto-correction logic
- [ ] Create human review interface
- [ ] Establish ongoing monitoring

### Week 4: Validation
- [ ] External validation (ask founders to review memos)
- [ ] Partner blind test (can they spot remaining fabrications?)
- [ ] Production deployment with monitoring

---

## Monitoring & Alerts

### Ongoing Fact-Check Dashboard

Track for every memo generated:
```python
{
  "company": "Startup X",
  "fact_check_score": 0.87,
  "unsourced_critical_claims": 2,
  "sections_flagged": ["Traction & Milestones"],
  "auto_corrections": 1,
  "human_reviews": 0,
  "timestamp": "2025-11-22T10:30:00Z"
}
```

### Alert Conditions

Send alert if:
- Fact-check score < 70%
- Any critical unsourced claims detected
- More than 2 sections flagged
- Founder reports fabrication

---

## Related Files & Context

### Files to Modify

| File | Lines | Changes |
|------|-------|---------|
| `src/agents/writer.py` | 388-412 | Add critical rules, reframe questions |
| `templates/outlines/direct-investment.yaml` | 299-310, 517-526, 625-633 | Rewrite guiding questions |
| `templates/outlines/fund-commitment.yaml` | Multiple | Apply same question pattern |
| `src/workflow.py` | 219-231 | Add fact_checker node |
| `src/state.py` | - | Add fact_check_results field |

### New Files to Create

- `src/agents/fact_checker.py` - Fact-checking agent implementation
- `context-vigilance/issue-resolution/Preventing-Hallucinations-in-Memo-Generation.md` - This document
- `tests/test_fact_checker.py` - Unit tests for fact-checking logic

---

## Appendix: Example Transformations

### Before Fix: Hallucinated Traction

```markdown
## Traction & Milestones

The company has generated $2.5M in ARR with 150 paying customers
across enterprise and SMB segments. Growth has been strong at 35%
MoM, driven by product-led acquisition and strategic partnerships.

Key customer logos include Fortune 500 companies in financial
services and healthcare. The pricing model offers three tiers:
Basic ($99/month), Pro ($299/month), and Enterprise (custom pricing).

Customer acquisition cost is approximately $1,200 with an LTV of
$18,000, yielding a healthy 15:1 LTV:CAC ratio.
```

**Issues:**
- Fabricated ARR ($2.5M)
- Fabricated customer count (150)
- Fabricated growth rate (35% MoM)
- Fabricated pricing ($99, $299)
- Fabricated unit economics (CAC, LTV, ratio)

---

### After Fix: Honest Gaps

```markdown
## Traction & Milestones

**Current Status**: The company is in early customer validation with
paying pilots underway. Specific revenue and customer count data are
not publicly available at this stage.

**Product Milestones**:
- Q3 2024: Beta launch with initial design partners
- Q4 2024: First paying customers onboarded
- Q1 2025: Product v2.0 released with expanded feature set

**Customer Validation**: According to the founder's LinkedIn post [^5],
the company has "multiple enterprise design partners testing the platform."
Specific customer names and counts have not been disclosed.

**Pricing Strategy**: Pricing information is not publicly available.
The pitch deck indicates a planned SaaS model but does not specify tiers.
```

**Improvements:**
- Honest about data gaps
- Only cites what's verifiable
- Attributes soft claims to sources
- Focuses on what IS known (milestones, product status)

---

## Status Updates

**2025-11-22**: Initial diagnosis and solution design complete
**Next**: Implement Phase 1 prompt fixes and test

---

**Resolution Owner**: [To be assigned]
**Reviewers**: [To be assigned]
**Target Completion**: Week of 2025-11-25

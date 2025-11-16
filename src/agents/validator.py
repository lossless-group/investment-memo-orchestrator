"""
Validator Agent - Ensures memos meet Hypernova quality standards.

This agent validates investment memos against a comprehensive checklist
and provides specific feedback for improvements.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import json
import os
from pathlib import Path
from typing import Dict, Any

from ..state import MemoState, ValidationFeedback
from ..artifacts import sanitize_filename, save_validation_artifacts
from ..versioning import VersionManager


def load_style_guide() -> str:
    """Load the style guide from file."""
    style_guide_path = Path(__file__).parent.parent.parent / "templates" / "style-guide.md"
    with open(style_guide_path, "r") as f:
        return f.read()


# System prompt for Validator Agent (style guide will be appended at runtime)
VALIDATOR_SYSTEM_PROMPT_BASE = """You are a rigorous investment memo reviewer for Hypernova Capital.

Your task is to validate investment memos against strict quality standards and provide
specific, actionable feedback for improvements.


VALIDATION CHECKLIST:
1. Structure (0-2 points)
   - Follows exact 10-section format
   - All required sections present
   - Proper formatting and hierarchy

2. Metric Specificity (0-3 points)
   - Uses exact numbers (not vague terms like "large", "many")
   - Includes dates for milestones
   - Names specific companies, people, investors
   - Quantifies market sizes with sources

3. Risk Analysis (0-2 points)
   - Identifies 4-6 specific risks
   - Each risk has concrete mitigation strategy
   - Risks are substantive (not generic)
   - Honest assessment of challenges

4. Tone & Voice (0-2 points)
   - Analytical, not promotional
   - Balanced perspective (acknowledges weaknesses)
   - Avoids superlatives and hype
   - Professional and objective

5. Source Attribution (0-1 point)
   - Market sizing includes sources
   - Claims are backed by data
   - Sources are credible and recent

TOTAL: 10 points maximum

SCORING GUIDELINES:
- 9-10: Exceptional quality, ready for partners
- 8: High quality, minor revisions only
- 6-7: Good foundation, needs improvement in specific areas
- 4-5: Significant issues, major revision needed
- 0-3: Does not meet standards, restart required

BE RIGOROUS: High-quality memos are rare. Don't inflate scores.
Be specific about what needs improvement and why.

OUTPUT FORMAT: Return JSON with this structure:
{
  "overall_score": 7.5,
  "needs_revision": true,
  "category_scores": {
    "structure": 2.0,
    "metric_specificity": 2.0,
    "risk_analysis": 1.5,
    "tone_voice": 1.5,
    "source_attribution": 0.5
  },
  "issues": [
    "Market sizing lacks sources (claims $23B TAM but no citation)",
    "Risk section has only 3 risks instead of required 4-6",
    "Uses vague terms like 'significant traction' instead of specific metrics"
  ],
  "suggestions": [
    "Add source citation for TAM claim (e.g., Gartner, PitchBook)",
    "Expand risks section with regulatory and competitive risks",
    "Replace 'significant traction' with actual numbers (revenue, customers, etc.)"
  ],
  "strengths": [
    "Good founder backgrounds with specific prior companies and roles",
    "Technology section clearly explains approach with benchmarks"
  ]
}
"""


def validator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Validator Agent implementation.

    Validates the drafted memo against Hypernova quality standards.

    Args:
        state: Current memo state containing draft_sections

    Returns:
        Updated state with validation_results and overall_score
    """
    draft_sections = state.get("draft_sections", {})
    if not draft_sections:
        raise ValueError("No draft available. Writer agent must run first.")

    company_name = state["company_name"]
    memo_content = draft_sections.get("full_memo", {}).get("content", "")

    if not memo_content:
        raise ValueError("Draft memo content is empty.")

    # Load style guide
    style_guide = load_style_guide()

    # Initialize Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0.3,  # Lower temperature for consistent evaluation
    )

    # Create validation prompt
    user_prompt = f"""Validate this investment memo for {company_name} against Hypernova quality standards.

MEMO TO VALIDATE:
{memo_content}

Provide a rigorous, honest assessment:
1. Score each category (structure, metrics, risks, tone, sources)
2. Calculate overall score (sum of category scores, max 10)
3. Identify specific issues with examples from the memo
4. Provide actionable suggestions for improvement
5. Note strengths to preserve during revision

Be specific and cite examples from the memo. Don't inflate scores - high quality is rare.

Return your validation as JSON matching the schema in your system prompt."""

    # Build the system prompt with style guide prepended
    system_prompt = (
        f"STYLE GUIDE FOR REFERENCE:\n{style_guide}\n\n"
        f"{VALIDATOR_SYSTEM_PROMPT_BASE}"
    )

    # Call Claude for validation
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]

    response = model.invoke(messages)

    # Parse response as JSON
    try:
        validation_data = json.loads(response.content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        content = response.content
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            validation_data = json.loads(json_str)
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            validation_data = json.loads(json_str)
        else:
            raise ValueError(f"Could not parse validation data as JSON: {content[:200]}...")

    overall_score = validation_data.get("overall_score", 0.0)
    needs_revision = validation_data.get("needs_revision", True)

    # Create validation feedback
    validation_results = {
        "full_memo": ValidationFeedback(
            section_name="full_memo",
            score=overall_score,
            issues=validation_data.get("issues", []),
            suggestions=validation_data.get("suggestions", [])
        )
    }

    # Save validation artifacts
    try:
        # Get version manager
        version_mgr = VersionManager(Path("output"))
        safe_name = sanitize_filename(company_name)
        version = version_mgr.get_next_version(safe_name)

        # Get artifact directory (should already exist)
        output_dir = Path("output") / f"{safe_name}-{version}"

        # Prepare validation data for saving
        validation_artifact = {
            "overall_score": overall_score,
            "needs_revision": needs_revision,
            "category_scores": validation_data.get("category_scores", {}),
            "issues": validation_data.get("issues", []),
            "suggestions": validation_data.get("suggestions", []),
            "strengths": validation_data.get("strengths", []),
            "full_memo": {
                "score": overall_score,
                "issues": validation_data.get("issues", []),
                "suggestions": validation_data.get("suggestions", [])
            }
        }

        # Save validation artifacts
        save_validation_artifacts(output_dir, validation_artifact)

        print(f"Validation artifacts saved to: {output_dir}")
    except Exception as e:
        print(f"Warning: Could not save validation artifacts: {e}")

    # Update state
    return {
        "validation_results": validation_results,
        "overall_score": overall_score,
        "messages": [
            f"Validation completed: Score {overall_score}/10 - "
            f"{'Needs revision' if needs_revision else 'Approved'}"
        ]
    }

"""
Validator Agent - Ensures memos meet Hypernova quality standards.

This agent validates investment memos against a comprehensive checklist
and provides specific feedback for improvements.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

from ..state import MemoState, ValidationFeedback
from ..llm_provider import complete

# Scoring a whole memo is one long call, not an extraction. The CLI carries
# fixed per-call overhead before it sees the prompt, so the 300s provider
# default is tight for a full draft.
_TIMEOUT = 600
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
        state: Current memo state

    Returns:
        Updated state with validation_results and overall_score
    """
    from ..utils import get_output_dir_from_state
    from pathlib import Path

    company_name = state["company_name"]
    firm = state.get("firm")

    # Read from final draft file (new architecture stores sections in files, not state)
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        raise ValueError("No output directory found. Writer agent must run first.")

    # Find final draft file using canonical utility
    from ..final_draft import find_final_draft
    final_draft_path = find_final_draft(output_dir)

    if not final_draft_path or not final_draft_path.exists():
        raise ValueError("No final draft found. Citation assembly must run first.")

    memo_content = final_draft_path.read_text()

    if not memo_content.strip():
        raise ValueError("Draft memo content is empty.")

    # Load style guide
    style_guide = load_style_guide()

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

    # Call Claude for validation.
    #
    # The system prompt is folded into the body rather than sent as a separate
    # role: the CLI path replaces the system prompt with its own extraction
    # preamble, so anything load-bearing — here the scoring schema and the style
    # guide — has to travel in the prompt itself to survive both providers.
    #
    # Temperature was 0.3 "for consistent evaluation"; the provider pins it to 0,
    # which serves that intent more strictly, not less.
    completion = complete(
        f"{system_prompt}\n\n---\n\n{user_prompt}",
        max_tokens=4000,
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        timeout=_TIMEOUT,
    )
    if not completion.ok:
        raise ValueError(
            f"Validation call failed: {completion.error or 'empty response'} "
            f"(provider={completion.provider})"
        )

    # Parse response as JSON
    try:
        validation_data = json.loads(completion.text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        content = completion.text
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
        from ..utils import get_output_dir_from_state

        # Get artifact directory (respects state["output_dir"] for resume)
        output_dir = get_output_dir_from_state(state)

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

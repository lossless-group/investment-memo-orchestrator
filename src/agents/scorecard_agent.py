import os
import json
from pathlib import Path
from typing import Dict, Any

from langchain_anthropic import ChatAnthropic

from ..state import MemoState
from ..utils import get_latest_output_dir


def _load_scorecard_template() -> Dict[str, Any]:
    template_path = Path("templates/scorecards/lp-commits_emerging-managers/hypernova-scorecard.yaml")
    if not template_path.exists():
        raise FileNotFoundError(f"Scorecard template not found: {template_path}")
    import yaml

    with open(template_path) as f:
        return yaml.safe_load(f)


def _load_section_snippets(output_dir: Path) -> Dict[str, str]:
    """Load key memo sections as additional context for the scorecard.

    We keep this lightweight by only pulling the most relevant sections
    for GP and fund evaluation. If files are missing, they are skipped.
    """
    sections_dir = output_dir / "2-sections"
    snippets: Dict[str, str] = {}

    if not sections_dir.exists():
        return snippets

    candidates = {
        "gp_background_credibility": "02-gp-background--credibility.md",
        "fund_strategy_thesis": "03-fund-strategy--thesis.md",
        "portfolio_construction": "04-portfolio-construction.md",
        "track_record_analysis": "05-track-record--analysis.md",
    }

    for key, filename in candidates.items():
        path = sections_dir / filename
        if path.exists():
            try:
                # Read full section; the model can decide what to use
                snippets[key] = path.read_text(encoding="utf-8")
            except Exception:
                continue

    return snippets


def _build_scorecard_prompt(
    state: MemoState,
    scorecard_schema: Dict[str, Any],
    research: Dict[str, Any],
    sections: Dict[str, str],
) -> str:
    company_name = state["company_name"]
    investment_type = state.get("investment_type", "fund")
    # Prefer explicit memo_mode if set on state; otherwise fall back to the
    # original JSON "mode" value where available.
    memo_mode = state.get("memo_mode") or state.get("mode") or "consider"
    company_description = state.get("company_description") or ""
    company_url = state.get("company_url") or ""

    deck_analysis = state.get("deck_analysis") or {}

    context = {
        "company_name": company_name,
        "investment_type": investment_type,
        "memo_mode": memo_mode,
        "company_description": company_description,
        "company_url": company_url,
        "deck_analysis": deck_analysis,
        "research_summary": {
            "company": research.get("company", {}),
            "team": research.get("team", {}),
            "funding": research.get("funding", {}),
            "traction": research.get("traction", {}),
            "recent_news": research.get("recent_news", {}),
        },
        "sections": sections,
    }

    dimensions = scorecard_schema.get("dimensions", {})
    dimension_groups = scorecard_schema.get("dimension_groups", [])

    # Mode-aware guidance: consider vs justify.
    if str(memo_mode).lower() == "justify":
        mode_instructions = (
            "This is a JUSTIFY memo: assume the LP has ALREADY committed to the fund "
            "and is explaining WHY, using the existing memo sections as the primary "
            "source of truth. When information is thin, acknowledge limitations but "
            "avoid generic 'no information available' language; instead, infer a "
            "neutral 3/5 score with a rationale like 'limited disclosed data; based on X "
            "we infer Y while noting this is an area to monitor.'"
        )
    else:
        mode_instructions = (
            "This is a CONSIDER memo: the LP is evaluating whether to commit. It is "
            "acceptable to highlight missing data as a risk, but you must still ground "
            "all judgments in the provided context and avoid speculation beyond it."
        )

    return f"""You are an LP evaluator using Hypernova Capital's Emerging Manager Scorecard to assess a GP / fund.

MODE: {memo_mode.upper()}.

MODE-SPECIFIC GUIDANCE:
{mode_instructions}

COMPANY CONTEXT (FROM INTERNAL ARTIFACTS ONLY):
{json.dumps(context, indent=2)}

SCORECARD SCHEMA (YAML, PARTIAL):
{json.dumps({"dimension_groups": dimension_groups, "dimensions": dimensions}, indent=2)}

TASK:
1. Assign a score from 1 to 5 for EACH of the 12 dimensions.
2. For each dimension, select the percentile label implied by the score using the mapping:
   - 5 => "Top 2-5%"
   - 4 => "Top 10-25%"
   - 3 => "Top 50%"
   - 2 => "Bottom 50%"
   - 1 => "Bottom 25%"
3. For each dimension, write a 1-2 sentence rationale grounded ONLY in the provided context (including memo sections). Prefer concrete evidence from sections over generic statements about missing data.
4. When data is limited for a dimension, default to score 3/5 and explicitly note that the score reflects limited disclosed data plus any reasonable inference from the memo, rather than saying there is "no information".
5. Then produce three HORIZONTAL markdown tables (one per group) in this exact format:

   | Empathy | Theory of Market | Ecosystem Imprint | Hustle |
   |---------|------------------|-------------------|--------|
   | 4/5 | 4/5 | 5/5 | 5/5 |
   | Top 25% | Top 5% | Top 5% | Top 2% |
   | [Short rationale...] | [Short rationale...] | [Short rationale...] | [Short rationale...] |

6. After the tables, write a short markdown summary:
   - Overall assessment paragraph
   - Bullet list of standout strengths (scores of 5)
   - Bullet list of areas of concern (scores of 1-2)
   - Final recommendation: PASS / CONSIDER / COMMIT, with one-sentence rationale.

REQUIREMENTS:
- Base ALL judgments on the provided context (deck analysis, research JSON, and memo sections). Do NOT invent facts that contradict these artifacts.
- Do NOT add citations or new external research.
- Do NOT mention this instruction block or the YAML; just output the markdown tables and summary.

OUTPUT FORMAT (MARKDOWN ONLY):
1. Group 1 table
2. Group 2 table
3. Group 3 table
4. Overall markdown summary as described above.
"""


def scorecard_agent(state: MemoState) -> Dict[str, Any]:
    company_name = state["company_name"]
    firm = state.get("firm")
    outline_name = state.get("outline_name")
    investment_type = state.get("investment_type", "direct")

    if investment_type != "fund":
        return {"messages": ["Scorecard agent skipped - investment_type is not 'fund'"]}

    if outline_name != "lpcommit-emerging-manager":
        return {"messages": ["Scorecard agent skipped - outline is not lpcommit-emerging-manager"]}

    # Get output directory (respects state["output_dir"] for resume, falls back to auto-detect)
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        return {"messages": ["Scorecard agent skipped - no output directory found"]}

    # Load any existing section content to give the model richer context.
    sections = _load_section_snippets(output_dir)

    state_path = output_dir / "state.json"
    research_path = output_dir / "1-research.json"

    if research_path.exists():
        with open(research_path) as f:
            research = json.load(f)
    else:
        research = {}

    scorecard_schema = _load_scorecard_template()

    prompt = _build_scorecard_prompt(state, scorecard_schema, research, sections)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0,
    )

    response = model.invoke(prompt)
    markdown_scorecard = response.content

    scorecard_md_path = output_dir / "scorecard.md"
    with open(scorecard_md_path, "w") as f:
        f.write("# Emerging Manager Scorecard\n\n")
        f.write(markdown_scorecard.strip() + "\n")

    messages = [
        f"Scorecard generated for {company_name} using Hypernova emerging manager framework",
        f"Saved to {scorecard_md_path}",
    ]

    return {"messages": messages, "scorecard_path": str(scorecard_md_path)}

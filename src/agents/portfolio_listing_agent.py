"""Portfolio Listing Agent.

Builds a structured view of the fund's current portfolio and authors a
`Current Portfolio` subsection under Portfolio Construction.

Responsibilities:

1. Read deck/research context from MemoState (and/or state.json) and
   identify all portfolio companies mentioned.
2. Capture ALL available details for each portfolio company from the
   context (name, stage, theme, any textual notes) and let the LLM
   standardize them.
3. Attempt to locate the fund's portfolio page on the firm website and
   per-company URLs/logo URLs, using the LLM's web capabilities.
4. Produce:
   - `current_portfolio.json` in the latest output directory, with a
     structured list of companies and metadata.
   - A markdown subsection titled `## Current Portfolio` saved into the
     Portfolio Construction section file (04-portfolio-construction.md),
     appending or creating as needed.
5. Call `link_enrichment_agent` afterwards so that any remaining
   unlinked entities get links where possible.

NOTE: This agent intentionally delegates heavy parsing and web lookup to
Anthropic (ChatAnthropic), similar to other agents in this project.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import MemoState
from ..utils import get_latest_output_dir
from .link_enrichment import link_enrichment_agent


PORTFOLIO_LISTING_SYSTEM_PROMPT = """You are a portfolio listing specialist for
LP commitment memos about venture funds.

Your job is to, given structured context about a fund (deck analysis,
research JSON, and state), EXHAUSTIVELY enumerate current portfolio
companies and produce both:

1. A structured JSON object describing the portfolio companies
2. A markdown subsection titled `## Current Portfolio`

RULES:
- Only include companies that are explicitly or very strongly implied to
  be in the fund's portfolio or track record.
- DO NOT invent company names that do not appear anywhere in the
  provided context.
- If you are unsure whether a company is in the portfolio, you may
  include it but clearly mark `role`: "uncertain".
- Use web research ONLY to enrich details (descriptions, URLs, logo
  URLs) for companies that are already surfaced from context.

For each portfolio company you output in JSON, include fields where
available:
- name (string, REQUIRED)
- url (string, optional)
- logo_url (string, optional)
- stage (string, optional: Seed, Series A, etc.)
- theme_or_sector (string, optional)
- role (string, optional: "core fund", "SPV", "track record", "uncertain")
- notes (string, optional, capturing ALL relevant details you see in the
  context about this company and its relationship to the fund)

When searching for URLs and logo URLs:
- First look for a portfolio page on the fund's website
  (e.g., /portfolio, nav links, or obvious portfolio sections).
- Prefer the company's own website (https://company.com) as the main URL.
- For logo_url, prefer a reasonably stable image URL from the portfolio
  page or company site if one is clearly available. If not, omit logo.
- NEVER guess URLs or logos that are not clearly discoverable.

OUTPUT FORMAT (CRITICAL):

Return your answer in TWO parts, exactly in this order:

JSON:
<JSON object here>

MARKDOWN:
<markdown section here>

Where:
- The JSON object has a top-level key `portfolio_companies` that is a
  list of company objects.
- The markdown section starts with a line: `## Current Portfolio` and
  then lists each company as a bullet:

  - **Company Name** — 50-100 character description. Theme: X. Stage: Y. [Website](https://...)

If you truly cannot identify ANY portfolio companies from the context,
return:

JSON:
{"portfolio_companies": []}

MARKDOWN:
## Current Portfolio

No portfolio companies were identifiable from the current deck and
research context.
"""


def portfolio_listing_agent(state: MemoState) -> Dict[str, Any]:
    """Portfolio Listing Agent.

    Uses deck/research context to build `current_portfolio.json` and
    append a `Current Portfolio` subsection to the Portfolio Construction
    section. Then runs link enrichment so portfolio names get links.
    """

    company_name = state["company_name"]
    firm = state.get("firm")

    # Determine latest output directory (firm-aware)
    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        print(f"⊘ Portfolio listing skipped - no output directory for {company_name}")
        return {"messages": ["Portfolio listing skipped - no output directory"]}

    state_file = output_dir / "state.json"
    research_file = output_dir / "1-research.json"

    state_data: Dict[str, Any] = {}
    research_data: Dict[str, Any] = {}

    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text())
        except Exception as e:
            print(f"⚠ Failed to load state.json for portfolio listing: {e}")

    if research_file.exists():
        try:
            research_data = json.loads(research_file.read_text())
        except Exception as e:
            print(f"⚠ Failed to load 1-research.json for portfolio listing: {e}")

    # Build compact context for the LLM
    deck_analysis = state_data.get("deck_analysis", {})
    research_company = research_data.get("company", {}) if isinstance(research_data, dict) else {}
    research_traction = research_data.get("traction", {}) if isinstance(research_data, dict) else {}

    context = {
        "company_name": state_data.get("company_name", company_name),
        "company_url": state_data.get("company_url"),
        "deck_analysis": deck_analysis,
        "research_company": research_company,
        "research_traction": research_traction,
    }

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0,
    )

    print("\n📊 Building portfolio company listing (Current Portfolio section)...")

    system_msg = SystemMessage(content=PORTFOLIO_LISTING_SYSTEM_PROMPT)
    user_msg = HumanMessage(
        content=(
            "Use the following structured context (state + deck_analysis + research) "
            "to build the portfolio listing.\n\nCONTEXT:\n" + json.dumps(context, indent=2)
        )
    )

    try:
        response = model.invoke([system_msg, user_msg])
        raw_content: str = response.content if isinstance(response.content, str) else str(response.content)
    except Exception as e:
        print(f"⊘ Portfolio listing failed: {e}")
        return {"messages": [f"Portfolio listing failed: {e}"]}

    # Parse the two-part response
    json_part: str = ""
    markdown_part: str = ""

    if "\nMARKDOWN:" in raw_content:
        before, after = raw_content.split("\nMARKDOWN:", 1)
        if before.startswith("JSON:"):
            json_part = before[len("JSON:") :].strip()
            markdown_part = after.strip()
        else:
            json_part = before.strip()
            markdown_part = after.strip()
    else:
        # Fallback: try to treat whole thing as markdown, empty JSON
        markdown_part = raw_content.strip()
        json_part = "{\"portfolio_companies\": []}"

    portfolio_json: Dict[str, Any]
    try:
        portfolio_json = json.loads(json_part)
        if not isinstance(portfolio_json, dict) or "portfolio_companies" not in portfolio_json:
            # Normalize to expected structure
            portfolio_json = {"portfolio_companies": portfolio_json}
    except Exception:
        print("⚠ Could not parse JSON portion of portfolio listing; using empty list.")
        portfolio_json = {"portfolio_companies": []}

    # Save JSON artifact
    current_portfolio_file = output_dir / "current_portfolio.json"
    try:
        current_portfolio_file.write_text(json.dumps(portfolio_json, indent=2))
        print(f"✓ Saved current_portfolio.json: {current_portfolio_file}")
    except Exception as e:
        print(f"⚠ Failed to write current_portfolio.json: {e}")

    # Append (or create) Current Portfolio subsection in Portfolio Construction
    sections_dir = output_dir / "2-sections"
    sections_dir.mkdir(exist_ok=True)
    portfolio_section_file = sections_dir / "04-portfolio-construction.md"

    current_portfolio_md = markdown_part.strip()
    if not current_portfolio_md.startswith("## Current Portfolio"):
        current_portfolio_md = "## Current Portfolio\n\n" + current_portfolio_md

    try:
        if portfolio_section_file.exists():
            existing = portfolio_section_file.read_text()
            # Avoid duplicating if a Current Portfolio section already exists
            if "## Current Portfolio" in existing:
                # Replace existing Current Portfolio section
                parts = existing.split("## Current Portfolio", 1)
                # Keep everything before, replace from Current Portfolio onward
                new_content = parts[0].rstrip() + "\n\n" + current_portfolio_md + "\n"
            else:
                new_content = existing.rstrip() + "\n\n" + current_portfolio_md + "\n"
        else:
            new_content = "# Portfolio Construction\n\n" + current_portfolio_md + "\n"

        portfolio_section_file.write_text(new_content)
        print(f"✓ Updated portfolio construction section with Current Portfolio subsection: {portfolio_section_file}")
    except Exception as e:
        print(f"⚠ Failed to update portfolio construction section: {e}")

    # Run link enrichment to add hyperlinks where possible
    try:
        link_enrichment_agent(state)
    except Exception as e:
        print(f"⚠ Link enrichment after portfolio listing failed: {e}")

    return {
        "messages": [
            f"Portfolio listing completed for {company_name} - "
            f"JSON + Current Portfolio subsection generated."
        ]
    }

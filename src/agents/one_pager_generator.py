"""
One-Pager Generator Agent — Distills the full memo into a single-page visual summary.

Reads the final draft and state.json, uses Claude to extract content into fixed
slots (headline, bullets, metrics, market stats, etc.), renders an HTML template
with CSS grid layout, and converts to PDF via WeasyPrint.

Output artifacts:
  8-one-pager.html         — Standalone HTML one-pager
  8-one-pager.pdf          — PDF export (single page, US Letter)
  8-one-pager-content.json — Extracted content slots (for debugging/iteration)

Pipeline position: runs after integrate_scorecard, before finalize.
Can also be called standalone via cli/generate_one_pager.py.
"""

import os
import json
import re
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from ..state import MemoState


DIRECT_INVESTMENT_SCHEMA = {
    "headline_thesis": "string, max 2 sentences summarizing the investment opportunity",
    "key_bullets": ["string, max 30 words each, exactly 3 bullets, bold **key terms**"],
    "stage": "string, 1-2 words (e.g., 'Seed', 'Series A')",
    "round_size": "string (e.g., '$5M') or null if not available",
    "valuation": "string (e.g., '$25M pre-money') or null",
    "lead_investors": "string, 1-2 investor names or null",
    "syndicate_participants": ["string, names of other investors in the round, up to 6"],
    "location": "string, City, State or null",
    "team_size": "string (e.g., '12 people') or null",
    "key_metrics": [{"label": "string", "value": "string"}],
    "cap_table_highlights": [{"name": "string (entity name)", "percentage": "string (e.g., '54%')"}],
    "market_stats": [{"category": "string", "stat": "string with **bold figure**"}],
    "technology_summary": "string, 2-3 sentences on product/technology",
    "competitive_positioning": "string, 2-3 sentences on competitive landscape",
    "traction_milestones": ["string, max 15 words each, 3-4 items"],
    "recommendation": "string, 1-2 sentences",
    "recommendation_verdict": "PASS or CONSIDER or COMMIT",
    "top_sources": ["string, abbreviated source title, 3-5 items"],
    "company_tagline": "string, one-line company description, max 10 words"
}

FUND_COMMITMENT_SCHEMA = {
    "headline_thesis": "string, max 2 sentences",
    "key_bullets": ["string, max 30 words each, exactly 3"],
    "target_fund_size": "string (e.g., '$50MM')",
    "gp_commit": "string (e.g., '5%')",
    "fund_term": "string (e.g., '10 years')",
    "fees": "string (e.g., '2/20')",
    "investment_period": "string (e.g., '5 years')",
    "location": "string or null",
    "governance": "string (e.g., '3-Member LPAC') or null",
    "key_metrics": [{"label": "string", "value": "string"}],
    "market_stats": [{"category": "string", "stat": "string with **bold figure**"}],
    "track_record_highlights": "string, 2-3 sentences",
    "competitive_positioning": "string, 2-3 sentences",
    "traction_milestones": ["string, max 15 words each, 3-4 items"],
    "recommendation": "string, 1-2 sentences",
    "recommendation_verdict": "PASS or CONSIDER or COMMIT",
    "top_sources": ["string, abbreviated source title, 3-5 items"],
    "company_tagline": "string, one-line fund description, max 10 words"
}


def _build_extraction_prompt(
    final_draft_text: str,
    state: Dict[str, Any],
    investment_type: str
) -> str:
    schema = DIRECT_INVESTMENT_SCHEMA if investment_type == "direct" else FUND_COMMITMENT_SCHEMA

    return f"""You are extracting content from an investment memo into fixed slots for a one-page visual summary.

RULES:
- Use EXACT numbers, names, and metrics from the memo. Do not round or paraphrase.
- If data for a slot is not available in the memo, return null for that slot.
- Maximum lengths are HARD LIMITS — truncate if needed.
- Do NOT add any information not present in the memo.
- For key_bullets: select the 3 most compelling points that would convince
  an investor to keep reading. Bold key terms using **term** markdown syntax.
- For market_stats: include the bold figure inline like "TAM projected to reach **$50B by 2030**"
- For cap_table_highlights: extract from cap table data if mentioned, otherwise null
- For syndicate_participants: list investors beyond the lead, if mentioned

INVESTMENT TYPE: {investment_type}
COMPANY: {state.get('company_name', 'Unknown')}
STAGE: {state.get('company_stage', 'Unknown')}

===== FULL MEMO =====
{final_draft_text[:30000]}
=====================

Extract content into this JSON structure. Respond with ONLY valid JSON:

{json.dumps(schema, indent=2)}"""


def _parse_extraction_response(response_text: str) -> Dict[str, Any]:
    """Parse Claude's JSON response, handling markdown code fences."""
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            return json.loads(text[brace_start:brace_end + 1])
        raise


def _slots_to_html(slots: Dict[str, Any], investment_type: str) -> Dict[str, str]:
    """Convert raw slot values into HTML fragments for template substitution."""
    html = {}

    # Key bullets
    bullets = slots.get("key_bullets") or []
    html["key_bullets_html"] = "\n".join(
        f'<li>{_md_bold_to_html(b)}</li>' for b in bullets[:3]
    )

    # Sidebar deal fields
    if investment_type == "direct":
        fields = [
            ("Stage", slots.get("stage")),
            ("Round Size", slots.get("round_size")),
            ("Valuation", slots.get("valuation")),
            ("Lead Investor", slots.get("lead_investors")),
            ("Location", slots.get("location")),
            ("Team", slots.get("team_size")),
        ]
    else:
        fields = [
            ("Fund Size", slots.get("target_fund_size")),
            ("GP Commit", slots.get("gp_commit")),
            ("Fund Term", slots.get("fund_term")),
            ("Fees", slots.get("fees")),
            ("Inv. Period", slots.get("investment_period")),
            ("Location", slots.get("location")),
            ("Governance", slots.get("governance")),
        ]
    html["sidebar_deal_fields"] = "\n".join(
        f'<div class="sidebar-field"><div class="sidebar-label">{label}</div>'
        f'<div class="sidebar-value">{value}</div></div>'
        for label, value in fields if value
    )

    # Key metrics
    metrics = slots.get("key_metrics") or []
    html["sidebar_metrics"] = "\n".join(
        f'<div class="sidebar-metric">'
        f'<span class="sidebar-metric-label">{m.get("label", "")}</span>'
        f'<span class="sidebar-metric-value">{m.get("value", "")}</span></div>'
        for m in metrics[:5]
    )

    # Cap table
    cap = slots.get("cap_table_highlights") or []
    if cap:
        html["sidebar_cap_table"] = "\n".join(
            f'<div class="sidebar-cap-entry">'
            f'<span class="sidebar-cap-name">{c.get("name", "")}</span>'
            f'<span class="sidebar-cap-pct">{c.get("percentage", "")}</span></div>'
            for c in cap
        )
    else:
        html["sidebar_cap_table"] = ""

    # Market stats
    stats = slots.get("market_stats") or []
    html["market_stats_html"] = "\n".join(
        f'<div class="stat-row">'
        f'<span class="stat-category">{s.get("category", "")}</span>'
        f'<span class="stat-value">{_md_bold_to_html(s.get("stat", ""), css_class="stat-figure")}</span></div>'
        for s in stats[:6]
    )

    # Technology / Track record
    tech = slots.get("technology_summary") or slots.get("track_record_highlights") or ""
    html["technology_summary"] = _md_bold_to_html(tech)

    # Competitive positioning
    html["competitive_positioning"] = _md_bold_to_html(slots.get("competitive_positioning") or "")

    # Traction milestones
    milestones = slots.get("traction_milestones") or []
    html["traction_milestones_html"] = "\n".join(
        f'<li>{_md_bold_to_html(m)}</li>' for m in milestones[:4]
    )

    # Syndicate pills
    syndicate = slots.get("syndicate_participants") or []
    lead = slots.get("lead_investors") or ""
    pills = []
    if lead:
        pills.append(f'<span class="pill pill-lead">{lead} (Lead)</span>')
    for inv in syndicate[:6]:
        if inv and inv != lead:
            pills.append(f'<span class="pill">{inv}</span>')
    html["syndicate_pills_html"] = "\n".join(pills)

    # Recommendation
    html["recommendation"] = _md_bold_to_html(slots.get("recommendation") or "")
    html["recommendation_verdict"] = slots.get("recommendation_verdict") or ""

    # Sources
    sources = slots.get("top_sources") or []
    html["top_sources"] = " · ".join(sources[:5])

    # Simple pass-throughs
    html["headline_thesis"] = _md_bold_to_html(slots.get("headline_thesis") or "")
    html["company_tagline"] = slots.get("company_tagline") or ""

    return html


def _md_bold_to_html(text: str, css_class: str = "") -> str:
    """Convert **bold** markdown to <strong> tags."""
    if not text:
        return ""
    cls = f' class="{css_class}"' if css_class else ""
    return re.sub(r'\*\*(.+?)\*\*', rf'<strong{cls}>\1</strong>', text)


def _remove_empty_slots(html_content: str) -> str:
    """Remove HTML elements with data-slot attribute when their content is empty."""
    pattern = r'<div[^>]*data-slot="[^"]*"[^>]*>\s*<div class="card-header">[^<]*</div>\s*<div class="card-body[^"]*">\s*</div>\s*</div>'
    html_content = re.sub(pattern, '', html_content)

    pattern = r'<div[^>]*data-slot="[^"]*"[^>]*>\s*<div class="sidebar-card-header">[^<]*</div>\s*</div>'
    html_content = re.sub(pattern, '', html_content)

    pattern = r'<div[^>]*data-slot="[^"]*"[^>]*>\s*<hr[^>]*>\s*<div class="sidebar-card-header">[^<]*</div>\s*</div>'
    html_content = re.sub(pattern, '', html_content)

    return html_content


def render_one_pager(
    slots: Dict[str, Any],
    state: Dict[str, Any],
    brand_config=None,
    mode: str = "light"
) -> str:
    """
    Render the one-pager HTML from extracted slots.

    Args:
        slots: Extracted content slots from LLM
        state: Pipeline state
        brand_config: BrandConfig object (optional, loads from firm if not provided)
        mode: "light" or "dark"

    Returns:
        Rendered HTML string
    """
    from ..branding import BrandConfig

    if brand_config is None:
        firm = state.get("firm")
        brand_config = BrandConfig.load(brand_name=firm, firm=firm)

    investment_type = state.get("investment_type", "direct")
    html_fragments = _slots_to_html(slots, investment_type)

    # Load template
    template_path = Path(__file__).parent.parent.parent / "templates" / "one-pager-template.html"
    template = template_path.read_text(encoding="utf-8")

    # Determine brand colors based on mode
    if mode == "dark" and brand_config.colors.dark_theme:
        bg = brand_config.colors.dark_theme.get("background", brand_config.colors.background)
        text_dark = brand_config.colors.dark_theme.get("text_header", brand_config.colors.text_dark)
        text_light = brand_config.colors.dark_theme.get("text_body", brand_config.colors.text_light)
    elif brand_config.colors.light_theme:
        bg = brand_config.colors.light_theme.get("background", brand_config.colors.background)
        text_dark = brand_config.colors.light_theme.get("text_header", brand_config.colors.text_dark)
        text_light = brand_config.colors.light_theme.get("text_body", brand_config.colors.text_light)
    else:
        bg = brand_config.colors.background
        text_dark = brand_config.colors.text_dark
        text_light = brand_config.colors.text_light

    # Substitute brand variables
    replacements = {
        "{{brand_primary}}": brand_config.colors.primary,
        "{{brand_secondary}}": brand_config.colors.secondary,
        "{{brand_background}}": bg,
        "{{brand_background_alt}}": brand_config.colors.background_alt,
        "{{brand_text_dark}}": text_dark,
        "{{brand_text_light}}": text_light,
        "{{brand_font_family}}": f"'{brand_config.fonts.family}'",
        "{{brand_font_fallback}}": brand_config.fonts.fallback,
        "{{body_class}}": "dark-mode" if mode == "dark" else "",
        "{{company_name}}": state.get("company_name", ""),
    }

    for key, value in replacements.items():
        template = template.replace(key, value or "")

    # Substitute content slots
    for key, value in html_fragments.items():
        template = template.replace("{{" + key + "}}", value or "")

    # Company logo (trademark)
    trademark = state.get("company_trademark_light") if mode == "light" else state.get("company_trademark_dark")
    trademark = trademark or state.get("company_trademark_light") or state.get("company_trademark_dark")
    if trademark:
        logo_html = f'<img src="{trademark}" alt="{state.get("company_name", "")}" style="max-width: 1.6in; height: auto;">'
    else:
        logo_html = ""
    template = template.replace("{{company_logo}}", logo_html)

    # VC firm logo (always use dark_mode version since footer background is dark)
    vc_logo = ""
    if brand_config.logo:
        logo_url = brand_config.logo.dark_mode or brand_config.logo.light_mode
        if logo_url:
            vc_logo = f'<img src="{logo_url}" alt="{brand_config.logo.alt or ""}" style="height: 18px; width: auto;">'
    template = template.replace("{{vc_firm_logo}}", vc_logo)

    # Footer contact
    template = template.replace("{{footer_contact}}", state.get("company_url") or "")

    # Clean up any remaining unreplaced placeholders
    template = re.sub(r'\{\{[a-z_]+\}\}', '', template)

    # Remove empty slot containers
    template = _remove_empty_slots(template)

    return template


def one_pager_generator_agent(state: MemoState) -> Dict[str, Any]:
    """
    One-Pager Generator Agent.

    Reads the final draft, extracts content into fixed slots via Claude,
    renders HTML template, converts to PDF.

    Args:
        state: Current memo state

    Returns:
        State updates with one_pager_path and messages
    """
    company_name = state["company_name"]
    investment_type = state.get("investment_type", "direct")

    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        print("⊘ One-pager skipped - no output directory")
        return {"messages": ["One-pager skipped - no output directory"]}

    # Find final draft
    from ..final_draft import find_final_draft, read_final_draft
    final_draft_path = find_final_draft(output_dir)
    if not final_draft_path:
        print("⊘ One-pager skipped - no final draft found")
        return {"messages": ["One-pager skipped - no final draft"]}

    final_draft_text = read_final_draft(output_dir)

    print("\n" + "=" * 70)
    print(f"📄 GENERATING ONE-PAGER FOR {company_name}")
    print("=" * 70)

    # Extract content via Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⊘ One-pager skipped - no ANTHROPIC_API_KEY")
        return {"messages": ["One-pager skipped - no API key"]}

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    prompt = _build_extraction_prompt(final_draft_text, state, investment_type)

    print("  Extracting content slots via Claude...")
    try:
        response = client.messages.create(
            model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
            max_tokens=2000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        slots = _parse_extraction_response(response.content[0].text)
    except Exception as e:
        print(f"  ❌ Content extraction failed: {e}")
        return {"messages": [f"One-pager failed: {e}"]}

    # Save extracted content
    content_path = output_dir / "8-one-pager-content.json"
    with open(content_path, "w") as f:
        json.dump(slots, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Content slots saved: {content_path.name}")

    # Render HTML
    html_content = render_one_pager(slots, state, mode="light")
    html_path = output_dir / "8-one-pager.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"  ✓ HTML rendered: {html_path.name}")

    # Convert to PDF
    try:
        from weasyprint import HTML
        pdf_path = output_dir / "8-one-pager.pdf"
        HTML(string=html_content, base_url=str(output_dir)).write_pdf(str(pdf_path))
        print(f"  ✓ PDF generated: {pdf_path.name}")
    except Exception as e:
        print(f"  ⚠️  PDF generation failed: {e}")
        pdf_path = None

    print(f"{'=' * 70}\n")

    return {
        "messages": [f"✓ One-pager generated: {html_path.name}" + (f" + {pdf_path.name}" if pdf_path else "")]
    }

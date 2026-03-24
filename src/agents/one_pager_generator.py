"""
One-Pager Generator Agent — Distills the full memo into a single-page visual summary.

Two-step process:
  Step 1: Claude extracts content from the memo into structured JSON slots
  Step 2: Claude designs and generates a complete, branded single-page HTML layout

This approach gives Claude creative control over the visual design while
constraining it with the brand config (colors, fonts, logos) and content slots.
No fixed HTML template — the layout is generated fresh each time.

Output artifacts:
  8-one-pager.html         — Standalone HTML one-pager (Claude-designed)
  8-one-pager.pdf          — PDF export (single page, US Letter)
  8-one-pager-content.json — Extracted content slots (for debugging/iteration)

Pipeline position: runs after integrate_scorecard, before finalize.
Can also be called standalone via cli/generate_one_pager.py.
"""

import os
import json
import re
from typing import Dict, Any, Optional
from pathlib import Path

from ..state import MemoState


# ── Step 1: Content extraction schemas ──────────────────────────────

DIRECT_INVESTMENT_SCHEMA = {
    "headline_lede": "string, ONE sentence max 20 words — the single most compelling hook for this investment. Punchy, bold, attention-grabbing.",
    "headline_extended": "string, 1-2 additional sentences expanding on the lede with key context (market size, positioning, timing). This is secondary to the lede.",
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
    "headline_lede": "string, ONE sentence max 20 words — the single most compelling hook. Punchy, attention-grabbing.",
    "headline_extended": "string, 1-2 additional sentences expanding on the lede with key context.",
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
    """Build the content extraction prompt (Step 1)."""
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


def _build_design_prompt(
    slots: Dict[str, Any],
    brand_config,
    state: Dict[str, Any],
    mode: str = "light"
) -> str:
    """Build the HTML design prompt (Step 2)."""

    # Resolve brand colors for the requested mode
    if mode == "dark" and brand_config.colors.dark_theme:
        bg = brand_config.colors.dark_theme.get("background", brand_config.colors.background)
        text_body = brand_config.colors.dark_theme.get("text_body", brand_config.colors.text_light)
        text_header = brand_config.colors.dark_theme.get("text_header", brand_config.colors.text_dark)
    elif brand_config.colors.light_theme:
        bg = brand_config.colors.light_theme.get("background", brand_config.colors.background)
        text_body = brand_config.colors.light_theme.get("text_body", brand_config.colors.text_light)
        text_header = brand_config.colors.light_theme.get("text_header", brand_config.colors.text_dark)
    else:
        bg = brand_config.colors.background
        text_body = brand_config.colors.text_light
        text_header = brand_config.colors.text_dark

    # Company logo
    trademark = state.get("company_trademark_light") if mode == "light" else state.get("company_trademark_dark")
    trademark = trademark or state.get("company_trademark_light") or state.get("company_trademark_dark") or ""

    # VC firm logo (always use dark_mode for dark headers/footers)
    vc_logo = ""
    if brand_config.logo:
        vc_logo = brand_config.logo.dark_mode or brand_config.logo.light_mode or ""

    return f"""You are an expert UI designer creating a single-page investment summary as a self-contained HTML document.

DESIGN BRIEF:
Create a polished, professional, information-dense one-pager for an investment deal.
It must fit on exactly ONE US Letter page (8.5" x 11") when printed or exported to PDF.
The design should feel like a premium VC deal teaser — clean, modern, and scannable.

BRAND CONFIGURATION:
- Primary color (dark, for headers/sidebar backgrounds): {brand_config.colors.primary}
- Accent color (for links, highlights, labels, CTAs): {brand_config.colors.secondary}
- Page background: {bg}
- Body text color: {text_body}
- Header text color: {text_header}
- Subtle background (for cards, callouts): {brand_config.colors.background_alt}
- Font family: {brand_config.fonts.family}, {brand_config.fonts.fallback}
- Header font: {brand_config.fonts.header_family or brand_config.fonts.family}
- Mode: {mode}

LOGOS — DO NOT ADD ANY <img> TAGS FOR LOGOS. Instead, use these exact placeholder markers:
- Where the VC firm logo should go (top of sidebar): write exactly %%VC_FIRM_LOGO%%
- Where the company logo should go (below VC logo in sidebar): write exactly %%COMPANY_LOGO%%
- Do NOT use <img> tags for any logos. Only use the placeholder text above.
- Each placeholder must appear EXACTLY ONCE.

NAMES:
- VC firm name: {brand_config.company.name}
- Company name: {state.get('company_name', '')}

CONTENT TO DISPLAY:
{json.dumps(slots, indent=2)}

CRITICAL — ENTITY NAME:
The company name is EXACTLY "{state.get('company_name', '')}". Do NOT change, shorten, or
"correct" the company name. For example, do NOT change "Metabologic" to "Metabolic".
Use the exact company name as provided everywhere it appears in the HTML.

FRAMING:
This one-pager is {brand_config.company.name} presenting its investment in {state.get('company_name', '')}.
The VC firm is the author/presenter. The company being invested in is the subject.

LAYOUT REQUIREMENTS:
1. Two-column layout: left sidebar (~28-30% width) for deal overview data, right main area for narrative
2. The sidebar top should read as "{brand_config.company.name} is syndicating an investment in {state.get('company_name', '')}":
   - VC FIRM LOGO first (the presenter) via %%VC_FIRM_LOGO%% placeholder
   - A small label like "is syndicating" or "presents" in subtle text
   - Then the COMPANY LOGO via %%COMPANY_LOGO%% placeholder
   - The company tagline in small text below the logo
   - Do NOT add a large text header with the company name — the logo already communicates the identity. If the logo is clear and legible, a redundant text header wastes space.
   - Then deal overview fields (stage, round, valuation, etc.), key metrics, and cap table highlights if available
3. The main area header has TWO headline elements:
   - "headline_lede": The hook — render this in bold, ~12-13pt, max 2 lines. This is the eye-catcher.
   - "headline_extended": Supporting context — render this in regular weight, ~9pt, immediately below the lede. Smaller, secondary, flows naturally after the lede.
   Then 3 key bullets below both.
4. Below that, use a card-based grid (2 columns) for: Market Opportunity, Technology/Product, Competitive Landscape, Traction & Milestones
5. Each card has a colored header bar (using primary color) and dense body text
6. Include a Syndicate/Investors section if investor data is available (use pill/badge styling)
7. A recommendation callout box near the bottom (bordered with accent color, showing verdict prominently)
8. Small sources footer
9. Page footer with VC firm logo, and "Proprietary & Confidential"
10. Omit any section where the data is null or empty — don't show empty cards

TECHNICAL REQUIREMENTS:
- Self-contained HTML with all CSS inline in a <style> block
- Use @page {{ size: letter; margin: 0; }} for PDF export
- For PRINT/PDF: Set html/body to exactly 8.5in x 11in with overflow: hidden
- For SCREEN: Allow scrolling so the page is viewable in a browser. Use a @media screen rule that sets overflow: auto and min-height instead of fixed height
- Use CSS grid or flexbox for layout
- All text must be sized to fit on one page — be conservative with font sizes
- Use the brand colors consistently throughout
- If a logo URL is provided, use <img src="URL"> tags with the EXACT URL as given — do NOT modify, shorten, or "fix" any URLs
- CRITICAL: Copy all URLs character-for-character. Do not change "Metabologic" to "Metabolic" or alter any part of a URL.
- Do NOT use JavaScript
- Do NOT use external resources (all CSS inline)
- Respond with ONLY the complete HTML document, no explanation or markdown fences"""


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


def _parse_html_response(response_text: str) -> str:
    """Parse Claude's HTML response, stripping any markdown fences."""
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r'^```(?:html)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

    # Ensure it starts with <!DOCTYPE or <html
    if not text.startswith("<!") and not text.startswith("<html"):
        # Try to find HTML start
        html_start = text.find("<!DOCTYPE")
        if html_start < 0:
            html_start = text.find("<html")
        if html_start >= 0:
            text = text[html_start:]

    return text


def render_one_pager(
    slots: Dict[str, Any],
    state: Dict[str, Any],
    brand_config=None,
    mode: str = "light"
) -> str:
    """
    Generate the one-pager HTML by having Claude design the layout.

    Step 2 of the pipeline: Claude receives the brand config and extracted
    content slots, and generates a complete self-contained HTML page.

    Args:
        slots: Extracted content slots from Step 1
        state: Pipeline state
        brand_config: BrandConfig object (optional, loads from firm if not provided)
        mode: "light" or "dark"

    Returns:
        Complete HTML string designed by Claude
    """
    from ..branding import BrandConfig

    if brand_config is None:
        firm = state.get("firm")
        brand_config = BrandConfig.load(brand_name=firm, firm=firm)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    prompt = _build_design_prompt(slots, brand_config, state, mode)

    print(f"  Generating {mode} mode layout via Claude...")
    response = client.messages.create(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        max_tokens=8000,
        temperature=0.3,  # Some creative latitude for design
        messages=[{"role": "user", "content": prompt}]
    )

    html = _parse_html_response(response.content[0].text)

    # Mechanical disambiguation: fix company name and URL mutations
    company_name = state.get("company_name", "")
    if company_name:
        # Build a list of wrong names to replace from disambiguation_excludes
        # e.g., if company is "Metabologic" and excludes include "metabolic.ai",
        # replace standalone "Metabolic" with "Metabologic" in the HTML
        disambiguation_excludes = state.get("disambiguation_excludes", [])
        for excl_domain in disambiguation_excludes:
            wrong_name = excl_domain.split('.')[0]  # "metabolic" from "metabolic.ai"
            if wrong_name.lower() == company_name.lower():
                continue  # Same name, skip
            # Only replace the CAPITALIZED form when used as a proper noun
            # (i.e., "Metabolic" at start of sentence or standalone as company name)
            # Do NOT replace lowercase "metabolic" which is a common English word
            wrong_capitalized = wrong_name.capitalize()  # "Metabolic"
            # Replace "Metabolic" only when:
            # - It's capitalized (proper noun usage)
            # - It's NOT followed by lowercase letters that would make it part of
            #   a longer word like "Metabolically"
            # - It's NOT preceded by "meta" or similar (avoid "Metabologic" → "Metabologiclogic")
            if wrong_capitalized in html:
                # Only replace capitalized form, not lowercase
                html = re.sub(
                    rf'(?<![a-zA-Z]){re.escape(wrong_capitalized)}(?![a-z])',
                    company_name,
                    html
                )

    # Inject logos via placeholder replacement (reliable, no dedup needed)
    trademark = state.get("company_trademark_light") or state.get("company_trademark_dark") or ""
    company_logo_html = ""
    if trademark:
        company_logo_html = f'<img src="{trademark}" alt="{company_name}" style="max-width: 150px; height: auto;">'
    html = html.replace("%%COMPANY_LOGO%%", company_logo_html)

    vc_logo_url = ""
    if brand_config and brand_config.logo:
        vc_logo_url = brand_config.logo.dark_mode or brand_config.logo.light_mode or ""
    vc_logo_html = ""
    if vc_logo_url:
        vc_logo_html = f'<img src="{vc_logo_url}" alt="{brand_config.company.name}" style="max-width: 130px; height: auto;">'
    html = html.replace("%%VC_FIRM_LOGO%%", vc_logo_html)

    # Remove any <img> tags Claude may have added despite being told not to
    # (keep only our injected ones by removing any img with logo/trademark URLs)
    # This is a safety net — the placeholders should be the only logo mechanism
    if trademark:
        frag = trademark.split("/")[-1].split("?")[0]
        # Count our injected logo
        injected_count = html.count(trademark)
        if injected_count > 1:
            # Remove extras (keep first)
            first_pos = html.find(trademark)
            before = html[:first_pos + len(trademark)]
            after = html[first_pos + len(trademark):].replace(trademark, "REMOVED_DUPLICATE")
            html = before + after

    return html


def one_pager_generator_agent(state: MemoState) -> Dict[str, Any]:
    """
    One-Pager Generator Agent.

    Step 1: Extracts content from final draft into structured slots.
    Step 2: Claude designs a branded single-page HTML layout.
    Step 3: WeasyPrint converts to PDF.

    Args:
        state: Current memo state

    Returns:
        State updates with messages
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

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⊘ One-pager skipped - no ANTHROPIC_API_KEY")
        return {"messages": ["One-pager skipped - no API key"]}

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    # Step 1: Extract content slots
    prompt = _build_extraction_prompt(final_draft_text, state, investment_type)

    print("  Step 1: Extracting content slots...")
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

    # Step 2: Generate HTML layout via Claude
    try:
        html_content = render_one_pager(slots, state, mode="light")
    except Exception as e:
        print(f"  ❌ HTML generation failed: {e}")
        return {"messages": [f"One-pager HTML failed: {e}"]}

    html_path = output_dir / "8-one-pager.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"  ✓ HTML generated: {html_path.name}")

    # Step 3: Convert to PDF
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

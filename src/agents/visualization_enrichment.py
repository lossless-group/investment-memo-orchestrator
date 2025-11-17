"""
Visualization Enrichment Agent - Finds and embeds relevant charts, graphs, and diagrams.

This agent enriches memo sections by finding and embedding:
- Company website charts and infographics
- Product diagrams and architecture visuals
- Market data visualizations
- Publicly available graphs and charts

Images are embedded using markdown syntax: ![Alt text](image-url)
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import os
from typing import Dict, Any, List
from ..state import MemoState
import json
from openai import OpenAI  # Perplexity uses OpenAI SDK


VISUALIZATION_SYSTEM_PROMPT = """You are a visualization enrichment specialist for investment memos.

Your task is to identify opportunities to embed relevant charts, graphs, diagrams, and visualizations that enhance understanding of the company, market, or technology.

TYPES OF VISUALIZATIONS TO CONSIDER:
1. **Company metrics**: Growth charts, traction graphs, revenue curves
2. **Market data**: TAM/SAM charts, market sizing diagrams, competitive landscapes
3. **Technical diagrams**: Product architecture, technology stack, system diagrams
4. **Process flows**: Business model diagrams, workflow visualizations
5. **Geographic maps**: Market presence, facility locations
6. **Infographics**: Company timelines, milestone charts

EMBEDDING FORMAT:
Use markdown syntax: ![Description of visualization](https://url-to-image.png)

RULES:
1. ONLY embed publicly accessible images (no authentication required)
2. Place visualizations in contextually relevant sections
3. Add a descriptive alt text that explains what the image shows
4. Prefer images from the company's own website or official sources
5. Avoid embedding too many images (max 2-3 per memo)
6. DO NOT embed logos, headshots, or promotional images
7. Ensure image URLs are direct links to image files (.png, .jpg, .svg, .webp)
8. Add a newline before and after embedded images for proper rendering

QUALITY CRITERIA:
- Image must be relevant to the investment analysis
- Image must be high-quality and professional
- Image must add information value (not decorative)
- Image must be from a credible source

OUTPUT:
Return a JSON object with:
{
  "visualizations": [
    {
      "section": "Market Context",
      "image_url": "https://...",
      "alt_text": "Description",
      "placement": "after_paragraph_2",
      "rationale": "Why this image is valuable"
    }
  ],
  "total_count": 2
}

If no suitable visualizations are found, return {"visualizations": [], "total_count": 0}
"""


def find_visualizations_with_perplexity(company_name: str, section_context: str) -> List[Dict[str, str]]:
    """
    Use Perplexity to find relevant charts, graphs, and visualizations.

    Args:
        company_name: Name of the company
        section_context: Context about what type of visualization is needed

    Returns:
        List of visualization dictionaries with url, description, and source
    """
    perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")

    if not perplexity_api_key:
        print("Warning: PERPLEXITY_API_KEY not set, skipping visualization search")
        return []

    try:
        client = OpenAI(
            api_key=perplexity_api_key,
            base_url="https://api.perplexity.ai"
        )

        # Create search query for visualizations
        query = f"""Find publicly accessible charts, graphs, infographics, or technical diagrams related to {company_name}.

Focus on: {section_context}

Provide:
1. Direct URLs to image files (PNG, JPG, SVG, WEBP)
2. Description of what each visualization shows
3. Source website

Only include professional, high-quality visualizations from credible sources (company website, press releases, industry reports, tech blogs).
Avoid logos, headshots, or promotional images."""

        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {"role": "user", "content": query}
            ]
        )

        content = response.choices[0].message.content

        # Parse response for image URLs and descriptions
        # Perplexity returns image URLs in its response
        visualizations = []

        # Try to extract image URLs from the response
        # This is a simple extraction - Perplexity's API may return structured data
        lines = content.split('\n')
        for line in lines:
            # Look for image URLs
            if any(ext in line.lower() for ext in ['.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif']):
                # Extract URL (basic extraction, may need refinement)
                import re
                urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+\.(?:png|jpg|jpeg|svg|webp|gif)', line, re.IGNORECASE)
                for url in urls:
                    visualizations.append({
                        "url": url,
                        "description": line.replace(url, '').strip(),
                        "source": "Perplexity search"
                    })

        return visualizations[:5]  # Return top 5

    except Exception as e:
        print(f"Warning: Could not search for visualizations with Perplexity: {e}")
        return []


def visualization_enrichment_agent(state: MemoState) -> Dict[str, Any]:
    """
    Visualization Enrichment Agent implementation.

    Finds and embeds relevant charts, graphs, and diagrams in memo sections.

    Args:
        state: Current memo state with draft sections and research

    Returns:
        Updated state with visualization-enriched sections
    """
    draft_sections = state.get("draft_sections", {})
    research = state.get("research", {})

    if not draft_sections:
        return {
            "messages": ["No draft sections available for visualization enrichment"]
        }

    company_name = state["company_name"]

    # Get company website from research
    company_data = research.get("company", {}) if research else {}
    company_url = company_data.get("website", "")

    # Get the full memo content
    full_memo = draft_sections.get("full_memo", {})
    memo_content = full_memo.get("content", "")

    if not memo_content:
        return {
            "messages": ["No memo content available for visualization enrichment"]
        }

    # Find candidate visualizations using Perplexity
    # Search for market charts, product diagrams, and company infographics
    print(f"Searching for visualizations using Perplexity...")
    market_viz = find_visualizations_with_perplexity(
        company_name,
        "market size charts, competitive landscape diagrams, market growth graphs"
    )
    product_viz = find_visualizations_with_perplexity(
        company_name,
        "product architecture diagrams, technical schematics, system diagrams"
    )

    candidate_images = market_viz + product_viz
    print(f"Found {len(candidate_images)} candidate visualizations")

    # Initialize Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0,
    )

    # Create visualization identification prompt
    import json

    candidates_info = json.dumps(candidate_images[:5], indent=2) if candidate_images else "[]"

    user_prompt = f"""Identify opportunities to embed visualizations in this investment memo for {company_name}.

MEMO CONTENT:
{memo_content}

CANDIDATE IMAGES FROM COMPANY WEBSITE:
{candidates_info}

COMPANY INFO:
Website: {company_url}

INSTRUCTIONS:
1. Review the memo and identify 1-3 sections that would benefit from visualizations
2. For each opportunity, specify which candidate image to use (if available) OR suggest what type of visualization would be valuable
3. Only recommend publicly accessible images
4. Prioritize charts, graphs, diagrams, and infographics over photos
5. Return JSON with visualization recommendations

Return JSON in this format:
{{
  "visualizations": [
    {{
      "section": "Section name",
      "image_url": "https://..." (if candidate available) or null,
      "alt_text": "Descriptive alt text",
      "suggested_search": "What to search for if no candidate" (if image_url is null),
      "rationale": "Why this adds value"
    }}
  ],
  "total_count": 1
}}
"""

    # Call Claude
    messages = [
        SystemMessage(content=VISUALIZATION_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt)
    ]

    print("Analyzing memo for visualization opportunities...")
    response = model.invoke(messages)

    try:
        # Parse JSON response
        viz_recommendations = json.loads(response.content)
        visualizations = viz_recommendations.get("visualizations", [])

        if not visualizations:
            print("No suitable visualizations found")
            return {
                "messages": [f"No suitable visualizations found for {company_name}"]
            }

        # Embed visualizations in memo
        enriched_content = memo_content

        for viz in visualizations:
            if viz.get("image_url"):
                # Create markdown image embed
                img_markdown = f"\n\n![{viz['alt_text']}]({viz['image_url']})\n\n"

                # Find appropriate section and insert
                section_name = viz.get("section", "")
                if section_name in enriched_content:
                    # Insert after section header
                    section_header = f"## {section_name}" if "##" not in section_name else section_name
                    enriched_content = enriched_content.replace(
                        section_header,
                        f"{section_header}{img_markdown}",
                        1  # Only first occurrence
                    )

        print(f"Visualization enrichment completed: {len([v for v in visualizations if v.get('image_url')])} images embedded")

        # Update draft sections
        enriched_sections = {
            "full_memo": {
                "section_name": "full_memo",
                "content": enriched_content,
                "word_count": len(enriched_content.split()),
                "citations": full_memo.get("citations", [])
            }
        }

        return {
            "draft_sections": enriched_sections,
            "messages": [f"Visualizations added to memo for {company_name} ({len(visualizations)} opportunities identified)"]
        }

    except json.JSONDecodeError:
        print(f"Warning: Could not parse visualization recommendations")
        return {
            "messages": ["Visualization analysis complete but no images embedded"]
        }

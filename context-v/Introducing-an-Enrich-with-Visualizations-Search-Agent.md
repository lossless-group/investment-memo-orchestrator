---
title: Introducing an Enrich Visualizations Agent
lede: An enrichment agent that discovers and embeds publicly accessible charts, graphs, diagrams, and infographics from web sources to visually reinforce key claims in investment memos — the automated equivalent of grabbing charts from Google Image search.
date_authored_initial_draft: 2026-03-10
date_authored_current_draft: 2026-03-10
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-10
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Specification
tags: [Agent-Design, Visualizations, Charts, Image-Search, Enrichment]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A memo section with a market sizing chart from Statista embedded inline, alongside a competitive landscape quadrant diagram sourced from a research report, with subtle attribution captions beneath each.
date_created: 2026-03-10
date_modified: 2026-03-10
---

# Introducing an Enrich Visualizations Agent

**Status**: Draft
**Date**: 2026-03-10
**Last Updated**: 2026-03-10
**Author**: AI Labs Team
**Related**: Introducing-a-Diagram-Generator-Agent.md (complementary — generates visuals programmatically), Introducing-a-Table-Generator-Agent.md, Multi-Agent-Orchestration-for-Investment-Memo-Generation.md
**Supersedes**: The existing disabled `visualization_enrichment.py` agent (which needs a full rewrite for section-by-section processing and better image discovery)

---

## Executive Summary

When an analyst builds an investment memo by hand, one of the most common moves is to go to Google Image search, type something like "metabolic health market size chart 2025," and grab a chart from Statista, Grand View Research, or a McKinsey report. These found visuals add enormous credibility and comprehension — a market sizing chart from a research firm is worth more than a paragraph describing the same numbers.

The current `visualization_enrichment.py` agent was built with this intent but was disabled because:
1. It operated on the full assembled memo rather than section-by-section
2. Its image discovery was too naive — Perplexity text responses aren't great at finding direct image URLs
3. No validation that found URLs actually serve images
4. No attribution or source citation for embedded images

This specification redesigns the agent with robust image discovery, URL validation, proper attribution, and section-by-section processing.

---

## The Human Workflow We're Automating

When a human analyst enriches a memo with visuals, they typically:

1. **Read a section** and notice a claim that would benefit from a chart ("The global enzyme supplement market is $8.2B growing at 7.5% CAGR")
2. **Search for visuals** — Google Image search, or directly on Statista, Grand View Research, PitchBook, CB Insights, etc.
3. **Evaluate results** — Is this chart from a credible source? Does it actually show the right data? Is it recent enough?
4. **Grab the image** — Copy the image URL or download and re-host it
5. **Embed with attribution** — Place it in the memo with a source caption

This is quick, effective, and adds significant polish. The challenge in automating it is that image search APIs are less mature than text search, and direct image URLs from research firms are often behind paywalls or dynamically generated.

---

## Goals

1. **Find relevant charts and graphs** from public web sources that reinforce claims made in the memo
2. **Validate image URLs** — confirm they actually serve an image before embedding
3. **Attribute sources properly** — every embedded image gets a caption with source and date
4. **Process section-by-section** — consistent with all other enrichment agents
5. **Be conservative** — better to embed 1-2 high-quality visuals than 5 broken or irrelevant ones
6. **Complement, don't compete** — this agent finds *existing* visuals; the Diagram Generator agent *creates* new ones programmatically

---

## What Kinds of Visuals to Find

### High Value (actively search for these)

| Visual Type | Example Search | Typical Source | Target Sections |
|-------------|---------------|----------------|-----------------|
| Market sizing charts | "[industry] market size chart 2025" | Statista, Grand View Research, Mordor Intelligence | Market Context, Opening, Opportunity |
| Competitive landscape quadrants | "[industry] competitive landscape" | Gartner, Forrester, G2 Grid | Market Context, Opportunity |
| Growth trend charts | "[industry] growth rate CAGR chart" | McKinsey, Deloitte, PwC reports | Market Context |
| Funding landscape charts | "[industry] venture funding chart" | PitchBook, CB Insights, Crunchbase | Funding & Terms |
| Technology adoption curves | "[technology] adoption curve" | Gartner Hype Cycle, industry reports | Technology & Product |
| Regulatory pathway diagrams | "FDA approval pathway diagram" | FDA.gov, regulatory consultancies | Technology & Product (biotech/health) |

### Medium Value (search if section needs reinforcement)

| Visual Type | Example Search | Target Sections |
|-------------|---------------|-----------------|
| Industry value chain diagrams | "[industry] value chain" | Business Overview |
| Geographic market maps | "[industry] market by region" | Market Context |
| Consumer behavior charts | "[consumer segment] spending trends" | Market Context, Traction |
| Benchmark comparisons | "[industry] SaaS benchmarks" | Traction & Milestones |

### Avoid (do not embed)

- Company logos and headshots (handled by trademark enrichment)
- Generic stock photos and clip art
- Low-resolution or watermarked images
- Charts older than 3 years (unless showing historical trends)
- Paywalled images that show a preview overlay
- Screenshots of social media posts
- Promotional marketing materials

---

## Pipeline Position

```
... → enrich_links → generate_tables → ENRICH_VISUALIZATIONS → toc → ...
```

**Runs after**: `generate_tables` (tables are in place, so the agent can see what data is already presented in tabular form and avoid visual redundancy)
**Runs before**: `toc` (if visuals add section headers or captions, TOC captures them)

This is the same position the disabled agent occupied. No workflow changes needed.

---

## Architecture

### Section-by-Section Processing

Like all enrichment agents, this processes one section file at a time from `2-sections/`. For each section:

1. **Analyze section content** — identify claims that would benefit from a visual
2. **Generate search queries** — create 1-2 targeted image search queries per section
3. **Search for images** — use image search API(s) to find candidate visuals
4. **Validate candidates** — HTTP HEAD request to confirm URL serves an image
5. **Select best match** — pick the most relevant, highest-quality visual
6. **Embed with attribution** — insert markdown image with source caption
7. **Save section** — write back to the section file

### Image Discovery Strategy

The current implementation uses Perplexity for text-based search, which doesn't reliably return direct image URLs. The redesigned agent should use a multi-source approach:

#### Source 1: Google Custom Search API (Image Mode)

Google's Custom Search JSON API supports image search and returns direct image URLs with metadata.

```python
# Google Custom Search API with image search
import requests

def search_images_google(query: str, api_key: str, cx: str, num: int = 5) -> list:
    """Search Google Images via Custom Search API."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": api_key,
        "cx": cx,
        "searchType": "image",
        "imgSize": "large",
        "imgType": "charts",  # or "photo", "clipart", etc.
        "num": num,
        "safe": "active",
    }
    response = requests.get(url, params=params)
    results = response.json().get("items", [])
    return [
        {
            "url": item["link"],
            "thumbnail": item["image"]["thumbnailLink"],
            "context_url": item["image"]["contextLink"],  # Page the image appears on
            "title": item.get("title", ""),
            "source_domain": item.get("displayLink", ""),
            "width": item["image"].get("width"),
            "height": item["image"].get("height"),
        }
        for item in results
    ]
```

**Pros**: Returns actual image URLs with metadata, supports image type filtering
**Cons**: Requires API key and Custom Search Engine ID, has daily quota (100 free/day, $5 per 1000 after)

**Environment variables**:
- `GOOGLE_SEARCH_API_KEY` — Google Cloud API key
- `GOOGLE_SEARCH_CX` — Custom Search Engine ID (configured for image search)

#### Source 2: Perplexity with Image-Focused Prompting (Fallback)

If Google Image API is not configured, fall back to Perplexity with prompts specifically designed to extract image URLs from research reports and data providers.

```
Find a DIRECT IMAGE URL (ending in .png, .jpg, .svg, or .webp) for a chart
showing [specific data point]. Look on these sites:
- statista.com
- grandviewresearch.com
- mordorintelligence.com
- cbinsights.com
- mckinsey.com/featured-insights

Return ONLY the direct image URL, not a page URL. If you cannot find a direct
image URL, say "NO_IMAGE_FOUND".
```

#### Source 3: Known Data Provider Patterns (Supplementary)

Some data providers have predictable URL patterns for their chart images:

```python
KNOWN_CHART_SOURCES = {
    "statista": {
        "search_pattern": "site:statista.com {query} chart",
        "image_pattern": r"https://www\.statista\.com/graphic/\d+/.*",
    },
    "cbinsights": {
        "search_pattern": "site:cbinsights.com {query} chart infographic",
        "image_pattern": r"https://.*cbinsights\.com/.*\.(png|jpg|svg)",
    },
}
```

### Image URL Validation

Before embedding any image, validate that the URL actually serves an image:

```python
import requests

def validate_image_url(url: str, timeout: int = 10) -> dict:
    """
    Validate that a URL serves an actual image.

    Returns dict with:
      valid: bool
      content_type: str
      size_bytes: int
      reason: str (if invalid)
    """
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)

        content_type = response.headers.get("Content-Type", "")
        content_length = int(response.headers.get("Content-Length", 0))

        # Must be an image content type
        if not content_type.startswith("image/"):
            return {"valid": False, "reason": f"Not an image: {content_type}"}

        # Must be reasonably sized (not a 1x1 tracking pixel, not a 50MB photo)
        if content_length > 0 and content_length < 1000:
            return {"valid": False, "reason": "Too small (likely tracking pixel)"}
        if content_length > 10_000_000:
            return {"valid": False, "reason": "Too large (>10MB)"}

        # Must return 200
        if response.status_code != 200:
            return {"valid": False, "reason": f"HTTP {response.status_code}"}

        return {
            "valid": True,
            "content_type": content_type,
            "size_bytes": content_length,
        }

    except requests.RequestException as e:
        return {"valid": False, "reason": str(e)}
```

### Image Caching and Local Storage

External image URLs can break over time. For production-quality memos:

1. **Download validated images** to `output/{Company}-v0.0.x/images/`
2. **Embed with local path** as primary, external URL as fallback
3. **Store metadata** in `images/manifest.json`

```
output/{Company}-v0.0.x/
├── images/
│   ├── manifest.json
│   ├── market-sizing-statista-2025.png
│   └── competitive-landscape-gartner-2024.png
```

This ensures the memo remains complete even if the source URLs change. The HTML/PDF export uses local images; the markdown source can reference either.

---

## Attribution and Captioning

Every embedded image MUST have proper attribution. This serves both legal (fair use / copyright) and credibility purposes.

### Markdown Format

```markdown
![Global enzyme supplement market size and forecast, 2020-2030](images/market-sizing-statista-2025.png)
*Source: [Statista](https://www.statista.com/statistics/...), March 2025. Used under fair use for analytical purposes.*
```

### Attribution Template

```
*Source: [{Source Name}]({source_page_url}), {date}. Used under fair use for analytical purposes.*
```

### Fair Use Considerations

Investment memos are analytical documents, not publications. Embedding a chart from Statista in an internal investment memo falls under fair use in most jurisdictions. However:

- Always attribute the source
- Link back to the original page (not just the image)
- Use the image to support analysis, not as standalone content
- If the memo is published externally, image permissions should be reviewed

---

## Agent Behavior

### Input

```python
def enrich_visualizations_agent(state: MemoState) -> Dict[str, Any]:
    """
    Find and embed relevant charts, graphs, and diagrams from web sources.
    Processes section-by-section with image validation and attribution.
    """
```

### Per-Section Processing

For each section file:

1. **Skip conditions**:
   - Section is too short (<200 chars)
   - Section already has 2+ embedded images
   - Section type doesn't benefit from visuals (e.g., Executive Summary, Recommendation)

2. **Identify visual opportunity**:
   Use Claude to analyze section content and determine:
   - What specific claim would benefit from a visual?
   - What type of chart/graph would be most relevant?
   - What search query would find it?

3. **Search for images**:
   - Run 1-2 targeted searches per section
   - Collect candidate URLs

4. **Validate and select**:
   - HTTP HEAD each candidate
   - Filter to valid images from credible sources
   - Select the best match (most relevant, highest quality, most recent)

5. **Download and embed**:
   - Download image to `images/` directory
   - Insert markdown image + attribution caption into section
   - Place after the paragraph containing the claim it supports

### Output

```python
return {
    "messages": [
        f"Visualization enrichment: {n} images embedded in {s} sections",
        f"Images saved to {output_dir}/images/"
    ]
}
```

### Conservative Defaults

- **Max 1 image per section** (prevents visual clutter)
- **Max 3-4 images per memo** (memos should be primarily text-driven)
- **Only embed if confidence is high** — if the search doesn't return a clearly relevant, high-quality chart, skip that section
- **Prefer recent sources** — charts from the last 2 years, unless showing historical trends

---

## Sections Most Likely to Benefit

| Section | Visual Opportunity | Likelihood |
|---------|-------------------|------------|
| Market Context / Opening / Opportunity | Market sizing chart, growth trends | High |
| Market Context / Opportunity | Competitive landscape quadrant | High |
| Technology & Product / Offering | Technology adoption curve, architecture diagram | Medium |
| Traction & Milestones | Industry benchmark comparison | Medium |
| Funding & Terms | VC funding trends in sector | Medium |
| Business Overview | Value chain or business model diagram | Low |
| Team / Organization | — | Skip |
| Executive Summary | — | Skip |
| Risks & Mitigations | — | Skip |
| Recommendation / Closing | — | Skip |

---

## Relationship to Other Visual Agents

This system has three distinct visual enhancement agents, each with a different approach:

| Agent | What It Does | Source of Visuals | Status |
|-------|-------------|-------------------|--------|
| **Enrich Visualizations** (this spec) | Finds and embeds existing charts/graphs from the web | Google Image Search, Perplexity, data providers | Needs rewrite |
| **Diagram Generator** (separate spec) | Creates new diagrams programmatically | Generated from memo data via Mermaid/SVG | Spec complete |
| **Inject Deck Images** (existing) | Embeds screenshots from the pitch deck | Deck PDF → PNG conversion | Implemented |

These are complementary:
- Deck screenshots show what the company presented
- Found visuals show what third parties report about the market
- Generated diagrams present the memo's own analysis visually

---

## Configuration

### Environment Variables

```bash
# Required for Google Image Search (preferred)
GOOGLE_SEARCH_API_KEY=your-api-key
GOOGLE_SEARCH_CX=your-custom-search-engine-id

# Already required (fallback)
PERPLEXITY_API_KEY=your-perplexity-key
```

### Company JSON Config

```json
{
  "visualization_queries": [
    "metabolic health market size chart 2025",
    "GLP-1 market growth forecast",
    "enzyme supplement industry chart"
  ]
}
```

Optional `visualization_queries` field lets users provide specific search queries they know will find good charts — same pattern as `search_variants` for competitive research.

### Outline YAML

```yaml
visualization:
  max_per_memo: 4
  max_per_section: 1
  preferred_sources:
    - statista.com
    - grandviewresearch.com
    - cbinsights.com
    - mckinsey.com
  skip_sections:
    - "01-executive-summary"
    - "10-recommendation"
    - "10-closing-assessment"
```

---

## Implementation Priority

This agent is **lower priority** than the competitive landscape system and table generator, but higher than the diagram generator because it builds on a simpler concept (find existing images vs. generate new ones).

1. Set up Google Custom Search API integration
2. Image URL validation
3. Download and local storage
4. Section-by-section processing with attribution
5. Perplexity fallback for non-Google setups

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Embedded images per memo | 1-3 (quality over quantity) |
| Image URL validity at embed time | 100% (validated before embedding) |
| Image URL validity after 30 days | >80% (local cache mitigates this) |
| Images with proper attribution | 100% |
| Images from credible sources | 100% |
| Sections where visuals add analytical value | >90% of embedded images |

---

## Open Questions

1. **Image hosting for long-term memos**: Should we upload cached images to a CDN (like ImageKit, which the project already uses for logos) so exported HTML memos have reliable image URLs? Or is local storage sufficient?

2. **Copyright and licensing**: For memos shared externally with LPs, should the agent check image licensing more carefully? Some research firms allow fair use for internal analysis but not redistribution.

3. **AI-generated chart descriptions**: When embedding a chart, should the agent also generate a 1-2 sentence description of what the chart shows, for readers who can't see the image (accessibility) and for contexts where images don't render (plain markdown)?

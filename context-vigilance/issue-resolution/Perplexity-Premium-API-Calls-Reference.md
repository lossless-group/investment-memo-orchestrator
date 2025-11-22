# Perplexity Premium API Calls - Complete Reference

**Date**: 2025-11-22
**Updated**: 2025-11-22
**Purpose**: Use `@source` syntax and premium data sources for high-quality investment research

**Status**: ✅ **@ syntax CONFIRMED working via API** (tested 2025-11-22)

---

## Executive Summary

**The Simple Solution That Works:**

```python
# OLD WAY (no quality control)
query = f"What is {company}'s revenue?"

# NEW WAY (targets premium sources)
query = f"What is {company}'s revenue? @crunchbase @pitchbook @statista"
```

**That's it.** Just add `@source` names to your query string.

**Confirmed Working Sources** (tested via API):
- `@crunchbase` - Funding, investors, firmographics
- `@pitchbook` - Valuations, market analysis, deal data
- `@statista` - Statistics, market size, forecasts
- `@bloomberg` - Financial news, market data
- `@reuters` - Breaking news, verified reporting
- `@forbes` - Business news, rankings
- `@sec` - Regulatory filings, IPO data

**Premium Partners** (available with Pro subscription):
- `@wiley` - Academic research (business, STEM, medical)
- `@cbinsights` - Market trends, startup tracking, market maps

---

## Current Implementation (Basic)

**File**: `src/agents/research_enhanced.py` (Lines 91-97)

```python
# CURRENT - No quality source targeting
response = self.client.chat.completions.create(
    model="sonar-pro",
    messages=[
        {"role": "system", "content": "You are a research assistant..."},
        {"role": "user", "content": query}
    ]
)
```

**Problems**:
- ❌ Searches entire web (including generic SaaS blogs, benchmark sites)
- ❌ No premium source prioritization
- ❌ Returns filler content from low-quality sources
- ❌ Wastes API calls on unreliable data

---

## ✅ RECOMMENDED: @ Syntax (Simple & Works Now)

**How it works**: Simply add `@source` names directly in your query string. Perplexity will prioritize those sources.

### Basic Implementation

```python
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("PERPLEXITY_API_KEY"),
    base_url="https://api.perplexity.ai"
)

# Simply add @sources to your query
query = f"What is {company_name}'s revenue and customer count? @crunchbase @pitchbook @statista"

response = client.chat.completions.create(
    model="sonar-pro",
    messages=[
        {
            "role": "system",
            "content": "You are a research assistant providing detailed, cited information for investment analysis."
        },
        {
            "role": "user",
            "content": query  # @ sources are in the query string
        }
    ]
)

content = response.choices[0].message.content
```

**That's it!** No complex `extra_body` parameters needed.

### Section-Specific Source Recommendations

Use different `@sources` based on the memo section you're researching:

```python
# Section-specific source strings
SECTION_SOURCES = {
    "Executive Summary": "@crunchbase @pitchbook @bloomberg",
    "Business Overview": "@crunchbase @techcrunch @forbes",
    "Market Context": "@statista @cbinsights @pitchbook",
    "Team": "@crunchbase @linkedin",
    "Technology & Product": "@techcrunch @wired",
    "Traction & Milestones": "@crunchbase @techcrunch @bloomberg",
    "Funding & Terms": "@crunchbase @pitchbook @sec",
    "Risks & Mitigations": "@sec @bloomberg @reuters",
    "Investment Thesis": "@pitchbook @statista @cbinsights",
}

# Usage in research agent
def research_with_sources(company_name: str, section: str) -> str:
    sources = SECTION_SOURCES.get(section, "@crunchbase @pitchbook")
    query = f"Research {company_name} for {section} section. {sources}"

    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": query}]
    )

    return response.choices[0].message.content
```

### Complete Working Example

```python
import os
from openai import OpenAI

def research_company_section(
    company_name: str,
    section: str = "Traction & Milestones"
) -> dict:
    """
    Research company using @ syntax for premium sources.

    Args:
        company_name: Company name (e.g., "Stripe")
        section: Memo section name

    Returns:
        Dict with content and metadata
    """

    # Section-specific sources
    SECTION_SOURCES = {
        "Executive Summary": "@crunchbase @pitchbook @bloomberg",
        "Business Overview": "@crunchbase @techcrunch @forbes",
        "Market Context": "@statista @cbinsights @pitchbook",
        "Team": "@crunchbase @linkedin",
        "Technology & Product": "@techcrunch @wired",
        "Traction & Milestones": "@crunchbase @techcrunch @bloomberg",
        "Funding & Terms": "@crunchbase @pitchbook @sec",
        "Risks & Mitigations": "@sec @bloomberg @reuters",
        "Investment Thesis": "@pitchbook @statista @cbinsights",
    }

    client = OpenAI(
        api_key=os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai"
    )

    sources = SECTION_SOURCES.get(section, "@crunchbase @pitchbook")
    query = f"Research {company_name} for investment memo {section} section. Provide specific metrics, dates, and data. {sources}"

    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {
                "role": "system",
                "content": f"You are researching {company_name} for an investment memo. Provide only factual information from authoritative sources. Cite all sources."
            },
            {
                "role": "user",
                "content": query
            }
        ]
    )

    return {
        "content": response.choices[0].message.content,
        "sources_requested": sources,
        "section": section
    }


# Usage
result = research_company_section(
    company_name="Stripe",
    section="Funding & Terms"
)

print("Content:", result["content"])
print("\nSources requested:", result["sources_requested"])
```

---

## FALLBACK: search_domain_filter (Tier 3 Enterprise Only)

**⚠️ Use this ONLY if @ syntax doesn't provide enough control**

### When to use search_domain_filter instead of @ syntax:

1. You need to **EXCLUDE** specific domains (e.g., `-*.benchmark.com`)
2. You need **exact domain control** (allowlist/denylist)
3. You have Tier 3 (Enterprise) subscription

### `search_domain_filter` - Example Usage

**Tier Requirement**: **Tier 3 (Enterprise)** - requires expensive subscription
**Max Domains**: 20
**Syntax**:
- Include: `"crunchbase.com"`
- Exclude: `"-reddit.com"` (prefix with `-`)

```python
response = client.chat.completions.create(
    model="sonar-pro",
    messages=[{"role": "user", "content": query}],
    extra_body={
        "search_domain_filter": [
            "crunchbase.com",
            "pitchbook.com",
            "sec.gov",
            "-*.saas-metrics.com",    # EXCLUDE filler
            "-*.benchmark.com",        # EXCLUDE filler
        ],
        "search_recency_filter": "month"  # Recent content only
    }
)
```

**When to use this:**
- You need to EXCLUDE low-quality domains
- You have Tier 3 Enterprise subscription
- @ syntax alone isn't enough

**Recommendation**: Try @ syntax first. Only use `search_domain_filter` if you specifically need exclusions.

---

## Implementation for Investment Memo System

### 1. Add Preferred Sources to YAML Outlines

**⚠️ IMPORTANT**: This system uses **YAML outlines** (not markdown templates) for content structure.

**Update these files:**
- `templates/outlines/direct-investment.yaml`
- `templates/outlines/fund-commitment.yaml`

Each section in the outline should include `preferred_sources` for research quality and consistency:

```yaml
sections:
  - number: 3
    name: "Market Context"
    filename: "03-market-context.md"
    target_length:
      min_words: 500
      max_words: 700
      ideal_words: 600

    description: |
      Analysis of market size, growth trends, competitive landscape,
      and market dynamics relevant to the investment opportunity.

    guiding_questions:
      - "What is the total addressable market (TAM) and how is it growing?"
      - "Who are the key competitors and how is the company differentiated?"
      - "What market dynamics favor (or challenge) this opportunity?"

    # NEW: Preferred sources for research
    preferred_sources:
      perplexity_at_syntax:
        - "@statista"      # Market size, statistics, forecasts
        - "@cbinsights"    # Market trends, competitive intelligence
        - "@pitchbook"     # Market analysis, deal data

      domains:
        include:
          - "statista.com"         # Industry statistics
          - "cbinsights.com"       # Trend reports
          - "pitchbook.com"        # Market sizing
          - "gartner.com"          # Analyst reports
          - "[company-domain]"     # Company's own market analysis

        exclude:
          - "*.top10.com"          # Generic list sites
          - "*.saas-metrics.com"   # Benchmark filler
          - "*.market-guide.com"   # SEO spam

    section_vocabulary:
      # ... existing vocabulary config ...
```

**Example for all 10 sections:**

```yaml
sections:
  # 1. Executive Summary
  - number: 1
    name: "Executive Summary"
    preferred_sources:
      perplexity_at_syntax: ["@crunchbase", "@pitchbook", "@bloomberg"]
      domains:
        include: ["crunchbase.com", "pitchbook.com", "bloomberg.com"]

  # 2. Business Overview
  - number: 2
    name: "Business Overview"
    preferred_sources:
      perplexity_at_syntax: ["@crunchbase", "@techcrunch", "@forbes"]
      domains:
        include: ["[company-domain]", "crunchbase.com", "techcrunch.com"]

  # 3. Market Context
  - number: 3
    name: "Market Context"
    preferred_sources:
      perplexity_at_syntax: ["@statista", "@cbinsights", "@pitchbook"]
      domains:
        include: ["statista.com", "cbinsights.com", "pitchbook.com"]
        exclude: ["*.top10.com", "*.saas-metrics.com"]

  # 4. Team
  - number: 4
    name: "Team"
    preferred_sources:
      perplexity_at_syntax: ["@crunchbase", "@linkedin"]
      domains:
        include: ["linkedin.com", "crunchbase.com", "[company-domain]/about"]

  # 5. Technology & Product
  - number: 5
    name: "Technology & Product"
    preferred_sources:
      perplexity_at_syntax: ["@techcrunch", "@wired"]
      domains:
        include: ["[company-domain]", "techcrunch.com", "wired.com"]

  # 6. Traction & Milestones
  - number: 6
    name: "Traction & Milestones"
    preferred_sources:
      perplexity_at_syntax: ["@crunchbase", "@techcrunch", "@bloomberg"]
      domains:
        include: ["[company-domain]", "crunchbase.com", "techcrunch.com"]

  # 7. Funding & Terms
  - number: 7
    name: "Funding & Terms"
    preferred_sources:
      perplexity_at_syntax: ["@crunchbase", "@pitchbook", "@sec"]
      domains:
        include: ["crunchbase.com", "pitchbook.com", "sec.gov"]

  # 8. Risks & Mitigations
  - number: 8
    name: "Risks & Mitigations"
    preferred_sources:
      perplexity_at_syntax: ["@sec", "@bloomberg", "@reuters"]
      domains:
        include: ["sec.gov", "bloomberg.com", "reuters.com", "wsj.com"]

  # 9. Investment Thesis
  - number: 9
    name: "Investment Thesis"
    preferred_sources:
      perplexity_at_syntax: ["@pitchbook", "@statista", "@cbinsights"]
      domains:
        include: ["pitchbook.com", "statista.com", "cbinsights.com"]

  # 10. Recommendation
  - number: 10
    name: "Recommendation"
    preferred_sources:
      # Synthesizes from all above sections
      perplexity_at_syntax: ["@crunchbase", "@pitchbook"]
```

### 2. Update `src/agents/research_enhanced.py`

**Add section-specific sources at top of file:**

```python
# Section-specific premium sources (@ syntax)
SECTION_SOURCES = {
    "Executive Summary": "@crunchbase @pitchbook @bloomberg",
    "Business Overview": "@crunchbase @techcrunch @forbes",
    "Market Context": "@statista @cbinsights @pitchbook",
    "Team": "@crunchbase @linkedin",
    "Technology & Product": "@techcrunch @wired",
    "Traction & Milestones": "@crunchbase @techcrunch @bloomberg",
    "Funding & Terms": "@crunchbase @pitchbook @sec",
    "Risks & Mitigations": "@sec @bloomberg @reuters",
    "Investment Thesis": "@pitchbook @statista @cbinsights",
}

# Section-specific domain preferences (fallback if @ syntax insufficient)
SECTION_DOMAINS = {
    "Market Context": [
        "statista.com",
        "cbinsights.com",
        "pitchbook.com",
        "gartner.com",
        "-*.top10.com",
        "-*.saas-metrics.com"
    ],
    "Funding & Terms": [
        "crunchbase.com",
        "pitchbook.com",
        "sec.gov",
        "bloomberg.com",
        "-*.fundraising-guide.com"
    ],
    # ... add more sections as needed
}
```

**Modify query to include sources (Lines ~91-97):**

```python
# BEFORE
query = f"Research {company_name}'s {topic}"

# AFTER
section = determine_section_from_query(query)  # Or pass section as parameter
sources = SECTION_SOURCES.get(section, "@crunchbase @pitchbook")
query = f"Research {company_name}'s {topic}. {sources}"
```

### 3. Why Include Sources in Templates?

**Benefits:**

1. **Research Consistency** - All researchers/agents use the same quality sources
2. **Quality Control** - Prevents filler content from low-quality blogs
3. **Transparency** - Users know where data should come from
4. **Debugging** - Easy to verify if correct sources were used
5. **Agent Guidance** - LLM agents can read template and use recommended sources

**Two-tier approach:**
- **@ syntax sources** - Easy for Perplexity API queries
- **Domain URLs** - For reference, validation, and fallback to `search_domain_filter` if needed

### 4. Benefits of This Approach

✅ **Simple** - Just add strings to queries
✅ **No new parameters** - Works with existing code structure
✅ **No subscription upgrade** - Works with current API tier
✅ **Section-aware** - Different sources for different memo sections
✅ **Tested and confirmed** - Verified working via API (2025-11-22)
✅ **Template-documented** - Sources are now part of the section specification

---

## Quick Reference

### Confirmed Working Sources

| Source | Specialty | Use For |
|--------|-----------|---------|
| `@crunchbase` | Funding, investors, firmographics | All sections |
| `@pitchbook` | Valuations, market data, deals | Funding, Market, Investment Thesis |
| `@statista` | Statistics, market size, forecasts | Market Context |
| `@bloomberg` | Financial news, market data | Exec Summary, Funding, Risks |
| `@reuters` | Breaking news, verified reporting | Risks, News |
| `@forbes` | Business news, rankings | Business Overview |
| `@sec` | Regulatory filings, IPO data | Funding, Risks |
| `@cbinsights` | Market trends, startup tracking | Market Context, Investment Thesis |
| `@wiley` | Academic research | Technology deep dives |

### Usage Pattern

```python
# Pattern: Add @sources to end of query
query = f"{your_research_question} @source1 @source2 @source3"
```

---

## Testing

**Test script**: `test-perplexity-at-syntax.py` (in repo)

**Results**: ✅ @ syntax works via API, sources are mentioned and prioritized in results

---

## Next Steps

1. ✅ @ syntax confirmed working (2025-11-22)
2. ⬜ **Add `preferred_sources` to YAML outlines**:
   - Update `templates/outlines/direct-investment.yaml`
   - Update `templates/outlines/fund-commitment.yaml`
   - Add to all 10 sections in each file
3. ⬜ **Update research agent** to read sources from outlines:
   - Modify `src/agents/research_enhanced.py`
   - Load outline and extract `preferred_sources.perplexity_at_syntax`
   - Append to research queries
4. ⬜ **Update outline loader** (if needed):
   - Ensure `src/outline_loader.py` supports `preferred_sources` field
   - Add to schema validation
5. ⬜ Test memo generation with new source targeting
6. ⬜ Compare output quality before/after
7. ⬜ Document results in changelog

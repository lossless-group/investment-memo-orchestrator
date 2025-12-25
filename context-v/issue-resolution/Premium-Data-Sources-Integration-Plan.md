# Issue Resolution: Premium Data Sources Integration Plan

**Date Created**: 2025-11-22
**Status**: Planning - Ready for Implementation
**Priority**: HIGH
**Impact**: Eliminate industry benchmark filler, increase authoritative company-specific data

---

## Problem Statement

**Current Issue**: While Tier 1 fixes eliminated fabricated metrics (85% effectiveness), Perplexity still pads sections with generic industry benchmarks when company-specific data is unavailable:

> "Successful AI SaaS startups in 2025 commonly achieve $10,000–$100,000 in monthly recurring revenue (MRR) within 12 months of launch..."

**Problem**:
- These benchmarks come from generic SaaS blogs, not authoritative sources
- Creates confusion about whether data applies to THIS company
- Reduces memo quality and credibility
- Wastes API tokens on low-value content

**Root Cause**: Perplexity Sonar Pro searches the ENTIRE web, including:
- Generic SaaS marketing blogs
- "Top 10 SaaS metrics" articles
- Industry benchmark aggregators
- Competitor marketing sites

---

## Opportunity: Perplexity Premium Features

### Discovery

Perplexity's **Sonar API** ([launched January 2025](https://techcrunch.com/2025/01/21/perplexity-launches-sonar-an-api-for-ai-search/)) provides enterprise features for **customizing data sources**:

1. **`search_domain_filter`**: Restrict searches to specific authoritative domains
2. **`search_recency_filter`**: Filter by content recency
3. **`return_related_questions`**: Get follow-up questions for deeper research
4. **`return_images`**: Include company logos, product screenshots
5. **Sonar Pro tier**: Better for complex questions, deeper research

**Key Insight from [Perplexity Sonar Pro docs](https://docs.perplexity.ai/getting-started/models/models/sonar-pro)**:
> "The search_domain_filter parameter allows you to include specific domains: List domains to include or exclude (prefix with - to exclude). Target trusted sources: Use search_domain_filter to restrict searches to trusted or industry-specific domains."

**Example Use Case** ([from PromptFoo docs](https://www.promptfoo.dev/docs/providers/perplexity/)):
> "Limit medical queries to domains like nih.gov or who.int"

**For Investment Memos**: Limit company queries to authoritative VC/startup data sources

---

## Solution: Authoritative Source Filtering

### Strategy

Instead of searching the entire web, **restrict Perplexity to ONLY authoritative investment data sources**:

**Tier 1: Company-Specific Sources**
- Company website (`company.com`)
- Company blog/newsroom (`company.com/blog`, `company.com/news`)
- Company careers page (`company.com/careers`)
- Official press releases

**Tier 2: Verified Third-Party Data**
- **Crunchbase** (`crunchbase.com`) - Funding, investors, team
- **PitchBook** (`pitchbook.com`) - Valuations, cap tables, deals
- **SEC EDGAR** (`sec.gov`) - Public filings, financials
- **AngelList** (`angel.co`, `wellfound.com`) - Startup profiles
- **LinkedIn** (`linkedin.com`) - Team backgrounds, company updates

**Tier 3: Reputable Tech/VC News**
- **TechCrunch** (`techcrunch.com`) - Funding announcements
- **VentureBeat** (`venturebeat.com`) - Industry news
- **The Information** (`theinformation.com`) - In-depth reporting
- **Bloomberg** (`bloomberg.com`) - Financial news
- **WSJ** (`wsj.com`) - Business news

**Tier 4: VC Firm Blogs** (for fund research)
- Andreessen Horowitz blog (`a16z.com/blog`)
- Sequoia blog (`sequoiacap.com/article`)
- First Round Review (`review.firstround.com`)

**EXCLUDE Generic Sources**:
- Generic SaaS blogs (`*.saas-metrics.com`, `*.saas-guide.com`)
- Listicle sites (`*.top10.com`, `*.best-of.com`)
- Marketing comparison sites
- Industry benchmark aggregators

---

## Implementation Plan

### Phase 1: Research Agent Enhancement (Immediate)

**File**: `src/agents/research_enhanced.py`

**Current Implementation** (Lines 88-130):
```python
class PerplexityProvider(WebSearchProvider):
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": "sonar-pro",
                "messages": [{"role": "user", "content": query}],
            }
        )
```

**Enhanced Implementation**:
```python
class PerplexityProvider(WebSearchProvider):
    # Authoritative sources for investment research
    INVESTMENT_DATA_SOURCES = [
        # Tier 1: Company-specific (added dynamically per query)
        # Tier 2: Verified third-party data
        "crunchbase.com",
        "pitchbook.com",
        "sec.gov",
        "angel.co",
        "wellfound.com",
        "linkedin.com",
        # Tier 3: Reputable tech/VC news
        "techcrunch.com",
        "venturebeat.com",
        "theinformation.com",
        "bloomberg.com",
        "wsj.com",
        # Tier 4: VC firm blogs (for fund research)
        "a16z.com",
        "sequoiacap.com",
        "review.firstround.com",
    ]

    # Generic sources to exclude
    EXCLUDE_DOMAINS = [
        "-*.saas-metrics.com",
        "-*.saas-guide.com",
        "-*.top10.com",
        "-*.best-of.com",
        "-*.comparison.com",
        "-*.versus.com",
    ]

    def search(
        self,
        query: str,
        max_results: int = 10,
        company_domain: Optional[str] = None,  # NEW: Company's domain
        use_domain_filter: bool = True,  # NEW: Toggle filtering
    ) -> List[Dict[str, Any]]:
        """
        Search with domain filtering for authoritative sources.

        Args:
            query: Search query
            max_results: Max results to return
            company_domain: Company's website domain (e.g., "workback.ai")
            use_domain_filter: Whether to apply domain filtering
        """
        # Build domain filter
        search_domains = []

        if use_domain_filter:
            # Add company domain if provided
            if company_domain:
                search_domains.append(company_domain)
                search_domains.append(f"{company_domain}/blog")
                search_domains.append(f"{company_domain}/news")

            # Add authoritative sources
            search_domains.extend(self.INVESTMENT_DATA_SOURCES)

            # Add exclusions
            search_domains.extend(self.EXCLUDE_DOMAINS)

        # Call Perplexity API with domain filter
        payload = {
            "model": "sonar-pro",
            "messages": [{"role": "user", "content": query}],
        }

        if search_domains:
            payload["search_domain_filter"] = search_domains

        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload
        )

        # Rest of implementation...
```

**Benefits**:
- ✅ Eliminates generic SaaS blog filler
- ✅ Focuses on authoritative, verifiable sources
- ✅ Company domain automatically prioritized
- ✅ Can toggle filtering for debugging

---

### Phase 2: Section-Specific Source Lists (Advanced)

Different sections need different authoritative sources:

**Traction & Milestones**:
- Priority: Company blog, Crunchbase, TechCrunch
- Exclude: Industry benchmarks, generic SaaS guides

**Funding & Terms**:
- Priority: Crunchbase, PitchBook, SEC filings, TechCrunch
- Exclude: Generic fundraising advice blogs

**Team**:
- Priority: LinkedIn, company careers page, Crunchbase
- Exclude: Generic "how to build a team" articles

**Market Context**:
- Priority: Industry analyst reports, Bloomberg, WSJ, CB Insights
- Allow: Some industry research firms (Gartner, Forrester)

**Implementation**:
```python
SECTION_SOURCE_PRIORITIES = {
    "Traction & Milestones": {
        "include": ["crunchbase.com", "techcrunch.com", "sec.gov"],
        "exclude": ["-*.saas-metrics.com", "-*.benchmark.com"],
    },
    "Funding & Terms": {
        "include": ["crunchbase.com", "pitchbook.com", "sec.gov", "techcrunch.com"],
        "exclude": ["-*.fundraising-guide.com"],
    },
    "Team": {
        "include": ["linkedin.com", "crunchbase.com"],
        "exclude": ["-*.hiring-tips.com", "-*.team-building.com"],
    },
    "Market Context": {
        "include": ["bloomberg.com", "wsj.com", "cbinsights.com", "gartner.com"],
        "exclude": ["-*.market-size.com"],
    },
}

def get_domain_filter_for_section(section_name: str, company_domain: str) -> List[str]:
    """Get domain filter tailored to section needs."""
    base_domains = [company_domain]

    section_config = SECTION_SOURCE_PRIORITIES.get(section_name, {})
    base_domains.extend(section_config.get("include", []))
    base_domains.extend(section_config.get("exclude", []))

    return base_domains
```

---

### Phase 3: Recency Filtering for Time-Sensitive Data

**Problem**: Old funding announcements, outdated team info

**Solution**: Use `search_recency_filter` parameter

**Example**:
```python
payload = {
    "model": "sonar-pro",
    "messages": [{"role": "user", "content": query}],
    "search_domain_filter": domain_list,
    "search_recency_filter": "month",  # Options: hour, day, week, month, year
}
```

**Use Cases**:
- **Traction research**: `"month"` (recent metrics only)
- **Funding announcements**: `"year"` (last 12 months)
- **Team changes**: `"month"` (recent hires/departures)
- **Market trends**: `"year"` (current market dynamics)

---

### Phase 4: Related Questions for Deeper Research

**Feature**: `return_related_questions`

**Use Case**: When initial query returns insufficient data, use related questions to dig deeper

**Example**:
```python
payload = {
    "model": "sonar-pro",
    "messages": [{"role": "user", "content": "What is Work Back AI's revenue?"}],
    "search_domain_filter": authoritative_sources,
    "return_related_questions": True,
}

# Response includes:
{
    "answer": "Revenue data not publicly available...",
    "related_questions": [
        "Has Work Back AI announced any funding rounds?",
        "What customers has Work Back AI disclosed?",
        "What is Work Back AI's business model?",
    ]
}
```

**Implementation Strategy**:
1. If initial query returns "not available", check related questions
2. Follow up on 1-2 most relevant related questions
3. Aggregate findings from multiple angles

---

### Phase 5: Image Integration for Visual Context

**Feature**: `return_images`

**Use Cases**:
- Company logos (for trademark section)
- Product screenshots (for Technology & Product section)
- Team photos (for Team section)
- Pitch deck screenshots (if publicly available)

**Example**:
```python
payload = {
    "model": "sonar-pro",
    "messages": [{"role": "user", "content": "Work Back AI company logo"}],
    "return_images": True,
}

# Response includes:
{
    "images": [
        "https://workback.ai/logo.png",
        "https://crunchbase.com/workback-logo.jpg",
    ]
}
```

---

## Configuration System

### Environment Variables

Add to `.env`:
```bash
# Perplexity Premium Features
PERPLEXITY_USE_DOMAIN_FILTER=true
PERPLEXITY_USE_RECENCY_FILTER=true
PERPLEXITY_USE_RELATED_QUESTIONS=true
PERPLEXITY_USE_IMAGES=false

# Domain Filter Mode
PERPLEXITY_DOMAIN_FILTER_MODE=strict  # strict, moderate, permissive

# Recency Filter Default
PERPLEXITY_DEFAULT_RECENCY=month
```

### Domain Filter Modes

**Strict Mode** (Default):
- ONLY authoritative sources (Crunchbase, PitchBook, company site)
- EXCLUDE all generic blogs
- Risk: Might miss some data
- Benefit: Maximum quality, zero filler

**Moderate Mode**:
- Authoritative sources + reputable tech news
- EXCLUDE generic SaaS blogs
- Risk: Some marginal quality sources
- Benefit: Better coverage

**Permissive Mode**:
- Wide net, minimal exclusions
- Use when strict mode returns insufficient data
- Risk: More filler
- Benefit: Maximum coverage

---

## Expected Outcomes

### Quantitative Improvements

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Industry benchmark filler | ~30% | <5% | -83% |
| Authoritative citations | ~60% | >90% | +50% |
| "Generic SaaS" sources | ~25% | <2% | -92% |
| Company-specific data | ~50% | >75% | +50% |
| Overall quality score | 85% | >95% | +12% |

### Qualitative Improvements

**Before** (Generic filler):
> "AI SaaS startups typically achieve $10K-$100K MRR within 12 months. The average CAC for B2B SaaS is $1,200, with LTV:CAC ratios between 3:1 and 5:1. Net revenue retention benchmarks suggest 110-120% for successful SaaS companies."

**After** (Authoritative or honest):
> According to Crunchbase [^1], Work Back AI raised a $2M seed round in March 2024 from Sequoia Capital. The company's website states they serve "Fortune 500 enterprises" but does not disclose specific customer names. [^2] Revenue and growth metrics have not been publicly disclosed.

**Improvement**:
- ✅ All claims from authoritative sources (Crunchbase, company site)
- ✅ Specific to THIS company
- ✅ Citations to verifiable sources
- ✅ Honest about gaps without generic filler
- ✅ No industry benchmarks masquerading as company data

---

## Implementation Steps

### Step 1: Update Research Agent (2 hours)

**File**: `src/agents/research_enhanced.py`

- [ ] Add `INVESTMENT_DATA_SOURCES` constant
- [ ] Add `EXCLUDE_DOMAINS` constant
- [ ] Modify `PerplexityProvider.search()` to accept `company_domain`
- [ ] Build `search_domain_filter` list dynamically
- [ ] Add `search_recency_filter` parameter
- [ ] Test with Work Back AI example

### Step 2: Extract Company Domain from State (30 min)

**File**: `src/agents/research_enhanced.py`

- [ ] Extract domain from `state["url"]` field
- [ ] Pass to Perplexity provider
- [ ] Handle cases where URL missing

```python
def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    # https://workback.ai/about -> workback.ai
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "")
```

### Step 3: Add Section-Specific Filters (2 hours)

**File**: `src/agents/research_enhanced.py`

- [ ] Create `SECTION_SOURCE_PRIORITIES` dict
- [ ] Implement `get_domain_filter_for_section()`
- [ ] Update research calls to use section-specific filters
- [ ] Test each section type

### Step 4: Configuration & Environment (1 hour)

- [ ] Add environment variables to `.env.example`
- [ ] Update `CLAUDE.md` with new configuration
- [ ] Add domain filter mode switching
- [ ] Document in README

### Step 5: Testing & Validation (3 hours)

- [ ] Test on Work Back AI (seed, minimal data)
- [ ] Test on Avalanche (fund, some data)
- [ ] Test on public company (lots of data)
- [ ] Measure filler reduction
- [ ] Validate source quality

### Step 6: Documentation (1 hour)

- [ ] Update `CLAUDE.md` with premium features
- [ ] Create usage examples
- [ ] Document troubleshooting
- [ ] Update changelog

**Total Estimated Time**: 9-10 hours

---

## Testing Protocol

### Test Case 1: Seed Company (High Filler Risk)

**Company**: Work Back AI
**Expected Before**: 30% industry benchmark filler
**Expected After**: <5% filler, mostly "data not available" statements

**Validation**:
- Count industry benchmark mentions
- Verify all citations are authoritative sources
- Check for generic SaaS blog citations

### Test Case 2: Series A Company (Moderate Data)

**Company**: [Select company with TechCrunch coverage but no public metrics]
**Expected Before**: 20% filler
**Expected After**: <3% filler, more Crunchbase/TechCrunch citations

**Validation**:
- Verify funding data from Crunchbase
- Check team data from LinkedIn
- Ensure no generic benchmarks

### Test Case 3: Public Company (High Data Availability)

**Company**: [Select public company with SEC filings]
**Expected Before**: 10% filler (less needed)
**Expected After**: <1% filler, all SEC/Bloomberg citations

**Validation**:
- All financial data from SEC filings
- No generic industry benchmarks
- High citation quality

---

## Rollout Plan

### Week 1: Core Implementation
- Day 1-2: Research agent domain filtering
- Day 3: Company domain extraction
- Day 4: Testing on 3 companies
- Day 5: Bug fixes and refinements

### Week 2: Advanced Features
- Day 1-2: Section-specific filters
- Day 3: Recency filtering
- Day 4: Related questions integration
- Day 5: Full system testing

### Week 3: Validation
- Day 1-3: Generate 10 memos with new system
- Day 4: Measure filler reduction
- Day 5: Documentation and rollout

---

## Success Metrics

### Critical Success Factors

- ✅ Industry benchmark filler reduced to <5%
- ✅ All citations from authoritative sources (Crunchbase, PitchBook, company, reputable news)
- ✅ Zero generic SaaS blog citations
- ✅ Company-specific data coverage increased >25%
- ✅ Overall memo quality score >95%

### Monitoring

Track for every memo:
```json
{
  "company": "Work Back AI",
  "sources_breakdown": {
    "company_domain": 15,
    "crunchbase": 8,
    "linkedin": 6,
    "techcrunch": 4,
    "generic_blogs": 0,
    "total": 33
  },
  "filler_percentage": 2.1,
  "quality_score": 96,
  "timestamp": "2025-11-22"
}
```

---

## Risk Mitigation

### Risk 1: Over-Filtering (Missing Data)

**Issue**: Strict filtering might exclude valid sources

**Mitigation**:
- Start with "moderate" mode by default
- If results insufficient, automatically retry with "permissive" mode
- Log when fallback occurs for analysis

### Risk 2: API Tier Requirements

**Issue**: `search_domain_filter` requires Tier 3 per documentation

**Mitigation**:
- Verify current API tier
- Upgrade if necessary
- Fall back to standard search if feature unavailable

### Risk 3: Company Domain Unknown

**Issue**: Some companies in `data/*.json` may not have URL

**Mitigation**:
- Use company name-based search as fallback
- Still apply authoritative source filtering
- Log missing domains for manual addition

---

## Cost-Benefit Analysis

### Costs

**Development Time**: 9-10 hours
**API Tier Upgrade**: Potentially $0-$50/month (if tier upgrade needed)
**Maintenance**: Minimal (update domain lists quarterly)

### Benefits

**Quality Improvement**: 85% → 95% (12% increase)
**Filler Reduction**: 30% → <5% (83% reduction)
**Time Savings**: Partners spend less time validating memo accuracy
**Trust Increase**: Memos can be shared externally without embarrassment
**Decision Quality**: Better decisions from higher-quality data

**ROI**: Significant positive impact for minimal cost

---

## Related Work

### Tier 1 Anti-Hallucination (Completed)
- Eliminated fabricated metrics (100% success)
- Achieved 85% overall effectiveness
- Established honesty about data gaps

### Tier 2 Premium Sources (This Plan)
- Eliminate industry benchmark filler
- Target 95% effectiveness
- Increase authoritative citations

### Tier 3 Fact-Checker Agent (Future)
- Automated validation of all claims
- Target 98%+ effectiveness
- Complete fabrication prevention

---

## References

### Perplexity Documentation
- [Sonar Pro API](https://docs.perplexity.ai/getting-started/models/models/sonar-pro)
- [Chat Completions API](https://docs.perplexity.ai/api-reference/chat-completions-post)
- [Perplexity API Platform](https://www.perplexity.ai/api-platform)

### Related Articles
- [TechCrunch: Perplexity launches Sonar API](https://techcrunch.com/2025/01/21/perplexity-launches-sonar-an-api-for-ai-search/)
- [PromptFoo: Perplexity Provider Docs](https://www.promptfoo.dev/docs/providers/perplexity/)
- [Analytics Vidhya: Perplexity Sonar API Guide](https://www.analyticsvidhya.com/blog/2025/01/perplexity-sonar-api/)

### Internal Documents
- `context-vigilance/issue-resolution/Preventing-Hallucinations-in-Memo-Generation.md`
- `context-vigilance/issue-resolution/Tier-1-Test-Results-WorkBack.md`
- `changelog/2025-11-22_01.md`

---

**Status**: ✅ **PLAN COMPLETE - READY FOR IMPLEMENTATION**
**Priority**: HIGH (closes 15% effectiveness gap from Tier 1)
**Estimated Impact**: 85% → 95% effectiveness (+12%)
**Implementation Time**: 9-10 hours
**Recommended Start**: Immediate (following Tier 1 success)

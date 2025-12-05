# Disambiguation Management Across Agents

**Date Created**: 2025-11-28
**Status**: IMPLEMENTED (core), IN_PROGRESS (exclusion list feature)
**Priority**: CRITICAL
**Last Updated**: 2025-12-05
**Related Issues**:
- `context-vigilance/issue-resolution/Preventing-Hallucinations-in-Memo-Generation.md`
- `context-vigilance/Anti-Hallucination-Fact-Checker-Agent.md`

---

## Problem Statement

### The Entity Confusion Problem

When generating investment memos, LLMs (including web-grounded models like Perplexity Sonar Pro) frequently confuse companies with similar or identical names. This is **distinct from hallucination** - the model isn't inventing data, it's retrieving **real data about the wrong company**.

**Example Case: Sava (November 2025)**

| Attribute | Target Company | Confused With |
|-----------|----------------|---------------|
| Name | Sava (Sava Lakh, Inc.) | Sava Technologies |
| Domain | savahq.com | sava.ai |
| Business | AI-powered trust administration | Glucose biosensor/CGM |
| Stage | YC F25, Pre-charter | Series A ($19M raised) |
| Location | San Francisco | London (Imperial College) |

**Result**: The Funding & Terms section contained detailed, accurate information about a $19M Series A round - for the **completely wrong company**. This passed initial quality checks because:
1. The data was factually accurate (for Sava Technologies)
2. It was well-cited with legitimate sources
3. It followed the correct format and structure

The fact-checker flagged the discrepancy only because the funding timeline didn't match other sections.

### Why This Is Different From Hallucination

| Hallucination | Entity Confusion |
|---------------|------------------|
| LLM invents plausible-sounding data | LLM retrieves real data for wrong entity |
| No source exists for the claim | Sources exist but reference wrong company |
| Detectable by source verification | Requires semantic understanding to detect |
| "The company has $5M ARR" (invented) | "The company raised $19M Series A" (true, but wrong company) |

### Impact Assessment

**Severity: CRITICAL**

1. **Trust Destruction**: Wrong-company data is harder to catch than invented data
2. **Professional Embarrassment**: Sending a memo with competitor's metrics to founders
3. **Investment Risk**: Making decisions based on another company's performance
4. **Legal Exposure**: Misrepresenting material facts in investment documents
5. **Cascade Effect**: One confused section can propagate errors to others

---

## Root Cause Analysis

### Cause 1: Ambiguous Company Names

Many startups share names with other entities:
- **Sava** (trust platform) vs **Sava Technologies** (biosensor)
- **Mercury** (banking) vs **Mercury** (many others)
- **Notion** (productivity) vs **Notion** (AI note-taking)
- **Runway** (video AI) vs **Runway** (fintech)

Search engines and LLMs default to the **most prominent** entity with that name, which is often NOT the early-stage startup we're researching.

### Cause 2: Insufficient Context in Prompts

**Before Fix - Research Agent Prompt:**
```python
{"role": "system", "content": "You are a research assistant providing detailed, cited information for investment analysis."},
{"role": "user", "content": f"{company_name} funding investors Crunchbase"}
```

**Problem**: No disambiguation signal. Perplexity searches for "Sava" and returns the first/most prominent result.

**Before Fix - Section Research Query:**
```python
query = f"""Research and write comprehensive content for the "{section_name}"
section of an investment memo about {company_name}.

COMPANY OVERVIEW:
{company_description}
"""
```

**Problem**: Company description was provided but not emphasized as a disambiguation constraint.

### Cause 3: Domain Hints Insufficient

The research agent used `site:` domain hints:
```python
domain_hint = f"site:{parsed.netloc}"
query = f"{company_name} {domain_hint} funding investors"
# Result: "Sava site:savahq.com funding investors"
```

**Problem**:
- `site:` only prioritizes results from that domain
- Perplexity still returns results from other domains
- LLM may synthesize data from wrong-company sources alongside correct ones

### Cause 4: No Cross-Validation

The pipeline had no mechanism to verify that retrieved data actually pertained to the target company:
- Research phase: Retrieved data without entity verification
- Section research: Generated citations without domain matching
- Writer: Used all provided data without source validation
- Citation enrichment: Added more citations without entity checks

---

## Three-Layer Defense Architecture

### Layer 1: Query-Level Disambiguation

**Where**: Every LLM API call that performs research

**Mechanism**: Include explicit disambiguation context in system prompts and queries

**Implementation Locations**:
1. `src/agents/research_enhanced.py` - PerplexityProvider.search()
2. `src/agents/perplexity_section_researcher.py` - build_section_research_query()
3. `cli/improve_section.py` - improve_section_with_sonar_pro()

### Layer 2: Source-Level Verification

**Where**: Citation enrichment and validation phases

**Mechanism**: Verify that cited sources reference the correct entity by checking:
- Domain matches company URL
- Company description terms appear in source
- No conflicting entity identifiers (different founding date, location, business model)

### Layer 3: Cross-Section Consistency

**Where**: Fact-checker and validator agents

**Mechanism**: Detect entity confusion by identifying contradictions:
- Founding date in Team section vs Funding section
- Business model in Business Overview vs Traction
- Team size in Team vs other mentions

---

## Implementation Specification

### Data Model: Disambiguation Context

**Source**: `data/{CompanyName}.json` or `io/{firm}/deals/{Deal}/{Deal}.json`

```json
{
  "type": "direct",
  "mode": "consider",
  "description": "Sava is a financial and legal technology platform specialized in quickly setting up and managing Trusts",
  "url": "https://www.savahq.com",
  "stage": "Series A",
  "deck": "data/Secure-Inputs/2025-11_Sava-Fundraising-Deck--Series-A.pdf",
  "notes": "Focus on team backgrounds, technology platform, and market positioning.",
  "disambiguation": [
    "https://sava.ai",
    "https://www.savatechnologies.com"
  ]
}
```

**Critical Fields for Disambiguation**:

| Field | Purpose | Example |
|-------|---------|---------|
| `description` | Semantic identifier | "AI-powered trust administration platform" |
| `url` | Domain anchor (CORRECT company) | "https://www.savahq.com" |
| `notes` | Additional research guidance | "Focus on team backgrounds..." |
| `disambiguation` | **NEW**: Array of WRONG-entity URLs to exclude | `["https://sava.ai", "https://othersava.com"]` |

### The `disambiguation` Field

The `disambiguation` array contains URLs of **wrong entities** that share a similar name. When the research agents encounter sources from these domains, they should:

1. **DISCARD** any data from those sources
2. **NOT CITE** those URLs
3. **Flag** if significant content was found there (indicates confusion risk)

**Example for Reson8:**
```json
{
  "name": "Reson8",
  "url": "https://reson8.xyz/",
  "disambiguation": [
    "https://www.reson8.group/",
    "https://www.reson8media.com/",
    "https://reson8sms.com/"
  ]
}
```

**Prompt Integration:**
```
EXCLUDED ENTITIES (DO NOT USE DATA FROM THESE):
- reson8.group (different company)
- reson8media.com (different company)
- reson8sms.com (different company)

If you find information from these domains, DISCARD IT completely.
```

### State Propagation

Disambiguation context flows through the pipeline via `MemoState`:

```
data/{Company}.json or io/{firm}/deals/{Deal}/{Deal}.json
        ↓
    main.py (loads JSON, populates state)
        ↓
    MemoState {
        company_name: "Sava",
        company_description: "...",
        company_url: "https://www.savahq.com",
        research_notes: "...",
        disambiguation_excludes: ["sava.ai", "savatechnologies.com"]  # NEW
    }
        ↓
    All agents receive full state
```

**State Field**: `disambiguation_excludes`
- **Source**: `disambiguation` array in JSON config
- **Type**: `List[str]` of domains to exclude
- **Processing**: URLs are parsed to extract domains (e.g., `https://sava.ai` → `sava.ai`)

### Implementation 1: PerplexityProvider.search()

**File**: `src/agents/research_enhanced.py`
**Lines**: 134-173

```python
def search(
    self,
    query: str,
    max_results: int = 10,
    sources: Optional[List[str]] = None,
    disambiguation_context: Optional[str] = None  # NEW PARAMETER
) -> List[Dict[str, str]]:
    """
    Search using Perplexity API with entity disambiguation.

    Args:
        disambiguation_context: Company identification info to prevent
                               confusion with similarly-named entities
    """
    # Build system prompt with disambiguation
    system_prompt = "You are a research assistant providing detailed, cited information for investment analysis."

    if disambiguation_context:
        system_prompt += f"""

CRITICAL DISAMBIGUATION:
{disambiguation_context}

ONLY return information about the CORRECT company. If search results contain
data about a DIFFERENT company with a similar name, DISCARD that data and
state that you could not find information for the correct entity."""

    response = self.client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": enhanced_query}
        ]
    )
```

**Disambiguation Context Format**:
```
Target company: Sava
Description: Sava is a financial and legal technology platform...
Website: https://www.savahq.com
Domain: savahq.com
Notes: Ensure research is about SavaHQ, NOT other companies named Sava.
```

### Implementation 2: Research Agent Context Building

**File**: `src/agents/research_enhanced.py`
**Lines**: 291-307

```python
# Build disambiguation context for Perplexity searches
disambiguation_context = None
if company_description or company_url:
    disambiguation_parts = [f"Target company: {company_name}"]

    if company_description:
        disambiguation_parts.append(f"Description: {company_description}")

    if company_url:
        parsed = urlparse(company_url)
        domain = parsed.netloc if parsed.netloc else company_url
        disambiguation_parts.append(f"Website: {company_url}")
        disambiguation_parts.append(f"Domain: {domain}")

    if research_notes:
        disambiguation_parts.append(f"Notes: {research_notes}")

    disambiguation_context = "\n".join(disambiguation_parts)
    print(f"Disambiguation context built for entity verification")
```

### Implementation 3: Section Research Queries

**File**: `src/agents/perplexity_section_researcher.py`
**Lines**: 137-155

```python
# Build disambiguation block if we have identifying info
disambiguation_block = ""
if company_url or research_notes:
    disambiguation_block = f"""
CRITICAL - ENTITY DISAMBIGUATION:
There may be multiple companies named "{company_name}". You MUST research the CORRECT company:
- Company website: {company_url or 'See description'}
- Description: {company_description}
"""
    if research_notes:
        disambiguation_block += f"- Research notes: {research_notes}\n"

    disambiguation_block += """
DISAMBIGUATION RULES:
1. ONLY use sources that reference THIS specific company
2. If you find funding/revenue data for a DIFFERENT company with the same name, DISCARD IT
3. Cross-reference company website to verify you have the correct entity
4. If unsure, state "Data not verified for this entity" rather than include wrong data
"""
```

### Implementation 4: Section Improvement Tool

**File**: `cli/improve_section.py`
**Lines**: 153-183

```python
# Get disambiguation context from state
company_description = state.get("company_description", "")
company_url = state.get("company_url", "")
research_notes = state.get("research_notes", "")

# Build disambiguation block
disambiguation_context = ""
if company_description or company_url:
    disambiguation_context = f"""
CRITICAL - ENTITY DISAMBIGUATION:
There may be multiple companies named "{company_name}". You MUST research the CORRECT company:

"""
    if company_description:
        disambiguation_context += f"COMPANY DESCRIPTION: {company_description}\n"
    if company_url:
        domain = company_url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        disambiguation_context += f"OFFICIAL WEBSITE: {company_url}\n"
        disambiguation_context += f"DOMAIN TO MATCH: {domain}\n"
    if research_notes:
        disambiguation_context += f"RESEARCH NOTES: {research_notes}\n"

    disambiguation_context += f"""
DISAMBIGUATION RULES:
1. ONLY use sources that reference THIS specific company (website: {company_url or 'see description'})
2. If you find data for a DIFFERENT company with the same name, DISCARD IT
3. When citing funding/revenue/metrics, verify the source mentions the correct company
4. If unsure whether data is about the right company, state "Data not verified for this entity"
5. Cross-reference with company website ({company_url}) to confirm you have the right entity
"""
```

---

## Disambiguation Rules (Standardized)

All agents use these consistent rules:

### Rule 1: Source Domain Matching
```
ONLY use sources that reference THIS specific company (website: {url})
```

### Rule 2: Wrong-Entity Data Discard
```
If you find funding/revenue/metrics for a DIFFERENT company with the same name, DISCARD IT
```

### Rule 3: Explicit Exclusion List (NEW)
```
EXCLUDED DOMAINS - DO NOT USE DATA FROM:
{list of domains from disambiguation_excludes}

If you encounter sources from these domains, they are about a DIFFERENT company.
DISCARD all information from these sources completely.
```

### Rule 4: Source Verification
```
When citing specific data, verify the source mentions the correct company
```

### Rule 5: Uncertainty Acknowledgment
```
If unsure whether data is about the right company, state "Data not verified for this entity"
```

### Rule 6: Cross-Reference Requirement
```
Cross-reference with company website to confirm you have the correct entity
```

### Building the Exclusion Block

When `disambiguation_excludes` is populated, add to prompts:

```python
# Build exclusion block from disambiguation array
exclusion_block = ""
if disambiguation_excludes and len(disambiguation_excludes) > 0:
    exclusion_block = "\nEXCLUDED ENTITIES - DO NOT USE DATA FROM THESE DOMAINS:\n"
    for domain in disambiguation_excludes:
        exclusion_block += f"- {domain} (WRONG company, different entity)\n"
    exclusion_block += "\nIf you find information from these domains, DISCARD IT completely.\n"
```

---

## Testing Protocol

### Test Case 1: Known Ambiguous Name

**Setup**:
```json
{
  "description": "AI-powered trust administration platform for wealth managers",
  "url": "https://www.savahq.com",
  "notes": "Research SavaHQ only, NOT Sava Technologies (biosensor company)"
}
```

**Expected Behavior**:
- No references to biosensor, CGM, glucose monitoring
- No funding data from Sava Technologies ($19M Series A)
- All citations reference savahq.com or YC profile
- Explicit acknowledgment if data unavailable: "Funding details not publicly disclosed"

**Validation**:
```bash
# Check for wrong-entity contamination
grep -i "biosensor\|glucose\|CGM\|Imperial College" output/Sava-v0.0.x/2-sections/*.md
# Should return no results

# Check citations reference correct domain
grep -o 'https://[^)]*' output/Sava-v0.0.x/4-final-draft.md | grep -v savahq.com | grep -v ycombinator.com
# Review any non-company URLs for relevance
```

### Test Case 2: Highly Ambiguous Name

**Setup** (hypothetical):
```json
{
  "name": "Mercury",
  "description": "Business banking platform for startups",
  "url": "https://mercury.com",
  "notes": "Mercury the fintech bank, NOT Mercury Insurance, Mercury Systems, or other entities"
}
```

**Validation Points**:
- Business model references banking/fintech, not insurance or defense
- Founders are Immad Akhund and team, not other Mercury executives
- Funding references match Mercury fintech timeline

### Test Case 3: No Disambiguation Context

**Setup** (incomplete data file):
```json
{
  "description": "Startup in stealth mode",
  "url": ""
}
```

**Expected Behavior**:
- System proceeds without disambiguation (graceful degradation)
- Higher risk of entity confusion acknowledged in output
- Fact-checker may flag inconsistencies for human review

---

## Monitoring and Alerting

### Detection Signals

**Signal 1: Cross-Section Contradictions**
- Founding date differs between sections
- Team size inconsistent
- Business model descriptions conflict

**Signal 2: Domain Mismatch in Citations**
- Citations reference domains other than company URL
- Multiple different company websites cited

**Signal 3: Keyword Contamination**
Check for terms associated with wrong entities:
```python
# Example for Sava case
wrong_entity_terms = ["biosensor", "glucose", "CGM", "Imperial College", "London"]
for term in wrong_entity_terms:
    if term.lower() in section_content.lower():
        flag_for_review(f"Possible entity confusion: found '{term}'")
```

### Logging

Add disambiguation logging to track effectiveness:

```python
# In research_enhanced.py
if disambiguation_context:
    print(f"[DISAMBIGUATION] Context built for {company_name}")
    print(f"[DISAMBIGUATION] Domain anchor: {domain}")

# After search
print(f"[DISAMBIGUATION] Search returned {len(results)} results")
# Log source domains for verification
```

---

## Best Practices for Data File Authors

### Required Fields for Ambiguous Names

When creating `data/{Company}.json` for companies with common names:

```json
{
  "description": "SPECIFIC description with unique identifiers (product, market, technology)",
  "url": "REQUIRED - official company website",
  "notes": "EXPLICIT disambiguation: 'Research X company only, NOT Y company'"
}
```

### Disambiguation Checklist

Before running memo generation:

- [ ] Is the company name shared with other known entities?
- [ ] Is `url` field populated with official website?
- [ ] Does `description` contain unique identifiers?
- [ ] Does `notes` explicitly exclude confusable entities?

### High-Risk Name Patterns

Names requiring extra disambiguation care:
- Single common words: "Notion", "Runway", "Mercury", "Stripe"
- Acronyms: "AI", "ML", "AR" companies
- Generic tech terms: "Quantum", "Cloud", "Data"
- Appended suffixes: "X Labs", "X AI", "X Tech"

---

## Failure Modes and Mitigations

### Failure Mode 1: Disambiguation Ignored

**Symptom**: Despite context, LLM returns wrong-company data

**Mitigation**:
- Move disambiguation to system prompt (higher priority)
- Use stronger language: "CRITICAL", "MUST", "FORBIDDEN"
- Add consequence framing: "Wrong-entity data will be rejected"

### Failure Mode 2: Partial Contamination

**Symptom**: Some sections correct, others confused

**Mitigation**:
- Cross-section consistency checking in fact-checker
- Flag founding date/team/business model contradictions
- Human review trigger for detected inconsistencies

### Failure Mode 3: Over-Filtering

**Symptom**: System discards legitimate data as "wrong entity"

**Mitigation**:
- Allow data from third-party sources (TechCrunch, Crunchbase) that reference correct company
- Don't require exact domain match for news articles
- Use semantic matching: does source describe same business model?

### Failure Mode 4: No Disambiguation Context Available

**Symptom**: Early-stage company with minimal public presence

**Mitigation**:
- Rely more heavily on deck analysis as ground truth
- Flag sections with significant external research as "unverified"
- Recommend human verification for key metrics

---

## Integration Points

### Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| `src/agents/research_enhanced.py` | Lines 134-173, 291-307, 403-412 | Perplexity search disambiguation |
| `src/agents/perplexity_section_researcher.py` | Lines 86-88, 137-155, 200-202, 286-288 | Section research disambiguation |
| `cli/improve_section.py` | Lines 153-183, 225 | Section improvement disambiguation |

### State Fields Used

| Field | Source | Agents Using |
|-------|--------|--------------|
| `company_name` | JSON / CLI | All |
| `company_description` | JSON `description` | research_enhanced, perplexity_section_researcher, improve_section |
| `company_url` | JSON `url` | research_enhanced, perplexity_section_researcher, improve_section |
| `research_notes` | JSON `notes` | research_enhanced, perplexity_section_researcher, improve_section |
| `disambiguation_excludes` | JSON `disambiguation` | research_enhanced, perplexity_section_researcher, improve_section |

### Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    data/{Company}.json                          │
│  {description, url, notes} → disambiguation context             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Deck Analyst                                  │
│  (No disambiguation needed - works with provided PDF)           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Research Agent (research_enhanced.py)            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ PerplexityProvider.search()                             │    │
│  │ + disambiguation_context in system prompt               │    │
│  │ + domain hints in query                                 │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│          Section Researcher (perplexity_section_researcher.py)   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ build_section_research_query()                          │    │
│  │ + CRITICAL DISAMBIGUATION block in query                │    │
│  │ + company_url and research_notes passed through         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  For each of 10 sections:                                       │
│    → Perplexity Sonar Pro with disambiguation                   │
│    → Save to 1-research/{section}-research.md                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Writer Agent                             │
│  (Polishes research files - disambiguation already applied)     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Enrichment Agents                             │
│  Trademark, Socials, Links, Citations                           │
│  (Work with already-disambiguated content)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Fact Checker                                │
│  Cross-section consistency checks can detect entity confusion   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               Section Improvement (cli/improve_section.py)       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ improve_section_with_sonar_pro()                        │    │
│  │ + Full disambiguation context from state                │    │
│  │ + DISAMBIGUATION RULES block in prompt                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│  Can be run post-pipeline to fix confused sections              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Success Metrics

### Quantitative

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Wrong-entity sections per memo | 1-3 | 0 | 0 |
| Entity confusion detection rate | Manual | Automated | 95%+ |
| False positive rate (over-filtering) | N/A | <5% | <5% |

### Qualitative

1. **Founder Validation**: Founders recognize their own company's data
2. **Cross-Section Consistency**: No contradictory company descriptions
3. **Citation Quality**: All citations reference correct entity
4. **Graceful Degradation**: When data unavailable, says so rather than using wrong data

---

## Future Enhancements

### Enhancement 1: Automated Entity Verification

Add post-research verification step:
```python
def verify_entity_match(citation_url: str, company_url: str, company_description: str) -> bool:
    """
    Fetch citation URL and verify it references the correct company.

    Checks:
    - Domain relationship (same domain, or mentions company domain)
    - Business description match
    - Key identifier presence (founder names, product names)
    """
```

### Enhancement 2: Entity Confusion Detector

Add to fact-checker:
```python
def detect_entity_confusion(sections: Dict[str, str]) -> List[str]:
    """
    Cross-reference sections for entity confusion signals.

    Detects:
    - Founding date inconsistencies
    - Location contradictions
    - Business model conflicts
    - Team member name mismatches
    """
```

### Enhancement 3: Known Entities Database

Maintain database of known confusable entities:
```json
{
  "Sava": {
    "target": {"domain": "savahq.com", "business": "trust administration"},
    "confusables": [
      {"domain": "sava.ai", "business": "biosensor", "exclude_terms": ["glucose", "CGM"]}
    ]
  }
}
```

### Enhancement 4: User Confirmation for Ambiguous Names

When company name matches known ambiguous pattern:
```
⚠️  "Sava" matches multiple known entities:
  1. Sava (savahq.com) - Trust administration platform
  2. Sava Technologies (sava.ai) - Glucose biosensor company

Proceeding with: Sava (savahq.com) based on provided URL
```

---

## Appendix: Example Disambiguation Blocks

### Full Disambiguation (High-Risk Name)

```
CRITICAL - ENTITY DISAMBIGUATION:
There may be multiple companies named "Sava". You MUST research the CORRECT company:

COMPANY DESCRIPTION: Sava is a financial and legal technology platform specialized in quickly setting up and managing Trusts (the legal entities)
OFFICIAL WEBSITE: https://www.savahq.com
DOMAIN TO MATCH: savahq.com
RESEARCH NOTES: Focus on team backgrounds, technology platform, and market positioning. Ensure research is about SavaHQ (savahq.com), NOT other companies named Sava.

DISAMBIGUATION RULES:
1. ONLY use sources that reference THIS specific company (website: https://www.savahq.com)
2. If you find data for a DIFFERENT company with the same name, DISCARD IT
3. When citing funding/revenue/metrics, verify the source mentions the correct company
4. If unsure whether data is about the right company, state "Data not verified for this entity"
5. Cross-reference with company website (https://www.savahq.com) to confirm you have the right entity
```

### Minimal Disambiguation (Unique Name)

```
Target company: UniqueStartupName
Description: AI-powered widget optimization for enterprise
Website: https://uniquestartupname.com
Domain: uniquestartupname.com
```

### No Disambiguation (Fallback)

When no identifying info available, system proceeds without disambiguation block but with higher scrutiny in validation phase.

---

## References

- **Hallucination Prevention**: `context-vigilance/issue-resolution/Preventing-Hallucinations-in-Memo-Generation.md`
- **Fact Checker Design**: `context-vigilance/Anti-Hallucination-Fact-Checker-Agent.md`
- **Perplexity API Reference**: `context-vigilance/issue-resolution/Perplexity-Premium-API-Calls-Reference.md`

---

**Document Owner**: Investment Memo Orchestrator Team
**Last Updated**: 2025-11-28
**Review Cadence**: After each entity confusion incident

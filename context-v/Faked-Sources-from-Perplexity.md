# Faked Sources from Perplexity

## Problem Summary

Perplexity Sonar Pro, used for citation enrichment in the memo generation pipeline, produces **hallucinated URLs** that appear legitimate but do not exist. These are not `example.com` placeholders—they use real domains with fabricated paths.

## Discovery (2025-12-14)

During ProfileHealth memo generation, the citation validator flagged URLs returning HTTP error codes:

| Error Type | Count | Description |
|-----------|-------|-------------|
| HTTP 404 | 8 | **Page not found** - URL path doesn't exist |
| HTTP 403 | 18 | Forbidden - could be real (bot-blocked) or fake |
| HTTP 401 | 3 | Unauthorized - likely real but paywalled |
| Timeout | 9 | Server slow - likely real (McKinsey, etc.) |
| Other | 1 | Obvious placeholder (`XXXXX` in URL) |

## Confirmed Hallucinations

### 1. Obvious Placeholder
```
[^41]: https://www.nature.com/articles/s41591-025-XXXXX
```
The `XXXXX` is clearly a placeholder. Real Nature article IDs follow format like `s41591-024-02897-9`.

### 2. 404 Errors (Non-Existent Pages)

These URLs use real domains but paths that don't exist:

| Citation | URL | Issue |
|----------|-----|-------|
| [^8] | `healthit.gov/topic/clinician-burnout` | 404 - Path doesn't exist |
| [^11] | `healthsystemtracker.org/brief/out-of-pocket-spending-in-the-u-s-health-care-system-2022` | 404 - Plausible but fake |
| [^39] | `techcrunch.com/2024/09/30/why-freemium-is-gaining-traction-in-digital-health/` | 404 - Article doesn't exist |
| [^55] | `nam.edu/ehr-and-physician-burnout` | 404 - Path doesn't exist |
| [^36] | `forbes.com/sites/forbestechcouncil/2025/04/22/how-digital-health-platforms-unlock-ancillary-revenue-streams/` | 403 - Future date (Apr 2025) |
| [^40] | `axios.com/2025/07/08/health-tech-ai-pilots-scaling` | 403 - Future date (Jul 2025) |

### 3. Suspicious Patterns

**Future Dates**: Several citations have publication dates in 2025 that were in the future when researched:
- `Published: 2025-04-10`
- `Published: 2025-06-15`
- `Published: 2025-08-14`

**Generic Document IDs**: URLs like `gartner.com/document/4012345` use suspiciously round numbers.

## Root Cause

Perplexity Sonar Pro generates citations by:
1. Understanding the content topic
2. Identifying relevant publication names (McKinsey, Nature, Forbes)
3. **Fabricating plausible-looking URLs** based on known URL patterns
4. Assigning dates that seem reasonable

The model doesn't actually verify these URLs exist—it generates them based on patterns learned during training.

## Impact

- **Credibility Risk**: Readers clicking citations find broken links
- **Verification Failure**: Cannot trace claims to actual sources
- **Regulatory Risk**: In investment memos, unsourced claims could be problematic

## Comparison: Before vs After Pipeline Improvements

| Metric | Old Pipeline | New Pipeline |
|--------|-------------|--------------|
| Citation format | `example.com` placeholders | Real domains |
| URL realism | Obviously fake | Plausibly fake |
| Detectability | Easy (all `example.com`) | Requires HTTP validation |
| Valid citations | 0% | ~57% |

## Proposed Solution

Create a **Citation Cleanup Agent** that:

1. **Validates all URLs** via HTTP HEAD requests
2. **Flags 404s** as definite hallucinations for removal
3. **Handles 403/401** as potentially valid (paywalled content)
4. **Removes citations** with obvious placeholders (`XXXXX`, `example.com`)
5. **Renumbers remaining citations** to maintain sequential numbering

### Validation Logic

```
HTTP 200 → Valid, keep citation
HTTP 301/302 → Follow redirect, revalidate
HTTP 403 → Likely paywalled, keep with warning
HTTP 401 → Likely paywalled, keep with warning
HTTP 404 → Invalid, REMOVE citation
HTTP 5xx → Server error, retry once then warn
Timeout → Warn but keep (slow server)
```

## Files to Modify

1. **New Agent**: `src/agents/citation_cleanup.py`
   - Validate URLs via HTTP
   - Remove invalid citations from section files
   - Renumber remaining citations globally
   - Update final draft

2. **Workflow**: `src/workflow.py`
   - Add citation cleanup after citation enrichment
   - Run before TOC generation

3. **Validator Update**: `src/agents/citation_validator.py`
   - Already fixed to parse markdown link format
   - Now correctly categorizes issues by severity

## Metrics to Track

- Total citations before cleanup
- Citations removed (404s)
- Citations kept with warnings (403/401)
- Final valid citation count
- Percentage of claims with valid sources

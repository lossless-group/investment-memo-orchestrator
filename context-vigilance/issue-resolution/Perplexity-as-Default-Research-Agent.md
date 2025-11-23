# Perplexity API Fix - Zero Balance Issue

**Date:** 2025-11-21
**Status:** 🔴 **BLOCKER IDENTIFIED** - Requires action
**Issue:** API key has zero balance and is being blocked by Perplexity

---

## Problem Summary

Perplexity API requests are failing with Cloudflare 401 errors:
```
401 Authorization Required
openresty/1.27.4
```

## Root Cause

According to [Perplexity API documentation](https://docs.perplexity.ai/getting-started/api-groups):

> **"API keys can only be generated when your balance is nonzero."**
>
> **"If you run out of credits, your API keys will be blocked until you add to your credit balance."**

Your API key exists (`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`) but has **zero credits**, so it's being rejected.

---

## How to Fix

### Step 1: Check Current Balance

1. Go to https://www.perplexity.ai/account/api/group
2. Check your current credit balance (likely $0.00)

### Step 2: Add Credits

1. In Settings → API tab, click "**Add credits**"
2. Choose a credit amount to purchase (start with $5-$10)
3. Complete the payment

**Pricing Reference:**
- Sonar Pro: ~$0.50-$1.00 per 1,000 requests (varies by usage)
- For our memo generation: ~10 sections × $0.75 = ~$7.50 per memo

### Step 3: Verify API Key Works

After adding credits, run:
```bash
./test-perplexity-curl.sh
```

Expected output:
```json
{
  "choices": [
    {
      "message": {
        "content": "2 + 2 equals 4."
      }
    }
  ]
}
```

---

## Alternative: Pro Subscription

If you have a **Perplexity Pro subscription** ($20/month):
- You receive **$5 in monthly API credits** on the 1st of each month
- Auto-renews monthly
- **Do NOT manually add credits** if you're a Pro subscriber - wait for the monthly credit
  - Manual add will charge you $5 even though Pro includes it

### To check if you have Pro:
1. Go to https://www.perplexity.ai/account
2. Look for "Pro" badge or subscription status

---

## What Happens After Adding Credits

Once you have a non-zero balance, the following will work:

### 1. Research Agent (Perplexity Provider)
```python
# src/agents/research_enhanced.py:92
model="sonar-pro"  # ✅ Will work
```

### 2. Citation Enrichment Agent
```python
# src/agents/citation_enrichment.py:121
model="sonar-pro"  # ✅ Will work
```

### 3. NEW: Section-Specific Research POC
```bash
python poc-perplexity-section-research.py  # ✅ Will work
```

---

## Testing Checklist

After adding credits:

- [ ] Run `./test-perplexity-curl.sh` → Should return valid JSON response
- [ ] Run `python test_perplexity.py` → Should print "SUCCESS"
- [ ] Run `python poc-perplexity-section-research.py` → Should generate Market Context research
- [ ] Generate a full memo with citations → Should work end-to-end

---

## Cost Estimates

Based on Perplexity Sonar Pro pricing:

| Operation | API Calls | Estimated Cost |
|-----------|-----------|----------------|
| Full memo (current) | ~10 citations | ~$5-7 |
| Full memo (new POC) | ~10 section research | ~$7-10 |
| Section improvement | 1 section | ~$0.75 |
| General research | 4-5 queries | ~$2-3 |

**Recommendation:** Add $25-50 credits for testing and development.

---

## Next Steps

1. **ACTION REQUIRED:** Add credits to Perplexity API account
2. **Verify:** Run test scripts to confirm API access
3. **Resume:** Continue with POC testing (Perplexity research → Claude polish)
4. **Expand:** Roll out to all 10 sections if POC succeeds

---

## Related Files

- `test-perplexity-curl.sh` - Simple curl test
- `test_perplexity.py` - Python API test
- `poc-perplexity-section-research.py` - Full POC implementation
- `context-vigilance/issue-resolution/Getting-Sonar-Pro-to-work-in-first-Research-Agent.md` - Detailed troubleshooting log

---

**TL;DR:** Add credits to your Perplexity API account at https://www.perplexity.ai/account/api/group, then run tests to verify.

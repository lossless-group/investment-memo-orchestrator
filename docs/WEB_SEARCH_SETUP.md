# Web Search Setup Guide

The Research Agent can use web search to gather real company information instead of just acknowledging data gaps.

## Quick Start

**Option 1: Tavily (Recommended - Free tier available)**
1. Sign up at [tavily.com](https://tavily.com)
2. Get your API key from the dashboard
3. Add to `.env`:
   ```
   TAVILY_API_KEY=tvly-xxxxx
   RESEARCH_PROVIDER=tavily
   ```

**Option 2: Perplexity API**
1. Sign up at [perplexity.ai](https://www.perplexity.ai)
2. Get API key from settings
3. Add to `.env`:
   ```
   PERPLEXITY_API_KEY=pplx-xxxxx
   RESEARCH_PROVIDER=perplexity
   ```

**Option 3: No Web Search (POC Mode)**
```
USE_WEB_SEARCH=false
```

## Comparison

### Tavily
- **Best for**: General use, free tier available
- **Pros**: Built for AI agents, includes AI-generated summaries, good citations
- **Cons**: Smaller than Google's index
- **Cost**: Free tier: 1,000 searches/month, Paid: $100/month for 10k searches

### Perplexity
- **Best for**: High-quality research with citations
- **Pros**: Excellent at synthesis, very current, great citations
- **Cons**: More expensive
- **Cost**: $20/month for API access (1000 queries)

### No Web Search (Claude-only)
- **Best for**: Testing workflow without API keys
- **Pros**: No additional costs or API keys needed
- **Cons**: Will generate framework-only memos like the POC demo

## What the Research Agent Searches For

When web search is enabled, the agent runs 4 searches:

1. **Company Overview**: `{company} founders technology product`
2. **Funding**: `{company} funding investors Series A Crunchbase`
3. **Team**: `{company} founders CEO team LinkedIn background`
4. **News**: `{company} news announcement partnership 2024`

Then Claude synthesizes all results into structured JSON.

## Example Output Improvement

**Without Web Search:**
```
Founders: [Data not available]
Funding: [Data not available]
```

**With Web Search (Tavily/Perplexity):**
```
Founders:
- Jane Smith (CEO): Former VP Engineering at SpaceX, MIT PhD
- John Doe (CTO): 10 years at GE Hitachi, nuclear engineering background

Funding:
- Seed: $5M from Breakthrough Energy Ventures (2022)
- Series A: $25M led by Lowercarbon Capital (2024)
Total raised: $30M
```

## Testing

Test with a well-known company to verify it's working:

```bash
python -m src.main "OpenAI"
```

You should see output like:
```
Searching for: OpenAI company overview...
Searching for: OpenAI funding...
Searching for: OpenAI team...
Searching for: OpenAI news...
Synthesizing research with Claude...
```

## Troubleshooting

**"TAVILY_API_KEY not set, falling back to Claude-only research"**
- Add your Tavily API key to `.env`
- Make sure `.env` file exists (not just `.env.example`)

**"tavily-python not installed"**
```bash
uv pip install tavily-python --python /Users/mpstaton/.pyenv/shims/python3.11
```

**Research takes too long**
- Reduce `MAX_SEARCH_RESULTS` from 10 to 5
- Use `RESEARCH_PROVIDER=tavily` (faster than Perplexity)

**Poor quality results**
- Try switching to `RESEARCH_PROVIDER=perplexity` for better synthesis
- Increase `MAX_SEARCH_RESULTS` to 15-20 for more context

"""
Enhanced Research Agent with Web Search capability.

This version actively searches the web for company information instead of
just acknowledging data gaps.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import json
import os
from typing import Dict, Any, List, Optional
import httpx
from bs4 import BeautifulSoup

from ..state import MemoState, ResearchData


class WebSearchProvider:
    """Base class for web search providers."""

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Search the web and return results."""
        raise NotImplementedError


class TavilyProvider(WebSearchProvider):
    """Tavily web search provider (optimized for AI agents)."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        try:
            from tavily import TavilyClient
            self.client = TavilyClient(api_key=api_key)
        except ImportError:
            raise ImportError("tavily-python not installed. Run: pip install tavily-python")

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Search using Tavily API."""
        try:
            response = self.client.search(
                query=query,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False
            )

            results = []
            # Add the AI-generated answer if available
            if response.get('answer'):
                results.append({
                    'title': 'AI Summary',
                    'url': 'tavily://summary',
                    'content': response['answer']
                })

            # Add search results
            for result in response.get('results', []):
                results.append({
                    'title': result.get('title', ''),
                    'url': result.get('url', ''),
                    'content': result.get('content', '')
                })

            return results
        except Exception as e:
            print(f"Tavily search error: {e}")
            return []


class PerplexityProvider(WebSearchProvider):
    """Perplexity API provider (excellent for research)."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.perplexity.ai"
            )
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Search using Perplexity API."""
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-sonar-large-128k-online",
                messages=[
                    {"role": "system", "content": "You are a research assistant providing detailed, cited information for investment analysis."},
                    {"role": "user", "content": query}
                ]
            )

            content = response.choices[0].message.content

            # Perplexity returns a single comprehensive answer with citations
            return [{
                'title': 'Perplexity Research',
                'url': 'perplexity://research',
                'content': content
            }]
        except Exception as e:
            print(f"Perplexity search error: {e}")
            return []


def fetch_website(url: str) -> Optional[str]:
    """Fetch and extract text from a website."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            # Get text
            text = soup.get_text()

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)

            # Limit to first 5000 characters
            return text[:5000]
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def research_agent_enhanced(state: MemoState) -> Dict[str, Any]:
    """
    Enhanced Research Agent with web search capability.

    Actively searches for company information across multiple sources:
    - General web search for company info
    - Company website
    - Funding databases (Crunchbase, PitchBook via search)
    - Team information (LinkedIn via search)
    - News and press releases

    Args:
        state: Current memo state containing company_name

    Returns:
        Updated state with research data populated
    """
    company_name = state["company_name"]

    # Get configuration
    provider_name = os.getenv("RESEARCH_PROVIDER", "tavily").lower()
    max_results = int(os.getenv("MAX_SEARCH_RESULTS", "10"))

    # Initialize search provider
    search_provider = None

    if provider_name == "tavily":
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            search_provider = TavilyProvider(tavily_key)
        else:
            print("Warning: TAVILY_API_KEY not set, falling back to Claude-only research")

    elif provider_name == "perplexity":
        perplexity_key = os.getenv("PERPLEXITY_API_KEY")
        if perplexity_key:
            search_provider = PerplexityProvider(perplexity_key)
        else:
            print("Warning: PERPLEXITY_API_KEY not set, falling back to Claude-only research")

    # Gather research from multiple sources
    research_context = []

    if search_provider:
        # Search 1: Company overview
        print(f"Searching for: {company_name} company overview...")
        results = search_provider.search(
            f"{company_name} company founders technology product",
            max_results=max_results
        )
        for r in results:
            research_context.append(f"Source: {r['title']} ({r['url']})\n{r['content']}\n")

        # Search 2: Funding and investors
        print(f"Searching for: {company_name} funding...")
        results = search_provider.search(
            f"{company_name} funding investors Series A seed Crunchbase",
            max_results=5
        )
        for r in results:
            research_context.append(f"Source: {r['title']} ({r['url']})\n{r['content']}\n")

        # Search 3: Team and founders
        print(f"Searching for: {company_name} team...")
        results = search_provider.search(
            f"{company_name} founders CEO team LinkedIn background",
            max_results=5
        )
        for r in results:
            research_context.append(f"Source: {r['title']} ({r['url']})\n{r['content']}\n")

        # Search 4: Recent news
        print(f"Searching for: {company_name} news...")
        results = search_provider.search(
            f"{company_name} news announcement partnership 2024",
            max_results=5
        )
        for r in results:
            research_context.append(f"Source: {r['title']} ({r['url']})\n{r['content']}\n")

    # Compile research context
    research_text = "\n\n---\n\n".join(research_context) if research_context else "No web search results available."

    # Use Claude to synthesize the research
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0.3,
    )

    system_prompt = """You are an investment research specialist synthesizing web search results into structured company data.

Your task is to extract and organize information from web search results into a structured JSON format for investment analysis.

CRITICAL INSTRUCTIONS:
1. Use ONLY information found in the provided search results
2. Do NOT fabricate or infer information not present in sources
3. For missing data, explicitly mark as "Data not available" or leave as empty array/object
4. Include source citations for all claims
5. Be specific with numbers, dates, and names when available

OUTPUT FORMAT: Return structured JSON matching this schema:
{
  "company": {
    "name": "...",
    "stage": "...",
    "hq_location": "...",
    "website": "...",
    "founded_year": "...",
    "founders": [{"name": "...", "title": "...", "background": "..."}]
  },
  "market": {
    "tam": "...",
    "growth_rate": "...",
    "sources": ["..."],
    "dynamics": ["..."]
  },
  "technology": {
    "description": "...",
    "product_status": "...",
    "roadmap": ["..."]
  },
  "team": {
    "founders": ["..."],
    "key_hires": ["..."],
    "team_size": "...",
    "assessment": "..."
  },
  "traction": {
    "revenue": "...",
    "customers": "...",
    "partnerships": ["..."],
    "milestones": ["..."]
  },
  "funding": {
    "current_round": "...",
    "amount_raising": "...",
    "valuation": "...",
    "total_raised": "...",
    "prior_rounds": ["..."],
    "notable_investors": ["..."]
  },
  "sources": ["..."]
}

Be thorough but honest about data gaps. Quality over completeness."""

    user_prompt = f"""Analyze the following web search results about {company_name} and extract structured company data for investment analysis.

WEB SEARCH RESULTS:
{research_text}

Extract and organize this information into the JSON schema provided in your system prompt. Focus on:
1. Company fundamentals (stage, location, founding team)
2. Technology and product details
3. Market context and opportunity
4. Traction metrics and milestones
5. Funding history and investors
6. Team backgrounds and expertise

Return valid JSON only."""

    print("Synthesizing research with Claude...")
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]

    response = model.invoke(messages)

    # Parse response as JSON
    try:
        research_data = json.loads(response.content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        content = response.content
        if "```json" in content:
            json_start = content.find("```json") + 7
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            research_data = json.loads(json_str)
        elif "```" in content:
            json_start = content.find("```") + 3
            json_end = content.find("```", json_start)
            json_str = content[json_start:json_end].strip()
            research_data = json.loads(json_str)
        else:
            raise ValueError(f"Could not parse research data as JSON: {content[:200]}...")

    # Update state
    return {
        "research": ResearchData(**research_data),
        "messages": [f"Research completed for {company_name} (web search + synthesis)"]
    }

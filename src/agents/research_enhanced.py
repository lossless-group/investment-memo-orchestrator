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
from ..artifacts import create_artifact_directory, save_research_artifacts
from ..versioning import VersionManager
from pathlib import Path


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
                model="sonar-pro",  # Perplexity Sonar Pro for advanced research with citations
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


def generate_queries_from_deck(company_name: str, deck_data: Dict[str, Any]) -> List[str]:
    """
    Generate targeted search queries based on deck gaps.

    Args:
        company_name: Name of the company
        deck_data: Deck analysis data

    Returns:
        List of search queries tailored to fill gaps
    """
    queries = [f"{company_name} company overview"]

    # Add queries for missing information
    if not deck_data.get("team_members") or deck_data.get("team_members") == "Not mentioned":
        queries.append(f"{company_name} founders team background LinkedIn")

    if not deck_data.get("market_size") or deck_data.get("market_size") == "Not mentioned":
        queries.append(f"{company_name} market size TAM SAM industry analysis")

    if not deck_data.get("traction_metrics") or deck_data.get("traction_metrics") == "Not mentioned":
        queries.append(f"{company_name} revenue customers traction metrics")

    # Always verify claimed traction and get recent news
    queries.append(f"{company_name} latest news funding announcements 2024")
    queries.append(f"{company_name} funding investors Crunchbase")

    return queries


def research_agent_enhanced(state: MemoState) -> Dict[str, Any]:
    """
    Enhanced Research Agent with web search capability.

    Actively searches for company information across multiple sources:
    - General web search for company info
    - Company website
    - Funding databases (Crunchbase, PitchBook via search)
    - Team information (LinkedIn via search)
    - News and press releases

    NEW: Deck-aware research - adjusts queries based on deck analysis gaps.

    Args:
        state: Current memo state containing company_name

    Returns:
        Updated state with research data populated
    """
    company_name = state["company_name"]
    deck_analysis = state.get("deck_analysis")

    # NEW: Get company context from state (from JSON input file)
    company_description = state.get("company_description")
    company_url = state.get("company_url")
    company_stage = state.get("company_stage")
    research_notes = state.get("research_notes")

    # Display loaded context
    if company_description:
        print(f"Using company description: {company_description[:80]}...")
    if company_url:
        print(f"Using company URL: {company_url}")
    if research_notes:
        print(f"Research focus: {research_notes[:80]}...")

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

    # NEW: Add company website as first source if URL provided
    if company_url:
        try:
            print(f"Fetching company website: {company_url}")
            website_content = fetch_website(company_url)
            if website_content:
                research_context.append(f"Source: Company Website ({company_url})\n{website_content}\n")
        except Exception as e:
            print(f"Warning: Could not fetch company website: {e}")

    if search_provider:
        # NEW: Generate targeted queries based on deck analysis
        if deck_analysis:
            print(f"Deck analysis available - generating targeted queries to fill gaps...")
            search_queries = generate_queries_from_deck(company_name, deck_analysis)
        else:
            # Enhanced queries using company description and research notes
            search_queries = [
                f"{company_name} company founders technology product"
            ]

            # Add description-based query if available
            if company_description:
                # Extract key terms from description for better search
                search_queries.append(f"{company_name} {company_description[:50]}")

            # Standard queries
            search_queries.extend([
                f"{company_name} funding investors {company_stage or 'Series A seed'} Crunchbase",
                f"{company_name} founders CEO team LinkedIn background",
                f"{company_name} news announcement partnership 2024"
            ])

            # Add research notes focus if provided
            if research_notes:
                search_queries.append(f"{company_name} {research_notes[:80]}")

        # Execute searches
        for idx, query in enumerate(search_queries, 1):
            print(f"Search {idx}/{len(search_queries)}: {query}...")
            results = search_provider.search(query, max_results=5 if idx > 1 else max_results)
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

    # NEW: Include deck analysis context if available
    deck_context = ""
    if deck_analysis:
        deck_context = f"""
PITCH DECK ANALYSIS:
The following information was extracted from the company's pitch deck:
{json.dumps(deck_analysis, indent=2)}

Use this as a baseline, but prioritize web search results for verification and additional details.
Note any discrepancies between deck claims and external sources.
"""

    # NEW: Include company context from input JSON
    company_context = ""
    if company_description or research_notes:
        company_context = "\nCOMPANY CONTEXT:\n"
        if company_description:
            company_context += f"Description: {company_description}\n"
        if company_stage:
            company_context += f"Stage: {company_stage}\n"
        if research_notes:
            company_context += f"Research Focus: {research_notes}\n"
        company_context += "\nUse this context to guide your research synthesis, but verify all claims with search results.\n"

    user_prompt = f"""Analyze the following web search results about {company_name} and extract structured company data for investment analysis.

{company_context}
{deck_context}

WEB SEARCH RESULTS:
{research_text}

Extract and organize this information into the JSON schema provided in your system prompt. Focus on:
1. Company fundamentals (stage, location, founding team)
2. Technology and product details
3. Market context and opportunity
4. Traction metrics and milestones
5. Funding history and investors
6. Team backgrounds and expertise
{f"7. PRIORITY: {research_notes}" if research_notes else ""}

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

    # Add web search metadata to research data
    if search_provider:
        research_data["web_search_metadata"] = {
            "provider": provider_name,
            "queries_count": 4,  # We ran 4 searches
            "total_results": len(research_context)
        }

    # Save research artifacts
    try:
        # Get version manager
        version_mgr = VersionManager(Path("output"))
        from ..artifacts import sanitize_filename
        safe_name = sanitize_filename(company_name)
        version = version_mgr.get_next_version(safe_name)

        # Create artifact directory
        output_dir = create_artifact_directory(company_name, str(version))

        # Save research artifacts
        save_research_artifacts(output_dir, research_data)

        print(f"Research artifacts saved to: {output_dir}")
    except Exception as e:
        print(f"Warning: Could not save research artifacts: {e}")

    # Update state
    return {
        "research": ResearchData(**research_data),
        "messages": [f"Research completed for {company_name} (web search + synthesis)"]
    }

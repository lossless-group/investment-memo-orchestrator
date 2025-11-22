#!/usr/bin/env python3
"""
Test which premium sources work with @ syntax in Perplexity API.

Tests various premium and authoritative sources mentioned in:
- Perplexity help center
- Investment research contexts
"""

import os
from openai import OpenAI

# Load API key
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
if not PERPLEXITY_API_KEY:
    raise ValueError("PERPLEXITY_API_KEY not found in environment")

# Initialize client
client = OpenAI(
    api_key=PERPLEXITY_API_KEY,
    base_url="https://api.perplexity.ai"
)

# Premium sources to test
SOURCES_TO_TEST = {
    # Known premium partners
    "Premium Partners": ["@statista", "@pitchbook", "@wiley"],

    # Financial data sources
    "Financial Data": ["@crunchbase", "@bloomberg", "@reuters", "@wsj", "@forbes"],

    # Tech/startup news
    "Tech News": ["@techcrunch", "@venturebeat", "@theinformation"],

    # Business publications
    "Business": ["@businessinsider", "@fastcompany", "@inc"],

    # Academic/research
    "Academic": ["@arxiv", "@scholar", "@pubmed"],

    # Government/regulatory
    "Government": ["@sec", "@sec.gov"],

    # Other data sources
    "Data Providers": ["@factset", "@cbinsights"],
}

# Test query
QUERY = "What is Stripe's latest funding round?"


def test_source_group(group_name, sources):
    """Test a group of sources to see if @ syntax works."""
    print("\n" + "="*80)
    print(f"Testing: {group_name}")
    print("="*80)

    # Test all sources in one query
    sources_str = " ".join(sources)
    query = f"{QUERY} {sources_str}"

    print(f"\nQuery: {query}")
    print(f"Sources: {sources_str}")
    print("\nCalling Perplexity API...")

    try:
        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {
                    "role": "user",
                    "content": query
                }
            ]
        )

        content = response.choices[0].message.content

        # Check which sources were mentioned
        mentioned = []
        not_mentioned = []

        for source in sources:
            source_name = source.replace("@", "")
            # Check for exact name or domain
            if (source_name.lower() in content.lower() or
                f"{source_name}.com" in content.lower()):
                mentioned.append(source)
            else:
                not_mentioned.append(source)

        # Print results
        print(f"\n{'Status':<12} {'Source':<20} {'Found in Response'}")
        print("-" * 60)

        for source in mentioned:
            print(f"{'✓ WORKS':<12} {source:<20} Yes")

        for source in not_mentioned:
            print(f"{'✗ NO':<12} {source:<20} No")

        # Print excerpt showing source mentions
        if mentioned:
            print(f"\nResponse excerpt (first 500 chars):")
            print("-" * 60)
            print(content[:500] + "..." if len(content) > 500 else content)

        return {
            "mentioned": mentioned,
            "not_mentioned": not_mentioned,
            "content": content
        }

    except Exception as e:
        print(f"\n✗ Error: {e}")
        return None


def test_individual_sources(sources):
    """Test sources individually to isolate which ones work."""
    print("\n" + "="*80)
    print("Individual Source Testing (High Confidence)")
    print("="*80)
    print("\nTesting each source individually to confirm which actually work...")

    results = {}

    for source in sources:
        query = f"{QUERY} {source}"
        source_name = source.replace("@", "")

        try:
            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[{"role": "user", "content": query}]
            )

            content = response.choices[0].message.content

            # Check if source is explicitly mentioned or cited
            if (source_name.lower() in content.lower() or
                f"{source_name}.com" in content.lower()):
                results[source] = "✓ CONFIRMED"
                print(f"{source:<25} ✓ CONFIRMED (mentioned in response)")
            else:
                results[source] = "✗ Not mentioned"
                print(f"{source:<25} ✗ Not mentioned")

        except Exception as e:
            results[source] = f"✗ Error: {str(e)[:50]}"
            print(f"{source:<25} ✗ Error")

    return results


def main():
    print("Testing Premium Sources with @ Syntax")
    print("Query:", QUERY)

    all_mentioned = []
    all_not_mentioned = []

    # Test each group
    for group_name, sources in SOURCES_TO_TEST.items():
        result = test_source_group(group_name, sources)
        if result:
            all_mentioned.extend(result["mentioned"])
            all_not_mentioned.extend(result["not_mentioned"])

    # Summary
    print("\n" + "="*80)
    print("SUMMARY: Working Premium Sources")
    print("="*80)

    if all_mentioned:
        print("\n✓ Sources that appear to work:")
        for source in sorted(set(all_mentioned)):
            print(f"  - {source}")

    if all_not_mentioned:
        print("\n✗ Sources that may not work (or weren't mentioned):")
        for source in sorted(set(all_not_mentioned)):
            print(f"  - {source}")

    # High-confidence test on promising sources
    if all_mentioned:
        print("\n" + "="*80)
        print("Running individual tests on promising sources for confirmation...")
        print("="*80)
        individual_results = test_individual_sources(list(set(all_mentioned)))

    # Final recommendations
    print("\n" + "="*80)
    print("RECOMMENDATIONS FOR INVESTMENT MEMO SYSTEM")
    print("="*80)

    confirmed = [s for s in all_mentioned if s in [
        "@statista", "@pitchbook", "@crunchbase", "@bloomberg",
        "@techcrunch", "@wsj", "@reuters", "@forbes"
    ]]

    if confirmed:
        print("\nConfirmed sources for investment research:")
        print("\nAdd to queries like this:")
        print("```python")
        print('query = f"What is {company}\'s revenue? ' + ' '.join(confirmed[:5]) + '"')
        print("```")

    print("\nNote: Source mentioned ≠ source actually used for retrieval")
    print("Perplexity may mention sources in text even if not prioritized in search.")
    print("True test: Check if adding @ syntax changes the quality/content of responses.")


if __name__ == "__main__":
    main()

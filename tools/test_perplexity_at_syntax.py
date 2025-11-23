#!/usr/bin/env python3
"""
Test if @ syntax works with Perplexity API for targeting premium sources.

Tests three approaches:
1. Basic query (no source targeting)
2. @ syntax in query text (e.g., "@crunchbase @statista")
3. search_domain_filter parameter via extra_body
"""

import os
import json
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

# Test query - using a well-known company
COMPANY = "Stripe"
BASE_QUERY = f"What is {COMPANY}'s latest revenue and valuation?"


def test_basic_query():
    """Test 1: Basic query without any source targeting."""
    print("\n" + "="*80)
    print("TEST 1: Basic Query (No Source Targeting)")
    print("="*80)

    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {
                "role": "user",
                "content": BASE_QUERY
            }
        ]
    )

    content = response.choices[0].message.content
    print(f"\nQuery: {BASE_QUERY}")
    print(f"\nResponse:\n{content}")

    # Try to extract citations
    if hasattr(response, 'citations'):
        print(f"\nCitations: {response.citations}")

    return content


def test_at_syntax():
    """Test 2: Query with @ syntax to target premium sources."""
    print("\n" + "="*80)
    print("TEST 2: @ Syntax (Premium Source Targeting)")
    print("="*80)

    # Try multiple @ syntax variations
    queries_to_test = [
        f"{BASE_QUERY} @crunchbase @pitchbook @statista",
        f"@crunchbase @pitchbook {BASE_QUERY}",
        f"{BASE_QUERY} Use @crunchbase and @pitchbook sources."
    ]

    for i, query in enumerate(queries_to_test, 1):
        print(f"\n--- Variation {i} ---")
        print(f"Query: {query}")

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
        print(f"\nResponse:\n{content}")

        # Check for mentions of premium sources
        mentions = []
        for source in ["crunchbase", "pitchbook", "statista"]:
            if source.lower() in content.lower():
                mentions.append(source)

        if mentions:
            print(f"\n✓ Premium sources mentioned: {', '.join(mentions)}")
        else:
            print("\n✗ No premium sources mentioned")

        if i < len(queries_to_test):
            print("\n" + "-"*40)


def test_domain_filter():
    """Test 3: Using search_domain_filter parameter via extra_body."""
    print("\n" + "="*80)
    print("TEST 3: search_domain_filter Parameter (via extra_body)")
    print("="*80)

    try:
        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {
                    "role": "user",
                    "content": BASE_QUERY
                }
            ],
            extra_body={
                "search_domain_filter": [
                    "crunchbase.com",
                    "pitchbook.com",
                    "techcrunch.com"
                ],
                "search_recency_filter": "year"
            }
        )

        content = response.choices[0].message.content
        print(f"\nQuery: {BASE_QUERY}")
        print(f"Domain filter: crunchbase.com, pitchbook.com, techcrunch.com")
        print(f"\nResponse:\n{content}")

        # Check for mentions of filtered domains
        mentions = []
        for domain in ["crunchbase", "pitchbook", "techcrunch"]:
            if domain.lower() in content.lower():
                mentions.append(domain)

        if mentions:
            print(f"\n✓ Filtered domains mentioned: {', '.join(mentions)}")
        else:
            print("\n✗ No filtered domains mentioned")

        return content

    except Exception as e:
        print(f"\n✗ Error with domain filter: {e}")
        print("\nThis might indicate:")
        print("  - Tier 3 (Enterprise) subscription required")
        print("  - Invalid parameter syntax")
        print("  - API doesn't support this parameter")
        return None


def compare_sources(basic_content, at_content, filter_content):
    """Compare which sources were used in each approach."""
    print("\n" + "="*80)
    print("COMPARISON: Source Detection")
    print("="*80)

    common_sources = [
        "crunchbase", "pitchbook", "statista", "techcrunch",
        "bloomberg", "forbes", "reuters", "wsj"
    ]

    print("\nSource mentions across tests:")
    print(f"{'Source':<15} {'Basic':<10} {'@Syntax':<10} {'Filter':<10}")
    print("-" * 45)

    for source in common_sources:
        basic_has = "✓" if basic_content and source.lower() in basic_content.lower() else "✗"
        at_has = "✓" if at_content and source.lower() in at_content.lower() else "✗"
        filter_has = "✓" if filter_content and source.lower() in filter_content.lower() else "✗"

        print(f"{source:<15} {basic_has:<10} {at_has:<10} {filter_has:<10}")


def main():
    print("Testing Perplexity API Source Targeting Methods")
    print("Company:", COMPANY)

    # Run tests
    basic_content = test_basic_query()

    # For @ syntax test, we'll use the first variation's result
    test_at_syntax()  # This prints all variations

    # Now run just the first variation again to capture content for comparison
    print("\n" + "="*80)
    print("Capturing @ Syntax Result for Comparison")
    print("="*80)
    at_query = f"{BASE_QUERY} @crunchbase @pitchbook @statista"
    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": at_query}]
    )
    at_content = response.choices[0].message.content

    filter_content = test_domain_filter()

    # Compare results
    compare_sources(basic_content, at_content, filter_content)

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("\nBased on the tests above:")
    print("1. If @ syntax shows different sources than basic → @ syntax WORKS via API")
    print("2. If @ syntax shows same sources as basic → @ syntax is UI-only feature")
    print("3. If domain_filter works → Need Tier 3 (Enterprise) subscription")
    print("4. If domain_filter fails → Current tier doesn't support it")
    print("\nCheck the source mentions table above to determine which approach works!")


if __name__ == "__main__":
    main()

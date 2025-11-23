#!/usr/bin/env python3
"""
Focused test on premium partner sources that should work according to Perplexity docs:
- @statista
- @pitchbook
- @wiley

Tests different query types to see if @ syntax is query-dependent.
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

# Different query types
QUERIES = {
    "Revenue query": "What is Stripe's latest revenue?",
    "Valuation query": "What is Stripe's current valuation?",
    "Market data query": "What is the average SaaS company growth rate in 2025?",
    "Academic query": "What are the latest research findings on AI applications in fintech?",
}


def test_source_with_query(source, query_name, query):
    """Test a specific source with a specific query type."""
    query_with_source = f"{query} {source}"

    try:
        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[{"role": "user", "content": query_with_source}]
        )

        content = response.choices[0].message.content
        source_name = source.replace("@", "")

        # Check if source is mentioned
        mentioned = (source_name.lower() in content.lower() or
                    f"{source_name}.com" in content.lower())

        return {
            "mentioned": mentioned,
            "content": content[:300]  # First 300 chars
        }

    except Exception as e:
        return {
            "mentioned": False,
            "error": str(e)
        }


def main():
    print("Testing Premium Partner Sources: @statista @pitchbook @wiley")
    print("="*80)

    sources = ["@statista", "@pitchbook", "@wiley"]

    # Test each source with each query type
    results = {}

    for source in sources:
        print(f"\n{'='*80}")
        print(f"Testing: {source}")
        print(f"{'='*80}")

        results[source] = {}

        for query_name, query in QUERIES.items():
            print(f"\n{query_name}: {query}")
            result = test_source_with_query(source, query_name, query)

            if "error" in result:
                print(f"  ✗ Error: {result['error']}")
                results[source][query_name] = "Error"
            elif result["mentioned"]:
                print(f"  ✓ MENTIONED in response")
                print(f"  Excerpt: {result['content']}...")
                results[source][query_name] = "✓"
            else:
                print(f"  ✗ NOT mentioned")
                results[source][query_name] = "✗"

    # Summary table
    print("\n" + "="*80)
    print("SUMMARY TABLE")
    print("="*80)

    print(f"\n{'Source':<15} ", end="")
    for query_name in QUERIES.keys():
        print(f"{query_name:<20} ", end="")
    print()
    print("-" * 90)

    for source in sources:
        print(f"{source:<15} ", end="")
        for query_name in QUERIES.keys():
            status = results[source].get(query_name, "?")
            print(f"{status:<20} ", end="")
        print()

    # Conclusion
    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)

    working_sources = []
    for source in sources:
        mentions = sum(1 for v in results[source].values() if v == "✓")
        total = len(QUERIES)
        if mentions > 0:
            working_sources.append(source)
            print(f"{source}: Works in {mentions}/{total} queries")
        else:
            print(f"{source}: Does NOT work (0/{total} queries)")

    if working_sources:
        print(f"\n✓ These sources appear to work with @ syntax:")
        for source in working_sources:
            print(f"  - {source}")
    else:
        print(f"\n✗ NONE of the premium partner sources appear to work consistently")
        print(f"\nPossible reasons:")
        print(f"  1. @ syntax may be UI-only feature (not available via API)")
        print(f"  2. Requires specific subscription tier (Pro/Enterprise)")
        print(f"  3. Only works in web interface, not API")
        print(f"  4. Documentation may be referring to web UI, not API")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Test Perplexity API connection with Cloudflare bypass headers."""

import os
from openai import OpenAI

# Load API key
api_key = os.getenv("PERPLEXITY_API_KEY")
if not api_key:
    print("ERROR: PERPLEXITY_API_KEY not set in environment")
    exit(1)

print(f"Testing Perplexity API with key: {api_key[:10]}...")

# Test with default headers (Cloudflare bypass)
try:
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    print("Calling Perplexity Sonar Pro...")
    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {"role": "user", "content": "What is 2+2? Answer in one sentence."}
        ],
        max_tokens=50
    )

    print("\n✅ SUCCESS!")
    print(f"Response: {response.choices[0].message.content}")
    print("\nCloudflare bypass working! Citations should now work in memo generation.")

except Exception as e:
    print(f"\n❌ FAILED: {e}")
    print("\nIf you see HTML with '401 Authorization Required', Cloudflare is still blocking.")
    print("If you see a different error, it may be an API key or model access issue.")

#!/usr/bin/env python3
"""Test Perplexity API connection and quota."""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("PERPLEXITY_API_KEY")

if not api_key:
    print("ERROR: No PERPLEXITY_API_KEY found in .env")
    exit(1)

print(f"API Key found: {api_key[:8]}...{api_key[-4:]}")
print("\nTesting Perplexity API...")

try:
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai"
    )

    # Simple test query
    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2+2? Reply with just the number."}
        ],
        max_tokens=10
    )

    print("✓ API call successful!")
    print(f"Response: {response.choices[0].message.content}")
    print(f"\nUsage:")
    print(f"  Prompt tokens: {response.usage.prompt_tokens}")
    print(f"  Completion tokens: {response.usage.completion_tokens}")
    print(f"  Total tokens: {response.usage.total_tokens}")

    # Check headers for rate limit info
    print("\n✓ Perplexity API is working - no quota issues detected")

except Exception as e:
    print(f"✗ API call failed!")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")

    if "rate_limit" in str(e).lower():
        print("\n⚠️  RATE LIMIT HIT - Your account may be maxed out")
    elif "quota" in str(e).lower():
        print("\n⚠️  QUOTA EXCEEDED - Your account limit reached")
    elif "auth" in str(e).lower():
        print("\n⚠️  AUTHENTICATION FAILED - Check your API key")
    elif "insufficient_quota" in str(e).lower():
        print("\n⚠️  INSUFFICIENT QUOTA - Your Perplexity credits are depleted")

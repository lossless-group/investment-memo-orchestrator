#!/usr/bin/env python3
"""Test Anthropic (Claude) API connection and quota."""

import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    print("ERROR: No ANTHROPIC_API_KEY found in .env")
    exit(1)

print(f"API Key found: {api_key[:8]}...{api_key[-4:]}")
print("\nTesting Anthropic API...")

try:
    client = Anthropic(api_key=api_key)

    # Simple test query
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=10,
        messages=[
            {"role": "user", "content": "What is 2+2? Reply with just the number."}
        ]
    )

    print("✓ API call successful!")
    print(f"Response: {message.content[0].text}")
    print(f"\nUsage:")
    print(f"  Input tokens: {message.usage.input_tokens}")
    print(f"  Output tokens: {message.usage.output_tokens}")
    print(f"\n✓ Anthropic API is working - no quota issues detected")

except Exception as e:
    print(f"✗ API call failed!")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")

    error_str = str(e).lower()
    if "rate_limit" in error_str or "429" in error_str:
        print("\n⚠️  RATE LIMIT HIT - Too many requests, wait a bit")
    elif "quota" in error_str or "insufficient_quota" in error_str:
        print("\n⚠️  QUOTA EXCEEDED - Your Anthropic credits are depleted")
    elif "auth" in error_str or "401" in error_str:
        print("\n⚠️  AUTHENTICATION FAILED - Check your API key")
    elif "overloaded" in error_str or "529" in error_str:
        print("\n⚠️  ANTHROPIC OVERLOADED - Their servers are busy, retry later")
    elif "connection" in error_str or "timeout" in error_str:
        print("\n⚠️  CONNECTION ERROR - Network or API server issue, retry")

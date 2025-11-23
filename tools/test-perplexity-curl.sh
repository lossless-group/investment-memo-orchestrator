#!/bin/bash
# Test Perplexity API with curl

# Load API key from .env
source .env

echo "Testing Perplexity API..."
echo "API Key (first 10 chars): ${PERPLEXITY_API_KEY:0:10}..."

curl --request POST \
  --url https://api.perplexity.ai/chat/completions \
  --header "Authorization: Bearer $PERPLEXITY_API_KEY" \
  --header "Content-Type: application/json" \
  --data '{
    "model": "sonar-pro",
    "messages": [
      {
        "role": "user",
        "content": "What is 2+2? Answer in one sentence."
      }
    ],
    "max_tokens": 50
  }'

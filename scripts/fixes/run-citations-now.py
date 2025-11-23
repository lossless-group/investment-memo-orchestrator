#!/usr/bin/env python3
"""Emergency citation enrichment for Powerline."""
import os
import re
from pathlib import Path
from openai import OpenAI

perplexity_key = os.getenv("PERPLEXITY_API_KEY", "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")
client = OpenAI(api_key=perplexity_key, base_url="https://api.perplexity.ai")

sections_dir = Path("output/Powerline-v0.0.1/2-sections")
section_files = sorted(sections_dir.glob("*.md"))

print(f"📚 Enriching {len(section_files)} sections with Perplexity Sonar Pro...\n")

enriched_content = "# Investment Memo: Powerline\n\n**Date**: November 2025\n\n"
total_citations = 0

for section_file in section_files:
    section_name = section_file.stem.split("-", 1)[1].replace("--", " & ").replace("-", " ").title()
    print(f"  Enriching: {section_name}...")

    with open(section_file) as f:
        section_content = f.read()

    prompt = f"""Add inline citations to this {section_name} section for Powerline (battery optimization AI).

CRITICAL:
1. Do NOT rewrite - ONLY add [^1], [^2] citations
2. Place citations AFTER punctuation: "text. [^1]"
3. Format: [^1]: YYYY, MMM DD. Title. Published: YYYY-MM-DD | Updated: N/A | URL: https://...

SECTION:
{section_content}

Return same content with citations, plus citation list."""

    try:
        response = client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {"role": "system", "content": "Add citations WITHOUT rewriting."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=6000,
            temperature=0.3
        )

        enriched_section = response.choices[0].message.content

        with open(section_file, "w") as f:
            f.write(enriched_section)

        section_num = section_file.stem.split("-")[0]
        enriched_content += f"## {section_num}. {section_name}\n\n{enriched_section}\n\n"

        cites = len(re.findall(r'\[\^[0-9]+\]', enriched_section))
        total_citations += cites
        print(f"  ✓ {section_name}: {cites} citations")

    except Exception as e:
        print(f"  ✗ {section_name}: {e}")
        section_num = section_file.stem.split("-")[0]
        enriched_content += f"## {section_num}. {section_name}\n\n{section_content}\n\n"

with open("output/Powerline-v0.0.1/4-final-draft.md", "w") as f:
    f.write(enriched_content)

print(f"\n✓ DONE: {total_citations} total citations")
print(f"✓ Saved: output/Powerline-v0.0.1/4-final-draft.md")

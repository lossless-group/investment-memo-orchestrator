#!/usr/bin/env python3
"""Manually run citation enrichment on a completed memo."""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.citation_enrichment import citation_enrichment_agent
from src.state import MemoState

load_dotenv()

# Load the existing memo and state
output_dir = Path("output/Powerline-v0.0.1")

with open(output_dir / "state.json") as f:
    state_data = json.load(f)

with open(output_dir / "1-research.json") as f:
    research_data = json.load(f)

with open(output_dir / "4-final-draft.md") as f:
    memo_content = f.read()

# Build full state
state = MemoState(
    company_name=state_data["company_name"],
    investment_type=state_data["investment_type"],
    memo_mode=state_data["memo_mode"],
    company_description=state_data.get("company_description"),
    company_url=state_data.get("company_url"),
    company_stage=state_data.get("company_stage"),
    research_notes=state_data.get("research_notes"),
    deck_path=None,
    deck_analysis=None,
    research=research_data,
    draft_sections={"full_memo": {"content": memo_content}},
    validation_results={},
    citation_validation=None,
    overall_score=0.0,
    revision_count=0,
    final_memo=None,
    messages=[]
)

print("Running citation enrichment agent...")
print(f"Company: {state['company_name']}")
print(f"Memo length: {len(memo_content)} characters\n")

# Run citation enrichment
result = citation_enrichment_agent(state)

# Save the enriched memo
enriched_content = result["draft_sections"]["full_memo"]["content"]

with open(output_dir / "4-final-draft-cited.md", "w") as f:
    f.write(enriched_content)

print(f"\n✓ Citation enrichment complete!")
print(f"✓ Saved to: {output_dir}/4-final-draft-cited.md")
print(f"✓ New length: {len(enriched_content)} characters")

# Count citations
import re
inline_cites = len(re.findall(r'\[\^[0-9]+\]', enriched_content))
print(f"✓ Inline citations: {inline_cites}")

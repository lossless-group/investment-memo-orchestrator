#!/usr/bin/env python3
"""
Test script to verify outline source loading works correctly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agents.research_enhanced import load_outline_sources

def test_outline_sources():
    """Test loading preferred sources from both outline types."""

    print("=" * 60)
    print("Testing Outline Source Loading")
    print("=" * 60)

    # Test direct investment outline
    print("\n1. Testing direct investment outline...")
    direct_sources = load_outline_sources("direct")

    if direct_sources:
        print(f"   ✓ Loaded {len(direct_sources)} sections")

        # Show a sample
        sample_sections = ["Executive Summary", "Market Context", "Funding & Terms"]
        for section in sample_sections:
            if section in direct_sources:
                sources_str = " ".join(direct_sources[section])
                print(f"   - {section}: {sources_str}")
    else:
        print("   ✗ Failed to load sources")
        return False

    # Test fund commitment outline
    print("\n2. Testing fund commitment outline...")
    fund_sources = load_outline_sources("fund")

    if fund_sources:
        print(f"   ✓ Loaded {len(fund_sources)} sections")

        # Show a sample
        sample_sections = ["Executive Summary", "Fund Strategy & Thesis", "Track Record Analysis"]
        for section in sample_sections:
            if section in fund_sources:
                sources_str = " ".join(fund_sources[section])
                print(f"   - {section}: {sources_str}")
    else:
        print("   ✗ Failed to load sources")
        return False

    # Test aggregation (simulating research agent behavior)
    print("\n3. Testing source aggregation (research phase)...")
    key_sections = ["Executive Summary", "Business Overview", "Market Context", "Team", "Traction & Milestones"]

    aggregated = set()
    for section in key_sections:
        if section in direct_sources:
            aggregated.update(direct_sources[section])

    if aggregated:
        print(f"   ✓ Aggregated {len(aggregated)} unique sources from {len(key_sections)} sections")
        print(f"   Sources: {' '.join(sorted(aggregated))}")
    else:
        print("   ✗ No sources aggregated")
        return False

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_outline_sources()
    sys.exit(0 if success else 1)

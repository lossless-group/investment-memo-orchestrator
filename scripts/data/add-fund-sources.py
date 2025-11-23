#!/usr/bin/env python3
"""
Script to add preferred_sources to fund-commitment.yaml sections 3-10.
Run after sections 1-2 have been manually updated.
"""

# Define preferred sources for each fund section
FUND_SOURCES = {
    3: {  # Fund Strategy & Thesis
        "at_syntax": ["@pitchbook", "@cbinsights", "@statista"],
        "include": ["pitchbook.com", "cbinsights.com", "statista.com", "[fund-domain]"],
        "exclude": ["*.vc-strategy.com"]
    },
    4: {  # Portfolio Construction
        "at_syntax": ["@pitchbook", "@crunchbase"],
        "include": ["pitchbook.com", "crunchbase.com", "[fund-domain]"],
        "exclude": ["*.portfolio-guide.com"]
    },
    5: {  # Value Add & Differentiation
        "at_syntax": ["@pitchbook", "@cbinsights"],
        "include": ["pitchbook.com", "cbinsights.com", "[fund-domain]"],
        "exclude": ["*.vc-tips.com"]
    },
    6: {  # Track Record Analysis
        "at_syntax": ["@pitchbook", "@crunchbase"],
        "include": ["pitchbook.com", "crunchbase.com", "sec.gov", "[fund-domain]"],
        "exclude": ["*.performance-calc.com"]
    },
    7: {  # Fee Structure & Economics
        "at_syntax": ["@pitchbook", "@sec"],
        "include": ["pitchbook.com", "sec.gov", "[fund-domain]"],
        "exclude": ["*.fee-calculator.com"]
    },
    8: {  # LP Base & References
        "at_syntax": ["@pitchbook", "@linkedin"],
        "include": ["pitchbook.com", "linkedin.com", "[fund-domain]"],
        "exclude": ["*.lp-directory.com"]
    },
    9: {  # Risks & Mitigations
        "at_syntax": ["@sec", "@bloomberg", "@reuters"],
        "include": ["sec.gov", "bloomberg.com", "reuters.com", "wsj.com"],
        "exclude": ["*.risk-guide.com"]
    },
    10: {  # Recommendation
        "at_syntax": ["@pitchbook"],
        "include": ["pitchbook.com", "[fund-domain]"],
        "exclude": []
    }
}

def generate_preferred_sources_yaml(section_num):
    """Generate YAML for preferred_sources field."""
    sources = FUND_SOURCES[section_num]

    yaml = "\n    preferred_sources:\n"
    yaml += "      perplexity_at_syntax:\n"
    for source in sources["at_syntax"]:
        comment = {
            "@pitchbook": "# Fund data, performance",
            "@cbinsights": "# Market intelligence, trends",
            "@statista": "# Market statistics, forecasts",
            "@crunchbase": "# Portfolio companies",
            "@sec": "# Regulatory filings",
            "@bloomberg": "# Financial news, market data",
            "@reuters": "# Breaking news",
            "@linkedin": "# Professional backgrounds"
        }.get(source, "")
        yaml += f"        - \"{source}\"{' ':<15}{comment}\n"

    yaml += "      domains:\n"
    yaml += "        include:\n"
    for domain in sources["include"]:
        yaml += f"          - \"{domain}\"\n"

    if sources["exclude"]:
        yaml += "        exclude:\n"
        for domain in sources["exclude"]:
            yaml += f"          - \"{domain}\"\n"

    return yaml

# Print instructions
print("To add sources to fund-commitment.yaml sections 3-10:")
print("1. Read the file to find the end of each section's guiding_questions")
print("2. Insert the preferred_sources YAML before section_vocabulary")
print("\nGenerated YAML for each section:\n")

for section_num in range(3, 11):
    print(f"=== Section {section_num} ===")
    print(generate_preferred_sources_yaml(section_num))

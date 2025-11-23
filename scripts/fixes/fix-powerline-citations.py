#!/usr/bin/env python3
"""Fix Powerline memo citations by renumbering globally."""
import re
from pathlib import Path


def renumber_citations_globally(sections_data: list) -> str:
    """
    Renumber citations globally across all sections.

    Each section comes with its own [^1], [^2], etc. This function
    renumbers them sequentially across the entire memo so each unique
    source gets a globally unique citation number.

    Args:
        sections_data: List of tuples (section_num, section_name, section_content)

    Returns:
        Combined content with globally renumbered citations
    """
    combined_content = ""
    citation_counter = 1
    citation_map = {}  # Maps (section_idx, old_num) -> new_num

    # First pass: Renumber inline citations and build mapping
    for idx, (section_num, section_name, section_content) in enumerate(sections_data):
        # Split content from citations
        parts = section_content.split("### Citations")
        main_content = parts[0] if parts else section_content
        citations_section = parts[1] if len(parts) > 1 else ""

        # Find all citation numbers in this section
        old_citations = set(re.findall(r'\[\^(\d+)\]', section_content))

        # Create mapping for this section
        section_map = {}
        for old_num in sorted(old_citations, key=int):
            section_map[old_num] = citation_counter
            citation_map[(idx, old_num)] = citation_counter
            citation_counter += 1

        # Renumber inline citations in main content
        for old_num, new_num in section_map.items():
            # Replace inline citations [^X] with [^NEW]
            main_content = re.sub(
                rf'\[\^{old_num}\]',
                f'[^{new_num}]',
                main_content
            )

        # Renumber citations in the reference list
        if citations_section:
            for old_num, new_num in section_map.items():
                # Replace citation definitions [^X]: with [^NEW]:
                citations_section = re.sub(
                    rf'\[\^{old_num}\]:',
                    f'[^{new_num}]:',
                    citations_section
                )

        # Reconstruct section with renumbered citations
        if citations_section:
            section_content = main_content + "### Citations" + citations_section
        else:
            section_content = main_content

        # Add to combined content
        combined_content += f"## {section_num}. {section_name}\n\n{section_content}\n\n"

    return combined_content


def main():
    sections_dir = Path("output/Powerline-v0.0.1/2-sections")

    if not sections_dir.exists():
        print(f"❌ Sections directory not found: {sections_dir}")
        return

    print(f"🔧 Fixing Powerline citations...\n")

    # Load all section files
    section_files = sorted(sections_dir.glob("*.md"))
    sections_data = []

    for section_file in section_files:
        section_name = section_file.stem.split("-", 1)[1].replace("--", " & ").replace("-", " ").title()

        with open(section_file) as f:
            section_content = f.read()

        section_num = section_file.stem.split("-")[0]
        sections_data.append((section_num, section_name, section_content))

        # Count citations in this section
        section_cites = len(re.findall(r'\[\^[0-9]+\]', section_content))
        print(f"  Section {section_num} ({section_name}): {section_cites} citation markers")

    # Renumber citations globally
    print(f"\n🔢 Renumbering citations globally across all sections...")
    enriched_content = "# Investment Memo: Powerline\n\n"
    enriched_content += renumber_citations_globally(sections_data)

    # Save corrected final draft
    output_file = Path("output/Powerline-v0.0.1/4-final-draft.md")
    with open(output_file, "w") as f:
        f.write(enriched_content)

    # Count unique citations
    total_unique = len(set(re.findall(r'\[\^(\d+)\]', enriched_content)))
    print(f"✓ Citation renumbering complete: {total_unique} unique citations")
    print(f"✓ Saved: {output_file}")


if __name__ == "__main__":
    main()

"""
Citation-Enrichment Agent - Adds additional inline citations to research files.

IMPORTANT: This agent operates on 1-research/ files (NOT 2-sections/) so that any
new citations become part of the source material that flows through the writer.

This agent PRESERVES all existing content and citations. It only ADDS new citations
to uncited factual claims - it never removes or overwrites existing content.

The workflow is:
1. Extract existing citations from research file
2. Find the highest citation number
3. Ask Perplexity to add NEW citations starting from N+1
4. Merge Perplexity's additions with existing content
5. Save enriched research back to file
"""

from langchain_core.messages import HumanMessage, SystemMessage
import os
from typing import Dict, Any, Tuple, Set
import re

from ..state import MemoState


def extract_existing_citations(content: str) -> Tuple[Set[str], int, str, str]:
    """
    Extract existing citations from content.

    Args:
        content: Markdown content with potential citations

    Returns:
        Tuple of:
        - Set of existing citation keys (e.g., {'1', '2', 'deck'})
        - Highest numeric citation number (0 if none)
        - Main content (before ### Citations)
        - Existing citations section (after ### Citations)
    """
    # Split content from citations section
    parts = content.split("### Citations")
    main_content = parts[0].strip() if parts else content.strip()
    citations_section = parts[1].strip() if len(parts) > 1 else ""

    # Find all citation keys in inline references
    inline_refs = set(re.findall(r'\[\^([a-zA-Z0-9_]+)\]', main_content))

    # Find all citation keys in definitions
    definition_keys = set(re.findall(r'^\[\^([a-zA-Z0-9_]+)\]:', citations_section, re.MULTILINE))

    all_keys = inline_refs | definition_keys

    # Find highest numeric citation
    highest_num = 0
    for key in all_keys:
        try:
            num = int(key)
            if num > highest_num:
                highest_num = num
        except ValueError:
            pass  # Non-numeric key like 'deck'

    return all_keys, highest_num, main_content, citations_section


def build_enrichment_prompt(
    content: str,
    section_name: str,
    company_name: str,
    existing_keys: Set[str],
    start_from: int
) -> str:
    """
    Build a prompt that instructs Perplexity to ADD citations without changing existing content.

    Args:
        content: The research content to enrich
        section_name: Name of the section
        company_name: Company name
        existing_keys: Set of existing citation keys to preserve
        start_from: Number to start new citations from

    Returns:
        Prompt string for Perplexity
    """
    existing_list = ", ".join(sorted(existing_keys)) if existing_keys else "none"

    return f"""You are enriching research content for {company_name} with additional citations.

CRITICAL PRESERVATION RULES:
1. DO NOT rewrite, rephrase, or modify ANY existing text
2. DO NOT remove or change ANY existing citations [{existing_list}]
3. DO NOT add citations to claims that already have citations
4. ONLY add NEW citations to UNCITED factual claims

CITATION NUMBERING:
- Existing citations: {existing_list}
- Start NEW citations from: [^{start_from}]
- Number sequentially: [^{start_from}], [^{start_from + 1}], [^{start_from + 2}], etc.

WHAT TO CITE (if not already cited):
- Market size and TAM figures
- Company founding date, location, team info
- Funding amounts and investor names
- Technical specifications and product details
- Traction metrics and milestones
- Competitive landscape claims

CITATION FORMAT:
- Inline: Place AFTER punctuation with space: "text. [^{start_from}]"
- Definition: [^N]: YYYY, MMM DD. [Title](https://url.com). Publisher. Published: YYYY-MM-DD | Updated: N/A

OUTPUT REQUIREMENTS:
1. Return the COMPLETE content with new citations added (preserve ALL existing text exactly)
2. End with "### New Citations" header followed by ONLY the NEW citation definitions
3. Do NOT include existing citations in the New Citations section

RESEARCH CONTENT TO ENRICH:
{content}

Return the enriched content with new citations added to uncited claims, then a "### New Citations" section with only the new definitions."""


def enrich_research_with_citations(
    research_content: str,
    section_name: str,
    company_name: str,
    perplexity_client
) -> str:
    """
    Enrich research content with additional citations while preserving existing ones.

    Args:
        research_content: Research content to enrich
        section_name: Name of the section
        company_name: Company name
        perplexity_client: Perplexity API client

    Returns:
        Research content with additional citations merged in
    """
    # Extract existing citations
    existing_keys, highest_num, main_content, existing_citations = extract_existing_citations(research_content)
    start_from = highest_num + 1

    print(f"      Existing citations: {len(existing_keys)} (highest: {highest_num})")
    print(f"      New citations will start from: [^{start_from}]")

    # Build prompt
    prompt = build_enrichment_prompt(
        content=research_content,
        section_name=section_name,
        company_name=company_name,
        existing_keys=existing_keys,
        start_from=start_from
    )

    try:
        response = perplexity_client.chat.completions.create(
            model="sonar-pro",
            messages=[
                {"role": "system", "content": "You are a citation specialist. Your job is to ADD citations to uncited claims while preserving ALL existing content exactly as written."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=8000,
            temperature=0.2
        )
        enriched = response.choices[0].message.content

        # Validate that existing citations are preserved
        new_keys, _, new_main, new_citations = extract_existing_citations(enriched)

        missing_keys = existing_keys - new_keys
        if missing_keys:
            print(f"      WARNING: Perplexity removed citations: {missing_keys}")
            print(f"      Falling back to original content")
            return research_content

        # Count new citations added
        added_keys = new_keys - existing_keys
        print(f"      Added {len(added_keys)} new citations")

        # Merge citations: existing + new
        # Extract new citation definitions from Perplexity response
        new_citation_defs = ""
        if "### New Citations" in enriched:
            new_citation_defs = enriched.split("### New Citations")[1].strip()
            enriched = enriched.split("### New Citations")[0].strip()
        elif "### Citations" in enriched:
            # Perplexity might use regular Citations header
            enriched_parts = enriched.split("### Citations")
            if len(enriched_parts) > 1:
                new_main = enriched_parts[0].strip()
                potential_new_defs = enriched_parts[1].strip()
                # Only take definitions that are NEW (not in existing_keys)
                new_def_lines = []
                for line in potential_new_defs.split('\n'):
                    match = re.match(r'\[\^([a-zA-Z0-9_]+)\]:', line)
                    if match:
                        key = match.group(1)
                        if key not in existing_keys:
                            new_def_lines.append(line)
                    elif new_def_lines and line.strip():
                        # Continuation of previous definition
                        new_def_lines.append(line)
                new_citation_defs = '\n'.join(new_def_lines)
                enriched = new_main

        # Rebuild final content with merged citations
        final_content = enriched.strip()

        # Add citations section with existing + new
        all_citations = existing_citations.strip() if existing_citations else ""
        if new_citation_defs:
            if all_citations:
                all_citations += "\n\n" + new_citation_defs.strip()
            else:
                all_citations = new_citation_defs.strip()

        if all_citations:
            final_content += "\n\n---\n\n### Citations\n\n" + all_citations

        return final_content

    except Exception as e:
        print(f"      Warning: Citation enrichment failed: {e}")
        return research_content  # Return original if enrichment fails


def citation_enrichment_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation-Enrichment Agent - Enriches 1-research/ files with additional citations.

    This agent operates on research files (NOT sections) so that new citations
    become part of the source material that flows through the writer to sections.

    PRESERVATION: This agent preserves ALL existing content and citations.
    It only ADDS new citations to uncited factual claims.

    Args:
        state: Current memo state

    Returns:
        Updated state with enrichment results
    """
    company_name = state["company_name"]
    firm = state.get("firm")

    # Check if Perplexity is configured
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")
    if not perplexity_key:
        print("Warning: PERPLEXITY_API_KEY not set, skipping citation enrichment")
        return {
            "messages": ["Citation enrichment skipped - no Perplexity API key configured"]
        }

    # Initialize Perplexity client
    try:
        from openai import OpenAI
        from pathlib import Path
        from ..utils import get_output_dir_from_state

        # Use default_headers to set User-Agent (bypasses Cloudflare)
        perplexity_client = OpenAI(
            api_key=perplexity_key,
            base_url="https://api.perplexity.ai",
            default_headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
    except ImportError:
        print("Warning: openai package not installed, skipping citation enrichment")
        return {
            "messages": ["Citation enrichment skipped - openai package not installed"]
        }

    # Get output directory
    try:
        output_dir = get_output_dir_from_state(state)
        research_dir = output_dir / "1-research"
    except FileNotFoundError:
        print("Warning: No output directory found, skipping citation enrichment")
        return {"messages": ["Citation enrichment skipped - no output directory"]}

    if not research_dir.exists():
        print("Warning: No research directory found, skipping citation enrichment")
        return {"messages": ["Citation enrichment skipped - no research found"]}

    print(f"\n📚 Enriching research files with additional citations...")
    print(f"   (Preserving all existing content and citations)")

    # Load all research files
    research_files = sorted(research_dir.glob("*-research.md"))

    if not research_files:
        print("Warning: No research files found")
        return {"messages": ["Citation enrichment skipped - no research files"]}

    total_citations_added = 0
    files_enriched = 0

    for research_file in research_files:
        section_name = research_file.stem.replace("-research", "").split("-", 1)
        section_name = section_name[1] if len(section_name) > 1 else section_name[0]
        section_name = section_name.replace("-", " ").title()

        print(f"  Enriching: {section_name}...")

        # Read research file
        with open(research_file) as f:
            research_content = f.read()

        # Count existing citations
        existing_keys, _, _, _ = extract_existing_citations(research_content)
        citations_before = len(existing_keys)

        # Enrich with citations (preserving existing)
        enriched_content = enrich_research_with_citations(
            research_content=research_content,
            section_name=section_name,
            company_name=company_name,
            perplexity_client=perplexity_client
        )

        # Count new citations
        new_keys, _, _, _ = extract_existing_citations(enriched_content)
        citations_after = len(new_keys)
        citations_added = citations_after - citations_before

        if citations_added > 0:
            # Save enriched research back
            with open(research_file, "w") as f:
                f.write(enriched_content)

            total_citations_added += citations_added
            files_enriched += 1
            print(f"    ✓ Added {citations_added} citations (total: {citations_after})")
        else:
            print(f"    - No new citations added (existing: {citations_before})")

    summary = f"Citation enrichment complete: {total_citations_added} citations added across {files_enriched} files"
    print(f"\n✓ {summary}")

    return {
        "messages": [summary]
    }


def extract_citation_count(content: str) -> list:
    """
    Extract list of citations from content.

    Args:
        content: Markdown content with citations

    Returns:
        List of citation markers found (e.g., ["[^1]", "[^2]"])
    """
    # Find all citation markers like [^1], [^2], etc.
    citations = re.findall(r'\[\^\w+\]', content)
    return list(set(citations))  # Return unique citations

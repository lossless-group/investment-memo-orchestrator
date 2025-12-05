"""
Internal Comments Sanitizer Agent

Detects and extracts LLM process commentary from memo sections,
moving it to a separate internal notes folder while preserving
clean, shareable content in the main sections.

This addresses the inherent LLM tendency to include meta-commentary
like "Let me search for...", "Note: Unable to find...", etc.
"""

import re
from pathlib import Path
from typing import Tuple, List, Dict, Any
from datetime import datetime

from ..state import MemoState
from ..utils import get_latest_output_dir


# Regex patterns for detecting leaked LLM commentary
LEAKED_COMMENTARY_PATTERNS = [
    # Process narration - sentences that start with LLM process descriptions
    (r"^Let me (search|look|find|check|verify|research|examine|explore|investigate).*?[.!]\s*", "process_narration"),
    (r"^I('ll| will| would| can| could) (add|include|search|look|find|check|verify|now|first).*?[.!]\s*", "process_narration"),
    (r"^(Searching|Looking|Checking|Verifying|Examining|Exploring) for.*?[.!]\s*", "process_narration"),
    (r"^(Based on|According to) (my search|the search|my research|the research).*?[.!]\s*", "process_narration"),

    # Capability caveats - **Note:** blocks explaining limitations
    (r"\*\*Note:\*\*[^*]*?(does not contain|unable to|could not|cannot|no .* found|no .* available)[^*]*?\n", "capability_caveat"),
    (r"\*\*Note:\*\*[^*]*?(placeholder|needs to be|should be|will be added)[^*]*?\n", "capability_caveat"),

    # Data gap confessions
    (r"Data not verified for this entity[^.]*\.", "data_gap"),
    (r"Unable to (find|verify|locate|confirm|determine)[^.]*\.", "data_gap"),
    (r"No (specific|concrete|verified|reliable) (data|information|metrics|details)[^.]*\.", "data_gap"),
    (r"(Could not|Cannot|Couldn't) (find|verify|locate|confirm|access)[^.]*\.", "data_gap"),

    # User instructions - asking user to provide content
    (r"(please|kindly) (share|provide|send|supply)[^.]*\.", "user_instruction"),
    (r"Once (the|you|we) (actual|have|receive|get)[^.]*\.", "user_instruction"),
    (r"If you have[^.]*please[^.]*\.", "user_instruction"),
    (r"When (the actual|you provide|we receive)[^.]*\.", "user_instruction"),

    # Task acknowledgments
    (r"I('ll| will) add (appropriate|relevant|proper)[^.]*\.", "task_acknowledgment"),
    (r"(hyperlinks|citations|links|references) (can|will|should) be added[^.]*\.", "task_acknowledgment"),
    (r"Once the content is provided[^.]*\.", "task_acknowledgment"),

    # Hedging statements at start of sentences
    (r"^Unfortunately,.*?[.!]\s*", "hedging"),
    (r"I was unable to[^.]*\.", "hedging"),
    (r"(could not|couldn't) be (verified|confirmed|found|located)[^.]*\.", "hedging"),

    # Placeholder indicators
    (r"appears to be a placeholder[^.]*\.", "placeholder"),
    (r"This section (is|appears|seems) (empty|incomplete|placeholder)[^.]*\.", "placeholder"),
    (r"\[placeholder\]|\[to be added\]|\[TBD\]|\[TODO\]", "placeholder"),

    # Full paragraph blocks that are clearly internal
    (r"---\s*\n\*\*Note:\*\*[\s\S]*?(?=\n---|\n##|\Z)", "note_block"),
]

# Patterns that indicate an entire paragraph should be extracted
PARAGRAPH_EXTRACTION_PATTERNS = [
    r"^Let me ",
    r"^\*\*Note:\*\*",
    r"^I('ll| will| would) ",
    r"^If you have",
    r"^Once (the|you|we)",
    r"^Unfortunately,",
    r"^This section (does not|appears|seems)",
]


def detect_commentary_in_line(line: str) -> Tuple[bool, str, str]:
    """
    Check if a line contains leaked commentary.

    Returns:
        Tuple of (is_commentary, category, matched_text)
    """
    for pattern, category in LEAKED_COMMENTARY_PATTERNS:
        match = re.search(pattern, line, re.IGNORECASE | re.MULTILINE)
        if match:
            return True, category, match.group(0)
    return False, "", ""


def should_extract_paragraph(paragraph: str) -> bool:
    """
    Determine if an entire paragraph should be extracted as internal commentary.
    """
    first_line = paragraph.strip().split('\n')[0] if paragraph.strip() else ""
    for pattern in PARAGRAPH_EXTRACTION_PATTERNS:
        if re.match(pattern, first_line, re.IGNORECASE):
            return True
    return False


def extract_commentary(content: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    Extract internal commentary from content.

    Args:
        content: The section content to analyze

    Returns:
        Tuple of (clean_content, extracted_notes, extraction_log)
    """
    lines = content.split('\n')
    clean_lines = []
    extracted_items = []
    extraction_log = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for paragraph-level extraction (like **Note:** blocks)
        if should_extract_paragraph(line):
            # Collect the entire paragraph
            paragraph_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                paragraph_lines.append(lines[i])
                i += 1
            paragraph = '\n'.join(paragraph_lines)

            # Log and extract
            is_commentary, category, _ = detect_commentary_in_line(paragraph)
            if is_commentary or should_extract_paragraph(paragraph):
                extracted_items.append({
                    'type': 'paragraph',
                    'category': category or 'paragraph_block',
                    'content': paragraph
                })
                extraction_log.append({
                    'line_start': i - len(paragraph_lines),
                    'category': category or 'paragraph_block',
                    'preview': paragraph[:80] + '...' if len(paragraph) > 80 else paragraph
                })
                # Skip this paragraph in clean output
                continue

        # Check for line-level commentary
        is_commentary, category, matched = detect_commentary_in_line(line)
        if is_commentary:
            extracted_items.append({
                'type': 'line',
                'category': category,
                'content': line
            })
            extraction_log.append({
                'line': i,
                'category': category,
                'preview': line[:80] + '...' if len(line) > 80 else line
            })
            # Don't add to clean output
        else:
            clean_lines.append(line)

        i += 1

    # Build extracted notes as markdown
    extracted_notes = ""
    if extracted_items:
        # Group by category
        by_category = {}
        for item in extracted_items:
            cat = item['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item['content'])

        # Format as markdown
        category_labels = {
            'process_narration': 'Process Narration',
            'capability_caveat': 'Capability Caveats',
            'data_gap': 'Data Gap Confessions',
            'user_instruction': 'User Instructions',
            'task_acknowledgment': 'Task Acknowledgments',
            'hedging': 'Hedging Statements',
            'placeholder': 'Placeholder Content',
            'note_block': 'Note Blocks',
            'paragraph_block': 'Extracted Paragraphs',
        }

        for category, items in by_category.items():
            label = category_labels.get(category, category.replace('_', ' ').title())
            extracted_notes += f"### {label}\n\n"
            for item in items:
                # Quote the extracted content
                quoted = '\n'.join(f"> {line}" for line in item.split('\n'))
                extracted_notes += f"{quoted}\n\n"

    # Clean up excessive blank lines in clean output
    clean_content = '\n'.join(clean_lines)
    clean_content = re.sub(r'\n{3,}', '\n\n', clean_content)

    return clean_content, extracted_notes, extraction_log


def sanitize_section_file(section_file: Path, internal_dir: Path) -> Dict[str, Any]:
    """
    Sanitize a single section file.

    Args:
        section_file: Path to the section markdown file
        internal_dir: Directory for internal notes

    Returns:
        Dict with sanitization results
    """
    content = section_file.read_text()
    clean_content, extracted_notes, extraction_log = extract_commentary(content)

    result = {
        'file': section_file.name,
        'had_commentary': bool(extracted_notes),
        'items_extracted': len(extraction_log),
        'extraction_log': extraction_log,
    }

    if extracted_notes:
        # Save internal notes
        section_name = section_file.stem
        notes_file = internal_dir / f"{section_name}-internal-notes.md"

        notes_content = f"# Internal Notes: {section_name}\n\n"
        notes_content += f"*Extracted: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        notes_content += "These notes contain process commentary and meta-content that was\n"
        notes_content += "extracted from the main section to keep the external output clean.\n\n"
        notes_content += "---\n\n"
        notes_content += extracted_notes

        notes_file.write_text(notes_content)
        result['notes_file'] = str(notes_file)

        # Update the clean section
        section_file.write_text(clean_content)
        result['clean_file'] = str(section_file)

    return result


def internal_comments_sanitizer_agent(state: MemoState) -> dict:
    """
    Sanitizes memo by extracting internal commentary to separate files.

    This agent:
    1. Scans all section files for leaked LLM commentary
    2. Extracts commentary to 2-sections-internal/ folder
    3. Updates clean sections in 2-sections/
    4. Consolidates all notes into 4-internal-notes.md
    5. Reassembles 4-final-draft.md without commentary

    Args:
        state: Current memo state

    Returns:
        Updated state with sanitization results
    """
    company_name = state["company_name"]
    firm = state.get("firm")

    print(f"\n{'='*70}")
    print(f"🧹 INTERNAL COMMENTS SANITIZER")
    print(f"{'='*70}")
    print(f"Company: {company_name}")

    # Get output directory
    try:
        output_dir = get_latest_output_dir(company_name, firm=firm)
    except FileNotFoundError:
        print(f"⚠️  No output directory found for {company_name}")
        return {
            "messages": [f"Sanitizer skipped - no output directory for {company_name}"]
        }

    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        print(f"⚠️  No sections directory found at {sections_dir}")
        return {
            "messages": ["Sanitizer skipped - no sections directory"]
        }

    # Create internal notes directory
    internal_dir = output_dir / "2-sections-internal"
    internal_dir.mkdir(exist_ok=True)

    print(f"Sections: {sections_dir}")
    print(f"Internal notes: {internal_dir}")
    print(f"{'='*70}\n")

    # Process each section
    results = []
    total_extracted = 0
    all_internal_notes = []

    section_files = sorted(sections_dir.glob("*.md"))
    print(f"Found {len(section_files)} section files\n")

    for section_file in section_files:
        print(f"  Scanning: {section_file.name}...")
        result = sanitize_section_file(section_file, internal_dir)
        results.append(result)

        if result['had_commentary']:
            total_extracted += 1
            print(f"    ✓ Extracted {result['items_extracted']} items")

            # Collect for consolidated notes
            section_name = section_file.stem
            notes_file = internal_dir / f"{section_name}-internal-notes.md"
            if notes_file.exists():
                notes_content = notes_file.read_text()
                # Extract just the notes part (after the header)
                if "---\n\n" in notes_content:
                    notes_part = notes_content.split("---\n\n", 1)[1]
                    all_internal_notes.append(f"## {section_name}\n\n{notes_part}")
        else:
            print(f"    ✓ Clean (no commentary detected)")

    # Generate consolidated internal notes
    if all_internal_notes:
        consolidated_path = output_dir / "4-internal-notes.md"

        consolidated = "# Internal Notes and Recommendations\n\n"
        consolidated += f"**Memo:** {company_name} Investment Memo\n"
        consolidated += f"**Sanitized:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        consolidated += "These notes were extracted from the memo during sanitization.\n"
        consolidated += "They contain process commentary, data gaps, and recommendations\n"
        consolidated += "that are useful internally but inappropriate for external documents.\n\n"
        consolidated += "---\n\n"
        consolidated += "\n---\n\n".join(all_internal_notes)

        consolidated_path.write_text(consolidated)
        print(f"\n✓ Consolidated notes: {consolidated_path}")

    # Reassemble final draft (import here to avoid circular imports)
    print(f"\n📑 Reassembling final draft...")
    try:
        # Use CLI assemble_draft module
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from cli.assemble_draft import assemble_final_draft
        assemble_final_draft(output_dir, verbose=False)
        print(f"✓ Final draft reassembled: {output_dir / '4-final-draft.md'}")
    except Exception as e:
        print(f"⚠️  Could not reassemble final draft: {e}")

    # Summary
    print(f"\n{'='*70}")
    print(f"✅ SANITIZATION COMPLETE")
    print(f"{'='*70}")
    print(f"Sections processed: {len(section_files)}")
    print(f"Sections with commentary: {total_extracted}")
    print(f"Internal notes directory: {internal_dir}")
    if all_internal_notes:
        print(f"Consolidated notes: {output_dir / '4-internal-notes.md'}")
    print(f"{'='*70}\n")

    return {
        "messages": [f"Sanitized memo: {total_extracted}/{len(section_files)} sections had internal commentary extracted"]
    }


# Standalone function for CLI use
def sanitize_memo(company_name: str, firm: str = None, version: str = None) -> Dict[str, Any]:
    """
    Sanitize a memo's sections (for CLI use).

    Args:
        company_name: Company/deal name
        firm: Optional firm name for firm-scoped IO
        version: Optional specific version (default: latest)

    Returns:
        Dict with sanitization results
    """
    from ..utils import get_latest_output_dir
    from ..artifacts import sanitize_filename

    # Resolve output directory
    if version:
        safe_name = sanitize_filename(company_name)
        if firm:
            from ..paths import resolve_deal_context
            ctx = resolve_deal_context(company_name, firm=firm)
            output_dir = ctx.outputs_dir / f"{safe_name}-{version}"
        else:
            output_dir = Path("output") / f"{safe_name}-{version}"
    else:
        output_dir = get_latest_output_dir(company_name, firm=firm)

    if not output_dir.exists():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        raise FileNotFoundError(f"Sections directory not found: {sections_dir}")

    # Create internal notes directory
    internal_dir = output_dir / "2-sections-internal"
    internal_dir.mkdir(exist_ok=True)

    # Process sections
    results = []
    all_internal_notes = []

    for section_file in sorted(sections_dir.glob("*.md")):
        result = sanitize_section_file(section_file, internal_dir)
        results.append(result)

        if result['had_commentary']:
            section_name = section_file.stem
            notes_file = internal_dir / f"{section_name}-internal-notes.md"
            if notes_file.exists():
                notes_content = notes_file.read_text()
                if "---\n\n" in notes_content:
                    notes_part = notes_content.split("---\n\n", 1)[1]
                    all_internal_notes.append(f"## {section_name}\n\n{notes_part}")

    # Generate consolidated notes
    consolidated_path = None
    if all_internal_notes:
        consolidated_path = output_dir / "4-internal-notes.md"

        consolidated = "# Internal Notes and Recommendations\n\n"
        consolidated += f"**Memo:** {company_name} Investment Memo\n"
        consolidated += f"**Sanitized:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        consolidated += "These notes were extracted from the memo during sanitization.\n"
        consolidated += "They contain process commentary, data gaps, and recommendations\n"
        consolidated += "that are useful internally but inappropriate for external documents.\n\n"
        consolidated += "---\n\n"
        consolidated += "\n---\n\n".join(all_internal_notes)

        consolidated_path.write_text(consolidated)

    return {
        'output_dir': str(output_dir),
        'sections_processed': len(results),
        'sections_with_commentary': sum(1 for r in results if r['had_commentary']),
        'internal_notes_dir': str(internal_dir),
        'consolidated_notes': str(consolidated_path) if consolidated_path else None,
        'results': results,
    }

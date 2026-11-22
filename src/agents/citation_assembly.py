"""
Citation Assembly Agent - Consolidates and renumbers citations across all sections.

This agent runs after all citation-adding and cleanup agents to:
1. Pair each section (2-sections/X.md) with its research file's definitions
   (1-research/X-research.md): citation keys are local to a section
2. Number sources 1..N across the memo by first appearance, one number per
   source (identified by link), via consolidate_citations()
3. Warn about any citation whose source is not in its section's research
4. Consolidate all citations into ONE block at document end
5. Assemble the final draft

Can be called:
- As part of the workflow (after remove_invalid_sources, before validate_citations)
- Independently via CLI: python -m src.agents.citation_assembly <output_dir>

Runs AFTER: citation_enrichment, toc_generator, revise_summaries, remove_invalid_sources
Runs BEFORE: validate_citations, fact_checker
"""

import json
import re
import sys
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from collections import OrderedDict
from urllib.parse import unquote

from ..state import MemoState
from ..utils import get_latest_output_dir


def extract_inline_citations(content: str) -> List[str]:
    """
    Extract all inline citation references from content in order of appearance.

    Handles both numeric ([^1], [^2]) and alphanumeric ([^deck], [^ehrtime]) citations.

    Args:
        content: Markdown content

    Returns:
        List of citation keys (as strings) in order of first appearance
    """
    seen = set()
    ordered = []

    # Match both numeric and alphanumeric citation keys
    for match in re.finditer(r'\[\^([a-zA-Z0-9_-]+)\](?!:)', content):
        key = match.group(1)
        if key not in seen:
            seen.add(key)
            ordered.append(key)

    return ordered


def extract_citation_definitions(content: str) -> Dict[str, str]:
    """
    Extract all citation definitions from content.

    Handles both numeric ([^1]:) and alphanumeric ([^deck]:) definitions.

    Args:
        content: Markdown content

    Returns:
        Dict mapping citation key to full definition text
    """
    definitions = {}

    # Match citation definitions: [^key]: ... (until next [^ or end of content)
    # Handles numeric and alphanumeric keys
    pattern = r'^\[\^([a-zA-Z0-9_-]+)\]:\s*(.+?)(?=^\[\^|\Z)'

    for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
        key = match.group(1)
        text = match.group(2).strip()
        definitions[key] = text

    return definitions


def remove_citation_definitions_from_content(content: str) -> str:
    """
    Remove all citation definition blocks from content.

    Handles both numeric ([^1]:) and alphanumeric ([^deck]:) definitions.

    Args:
        content: Markdown content

    Returns:
        Content with citation definitions removed
    """
    # Remove citation definitions (lines starting with [^key]:)
    lines = content.split('\n')
    filtered = []
    in_citation_block = False

    for line in lines:
        # Check if this line starts a citation definition (numeric or alphanumeric)
        if re.match(r'^\[\^[a-zA-Z0-9_-]+\]:', line):
            in_citation_block = True
            continue

        # Check if we're continuing a multi-line citation
        if in_citation_block:
            # If line is empty or starts with new citation, stay in block
            if line.strip() == '' or re.match(r'^\[\^[a-zA-Z0-9_-]+\]:', line):
                continue
            # If line starts with content (not indented continuation), exit block
            if not line.startswith(' ') and not line.startswith('\t'):
                in_citation_block = False
                filtered.append(line)
            # Otherwise skip (indented continuation)
            continue

        filtered.append(line)

    # Clean up trailing empty lines
    while filtered and filtered[-1].strip() == '':
        filtered.pop()

    result = '\n'.join(filtered)

    # Remove empty "### Citations" header (with optional preceding break)
    result = re.sub(r'\n*(?:---|\*\*\*)\n*### Citations\s*$', '', result, flags=re.MULTILINE)
    result = re.sub(r'\n*### Citations\s*$', '', result, flags=re.MULTILINE)

    return result.rstrip()


def renumber_inline_citations(content: str, old_to_new: Dict[str, str]) -> str:
    """
    Renumber all inline citation references in content.

    Handles both numeric and alphanumeric citation keys.

    Uses a single-pass callable-based substitution so that each match is
    independently rewritten based on the map. Two bugs the current
    implementation defends against:

    1. The previous sequential str.replace approach was vulnerable to a
       cascading-replacement bug: when [^notes1] -> [^1] ran, the resulting
       [^1] could then be caught by the next rule [^1] -> [^3], etc.,
       collapsing many distinct citations to a single number. The single-pass
       replacer below visits each marker exactly once.

    2. The previous `(?!:)` negative lookahead also excluded inline citations
       followed by an English colon — e.g., "three claims [^notes1]:" at the
       end of a list-introducing sentence — leaving them as orphan markers
       in the body. The fix here matches every [^X] marker, then asks "is
       this actually a definition?" by checking for the structural pattern
       of definitions: at the start of a line, followed by `: ` (colon and
       space, which separates a definition's key from its body). Inline
       citations at the end of an English sentence — even when followed by
       a colon — are correctly renumbered.

    Args:
        content: Markdown content
        old_to_new: Mapping from old citation keys to new ones

    Returns:
        Content with renumbered citations
    """
    if not old_to_new:
        return content

    def replacer(match: re.Match) -> str:
        start = match.start()
        end = match.end()
        text = match.string
        # A definition is `[^X]:` at the start of a line followed by a space.
        # Inline citations at end-of-sentence (e.g., "claims [^X]:") are NOT
        # at the start of a line and should be renumbered.
        at_line_start = (start == 0 or text[start - 1] == '\n')
        followed_by_colon_space = (
            end + 1 < len(text)
            and text[end] == ':'
            and text[end + 1] in (' ', '\t')
        )
        if at_line_start and followed_by_colon_space:
            # Definition — leave the body as-is so format_citation_block can
            # rewrite from the renumbered_definitions dict later.
            return match.group(0)
        old_key = match.group(1)
        new_key = old_to_new.get(old_key, old_key)
        return f'[^{new_key}]'

    return re.sub(r'\[\^([a-zA-Z0-9_-]+)\]', replacer, content)


def format_citation_block(citations: Dict[str, str], ordered_nums: List[str]) -> str:
    """
    Format citations as a consolidated markdown block.

    Args:
        citations: Dict mapping citation numbers to definition text
        ordered_nums: List of citation numbers in desired order

    Returns:
        Formatted citation block
    """
    lines = ['\n***\n', '\n### Citations\n']

    for num in ordered_nums:
        if num in citations:
            lines.append(f'[^{num}]: {citations[num]}\n')

    return '\n'.join(lines)


_DEFINITION_URL = re.compile(r'\]\(((?:https?|file)://[^)\s]+)\)')


def _source_identity(definition: str) -> str:
    """What makes two definitions the same source: the link, else the text.

    Dataroom sources are file:// links, and the same document is often described
    with different publisher text from one section to the next, so the link (not
    the text) has to be the identity. Percent-encoding is decoded so an encoded
    and an unencoded link to one document match.
    """
    match = _DEFINITION_URL.search(definition)
    if match:
        return unquote(match.group(1)).rstrip('/').lower()
    return ' '.join(definition.split()).lower()


def consolidate_citations(
    texts: List[str],
    definitions: Optional[List[Optional[Dict[str, str]]]] = None,
) -> Tuple[List[str], str, Dict[str, Any]]:
    """
    Consolidate citations across self-contained texts, with no files and no state.

    Unlike renumber_citations(), which treats citation keys as global across
    2-sections/, this treats each text's keys as LOCAL: section A's [^1] and
    section B's [^1] may be different sources, because each text carries its own
    definitions (the connector's section drafts do). A source is identified by
    its URL (or, without one, its definition text), so a source cited by
    several texts gets one number. Numbers run 1..N by first appearance.

    Args:
        texts: Section texts in memo order, each with its own [^key]: definitions
        definitions: Optional, one dict per text: definitions that text's keys
            resolve to when the text does not define them itself (the local
            pipeline passes each section's research-file definitions here).
            A definition in the text wins over one passed here.

    Returns:
        (bodies, citation_block, stats): each text with its definitions removed
        and its inline citations renumbered; one consolidated block made by
        format_citation_block() ("" if nothing is cited); and stats with
        "sources" (definitions in the block), "cited" (distinct numbers used),
        and "missing" (["<text index>:<key>", ...] cited without a definition).
    """
    number_of: Dict[str, str] = {}
    definition_of: Dict[str, str] = {}
    missing: List[str] = []
    bodies: List[str] = []
    for index, text in enumerate(texts):
        known: Dict[str, str] = dict((definitions[index] or {}) if definitions else {})
        known.update(extract_citation_definitions(text))
        body = remove_citation_definitions_from_content(text)
        local: Dict[str, str] = {}
        for key in extract_inline_citations(body):
            definition = known.get(key)
            if definition is None:
                missing.append(f"{index}:{key}")
                identity = f"missing:{index}:{key}"
            else:
                identity = _source_identity(definition)
            if identity not in number_of:
                number_of[identity] = str(len(number_of) + 1)
                if definition is not None:
                    definition_of[number_of[identity]] = definition
            local[key] = number_of[identity]
        bodies.append(renumber_inline_citations(body, local))
    ordered = sorted(definition_of, key=int)
    block = format_citation_block(definition_of, ordered) if ordered else ""
    stats = {"sources": len(ordered), "cited": len(number_of), "missing": missing}
    return bodies, block, stats


_DEFINITION_LINE = re.compile(r'^\[\^([a-zA-Z0-9_-]+)\]: (.*)$', re.MULTILINE)


def merge_duplicate_definitions(markdown: str) -> Tuple[str, int]:
    """Give each source exactly one definition in an assembled memo.

    The last pass before a final draft is written, whatever path assembled it.
    Definitions with the same _source_identity() are merged into the first;
    inline citations are pointed at it, and all citations are renumbered 1..N
    by first inline appearance, with the definitions rewritten in that order
    where the first definition stood.

    Returns:
        (markdown, merged): merged is the number of duplicate definitions removed.
    """
    lines = _DEFINITION_LINE.findall(markdown)
    if not lines:
        return markdown, 0
    definitions = dict(lines)
    keeper_of: Dict[str, str] = {}
    first_key: Dict[str, str] = {}
    for key, definition in lines:
        identity = _source_identity(definition)
        first_key.setdefault(identity, key)
        keeper_of[key] = first_key[identity]
    merged = sum(1 for key, keeper in keeper_of.items() if key != keeper)

    first_definition = _DEFINITION_LINE.search(markdown).start()
    body = re.sub(r'^\[\^[a-zA-Z0-9_-]+\]: .*\n?(?:[ \t]*\n)*', '', markdown, flags=re.MULTILINE)
    body = renumber_inline_citations(body, {k: v for k, v in keeper_of.items() if k != v})

    order: List[str] = []
    for key in extract_inline_citations(body):
        if key not in order and key in definitions:
            order.append(key)
    new_number = {key: str(i) for i, key in enumerate(order, 1)}
    body = renumber_inline_citations(body, new_number)

    block = '\n'.join(f'[^{new_number[key]}]: {definitions[key]}\n' for key in order)
    # The definitions were removed from the body, so map the original offset
    # of the first one to the same point in the rewritten text.
    prefix = renumber_inline_citations(
        renumber_inline_citations(markdown[:first_definition], {k: v for k, v in keeper_of.items() if k != v}),
        new_number,
    )
    insert_at = len(prefix) if body.startswith(prefix) else len(body)
    return body[:insert_at] + block + '\n' + body[insert_at:], merged


def build_background_sources_block(state, cited_urls: set) -> str:
    """Render approved-but-uncited sources as a Background Sources block.

    An approved source that no claim happened to need is still part of the
    diligence record: the analyst vouched for it, and several are approved
    precisely because they are authoritative but unreachable to bots (McKinsey,
    Reuters, the NYT all refuse automated fetches, so they can supply no text to
    cite). Dropping them from the references misrepresents what the memo was
    built from — it makes a 28-source corpus look like a 15-source one.

    They are listed separately rather than merged into the numbered citations,
    because a numbered footnote asserts "this source supports that claim" and
    these support no particular claim. Same record, honest about its status.
    """
    try:
        from ..curation import load_sources_md
        from ..agents.codified_section_researcher import find_deal_inputs_dir
        from ..curation.sources_md import is_approved_entry
        from .perplexity_sources import normalize_url
    except Exception:  # noqa: BLE001
        return ""

    inputs_dir = find_deal_inputs_dir(state)
    if not inputs_dir:
        return ""
    sources_md = load_sources_md(inputs_dir)
    if not sources_md or not sources_md.sources:
        return ""

    cited_norm = {normalize_url(u) for u in cited_urls if u}
    uncited = [
        e for e in sources_md.sources
        if e.url and is_approved_entry(e) and normalize_url(e.url) not in cited_norm
    ]
    if not uncited:
        return ""

    lines = [
        "## Background Sources",
        "",
        "_Approved sources reviewed for this memo that no specific claim cites._",
        "",
    ]
    for e in sorted(uncited, key=lambda x: (x.publisher or "", x.title or x.url)):
        title = (e.title or "").strip() or e.url
        # Some titles are whole documents — an X post carries its full body as
        # <title>. Collapse newlines and cap length so the list stays readable.
        title = " ".join(title.split())
        if len(title) > 130:
            title = title[:127].rstrip(" ,.;:-") + "…"
        title = title.replace("[", "(").replace("]", ")")
        bits = []
        if e.publisher:
            bits.append(e.publisher)
        if e.published_date:
            bits.append(str(e.published_date))
        meta = f" {' · '.join(bits)}." if bits else ""
        lines.append(f"- [{title}]({e.url}).{meta}")
    lines.append("")
    return "\n".join(lines)


def citation_assembly_agent(state: MemoState) -> Dict[str, Any]:
    """
    Citation Assembly Agent implementation.

    Consolidates all citations from section files into a single block
    with sequential numbering.

    Args:
        state: Current memo state

    Returns:
        Updated state with messages
    """
    company_name = state["company_name"]
    firm = state.get("firm")

    print(f"\n📚 Assembling citations for {company_name}...")

    # Get output directory from state (created at workflow start)
    from ..utils import get_output_dir_from_state
    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        return {
            "messages": ["Citation assembly skipped: no output directory found"]
        }

    return assemble_citations(output_dir, state)


def renumber_citations(output_dir: Path) -> Dict[str, Any]:
    """
    Renumber citations in section files and build a consolidated citation block.

    This is the RENUMBERING-ONLY function. It:
    1. Reads all sections and collects citations
    2. Builds a sequential renumbering map
    3. Renumbers inline refs in section files (writes back to disk)
    4. Removes citation definitions from section files
    5. Returns the consolidated citation block as a string

    Does NOT assemble the final draft — that's the assembler's job.

    CAUTION: this treats citation keys as GLOBAL across sections, so when two
    sections' research files both use [^25] for different sources, both get
    the first one found. assemble_citations() no longer uses it for that reason
    (see context-v/issues/Final-Draft-Citations-Collide-Across-Sections.md);
    it remains for cli/assemble_draft.py.

    Args:
        output_dir: Path to output directory containing 2-sections/

    Returns:
        Dict with:
          - "citation_block": str — the consolidated citation definitions block
          - "stats": dict with total_inline_refs, definitions_found, etc.
          - "messages": list of status messages
    """
    output_dir = Path(output_dir)
    sections_dir = output_dir / "2-sections"
    research_dir = output_dir / "1-research"
    header_file = output_dir / "header.md"

    if not sections_dir.exists():
        print("  ⚠️  No sections directory found")
        return {"citation_block": "", "stats": {}, "messages": ["Citation renumbering skipped: no sections directory"]}

    # Step 1: Read all sections and collect citations
    print("  📖 Reading sections and collecting citations...")

    all_definitions: Dict[str, str] = {}  # citation_num -> definition
    appearance_order: List[str] = []  # citation numbers in order of first appearance

    # Process header first if exists
    if header_file.exists():
        content = header_file.read_text()
        for num in extract_inline_citations(content):
            if num not in appearance_order:
                appearance_order.append(num)

    # Process sections in order
    section_files = sorted(sections_dir.glob("*.md"))

    for section_file in section_files:
        content = section_file.read_text()

        # Extract inline citations (track order)
        for num in extract_inline_citations(content):
            if num not in appearance_order:
                appearance_order.append(num)

        # Extract definitions from sections
        definitions = extract_citation_definitions(content)
        for num, text in definitions.items():
            if num not in all_definitions:
                all_definitions[num] = text

    # Also collect definitions from 1-research/ as fallback source
    # (definitions may have been stripped from sections in previous runs)
    if research_dir.exists():
        for research_file in sorted(research_dir.glob("*.md")):
            content = research_file.read_text()
            definitions = extract_citation_definitions(content)
            for num, text in definitions.items():
                if num not in all_definitions:
                    all_definitions[num] = text

    total_citations = len(appearance_order)
    print(f"  📊 Found {total_citations} unique citations across {len(section_files)} sections")

    if total_citations == 0:
        print("  ℹ️  No citations found")
        return {"citation_block": "", "stats": {"total_inline_refs": 0, "definitions_found": 0, "missing_definitions": 0, "renumbered": False}, "messages": ["No citations to renumber"]}

    # Step 2: Build renumbering map (sequential starting at 1)
    old_to_new: Dict[str, str] = {}
    new_to_old: Dict[str, str] = {}

    for new_num, old_num in enumerate(appearance_order, 1):
        old_to_new[old_num] = str(new_num)
        new_to_old[str(new_num)] = old_num

    # Check if renumbering is needed
    needs_renumbering = any(old != new for old, new in old_to_new.items())

    if needs_renumbering:
        print(f"  🔢 Renumbering {total_citations} citations...")
    else:
        print(f"  ✓ Citations already sequential (1-{total_citations})")

    # Step 3: Process each section.
    #
    # IMPORTANT: section files are the durable source of truth for *both* prose
    # and the inline citation IDs they reference. Section files keep their
    # semantic IDs (`[^chroma-site]`, `[^notes1]`, etc.) — they are NEVER
    # renumbered in place. The assembler only:
    #   (a) strips local `[^X]:` definitions from section files (defs belong
    #       in 1-research/, not duplicated in sections), and
    #   (b) writes a renumbered copy of the content into the assembled final
    #       draft (the renumbering happens at assembly time, not section time).
    #
    # If we wrote renumbered IDs back to section files here, every assembler
    # run would replace the durable semantic IDs with numeric IDs that depend
    # on the current run's appearance_order. Section files would then have
    # `[^12]`, `[^13]`, etc. with no matching `[^12]:` / `[^13]:` definitions
    # in research, and the next assembler run would orphan them. See
    # context-v/skills/manage-memo-citations and adhoc-edits-workflow.
    print("  ✏️  Processing sections (strip defs only — inline IDs preserved)...")

    for section_file in section_files:
        content = section_file.read_text()
        original = content

        # Strip [^X]: definitions from section files (they belong in research).
        content = remove_citation_definitions_from_content(content)

        if content != original:
            section_file.write_text(content)
            print(f"    ✓ {section_file.name}")

    # Process header if exists
    if header_file.exists():
        content = header_file.read_text()
        original = content
        content = remove_citation_definitions_from_content(content)
        if needs_renumbering:
            content = renumber_inline_citations(content, old_to_new)
        if content != original:
            header_file.write_text(content)
            print(f"    ✓ header.md")

    # Step 4: Build renumbered citation definitions
    renumbered_definitions: Dict[str, str] = {}
    for new_num in sorted(new_to_old.keys(), key=int):
        old_num = new_to_old[new_num]
        if old_num in all_definitions:
            renumbered_definitions[new_num] = all_definitions[old_num]
        else:
            print(f"    ⚠️  Warning: No definition found for [^{old_num}] (now [^{new_num}])")

    # Build citation block string
    citation_block = ""
    if renumbered_definitions:
        citation_block = format_citation_block(
            renumbered_definitions,
            sorted(renumbered_definitions.keys(), key=int)
        )

    defined_count = len(renumbered_definitions)
    missing_count = total_citations - defined_count

    summary = f"Renumbered {defined_count} citations (sequential 1-{defined_count})"
    if missing_count > 0:
        summary += f", {missing_count} missing definitions"

    print(f"\n  ✅ {summary}")

    return {
        "citation_block": citation_block,
        "old_to_new": old_to_new,  # Section files keep semantic IDs; assemble_citations() applies this map in memory at concat time.
        "stats": {
            "total_inline_refs": total_citations,
            "definitions_found": defined_count,
            "missing_definitions": missing_count,
            "renumbered": needs_renumbering,
        },
        "messages": [summary],
    }


def assemble_citations(output_dir: Path, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Full citation assembly: renumber citations AND assemble the final draft.

    This is the pipeline-facing function used by the workflow agent. Each
    section's keys are resolved against its own research file and the sections
    go through consolidate_citations() (as the connector's compile does), then
    sections + citation block are written as the final draft, with
    merge_duplicate_definitions() as the last pass. Stats include
    "research_mismatches": one warning per citation whose source is not in its
    section's research file.

    NOTE: This agent creates the final draft file. The TOC agent runs AFTER
    this in the workflow to insert the Table of Contents. Do not add TOC
    logic here — the orchestrator (workflow.py) owns that sequence.
    See context-v/reminders/Ideal-Orchestration-Agent-Workflow.md

    Args:
        output_dir: Path to output directory containing 2-sections/
        state: Pipeline state, used to find the deal's Sources.md for the
            Background Sources block. When omitted (standalone CLI), it is
            read from the run's state.json.

    Returns:
        Dict with messages and stats
    """
    output_dir = Path(output_dir)
    if state is None:
        # The Background Sources block referenced a `state` this function never
        # received, so it raised NameError and was skipped on every run.
        state_file = output_dir / "state.json"
        try:
            state = json.loads(state_file.read_text()) if state_file.exists() else {}
        except (OSError, ValueError):
            state = {}
    sections_dir = output_dir / "2-sections"
    research_dir = output_dir / "1-research"
    header_file = output_dir / "header.md"

    if not sections_dir.exists():
        print("  ⚠️  No sections directory found")
        return {"messages": ["Citation assembly skipped: no sections directory"]}

    # Step 1: Pair each text with the definitions its keys mean. Citation keys
    # are LOCAL to a section: each research file numbers its sources from 1, so
    # Overview's [^25] and Flags' [^25] are usually different sources. A section
    # resolves its keys against its own research file (2-sections/X.md ↔
    # 1-research/X-research.md, the name writer.py reads), then against any
    # definitions it carries itself. Section files keep their semantic IDs on
    # disk; renumbering happens in memory, in consolidate_citations().
    print("  📖 Reading sections and their research files...")
    section_files = sorted(sections_dir.glob("*.md"))
    fallback = _unambiguous_research_definitions(research_dir)

    names: List[str] = []
    texts: List[str] = []
    research_of: List[Optional[Dict[str, str]]] = []
    if header_file.exists():
        names.append(header_file.name)
        texts.append(header_file.read_text())
        research_of.append(None)
    for section_file in section_files:
        research_file = research_dir / f"{section_file.stem}-research.md"
        names.append(section_file.name)
        texts.append(section_file.read_text())
        research_of.append(
            extract_citation_definitions(research_file.read_text()) if research_file.exists() else None
        )

    resolve_with: List[Dict[str, str]] = []
    for name, text, research in zip(names, texts, research_of):
        if research is not None:
            resolve_with.append(research)
            _strip_definitions_kept_in_research(sections_dir / name, text, research)
            continue
        # No research file (header.md, a hand-added section, a stub-less run):
        # borrow a definition only when every research file that defines the
        # key agrees on its source. An ambiguous key stays undefined and is
        # reported, rather than silently taking the first section's source.
        own = extract_citation_definitions(text)
        borrowed: Dict[str, str] = {}
        for key in extract_inline_citations(remove_citation_definitions_from_content(text)):
            if key in own:
                continue
            if key in fallback:
                borrowed[key] = fallback[key]
            else:
                print(f"    ⚠️  {name}: [^{key}] has no definition and no research file to resolve it")
        resolve_with.append(borrowed)

    # Step 2: Consolidate. One number per source across the memo, 1..N by first
    # appearance; a source is identified by its link.
    bodies, citation_block, cstats = consolidate_citations(texts, resolve_with)
    print(f"  📊 Found {cstats['cited']} unique citations across {len(section_files)} sections")
    for missing in cstats["missing"]:
        index, key = missing.split(":", 1)
        print(f"    ⚠️  Warning: No definition found for [^{key}] in {names[int(index)]}")

    # Step 3: Guard. Every citation in the assembled sections must point at a
    # source its own research file cited. A mismatch is this bug class
    # (a key resolved against another section's research), so log each one.
    mismatches, unchecked = check_citations_against_research(names, texts, bodies, citation_block, research_of)
    for warning in mismatches:
        print(f"    ⚠️  {warning}")
    for name in unchecked:
        print(f"    ℹ️  {name}: no research file, citations not checked against research")

    print("  📄 Assembling final draft...")
    final_parts = list(bodies)
    if citation_block:
        final_parts.append(citation_block)

    # Approved sources that no claim cites still belong in the record.
    try:
        import re as _re
        cited_urls = set(_re.findall(r'\((https?://[^)\s]+)\)', citation_block or ""))
        background = build_background_sources_block(state, cited_urls)
        if background:
            final_parts.append(background)
            n = background.count("\n- ")
            print(f"  \u2713 Background Sources: {n} approved source(s) not cited inline")
    except Exception as exc:  # noqa: BLE001 - never break assembly over this
        print(f"  \u26a0\ufe0f  Background Sources block skipped: {exc}")

    # Write final draft, with one definition per source
    final_content, merged = merge_duplicate_definitions('\n\n'.join(final_parts))
    if merged:
        print(f"  ✓ Merged {merged} duplicate citation definition(s)")

    # Use canonical final draft path from final_draft module
    from ..final_draft import get_final_draft_path
    from ..md_breaks import normalize_section_breaks
    final_draft_path = get_final_draft_path(output_dir)
    final_draft_path.write_text(normalize_section_breaks(final_content))
    print(f"  ✓ Final draft: {final_draft_path.name}")

    summary = f"Assembled {cstats['sources']} citations (sequential 1-{cstats['sources']})"
    if cstats["missing"]:
        summary += f", {len(cstats['missing'])} missing definitions"
    if mismatches:
        summary += f", {len(mismatches)} not in their section's research"
    print(f"\n  ✅ {summary}")

    stats = {
        "total_inline_refs": cstats["cited"],
        "definitions_found": cstats["sources"],
        "missing_definitions": len(cstats["missing"]),
        "renumbered": True,
        "research_mismatches": mismatches,
        "unchecked_sections": unchecked,
        "final_draft": str(final_draft_path),
    }

    return {
        "messages": [summary],
        "citation_assembly": stats,
    }


def _unambiguous_research_definitions(research_dir: Path) -> Dict[str, str]:
    """Keys every research file that defines them agrees on.

    The fallback for a text with no research file of its own. A key two research
    files define with different sources is left out: it has no single meaning.
    """
    seen: Dict[str, Optional[str]] = {}
    if not research_dir.exists():
        return {}
    for research_file in sorted(research_dir.glob("*.md")):
        for key, definition in extract_citation_definitions(research_file.read_text()).items():
            if key not in seen:
                seen[key] = definition
            elif seen[key] is not None and _source_identity(seen[key]) != _source_identity(definition):
                seen[key] = None
    return {key: definition for key, definition in seen.items() if definition is not None}


def _strip_definitions_kept_in_research(section_file: Path, text: str, research: Dict[str, str]) -> None:
    """Remove a section file's own [^X]: definitions when its research holds them.

    Definitions belong in 1-research/. A section definition is only removed when
    the research file defines the same key with the same source, so a definition
    that exists nowhere else (or disagrees with research) is never lost.
    """
    own = extract_citation_definitions(text)
    if not own:
        return
    if all(key in research and _source_identity(research[key]) == _source_identity(d) for key, d in own.items()):
        section_file.write_text(remove_citation_definitions_from_content(text))
        print(f"    ✓ {section_file.name} (definitions left to research)")


_INLINE_MARKER = re.compile(r'\[\^([a-zA-Z0-9_-]+)\]')


def check_citations_against_research(
    names: List[str],
    texts: List[str],
    bodies: List[str],
    citation_block: str,
    research_of: List[Optional[Dict[str, str]]],
) -> Tuple[List[str], List[str]]:
    """Check the assembled output: each section cites only its own research.

    For every text with a research file, each inline citation in the assembled
    body is followed to its definition in the consolidated block, and that
    source must be one the research file defines. Original keys are recovered
    by pairing markers in order (renumbering replaces them one for one).

    Returns:
        (mismatches, unchecked): one warning per (section, key) whose source is
        not in that section's research; names of texts with no research file.
    """
    block = extract_citation_definitions(citation_block) if citation_block else {}
    mismatches: List[str] = []
    unchecked: List[str] = []
    for name, text, body, research in zip(names, texts, bodies, research_of):
        if research is None:
            if extract_inline_citations(body):
                unchecked.append(name)
            continue
        allowed = {_source_identity(d) for d in research.values()}
        original = _INLINE_MARKER.findall(remove_citation_definitions_from_content(text))
        assembled = _INLINE_MARKER.findall(body)
        reported = set()
        for old_key, new_key in zip(original, assembled):
            definition = block.get(new_key)
            if definition is None or old_key in reported:
                continue
            if _source_identity(definition) not in allowed:
                reported.add(old_key)
                link = _DEFINITION_URL.search(definition)
                source = link.group(1) if link else definition[:80]
                mismatches.append(f"{name}: [^{old_key}] cites a source not in its research file ({source})")
    return mismatches, unchecked


# CLI interface for standalone usage
def main():
    """CLI entry point for standalone citation assembly."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.citation_assembly <output_dir>")
        print("Example: python -m src.agents.citation_assembly io/dark-matter/deals/ProfileHealth/outputs/ProfileHealth-v0.0.3")
        sys.exit(1)

    output_dir = Path(sys.argv[1])

    if not output_dir.exists():
        print(f"Error: Directory not found: {output_dir}")
        sys.exit(1)

    result = assemble_citations(output_dir)

    if "error" in str(result.get("messages", [])).lower():
        sys.exit(1)


if __name__ == "__main__":
    main()

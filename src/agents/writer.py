"""
Writer Agent - Drafts investment memo sections following Hypernova format.

This agent is responsible for transforming research data into well-written
memo sections that follow the Hypernova style guide and template structure.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from ..state import MemoState, SectionDraft
from ..llm_provider import complete, complete_with_retry

# A section is one long generation, not an extraction, and the CLI carries fixed
# per-call overhead before it sees the prompt. The 300s provider default is tight
# for a 500-word section written against a full research file.
_TIMEOUT = 600

# Temperature was 0.7 here. The provider pins prose generation to 0, which AGENTS.md
# §8 permits either way — sampling temperature is explicitly allowed to vary because
# it must not change the cited facts, the source set, or the section structure.
_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929")
from ..artifacts import sanitize_filename, save_section_artifact
from ..versioning import VersionManager
from ..frame_context import writer_block
from ..outline_loader import load_outline_for_state
from ..schemas.outline_schema import OutlineDefinition, SectionDefinition
import re


def load_template(investment_type: str = "direct") -> str:
    """
    Load the appropriate memo template based on investment type.

    Args:
        investment_type: "direct" for startup investments, "fund" for LP commitments

    Returns:
        Template markdown content
    """
    templates_dir = Path(__file__).parent.parent.parent / "templates"

    if investment_type == "fund":
        template_path = templates_dir / "memo-template-fund.md"
    else:
        template_path = templates_dir / "memo-template-direct.md"

    # Fallback to original template if specific one doesn't exist
    if not template_path.exists():
        template_path = templates_dir / "memo-template.md"

    with open(template_path, "r") as f:
        return f.read()


def load_style_guide() -> str:
    """Load the style guide from file."""
    style_guide_path = Path(__file__).parent.parent.parent / "templates" / "style-guide.md"
    with open(style_guide_path, "r") as f:
        return f.read()


def parse_memo_sections(memo_content: str) -> Dict[str, str]:
    """
    Parse memo into individual sections.

    Args:
        memo_content: Full memo markdown content

    Returns:
        Dictionary mapping section names to content
    """
    sections = {}

    # Define the 10 expected sections with their markdown headers
    section_patterns = [
        (1, r"##\s*1\.\s*Executive Summary", "Executive Summary"),
        (2, r"##\s*2\.\s*Business Overview", "Business Overview"),
        (3, r"##\s*3\.\s*Market Context", "Market Context"),
        (4, r"##\s*4\.\s*Technology & Product", "Technology & Product"),
        (5, r"##\s*5\.\s*Traction & Milestones", "Traction & Milestones"),
        (6, r"##\s*6\.\s*Team", "Team"),
        (7, r"##\s*7\.\s*Funding & Terms", "Funding & Terms"),
        (8, r"##\s*8\.\s*Risks & Mitigations", "Risks & Mitigations"),
        (9, r"##\s*9\.\s*Investment Thesis", "Investment Thesis"),
        (10, r"##\s*10\.\s*Recommendation", "Recommendation"),
    ]

    # Split content by section headers
    for i, (num, pattern, name) in enumerate(section_patterns):
        # Find start of this section
        match = re.search(pattern, memo_content, re.IGNORECASE)
        if not match:
            continue

        start_pos = match.end()

        # Find start of next section (or end of document)
        if i + 1 < len(section_patterns):
            next_pattern = section_patterns[i + 1][1]
            next_match = re.search(next_pattern, memo_content[start_pos:], re.IGNORECASE)
            if next_match:
                end_pos = start_pos + next_match.start()
            else:
                end_pos = len(memo_content)
        else:
            end_pos = len(memo_content)

        # Extract section content
        section_content = memo_content[start_pos:end_pos].strip()
        sections[name] = section_content

    return sections


# System prompt for Writer Agent (template/style guide will be appended at runtime)
WRITER_SYSTEM_PROMPT_BASE = """You are an investment analyst writing memos for Hypernova Capital, a VENTURE CAPITAL firm.

Your task is to transform research data into a complete, well-structured investment memo
that follows Hypernova's format and style guidelines.

KEY WRITING PRINCIPLES:
1. VENTURE CAPITAL MINDSET - Look for reasons this could be a massive winner, while being honest about risks
2. Specific metrics over vague claims (use exact numbers, dates, names)
3. Lead with opportunity, acknowledge risks in the appropriate section
4. Source attribution for market claims
5. Follow the exact 10-section structure from the template

VENTURE CAPITAL vs PRIVATE EQUITY FRAMING:
- VC asks "What could go RIGHT?" not "What could go wrong?"
- VC looks for POTENTIAL while being aware of flaws
- VC builds the case for upside, not the case for passing
- Save skepticism and risk enumeration for Section 8 (Risks & Mitigations)
- Do NOT end sections with caveats, conditions, or "what needs to be validated"
- Observations and conclusions are encouraged - but frame as opportunity

SECTION REQUIREMENTS:
- Each section should be complete and self-contained
- Use bullet points for scannability
- Include specific numbers, dates, and names
- Cite sources for market data
- Match the word count targets in the style guide
- Spell out acronyms on first use

AVOID:
- Superlatives without data ("revolutionary", "game-changing")
- Vague growth claims ("massive market", "rapidly growing")
- PE-style skeptical wrap-ups at the end of every section
- "However, the investment thesis depends on..." outside Section 10
- "Conditions that need to be validated..." outside Sections 8 or 10
- Generalizations instead of specifics

OUTPUT FORMAT:
Return a complete markdown memo following the template structure exactly.
Replace all template placeholders with actual data from the research.
"""


def augment_section_draft(
    section_name: str,
    existing_draft: str,
    research: Dict[str, Any],
    deck_data: Dict[str, Any],
) -> str:
    """
    Augment existing section draft with research findings.

    Args:
        section_name: Name of the section being augmented
        existing_draft: Existing draft from deck analysis
        research: Research data
        deck_data: Deck analysis data (for context)

    Returns:
        Augmented section content
    """
    import json

    prompt = f"""You have an initial section draft from deck analysis. Augment it with web research findings.

EXISTING DRAFT (from pitch deck):
{existing_draft}

RESEARCH FINDINGS:
{json.dumps(research, indent=2)}

TASK:
1. Keep all good information from the existing draft
2. Add new findings from research (with appropriate context)
3. Fill in gaps noted in original draft
4. Maintain analytical tone
5. Ensure no contradictions (note if deck claims differ from research)
6. Integrate the information smoothly - don't just append

Output the AUGMENTED section (300-500 words) in markdown format.
Return ONLY the section content, no preamble.
"""

    completion = complete(prompt, max_tokens=4000, model=_MODEL, timeout=_TIMEOUT)
    if not completion.ok:
        # Returning the draft unchanged is the honest degradation: the deck-derived
        # text is real, it is simply un-augmented. Substituting an apology would put
        # meta-commentary into a section file (AGENTS.md §6).
        print(f"      ⚠️  Augmentation failed for {section_name}: "
              f"{completion.error or 'empty response'} "
              f"(provider={completion.provider}); keeping the deck draft")
        return existing_draft
    return completion.text



# =============================================================================
# Grounding sections in the company's own documents
# =============================================================================

def dataroom_facts_for_section(section_def, dataroom_analysis) -> str:
    """
    The slice of the dataroom a given section is answerable from.

    Web research says what the internet believes about a company. The dataroom is
    what the company stated in its own executed documents. When a memo's Funding
    & Terms section reads "valuation terms are not publicly available" while
    seven signed SAFEs sit in the same output folder, the pipeline has failed at
    the thing it exists to do.

    **Returns "" for anything it does not understand, and never raises.** Most
    deals have no dataroom at all — a pipeline deal is a deck plus web research,
    and `dataroom_analysis` is variously a dict, ``None``, or absent from state
    entirely depending on when the run was written. Grounding is an enhancement
    on top of the existing path, never a precondition for it: a writer that
    fails because a deal has no dataroom is worse than one that never had this.

    Facts are passed through **as stated, per document**. Nothing is reconciled:
    where two instruments differ, both appear, and the difference is structure.
    """
    import json as _json

    try:
        if not dataroom_analysis or not isinstance(dataroom_analysis, dict):
            return ""

        name = " ".join(str(getattr(section_def, attr, "") or "")
                        for attr in ("name", "filename")).lower()
        if not name.strip():
            return ""

        blocks = []

        def add(title, payload):
            if payload in (None, [], {}, ""):
                return
            blocks.append(f"### {title}\n```json\n"
                          f"{_json.dumps(payload, indent=1, default=str)[:6000]}\n```")

        def wants(*words):
            return any(w in name for w in words)

        def as_list(value):
            """`legal_docs` has been seen as a list and as a {documents: [...]} dict."""
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for key in ("documents", "records", "items"):
                    if isinstance(value.get(key), list):
                        return value[key]
            return []

        if wants("funding", "terms", "offering", "capital", "closing",
                 "executive", "scorecard"):
            # Per-document records, never the reconciled summary: reconciliation
            # collapses seven instruments at three caps into one number and
            # reports the differences as conflicts.
            instruments = [
                {k: d.get(k) for k in ("document_source", "security_type", "investor_name",
                                       "investment_amount", "valuation_cap", "discount_rate",
                                       "is_executed", "document_date", "effective_date")}
                for d in as_list(dataroom_analysis.get("legal_docs"))
                if isinstance(d, dict) and (d.get("investment_amount") or d.get("valuation_cap"))
            ]
            add("Financing instruments on file, one row per document, as stated", instruments)
            add("Cap table", dataroom_analysis.get("cap_table"))

        if wants("organization", "team", "people", "founder", "origins"):
            add("Team, from the dataroom", dataroom_analysis.get("team"))

        # The company's own competitive work. Five documents of it sat unread
        # while the competitive section was written from web search.
        if wants("competitive", "landscape", "market", "opportunity", "opening",
                 "positioning", "offering", "scorecard", "executive"):
            add("Competitive analysis, from the company's own documents",
                dataroom_analysis.get("competitive"))

        if wants("opportunity", "traction", "offering", "opening",
                 "scorecard", "executive"):
            add("Traction, from the dataroom", dataroom_analysis.get("traction"))
            add("Financials, from the dataroom", dataroom_analysis.get("financials"))

        if wants("risk", "closing", "executive"):
            add("Documents the dataroom does not contain", dataroom_analysis.get("data_gaps"))
            add("Where the company's own documents disagree with each other",
                dataroom_analysis.get("conflicts"))

        # Cheap, cross-cutting, and the same in every section.
        add("Key facts the dataroom established", dataroom_analysis.get("key_facts"))

        if not blocks:
            return ""

        inventory = dataroom_analysis.get("documents_by_type") or {}
        count = dataroom_analysis.get("document_count", "the")

        return f"""

## THE COMPANY'S OWN DOCUMENTS — use these first

These came from {count} documents the company provided.
Document types on file: {_json.dumps(inventory, default=str)[:1200]}

**These outrank web research.** Where the dataroom states a fact, state it, and
attribute it to the document it came from. Do not write that something is
"not disclosed", "not publicly available", or "not available in current
materials" when it appears below — that sentence is only true of the internet,
not of the dataroom.

Where two documents state different terms, report both with their sources. That
is deal structure, not a discrepancy to resolve, and never average or pick one.

Do not infer beyond what is stated. If a figure is absent here, it is absent.

{chr(10).join(blocks)}
"""

    except Exception as exc:  # never break a section over a grounding block
        print(f"      ⚠️  dataroom grounding skipped: {type(exc).__name__}: {exc}")
        return ""



def _prior_section_prose(frame, section_def, output_dir) -> str:
    """
    The existing section text, but only when a frame marks it `amend`.

    Read lazily and only for amend, because every other directive is either a
    clean regeneration (which must not see the old prose, or it will anchor on
    it) or a no-op.
    """
    if frame is None or not output_dir:
        return ""
    filename = getattr(section_def, "filename", "") or ""
    if frame.directive_for(filename).prose != "amend":
        return ""
    path = Path(output_dir) / "2-sections" / filename
    try:
        return path.read_text() if path.exists() else ""
    except OSError:
        return ""


def polish_section_research(
    section_def: SectionDefinition,
    research_content: str,
    company_name: str,
    memo_mode: str,
    style_guide: str,
    dataroom_facts: str = "",
    frame: Optional[Any] = None,
    output_dir: Optional[Any] = None,
) -> str:
    """
    Polish Perplexity research into final section while preserving citations.

    This is the NEW approach: take research with citations and polish it.

    Args:
        section_def: Section definition from outline
        research_content: Research content with citations from Perplexity
        company_name: Company name
        memo_mode: Memo mode
        style_guide: Style guide content

    Returns:
        Polished section content with preserved citations
    """
    import re

    # Count citations before polishing (alphanumeric keys like [^1], [^deck], [^source_name])
    all_citations_before = set(re.findall(r'\[\^([a-zA-Z0-9_]+)\]', research_content))
    citations_before = len(all_citations_before)

    # Find any embedded images in the research content
    image_embeds = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', research_content)
    has_images = len(image_embeds) > 0

    # Build mode guidance
    mode_guidance = ""
    if memo_mode == "justify":
        mode_guidance = "MEMO MODE: Retrospective justification (recommend COMMIT)"
    else:
        mode_guidance = "MEMO MODE: Prospective analysis (recommend PASS/CONSIDER/COMMIT)"

    # Get mode-specific emphasis if available
    mode_specific = section_def.mode_specific.get(memo_mode)
    if mode_specific:
        mode_guidance += f"\nSection Emphasis: {mode_specific.emphasis}"

    target_words = section_def.target_length.ideal_words

    # Thesis frame block. Empty when no frame is set, so a frameless run is
    # byte-identical to before. This is the primary writer path — the fallback
    # write_single_section only runs when a section has no research file.
    frame_guidance = writer_block(
        frame,
        getattr(section_def, "filename", "") or "",
        prior_prose=_prior_section_prose(frame, section_def, output_dir),
    )

    polish_prompt = f"""Rewrite the following Perplexity research into a polished "{section_def.name}" section for {company_name}.
{dataroom_facts}
{frame_guidance}

PERPLEXITY RESEARCH (with citations):
{research_content}

╔══════════════════════════════════════════════════════════════════════════════╗
║ VENTURE CAPITAL MINDSET (not Private Equity)                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

You are writing for a VC firm. VCs look for reasons to INVEST, not reasons to PASS.

VC FRAMING (what we want):
- Lead with opportunity and potential - "What could go RIGHT?"
- Draw observations and conclusions that highlight upside
- Connect facts to why this could be a massive winner
- Acknowledge risks exist, but save detailed risk analysis for Section 8

PE FRAMING (what to avoid):
- Do NOT end the section with skeptical wrap-ups or caveats
- Do NOT add "However, the investment thesis depends on..." (save for Section 10)
- Do NOT include "Conditions that need to be validated..." paragraphs
- Do NOT add "Assessment" subsections that enumerate concerns

Observations and conclusions are GOOD - just frame them as opportunity, not skepticism.

SECTION REQUIREMENTS:
- Target length: {target_words} words
- Analytical tone (not promotional, not PE-skeptical)
- Organized with clear subsections
- Scannable (use bullets where appropriate)
- {mode_guidance}

CITATION PRESERVATION (CRITICAL - WILL BE VALIDATED):
- PRESERVE ALL {citations_before} CITATIONS EXACTLY - DO NOT REMOVE ANY
- Citations may be numeric [^1] or alphanumeric [^deck] - preserve ALL of them
- Keep citation format: ". [^key]" (space before bracket, after punctuation)
- Keep ALL citation keys exactly as they appear: {list(all_citations_before)[:10]}{'...' if len(all_citations_before) > 10 else ''}
- DO NOT consolidate or remove "redundant" citations
- DO NOT renumber or rename citations - [^deck] MUST stay [^deck], [^1] MUST stay [^1]
- If a sentence has multiple citations [^1] [^deck], keep ALL of them
- INCLUDE the complete "### Citations" section at the end with ALL definitions
- COPY the citation definitions EXACTLY as they appear in the input (same keys, same text)
{"" if not has_images else f'''
IMAGE PRESERVATION (CRITICAL):
- PRESERVE ALL {len(image_embeds)} IMAGE EMBED(S) EXACTLY - DO NOT REMOVE ANY
- Keep image format: ![description](absolute/path/to/image.png)
- Place each image at the TOP of the section, before the text content
- These are screenshots from the company's pitch deck - they add credibility
- DO NOT modify the image paths
'''}
STYLE GUIDANCE:
{style_guide[:1000]}

WHAT YOU CAN DO:
- Reorder sentences and paragraphs
- Improve transitions and flow
- Add subsection headers
- Use bullet points for readability
- Rephrase for clarity

WHAT YOU CANNOT DO:
- Remove or change citation markers [^N]
- Remove the "### Citations" section
- Change citation format or spacing
- Add new factual claims without citations
- Change specific numbers or dates
- Consolidate multiple citations into one
- Remove or modify image embeds ![...](...)

VALIDATION: Your output will be checked to ensure ALL {citations_before} citations are preserved. If any are missing, the output will be rejected.

Output the polished section content (no section header "## {section_def.number}. {section_def.name}") followed by the complete "### Citations" section.
"""

    # Retry transient failures, then fall back to the unpolished research.
    # The retry used to catch anthropic's InternalServerError and RateLimitError;
    # complete() reports provider failures on the response rather than raising,
    # so complete_with_retry keys on .ok — which also covers a CLI timeout and an
    # empty completion, neither of which that exception list named.
    completion = complete_with_retry(
        polish_prompt,
        max_tokens=4000,
        model=_MODEL,
        timeout=_TIMEOUT,
        label=f"polish {section_def.name!r}",
    )
    if not completion.ok:
        print(f"      Using original research content without polishing")
        return research_content  # Fallback to original research

    polished_content = completion.text.strip()

    # Validate citations preserved (alphanumeric keys)
    all_citations_after = set(re.findall(r'\[\^([a-zA-Z0-9_]+)\]', polished_content))
    citations_after = len(all_citations_after)

    # Check if we lost citations
    lost_citations = all_citations_before - all_citations_after
    if lost_citations:
        print(f"      ⚠️  WARNING: Citation mismatch! Before: {citations_before}, After: {citations_after}")
        print(f"      Lost citations: {lost_citations}")
        print(f"      Using original research content to preserve citations")
        # Fall back to original research if citations were lost
        return research_content

    # Validate citation list exists
    if "### Citations" not in polished_content:
        print(f"      ⚠️  WARNING: Citation list missing! Using original research")
        return research_content

    # Validate citation DEFINITIONS exist (not just the header)
    # Count definitions in original research
    defs_before = len(re.findall(r'^\[\^[a-zA-Z0-9_]+\]:', research_content, re.MULTILINE))
    defs_after = len(re.findall(r'^\[\^[a-zA-Z0-9_]+\]:', polished_content, re.MULTILINE))

    if defs_before > 0 and defs_after == 0:
        print(f"      ⚠️  WARNING: Citation definitions lost! Before: {defs_before}, After: {defs_after}")
        print(f"      Using original research content to preserve citations")
        return research_content

    if defs_after < defs_before * 0.5:  # Lost more than half
        print(f"      ⚠️  WARNING: Too many citation definitions lost! Before: {defs_before}, After: {defs_after}")
        print(f"      Using original research content to preserve citations")
        return research_content

    # Validate that definition keys match inline citation keys
    inline_keys_after = set(re.findall(r'\[\^([a-zA-Z0-9_]+)\](?!:)', polished_content))
    definition_keys_after = set(re.findall(r'^\[\^([a-zA-Z0-9_]+)\]:', polished_content, re.MULTILINE))

    # Check if LLM renumbered citations (inline keys don't match original)
    if inline_keys_after != all_citations_before:
        renamed_keys = inline_keys_after - all_citations_before
        if renamed_keys:
            print(f"      ⚠️  WARNING: LLM renamed citation keys! New keys: {renamed_keys}")
            print(f"      Original keys were: {all_citations_before}")
            print(f"      Using original research content to preserve citations")
            return research_content

    # Check if definitions match inline references
    missing_defs = inline_keys_after - definition_keys_after
    if missing_defs:
        print(f"      ⚠️  WARNING: Missing definitions for inline citations: {missing_defs}")
        print(f"      Using original research content to preserve citations")
        return research_content

    # Validate images preserved (if any existed)
    if has_images:
        images_after = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', polished_content)
        if len(images_after) < len(image_embeds):
            print(f"      ⚠️  WARNING: Image embeds lost! Before: {len(image_embeds)}, After: {len(images_after)}")
            # Prepend missing images to the content
            missing_images = []
            after_paths = {path for _, path in images_after}
            for desc, path in image_embeds:
                if path not in after_paths:
                    missing_images.append(f"![{desc}]({path})")
            if missing_images:
                print(f"      Restoring {len(missing_images)} missing image embed(s)")
                polished_content = "\n\n".join(missing_images) + "\n\n" + polished_content

    return polished_content


def write_single_section(
    section_def: SectionDefinition,
    research: Dict[str, Any],
    company_name: str,
    investment_type: str,
    memo_mode: str,
    style_guide: str,
    current_date: str,
    dataroom_facts: str = "",
    frame: Optional[Any] = None,
    output_dir: Optional[Any] = None,
) -> str:
    """
    Write a single section of the memo using outline guidance.

    NOTE: This is the FALLBACK approach when section research doesn't exist.
    Prefer polish_section_research() when Perplexity research files are available.

    Args:
        section_def: Section definition from outline (with guiding questions, vocabulary)
        research: Research data
        company_name: Company name
        investment_type: Investment type
        memo_mode: Memo mode
        style_guide: Style guide content
        current_date: Current date string

    Returns:
        Section content as markdown
    """
    import json

    research_json = json.dumps(research, indent=2)[:3000]  # Limit research to 3k chars

    # Get mode-specific guidance from outline
    mode_specific = section_def.mode_specific.get(memo_mode)
    mode_guidance = ""

    if memo_mode == "justify":
        mode_guidance = """
IMPORTANT - MEMO MODE: JUSTIFY (Retrospective Justification)
This memo is justifying an EXISTING investment we have already made. Your recommendation MUST be "COMMIT"
since the investment has already occurred. Focus on explaining WHY we made this investment and what
strengths/thesis justified the commitment.
"""
    else:  # consider mode
        mode_guidance = """
IMPORTANT - MEMO MODE: CONSIDER (Prospective Analysis)
This memo is evaluating a POTENTIAL investment we have not yet made. Your recommendation should be
PASS, CONSIDER, or COMMIT based on the objective analysis of strengths vs. risks.
"""

    if mode_specific:
        mode_guidance += f"\nSection Emphasis: {mode_specific.emphasis}\n"

    # Thesis frame block. Empty string when no frame is set, so a frameless run
    # produces byte-identical prompts to before this existed.
    frame_guidance = writer_block(
        frame,
        getattr(section_def, "filename", "") or "",
        prior_prose=_prior_section_prose(frame, section_def, output_dir),
    )

    # Format guiding questions
    questions_text = "\n".join(f"- {q}" for q in section_def.guiding_questions)

    # Format vocabulary guidance
    vocab = section_def.section_vocabulary
    vocab_text = ""
    if vocab.preferred_terms:
        vocab_text += "\nPREFERRED TERMINOLOGY:\n" + "\n".join(f"- {term}" for term in vocab.preferred_terms[:5])
    if vocab.avoid:
        vocab_text += "\n\nAVOID:\n" + "\n".join(f"- {term}" for term in vocab.avoid[:5])
    if vocab.required_elements:
        vocab_text += "\n\nREQUIRED ELEMENTS:\n" + "\n".join(f"- {elem}" for elem in vocab.required_elements[:5])

    # Target length
    target_length = section_def.target_length.ideal_words

    user_prompt = f"""Write ONLY the "{section_def.name}" section for an investment memo about {company_name}.
{dataroom_facts}

CURRENT DATE: {current_date}
INVESTMENT TYPE: {investment_type.upper()}
{mode_guidance}
{frame_guidance}

SECTION GUIDANCE:
{section_def.description}

╔══════════════════════════════════════════════════════════════════════════════╗
║ CRITICAL RULES - FAILURE TO FOLLOW = AUTOMATIC REJECTION                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

0. VENTURE CAPITAL MINDSET (not Private Equity)
   You are writing for a VC firm. VCs look for reasons to INVEST, not reasons to PASS.

   VC FRAMING (what we want):
   - "What could go RIGHT?" - lead with opportunity and potential
   - Draw observations and conclusions that highlight upside
   - Connect facts to why this could be a massive winner
   - Acknowledge risks exist, but save detailed risk analysis for Section 8

   PE FRAMING (what to avoid):
   - Do NOT end every section with skeptical wrap-ups or caveats
   - Do NOT add "However, the investment thesis depends on..." (save for Section 10)
   - Do NOT include "Conditions that need to be validated..." paragraphs
   - Do NOT add "Assessment" subsections that enumerate concerns
   - Do NOT frame the narrative around "what could go wrong"

   Observations and conclusions are GOOD - just frame them as opportunity, not skepticism.

1. NEVER FABRICATE METRICS
   - If you don't have revenue data, write "Revenue data not available"
   - If you don't have pricing, write "Pricing not publicly available"
   - If you don't have customer count, write "Customer count not disclosed"
   - If you don't have growth rate, write "Growth metrics not disclosed"

2. CITE OR OMIT
   - Every specific number (revenue, customers, growth %) must come from research
   - If research doesn't mention a metric, DO NOT include it
   - "Estimated", "likely", "approximately", "around" = fabrication in disguise

3. DISTINGUISH FACT FROM INFERENCE
   - ✓ CORRECT: "The company has 50 customers according to their blog post"
   - ✗ FORBIDDEN: "As a seed-stage company, they likely have 20-50 customers"
   - ✗ FORBIDDEN: "Typical SaaS startups at this stage have around 30 customers"

4. INDUSTRY AVERAGES ARE NOT DATA
   - "Typical SaaS companies charge $99/month" ≠ "This company charges $99/month"
   - Never use "typical", "standard", "usually", "commonly" for THIS company's metrics
   - Only state what you can verify about THIS specific company

5. BE HONEST ABOUT GAPS
   - Investors prefer "Data not available" over guesses
   - Fabricated numbers destroy trust and credibility
   - It is ACCEPTABLE and PROFESSIONAL to acknowledge data gaps

VALIDATION PROCESS:
After you write this section, it will be fact-checked. Every claim will be verified:
- Does this number appear in the research data?
- Does this claim have supporting evidence?
- Is this speculation disguised as fact?

Unsourced metrics trigger automatic section rejection and rewrite.
Honesty about data gaps is REQUIRED, not optional.

DATA AVAILABILITY ASSESSMENT:
Before writing, review the research and mark each question below:

✓ = You have specific data from research to answer this
? = Partial data, can provide limited answer
✗ = No data available, will state "Data not available" or omit

Questions you mark ✗ should result in explicit "Data not available" statements
or be omitted from the section entirely. DO NOT invent data for ✗ questions.

GUIDING QUESTIONS (Only answer if you have evidence from research):
{questions_text}

For EACH question above, you have THREE valid options:
1. ANSWER with specific data from research (preferred - include details)
2. STATE EXPLICITLY "Data not available" (acceptable - be honest)
3. OMIT the question entirely if not relevant (acceptable)

You are FORBIDDEN from:
- Inferring numbers from industry averages
- Speculating based on company stage or size
- Making up pricing, metrics, or financial figures
- Using hedge phrases like "likely", "estimated", "typically", "around"

IF YOU CANNOT VERIFY A CLAIM FROM THE RESEARCH BELOW, DO NOT MAKE THE CLAIM.
{vocab_text}

RESEARCH DATA (summary):
{research_json}

STYLE GUIDE:
{style_guide}

Write ONLY this section's content (no section header, it will be added automatically).
Be specific and analytical, but ONLY use metrics and facts that appear in the research.
When data is unavailable, explicitly state so - this is professional and expected.
Target: {target_length} words (min: {section_def.target_length.min_words}, max: {section_def.target_length.max_words}).

SECTION CONTENT:
"""

    # Retry transient failures. Unlike the polish path there is no prior artifact
    # to fall back to — this branch runs precisely because no research file
    # exists — so exhausting the retries raises, as it did before.
    completion = complete_with_retry(
        user_prompt,
        max_tokens=4000,
        model=_MODEL,
        timeout=_TIMEOUT,
        label=f"write {section_def.name!r}",
    )
    if not completion.ok:
        raise RuntimeError(
            f"Writing section {section_def.name!r} failed: "
            f"{completion.error or 'empty response'} "
            f"(provider={completion.provider})"
        )
    return completion.text.strip()


def writer_agent(state: MemoState) -> Dict[str, Any]:
    """
    Writer Agent implementation - ITERATIVE SECTION-BY-SECTION.

    Writes memo one section at a time using YAML outline guidance.

    Args:
        state: Current memo state containing research data

    Returns:
        Updated state with draft_sections populated
    """
    research = state.get("research")
    if not research:
        raise ValueError("No research data available. Research agent must run first.")

    company_name = state["company_name"]
    investment_type = state.get("investment_type", "direct")
    memo_mode = state.get("memo_mode", "consider")

    # Load outline (with terminal output showing which outline is loaded)
    outline = load_outline_for_state(state)
    frame = state.get("frame")  # run variable; None => unchanged behaviour
    sections_preserved = 0      # skipped by a frame's `prose: unchanged`

    # Load style guide (still used for general writing guidance)
    style_guide = load_style_guide()

    # Get current date
    from datetime import datetime
    current_date = datetime.now().strftime("%B %Y")

    # Get version manager and output directory - firm-aware
    # IMPORTANT: Check for existing output_dir first (set by resume script)
    from ..paths import resolve_deal_context
    from ..artifacts import create_artifact_directory

    firm = state.get("firm")
    safe_name = sanitize_filename(company_name)

    # Check if output_dir already set (e.g., by resume script)
    existing_output_dir = state.get("output_dir")
    if existing_output_dir:
        output_dir = Path(existing_output_dir)
        print(f"   Using existing output directory: {output_dir}")
        # Ensure 2-sections directory exists
        (output_dir / "2-sections").mkdir(parents=True, exist_ok=True)
    elif firm:
        ctx = resolve_deal_context(company_name, firm=firm)
        version_mgr = VersionManager(ctx.outputs_dir.parent if ctx.outputs_dir else Path("output"), firm=firm)
        version = version_mgr.get_next_version(safe_name)
        output_dir = create_artifact_directory(company_name, str(version), firm=firm)
    else:
        version_mgr = VersionManager(Path("output"))
        version = version_mgr.get_next_version(safe_name)
        output_dir = Path("output") / f"{safe_name}-{version}"
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📝 Writing memo sections using outline guidance...")
    print(f"   Outline: {outline.metadata.outline_type} v{outline.metadata.version}")
    if outline.metadata.firm:
        print(f"   Firm: {outline.metadata.firm}")
    print(f"   Sections: {len(outline.sections)}\n")

    # Check for research directory with Perplexity section research
    research_dir = output_dir / "1-research"
    has_section_research = research_dir.exists()

    if has_section_research:
        print(f"   ℹ️  Found section research directory - will polish Perplexity research\n")

    # Write each section iteratively using outline definitions
    total_words = 0
    sections_polished = 0
    sections_written = 0

    # The dataroom is the company's own documents. It has been sitting in state
    # unread: every section was written from web research alone, which is why a
    # memo could report terms as "not disclosed" beside seven executed SAFEs.
    dataroom_analysis = state.get("dataroom_analysis") or {}
    if dataroom_analysis:
        print(f"   📄 Grounding sections in {dataroom_analysis.get('document_count', '?')} "
              f"dataroom documents")

    for section_def in outline.sections:
        section_num = section_def.number
        section_name = section_def.name

        print(f"  [{section_num}/10] {section_name}")
        print(f"      Target: {section_def.target_length.ideal_words} words | Questions: {len(section_def.guiding_questions)}")

        # A frame may declare this section's prose off-limits. This is the ONLY
        # mechanism protecting hand-authored work from a confident regeneration —
        # ProfileHealth's Funding & Terms carries a per-instrument SAFE
        # transcription written by hand, and nothing else would stop the writer
        # replacing it. Guarded on the file existing, because "leave it alone"
        # cannot mean "leave a hole in the memo": if there is nothing to preserve,
        # write it normally.
        if frame is not None:
            directive = frame.directive_for(section_def.filename)
            existing = Path(output_dir) / "2-sections" / section_def.filename
            if directive.prose == "unchanged" and existing.exists():
                print(f"      ⏭  frame '{frame.slug}': prose unchanged — preserving existing section")
                sections_preserved += 1
                continue

        # Check if Perplexity section research exists
        research_filename = section_def.filename.replace(".md", "-research.md")
        research_file = research_dir / research_filename if has_section_research else None

        if research_file and research_file.exists():
            # NEW PATH: Polish Perplexity research with citations
            print(f"      Found research file - polishing with citation preservation...")
            research_content = research_file.read_text()

            section_content = polish_section_research(
                section_def=section_def,
                research_content=research_content,
                company_name=company_name,
                memo_mode=memo_mode,
                style_guide=style_guide,
                dataroom_facts=dataroom_facts_for_section(section_def, dataroom_analysis),
                frame=frame,
                output_dir=output_dir,
            )
            sections_polished += 1
        else:
            # FALLBACK: Write from scratch using general research
            print(f"      No research file - writing from general research...")
            section_content = write_single_section(
                section_def=section_def,
                research=research,
                company_name=company_name,
                investment_type=investment_type,
                memo_mode=memo_mode,
                style_guide=style_guide,
                current_date=current_date,
                dataroom_facts=dataroom_facts_for_section(section_def, dataroom_analysis),
                frame=frame,
                output_dir=output_dir,
            )
            sections_written += 1

        # Save individual section
        save_section_artifact(output_dir, section_num, section_name, section_content)
        word_count = len(section_content.split())
        total_words += word_count

        print(f"      ✓ Saved ({word_count} words)\n")

    # Sections saved - enrichment agents will process files directly
    print(f"✅ All {len(outline.sections)} sections complete using outline: {outline.metadata.outline_type}")
    print(f"   Total words: {total_words}")
    if sections_polished > 0:
        print(f"   Polished from research: {sections_polished} sections")
    if sections_written > 0:
        print(f"   Written from scratch: {sections_written} sections")
    print(f"   Saved to: {output_dir}/2-sections/")
    print(f"   Enrichment agents will process sections individually\n")

    # Return minimal state (enrichment agents load from files)
    return {
        "draft_sections": {},  # Enrichment agents load from files, not state
        "messages": [f"Draft sections completed for {company_name} ({total_words} words total, {sections_polished} polished, {sections_written} written) using outline: {outline.metadata.outline_type}"]
    }

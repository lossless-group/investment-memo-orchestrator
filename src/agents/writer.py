"""
Writer Agent - Drafts investment memo sections following Hypernova format.

This agent is responsible for transforming research data into well-written
memo sections that follow the Hypernova style guide and template structure.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import os
from pathlib import Path
from typing import Dict, Any, Optional

from ..state import MemoState, SectionDraft
from ..artifacts import sanitize_filename, save_section_artifact
from ..versioning import VersionManager
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
    model: ChatAnthropic
) -> str:
    """
    Augment existing section draft with research findings.

    Args:
        section_name: Name of the section being augmented
        existing_draft: Existing draft from deck analysis
        research: Research data
        deck_data: Deck analysis data (for context)
        model: Language model for augmentation

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

    response = model.invoke(prompt)
    return response.content


def polish_section_research(
    section_def: SectionDefinition,
    research_content: str,
    company_name: str,
    memo_mode: str,
    style_guide: str,
    model: ChatAnthropic
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
        model: LLM model

    Returns:
        Polished section content with preserved citations
    """
    import re

    # Count citations before polishing
    citations_before = len(set(re.findall(r'\[\^(\d+)\]', research_content)))

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

    polish_prompt = f"""Rewrite the following Perplexity research into a polished "{section_def.name}" section for {company_name}.

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
- Keep citation format: ". [^1]" (space before bracket, after punctuation)
- Keep ALL citation numbers [^1] through [^{citations_before}]
- DO NOT consolidate or remove "redundant" citations
- DO NOT renumber citations
- If a sentence has multiple citations [^1] [^2], keep ALL of them
- INCLUDE the complete "### Citations" section at the end

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

VALIDATION: Your output will be checked to ensure ALL {citations_before} citations are preserved. If any are missing, the output will be rejected.

Output the polished section content (no section header "## {section_def.number}. {section_def.name}") followed by the complete "### Citations" section.
"""

    # Invoke with retry logic for transient API errors
    import time
    from anthropic import InternalServerError, RateLimitError

    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            response = model.invoke(polish_prompt)
            polished_content = response.content.strip()
            break  # Success, exit retry loop
        except (InternalServerError, RateLimitError) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                print(f"      ⚠️  API error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                print(f"      Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"      ❌ API error after {max_retries} attempts: {e}")
                print(f"      Using original research content without polishing")
                return research_content  # Fallback to original research
        except Exception as e:
            print(f"      ❌ Unexpected error during polishing: {e}")
            print(f"      Using original research content without polishing")
            return research_content  # Fallback to original research

    # Validate citations preserved
    citations_after = len(set(re.findall(r'\[\^(\d+)\]', polished_content)))

    if citations_before != citations_after:
        print(f"      ⚠️  WARNING: Citation mismatch! Before: {citations_before}, After: {citations_after}")
        print(f"      Attempting to use original research content with minimal formatting")
        # Fall back to original research if citations were lost
        return research_content

    # Validate citation list exists
    if "### Citations" not in polished_content:
        print(f"      ⚠️  WARNING: Citation list missing! Using original research")
        return research_content

    return polished_content


def write_single_section(
    section_def: SectionDefinition,
    research: Dict[str, Any],
    company_name: str,
    investment_type: str,
    memo_mode: str,
    style_guide: str,
    model: ChatAnthropic,
    current_date: str
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
        model: LLM model
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

CURRENT DATE: {current_date}
INVESTMENT TYPE: {investment_type.upper()}
{mode_guidance}

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

    # Invoke with retry logic for transient API errors
    import time
    from anthropic import InternalServerError, RateLimitError

    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            response = model.invoke(user_prompt)
            return response.content.strip()
        except (InternalServerError, RateLimitError) as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                print(f"      ⚠️  API error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}")
                print(f"      Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"      ❌ API error after {max_retries} attempts: {e}")
                raise  # Re-raise after all retries exhausted
        except Exception as e:
            print(f"      ❌ Unexpected error during writing: {e}")
            raise  # Re-raise unexpected errors


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

    # Load style guide (still used for general writing guidance)
    style_guide = load_style_guide()

    # Initialize Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0.7,
        max_tokens=4000  # Smaller context per section
    )

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

    for section_def in outline.sections:
        section_num = section_def.number
        section_name = section_def.name

        print(f"  [{section_num}/10] {section_name}")
        print(f"      Target: {section_def.target_length.ideal_words} words | Questions: {len(section_def.guiding_questions)}")

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
                model=model
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
                model=model,
                current_date=current_date
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

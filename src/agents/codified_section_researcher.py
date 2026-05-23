"""
Codified Section Researcher Agent.

When the analyst has hand-curated `deals/<deal>/inputs/Sources.md` with
`mode: codified`, this agent replaces the broad-search per-section
researcher entirely. Each curated URL is fetched (via Jina Reader, with
httpx fallback) and the content is grouped per section based on the
analyst's `sections: [...]` tags, then written to `1-research/<NN-slug>-research.md`
in the same shape the Perplexity researcher would have produced — so
downstream writer/enrichment agents work without modification.

The premise (from
`memopop-ai/context-v/explorations/Human-Curated-Source-Sets-and-Per-Firm-RAG-for-Memo-Narrative.md`):
the analyst ranks/prunes sources up-front; the pipeline doesn't waste
budget on broad search and doesn't introduce LLM-fabricated URLs at the
research layer.

When ANTHROPIC_API_KEY is present, the agent additionally invokes Claude
to synthesize per-section research notes with proper [^N] citations
from the curated content — matching the Perplexity output format. When
absent (or by `mode: codified-raw`), the agent writes the raw fetched
content with a citation list footer; the writer downstream then does
more synthesis work.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state import MemoState
from ..outline_loader import load_outline_for_state
from ..curation import (
    SourceEntry,
    SourcesMd,
    is_codified,
    load_sources_md,
    sources_for_section,
    fetch_url_markdown,
)


def find_deal_inputs_dir(state: Dict[str, Any]) -> Optional[Path]:
    """
    Resolve the deal's inputs directory based on state.

    Convention: `io/<firm>/deals/<company_name>/inputs/`. When no firm is
    set, fall back to the legacy `data/` location at the orchestrator root.
    """
    firm = state.get("firm") or ""
    company_name = state.get("company_name") or ""
    if not company_name:
        return None

    if firm:
        return Path("io") / firm / "deals" / company_name / "inputs"
    # Legacy non-firm-scoped layout (kept for back-compat).
    return Path("data")


def codified_section_researcher_agent(state: MemoState) -> Optional[Dict[str, Any]]:
    """
    If `Sources.md` is present and `mode: codified`, fetch every curated
    URL, write per-section research files, and short-circuit the rest of
    the per-section research pipeline by returning a state update. If
    Sources.md is absent or not in codified mode, returns None so the
    workflow continues with the broad-search researcher.

    Returns:
        State update dict if codified mode applied; None otherwise.
    """
    inputs_dir = find_deal_inputs_dir(state)
    if not inputs_dir:
        return None

    sources_md = load_sources_md(inputs_dir)
    if not is_codified(sources_md):
        return None

    print(
        f"📚 Codified-source mode active — "
        f"{len(sources_md.sources)} hand-curated URLs from {sources_md.source_path}"
    )

    outline = load_outline_for_state(state)

    from ..utils import get_output_dir_from_state
    output_dir = get_output_dir_from_state(state)
    research_dir = output_dir / "1-research"
    research_dir.mkdir(exist_ok=True)

    # Fetch every unique URL once; cache by URL so multi-section sources
    # don't get refetched.
    fetched: Dict[str, Dict[str, Any]] = {}
    for entry in sources_md.sources:
        if entry.url in fetched:
            continue
        print(f"  Fetching {entry.url[:90]}")
        result = fetch_url_markdown(entry.url)
        if result:
            fetched[entry.url] = result
            print(f"    ✓ {len(result.get('markdown', ''))} chars via {result.get('via')}")
        else:
            print(f"    ⚠️  fetch failed (no content)")

    # Per-section research file generation.
    use_llm = bool(os.environ.get("ANTHROPIC_API_KEY")) and sources_md.mode == "codified"
    if use_llm:
        synthesize = _synthesize_via_claude
    else:
        synthesize = _synthesize_raw

    sections_written = 0
    sections_with_no_sources: List[str] = []
    for idx, section in enumerate(outline.sections, start=1):
        section_name = getattr(section, "name", f"Section {idx}")
        matching = sources_for_section(sources_md, section_name, section_number=idx)
        if not matching:
            sections_with_no_sources.append(section_name)
            _write_section_stub(research_dir, idx, section_name)
            continue

        # Only pass entries whose URL actually fetched cleanly.
        usable = [e for e in matching if e.url in fetched]
        if not usable:
            sections_with_no_sources.append(section_name)
            _write_section_stub(
                research_dir, idx, section_name,
                reason="curated sources tagged but all fetches failed",
            )
            continue

        synthesize(research_dir, idx, section, usable, fetched, state)
        sections_written += 1
        print(f"    ✓ wrote {idx:02d}-{_slugify(section_name)}-research.md ({len(usable)} sources)")

    print(
        f"\n✓ Codified research complete: {sections_written}/{len(outline.sections)} "
        f"sections populated from {len(fetched)} fetched URLs"
    )
    if sections_with_no_sources:
        print(
            f"  ⚠️  No curated sources for: {', '.join(sections_with_no_sources)} — "
            f"these sections will have <needs-source> markers downstream."
        )

    return {
        "messages": [
            f"Codified research: {sections_written} sections from "
            f"{len(sources_md.sources)} curated sources ({len(fetched)} fetched cleanly)"
        ],
    }


# ─────────────────────────────────────────────────────────────────
# Per-section synthesis paths
# ─────────────────────────────────────────────────────────────────


def _synthesize_raw(
    research_dir: Path,
    idx: int,
    section: Any,
    matching: List[SourceEntry],
    fetched: Dict[str, Dict[str, Any]],
    state: MemoState,
) -> None:
    """
    No-LLM synthesis: dump fetched content with a citation footer in
    Perplexity-compatible format. Writer downstream picks up from here.
    """
    section_name = getattr(section, "name", f"Section {idx}")
    lines: List[str] = []
    lines.append(f"# {section_name} — Research")
    lines.append("")
    lines.append(
        f"_Codified-source research. Sources hand-curated from "
        f"`inputs/Sources.md`. No broad web search was performed for this section._"
    )
    lines.append("")

    citation_entries: List[str] = []
    for n, entry in enumerate(matching, start=1):
        doc = fetched.get(entry.url) or {}
        title = doc.get("title") or entry.url
        markdown = doc.get("markdown") or ""
        # Cap per-source excerpt so the file stays scannable. Writer can
        # always re-fetch from the URL if it needs more.
        excerpt = markdown[:8000]

        lines.append(f"## Source [^{n}]: {title}")
        lines.append("")
        if entry.note:
            lines.append(f"*Analyst note: {entry.note}*")
            lines.append("")
        lines.append(excerpt.strip())
        lines.append("")

        # Citation footer line in the canonical format.
        citation_entries.append(
            f"[^{n}]: [{title}]({entry.url}). Published: N/A | Updated: N/A"
        )

    lines.append("")
    lines.append("### Citations")
    lines.append("")
    lines.extend(citation_entries)
    lines.append("")

    section_filename = f"{idx:02d}-{_slugify(section_name)}-research.md"
    (research_dir / section_filename).write_text("\n".join(lines))


def _synthesize_via_claude(
    research_dir: Path,
    idx: int,
    section: Any,
    matching: List[SourceEntry],
    fetched: Dict[str, Dict[str, Any]],
    state: MemoState,
) -> None:
    """
    LLM-synthesis path: feed the curated content to Claude with strict
    instructions to cite by [^N] references that map to the provided
    sources only. Produces a research file in the same shape Perplexity
    would have written.
    """
    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError:
        # Fall back gracefully if langchain isn't available.
        return _synthesize_raw(research_dir, idx, section, matching, fetched, state)

    section_name = getattr(section, "name", f"Section {idx}")
    guiding_questions = getattr(section, "guiding_questions", []) or []
    guidance = "\n".join(f"- {q}" for q in guiding_questions) or "(no explicit guiding questions — synthesize whatever the sources support)"

    sources_block_lines: List[str] = []
    for n, entry in enumerate(matching, start=1):
        doc = fetched.get(entry.url) or {}
        title = doc.get("title") or entry.url
        excerpt = (doc.get("markdown") or "")[:8000]
        sources_block_lines.append(
            f"\n### Source [^{n}]: {title}\n"
            f"URL: {entry.url}\n"
            f"Rank: {entry.rank}\n"
            f"Note: {entry.note or '(none)'}\n\n"
            f"{excerpt}\n"
        )
    sources_block = "\n".join(sources_block_lines)

    system_prompt = (
        "You are a research analyst writing one section of the research notes "
        "for an investment memo. You will be given a section name, guiding "
        "questions, and a CURATED set of sources (hand-picked by the analyst; "
        "treat them as trusted).\n\n"
        "Your job:\n"
        "- Synthesize the sources to address the guiding questions.\n"
        "- Cite EVERY factual claim using Obsidian-style footnotes — [^1], [^2], etc.\n"
        "- Output: markdown body with inline [^N] citations, followed by a\n"
        "  '### Citations' section listing each source in this exact format:\n"
        "  `[^N]: YYYY, MMM DD. [Title](URL). Publisher. Published: YYYY-MM-DD | Updated: N/A`\n\n"
        "Hard rules:\n"
        "- ONLY cite the sources provided. Never invent URLs.\n"
        "- The [^N] you use must match the source number above.\n"
        "- If a guiding question isn't addressed by any source, do not write about it — "
        "  emit an inline `<needs-source claim=\"...\" />` marker instead.\n"
        "- Be specific (numbers, dates, names) where the sources support it; otherwise stay general."
    )

    user_prompt = (
        f"Section: {section_name}\n\n"
        f"Guiding questions:\n{guidance}\n\n"
        f"Curated sources for this section:\n{sources_block}\n\n"
        f"Write the research notes for this section now."
    )

    try:
        llm = ChatAnthropic(
            model=os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
            max_tokens=4000,
        )
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        print(f"    ⚠️  Claude synthesis failed: {e}; falling back to raw dump")
        return _synthesize_raw(research_dir, idx, section, matching, fetched, state)

    section_filename = f"{idx:02d}-{_slugify(section_name)}-research.md"
    (research_dir / section_filename).write_text(content)


def _write_section_stub(
    research_dir: Path,
    idx: int,
    section_name: str,
    reason: str = "no curated sources tagged for this section",
) -> None:
    """When a section has no curated sources, write a minimal placeholder."""
    section_filename = f"{idx:02d}-{_slugify(section_name)}-research.md"
    body = (
        f"# {section_name} — Research\n"
        f"\n"
        f"_Codified-source mode: {reason}._\n"
        f"\n"
        f"<needs-source claim=\"{section_name} section has no curated sources\" />\n"
    )
    (research_dir / section_filename).write_text(body)


def _slugify(s: str) -> str:
    """Section-name → filename slug: lower-kebab-case, alphanumerics + hyphens only."""
    s = (s or "").strip().lower()
    s = re.sub(r"&", "and", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "section"

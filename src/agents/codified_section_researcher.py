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

    # ── The durable foundation ──────────────────────────────────────────────
    # Fetched content and extracts live in inputs/sources/*.md, NOT in
    # outputs/<version>/. That makes them version-independent by construction:
    # generating v0.0.3 to reshape prose must not re-pay for reading the same
    # 28 documents. Only sources missing content get fetched.
    #
    # `--fresh` forces a re-read; otherwise a source whose file already carries
    # a body is reused as-is.
    fetched: Dict[str, Dict[str, Any]] = {}
    reused = 0
    _force = bool(state.get("fresh"))
    _inputs_dir = find_deal_inputs_dir(state)

    if _inputs_dir and not _force:
        from ..curation.source_file import read_source_file, resolve_path, sources_dir
        from ..curation.extracts import split_body
        _sdir = sources_dir(Path(_inputs_dir))
        if _sdir.exists():
            _on_disk = {}
            for _p in _sdir.glob("*.md"):
                _sf = read_source_file(_p)
                if not _sf:
                    continue
                _content, _ = split_body(_sf.body or "")
                if _content.strip():
                    _on_disk[_sf.url] = _content
            for entry in sources_md.sources:
                body = _on_disk.get(entry.url)
                if body:
                    fetched[entry.url] = {
                        "url": entry.url, "title": entry.title or entry.url,
                        "markdown": body, "via": "source-file",
                    }
                    reused += 1
    if reused:
        print(f"  ♻️  Reusing stored content for {reused} source(s) "
              f"— foundation already on file")

    for entry in sources_md.sources:
        if entry.url in fetched:
            continue
        print(f"  Fetching {entry.url[:90]}")
        result = fetch_url_markdown(entry.url)

        # A source can be approved AND unreachable: McKinsey, Reuters and the
        # NYT all refuse bots. When the analyst has staged a local copy, read
        # that instead of giving up — otherwise downloading the document
        # accomplishes nothing and the memo silently loses a vouched-for source.
        if not result and entry.local_path:
            from ..curation.fetch import fetch_local_file
            candidate = Path(entry.local_path)
            if not candidate.is_absolute():
                base = find_deal_inputs_dir(state)
                if base:
                    candidate = Path(base).parent / entry.local_path
            result = fetch_local_file(candidate, url=entry.url)
            if result:
                print(f"    ↪ URL unreachable — using staged local copy")

        if result:
            fetched[entry.url] = result
            print(f"    ✓ {len(result.get('markdown', ''))} chars via {result.get('via')}")
        else:
            print(f"    ⚠️  fetch failed (no content)")

    # Persist newly-fetched content into each source's own file so the next run
    # reuses it, then extract. Extraction is skipped for sources that already
    # carry an # Extracts section — reading is expensive and the result does not
    # change unless the content does.
    if _inputs_dir:
        try:
            _persist_and_extract(Path(_inputs_dir), sources_md, fetched, force=_force)
        except Exception as exc:  # noqa: BLE001 - never break a run over this
            print(f"  ⚠️  extraction step skipped: {exc}")

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



def _persist_and_extract(inputs_dir: Path, sources_md, fetched: Dict[str, Any],
                         *, force: bool = False) -> None:
    """Store fetched bodies on the source files, then extract what is missing.

    Both halves are idempotent. Content already stored is not re-fetched;
    extracts already present are not re-derived. This is what makes generating
    another memo version a prose-shaping operation rather than a re-read of the
    entire corpus.
    """
    from ..curation.extracts import EXTRACTS_HEADING, split_body
    from ..curation.source_file import (
        from_entry, read_source_file, resolve_path, write_source_file,
    )

    # Index existing files by normalized_url, NEVER by filename. The canonical
    # filename embeds a date, so `from_entry` generates today's name while the
    # file on disk carries the date it was captured — across a midnight boundary
    # that silently writes a duplicate for every source. normalized_url is the
    # actual identity of a source, and the same key the SurrealDB registry uses
    # as its UNIQUE constraint.
    from ..curation.best_sources import canonical_url
    from ..curation.source_file import sources_dir as _sdir_fn

    by_url = {}
    _sdir = _sdir_fn(inputs_dir)
    if _sdir.exists():
        for _p in _sdir.glob("*.md"):
            _existing = read_source_file(_p)
            if _existing and _existing.url:
                by_url[canonical_url(_existing.url)] = _existing

    wrote = 0
    for entry in sources_md.sources:
        doc = fetched.get(entry.url)
        if not doc or doc.get("via") == "source-file":
            continue
        sf = by_url.get(canonical_url(entry.url)) or from_entry(entry)
        _, existing_extracts = split_body(sf.body or "")
        body = doc.get("markdown") or ""
        sf.body = f"{body.rstrip()}\n\n{existing_extracts}".strip() if existing_extracts else body
        sf.content_pulled = True
        if not sf.title:
            sf.title = doc.get("title") or ""
        try:
            write_source_file(inputs_dir, sf)
            wrote += 1
        except Exception:  # noqa: BLE001
            continue
    if wrote:
        print(f"  💾 Stored fetched content on {wrote} source file(s)")

    # Extract only where there is content and no extracts yet.
    from ..curation.source_file import sources_dir
    sdir = sources_dir(inputs_dir)
    if not sdir.exists():
        return
    pending = 0
    for p in sdir.glob("*.md"):
        sf = read_source_file(p)
        if not sf:
            continue
        content, extracts = split_body(sf.body or "")
        if content.strip() and (force or not extracts.strip()):
            pending += 1
    if not pending:
        print("  ♻️  Extracts already on file for every source with content")
        return

    from .source_extractor import extract_for_deal
    extract_for_deal(inputs_dir, skip_existing=not force)


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
        f"- USE EVERY SOURCE. All {len(matching)} sources above must be cited at "
        "least once. A source the analyst approved and you ignored is a failure "
        "of this task, not an editorial choice.\n"
        "- READ the source text provided. Do NOT answer from memory. If you did "
        "not read it in the text above, you do not know it.\n"
        "- For each source, extract something SPECIFIC and verbatim-traceable: a "
        "figure, a date, a named entity, or a short direct quotation that appears "
        "word-for-word in that source's text above.\n"
        "- NEVER attribute a quote or figure to a source unless that exact string "
        "appears in that source's text above. Fabricating evidence of having read "
        "a source is the single worst failure mode here, and it is checked "
        "mechanically after you respond.\n"
        "- If a source does not bear on the guiding questions, still capture its "
        "distinct contribution in one line under an '### Additional context' "
        "heading at the end, cited to it. Do not silently drop it.\n"
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

    # Marker -> fetched text, for grounding verification. The source text is
    # already in memory here; checking a quoted span against it costs nothing.
    _source_text = {
        str(n): (fetched.get(e.url) or {}).get("markdown", "")
        for n, e in enumerate(matching, start=1)
    }
    _all_markers = [str(n) for n in range(1, len(matching) + 1)]

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

        # ── Enforcement: a rule with no validation is a suggestion. ──────────
        # The writer agent already proves this pattern works: state the count,
        # state that it is checked, then actually check it.
        from ..grounding import uncited_sources, verify

        skipped = uncited_sources(content, _all_markers)
        report = verify(content, _source_text)
        fabricated = report["unsupported"]

        if skipped or fabricated:
            problems = []
            if skipped:
                problems.append(
                    "You did not cite these sources at all: "
                    + ", ".join(f"[^{m}]" for m in skipped)
                    + ". Read each one in the text above and add at least one "
                    "specific, verbatim-traceable point from it."
                )
            if fabricated:
                bullets = "\n".join(
                    f'  - {f["kind"]} "{f["value"][:90]}" attributed to '
                    f'{", ".join("[^" + m + "]" for m in f["checked"])} '
                    f"— that string does not appear in those sources"
                    for f in fabricated[:8]
                )
                problems.append(
                    "These quotes/figures do NOT appear in the sources you "
                    f"attributed them to:\n{bullets}\n"
                    "Remove them, or replace each with an actual span from the "
                    "source text above. Do not restate them from memory."
                )
            print(f"      \u21ba Re-prompting: {len(skipped)} source(s) unused, "
                  f"{len(fabricated)} ungrounded claim(s)")
            retry = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
                *( [] ),
                HumanMessage(content=(
                    "Your draft failed validation.\n\n"
                    + "\n\n".join(problems)
                    + "\n\nRewrite the research notes now, fixing both issues. "
                      "Keep everything that was correct."
                )),
            ])
            retry_content = retry.content if hasattr(retry, "content") else str(retry)
            retry_skipped = uncited_sources(retry_content, _all_markers)
            retry_report = verify(retry_content, _source_text)
            # Accept the retry only if it is strictly better on both axes.
            if (len(retry_skipped) <= len(skipped)
                    and len(retry_report["unsupported"]) <= len(fabricated)):
                content = retry_content
                skipped, report = retry_skipped, retry_report
                fabricated = retry_report["unsupported"]

        coverage = len(_all_markers) - len(skipped)
        print(f"      \U0001f4d0 Grounding: {coverage}/{len(_all_markers)} sources used, "
              f"{len(report['supported'])}/{report['checked']} evidence spans verified"
              + (f", {len(fabricated)} UNGROUNDED" if fabricated else ""))
        for f in fabricated[:3]:
            print(f'         \u26a0\ufe0f  ungrounded {f["kind"]}: "{f["value"][:70]}"')
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

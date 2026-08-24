"""
Slide Stenographer

Transcribes a deck one slide at a time into per-slide markdown documents.

Additive to ``src/agents/deck_analyst.py``, which is untouched. That agent reads
a deck at deck level and emits the memo-shaped JSON the MemoPop workflow depends
on; it batches five slides per call and merges the results, which is efficient
for its purpose and destroys slide identity in the process. This one keeps the
slide as the unit: one render, one call, one document.

**The order of operations is the editorial position.** Text is extracted first
and handed to the model alongside the image, because a PDF's own text layer is a
more faithful record of a heading than any transcription of a picture of that
heading. Vision reads what the text layer cannot: layout, charts, which people
have photographs, what a diagram depicts. Where they disagree the text layer
wins, and the disagreement is recorded rather than resolved silently.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv

from .date_resolution import resolve_deck_date, sibling_dates_for
from .deck_lineage import (
    reveal_map,
    content_hash,
    deck_slug,
    detect_reveal_sequences,
    lineage_id,
    slide_filename,
    title_of,
)
from .slide_cdn import upload_slides
from .slide_markdown import (
    extract_user_commentary,
    render_deck_manifest,
    render_slide_markdown,
)
from .slide_schemas import (
    is_valid_slide_type,
    layout_prompt_block,
    rank_slide_types,
    schema_is_generic,
    schemas_prompt_block,
    slide_type_prompt_block,
    validate_slide_record,
)

AGENT_SIGNATURE = "Claude Code on Opus 5 with Claude Vision"

# 150 DPI matches what the existing screenshot path already uses. The deck
# analyst's vision pass renders at 0.5x, which is fine for gist and marginal for
# the verbatim fidelity this agent promises.
RENDER_DPI = 150
RENDER_MAX_WIDTH = 1600


# =============================================================================
# Entry point
# =============================================================================

def transcribe_deck(
    deck_path: str | Path,
    company: str,
    output_root: str | Path,
    *,
    round_name: str = "Unknown",
    deck_variant: str = "company",
    deck_version: int = 1,
    authored_by: str = "company",
    date_received: Optional[str] = None,
    upload_to_cdn: bool = True,
    cdn_repo: str = "example-firm/portfolio",
    use_vision: bool = True,
    max_slides: Optional[int] = None,
    dry_run: bool = False,
    resume: bool = True,
) -> Dict[str, Any]:
    """
    Transcribe one deck into per-slide markdown.

    Args:
        deck_path: PDF or PPTX to read.
        company: Portfolio company name.
        output_root: Directory under which the deck folder is created.
        round_name: Financing round, used in the folder name and lineage keys.
        deck_variant: ``company`` for the company's own deck, or the fork's name
            (``SPV``, ``reading``, ``board``).
        authored_by: ``company`` or ``firm``. Decides whether the slide's claims
            belong in a fact-check queue.
        upload_to_cdn: Mirror rendered slides to ImageKit.
        use_vision: Send images to the model. With this off, documents are built
            from the text layer alone — cheap, and useful for checking structure
            before spending on a full pass.
        max_slides: Stop after this many slides.
        dry_run: Render and assemble without uploading or writing.
        resume: Skip slides whose document already exists. On by default, so an
            interrupted run continues rather than repaying for finished work.
            Pass False to re-transcribe a deck from scratch.

    Returns:
        Summary dict with the output directory, per-slide records, and warnings.
    """
    deck = Path(deck_path)
    if not deck.exists():
        raise FileNotFoundError(f"deck not found: {deck}")

    print(f"\n{'=' * 62}\nSLIDE STENOGRAPHER\n{'=' * 62}")
    print(f"Deck:    {deck.name}\nCompany: {company}  ({round_name}, {deck_variant} v{deck_version})")

    pages = _read_pages(deck)
    print(f"Pages:   {len(pages)}")

    dates = _resolve_dates(deck, pages)
    print(f"Dated:   {dates.date_on_deck} via {dates.date_source} ({dates.date_confidence})")
    for note in dates.notes:
        print(f"         ⚠️  {note}")

    slug = deck_slug(company, round_name, dates.date_on_deck, deck_version,
                     None if deck_variant == "company" else deck_variant)
    out_dir = Path(output_root) / company.replace(" ", "-") / slug
    images_dir = out_dir / "slides"
    print(f"Output:  {out_dir}")

    reveals = reveal_map(pages)
    groups = detect_reveal_sequences(pages)
    if groups:
        confirmed = sum(1 for g in groups if g.confirmed)
        collapsed = sum(g.size - 1 for g in groups)
        print(f"Reveals: {len(groups)} group(s), {confirmed} confirmed by text — "
              f"{len(pages)} pages cover {len(pages) - collapsed} logical slides")

    if not dry_run:
        images_dir.mkdir(parents=True, exist_ok=True)

    # --- render ---
    print(f"\nRendering at {RENDER_DPI}dpi…")
    rendered = _render_pages(deck, images_dir, len(pages), dry_run=dry_run)

    # --- transcribe ---
    limit = min(max_slides or len(pages), len(pages))
    records: List[Dict[str, Any]] = []
    today = date.today().isoformat()
    reused = 0

    for index in range(1, limit + 1):
        page_text = pages[index - 1]
        image_path = rendered.get(index)
        position, total, canonical, confirmed = reveals.get(index, (None, None, True, True))

        # Resume. A Vision call per slide is the expensive part of this agent, and
        # an interrupted run used to lose every call because nothing was written
        # until the whole deck finished. Completed slides are now on disk and are
        # skipped, so a re-run costs only what it did not already do.
        if resume and not dry_run:
            done = _existing_slide(out_dir, index)
            if done is not None:
                print(f"  [{index:>2}/{limit}] already transcribed — skipping")
                records.append(done)
                reused += 1
                continue

        print(f"  [{index:>2}/{limit}] transcribing…", end=" ", flush=True)
        transcribed = _transcribe_slide(
            page_text=page_text,
            image_path=image_path,
            index=index,
            page_count=len(pages),
            company=company,
            use_vision=use_vision,
            reveal_hint=(position, total) if position else None,
        )

        record = _assemble(
            transcribed=transcribed,
            index=index,
            page_count=len(pages),
            page_text=page_text,
            company=company,
            round_name=round_name,
            slug=slug,
            deck=deck,
            deck_variant=deck_variant,
            deck_version=deck_version,
            authored_by=authored_by,
            dates=dates,
            date_received=date_received,
            today=today,
            image_path=image_path,
            out_dir=out_dir,
            reveal=(position, total, canonical, confirmed) if position else None,
        )
        if not dry_run:
            _write_slide(out_dir, record)
        if not dry_run and record.get("_proposed_type"):
            from .slide_schemas import PROPOSALS_FILENAME, propose_slide_type

            propose_slide_type(
                Path(output_root) / PROPOSALS_FILENAME,
                record["slide_type"],
                record["_proposed_type"],
                record["slide_uid"],
                today,
            )
            print(f"NEW TYPE proposed: {record['slide_type']}")

        records.append(record)
        print(f"{record['slide_type']}")

    # --- CDN ---
    if upload_to_cdn and not dry_run:
        print("\nUploading slide images…")
        urls = upload_slides(
            [{"index": r["index_number"], "path": r["_image_abs"],
              "slide_type": r["slide_type"], "alt": r.get("slide_image_alt", "")}
             for r in records
             if r.get("_image_abs") and not r.get("slide_image_cdn")],
            company=company, deck_slug=slug, repo=cdn_repo,
        )
        for record in records:
            if record["index_number"] in urls:
                if record.get("slide_image_cdn") != urls[record["index_number"]]:
                    record["_cdn_added"] = True
                record["slide_image_cdn"] = urls[record["index_number"]]
        print(f"   {len(urls)} uploaded")

    # --- write ---
    # Slide documents were written as they were transcribed; only the CDN URLs
    # and the deck manifest remain.
    warnings: List[str] = []
    if not dry_run:
        for record in records:
            # A reused slide is already complete on disk. Rewriting it from the
            # resumed record would destroy everything the record does not carry
            # — the resume path reads frontmatter only, so a rewrite replaced
            # the transcribed json-content with {} and silently threw away the
            # slide. Only write what this run produced, or what gained a URL.
            if record.get("_resumed") and not record.get("_cdn_added"):
                continue
            _write_slide(out_dir, record)
        _write_manifest(out_dir, records, company, round_name, slug, deck,
                        deck_variant, deck_version, authored_by, dates, groups, today)

    for record in records:
        if record.get("_resumed"):
            continue   # already validated when it was written
        for problem in validate_slide_record(record):
            warnings.append(f"slide {record['index_number']}: {problem}")

    print(f"\n{'=' * 62}")
    print(f"✓ {len(records)} slide document(s) → {out_dir}")
    if reused:
        print(f"  {reused} reused from a previous run, {len(records) - reused} transcribed now")
    if warnings:
        print(f"⚠️  {len(warnings)} validation warning(s)")
        for w in warnings[:10]:
            print(f"   - {w}")
    print(f"{'=' * 62}\n")

    return {
        "output_dir": str(out_dir),
        "deck_slug": slug,
        "slides": records,
        "warnings": warnings,
        "dates": dates.as_frontmatter(),
    }


# =============================================================================
# Reading and rendering
# =============================================================================

def _read_pages(deck: Path) -> List[str]:
    """Per-page text, in order. The text layer is the fidelity baseline."""
    suffix = deck.suffix.lower()

    if suffix == ".pdf":
        import pymupdf

        doc = pymupdf.open(str(deck))
        if doc.needs_pass:
            from ..dataroom.document_text import _try_passwords

            if _try_passwords(doc, deck) is None:
                doc.close()
                raise ValueError(f"{deck.name} is password protected and no password was recoverable")
        pages = [page.get_text("text").strip() for page in doc]
        doc.close()
        return pages

    if suffix == ".pptx":
        from ..dataroom.document_text import extract_text

        text = extract_text(deck).text
        return [s.strip() for s in re.split(r"=== SLIDE \d+ ===", text) if s.strip()]

    raise ValueError(f"unsupported deck format: {suffix}")


def _resolve_dates(deck: Path, pages: Sequence[str]):
    """Date the deck from its own content first, the filesystem last."""
    metadata: Dict[str, Any] = {}
    if deck.suffix.lower() == ".pdf":
        import pymupdf

        doc = pymupdf.open(str(deck))
        if doc.needs_pass:
            from ..dataroom.document_text import _try_passwords

            _try_passwords(doc, deck)
        metadata = doc.metadata or {}
        doc.close()

    # Opening slides carry the deck's own date; the closing slide often repeats
    # it in a footer.
    head = "\n".join(pages[:3])
    tail = pages[-1] if len(pages) > 1 else ""

    return resolve_deck_date(
        first_slides_text=f"{head}\n{tail}",
        pdf_title=metadata.get("title"),
        pdf_creation_date=metadata.get("creationDate"),
        filename=deck.name,
        file_mtime=datetime.fromtimestamp(deck.stat().st_mtime).date(),
        sibling_dates=sibling_dates_for(deck),
    )


def _render_pages(deck: Path, images_dir: Path, page_count: int,
                  dry_run: bool = False) -> Dict[int, Path]:
    """Render each page to JPEG. PPTX decks have no renderable pages here."""
    if deck.suffix.lower() != ".pdf" or dry_run:
        return {}

    import pymupdf
    from PIL import Image

    rendered: Dict[int, Path] = {}
    doc = pymupdf.open(str(deck))
    if doc.needs_pass:
        from ..dataroom.document_text import _try_passwords

        _try_passwords(doc, deck)

    scale = RENDER_DPI / 72.0
    for index in range(1, page_count + 1):
        target = images_dir / f"{index:02d}.jpg"
        try:
            pix = doc[index - 1].get_pixmap(matrix=pymupdf.Matrix(scale, scale))
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            if image.width > RENDER_MAX_WIDTH:
                ratio = RENDER_MAX_WIDTH / image.width
                image = image.resize(
                    (RENDER_MAX_WIDTH, int(image.height * ratio)), Image.Resampling.LANCZOS
                )
            image.save(target, "JPEG", quality=88, optimize=True)
            rendered[index] = target
        except Exception as e:
            print(f"   ⚠️  page {index} did not render: {type(e).__name__}: {e}")

    doc.close()
    return rendered


# =============================================================================
# Transcription
# =============================================================================

def _transcribe_slide(
    *,
    page_text: str,
    image_path: Optional[Path],
    index: int,
    page_count: int,
    company: str,
    use_vision: bool,
    reveal_hint: Optional[tuple],
) -> Dict[str, Any]:
    """One slide, one model call. Returns the parsed payload, or a stub on failure."""
    prompt = _build_prompt(page_text, index, page_count, company, reveal_hint,
                           has_image=bool(image_path) and use_vision)

    content: List[Dict[str, Any]] = []
    if use_vision and image_path and image_path.exists():
        import base64

        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(image_path.read_bytes()).decode("utf-8"),
            },
        })
    content.append({"type": "text", "text": prompt})

    try:
        from anthropic import Anthropic

        # The rest of the pipeline loads .env at entry; this agent can be called
        # directly, so it loads its own. Without it the only symptom was every
        # slide falling back to the text-layer stub with an auth error buried in
        # its warnings.
        load_dotenv()

        response = Anthropic().messages.create(
            model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
            max_tokens=8000,   # long team and operating-model slides truncate at 4k
            temperature=0,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return _stub(page_text, "model returned no JSON")
        return json.loads(match.group())
    except Exception as e:
        return _stub(page_text, f"transcription failed: {type(e).__name__}: {e}")


def _stub(page_text: str, reason: str) -> Dict[str, Any]:
    """
    Fallback record built from the text layer alone.

    A failed model call must still leave a usable document — the text layer is
    real evidence, and losing it because an API call failed would be worse than
    a thin file that says why it is thin.
    """
    lines = [line.strip() for line in (page_text or "").splitlines() if line.strip()]
    return {
        "slide_type": "other",
        "core_message": "",
        "tags": [],
        "layout_rows": 1,
        "layout_pattern": "single",
        "layout_description": [{"label": "Whole slide", "summary": "Untranscribed region",
                                "headingTxt": lines[0] if lines else None}],
        "transcription_fidelity": "partial",
        "content": {
            "titleRow": {"titleTxt": lines[0] if lines else None,
                         "subtitleTxt": lines[1] if len(lines) > 1 else None,
                         "eyebrowTxt": None},
            "regions": [{"regionLabel": "whole slide", "elementType": "text",
                         "textLines": lines, "tableRows": None, "description": None}],
        },
        "metrics": {},
        "claims_to_verify": [],
        "slide_image_alt": "",
        "analyst_commentary": "",
        "_warnings": [reason],
    }


def _build_prompt(page_text: str, index: int, page_count: int, company: str,
                  reveal_hint: Optional[tuple], has_image: bool) -> str:
    """
    The transcription instruction.

    Two things it insists on. Verbatim means verbatim — the deck is the source of
    truth and a tidied heading is a corrupted record. And the text layer, where
    present, outranks what the model reads off the pixels.
    """
    # Shortlist likely types from the text layer so the prompt can carry their
    # actual schemas. Sending all 25 would cost more than the slide; sending
    # only the generic one leaves the model guessing at the typed shape.
    shortlist = rank_slide_types(page_text)

    reveal_note = ""
    if reveal_hint:
        position, total = reveal_hint
        reveal_note = (
            f"\nThis page appears to be state {position} of {total} in an animation "
            f"reveal — consecutive pages share its heading. Say so in "
            f"`is_animation_reveal` if the image confirms it.\n"
        )

    text_note = (
        "\nTEXT LAYER (extracted directly from the file — authoritative for "
        "wording and spelling; prefer it over your reading of the image wherever "
        "the two disagree):\n---\n" + (page_text or "[no text layer]") + "\n---\n"
    )

    image_note = (
        "You are looking at a rendered image of the slide. Use it for layout, "
        "charts, diagrams, photographs, and anything the text layer cannot carry.\n"
        if has_image else
        "No image is available; work from the text layer alone and set "
        "`transcription_fidelity` to \"partial\".\n"
    )

    return f"""You are a stenographer transcribing slide {index} of {page_count} from
{company}'s deck. Your job is a faithful record, not a summary.

{image_note}{text_note}{reveal_note}
RULES
1. Transcribe VERBATIM. Copy headings, labels, and body text exactly as written,
   including capitalization, punctuation, and any typos. Never tidy, paraphrase,
   expand an abbreviation, or fix a spelling.
2. Report only what is on this slide. Never infer from what a deck like this
   usually contains. Use null for anything absent.
3. If text is unreadable, set `transcription_fidelity` to "partial" or
   "illegible" and note what you could not read.

SLIDE TYPES — choose one. This vocabulary exists to keep a corpus coherent, not
to constrain what a slide is allowed to be. Prefer an existing type; they are
what makes "show me every team slide" work. But if this slide genuinely does
something none of them names, coin a new lower_snake_case type and explain why
in `new_type_rationale`. Do not force a poor fit, and do not reach for "other"
when you can name the thing.
{slide_type_prompt_block()}

LAYOUT PATTERNS — choose exactly one:
{layout_prompt_block()}

Return ONLY this JSON:
{{
  "slide_type": "<a type from the list, or a new lower_snake_case one>",
  "new_type_rationale": "<null, or why no existing type fit>",
  "core_message": "<one sentence: the single point this slide makes. Your words.>",
  "tags": ["<2-4 Title-Case topic tags>"],
  "layout_rows": <integer count of horizontal bands>,
  "layout_pattern": "<one pattern from the list>",
  "layout_description": [
    {{"label": "<short name>", "position": "<e.g. 'Top Row'>",
      "summary": "<what this band contains, for a human reader>",
      "headingTxt": "<verbatim heading in this band, or null>",
      "subheadingTxt": "<verbatim subheading, or null>",
      "note": "<anything a rebuild would need, or null>"}}
  ],
  "transcription_fidelity": "verbatim|partial|illegible",
  "is_animation_reveal": <true|false>,
  "content": <object matching the CONTENT SHAPE below — verbatim strings>,
  "metrics": {{"<label as printed>": "<value as printed>"}},
  "claims_to_verify": ["<factual assertions a fact-checker should chase>"],
  "slide_image_alt": "<one sentence describing the slide for someone who cannot see it — concrete, names the numbers and people shown>",
  "analyst_commentary": "<2-4 sentences: what an investor should notice, what is conspicuously missing, how strong the evidence is. Your judgment, clearly separate from the transcription.>"
}}

CONTENT SHAPES. Pick your slide_type FIRST, then emit `content` in that type's
shape. Keys are fields and values describe what goes in them; omit any key the
slide has nothing for. Every *Txt field is verbatim.

{schemas_prompt_block(shortlist)}

If your chosen slide_type is not among the shapes above, use the generic shape
shown for "other".
"""


# =============================================================================
# Assembly
# =============================================================================

def _assemble(*, transcribed, index, page_count, page_text, company, round_name,
              slug, deck, deck_variant, deck_version, authored_by, dates,
              date_received, today, image_path, out_dir, reveal) -> Dict[str, Any]:
    """Fold a transcription plus everything computed locally into one record."""
    slide_type = transcribed.get("slide_type") or "other"
    title = title_of(page_text) or (
        (transcribed.get("content") or {}).get("titleRow", {}) or {}
    ).get("titleTxt", "")

    record: Dict[str, Any] = {
        # identity
        "company": company,
        "round": round_name,
        "deck_family": slug.split("--")[0],
        "deck_variant": deck_variant,
        "deck_version": deck_version,
        "authored_by": authored_by,
        "slide_uid": f"{slug}#{index:02d}",
        "lineage_id": lineage_id(company, round_name, title or "", slide_type),
        "content_hash": content_hash(page_text),
        "index_position": f"{index:02d}/{page_count:02d}",
        # dates
        **{k: v for k, v in dates.as_frontmatter().items() if k != "dates_mentioned"},
        "date_received": date_received,
        "date_first_analyzed": today,
        "date_last_analyzed": today,
        # content
        "slide_type": slide_type,
        "core_message": transcribed.get("core_message", ""),
        "tags": transcribed.get("tags", []),
        "layout_rows": transcribed.get("layout_rows", 1),
        "layout_pattern": transcribed.get("layout_pattern", "single"),
        "layout_description": transcribed.get("layout_description", []),
        "transcription_fidelity": transcribed.get("transcription_fidelity", "partial"),
        "content": transcribed.get("content", {}),
        "metrics": transcribed.get("metrics", {}),
        "analyst_commentary": transcribed.get("analyst_commentary", ""),
        # provenance
        "augmented_with": AGENT_SIGNATURE,
        "path_to_deck": _relative_to(deck, out_dir),
        # internal, stripped before frontmatter
        "index_number": index,
        "filename": slide_filename(index, slide_type, page_count),
        "_image_abs": str(image_path) if image_path else None,
    }

    if dates.dates_mentioned:
        interesting = [c.as_dict() for c in dates.dates_mentioned if c.kind != "mentioned"]
        if interesting:
            record["dates_mentioned"] = interesting

    # The firm's own slides state the firm's own terms. Sending them to a
    # fact-checker would spend tokens verifying Keystone against Keystone.
    claims = transcribed.get("claims_to_verify", []) or []
    record["claims_to_verify"] = [] if authored_by == "firm" else claims

    if image_path:
        record["slide_image_local"] = f"./slides/{image_path.name}"
        record["slide_image_alt"] = transcribed.get("slide_image_alt", "")

    if reveal:
        position, total, canonical, confirmed = reveal
        record["reveal_sequence"] = f"{position}/{total}"
        record["reveal_canonical"] = canonical

        # The model was asked whether the image confirms the grouping. Record
        # its answer: an earlier version asked the question, printed it in the
        # prompt, and then dropped the response — leaving five title-grouped
        # candidates permanently unadjudicated despite having paid to have them
        # looked at.
        verdict = transcribed.get("is_animation_reveal")
        if verdict is not None:
            record["reveal_confirmed_by_vision"] = bool(verdict)

        if confirmed:
            record["reveal_evidence"] = "text-similarity"
        elif verdict is True:
            record["reveal_evidence"] = "vision"
        elif verdict is False:
            record["reveal_evidence"] = "disputed"
            record.setdefault("extraction_warnings", []).append(
                "grouped as an animation reveal by a repeated heading, but the "
                "image says otherwise — treat these as separate slides"
            )
        else:
            record["reveal_evidence"] = "title-only"
            record.setdefault("extraction_warnings", []).append(
                "grouped as an animation reveal only because neighbouring pages "
                "share this heading — confirm against the images before collapsing"
            )

    if not is_valid_slide_type(slide_type):
        record["_proposed_type"] = (
            transcribed.get("new_type_rationale") or "no rationale given"
        )

    warnings = list(transcribed.get("_warnings", []))
    if transcribed.get("transcription_fidelity") in ("partial", "illegible"):
        warnings.append(f"transcription is {transcribed['transcription_fidelity']}, not verbatim")
    if schema_is_generic(slide_type) and slide_type != "other":
        warnings.append(f"no typed schema for '{slide_type}' — content is in generic form")
    if warnings:
        record.setdefault("extraction_warnings", []).extend(warnings)

    return record


# A relative path that climbs more levels than this stops being useful to a
# reader and starts being noise. Output written outside the repo produced
# "../../../../../../../../../Users/..." — technically correct, unreadable.
_MAX_RELATIVE_HOPS = 4


def _relative_to(target: Path, base: Path) -> str:
    """Relative path from the output folder back to the source deck."""
    try:
        relative = os.path.relpath(target.resolve(), base.resolve())
    except ValueError:
        return str(target.resolve())
    if relative.count("..") > _MAX_RELATIVE_HOPS:
        return str(target.resolve())
    return relative


def _is_stale(front: Dict[str, Any], body: str = "") -> Optional[str]:
    """
    Whether an existing slide document predates a fix that changes its content.

    Resume exists so an interrupted run does not repay for finished work. But
    "finished" is relative to the code that finished it: when a bug is fixed
    after a run, some of those documents are wrong, and skipping them because a
    file exists is just as bad as redoing all of them because one is.

    So staleness is checked per field, against the specific defects that have
    been fixed. Each entry names what was wrong and how to see it in a document,
    and each should be deleted once no archive still carries it.

    Returns a reason string when the slide needs re-transcribing, else None.
    """
    # The prompt asked whether the image confirmed an animation reveal, and the
    # assembler dropped the answer. Documents in a reveal group written before
    # that fix have a reveal_sequence but no reveal_evidence.
    if front.get("reveal_sequence") and not front.get("reveal_evidence"):
        return "reveal verdict was discarded before it could be recorded"

    # "other" used to be the only escape hatch: the vocabulary was closed and the
    # prompt said to fall back rather than name a new type. Anything filed as
    # "other" deserves another look now that coining is allowed.
    # An empty content block is the one defect invisible from frontmatter: the
    # document has a slide_type, a layout, and a core_message, and nothing in the
    # field the agent exists to fill. It has to be read out of the body.
    if body and re.search(r"```json-content\s*\{\s*\}\s*```", body):
        return "content block is empty; re-transcribe"

    if front.get("slide_type") == "other":
        return "typed 'other' under the closed vocabulary; re-check now that types can be coined"

    return None


def _existing_slide(out_dir: Path, index: int) -> Optional[Dict[str, Any]]:
    """
    Load an already-written slide document back into a record, or None.

    Only the fields the later stages need are recovered — enough to upload the
    image and to build the deck manifest — not the whole document.
    """
    if not out_dir.exists():
        return None

    width = 2
    matches = sorted(out_dir.glob(f"{index:0{width}d}-*.md"))
    if not matches:
        return None

    import yaml

    text = matches[0].read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    try:
        front = yaml.safe_load(text.split("---", 2)[1]) or {}
    except yaml.YAMLError:
        return None

    stale = _is_stale(front, text)
    if stale:
        print(f"  [{index:>2}] stale — {stale}")
        return None

    local = front.get("slide_image_local")
    return {
        **front,
        "index_number": index,
        "filename": matches[0].name,
        "_image_abs": str(out_dir / local.lstrip("./")) if local else None,
        "_resumed": True,
    }


def _write_slide(out_dir: Path, record: Dict[str, Any]) -> None:
    """Write one slide document, preserving any human commentary already there."""
    path = out_dir / record["filename"]

    # The filename encodes the slide type, so a re-transcription that changes the
    # type writes a new file and orphans the old one. Re-running a 38-slide deck
    # left 50 files, twelve indices duplicated — and a corpus reader would have
    # found two contradictory documents for the same slide.
    _remove_superseded(out_dir, record, path)
    existing = None
    if path.exists():
        existing = extract_user_commentary(path.read_text(encoding="utf-8"))
        # Re-analysis keeps the original first-analyzed date.
        # Strip the quotes YAML put around the value. Without this, each rewrite
        # captured the previous quoting and nested it again — one pass through
        # the write-then-update-with-CDN-URLs cycle turned '2026-08-23' into
        # '''2026-08-23'''.
        prior = re.search(r"^date_first_analyzed:\s*(\S+)", path.read_text(encoding="utf-8"), re.M)
        if prior:
            record["date_first_analyzed"] = prior.group(1).strip("'\"")

    emitted = {k: v for k, v in record.items() if not k.startswith("_")
               and k not in ("index_number", "filename")}
    path.write_text(
        render_slide_markdown(emitted, existing or record.get("_carried_commentary")),
        encoding="utf-8",
    )


def _remove_superseded(out_dir: Path, record: Dict[str, Any], keeping: Path) -> None:
    """
    Delete earlier documents for this slide index that a type change orphaned.

    Any human commentary on the orphan is carried into the new file first — it is
    the one thing in these documents no agent wrote.
    """
    index = record["index_number"]
    for stale in sorted(out_dir.glob(f"{index:02d}-*.md")):
        if stale == keeping:
            continue
        commentary = extract_user_commentary(stale.read_text(encoding="utf-8"))
        if commentary:
            record["_carried_commentary"] = commentary
        stale.unlink()


def _write_manifest(out_dir, records, company, round_name, slug, deck,
                    deck_variant, deck_version, authored_by, dates, groups, today) -> None:
    manifest = {
        "deck_family": slug.split("--")[0],
        "company": company,
        "round": round_name,
        "deck_variant": deck_variant,
        "deck_version": deck_version,
        "authored_by": authored_by,
        "date_on_deck": dates.date_on_deck.isoformat() if dates.date_on_deck else None,
        "date_source": dates.date_source,
        "date_confidence": dates.date_confidence,
        "date_notes": dates.notes,
        "source_file": _relative_to(deck, out_dir),
        "source_sha256": _file_hash(deck),
        "page_count": len(records),
        "reveal_groups": [
            {"pages": g.indices, "canonical": g.canonical, "confirmed": g.confirmed}
            for g in groups
        ],
        "analyzed_with": AGENT_SIGNATURE,
        "date_first_analyzed": today,
        "date_last_analyzed": today,
    }
    (out_dir / "deck.yaml").write_text(
        render_deck_manifest(manifest, records), encoding="utf-8"
    )


def _file_hash(path: Path) -> str:
    """SHA-256 of the source deck, so a re-run can tell if the file changed."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:32]

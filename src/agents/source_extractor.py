"""
Source Extractor — read each approved source once, and put what it says on file.

WHY THIS IS THE PRIMARY STEP
----------------------------
Coverage was being treated as a citation problem: 28 approved sources, 6 cited,
so add a rule that every source must be cited. That is backwards. A source goes
uncited because nobody ever extracted anything from it — and a model asked to
"synthesize 28 sources into 750 words" reads four and answers the rest from
parametric memory, because that is cheaper and the output looks identical.

Measured on TrustedRouter v0.0.2: 22 sources fetched successfully, 14 cited in
research. Eight documents were pulled, held in memory, and never read.

So reading becomes its own step:

    fetch → EXTRACT (one pass per source) → synthesize sections

Three properties make this work where a bigger synthesis prompt does not:

1. **One source per call.** No context pressure and nowhere to hide; a source
   cannot be quietly skipped when it has a dedicated pass.
2. **Verbatim evidence.** Every quote and stat must appear word-for-word in the
   fetched text, checked mechanically against the document already in memory
   (`src/grounding.py`). This is the only defense that catches a model FAKING
   having read something — inventing a quote and attributing it to a real,
   retrieved, live URL. Provenance, liveness, attribution and fact-verification
   all pass that case.
3. **Extracts land in the source's own file**, as LFM directives under
   `# Extracts` — the shape specified by
   `agent-skills/source-with-extracts-md/SKILL.md`. No JSON sidecar: the parse
   is the extraction, and structured querying belongs in the shared SurrealDB
   registry rather than a per-deal file only memopop can read.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..curation.extracts import merge_extracts, parse_extracts
from ..curation.source_file import (
    read_source_file,
    resolve_path,
    write_source_file,
)
from ..grounding import normalize

EXTRACTION_SYSTEM = """You are a research analyst reading ONE source document and recording what it actually says.

You are not writing prose. You are not summarizing for a reader. You are putting
extractable material on file so a writer can use it later.

Extract, from the document text provided and NOTHING ELSE:

- quote   — a short verbatim quotation, word-for-word from the document
- stat    — a specific number, dollar amount, percentage, or dated figure
- claim   — a factual assertion, non-obvious implication, or stance the document takes

HARD RULES — checked mechanically after you respond:

1. Every `quote` MUST appear WORD-FOR-WORD in the document text below. Copy it.
   Do not paraphrase it, do not tidy it up, do not fix its punctuation.
2. Every `stat` MUST appear in the document text below.
3. If you did not read it in the text below, you do not know it. Do NOT use prior
   knowledge about this company, publication or topic. Inventing a quote or figure
   and attributing it to this document is the worst thing you can do here, and it
   is exactly what this step exists to catch.
4. If the document is thin, paywalled, an error page, or off-topic, return few or
   zero items. Returning nothing is a valid, honest answer. Padding with
   plausible-sounding material is not.
5. Prefer specific over general. "Revenue tripled in 2025" beats "revenue grew".

Return ONLY a JSON object:

{"items": [{"kind": "quote|stat|claim",
            "text": "the extracted item",
            "verbatim": "exact span from the document supporting it, or null",
            "topic": "2-5 word tag, e.g. pricing, competition, regulation"}]}"""


def _extract_one(llm, sf, max_chars: int) -> Dict[str, Any]:
    """One source: extract, verify every span, return items + rejects."""
    from langchain_core.messages import HumanMessage, SystemMessage

    content, _ = _split_content(sf.body)
    text = (content or sf.excerpt or "")[:max_chars]
    label = sf.title or sf.url

    if not text.strip():
        return {"sf": sf, "items": [], "rejected": [], "scope": "none",
                "note": "no content on file"}

    scope = "full" if content.strip() else "excerpt"
    user = (f"Source title: {sf.title or sf.url}\nSource URL: {sf.url}\n\n"
            f"DOCUMENT TEXT:\n{text}\n\nExtract now. JSON only.")
    try:
        resp = llm.invoke([SystemMessage(content=EXTRACTION_SYSTEM),
                           HumanMessage(content=user)])
        raw = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as exc:  # noqa: BLE001
        return {"sf": sf, "items": [], "rejected": [], "scope": scope,
                "note": f"extraction failed: {exc}"[:160]}

    m = re.search(r"\{.*\}", raw, re.S)
    try:
        payload = json.loads(m.group(0)) if m else {"items": []}
    except json.JSONDecodeError:
        payload = {"items": []}

    hay = normalize(text)
    kept, rejected = [], []
    for it in payload.get("items") or []:
        if not isinstance(it, dict):
            continue
        kind = (it.get("kind") or "").strip().lower()
        body_text = (it.get("text") or "").strip()
        if not kind or not body_text:
            continue
        span = it.get("verbatim") or (body_text if kind in ("quote", "stat") else None)

        if kind in ("quote", "stat"):
            if span and normalize(span) in hay:
                kept.append({"kind": kind, "text": body_text,
                             "topic": it.get("topic") or "", "grounded": "true"})
            else:
                rejected.append({"kind": kind, "text": body_text})
        else:
            grounded = bool(span and normalize(span) in hay)
            kept.append({"kind": "claim", "text": body_text,
                         "topic": it.get("topic") or "",
                         "grounded": "true" if grounded else "unverified"})

    return {"sf": sf, "items": kept, "rejected": rejected, "scope": scope}


def _split_content(body: str):
    from ..curation.extracts import split_body
    return split_body(body or "")


def extract_for_deal(
    deal_inputs_dir: Path,
    *,
    only_approved: bool = True,
    max_chars: int = 16000,
    workers: int = 6,
) -> Dict[str, Any]:
    """Extract from every per-source file that has content, writing MD in place."""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        return {"extracted": 0, "note": "langchain_anthropic unavailable"}

    from ..curation.source_file import sources_dir
    sdir = sources_dir(Path(deal_inputs_dir))
    if not sdir.exists():
        return {"extracted": 0, "note": f"no sources dir at {sdir}"}

    files = [read_source_file(p) for p in sorted(sdir.glob("*.md"))]
    files = [f for f in files if f]
    if only_approved:
        files = [f for f in files if (f.verdict or "").lower() != "rejected"]
    if not files:
        return {"extracted": 0, "note": "no source files"}

    llm = ChatAnthropic(
        model=os.environ.get("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        max_tokens=4000, temperature=0,
    )

    print(f"  📑 Extracting from {len(files)} source file(s), one pass each…")
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_extract_one, llm, sf, max_chars): sf for sf in files}
        for fut in as_completed(futures):
            sf = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                results.append({"sf": sf, "items": [], "rejected": [],
                                "scope": "none", "note": str(exc)[:160]})

    total_items = total_rejected = written = 0
    empty: List[str] = []
    for r in results:
        sf, items = r["sf"], r["items"]
        total_rejected += len(r["rejected"])
        if not items:
            empty.append(sf.title or sf.url)
            continue
        sf.body = merge_extracts(sf.body, items)
        sf.extra_metadata = {**(sf.extra_metadata or {}),
                             "extraction_scope": r.get("scope", "full")}
        try:
            write_source_file(Path(deal_inputs_dir), sf)
            written += 1
            total_items += len(items)
        except Exception as exc:  # noqa: BLE001
            print(f"     ⚠️  could not write {sf.url[:60]}: {exc}")

    print(f"     ✓ {total_items} extract(s) written to {written} file(s)"
          + (f"; {total_rejected} ungrounded span(s) REJECTED" if total_rejected else "")
          + (f"; {len(empty)} source(s) yielded nothing" if empty else ""))
    for r in results:
        for rej in r["rejected"][:2]:
            print(f'        ⚠️  fabricated {rej["kind"]}: "{rej["text"][:66]}" '
                  f'— not in {(r["sf"].title or r["sf"].url)[:40]}')

    return {"extracted": total_items, "files": written,
            "rejected": total_rejected, "empty": len(empty)}


def load_extracts_for_deal(deal_inputs_dir: Path) -> List[Dict[str, Any]]:
    """Read every source's extracts back, one record per source."""
    from ..curation.source_file import sources_dir
    sdir = sources_dir(Path(deal_inputs_dir))
    if not sdir.exists():
        return []
    out = []
    for p in sorted(sdir.glob("*.md")):
        sf = read_source_file(p)
        if not sf:
            continue
        items = parse_extracts(sf.body, source_label=(sf.title or sf.url)[:60])
        if items:
            out.append({"url": sf.url, "title": sf.title, "rank": sf.rank,
                        "sections": sf.sections, "items": items})
    return out

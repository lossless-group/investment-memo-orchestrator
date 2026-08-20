"""
Triage a deal's curated source set before an analyst reviews it.

WHY THIS EXISTS
---------------
Curation asks the analyst one question per source — keep it or drop it — and
that question has three independent parts that get conflated:

  1. PROVENANCE — did a retrieval system actually return this URL, or did a
     language model produce the string? This is the strongest signal we have
     and it is cheap: `1-research/.provenance.json` records every URL Perplexity
     genuinely retrieved (written by `agents/perplexity_sources.py`).
  2. LIVENESS  — does the URL resolve to a real page today? Reuses the existing
     validation ladder in `agents/remove_invalid_sources.py` (hallucination-regex
     preflight, HTTP, soft-404 body sniff, paywall detection, gated-publisher
     allow-list).
  3. SUPPORT   — does that page actually say what the memo cites it for? Only
     partially machine-answerable, and deliberately left to the human.

These come apart constantly, and that is the whole point of separating them:

  - A URL can be LIVE and REAL and still be model-invented (never retrieved) —
    a plausible guess that happens to exist. Liveness alone would pass it.
  - A URL can be RETRIEVED and DEAD (link rot since the crawl).
  - A URL can be RETRIEVED and LIVE and still not support the claim, which no
    amount of URL checking will ever catch.

Provenance is also where the data-poisoning boundary sits, so it is worth being
precise about what it does NOT prove: it proves a retriever returned the page,
not that the page is honest. Adversarially planted content is retrievable by
construction. Provenance defends against fabrication, not against poisoning;
only reading the source defends against poisoning.

THE DENY-BASED DEFAULT
----------------------
`sources_md.is_approved_entry` treats a source as approved unless it is
EXPLICITLY rejected — a blank verdict grants membership. So a triage pass that
merely annotates would silently approve everything it doubted. This writes real
verdicts, and only the human upgrades an AMBER to approved.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.perplexity_sources import (  # noqa: E402
    PROVENANCE_FILENAME,
    normalize_url,
)
from src.agents.remove_invalid_sources import (  # noqa: E402
    CONTENT_INVALID_CODES,
    HALLUCINATION_PATTERN,
    INVALID_HTTP_CODES,
    PAYWALL_STUB,
    POTENTIALLY_VALID_CODES,
    SOFT_404_BODY,
    VERIFIED_GATED,
    validate_url,
)
from src.curation.serialize import write_sources_md  # noqa: E402
from src.curation.sources_md import load_sources_md  # noqa: E402

# Verdicts written back. Only GREEN/GATED stay in the approved set; everything
# else is explicitly rejected, because blank means approved.
GREEN   = "green"     # retrieved + live            -> leave unreviewed (approved)
GATED   = "gated"     # retrieved + paywalled/403   -> approved, flagged for the human
AMBER   = "amber"     # live but NEVER retrieved    -> rejected pending human review
RED     = "red"       # dead / soft-404 / fabricated-> rejected
ORPHAN  = "orphan"    # retrieved but now dead      -> rejected


def load_provenance_for(outputs_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Merge every `.provenance.json` under a version's `1-research/`."""
    merged: Dict[str, Dict[str, Any]] = {}
    for path in outputs_dir.rglob(PROVENANCE_FILENAME):
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                merged.update(data)
        except (json.JSONDecodeError, OSError):
            continue
    return merged


def classify(url: str, in_provenance: bool, code: int, status: str) -> Tuple[str, str]:
    """Return (verdict, reason) for one source."""
    dead = code in INVALID_HTTP_CODES or code in CONTENT_INVALID_CODES

    if code == HALLUCINATION_PATTERN:
        return RED, f"fabricated URL shape ({status})"
    if dead:
        if in_provenance:
            kind = "soft-404" if code == SOFT_404_BODY else (
                "paywall stub" if code == PAYWALL_STUB else f"HTTP {code}")
            return ORPHAN, f"retrieved at research time but {kind} now — link rot or gated"
        return RED, f"never retrieved AND {status}"

    if not in_provenance:
        # The dangerous class: resolves fine, but no retriever ever returned it.
        if code == VERIFIED_GATED or code in POTENTIALLY_VALID_CODES:
            return AMBER, (f"NOT in retrieved set; {status} so content unverifiable "
                           f"— treat as model-introduced until a human confirms")
        return AMBER, ("NOT in retrieved set — URL resolves but no retriever returned it; "
                       "model-introduced, needs human confirmation")

    if code == VERIFIED_GATED:
        return GATED, f"retrieved; gated publisher ({status}) — verify via subscription"
    if code in POTENTIALLY_VALID_CODES:
        return GATED, f"retrieved; {status} — real but not machine-verifiable"
    return GREEN, f"retrieved and live ({status})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--firm", required=True)
    ap.add_argument("--deal", required=True)
    ap.add_argument("--version", default=None, help="e.g. v0.0.1 (default: latest)")
    ap.add_argument("--apply", action="store_true",
                    help="write verdicts back into inputs/Sources.md (backed up)")
    ap.add_argument("--sources-file", default=None,
                    help="explicit path to a Sources*.md (default: inputs/Sources.md). "
                         "Use for the pipeline's outputs/.../Sources-aggregated.md draft.")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    deal_dir = Path("io") / args.firm / "deals" / args.deal
    inputs_dir = deal_dir / "inputs"
    outputs_dir = deal_dir / "outputs"
    if args.version:
        outputs_dir = outputs_dir / f"{args.deal}-{args.version}"

    if args.sources_file:
        # load_sources_md takes a directory and expects the file to be named
        # Sources.md, so stage the named file into a temp dir under that name.
        import shutil, tempfile
        src = Path(args.sources_file)
        if not src.exists():
            print(f"✗ {src} not found")
            return 1
        staging = Path(tempfile.mkdtemp())
        shutil.copy(src, staging / "Sources.md")
        sources_md = load_sources_md(staging)
        source_label = str(src)
    else:
        sources_md = load_sources_md(inputs_dir)
        source_label = f"{inputs_dir}/Sources.md"

    if not sources_md or not sources_md.sources:
        print(f"✗ No sources with entries at {source_label}")
        return 1
    print(f"📄 {source_label}")

    provenance = load_provenance_for(outputs_dir)
    print(f"📖 {len(sources_md.sources)} sources | "
          f"{len(provenance)} URLs in retrieved-source provenance")
    if not provenance:
        print("⚠️  No .provenance.json found — every source will read as AMBER.\n"
              "   Provenance is written by the research stage; check the run completed it.")

    entries = sources_md.sources
    results: Dict[str, Tuple[int, str]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(validate_url, e.url): e.url for e in entries if e.url}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                _, code, status = fut.result()
            except Exception as exc:  # noqa: BLE001
                code, status = 0, f"check failed: {exc}"[:80]
            results[url] = (code, status)

    buckets: Dict[str, List[Any]] = {k: [] for k in (GREEN, GATED, AMBER, ORPHAN, RED)}
    for e in entries:
        if not e.url:
            continue
        code, status = results.get(e.url, (0, "not checked"))
        in_prov = normalize_url(e.url) in provenance
        verdict, reason = classify(e.url, in_prov, code, status)
        buckets[verdict].append((e, reason))
        e.verdict = "" if verdict in (GREEN, GATED) else "rejected"
        e.verdict_reason = f"[{verdict}] {reason}"

    icons = {GREEN: "🟢", GATED: "🟡", AMBER: "🟠", ORPHAN: "🟤", RED: "🔴"}
    labels = {
        GREEN:  "VERIFIED   retrieved + live               → approved",
        GATED:  "GATED      retrieved, not machine-checkable → approved, spot-check",
        AMBER:  "UNBACKED   live but never retrieved        → REJECTED, needs you",
        ORPHAN: "LINK ROT   retrieved, dead now            → REJECTED",
        RED:    "DEAD/FAKE  never retrieved + broken        → REJECTED",
    }
    print("\n" + "=" * 78)
    for key in (GREEN, GATED, AMBER, ORPHAN, RED):
        rows = buckets[key]
        print(f"\n{icons[key]} {labels[key]}   [{len(rows)}]")
        for e, reason in rows[:40]:
            print(f"    {e.url[:88]}")
            print(f"        {reason}")
    print("\n" + "=" * 78)
    total = sum(len(v) for v in buckets.values())
    approved = len(buckets[GREEN]) + len(buckets[GATED])
    print(f"SUMMARY  {total} sources → {approved} approved, {total - approved} rejected")
    print(f"         🟢 {len(buckets[GREEN])}  🟡 {len(buckets[GATED])}  "
          f"🟠 {len(buckets[AMBER])}  🟤 {len(buckets[ORPHAN])}  🔴 {len(buckets[RED])}")
    if buckets[AMBER]:
        print(f"\n⚠️  {len(buckets[AMBER])} AMBER sources resolve but were never retrieved.\n"
              "   These are the model-introduced ones — the class that reads as\n"
              "   legitimate and is not. Review them in memopop-native before approving.")

    if args.apply:
        payload = [
            {"url": e.url, "title": e.title, "publisher": e.publisher,
             "published_date": e.published_date, "sections": e.sections,
             "rank": e.rank, "sensitivity": e.sensitivity,
             "verdict": e.verdict, "verdict_reason": e.verdict_reason, "note": e.note}
            for e in entries
        ]
        target, backup = write_sources_md(
            inputs_dir / "Sources.md", sources_md.raw_frontmatter, payload,
            sources_md.body, mode=sources_md.mode,
        )
        print(f"\n✍️  wrote {target}" + (f"  (backup: {backup})" if backup else ""))
    else:
        print("\n(dry run — pass --apply to write verdicts back into Sources.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

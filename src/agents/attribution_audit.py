"""
Attribution Audit Agent — flags claims attributed to the wrong company.

PIPELINE POSITION
-----------------
    fact_check  →  attribution_audit  →  fact_verify  →  fact_correct

It sits inside the existing correction chain rather than beside it, because the
chain already has the right shape: extract claims, judge them, apply fixes. What
was missing is a judgement about *subject*. `fact_verify` asks Perplexity "is
this true?" — and a misattributed claim is true, so it passes. Asking the
question one node earlier means the verifier and corrector both receive claims
already marked with who they are about.

WHY A NODE AND NOT A PATCH
--------------------------
The specific TrustedRouter bug (a competitor's $113M Series B summarized as the
subject's raise) was fixable with a regex filter in one agent. That fixes one
memo. Making it a graph node means every memo gets audited, the result is a
durable artifact an analyst can review, and the failure has somewhere to be
reported rather than depending on someone noticing.

MODES  (env `MEMOPOP_ATTRIBUTION_AUDIT`)
----------------------------------------
    flag   (default) — write the report, print a summary, continue
    halt             — write the report and STOP, like source curation does,
                       so a human corrects before the memo is finalized
    off              — skip entirely

`flag` is the default deliberately: the audit is heuristic, and a heuristic that
halts a pipeline on false positives gets switched off within a week. Start by
reporting; promote to `halt` once the signal is trusted on real memos.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from ..state import MemoState
from ..attribution import audit_claims, known_competitors

REPORT_BASENAME = "3-attribution-audit"


def _load_memo_text(output_dir: Path) -> str:
    """Prefer the assembled draft; fall back to concatenated sections."""
    try:
        from ..final_draft import find_final_draft, read_final_draft
        if find_final_draft(output_dir):
            return read_final_draft(output_dir)
    except Exception:  # noqa: BLE001
        pass
    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        return ""
    return "\n\n".join(f.read_text() for f in sorted(sections_dir.glob("*.md")))


def _render_report(company: str, flagged: List[Dict[str, Any]],
                   total: int, competitors: List[str]) -> str:
    lines = [
        f"# Attribution Audit — {company}",
        "",
        f"Quantitative claims examined: **{total}**  ",
        f"Flagged as possibly about another company: **{len(flagged)}**  ",
        f"Known competitors considered: {', '.join(competitors) if competitors else '(none found)'}",
        "",
        "A flagged claim is not necessarily wrong. It is a claim whose sentence",
        "names another company, or names no company this audit could resolve to",
        f"**{company}**. Confirm each one is about {company} before the memo ships —",
        "these are the errors that survive every other check, because the numbers",
        "are real, correctly cited, and simply about someone else.",
        "",
    ]
    if not flagged:
        lines += ["_No claims flagged._", ""]
        return "\n".join(lines)

    by_entity: Dict[str, List[Dict[str, Any]]] = {}
    for f in flagged:
        by_entity.setdefault(f.get("subject") or "(unresolved)", []).append(f)

    for entity, items in sorted(by_entity.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"## Attributed to: {entity}  ({len(items)})")
        lines.append("")
        for f in items:
            lines.append(f"- **[{f['claim_type']}]** {f['sentence']}")
        lines.append("")
    return "\n".join(lines)


def attribution_audit_agent(state: MemoState) -> Dict[str, Any]:
    """Audit quantitative claims for subject attribution."""
    mode = os.environ.get("MEMOPOP_ATTRIBUTION_AUDIT", "flag").strip().lower()
    if mode == "off":
        return {"messages": ["Attribution audit: disabled"]}

    try:
        from ..utils import get_output_dir_from_state
        output_dir = get_output_dir_from_state(state)
    except Exception:  # noqa: BLE001
        return {"messages": ["Attribution audit skipped - no output directory"]}

    company = state.get("company_name") or ""
    text = _load_memo_text(Path(output_dir))
    if not text.strip():
        return {"messages": ["Attribution audit skipped - no memo content"]}

    competitors = known_competitors(state)
    claims = audit_claims(text, company, competitors)
    # High confidence: the sentence names a KNOWN competitor and not the subject.
    # Low confidence: some other capitalized entity we could not resolve. Only
    # the former counts as flagged by default — a gate that fires on unresolved
    # nouns trains people to ignore it. Set MEMOPOP_ATTRIBUTION_STRICT=1 to
    # include the low-confidence set.
    strict = os.environ.get("MEMOPOP_ATTRIBUTION_STRICT", "").strip() in ("1", "true", "yes")
    competitor_hits = [c for c in claims if c["subject_kind"] == "competitor"]
    unresolved = [c for c in claims if c["subject_kind"] == "ambiguous"]
    flagged = competitor_hits + (unresolved if strict else [])

    print("\n🔎 ATTRIBUTION AUDIT")
    print(f"  Claims examined : {len(claims)}")
    print(f"  Flagged         : {len(flagged)}"
          + (f"  (+{len(unresolved)} unresolved, not flagged)" if not strict and unresolved else ""))
    if competitors:
        print(f"  Competitors     : {', '.join(competitors[:6])}"
              + (" …" if len(competitors) > 6 else ""))

    report = _render_report(company, flagged, len(claims), competitors)
    md_path = Path(output_dir) / f"{REPORT_BASENAME}.md"
    json_path = Path(output_dir) / f"{REPORT_BASENAME}.json"
    try:
        md_path.write_text(report)
        json_path.write_text(json.dumps(
            {"company": company, "competitors": competitors,
             "claims_examined": len(claims), "flagged": flagged},
            indent=2))
        print(f"  📝 Report: {md_path.name}")
    except OSError as exc:
        print(f"  ⚠️  Could not write report: {exc}")

    for f in flagged[:8]:
        print(f"    ⚠️  [{f.get('subject') or 'unresolved'}] {f['sentence'][:110]}")
    if len(flagged) > 8:
        print(f"    … {len(flagged) - 8} more in {md_path.name}")

    if flagged and mode == "halt":
        print()
        print("─" * 70)
        print("🛑 HALTING PIPELINE for attribution review.")
        print()
        print("Next steps:")
        print(f"  1. Open: {md_path}")
        print(f"  2. For each flagged claim, confirm it is about {company}.")
        print("     Fix or delete the ones that are not, in outputs/<v>/2-sections/.")
        print("  3. Re-run with --resume to continue from here.")
        print()
        print("  (Set MEMOPOP_ATTRIBUTION_AUDIT=flag to report without halting.)")
        print("─" * 70)
        sys.exit(0)

    return {
        "messages": [
            f"Attribution audit: {len(flagged)} of {len(claims)} claims flagged"
        ],
        "attribution_audit": {
            "claims_examined": len(claims),
            "flagged": len(flagged),
            "report": str(md_path),
        },
    }

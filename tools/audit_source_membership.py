#!/usr/bin/env python3
"""Read-only audit: how much of a memo cites sources the analyst never approved?

STRICTLY READ-ONLY. Writes nothing, changes nothing, makes no network
calls. Safe to point at firm-private deals.

This exists because the validator itself (`remove_invalid_sources`) is
destructive by design — even in `flag` mode it still removes genuinely
dead URLs and reassembles the final draft. To answer "how big is the
leak?" before changing anything, use this.

    python tools/audit_source_membership.py io/alpha-partners/deals/ChromaDB/outputs/ChromaDB-v0.0.9
    python tools/audit_source_membership.py --firm alpha-partners --deal ChromaDB   # newest version
    python tools/audit_source_membership.py --all                                   # every codified deal

Exit codes: 0 = clean or nothing to check, 1 = unapproved citations found.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.remove_invalid_sources import (  # noqa: E402
    collect_all_citation_urls,
    state_from_output_dir,
)
from src.curation import (  # noqa: E402
    approved_urls,
    is_approved_url,
    is_codified,
    load_sources_md,
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "?").replace("www.", "")
    except Exception:
        return "?"


def audit(output_dir: Path, *, quiet: bool = False) -> dict:
    """Audit one memo version. Returns a summary dict; writes nothing."""
    state = state_from_output_dir(output_dir)
    if not state:
        return {"skipped": "not a firm-scoped deal path", "dir": str(output_dir)}

    inputs = REPO_ROOT / "io" / state["firm"] / "deals" / state["company_name"] / "inputs"
    sources_md = load_sources_md(inputs)
    if not sources_md:
        return {"skipped": "no Sources.md", "dir": str(output_dir)}
    if not is_codified(sources_md):
        return {
            "skipped": f"mode: {sources_md.mode} (not codified)",
            "dir": str(output_dir),
        }

    approved = approved_urls(sources_md)
    cited = collect_all_citation_urls(output_dir)
    unapproved = sorted(u for u in cited if not is_approved_url(u, approved))
    used = {u for u in cited if is_approved_url(u, approved)}

    summary = {
        "deal": f"{state['firm']}/{state['company_name']}",
        "version": output_dir.name,
        "approved_total": len(approved),
        "cited_total": len(cited),
        "unapproved": len(unapproved),
        "approved_and_cited": len(used),
        "coverage_pct": round(100 * len(used) / len(approved), 1) if approved else 0.0,
        "unapproved_urls": unapproved,
    }

    if not quiet:
        print(f"\n{'=' * 72}")
        print(f"  {summary['deal']}  {summary['version']}")
        print(f"{'=' * 72}")
        print(f"  Approved sources in Sources.md : {summary['approved_total']}")
        print(f"  Unique URLs cited in the memo  : {summary['cited_total']}")
        print(f"  ✗ Cited but NOT approved       : {summary['unapproved']}")
        print(f"  ✓ Approved and actually cited  : {summary['approved_and_cited']}"
              f"  ({summary['coverage_pct']}% of the approved set)")

        if unapproved:
            print(f"\n  Off-set citations by host:")
            for host, n in Counter(_host(u) for u in unapproved).most_common(12):
                print(f"    {n:4d}  {host}")
            print(f"\n  Off-set URLs (first 15):")
            for u in unapproved[:15]:
                print(f"    ✗ {u[:110]}")
            if len(unapproved) > 15:
                print(f"    … and {len(unapproved) - 15} more")

        # Coverage is the counterweight: enforcement sets the ceiling, but a
        # memo that cites 7 of 33 approved sources has a different problem.
        if approved and summary["coverage_pct"] < 40:
            print(
                f"\n  ⚠️  Coverage is low ({summary['coverage_pct']}%) — "
                f"{len(approved) - len(used)} approved sources went uncited.\n"
                f"      See context-v/plans/Citation-Coverage-Promoter.md"
            )

    return summary


def _newest_version(firm: str, deal: str) -> Path | None:
    """Newest `<Deal>-vX.Y.Z` directory.

    Matches on `-v<digit>` specifically: a bare `*-v*` glob also catches
    names like `aix-ventures-roster` (the "-v" in "ventures"), which is
    not a memo version and audits as an empty one.

    Sorted by parsed version tuple, not lexically — `-v0.0.11` must sort
    after `-v0.0.9`.
    """
    import re

    outputs = REPO_ROOT / "io" / firm / "deals" / deal / "outputs"
    if not outputs.exists():
        return None

    pattern = re.compile(r"-v(\d+)\.(\d+)\.(\d+)$")
    versions = []
    for p in outputs.iterdir():
        m = pattern.search(p.name)
        if p.is_dir() and m:
            versions.append((tuple(int(g) for g in m.groups()), p))
    return max(versions)[1] if versions else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("output_dir", nargs="?", help="a memo version directory")
    ap.add_argument("--firm")
    ap.add_argument("--deal")
    ap.add_argument("--all", action="store_true", help="audit every codified deal")
    args = ap.parse_args()

    targets: list[Path] = []
    if args.all:
        for inputs in sorted((REPO_ROOT / "io").glob("*/deals/*/inputs")):
            sm = load_sources_md(inputs)
            if not is_codified(sm):
                continue
            newest = _newest_version(inputs.parts[-4], inputs.parts[-2])
            if newest:
                targets.append(newest)
    elif args.firm and args.deal:
        newest = _newest_version(args.firm, args.deal)
        if not newest:
            print(f"No output versions for {args.firm}/{args.deal}")
            return 0
        targets.append(newest)
    elif args.output_dir:
        targets.append(Path(args.output_dir))
    else:
        ap.print_help()
        return 0

    total_unapproved = 0
    for t in targets:
        if not t.exists():
            print(f"Not found: {t}")
            continue
        result = audit(t)
        if "skipped" in result:
            print(f"⊘ {t}  — {result['skipped']}")
        else:
            total_unapproved += result["unapproved"]

    if total_unapproved:
        print(f"\n{'=' * 72}")
        print(f"  TOTAL off-set citations across {len(targets)} memo(s): {total_unapproved}")
        print(f"{'=' * 72}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

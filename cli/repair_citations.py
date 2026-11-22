#!/usr/bin/env python3
"""
Repair a finished memo whose citations link to another section's source, rewriting them as hex keys.

Memos assembled before the citation-collision fix numbered every section's
sources from 1 and resolved the numbers globally, so most footnotes link to
another section's source. This re-derives each section's markers from its own
research file and writes hex keys from src/citation_keys.py. It changes only
markers and the definitions block; prose is checked unchanged before anything is
written. Regions it cannot prove are left byte-identical and reported. See
context-v/agent-skills/repair-memo-citations/SKILL.md.

Usage:
    # Which memos are affected (read-only):
    .venv/bin/python cli/repair_citations.py --scan io

    # Dry run (default): report what would change, write nothing
    .venv/bin/python cli/repair_citations.py io/<firm>/deals/<Deal>/outputs/<Deal>-v0.0.1

    # Repair in place (keeps 7-<Deal>-<v>.md.bak), then export dark and light HTML + PDF
    .venv/bin/python cli/repair_citations.py <version-dir> --write --export

    # Repair into a copy of the version dir instead
    .venv/bin/python cli/repair_citations.py <version-dir> --out /tmp/repaired-copy

Exit codes: 0 repaired (or scan done), 2 nothing repairable, 1 error or prose changed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src import citation_repair  # noqa: E402


def _print_report(report: dict) -> None:
    for region in report.get("regions", []):
        print(f"  {region['section']:40s} {region.get('status', ''):13s} {region.get('reason', '')}")
    for item in report.get("unverified", []):
        heads = ", ".join(item["headings"]) or "(text before the first heading)"
        print(f"  {'unverified':40s} {item['markers']:3d} markers  {heads}")
    for note in report.get("notes", []):
        print(f"  note: {note}")
    print(report.get("result", ""))


def _firm_of(path: Path) -> Optional[str]:
    match = re.search(r"/io/([^/]+)/", str(path.resolve()))
    return match.group(1) if match else None


def export_commands(memo: Path, exports_root: Path, brand: Optional[str], firm: Optional[str]) -> List[List[str]]:
    """One cli/export_branded.py call per mode, each writing HTML and PDF."""
    commands = []
    for mode in ("dark", "light"):
        cmd = [sys.executable, str(REPO / "cli" / "export_branded.py"), str(memo), "--mode", mode, "--pdf"]
        cmd += ["-o", str(exports_root / mode)]
        if brand:
            cmd += ["--brand", brand]
        if firm:
            cmd += ["--firm", firm]
        commands.append(cmd)
    return commands


def _scan(io_root: Path) -> int:
    rows = citation_repair.scan(io_root)
    if not rows:
        print(f"no finished memos with research files under {io_root}")
        return 0
    rows.sort(key=lambda r: (-(r.share or 0), str(r.memo)))
    print(f"{'wrong':>5}/{'cited':<5} {'share':>5}  memo")
    for row in rows:
        share = f"{100 * row.share:.0f}%" if row.share is not None else "-"
        flags = []
        if row.collapsed:
            flags.append(f"collapsed keys in {len(row.collapsed)} research file(s): those sections will be refused")
        if row.ambiguous:
            flags.append("several 7-*.md here: pass --memo")
        if row.duplicate_of:
            flags.append("duplicate of " + ", ".join(row.duplicate_of))
        print(f"{row.wrong:5d}/{row.checked:<5d} {share:>5}  {row.memo}")
        for flag in flags:
            print(f"{'':19s}! {flag}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repair a finished memo's section-colliding citations as hex keys (dry run by default)."
    )
    parser.add_argument("version_dir", type=Path, nargs="?", help="io/<firm>/<deals|portfolio>/<Deal>/outputs/<version>")
    parser.add_argument("--memo", help="Finished memo filename, required when the version dir has several 7-*.md")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--write", action="store_true", help="Repair in place, keeping <memo>.bak")
    target.add_argument("--out", type=Path, help="Copy the version dir here and repair the copy")
    parser.add_argument("--export", action="store_true", help="After repairing, export dark and light HTML and PDF")
    parser.add_argument("--brand", help="Brand for --export (default: the firm in the path)")
    parser.add_argument("--firm", help="Firm for --export (default: the firm in the path)")
    parser.add_argument("--scan", type=Path, metavar="IO_ROOT", help="List finished memos and their wrong-link share")
    args = parser.parse_args(argv)

    if args.scan:
        return _scan(args.scan)
    if not args.version_dir:
        parser.error("a version dir is required (or --scan <io-root>)")
    if args.export and not (args.write or args.out):
        parser.error("--export needs --write or --out")

    vd = args.version_dir.resolve()
    try:
        result = citation_repair.repair_memo(vd, args.memo)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = result.report
    if result.changed:
        try:
            citation_repair.check_prose(result)
            report["prose_unchanged"] = True
        except citation_repair.ProseChangedError as exc:
            report["prose_unchanged"] = False
            _print_report(report)
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if not (args.write or args.out):
        _print_report(report)
        print("dry run: nothing written (pass --write or --out)")
        return 0 if result.changed else 2

    if args.out:
        out = args.out.resolve()
        if out == vd or vd in out.parents:
            print("error: --out must be outside the version dir", file=sys.stderr)
            return 1
        if out.exists():
            print(f"error: {out} exists; choose a new --out", file=sys.stderr)
            return 1
        shutil.copytree(vd, out, symlinks=True)
        memo_out = out / result.memo_path.name
        report_dir, exports_root = out, out / "exports"
    else:
        memo_out = result.memo_path
        report_dir = vd
        deal_dir = vd.parent.parent if vd.parent.name == "outputs" else vd
        exports_root = deal_dir / "exports"
        backup = memo_out.with_name(memo_out.name + ".bak")
        if result.changed:
            if backup.exists():
                report["notes"].append(f"{backup.name} already exists and is kept as the oldest backup")
            else:
                shutil.copy2(memo_out, backup)

    if result.changed:
        memo_out.write_text(result.text)
    report["memo_out"] = str(memo_out)
    (report_dir / "repair-report.json").write_text(json.dumps(report, indent=2) + "\n")
    _print_report(report)
    print(f"report: {report_dir / 'repair-report.json'}")

    if result.changed and args.export:
        firm = args.firm or _firm_of(vd)
        brand = args.brand or firm
        for cmd in export_commands(memo_out, exports_root, brand, firm):
            print("$ " + " ".join(cmd[1:]))
            if subprocess.run(cmd, cwd=REPO).returncode != 0:
                print("error: export failed", file=sys.stderr)
                return 1
    return 0 if result.changed else 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Revise one memo section against an angle you supply, without losing its facts.

    .venv/bin/python cli/revise_section.py --firm humain --deal ProfileHealth \
        07 --angle "Lead with the carrier concentration risk on Sieb."

    # longer instructions from a file
    .venv/bin/python cli/revise_section.py --firm humain --deal ProfileHealth \
        "Risks" --angle-file notes/risks-angle.md

What it does NOT do is research. The section's claims are already grounded and
cited; a revision that goes looking for new sources is a regeneration wearing a
revision's name. The only new input is your angle.

Every citation marker and every figure present before the rewrite must be
present after it. If the model drops any, it is shown exactly what it lost and
asked once more. If it still drops them, the original stands untouched and the
archive records why.

Sections are addressed by their number prefix or a fragment of their filename,
never by a constructed name — `save_section_artifact` derives filenames from the
section's title while the outline declares its own, and the two do not agree.
Resolving from what is on disk sidesteps that entirely; an ambiguous prefix is
reported rather than guessed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console

from src.agents.section_reviser import revise_section
from src.utils import get_latest_output_dir

console = Console()


def resolve_section(sections_dir: Path, needle: str) -> Path:
    """Find exactly one section file for `needle`, or explain why we cannot."""
    candidates = sorted(p for p in sections_dir.glob("*.md") if p.is_file())
    if not candidates:
        raise SystemExit(f"No section files in {sections_dir}")

    needle = needle.strip().lower()

    # An exact stem wins outright. Without this, "07-risks" is ambiguous against
    # "07-risks--what-could-go-wrong" on a deal carrying both conventions, and
    # the precise name — the one an operator reaches for to disambiguate — is
    # the one that fails.
    exact = [p for p in candidates if p.stem.lower() == needle]
    if len(exact) == 1:
        return exact[0]

    matches = [p for p in candidates if p.stem.lower().startswith(needle)]
    if not matches:
        matches = [p for p in candidates if needle in p.stem.lower()]
    if not matches:
        listing = "\n".join(f"  {p.name}" for p in candidates)
        raise SystemExit(f"No section matches {needle!r}. Available:\n{listing}")
    if len(matches) > 1:
        listing = "\n".join(f"  {p.name}  ({len(p.read_text().split())} words)" for p in matches)
        raise SystemExit(
            f"{needle!r} matches {len(matches)} files:\n{listing}\n\n"
            "This deal has sections under two naming conventions. Name the file "
            "precisely, or reconcile the duplicates before revising — a revision "
            "written to one of them leaves the other in the assembled memo."
        )
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Revise a memo section against an angle, preserving its claims.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("section", help="Section number prefix (e.g. 07) or filename fragment")
    ap.add_argument("--firm", help="Firm slug for firm-scoped IO")
    ap.add_argument("--deal", help="Deal name (defaults to positional company)")
    ap.add_argument("--company", help="Company name when not using --firm/--deal")
    ap.add_argument("--version", help="Version directory (default: latest)")
    ap.add_argument("--path", help="Direct path to a version output directory")
    ap.add_argument("--angle", help="The revision request, inline")
    ap.add_argument("--angle-file", help="The revision request, from a file")
    ap.add_argument("--attempts", type=int, default=2,
                    help="Total attempts before giving up (default: 2 — one try, one correction)")
    ap.add_argument("--model", help="Override DEFAULT_MODEL for this revision")
    ap.add_argument("--reassemble", action="store_true",
                    help="Rebuild the final draft after an accepted revision")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be preserved and exit without calling a model")
    args = ap.parse_args()

    if not args.angle and not args.angle_file:
        ap.error("give an angle with --angle or --angle-file")
    angle = (Path(args.angle_file).read_text() if args.angle_file else args.angle)
    if not angle.strip():
        ap.error("the angle is empty")

    # Locate the version directory.
    if args.path:
        output_dir = Path(args.path)
    else:
        deal = args.deal or args.company
        if not deal:
            ap.error("need --deal (with --firm), --company, or --path")
        if args.version:
            from src.artifacts import sanitize_filename
            safe = sanitize_filename(deal)
            output_dir = (Path(f"io/{args.firm}/deals/{deal}/outputs/{safe}-{args.version}")
                          if args.firm else Path("output") / f"{safe}-{args.version}")
        else:
            output_dir = get_latest_output_dir(deal, firm=args.firm)

    if not output_dir or not output_dir.exists():
        raise SystemExit(f"No such output directory: {output_dir}")

    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        raise SystemExit(f"No 2-sections/ in {output_dir}")

    target = resolve_section(sections_dir, args.section)
    console.print(f"[bold cyan]Revising[/bold cyan] {target.relative_to(output_dir)}")

    if args.dry_run:
        from src.agents.section_reviser import Preservation
        keep = Preservation.of(target.read_text())
        console.print(f"  words:     {keep.words}")
        console.print(f"  citations: {len(keep.citations)} — {', '.join(sorted(keep.citations)[:12]) or '(none)'}")
        console.print(f"  figures:   {len(keep.figures)} — {', '.join(sorted(keep.figures)[:12]) or '(none)'}")
        console.print(f"  markers:   {', '.join(sorted(keep.markers)) or '(none)'}")
        console.print("\n[dim]Dry run — no model call, nothing written.[/dim]")
        return 0

    result = revise_section(target, angle, max_attempts=args.attempts, model=args.model)

    if not result.accepted:
        console.print(f"\n[bold yellow]Not applied.[/bold yellow] {result.reason}")
        if result.archive_dir:
            console.print(f"Drafts and the loss report: {result.archive_dir}")
        console.print("The section on disk is unchanged.")
        return 1

    before_words = len(result.before.split())
    after_words = len(result.after.split())
    console.print(f"\n[bold green]Applied.[/bold green] {before_words} → {after_words} words, "
                  "every citation and figure preserved.")
    if result.archive_dir:
        console.print(f"Archive (diff before.md against accepted.md): {result.archive_dir}")

    if args.reassemble:
        console.print("\nReassembling the final draft…")
        from src.agents.citation_assembly import citation_assembly_agent
        citation_assembly_agent({"output_dir": str(output_dir),
                                 "company_name": args.deal or args.company or ""})
    else:
        console.print("\n[dim]Run cli/assemble_draft.py when you have finished revising.[/dim]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

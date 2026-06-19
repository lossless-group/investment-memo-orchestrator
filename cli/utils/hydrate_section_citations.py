#!/usr/bin/env python3
"""Hydrate per-section ### Citations blocks from 1-research/*-research.md.

The writer agent puts `[^N]` references in 2-sections/NN-foo.md but the
actual citation definitions live in 1-research/NN-foo-research.md. The
downstream consolidator (cli/utils/consolidate_citations.py) only reads
### Citations blocks inside section files, so any ref whose def is in
1-research/ becomes an orphan in the exported memo.

This script closes that gap. For each 2-sections/NN-foo.md:

  1. Collect every [^id] reference in the body
  2. Collect every [^id]: definition already inside the section's
     ### Citations block (if any)
  3. For each reference not yet defined locally, look up the same id
     in 1-research/NN-foo-research.md and pull the definition into a
     ### Citations block at the end of the section file
  4. Skip refs that have no matching def in either place (they remain
     orphans; the script reports them so they're visible)

Idempotent. Safe to run before every assembly. Section files that
already have complete ### Citations blocks are not modified.

Usage:
    python cli/utils/hydrate_section_citations.py <artifact_dir>
    python cli/utils/hydrate_section_citations.py output/Company-v0.0.3
    python cli/utils/hydrate_section_citations.py --firm <firm> --deal <deal> --version v0.0.3
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

REF_RE = re.compile(r'\[\^([a-zA-Z0-9_-]+)\](?!:)')
DEF_RE = re.compile(r'^\[\^([a-zA-Z0-9_-]+)\]:\s*(.+?)$', re.MULTILINE)
CITATIONS_HEADING_RE = re.compile(r'^### Citations\s*$', re.MULTILINE)


def parse_definitions(text: str) -> Dict[str, str]:
    """Return a dict of citation_id -> definition_line (full text after the colon)."""
    out: Dict[str, str] = {}
    for m in DEF_RE.finditer(text):
        out[m.group(1)] = m.group(2).strip()
    return out


def collect_references(text: str) -> Set[str]:
    """Return the set of citation ids referenced inline (excluding definitions)."""
    return set(REF_RE.findall(text))


def hydrate_section(section_path: Path, research_path: Path | None) -> Tuple[bool, List[str]]:
    """Hydrate one section file. Returns (changed, list_of_orphan_ids)."""
    section_text = section_path.read_text()
    refs = collect_references(section_text)
    existing_defs = parse_definitions(section_text)
    missing = sorted(refs - existing_defs.keys(), key=lambda x: (len(x), x))

    research_defs: Dict[str, str] = {}
    if research_path and research_path.exists():
        research_defs = parse_definitions(research_path.read_text())

    pullable = [(rid, research_defs[rid]) for rid in missing if rid in research_defs]
    orphans = [rid for rid in missing if rid not in research_defs]

    if not pullable:
        return (False, orphans)

    # Append a ### Citations block (or extend the existing one) with the new defs.
    has_block = bool(CITATIONS_HEADING_RE.search(section_text))
    new_lines = [f'[^{rid}]: {definition}' for rid, definition in pullable]
    new_block = '\n\n'.join(new_lines)

    if has_block:
        # Append within the existing block — after the last existing definition.
        # Strategy: find the heading, then append at end of file (the block runs to EOF
        # in the section-file convention). Add a separating blank line.
        section_text = section_text.rstrip() + '\n\n' + new_block + '\n'
    else:
        section_text = section_text.rstrip() + '\n\n---\n\n### Citations\n\n' + new_block + '\n'

    section_path.write_text(section_text)
    return (True, orphans)


def discover_artifact_dir(args: argparse.Namespace) -> Path:
    if args.input is not None:
        return Path(args.input).resolve()
    if args.firm and args.deal:
        base = Path('io') / args.firm / 'deals' / args.deal / 'outputs'
        if args.version:
            return (base / f'{args.deal}-{args.version}').resolve()
        # Pick latest by sorted name
        candidates = sorted(base.glob(f'{args.deal}-v*'))
        if not candidates:
            raise SystemExit(f'No version dirs found under {base}')
        return candidates[-1].resolve()
    raise SystemExit('Provide either <input> path or --firm + --deal')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input', nargs='?', help='Artifact directory (with 2-sections/ and 1-research/)')
    parser.add_argument('--firm', help='Firm slug (e.g. alpha-jwc)')
    parser.add_argument('--deal', help='Deal slug')
    parser.add_argument('--version', help='Version (e.g. v0.0.3); default: latest')
    parser.add_argument('--dry-run', action='store_true', help='Report what would change without writing')
    args = parser.parse_args()

    artifact_dir = discover_artifact_dir(args)
    sections_dir = artifact_dir / '2-sections'
    research_dir = artifact_dir / '1-research'
    if not sections_dir.is_dir():
        raise SystemExit(f'Missing {sections_dir}')

    section_files = sorted(sections_dir.glob('*.md'))
    if not section_files:
        raise SystemExit(f'No section files in {sections_dir}')

    print(f'Hydrating {len(section_files)} sections under {artifact_dir}')
    total_changed = 0
    total_orphans: Dict[str, List[str]] = {}

    for section_path in section_files:
        stem = section_path.stem  # e.g. 01-risks
        # Match research file: 01-risks-research.md
        research_path = research_dir / f'{stem}-research.md' if research_dir.exists() else None
        if args.dry_run:
            # Just compute without writing
            section_text = section_path.read_text()
            refs = collect_references(section_text)
            existing_defs = parse_definitions(section_text)
            missing = sorted(refs - existing_defs.keys())
            research_defs = parse_definitions(research_path.read_text()) if (research_path and research_path.exists()) else {}
            pullable = [rid for rid in missing if rid in research_defs]
            orphans = [rid for rid in missing if rid not in research_defs]
            if pullable or orphans:
                print(f'  {stem}: would pull {len(pullable)} defs, {len(orphans)} orphans')
            if orphans:
                total_orphans[stem] = orphans
            continue

        changed, orphans = hydrate_section(section_path, research_path)
        if changed:
            total_changed += 1
            print(f'  ✓ {stem}: hydrated from 1-research/')
        if orphans:
            total_orphans[stem] = orphans

    print(f'\n{total_changed} section(s) hydrated' + (' (dry-run)' if args.dry_run else ''))
    if total_orphans:
        print('\nOrphan references (referenced but never defined — will not resolve in export):')
        for stem, ids in total_orphans.items():
            print(f'  {stem}: {", ".join("[^" + i + "]" for i in ids)}')
        sys.exit(2)


if __name__ == '__main__':
    main()

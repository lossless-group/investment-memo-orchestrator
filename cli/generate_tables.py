#!/usr/bin/env python3
"""
Table Generator CLI Tool.

Scans memo sections and structured state data for tabular data opportunities.
Generates markdown tables and inserts them into section files.

Usage:
    # Direct path to output directory
    python -m cli.generate_tables io/humain/deals/Metabologic/outputs/Metabologic-v0.2.1

    # By company name (auto-resolves latest version)
    python -m cli.generate_tables "Metabologic"

    # By company name with specific version
    python -m cli.generate_tables "Metabologic" --version v0.2.1

    # With firm context
    python -m cli.generate_tables "Metabologic" --firm humain

    # Dry run (show what tables would be generated without writing)
    python -m cli.generate_tables "Metabologic" --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename
from src.agents.table_generator import (
    table_generator_agent,
    extract_funding_history,
    extract_team_credentials,
    extract_market_sizing,
    extract_traction_metrics,
    build_markdown_table,
    DEFAULT_TABLE_SCHEMAS,
    find_target_section,
    section_has_table,
)


def resolve_output_dir(company_or_path: str, version: str = None, firm: str = None) -> Path:
    """Resolve to output directory from company name or direct path."""
    path = Path(company_or_path)
    if path.exists() and path.is_dir():
        return path

    safe_name = sanitize_filename(company_or_path)

    # Try firm-scoped path
    if firm:
        deals_dir = Path("io") / firm / "deals" / company_or_path / "outputs"
        if deals_dir.exists():
            if version:
                target = deals_dir / f"{safe_name}-{version}"
                if target.exists():
                    return target
            # Find latest
            matches = sorted(deals_dir.glob(f"{safe_name}-v*"), key=lambda p: p.name)
            if matches:
                return matches[-1]

    # Try auto-detecting firm from io/
    io_dir = Path("io")
    if io_dir.exists():
        for firm_dir in io_dir.iterdir():
            if not firm_dir.is_dir():
                continue
            deals_dir = firm_dir / "deals" / company_or_path / "outputs"
            if deals_dir.exists():
                if version:
                    target = deals_dir / f"{safe_name}-{version}"
                    if target.exists():
                        return target
                matches = sorted(deals_dir.glob(f"{safe_name}-v*"), key=lambda p: p.name)
                if matches:
                    return matches[-1]

    # Legacy fallback
    output_dir = Path("output")
    if version:
        target = output_dir / f"{safe_name}-{version}"
        if target.exists():
            return target
    matches = sorted(output_dir.glob(f"{safe_name}-v*"), key=lambda p: p.name)
    if matches:
        return matches[-1]

    print(f"Error: No output directory found for '{company_or_path}'")
    sys.exit(1)


def load_state(output_dir: Path) -> dict:
    """Load state.json from output directory."""
    state_path = output_dir / "state.json"
    if not state_path.exists():
        print(f"Warning: No state.json found in {output_dir}")
        return {}
    with open(state_path) as f:
        return json.load(f)


def dry_run(state: dict, output_dir: Path):
    """Preview what tables would be generated without writing anything."""
    sections_dir = output_dir / "2-sections"
    if not sections_dir.exists():
        print("No 2-sections/ directory found")
        return

    section_files = sorted(sections_dir.glob("*.md"))
    company_name = state.get("company_name", "Unknown")

    print(f"\n{'='*60}")
    print(f"DRY RUN — Table Generator for {company_name}")
    print(f"Output dir: {output_dir}")
    print(f"{'='*60}\n")

    extractors = [
        ("funding_history", extract_funding_history),
        ("team_credentials", extract_team_credentials),
        ("market_sizing", extract_market_sizing),
        ("traction_metrics", extract_traction_metrics),
    ]

    total_tables = 0

    for table_type, extractor in extractors:
        schema = DEFAULT_TABLE_SCHEMAS.get(table_type)
        if not schema:
            continue

        rows = extractor(state)
        min_rows = schema.get("min_rows", 3)

        print(f"--- {table_type} ---")
        print(f"  Rows extracted: {len(rows)}")
        print(f"  Min required:   {min_rows}")

        if len(rows) < min_rows:
            print(f"  Status: SKIP (insufficient rows)\n")
            continue

        target = find_target_section(section_files, schema["target_sections"])
        if not target:
            print(f"  Status: SKIP (no matching section)\n")
            continue

        content = target.read_text()
        if section_has_table(content):
            print(f"  Status: SKIP (section already has table)\n")
            continue

        table_md, overflow = build_markdown_table(
            schema["columns"], rows, subject_company=company_name
        )

        print(f"  Target:  {target.name}")
        print(f"  Status:  WOULD INSERT")
        print(f"  Preview:")
        for line in table_md.split("\n")[:5]:
            print(f"    {line}")
        if len(table_md.split("\n")) > 5:
            print(f"    ... ({len(rows)} rows total)")
        if overflow:
            print(f"  Overflow anchors: {list(overflow.keys())}")
        print()
        total_tables += 1

    print(f"{'='*60}")
    print(f"Total tables that would be generated: {total_tables}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown tables for investment memo sections"
    )
    parser.add_argument(
        "company_or_path",
        help="Company name or direct path to output directory",
    )
    parser.add_argument(
        "--version", "-v",
        help="Specific version (e.g., v0.2.1)",
    )
    parser.add_argument(
        "--firm", "-f",
        help="Firm name for firm-scoped resolution",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview tables without writing anything",
    )

    args = parser.parse_args()

    # Resolve output directory
    output_dir = resolve_output_dir(
        args.company_or_path,
        version=args.version,
        firm=args.firm,
    )
    print(f"Using output directory: {output_dir}")

    # Load state
    state = load_state(output_dir)
    if not state:
        print("Error: Could not load state.json — structured data extraction requires it")
        sys.exit(1)

    # Set output_dir in state so the agent can find it
    state["output_dir"] = str(output_dir)

    if args.dry_run:
        dry_run(state, output_dir)
    else:
        # Run the full agent (inserts tables into 2-sections/ files)
        result = table_generator_agent(state)
        for msg in result.get("messages", []):
            print(f"  {msg}")

        # Reassemble the final draft so tables appear in the output
        tables_generated = result.get("tables_generated", {})
        total = tables_generated.get("summary", {}).get("total_tables", 0)
        if total > 0:
            try:
                from cli.assemble_draft import assemble_final_draft
                from rich.console import Console
                console = Console()
                print(f"\nReassembling final draft with inserted tables...")
                final_path = assemble_final_draft(output_dir, console, verbose=False)
                print(f"✓ Final draft updated: {final_path}")
            except Exception as e:
                print(f"⚠️  Could not reassemble final draft: {e}")
                print(f"   Run manually: python -m cli.assemble_draft {output_dir}")


if __name__ == "__main__":
    main()

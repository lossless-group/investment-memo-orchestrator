#!/usr/bin/env python3
"""
Diagram Generator CLI Tool.

Generates visual diagrams (TAM/SAM/SOM concentric circles, etc.) from memo
data. Can target a full output directory, a specific section, or a standalone
markdown file.

Usage:
    # Full output directory (auto-resolves latest version)
    python -m cli.generate_diagrams "Metabologic"

    # Specific version
    python -m cli.generate_diagrams "Metabologic" --version v0.2.1

    # Direct path to output directory
    python -m cli.generate_diagrams io/humain/deals/Metabologic/outputs/Metabologic-v0.2.1

    # With firm context
    python -m cli.generate_diagrams "Metabolic" --firm humain

    # Target a specific markdown file (diagram saved next to it)
    python -m cli.generate_diagrams path/to/03-market-context.md

    # Dry run — show what diagrams would be generated
    python -m cli.generate_diagrams "Metabologic" --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename
from src.agents.diagram_generator import (
    extract_market_sizing_data,
    render_tam_sam_som,
    insert_diagram_reference,
    find_market_section,
    _parse_dollar_value,
    _format_dollar_label,
)


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


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

    return None


def load_state(output_dir: Path) -> dict:
    """Load state.json from output directory."""
    state_path = output_dir / "state.json"
    if not state_path.exists():
        return {}
    with open(state_path) as f:
        return json.load(f)


def extract_market_data_from_markdown(file_path: Path) -> dict:
    """
    Scan a markdown file for TAM/SAM/SOM values mentioned in prose.

    Looks for patterns like:
      - TAM of $50B, SAM of $12B, SOM of $800M
      - Total Addressable Market: $50 billion
      - $50B TAM
    """
    import re

    content = file_path.read_text()
    result = {}

    # Pattern: TAM/SAM/SOM followed by dollar amount
    patterns = [
        (r"(?:TAM|[Tt]otal\s+[Aa]ddressable\s+[Mm]arket)[:\s]+\$?([\d,.]+\s*(?:T|B|billion|M|million|K|thousand)?)", "tam"),
        (r"\$?([\d,.]+\s*(?:T|B|billion|M|million|K|thousand)?)\s*TAM", "tam"),
        (r"(?:SAM|[Ss]erviceable\s+[Aa]ddressable\s+[Mm]arket)[:\s]+\$?([\d,.]+\s*(?:T|B|billion|M|million|K|thousand)?)", "sam"),
        (r"\$?([\d,.]+\s*(?:T|B|billion|M|million|K|thousand)?)\s*SAM", "sam"),
        (r"(?:SOM|[Ss]erviceable\s+[Oo]btainable\s+[Mm]arket)[:\s]+\$?([\d,.]+\s*(?:T|B|billion|M|million|K|thousand)?)", "som"),
        (r"\$?([\d,.]+\s*(?:T|B|billion|M|million|K|thousand)?)\s*SOM", "som"),
    ]

    for pattern, key in patterns:
        if key in result:
            continue
        match = re.search(pattern, content)
        if match:
            raw = "$" + match.group(1).strip()
            parsed = _parse_dollar_value(raw)
            if parsed:
                result[key] = parsed

    return result


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def run_from_output_dir(output_dir: Path, dry_run: bool = False):
    """Run diagram generation using state.json from an output directory."""
    state = load_state(output_dir)
    company_name = state.get("company_name", output_dir.name.rsplit("-v", 1)[0])

    # Extract market data from state
    market_data = extract_market_sizing_data(state) if state else {}

    # If state didn't have market data, try scanning the market section file
    if not all(k in market_data for k in ("tam", "sam", "som")):
        sections_dir = output_dir / "2-sections"
        if sections_dir.exists():
            market_section = find_market_section(sections_dir)
            if market_section:
                prose_data = extract_market_data_from_markdown(market_section)
                for k, v in prose_data.items():
                    if k not in market_data:
                        market_data[k] = v

    # Also try the final draft
    if not all(k in market_data for k in ("tam", "sam", "som")):
        for draft in output_dir.glob("*final-draft*"):
            prose_data = extract_market_data_from_markdown(draft)
            for k, v in prose_data.items():
                if k not in market_data:
                    market_data[k] = v

    tam = market_data.get("tam")
    sam = market_data.get("sam")
    som = market_data.get("som")

    if not (tam and sam and som):
        missing = [k.upper() for k in ("tam", "sam", "som") if k not in market_data]
        print(f"Insufficient market data (missing: {', '.join(missing)})")
        print("Provide TAM/SAM/SOM values manually with --tam, --sam, --som flags")
        return

    growth_rates = {k: v for k, v in market_data.items() if k.endswith("_growth") or k == "cagr"}
    diagrams_dir = output_dir / "diagrams"

    print(f"\nCompany:  {company_name}")
    print(f"TAM:      {_format_dollar_label(tam)}")
    print(f"SAM:      {_format_dollar_label(sam)}")
    print(f"SOM:      {_format_dollar_label(som)}")
    if growth_rates:
        for k, v in growth_rates.items():
            print(f"{k}:  {v}")
    print(f"Output:   {diagrams_dir}/")

    if dry_run:
        print("\n[DRY RUN] Would generate TAM/SAM/SOM diagram — no files written")
        return

    svg_path, png_path = render_tam_sam_som(
        tam=tam, sam=sam, som=som,
        output_path=diagrams_dir,
        growth_rates=growth_rates if growth_rates else None,
        company_name=company_name,
    )
    print(f"\n✓ SVG: {svg_path}")
    print(f"✓ PNG: {png_path}")

    # Insert reference into market section
    sections_dir = output_dir / "2-sections"
    if sections_dir.exists():
        market_section = find_market_section(sections_dir)
        if market_section:
            inserted = insert_diagram_reference(
                market_section,
                svg_path.name,
                alt_text=f"{company_name} TAM/SAM/SOM Market Sizing",
            )
            if inserted:
                print(f"✓ Image reference inserted into {market_section.name}")
            else:
                print(f"⊘ Diagram already referenced in {market_section.name}")

    # Save manifest
    manifest = {
        "company": company_name,
        "diagrams": [{
            "id": "tam-sam-som",
            "type": "concentric_circles",
            "renderer": "matplotlib",
            "svg_path": f"diagrams/{svg_path.name}",
            "png_path": f"diagrams/{png_path.name}",
            "data": {"tam": tam, "sam": sam, "som": som, **growth_rates},
        }],
    }
    (diagrams_dir / "diagram-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )
    print(f"✓ Manifest: {diagrams_dir / 'diagram-manifest.json'}")


def run_from_file(
    file_path: Path,
    tam: float = None,
    sam: float = None,
    som: float = None,
    dry_run: bool = False,
):
    """Run diagram generation targeting a specific markdown file."""
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Try to extract values from the file if not provided via flags
    prose_data = extract_market_data_from_markdown(file_path)
    tam = tam or prose_data.get("tam")
    sam = sam or prose_data.get("sam")
    som = som or prose_data.get("som")

    if not (tam and sam and som):
        missing = []
        if not tam: missing.append("--tam")
        if not sam: missing.append("--sam")
        if not som: missing.append("--som")
        print(f"Could not find TAM/SAM/SOM in {file_path.name}")
        print(f"Provide values manually: {' '.join(missing)}")
        sys.exit(1)

    # Determine output location
    # If file is inside an output dir structure, use diagrams/ next to 2-sections/
    parent = file_path.parent
    if parent.name == "2-sections":
        diagrams_dir = parent.parent / "diagrams"
    else:
        diagrams_dir = parent / "diagrams"

    # Derive company name from file path or parent directory
    company_name = ""
    if parent.name == "2-sections":
        # output dir name like Metabologic-v0.2.1
        company_name = parent.parent.name.rsplit("-v", 1)[0].replace("-", " ")
    else:
        company_name = file_path.stem.replace("-", " ").title()

    print(f"\nFile:     {file_path}")
    print(f"Company:  {company_name}")
    print(f"TAM:      {_format_dollar_label(tam)}")
    print(f"SAM:      {_format_dollar_label(sam)}")
    print(f"SOM:      {_format_dollar_label(som)}")
    print(f"Output:   {diagrams_dir}/")

    if dry_run:
        print("\n[DRY RUN] Would generate TAM/SAM/SOM diagram — no files written")
        return

    svg_path, png_path = render_tam_sam_som(
        tam=tam, sam=sam, som=som,
        output_path=diagrams_dir,
        company_name=company_name,
    )
    print(f"\n✓ SVG: {svg_path}")
    print(f"✓ PNG: {png_path}")

    # Insert reference into the target file
    inserted = insert_diagram_reference(
        file_path,
        svg_path.name,
        alt_text=f"{company_name} TAM/SAM/SOM Market Sizing",
    )
    if inserted:
        print(f"✓ Image reference inserted into {file_path.name}")
    else:
        print(f"⊘ Diagram already referenced in {file_path.name}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Generate visual diagrams for investment memo sections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From company name (uses state.json for data)
  python -m cli.generate_diagrams "Metabologic"

  # Specific version
  python -m cli.generate_diagrams "Metabologic" --version v0.2.1

  # Direct path to output directory
  python -m cli.generate_diagrams io/humain/deals/Metabologic/outputs/Metabologic-v0.2.1

  # Target a specific .md file (extracts data from prose)
  python -m cli.generate_diagrams path/to/03-market-context.md

  # Provide values manually for any target
  python -m cli.generate_diagrams path/to/memo.md --tam 50B --sam 12B --som 800M

  # Dry run
  python -m cli.generate_diagrams "Metabologic" --dry-run
""",
    )
    parser.add_argument(
        "target",
        help="Company name, path to output directory, or path to a .md file",
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
        "--tam",
        help="TAM value (e.g., 50B, $50B, '50 billion')",
    )
    parser.add_argument(
        "--sam",
        help="SAM value (e.g., 12B, $12B, '12 billion')",
    )
    parser.add_argument(
        "--som",
        help="SOM value (e.g., 800M, $800M, '800 million')",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be generated without writing files",
    )

    args = parser.parse_args()

    # Parse manual TAM/SAM/SOM overrides
    manual_tam = _parse_dollar_value(f"${args.tam}") if args.tam else None
    manual_sam = _parse_dollar_value(f"${args.sam}") if args.sam else None
    manual_som = _parse_dollar_value(f"${args.som}") if args.som else None

    target = Path(args.target)

    # Case 1: Target is a .md file
    if target.exists() and target.is_file() and target.suffix == ".md":
        run_from_file(
            file_path=target,
            tam=manual_tam,
            sam=manual_sam,
            som=manual_som,
            dry_run=args.dry_run,
        )
        return

    # Case 2: Target is an output directory or company name
    output_dir = resolve_output_dir(args.target, version=args.version, firm=args.firm)
    if not output_dir:
        print(f"Error: No output directory found for '{args.target}'")
        sys.exit(1)

    print(f"Using output directory: {output_dir}")

    # If manual values provided, inject them into state
    if manual_tam or manual_sam or manual_som:
        state = load_state(output_dir)
        company_name = state.get("company_name", output_dir.name.rsplit("-v", 1)[0])

        # Build market data from manual + state
        market_data = extract_market_sizing_data(state) if state else {}
        if manual_tam:
            market_data["tam"] = manual_tam
        if manual_sam:
            market_data["sam"] = manual_sam
        if manual_som:
            market_data["som"] = manual_som

        tam = market_data.get("tam")
        sam = market_data.get("sam")
        som = market_data.get("som")

        if not (tam and sam and som):
            missing = [k.upper() for k in ("tam", "sam", "som") if k not in market_data]
            print(f"Still missing: {', '.join(missing)}")
            sys.exit(1)

        growth_rates = {k: v for k, v in market_data.items() if k.endswith("_growth") or k == "cagr"}
        diagrams_dir = output_dir / "diagrams"

        print(f"\nCompany:  {company_name}")
        print(f"TAM:      {_format_dollar_label(tam)}")
        print(f"SAM:      {_format_dollar_label(sam)}")
        print(f"SOM:      {_format_dollar_label(som)}")

        if args.dry_run:
            print("\n[DRY RUN] Would generate TAM/SAM/SOM diagram — no files written")
            return

        svg_path, png_path = render_tam_sam_som(
            tam=tam, sam=sam, som=som,
            output_path=diagrams_dir,
            growth_rates=growth_rates if growth_rates else None,
            company_name=company_name,
        )
        print(f"\n✓ SVG: {svg_path}")
        print(f"✓ PNG: {png_path}")

        # Insert into market section if present
        sections_dir = output_dir / "2-sections"
        if sections_dir.exists():
            market_section = find_market_section(sections_dir)
            if market_section:
                inserted = insert_diagram_reference(
                    market_section, svg_path.name,
                    alt_text=f"{company_name} TAM/SAM/SOM Market Sizing",
                )
                if inserted:
                    print(f"✓ Image reference inserted into {market_section.name}")
    else:
        run_from_output_dir(output_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

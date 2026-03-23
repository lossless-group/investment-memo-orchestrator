#!/usr/bin/env python3
"""
One-Pager Generator CLI Tool.

Generates a single-page visual investment summary from a completed memo output.
Can be run independently on any output directory without the full pipeline.

Usage:
    # Direct path to output directory
    python -m cli.generate_one_pager io/humain/deals/Metabologic/outputs/Metabologic-v0.2.4

    # By company name (auto-resolves latest version)
    python -m cli.generate_one_pager "Metabologic"

    # With firm and version
    python -m cli.generate_one_pager "Metabologic" --firm humain --version v0.2.4

    # Dark mode
    python -m cli.generate_one_pager "Metabologic" --firm humain --mode dark

    # Dry run (show extracted slots without rendering)
    python -m cli.generate_one_pager "Metabologic" --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename


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


def main():
    parser = argparse.ArgumentParser(
        description="Generate a one-page investment summary from a completed memo output"
    )
    parser.add_argument(
        "company_or_path",
        help="Company name (e.g., 'Metabologic') or path to output directory"
    )
    parser.add_argument("--version", "-v", help="Specific version (e.g., 'v0.2.4')")
    parser.add_argument("--firm", "-f", help="Firm name (e.g., 'humain')")
    parser.add_argument("--brand", "-b", help="Brand config name (defaults to firm)")
    parser.add_argument("--mode", "-m", choices=["light", "dark"], default="light",
                        help="Color mode (default: light)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Extract and display content slots without rendering")

    args = parser.parse_args()

    # Resolve output directory
    output_dir = resolve_output_dir(args.company_or_path, args.version, args.firm)
    print(f"Output directory: {output_dir}")

    # Load state
    state = load_state(output_dir)
    if not state:
        print("Error: Could not load state.json")
        sys.exit(1)

    state["output_dir"] = str(output_dir)
    company_name = state.get("company_name", args.company_or_path)
    investment_type = state.get("investment_type", "direct")

    # Find final draft
    from src.final_draft import find_final_draft, read_final_draft
    final_draft_path = find_final_draft(output_dir)
    if not final_draft_path:
        print(f"Error: No final draft found in {output_dir}")
        sys.exit(1)

    final_draft_text = read_final_draft(output_dir)
    print(f"Final draft: {final_draft_path.name} ({len(final_draft_text)} chars)")

    # Extract content via Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    from src.agents.one_pager_generator import (
        _build_extraction_prompt,
        _parse_extraction_response,
        render_one_pager,
    )
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    prompt = _build_extraction_prompt(final_draft_text, state, investment_type)

    print(f"\nExtracting content slots for {company_name}...")
    try:
        response = client.messages.create(
            model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
            max_tokens=2000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        slots = _parse_extraction_response(response.content[0].text)
    except Exception as e:
        print(f"Error extracting content: {e}")
        sys.exit(1)

    # Save extracted content
    content_path = output_dir / "8-one-pager-content.json"
    with open(content_path, "w") as f:
        json.dump(slots, f, indent=2, ensure_ascii=False)
    print(f"Content slots saved: {content_path}")

    # Dry run: just show the slots
    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — Extracted Content Slots")
        print(f"{'='*60}\n")
        print(json.dumps(slots, indent=2))
        print(f"\n{'='*60}")
        print("To render, run again without --dry-run")
        return

    # Load brand config
    from src.branding import BrandConfig
    brand_name = args.brand or args.firm or state.get("firm")
    brand = BrandConfig.load(brand_name=brand_name, firm=args.firm or state.get("firm"))

    # Render HTML
    html_content = render_one_pager(slots, state, brand_config=brand, mode=args.mode)
    html_path = output_dir / "8-one-pager.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"HTML rendered: {html_path}")

    # Convert to PDF
    try:
        from weasyprint import HTML
        pdf_path = output_dir / "8-one-pager.pdf"
        HTML(string=html_content, base_url=str(output_dir)).write_pdf(str(pdf_path))
        print(f"PDF generated: {pdf_path}")
    except Exception as e:
        print(f"Warning: PDF generation failed: {e}")
        pdf_path = None

    # Summary
    print(f"\nOne-pager generated for {company_name}")
    print(f"  HTML: {html_path}")
    if pdf_path:
        print(f"  PDF:  {pdf_path}")
    print(f"  Data: {content_path}")


if __name__ == "__main__":
    main()

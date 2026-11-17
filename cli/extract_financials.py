#!/usr/bin/env python3
"""Re-run only the financial extractor against a finished dataroom analysis.

Rewrites 3-financial-analysis.json/.md without re-scanning or re-classifying the
dataroom: the saved inventory already says which documents are financial.

Usage examples:

    # Firm-scoped: the latest version of a deal
    python cli/extract_financials.py --firm humain --deal New-Silicon
    python cli/extract_financials.py --firm humain --deal New-Silicon --version v0.0.2

    # Any directory holding 0-dataroom-inventory.json (e.g. a dataroom-only run)
    python cli/extract_financials.py io/humain/deals/New-Silicon/dataroom-analysis/NSC-Dataroom-2026-10-23
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure project root on path so src.* imports work when needed
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from src.paths import resolve_deal_context, get_latest_output_dir_for_deal

FINANCIAL_TYPES = ("financial_statements", "financial_projections")


def resolve_analysis_dir(target: Optional[str], firm: Optional[str],
                         deal: Optional[str], version: Optional[str]) -> Path:
    """Resolve the directory that holds the dataroom analysis artifacts."""
    if target and Path(target).is_dir():
        return Path(target)

    ctx = resolve_deal_context(deal or target, firm=firm)
    if version:
        candidates = [p for p in ctx.outputs_dir.glob(f"*-{version}") if p.is_dir()]
        if not candidates:
            raise FileNotFoundError(f"No output directory for {version} in {ctx.outputs_dir}")
        return candidates[0]
    return get_latest_output_dir_for_deal(ctx)


def company_name_for(analysis_dir: Path, firm: Optional[str], deal: Optional[str]) -> str:
    """Prefer the deal config's legal name, so it is stripped from filenames as the pipeline does."""
    if deal:
        try:
            ctx = resolve_deal_context(deal, firm=firm)
            config = json.loads(ctx.deal_json_path.read_text())
            return config.get("legal_name") or config.get("name") or deal
        except (OSError, ValueError, AttributeError):
            return deal
    return analysis_dir.name


def backup(path: Path) -> None:
    """Keep the previous output beside the new one, stamped, so the two can be compared."""
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        shutil.copy(path, path.with_name(f"{path.stem}.bak-{stamp}{path.suffix}"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Re-run only the financial extractor against a finished dataroom analysis "
            "and rewrite 3-financial-analysis.json/.md."
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Path to a directory holding 0-dataroom-inventory.json, or a deal name.",
    )
    parser.add_argument("--firm", help="Firm name for firm-scoped IO (e.g., 'humain').")
    parser.add_argument("--deal", help="Deal name when using --firm.")
    parser.add_argument("--version", help="Specific version (e.g., 'v0.0.2'); default is the latest.")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Overwrite the previous output without keeping a .bak copy.",
    )
    args = parser.parse_args()

    if not args.firm:
        args.firm = os.environ.get("MEMO_DEFAULT_FIRM")
    if not args.target and not args.deal:
        parser.error("provide a target path, or --firm and --deal")

    load_dotenv(Path(__file__).parent.parent / ".env")

    # Imported after load_dotenv so the provider sees the keys.
    from src.agents.dataroom.extractors.financial_extractor import extract_financial_data
    from src.agents.dataroom.dataroom_analyzer import format_financial_report

    analysis_dir = resolve_analysis_dir(args.target, args.firm, args.deal, args.version)
    inventory_path = analysis_dir / "0-dataroom-inventory.json"
    if not inventory_path.exists():
        print(f"Error: no 0-dataroom-inventory.json in {analysis_dir}. "
              "Run the dataroom stage first.")
        sys.exit(1)

    inventory = json.loads(inventory_path.read_text())
    # The end-of-run writer uses "inventory"; the mid-run checkpoint uses "documents".
    docs = inventory.get("inventory") or inventory.get("documents") or []
    financial_docs = [d for d in docs if d.get("document_type") in FINANCIAL_TYPES]
    if not financial_docs:
        print(f"No documents classified as {' or '.join(FINANCIAL_TYPES)} in {analysis_dir}.")
        sys.exit(1)

    company_name = company_name_for(analysis_dir, args.firm, args.deal)
    print(f"Analysis: {analysis_dir}")
    print(f"💰 Extracting financial data from {len(financial_docs)} documents...")
    for d in financial_docs:
        print(f"   · {d['filename']}")

    financials = extract_financial_data(financial_docs, use_llm=True)
    if not financials:
        print("Error: extraction returned nothing; previous output left untouched.")
        sys.exit(1)

    json_path = analysis_dir / "3-financial-analysis.json"
    md_path = analysis_dir / "3-financial-analysis.md"
    if not args.no_backup:
        backup(json_path)
        backup(md_path)
    json_path.write_text(json.dumps(financials, indent=2, ensure_ascii=False, default=str))
    md_path.write_text(format_financial_report(financials, company_name))
    print(f"   📄 Saved: {json_path.name}, {md_path.name}")

    # A later memo run reuses this analysis, and reads state.json before the
    # artifacts. Without this, the new financials would be ignored on reuse.
    state_path = analysis_dir / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if isinstance(state.get("dataroom_analysis"), dict):
            if not args.no_backup:
                backup(state_path)
            state["dataroom_analysis"]["financials"] = financials
            state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str))
            print(f"   📄 Updated: {state_path.name} (dataroom_analysis.financials)")

    cash = financials.get("cash")
    currency = financials.get("currency", "")
    print(f"✓ Done. Cash: {cash:,} {currency}" if isinstance(cash, (int, float)) else "✓ Done.")
    print("  6-synthesis-report was built from the previous financials; it is not regenerated here.")


if __name__ == "__main__":
    main()

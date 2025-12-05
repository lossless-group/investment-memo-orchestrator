#!/usr/bin/env python3
"""
CLI tool to revise Executive Summary and Closing Assessment based on complete memo.

Usage:
    python -m src.cli.revise_summaries "CompanyName"
    python -m src.cli.revise_summaries "CompanyName" --version v0.0.4
    python -m src.cli.revise_summaries "CompanyName" --firm hypernova
    python -m src.cli.revise_summaries "CompanyName" --dry-run

This tool reads the complete final draft and rewrites the bookend sections
(Executive Summary and Closing Assessment) to accurately reflect the actual
memo content, removing false hedging and adding specific metrics.
"""

import argparse
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agents.revise_summary_sections import revise_summaries_cli


def main():
    parser = argparse.ArgumentParser(
        description="Revise Executive Summary and Closing Assessment based on complete memo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.cli.revise_summaries "Reson8"
    python -m src.cli.revise_summaries "ProfileHealth" --version v0.0.2
    python -m src.cli.revise_summaries "Andela" --firm hypernova
    python -m src.cli.revise_summaries "Reson8" --dry-run

The tool will:
1. Read the complete 4-final-draft.md
2. Extract key metrics (funding, traction, market) from the body
3. Rewrite Executive Summary with specific data (no false hedging)
4. Rewrite Closing Assessment with synthesized recommendation
5. Reassemble the final draft with revised sections
        """
    )

    parser.add_argument(
        "company",
        help="Company name (e.g., 'Reson8', 'ProfileHealth')"
    )

    parser.add_argument(
        "--version", "-v",
        help="Specific version to revise (e.g., 'v0.0.4'). Default: latest"
    )

    parser.add_argument(
        "--firm", "-f",
        help="Firm name for firm-scoped IO (e.g., 'hypernova', 'dark-matter')"
    )

    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview what would be extracted without making changes"
    )

    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"REVISE SUMMARY SECTIONS")
    print(f"{'=' * 60}")
    print(f"Company: {args.company}")
    if args.version:
        print(f"Version: {args.version}")
    if args.firm:
        print(f"Firm: {args.firm}")
    if args.dry_run:
        print(f"Mode: DRY RUN (no changes will be made)")
    print(f"{'=' * 60}\n")

    try:
        result = revise_summaries_cli(
            company_name=args.company,
            version=args.version,
            firm=args.firm,
            dry_run=args.dry_run
        )

        print(f"\n{'=' * 60}")
        print("RESULT")
        print(f"{'=' * 60}")
        for msg in result.get("messages", []):
            print(f"  • {msg}")
        print(f"{'=' * 60}\n")

    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("Make sure the company name is correct and a memo has been generated.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

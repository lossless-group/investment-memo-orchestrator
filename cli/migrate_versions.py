#!/usr/bin/env python3
"""
Migration script to split legacy versions.json into firm-scoped versions.

Usage:
    # Dry run - see what would be migrated
    python cli/migrate_versions.py --firm hypernova --dry-run

    # Actually migrate
    python cli/migrate_versions.py --firm hypernova

    # Migrate specific deals only
    python cli/migrate_versions.py --firm hypernova --deals Aalo,Ontra,Avalanche
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.versioning import (
    migrate_versions_to_firm,
    get_firm_deals,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_IO_ROOT,
)


# Name mappings: legacy name -> new deal folder name
LEGACY_NAME_MAPPINGS = {
    "Aalo-Atomics": "Aalo",
    "Kearny-Jackson": "KearnyJackson",
    "Bear-AI": "BearAI",
    "Work-Back-AI": "WorkBack",
    "Watershed-VC": "WatershedVC",
}


def get_legacy_name(deal_name: str, legacy_data: dict) -> str:
    """Find the legacy name for a deal folder name."""
    # Direct match
    if deal_name in legacy_data:
        return deal_name

    # Check reverse mappings
    for legacy, new in LEGACY_NAME_MAPPINGS.items():
        if new == deal_name and legacy in legacy_data:
            return legacy

    return deal_name


def main():
    parser = argparse.ArgumentParser(
        description="Migrate deals from legacy versions.json to firm-scoped versions"
    )
    parser.add_argument(
        "--firm",
        required=True,
        help="Target firm name (e.g., 'hypernova')"
    )
    parser.add_argument(
        "--deals",
        help="Comma-separated list of deals to migrate (default: all deals in io/{firm}/deals/)"
    )
    parser.add_argument(
        "--legacy-file",
        default="output/versions.json",
        help="Path to legacy versions.json (default: output/versions.json)"
    )
    parser.add_argument(
        "--io-root",
        default="io",
        help="IO root directory (default: io)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes"
    )

    args = parser.parse_args()

    legacy_file = Path(args.legacy_file)
    io_root = Path(args.io_root)

    # Determine deals to migrate
    if args.deals:
        deals = [d.strip() for d in args.deals.split(",")]
    else:
        # Auto-detect from io/{firm}/deals/ directory
        deals = get_firm_deals(io_root, args.firm)
        if not deals:
            print(f"No deals found in {io_root}/{args.firm}/deals/")
            print("Use --deals to specify deals manually")
            return 1

    print(f"Migration {'(DRY RUN)' if args.dry_run else ''}")
    print(f"  Firm: {args.firm}")
    print(f"  Legacy file: {legacy_file}")
    print(f"  IO root: {io_root}")
    print(f"  Deals to migrate: {len(deals)}")
    print()

    # Load legacy data to show what exists
    legacy_data = {}
    if legacy_file.exists():
        with open(legacy_file) as f:
            legacy_data = json.load(f)
        print(f"Legacy versions.json contains {len(legacy_data)} deals:")

        # Build mapping of deal folder name -> legacy name
        deal_to_legacy = {}
        for deal in deals:
            legacy_name = get_legacy_name(deal, legacy_data)
            deal_to_legacy[deal] = legacy_name

        for legacy_deal in sorted(legacy_data.keys()):
            # Check if this legacy deal maps to any of our target deals
            is_target = legacy_deal in deal_to_legacy.values()
            marker = "→" if is_target else " "
            # Show the mapping if different
            mapped_to = ""
            for deal, legacy in deal_to_legacy.items():
                if legacy == legacy_deal and deal != legacy_deal:
                    mapped_to = f" (→ {deal})"
                    break
            print(f"  {marker} {legacy_deal}{mapped_to}")
        print()

    # Build list of legacy names to migrate
    legacy_names_to_migrate = []
    deal_name_mapping = {}  # legacy_name -> new_deal_name
    for deal in deals:
        legacy_name = get_legacy_name(deal, legacy_data)
        legacy_names_to_migrate.append(legacy_name)
        if legacy_name != deal:
            deal_name_mapping[legacy_name] = deal

    # Run migration with legacy names
    results = migrate_versions_to_firm(
        legacy_versions_file=legacy_file,
        firm=args.firm,
        deals_to_migrate=legacy_names_to_migrate,
        io_root=io_root,
        dry_run=args.dry_run
    )

    # Rename keys in firm_versions to use new deal names
    if deal_name_mapping and results['firm_versions']:
        renamed_versions = {}
        for key, value in results['firm_versions'].items():
            new_key = deal_name_mapping.get(key, key)
            # Also update file paths to use new deal name
            if key in deal_name_mapping:
                new_deal = deal_name_mapping[key]
                for entry in value.get('history', []):
                    old_path = entry.get('file_path', '')
                    # Update path: deals/{old}/outputs/... -> deals/{new}/outputs/...
                    entry['file_path'] = old_path.replace(f"deals/{key}/", f"deals/{new_deal}/")
            renamed_versions[new_key] = value
        results['firm_versions'] = renamed_versions

        # If not dry run, re-save with correct names
        if not args.dry_run:
            from src.versioning import VersionManager
            firm_vm = VersionManager(firm=args.firm, io_root=io_root)
            firm_vm.versions_data = renamed_versions
            firm_vm._save_versions()
            print(f"Re-saved with renamed deals to: {firm_vm.versions_file}")

    # Report results
    print("Results:")
    print(f"  Migrated: {len(results['migrated'])}")
    for deal in results['migrated']:
        new_name = deal_name_mapping.get(deal, deal)
        if deal != new_name:
            print(f"    ✓ {deal} → {new_name}")
        else:
            print(f"    ✓ {deal}")

    if results['skipped']:
        print(f"  Skipped (not in legacy): {len(results['skipped'])}")
        for deal in results['skipped']:
            print(f"    - {deal}")

    if args.dry_run:
        print()
        print("This was a dry run. Run without --dry-run to apply changes.")
        print(f"Would create: {io_root}/{args.firm}/versions.json")
    else:
        print()
        print(f"Created: {io_root}/{args.firm}/versions.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())

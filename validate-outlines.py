#!/usr/bin/env python3
"""
Validate outline YAML files against the JSON schema.
"""

import json
import yaml
from pathlib import Path
from jsonschema import validate, ValidationError

def validate_outline(outline_path: Path, schema_path: Path) -> bool:
    """
    Validate an outline YAML file against the schema.

    Args:
        outline_path: Path to outline YAML file
        schema_path: Path to JSON schema file

    Returns:
        True if valid, False otherwise
    """
    try:
        # Load schema
        with open(schema_path, 'r') as f:
            schema = json.load(f)

        # Load outline
        with open(outline_path, 'r') as f:
            outline = yaml.safe_load(f)

        # Validate
        validate(instance=outline, schema=schema)

        print(f"✓ {outline_path.name} is valid")

        # Count sections with preferred_sources
        sections_with_sources = sum(
            1 for section in outline.get('sections', [])
            if 'preferred_sources' in section
        )

        print(f"  - {sections_with_sources} sections have preferred_sources defined")

        return True

    except ValidationError as e:
        print(f"✗ {outline_path.name} validation failed:")
        print(f"  Error: {e.message}")
        print(f"  Path: {' > '.join(str(p) for p in e.path)}")
        return False
    except Exception as e:
        print(f"✗ {outline_path.name} error: {e}")
        return False

def main():
    """Validate all outline files."""

    print("=" * 60)
    print("Validating Outline YAML Files")
    print("=" * 60)

    base_dir = Path(__file__).parent
    schema_path = base_dir / "templates" / "outlines" / "sections-schema.json"
    outlines_dir = base_dir / "templates" / "outlines"

    if not schema_path.exists():
        print(f"✗ Schema not found: {schema_path}")
        return False

    # Validate both outline files
    outline_files = [
        outlines_dir / "direct-investment.yaml",
        outlines_dir / "fund-commitment.yaml"
    ]

    results = []
    for outline_path in outline_files:
        if not outline_path.exists():
            print(f"✗ Outline not found: {outline_path}")
            results.append(False)
            continue

        print(f"\nValidating {outline_path.name}...")
        results.append(validate_outline(outline_path, schema_path))

    print("\n" + "=" * 60)
    if all(results):
        print("✓ All outlines are valid!")
        print("=" * 60)
        return True
    else:
        print("✗ Some outlines failed validation")
        print("=" * 60)
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

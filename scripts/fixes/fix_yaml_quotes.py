#!/usr/bin/env python3
"""Fix YAML quoting issues in outline files."""

import re
from pathlib import Path

def fix_yaml_quotes(file_path: Path):
    """Fix list items that have quoted text followed by unquoted parentheses."""

    with open(file_path, 'r') as f:
        content = f.read()

    # Pattern: list item starting with "text" followed by space and (
    # Example: - "term" (note)
    # Should be: - "term (note)"
    pattern = r'^(\s+- )"([^"]+)"\s+\(([^)]+)\)'

    def replace_func(match):
        indent = match.group(1)
        text = match.group(2)
        note = match.group(3)
        return f'{indent}"{text} ({note})"'

    fixed_content = re.sub(pattern, replace_func, content, flags=re.MULTILINE)

    # Also fix unquoted list items that contain colons and parentheses
    # Example: - Term: "value" (note)
    # Should be: - "Term: value (note)"
    pattern2 = r'^(\s+- )([A-Z][^:]+): "([^"]+)"\s+\(([^)]+)\)'

    def replace_func2(match):
        indent = match.group(1)
        term = match.group(2)
        value = match.group(3)
        note = match.group(4)
        return f'{indent}"{term}: {value} ({note})"'

    fixed_content = re.sub(pattern2, replace_func2, fixed_content, flags=re.MULTILINE)

    with open(file_path, 'w') as f:
        f.write(fixed_content)

    print(f"✅ Fixed {file_path.name}")

if __name__ == "__main__":
    # Fix both outline files
    outlines_dir = Path("templates/outlines")

    fix_yaml_quotes(outlines_dir / "fund-commitment.yaml")

    print("\nValidating YAML files...")
    import yaml

    for yaml_file in [outlines_dir / "fund-commitment.yaml"]:
        try:
            with open(yaml_file, 'r') as f:
                yaml.safe_load(f)
            print(f"✅ {yaml_file.name} parses successfully")
        except yaml.YAMLError as e:
            print(f"❌ {yaml_file.name} has errors: {e}")

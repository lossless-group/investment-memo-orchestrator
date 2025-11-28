#!/usr/bin/env python3
"""Recompile a memo from sections and consolidate citations.

Usage examples:

    # Recompile latest version for Aito
    python cli/recompile_memo.py "Aito"

    # Recompile a specific version
    python cli/recompile_memo.py "Aito" --version v0.0.2

    # Recompile using an explicit artifact directory
    python cli/recompile_memo.py output/Aito-v0.0.2
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Ensure project root on path so src.* imports work when needed
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename
from src.versioning import VersionManager


def resolve_artifact_dir(target: str, version: Optional[str]) -> Path:
    """Resolve an artifact directory from a company name or explicit path."""
    target_path = Path(target)
    if target_path.exists() and target_path.is_dir():
        return target_path

    safe_name = sanitize_filename(target)
    output_root = Path("output")

    if version:
        artifact_dir = output_root / f"{safe_name}-{version}"
    else:
        version_mgr = VersionManager(output_root)
        if safe_name not in version_mgr.versions_data:
            raise FileNotFoundError(
                f"No versions found for '{target}' in output/versions.json"
            )
        latest_version = version_mgr.versions_data[safe_name]["latest_version"]
        artifact_dir = output_root / f"{safe_name}-{latest_version}"

    if not artifact_dir.exists():
        raise FileNotFoundError(f"Artifact directory not found: {artifact_dir}")

    return artifact_dir


def assemble_sections(artifact_dir: Path) -> Path:
    """Concatenate header + 2-sections/*.md into 4-final-draft.md.

    Sections are ordered lexicographically by filename (e.g., 01-*, 02-* ...).
    """
    header_path = artifact_dir / "header.md"
    sections_dir = artifact_dir / "2-sections"

    if not sections_dir.exists():
        raise FileNotFoundError(f"Sections directory not found: {sections_dir}")

    parts: list[str] = []

    if header_path.exists():
        parts.append(header_path.read_text(encoding="utf-8").rstrip() + "\n\n")

    section_files = sorted(sections_dir.glob("*.md"))
    if not section_files:
        raise FileNotFoundError(f"No section files found in {sections_dir}")

    for section_file in section_files:
        content = section_file.read_text(encoding="utf-8").rstrip()
        parts.append(content + "\n\n")

    final_draft = artifact_dir / "4-final-draft.md"
    final_draft.write_text("".join(parts).rstrip() + "\n", encoding="utf-8")
    return final_draft


def run_consolidate_citations(final_draft: Path) -> None:
    """Run the consolidate_citations CLI on the given final draft."""
    script_path = Path(__file__).parent / "utils" / "consolidate_citations.py"
    if not script_path.exists():
        print(
            "Warning: consolidate_citations.py not found; skipping citation consolidation."
        )
        return

    cmd = [sys.executable, str(script_path), str(final_draft)]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        print("Warning: consolidate_citations.py exited with non-zero status")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Recompile a memo from its sections (2-sections/*.md) into 4-final-draft.md "
            "and consolidate citations."
        )
    )

    parser.add_argument(
        "target",
        help=(
            "Company name (e.g., 'Aito') or path to artifact directory "
            "(e.g., output/Aito-v0.0.2)"
        ),
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.2') if target is a company name.",
    )

    args = parser.parse_args()

    try:
        artifact_dir = resolve_artifact_dir(args.target, args.version)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Artifact directory: {artifact_dir}")

    # Assemble sections
    final_draft = assemble_sections(artifact_dir)
    print(f"✓ Assembled sections into: {final_draft}")

    # Consolidate citations
    run_consolidate_citations(final_draft)


if __name__ == "__main__":  # pragma: no cover
    main()

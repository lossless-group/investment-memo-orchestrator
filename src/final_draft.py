"""
Final Draft Utilities - Single source of truth for final draft file operations.

This module centralizes ALL operations related to the final draft file:
- Filename generation
- Path resolution
- Reading/writing
- Finding existing drafts (with legacy fallback)

To change the final draft naming convention, update ONLY this file.

Current naming convention: 6-{Deal}-{Version}.md
  - Example: 6-MitrixBio-v0.0.2.md
  - Located in: output/{Deal}-{Version}/ directory

Legacy naming (for backwards compatibility): 4-final-draft.md
"""

from pathlib import Path
from typing import Optional, Union


# =============================================================================
# CONFIGURATION - Change these to update naming convention everywhere
# =============================================================================

FINAL_DRAFT_PREFIX = "6"
LEGACY_FILENAME = "4-final-draft.md"


# =============================================================================
# FILENAME AND PATH GENERATION
# =============================================================================

def get_final_draft_filename(output_dir: Path) -> str:
    """
    Get the final draft filename based on output directory name.

    The output directory follows the pattern: {Deal}-{Version}
    The final draft filename follows the pattern: {PREFIX}-{Deal}-{Version}.md

    Args:
        output_dir: Output directory path (e.g., output/MitrixBio-v0.0.2)

    Returns:
        Final draft filename (e.g., 6-MitrixBio-v0.0.2.md)
    """
    dir_name = output_dir.name  # e.g., "MitrixBio-v0.0.2"
    return f"{FINAL_DRAFT_PREFIX}-{dir_name}.md"


def get_final_draft_path(output_dir: Path) -> Path:
    """
    Get the full path to the final draft file.

    Args:
        output_dir: Output directory path

    Returns:
        Full path to final draft file (new naming convention)
    """
    return output_dir / get_final_draft_filename(output_dir)


# =============================================================================
# FINDING EXISTING DRAFTS (with legacy fallback)
# =============================================================================

def find_final_draft(output_dir: Path) -> Optional[Path]:
    """
    Find the final draft file in an output directory.

    Tries new naming convention first, falls back to legacy naming.

    Args:
        output_dir: Output directory path

    Returns:
        Path to final draft if found, None otherwise
    """
    # Try new naming pattern first: 6-{Deal}-{Version}.md
    new_pattern_files = list(output_dir.glob(f"{FINAL_DRAFT_PREFIX}-*.md"))
    if new_pattern_files:
        return new_pattern_files[0]

    # Fall back to legacy naming
    legacy_path = output_dir / LEGACY_FILENAME
    if legacy_path.exists():
        return legacy_path

    # Try other memo patterns
    memo_files = list(output_dir.glob("*-memo.md"))
    if memo_files:
        return memo_files[0]

    return None


def final_draft_exists(output_dir: Path) -> bool:
    """
    Check if a final draft exists in the output directory.

    Args:
        output_dir: Output directory path

    Returns:
        True if any final draft file exists
    """
    return find_final_draft(output_dir) is not None


# =============================================================================
# READING AND WRITING
# =============================================================================

def read_final_draft(output_dir: Path) -> Optional[str]:
    """
    Read the final draft content from an output directory.

    Automatically finds the draft using new or legacy naming.

    Args:
        output_dir: Output directory path

    Returns:
        Final draft content as string, or None if not found
    """
    draft_path = find_final_draft(output_dir)
    if draft_path and draft_path.exists():
        return draft_path.read_text(encoding="utf-8")
    return None


def write_final_draft(output_dir: Path, content: str) -> Path:
    """
    Write content to the final draft file.

    Always uses the new naming convention.

    Args:
        output_dir: Output directory path
        content: Content to write

    Returns:
        Path to the written file
    """
    draft_path = get_final_draft_path(output_dir)
    draft_path.write_text(content, encoding="utf-8")
    return draft_path


def save_final_draft(output_dir: Path, content: str) -> Path:
    """
    Alias for write_final_draft() for backwards compatibility.

    Args:
        output_dir: Output directory path
        content: Content to write

    Returns:
        Path to the written file
    """
    return write_final_draft(output_dir, content)


# =============================================================================
# BATCH OPERATIONS (for export tools)
# =============================================================================

def find_all_final_drafts(search_dir: Path, recursive: bool = True) -> list[Path]:
    """
    Find all final draft files in a directory.

    Useful for batch export operations.

    Args:
        search_dir: Directory to search
        recursive: Whether to search subdirectories

    Returns:
        List of paths to final draft files
    """
    pattern = "**/" if recursive else ""

    # Try new naming pattern first
    files = list(search_dir.glob(f"{pattern}{FINAL_DRAFT_PREFIX}-*.md"))

    if not files:
        # Fall back to legacy naming
        files = list(search_dir.glob(f"{pattern}{LEGACY_FILENAME}"))

    if not files:
        # Try memo pattern
        files = list(search_dir.glob(f"{pattern}*-memo.md"))

    return files


def is_final_draft_file(file_path: Path) -> bool:
    """
    Check if a file is a final draft based on its name.

    Args:
        file_path: Path to check

    Returns:
        True if the file appears to be a final draft
    """
    name = file_path.name
    return (
        name.startswith(f"{FINAL_DRAFT_PREFIX}-") or
        name == LEGACY_FILENAME or
        name.endswith("-memo.md")
    )

"""Utility functions for the investment memo orchestrator."""

from pathlib import Path
from .artifacts import sanitize_filename


def get_latest_output_dir(company_name: str) -> Path:
    """
    Find the most recent output directory for a company.
    
    Args:
        company_name: Company name
        
    Returns:
        Path to the most recent output directory
        
    Raises:
        FileNotFoundError: If no output directory exists
    """
    safe_name = sanitize_filename(company_name)
    output_base = Path("output")
    
    # Find all matching directories (exclude files)
    matching_dirs = [p for p in output_base.glob(f"{safe_name}-v*") if p.is_dir()]
    if not matching_dirs:
        raise FileNotFoundError(f"No output directory found for {company_name}")

    # Get the most recent one (highest version by name)
    return max(matching_dirs, key=lambda p: p.name)

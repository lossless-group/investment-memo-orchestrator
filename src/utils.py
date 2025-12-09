"""Utility functions for the investment memo orchestrator."""

from pathlib import Path
from typing import Optional, TYPE_CHECKING
from .artifacts import sanitize_filename

if TYPE_CHECKING:
    from .state import MemoState


def get_output_dir_from_state(state: "MemoState") -> Path:
    """
    Get output directory from state, falling back to get_latest_output_dir.

    This is the preferred method for agents to get the output directory.
    It respects state["output_dir"] (set during resume) before falling back
    to auto-detection via get_latest_output_dir.

    Args:
        state: MemoState containing company_name, firm, and optionally output_dir

    Returns:
        Path to the output directory

    Raises:
        FileNotFoundError: If no output directory can be determined
    """
    # Check for pre-set output_dir (e.g., from resume script)
    existing_output_dir = state.get("output_dir")
    if existing_output_dir:
        output_dir = Path(existing_output_dir)
        if output_dir.exists():
            return output_dir
        # Path was set but doesn't exist - log warning and continue
        print(f"Warning: state['output_dir'] set to {output_dir} but doesn't exist, falling back")

    # Fall back to auto-detection
    company_name = state["company_name"]
    firm = state.get("firm")
    return get_latest_output_dir(company_name, firm=firm)


def get_latest_output_dir(
    company_name: str,
    firm: Optional[str] = None,
    io_root: Optional[Path] = None
) -> Path:
    """
    Find the most recent output directory for a company.

    Supports both firm-scoped and legacy directory structures:
    - Firm-scoped: io/{firm}/deals/{company}/outputs/{company}-v*/
    - Legacy: output/{company}-v*/

    Resolution priority:
    1. If firm is provided, look in io/{firm}/deals/{company}/outputs/
    2. If no firm, auto-detect from io/ directory
    3. Fall back to legacy output/ directory

    Args:
        company_name: Company name
        firm: Optional firm name for firm-scoped resolution
        io_root: Optional IO root directory override

    Returns:
        Path to the most recent output directory

    Raises:
        FileNotFoundError: If no output directory exists
    """
    from .paths import resolve_deal_context, get_latest_output_dir_for_deal

    # Try firm-scoped resolution first
    ctx = resolve_deal_context(company_name, firm=firm, io_root=io_root)

    # If we found a firm-scoped deal with outputs, use that
    if not ctx.is_legacy and ctx.outputs_dir and ctx.outputs_dir.exists():
        try:
            return get_latest_output_dir_for_deal(ctx)
        except FileNotFoundError:
            pass  # Fall through to legacy

    # Legacy fallback
    safe_name = sanitize_filename(company_name)
    output_base = Path("output")

    # Find all matching directories (exclude files)
    matching_dirs = [p for p in output_base.glob(f"{safe_name}-v*") if p.is_dir()]
    if not matching_dirs:
        raise FileNotFoundError(f"No output directory found for {company_name}")

    # Get the most recent one (highest version by name)
    return max(matching_dirs, key=lambda p: p.name)

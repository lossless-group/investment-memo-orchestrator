"""
Centralized path resolution for the investment memo orchestrator.

Supports two directory structures:
1. Firm-scoped (new): io/{firm}/deals/{deal}/
2. Legacy: data/{deal}.json + output/{deal}-v*/

Resolution priority:
1. If firm is specified, use io/{firm}/deals/{deal}/
2. If no firm, check io/ for any firm containing the deal
3. Fall back to legacy data/ and output/ structure

Environment variables:
- MEMO_DEFAULT_FIRM: Default firm when not specified via CLI
- MEMO_IO_ROOT: Override IO root directory (default: "io")
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass


# Default paths
DEFAULT_IO_ROOT = Path("io")
DEFAULT_DATA_DIR = Path("data")
DEFAULT_OUTPUT_DIR = Path("output")


@dataclass
class DealContext:
    """
    Context for a deal, including paths and configuration.

    This object is passed through the workflow to ensure all agents
    use consistent path resolution.
    """
    deal_name: str
    firm: Optional[str] = None
    io_root: Path = DEFAULT_IO_ROOT

    # Resolved paths (set by resolve_deal_paths)
    deal_dir: Optional[Path] = None
    inputs_dir: Optional[Path] = None
    outputs_dir: Optional[Path] = None
    exports_dir: Optional[Path] = None
    deal_json_path: Optional[Path] = None

    # Whether using legacy or firm-scoped structure
    is_legacy: bool = False

    def __post_init__(self):
        """Resolve paths after initialization."""
        self._resolve_paths()

    def _resolve_paths(self):
        """Resolve all paths based on firm and deal name."""
        if self.firm:
            # Firm-scoped structure
            self.deal_dir = self.io_root / self.firm / "deals" / self.deal_name
            self.inputs_dir = self.deal_dir / "inputs"
            self.outputs_dir = self.deal_dir / "outputs"
            self.exports_dir = self.deal_dir / "exports"

            # Check multiple possible locations for deal config
            # Priority: inputs/deal.json > {deal}.json in deal_dir
            inputs_deal_json = self.inputs_dir / "deal.json"
            direct_deal_json = self.deal_dir / f"{self.deal_name}.json"

            if inputs_deal_json.exists():
                self.deal_json_path = inputs_deal_json
            elif direct_deal_json.exists():
                self.deal_json_path = direct_deal_json
            else:
                # Default to inputs/deal.json (canonical location)
                self.deal_json_path = inputs_deal_json

            self.is_legacy = False
        else:
            # Legacy structure
            self.deal_dir = None
            self.inputs_dir = DEFAULT_DATA_DIR
            self.outputs_dir = DEFAULT_OUTPUT_DIR
            self.exports_dir = Path("exports")
            self.deal_json_path = DEFAULT_DATA_DIR / f"{self.deal_name}.json"
            self.is_legacy = True

    def get_version_output_dir(self, version: str) -> Path:
        """
        Get the output directory for a specific version.

        Args:
            version: Version string (e.g., "v0.0.1")

        Returns:
            Path to version-specific output directory
        """
        from .artifacts import sanitize_filename
        safe_name = sanitize_filename(self.deal_name)

        if self.firm:
            # Firm-scoped: io/{firm}/deals/{deal}/outputs/{deal}-{version}/
            return self.outputs_dir / f"{safe_name}-{version}"
        else:
            # Legacy: output/{deal}-{version}/
            return self.outputs_dir / f"{safe_name}-{version}"

    def exists(self) -> bool:
        """Check if the deal configuration exists."""
        return self.deal_json_path and self.deal_json_path.exists()


def get_default_firm() -> Optional[str]:
    """
    Get default firm from environment variable.

    Returns:
        Default firm name or None
    """
    return os.getenv("MEMO_DEFAULT_FIRM")


def get_io_root() -> Path:
    """
    Get IO root directory from environment or default.

    Returns:
        Path to IO root directory
    """
    io_root = os.getenv("MEMO_IO_ROOT")
    if io_root:
        return Path(io_root)
    return DEFAULT_IO_ROOT


def find_deal_firm(deal_name: str, io_root: Optional[Path] = None) -> Optional[str]:
    """
    Search io/ directory to find which firm contains a deal.

    Args:
        deal_name: Name of the deal to find
        io_root: IO root directory (default: from env or "io")

    Returns:
        Firm name if found, None otherwise
    """
    io_root = io_root or get_io_root()

    if not io_root.exists():
        return None

    # Search each firm directory
    for firm_dir in io_root.iterdir():
        if not firm_dir.is_dir() or firm_dir.name.startswith('.'):
            continue

        deals_dir = firm_dir / "deals"
        if deals_dir.exists():
            deal_dir = deals_dir / deal_name
            if deal_dir.exists():
                return firm_dir.name

    return None


def resolve_deal_context(
    deal_name: str,
    firm: Optional[str] = None,
    io_root: Optional[Path] = None
) -> DealContext:
    """
    Resolve deal context with automatic firm detection and legacy fallback.

    Resolution priority:
    1. If firm is explicitly provided, use io/{firm}/deals/{deal}/
    2. If no firm, check MEMO_DEFAULT_FIRM environment variable
    3. If still no firm, search io/ for any firm containing the deal
    4. Fall back to legacy data/{deal}.json structure

    Args:
        deal_name: Name of the deal/company
        firm: Firm name (optional, will auto-detect)
        io_root: IO root directory (optional)

    Returns:
        DealContext with resolved paths
    """
    io_root = io_root or get_io_root()

    # Priority 1: Explicit firm
    if firm:
        ctx = DealContext(deal_name=deal_name, firm=firm, io_root=io_root)
        if ctx.exists():
            return ctx
        # Fall through to try other options

    # Priority 2: Default firm from environment
    default_firm = get_default_firm()
    if default_firm and not firm:
        ctx = DealContext(deal_name=deal_name, firm=default_firm, io_root=io_root)
        if ctx.exists():
            return ctx

    # Priority 3: Auto-detect firm from io/ directory
    detected_firm = find_deal_firm(deal_name, io_root)
    if detected_firm:
        return DealContext(deal_name=deal_name, firm=detected_firm, io_root=io_root)

    # Priority 4: Legacy fallback
    legacy_ctx = DealContext(deal_name=deal_name, firm=None, io_root=io_root)
    return legacy_ctx


def load_deal_config(ctx: DealContext) -> Dict[str, Any]:
    """
    Load deal configuration from JSON file.

    Args:
        ctx: DealContext with resolved paths

    Returns:
        Dictionary with deal configuration

    Raises:
        FileNotFoundError: If deal config doesn't exist
    """
    if not ctx.deal_json_path or not ctx.deal_json_path.exists():
        raise FileNotFoundError(f"Deal config not found: {ctx.deal_json_path}")

    with open(ctx.deal_json_path) as f:
        config = json.load(f)

    # Resolve relative paths in config
    if not ctx.is_legacy and ctx.inputs_dir:
        # For firm-scoped, resolve paths relative to inputs/
        if "deck" in config and config["deck"]:
            deck_path = ctx.inputs_dir / config["deck"]
            if deck_path.exists():
                config["deck"] = str(deck_path)

        if "dataroom" in config and config["dataroom"]:
            dataroom_path = ctx.inputs_dir / config["dataroom"]
            if dataroom_path.exists():
                config["dataroom"] = str(dataroom_path)

    return config


def resolve_deal_paths(
    deal_name: str,
    firm: Optional[str] = None,
    io_root: Optional[Path] = None
) -> Tuple[DealContext, Dict[str, Any]]:
    """
    Convenience function to resolve context and load config in one call.

    Args:
        deal_name: Name of the deal/company
        firm: Firm name (optional)
        io_root: IO root directory (optional)

    Returns:
        Tuple of (DealContext, config dict)
    """
    ctx = resolve_deal_context(deal_name, firm, io_root)

    if ctx.exists():
        config = load_deal_config(ctx)
    else:
        config = {}

    return ctx, config


def get_latest_output_dir_for_deal(ctx: DealContext) -> Path:
    """
    Find the most recent output directory for a deal.

    This is the firm-aware version of utils.get_latest_output_dir().

    Args:
        ctx: DealContext with resolved paths

    Returns:
        Path to the most recent output directory

    Raises:
        FileNotFoundError: If no output directory exists
    """
    from .artifacts import sanitize_filename

    safe_name = sanitize_filename(ctx.deal_name)
    outputs_dir = ctx.outputs_dir

    if not outputs_dir or not outputs_dir.exists():
        raise FileNotFoundError(f"Outputs directory not found: {outputs_dir}")

    # Find all matching directories
    matching_dirs = [p for p in outputs_dir.glob(f"{safe_name}-v*") if p.is_dir()]

    if not matching_dirs:
        raise FileNotFoundError(f"No output directory found for {ctx.deal_name} in {outputs_dir}")

    # Get the most recent one (highest version by name)
    return max(matching_dirs, key=lambda p: p.name)


def create_output_dir_for_deal(ctx: DealContext, version: str) -> Path:
    """
    Create output directory structure for a deal version.

    Args:
        ctx: DealContext with resolved paths
        version: Version string (e.g., "v0.0.1")

    Returns:
        Path to the created output directory
    """
    output_dir = ctx.get_version_output_dir(version)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create sections subdirectory
    sections_dir = output_dir / "2-sections"
    sections_dir.mkdir(exist_ok=True)

    return output_dir


def list_firms(io_root: Optional[Path] = None) -> list[str]:
    """
    List all firms in the io/ directory.

    Args:
        io_root: IO root directory (optional)

    Returns:
        List of firm names
    """
    io_root = io_root or get_io_root()

    if not io_root.exists():
        return []

    return [
        d.name for d in io_root.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ]


def list_deals_for_firm(firm: str, io_root: Optional[Path] = None) -> list[str]:
    """
    List all deals for a firm.

    Args:
        firm: Firm name
        io_root: IO root directory (optional)

    Returns:
        List of deal names
    """
    io_root = io_root or get_io_root()
    deals_dir = io_root / firm / "deals"

    if not deals_dir.exists():
        return []

    return [
        d.name for d in deals_dir.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ]

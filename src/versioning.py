"""
Versioning system for memo iterations.

Tracks versions of memos as they go through revision cycles:
- v0.0.x: Draft revisions (automated)
- v0.x.0: Minor versions (user approved draft quality)
- vx.0.0: Major versions (finalized, ready for distribution)

Supports both:
- Firm-scoped versioning: io/{firm}/versions.json
- Legacy global versioning: output/versions.json
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union
from datetime import datetime


# Default paths
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_IO_ROOT = Path("io")


class MemoVersion:
    """Represents a semantic version for memo drafts."""

    def __init__(self, major: int = 0, minor: int = 0, patch: int = 1):
        self.major = major
        self.minor = minor
        self.patch = patch

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def increment_patch(self) -> "MemoVersion":
        """Increment patch version (for revision iterations)."""
        return MemoVersion(self.major, self.minor, self.patch + 1)

    def increment_minor(self) -> "MemoVersion":
        """Increment minor version (for approved drafts)."""
        return MemoVersion(self.major, self.minor + 1, 0)

    def increment_major(self) -> "MemoVersion":
        """Increment major version (for final release)."""
        return MemoVersion(self.major + 1, 0, 0)

    @classmethod
    def from_string(cls, version_str: str) -> "MemoVersion":
        """Parse version from string like 'v0.1.2'."""
        version_str = version_str.lstrip("v")
        parts = version_str.split(".")
        return cls(
            major=int(parts[0]) if len(parts) > 0 else 0,
            minor=int(parts[1]) if len(parts) > 1 else 0,
            patch=int(parts[2]) if len(parts) > 2 else 1,
        )


class VersionManager:
    """
    Manages versioning for memo drafts.

    Supports two modes:
    1. Firm-scoped: When firm is provided, uses io/{firm}/versions.json
    2. Legacy: When no firm, uses output/versions.json

    Usage:
        # Firm-scoped (new)
        vm = VersionManager(firm="hypernova")

        # Legacy (backward compatible)
        vm = VersionManager(output_dir=Path("output"))

        # Auto-detect from deal path
        vm = VersionManager.from_deal_path("io/hypernova/deals/Aalo")
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        firm: Optional[str] = None,
        io_root: Optional[Path] = None
    ):
        """
        Initialize VersionManager.

        Args:
            output_dir: Legacy output directory (used if firm not provided)
            firm: Firm name for firm-scoped versioning (e.g., "hypernova")
            io_root: Root IO directory (default: "io")
        """
        self.firm = firm
        self.io_root = io_root or DEFAULT_IO_ROOT

        if firm:
            # Firm-scoped mode
            self.firm_dir = self.io_root / firm
            self.versions_file = self.firm_dir / "versions.json"
            self.output_dir = None  # Not used in firm mode
        else:
            # Legacy mode
            self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
            self.versions_file = self.output_dir / "versions.json"
            self.firm_dir = None

        self.versions_data = self._load_versions()

    @classmethod
    def from_deal_path(cls, deal_path: Union[str, Path]) -> "VersionManager":
        """
        Create VersionManager from a deal path.

        Auto-detects if path is firm-scoped (io/{firm}/deals/{deal})
        or legacy (output/{deal}-v0.0.x).

        Args:
            deal_path: Path to deal directory

        Returns:
            Configured VersionManager instance
        """
        deal_path = Path(deal_path)
        parts = deal_path.parts

        # Check if this is an io/{firm}/deals/{deal} path
        if "io" in parts:
            io_idx = parts.index("io")
            if len(parts) > io_idx + 1:
                firm = parts[io_idx + 1]
                io_root = Path(*parts[:io_idx + 1])
                return cls(firm=firm, io_root=io_root)

        # Fall back to legacy mode
        return cls(output_dir=DEFAULT_OUTPUT_DIR)

    @classmethod
    def for_firm(cls, firm: str, io_root: Optional[Path] = None) -> "VersionManager":
        """
        Create VersionManager for a specific firm.

        Args:
            firm: Firm name (e.g., "hypernova")
            io_root: Root IO directory (default: "io")

        Returns:
            Configured VersionManager instance
        """
        return cls(firm=firm, io_root=io_root)

    @classmethod
    def legacy(cls, output_dir: Optional[Path] = None) -> "VersionManager":
        """
        Create VersionManager in legacy mode.

        Args:
            output_dir: Output directory (default: "output")

        Returns:
            Configured VersionManager instance
        """
        return cls(output_dir=output_dir or DEFAULT_OUTPUT_DIR)

    def _load_versions(self) -> Dict[str, Any]:
        """Load versions data from JSON."""
        if self.versions_file.exists():
            with open(self.versions_file, "r") as f:
                return json.load(f)
        return {}

    def _save_versions(self):
        """Save versions data to JSON."""
        # Ensure parent directory exists
        self.versions_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.versions_file, "w") as f:
            json.dump(self.versions_data, f, indent=2)

    def get_deal_output_dir(self, deal_name: str, version: Optional[MemoVersion] = None) -> Path:
        """
        Get the output directory for a deal.

        Args:
            deal_name: Deal/company name
            version: Optional version (if None, returns base outputs dir)

        Returns:
            Path to the deal's output directory
        """
        if self.firm:
            # Firm-scoped: io/{firm}/deals/{deal}/outputs/{deal}-{version}/
            base = self.firm_dir / "deals" / deal_name / "outputs"
            if version:
                return base / f"{deal_name}-{version}"
            return base
        else:
            # Legacy: output/{deal}-{version}/
            if version:
                return self.output_dir / f"{deal_name}-{version}"
            return self.output_dir

    def get_relative_file_path(self, deal_name: str, version: MemoVersion, filename: str) -> str:
        """
        Get the relative file path for storage in versions.json.

        Args:
            deal_name: Deal/company name
            version: Version number
            filename: File name (e.g., "4-final-draft.md")

        Returns:
            Relative path string for storage
        """
        if self.firm:
            # Relative to firm dir: deals/{deal}/outputs/{deal}-{version}/{filename}
            return f"deals/{deal_name}/outputs/{deal_name}-{version}/{filename}"
        else:
            # Relative to output dir: {deal}-{version}/{filename}
            return f"{deal_name}-{version}/{filename}"

    def get_next_version(self, company_name: str) -> MemoVersion:
        """
        Get the next version number for a company's memo.

        Args:
            company_name: Sanitized company name

        Returns:
            Next version number to use
        """
        if company_name not in self.versions_data:
            # First version
            return MemoVersion(0, 0, 1)

        # Get latest version
        latest = self.versions_data[company_name]["latest_version"]
        version = MemoVersion.from_string(latest)

        # Increment patch version for new iteration
        return version.increment_patch()

    def get_current_version(self, company_name: str) -> MemoVersion:
        """
        Get the current (latest) version for a company's memo.

        Args:
            company_name: Sanitized company name

        Returns:
            Current version number, or v0.0.1 if no versions exist
        """
        if company_name not in self.versions_data:
            # No versions yet, return v0.0.1
            return MemoVersion(0, 0, 1)

        # Get latest version from versions.json
        latest = self.versions_data[company_name]["latest_version"]
        return MemoVersion.from_string(latest)

    def record_version(
        self,
        company_name: str,
        version: MemoVersion,
        validation_score: float,
        file_path: str,
        is_finalized: bool = False,
    ):
        """
        Record a new version in the history.

        Args:
            company_name: Sanitized company name
            version: Version number
            validation_score: Validation score (0-10)
            file_path: Path to the saved file
            is_finalized: Whether this version was finalized (score >= 8)
        """
        if company_name not in self.versions_data:
            self.versions_data[company_name] = {
                "latest_version": str(version),
                "history": [],
            }

        # Add to history
        self.versions_data[company_name]["history"].append(
            {
                "version": str(version),
                "timestamp": datetime.now().isoformat(),
                "validation_score": validation_score,
                "file_path": file_path,
                "is_finalized": is_finalized,
            }
        )

        # Update latest
        self.versions_data[company_name]["latest_version"] = str(version)

        self._save_versions()

    def get_version_history(self, company_name: str) -> list:
        """Get version history for a company."""
        if company_name not in self.versions_data:
            return []
        return self.versions_data[company_name]["history"]

    def promote_version(self, company_name: str, to_level: str = "minor") -> Optional[MemoVersion]:
        """
        Manually promote a version (user action).

        Args:
            company_name: Sanitized company name
            to_level: 'minor' (v0.x.0) or 'major' (vx.0.0)

        Returns:
            New version number or None if company not found
        """
        if company_name not in self.versions_data:
            return None

        latest = self.versions_data[company_name]["latest_version"]
        version = MemoVersion.from_string(latest)

        if to_level == "minor":
            new_version = version.increment_minor()
        elif to_level == "major":
            new_version = version.increment_major()
        else:
            raise ValueError(f"Invalid promotion level: {to_level}")

        # Update latest version
        self.versions_data[company_name]["latest_version"] = str(new_version)
        self._save_versions()

        return new_version


def format_version_history(history: list) -> str:
    """Format version history as a readable string."""
    if not history:
        return "No previous versions"

    lines = ["Version History:", ""]
    for entry in history:
        status = "✓ Finalized" if entry["is_finalized"] else "⚠ Draft"
        lines.append(
            f"  {entry['version']} - Score: {entry['validation_score']}/10 - {status}"
        )
        lines.append(f"    {entry['timestamp']}")
        lines.append(f"    {entry['file_path']}")
        lines.append("")

    return "\n".join(lines)


def migrate_versions_to_firm(
    legacy_versions_file: Path,
    firm: str,
    deals_to_migrate: list[str],
    io_root: Path = DEFAULT_IO_ROOT,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Migrate specific deals from legacy versions.json to firm-scoped versions.json.

    Args:
        legacy_versions_file: Path to the legacy output/versions.json
        firm: Target firm name (e.g., "hypernova")
        deals_to_migrate: List of deal names to migrate
        io_root: Root IO directory (default: "io")
        dry_run: If True, don't write files, just return what would be migrated

    Returns:
        Dict with migration results:
        - migrated: list of deal names successfully migrated
        - skipped: list of deal names not found in legacy
        - firm_versions: the new firm versions data
    """
    results = {
        "migrated": [],
        "skipped": [],
        "firm_versions": {}
    }

    # Load legacy versions
    if not legacy_versions_file.exists():
        print(f"Legacy versions file not found: {legacy_versions_file}")
        return results

    with open(legacy_versions_file, "r") as f:
        legacy_data = json.load(f)

    # Create firm version manager
    firm_vm = VersionManager(firm=firm, io_root=io_root)

    for deal_name in deals_to_migrate:
        if deal_name not in legacy_data:
            results["skipped"].append(deal_name)
            continue

        deal_data = legacy_data[deal_name]

        # Update file paths in history to use new firm-relative paths
        updated_history = []
        for entry in deal_data.get("history", []):
            old_path = entry.get("file_path", "")
            # Convert: output/Deal-v0.0.1/file.md -> deals/Deal/outputs/Deal-v0.0.1/file.md
            if old_path.startswith("output/"):
                # Extract version folder and filename
                parts = old_path.replace("output/", "").split("/", 1)
                if len(parts) == 2:
                    version_folder, filename = parts
                    new_path = f"deals/{deal_name}/outputs/{version_folder}/{filename}"
                else:
                    new_path = f"deals/{deal_name}/outputs/{parts[0]}"
            else:
                # Already relative or different format
                new_path = old_path

            updated_entry = entry.copy()
            updated_entry["file_path"] = new_path
            updated_history.append(updated_entry)

        # Add to firm versions
        firm_vm.versions_data[deal_name] = {
            "latest_version": deal_data["latest_version"],
            "history": updated_history
        }

        results["migrated"].append(deal_name)

    results["firm_versions"] = firm_vm.versions_data

    if not dry_run:
        firm_vm._save_versions()
        print(f"Saved firm versions to: {firm_vm.versions_file}")

    return results


def get_firm_deals(io_root: Path, firm: str) -> list[str]:
    """
    Get list of deal names for a firm from the io directory structure.

    Args:
        io_root: Root IO directory
        firm: Firm name

    Returns:
        List of deal names found in io/{firm}/deals/
    """
    deals_dir = io_root / firm / "deals"
    if not deals_dir.exists():
        return []

    return [
        d.name for d in deals_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]

"""
Versioning system for memo iterations.

Tracks versions of memos as they go through revision cycles:
- v0.0.x: Draft revisions (automated)
- v0.x.0: Minor versions (user approved draft quality)
- vx.0.0: Major versions (finalized, ready for distribution)
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


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
    """Manages versioning for memo drafts."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.versions_file = output_dir / "versions.json"
        self.versions_data = self._load_versions()

    def _load_versions(self) -> Dict[str, Any]:
        """Load versions data from JSON."""
        if self.versions_file.exists():
            with open(self.versions_file, "r") as f:
                return json.load(f)
        return {}

    def _save_versions(self):
        """Save versions data to JSON."""
        self.output_dir.mkdir(exist_ok=True)
        with open(self.versions_file, "w") as f:
            json.dump(self.versions_data, f, indent=2)

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

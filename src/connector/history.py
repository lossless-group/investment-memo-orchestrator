"""The history hook: phase 6 fills it with jj.

Every saved artifact calls :meth:`History.record` once, after the files are on
disk, with a message naming the step, deal, and section. Plan 1 ships the no-op
:class:`NullHistory`; phase 6 replaces :func:`history_for` with a jj-backed
implementation (one jj repository per firm workspace) without touching callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class History(Protocol):
    def record(self, message: str, paths: list[Path]) -> None:
        """Record one change covering ``paths`` (already written)."""

    def read(self, path: Path, version: int) -> str | None:
        """Return ``path``'s text at artifact ``version``, or None if not kept."""


class NullHistory:
    """Keeps nothing. Earlier versions are not readable until phase 6."""

    def record(self, message: str, paths: list[Path]) -> None:
        return None

    def read(self, path: Path, version: int) -> str | None:
        return None


def history_for(workspace_root: Path) -> History:
    """The firm's history. Phase 6: return a jj-backed History here."""
    return NullHistory()

"""Filesystem watcher that publishes file_added / file_modified / file_removed
events to a JobEventBus while a memo run is in progress.

Watches recursively under the job's output_dir. Started by JobRegistry once the
worker thread emits "📁 Created new output directory: ..." (detected in the bus
tap). Stopped in JobRegistry's finally block when the worker thread exits.

The watcher runs as an asyncio task on the FastAPI event loop. The worker
thread schedules start/stop via loop.call_soon_threadsafe, so the public API
is safe to call from any thread.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from watchfiles import Change, awatch

from .events import JobEventBus


class FileWatcher:
    """Async filesystem watcher tied to a single Job's output_dir.

    Lifecycle:
      1. Construction binds bus + output_dir.
      2. start() schedules the awatch task on the loop (thread-safe).
      3. stop() signals the watcher to drain and exit (thread-safe).

    Events published:
      file_added    { path, size }
      file_modified { path, size }
      file_removed  { path }

    `path` is always relative to output_dir, posix-style. Directories are
    suppressed — clients build the tree from file paths.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        bus: JobEventBus,
        output_dir: Path,
    ) -> None:
        self._loop = loop
        self._bus = bus
        # awatch always yields absolute, fully-resolved paths. The orchestrator
        # emits a *relative* path in "📁 Created new output directory: ..."
        # (e.g. io/alpha-partners/...), so resolve here to match — otherwise
        # every relative_to() comparison raises ValueError and live events get
        # silently dropped on the floor. (Initial snapshot still worked
        # because rglob preserves the input form, masking the bug.)
        self._output_dir = output_dir.resolve()
        self._stop_event: Optional[asyncio.Event] = None

    def start(self) -> None:
        def _spawn() -> None:
            # Event must be created on the loop it'll be awaited from.
            self._stop_event = asyncio.Event()
            self._loop.create_task(self._run())

        self._loop.call_soon_threadsafe(_spawn)

    def stop(self) -> None:
        def _signal() -> None:
            if self._stop_event is not None:
                self._stop_event.set()

        self._loop.call_soon_threadsafe(_signal)

    async def _run(self) -> None:
        try:
            self._emit_initial_snapshot()
            assert self._stop_event is not None
            async for changes in awatch(
                str(self._output_dir),
                recursive=True,
                stop_event=self._stop_event,
            ):
                for change_type, abs_path in changes:
                    self._emit_change(change_type, abs_path)
        except Exception as e:
            # The watcher is best-effort progress UX; never let it kill a run.
            self._bus.publish(
                {"type": "log", "line": f"⚠️  file watcher error: {e!s}"}
            )

    def _emit_initial_snapshot(self) -> None:
        """Walk the dir once and emit file_added for each existing file.

        Without this, late SSE subscribers (e.g. user re-opens JobView mid-run)
        would only see future changes — the bus's 2000-event backlog rotates
        old file events out of replay window after enough log churn.
        """
        if not self._output_dir.exists():
            return
        for p in sorted(self._output_dir.rglob("*")):
            if not p.is_file():
                continue
            try:
                rel = str(p.relative_to(self._output_dir))
                self._bus.publish(
                    {
                        "type": "file_added",
                        "path": rel,
                        "size": p.stat().st_size,
                    }
                )
            except Exception:
                pass

    def _emit_change(self, change_type: Change, abs_path: str) -> None:
        try:
            p = Path(abs_path)
            try:
                rel = str(p.relative_to(self._output_dir))
            except ValueError:
                return  # outside our watch root
            if change_type == Change.deleted:
                self._bus.publish({"type": "file_removed", "path": rel})
                return
            if not p.exists() or p.is_dir():
                return  # directories aren't surfaced; clients infer from paths
            size = p.stat().st_size
            if change_type == Change.added:
                self._bus.publish(
                    {"type": "file_added", "path": rel, "size": size}
                )
            elif change_type == Change.modified:
                self._bus.publish(
                    {"type": "file_modified", "path": rel, "size": size}
                )
        except Exception:
            pass

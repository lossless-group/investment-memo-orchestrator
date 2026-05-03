"""Per-job event bus for streaming logs + lifecycle to clients.

Worker threads call `bus.publish(event)` from any thread. Async consumers subscribe
via `bus.subscribe()` which replays a recent backlog and then live-tails until the
job's bus is closed.
"""

from __future__ import annotations

import asyncio
import io
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

# How many recent events to retain for late subscribers (per job).
MAX_BACKLOG = 2000


class JobEventBus:
    """Single job's event stream. Thread-safe writer, async-safe reader.

    Optional `tap` callback is invoked synchronously on every publish (from the
    publishing thread). Used to accumulate the full event history off-bus for
    later disk persistence — the in-memory backlog is capped at MAX_BACKLOG and
    can't be relied on for runs that emit more events than that.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        tap: Optional[object] = None,
    ) -> None:
        self._loop = loop
        self._lock = threading.Lock()
        self._backlog: deque[dict] = deque(maxlen=MAX_BACKLOG)
        self._subscribers: list[asyncio.Queue] = []
        self._closed = False
        self._tap = tap  # callable(dict) -> None
        # Monotonic per-job sequence stamped onto every published event. Lets
        # SSE clients dedup the backlog replay that subscribe() does on every
        # (re)connection — without this, an EventSource reconnect causes the
        # client to re-append the last MAX_BACKLOG events and any timer derived
        # from events[0] snaps forward.
        self._seq = 0

    def publish(self, event: dict) -> None:
        """Append to backlog and fan out to live subscribers. Safe from any thread."""
        if "ts" not in event:
            event["ts"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._seq += 1
            event["seq"] = self._seq
            self._backlog.append(event)
            subs = list(self._subscribers)
        if self._tap is not None:
            try:
                self._tap(event)  # type: ignore[operator]
            except Exception:
                # Don't let a misbehaving tap kill the publisher.
                pass
        for q in subs:
            self._loop.call_soon_threadsafe(_safe_put, q, event)

    def close(self) -> None:
        """Mark the bus closed; live subscribers see a None sentinel and exit cleanly."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subs = list(self._subscribers)
        for q in subs:
            self._loop.call_soon_threadsafe(_safe_put, q, None)

    async def subscribe(self) -> AsyncIterator[dict]:
        """Replay the backlog, then live-tail until the bus closes."""
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            for ev in self._backlog:
                q.put_nowait(ev)
            if self._closed:
                q.put_nowait(None)
            else:
                self._subscribers.append(q)
        try:
            while True:
                item = await q.get()
                if item is None:
                    return
                yield item
        finally:
            with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)


def _safe_put(q: asyncio.Queue, item: Any) -> None:
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:
        # Subscriber is too slow; dropping events is preferable to blocking the publisher.
        pass


class LogSink(io.TextIOBase):
    """Stream-like sink that splits writes into lines and publishes them as `log` events.

    Mirrors output to the original stdout/stderr (if provided) so dev runs still see
    the orchestrator's terminal output in their host shell.

    If `milestone_extractor` is provided, each emitted log line is also fed through
    it; matched milestones are published as additional `milestone` events on the bus.
    """

    def __init__(
        self,
        bus: JobEventBus,
        mirror: Optional[io.TextIOBase] = None,
        milestone_extractor: Optional[object] = None,
    ) -> None:
        super().__init__()
        self._bus = bus
        self._mirror = mirror
        self._extractor = milestone_extractor
        self._buffer = ""
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self._mirror is not None:
            try:
                self._mirror.write(s)
            except Exception:
                pass
        with self._lock:
            self._buffer += s
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if line:
                    self._publish_line(line)
        return len(s)

    def flush(self) -> None:
        if self._mirror is not None:
            try:
                self._mirror.flush()
            except Exception:
                pass
        with self._lock:
            if self._buffer:
                self._publish_line(self._buffer)
                self._buffer = ""

    def _publish_line(self, line: str) -> None:
        self._bus.publish({"type": "log", "line": line})
        if self._extractor is not None:
            milestone = self._extractor.process(line)  # type: ignore[attr-defined]
            if milestone is not None:
                self._bus.publish(milestone)

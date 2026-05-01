"""In-memory registry of memo-generation jobs.

A single ThreadPoolExecutor (max_workers=1) runs `generate_memo()` synchronously
on a background thread, while the FastAPI event loop stays free to serve status
polls and SSE streams. A single concurrent job is the right ceiling for a local
sidecar — Anthropic rate limits and dataroom paths assume one run at a time.

Jobs and their event buses live entirely in process memory; restarting the server
loses in-flight history. The on-disk artifact tree (`output/...` or
`io/{firm}/deals/{deal}/outputs/...`) is the durable store.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .events import JobEventBus, LogSink
from .log_persistence import persist_job_logs
from .milestones import MilestoneExtractor
from .models import CreateMemoRequest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    job_id: str
    request: CreateMemoRequest
    bus: JobEventBus
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_dir: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None
    # Full chronological event capture for on-disk log persistence. The bus's
    # backlog is capped (for SSE replay) so we keep our own list here.
    events_log: list[dict] = field(default_factory=list)


class JobRegistry:
    """One-instance, single-worker job runner. Owned by FastAPI's lifespan."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="memo-worker")

    def shutdown(self) -> None:
        with self._lock:
            buses = [job.bus for job in self._jobs.values()]
        for bus in buses:
            bus.close()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def submit(self, request: CreateMemoRequest) -> Job:
        job_id = uuid.uuid4().hex[:12]
        # Accumulate every published event into the job's events_log so we can
        # write the full run to disk at completion, regardless of bus backlog cap.
        events_log: list[dict] = []
        bus = JobEventBus(self._loop, tap=events_log.append)
        job = Job(
            job_id=job_id,
            request=request,
            bus=bus,
            events_log=events_log,
        )
        with self._lock:
            self._jobs[job_id] = job
        bus.publish({"type": "status", "status": "queued"})
        self._executor.submit(self._run, job)
        return job

    def _run(self, job: Job) -> None:
        bus = job.bus

        def transition(status: str) -> None:
            with self._lock:
                job.status = status
            bus.publish({"type": "status", "status": status})

        try:
            with self._lock:
                job.started_at = _now()
            transition("running")

            # Imported lazily so importing `src.server` (e.g., for app discovery)
            # doesn't drag the whole LangGraph workflow into memory.
            from ..workflow import generate_memo

            req = job.request
            extractor = MilestoneExtractor()
            sink_out = LogSink(bus, mirror=sys.__stdout__, milestone_extractor=extractor)
            sink_err = LogSink(bus, mirror=sys.__stderr__, milestone_extractor=extractor)

            with contextlib.redirect_stdout(sink_out), contextlib.redirect_stderr(sink_err):
                final_state = generate_memo(
                    company_name=req.company_name,
                    investment_type=req.investment_type,
                    memo_mode=req.memo_mode,
                    firm=req.firm,
                    force_version=req.force_version,
                    fresh=req.fresh,
                    dataroom_path=req.dataroom_path,
                    deck_path=req.deck_path,
                    company_description=req.company_description,
                    company_url=req.company_url,
                    company_stage=req.company_stage,
                    research_notes=req.research_notes,
                    company_trademark_light=req.company_trademark_light,
                    company_trademark_dark=req.company_trademark_dark,
                    outline_name=req.outline_name,
                    scorecard_name=req.scorecard_name,
                )

            output_dir = str(final_state.get("output_dir") or "")
            version = _extract_version(output_dir)

            with self._lock:
                job.output_dir = output_dir or None
                job.version = version
                job.completed_at = _now()
            bus.publish(
                {
                    "type": "complete",
                    "output_dir": output_dir or None,
                    "version": version,
                    "overall_score": final_state.get("overall_score"),
                }
            )
            transition("completed")
        except Exception as exc:
            tb = traceback.format_exc()
            with self._lock:
                job.error = str(exc)
                job.completed_at = _now()
            # If the orchestrator created its output dir before crashing, surface
            # it as the run's home so log persistence lands the failure trail
            # alongside whatever artifacts did get written.
            if not job.output_dir:
                fallback_dir = _scan_logs_for_output_dir(job.events_log)
                if fallback_dir:
                    with self._lock:
                        job.output_dir = fallback_dir
                        job.version = _extract_version(fallback_dir)
            bus.publish({"type": "error", "message": str(exc), "traceback": tb})
            transition("failed")
        finally:
            # Always persist the captured events to disk — both inside the run's
            # output dir (when known) and in the global mirror. Best-effort: any
            # filesystem error here is swallowed so we don't mask the real run
            # outcome the user is already seeing in the UI.
            try:
                persist_job_logs(
                    job_id=job.job_id,
                    company_name=job.request.company_name,
                    output_dir=job.output_dir,
                    version=job.version,
                    events=list(job.events_log),
                )
            except Exception:
                pass
            bus.close()


_VERSION_RE = re.compile(r"(v\d+\.\d+\.\d+)")
_OUTPUT_DIR_RE = re.compile(r"Created new output directory:\s+(\S+)")


def _extract_version(output_dir: str) -> Optional[str]:
    if not output_dir:
        return None
    m = _VERSION_RE.search(output_dir)
    return m.group(1) if m else None


def _scan_logs_for_output_dir(events: list[dict]) -> Optional[str]:
    """Recover output_dir from the orchestrator's `📁 Created new output directory: …`
    print, used when a run failed before populating final_state."""
    for ev in events:
        if ev.get("type") != "log":
            continue
        line = ev.get("line", "")
        if isinstance(line, str):
            m = _OUTPUT_DIR_RE.search(line)
            if m:
                return m.group(1)
    return None

"""Write a job's full event stream to disk in two formats and two locations.

Two formats — JSONL for structured analysis (one event per line, full fidelity
including milestones and stack traces), and plain text for human eyeballs
(mirrors what the desktop client's log pane renders).

Two locations:
  1. Inside the run's own output directory, alongside `state.json` and the
     final draft. Discoverable next to the artifacts they describe.
  2. A global mirror at `.logs/runs/{job_id}__{deal}-{version}.{jsonl,txt}`,
     so a user reporting an issue can `send the log file` without having to
     navigate into the firm-scoped tree.

Designed for support: `Worked on my machine!` becomes much smaller when both
parties can look at the same on-disk events.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

# All paths are relative to the orchestrator's repo root (cwd at runtime).
GLOBAL_LOGS_DIR = Path(".logs") / "runs"
LOG_BASENAME = "server-log"


def persist_job_logs(
    *,
    job_id: str,
    company_name: str,
    output_dir: Optional[str],
    version: Optional[str],
    events: list[dict],
) -> dict[str, str]:
    """Write the run's logs in JSONL and plain-text form.

    - When `output_dir` is provided and exists (or can be created), writes a
      pair of files inside it: `server-log.jsonl` and `server-log.txt`.
    - Always writes a global mirror under `.logs/runs/`, even if `output_dir`
      is missing — useful for runs that crashed before the orchestrator
      created its artifact directory.

    Returns a dict mapping `{run_jsonl, run_txt, global_jsonl, global_txt}` to
    the absolute string paths written, for logging or follow-up reference.
    """
    written: dict[str, str] = {}

    jsonl_text = "".join(json.dumps(e, default=str) + "\n" for e in events)
    text_text = _render_text(events)

    # 1. Co-located with the run's artifacts (if known).
    if output_dir:
        out_path = Path(output_dir)
        try:
            out_path.mkdir(parents=True, exist_ok=True)
            run_jsonl = out_path / f"{LOG_BASENAME}.jsonl"
            run_txt = out_path / f"{LOG_BASENAME}.txt"
            run_jsonl.write_text(jsonl_text)
            run_txt.write_text(text_text)
            written["run_jsonl"] = str(run_jsonl.resolve())
            written["run_txt"] = str(run_txt.resolve())
        except OSError:
            # Best-effort. The global mirror is the safety net.
            pass

    # 2. Global mirror — always written so support requests can be one-file.
    GLOBAL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    base = _global_basename(job_id, company_name, version)
    global_jsonl = GLOBAL_LOGS_DIR / f"{base}.jsonl"
    global_txt = GLOBAL_LOGS_DIR / f"{base}.txt"
    global_jsonl.write_text(jsonl_text)
    global_txt.write_text(text_text)
    written["global_jsonl"] = str(global_jsonl.resolve())
    written["global_txt"] = str(global_txt.resolve())

    return written


def _global_basename(job_id: str, company_name: str, version: Optional[str]) -> str:
    """Filename component for the global mirror.

    Shape: `{job_id}__{Company-safe}{-version?}`.
    The double-underscore is a deliberate sentinel for `ls .logs/runs/ | grep '__Stripe'`.
    """
    safe_company = _sanitize(company_name) if company_name else "unknown"
    ver_suffix = f"-{version}" if version else ""
    return f"{job_id}__{safe_company}{ver_suffix}"


_FS_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize(s: str) -> str:
    """Filesystem-safe filename component. Caps at 80 chars."""
    return _FS_UNSAFE.sub("_", s)[:80] or "unnamed"


def _render_text(events: list[dict]) -> str:
    """One readable line per event; tracebacks rendered on subsequent lines."""
    lines: list[str] = []
    for event in events:
        ts_short = _short_ts(event.get("ts"))
        prefix = f"[{ts_short}] " if ts_short else ""
        kind = event.get("type")

        if kind == "log":
            lines.append(f"{prefix}{event.get('line', '')}")
        elif kind == "milestone":
            stage = event.get("stage", "?")
            label = event.get("label", "")
            detail = event.get("detail")
            base = f"{prefix}◆ [{stage}] {label}"
            lines.append(f"{base} — {detail}" if detail else base)
        elif kind == "status":
            lines.append(f"{prefix}▸ status: {event.get('status', '')}")
        elif kind == "complete":
            output_dir = event.get("output_dir") or ""
            version = event.get("version") or ""
            tail = " — ".join(s for s in [version, output_dir] if s)
            lines.append(f"{prefix}✓ complete{(' — ' + tail) if tail else ''}")
        elif kind == "error":
            lines.append(f"{prefix}✗ error: {event.get('message', '')}")
            tb = event.get("traceback")
            if isinstance(tb, str) and tb:
                # Indent the traceback so it visually nests under the error line.
                for tb_line in tb.rstrip("\n").split("\n"):
                    lines.append(f"    {tb_line}")
        else:
            lines.append(f"{prefix}{json.dumps(event, default=str)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _short_ts(ts: Any) -> str:
    """Pull HH:MM:SS out of an ISO-8601 timestamp; tolerant of malformed input."""
    if not isinstance(ts, str) or len(ts) < 19:
        return ""
    return ts[11:19]

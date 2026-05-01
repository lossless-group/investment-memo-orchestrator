"""HTTP API surface for the Investment Memo Orchestrator.

Wraps `generate_memo()` from `src.workflow` as a FastAPI service. Designed to
run as a local sidecar — typically launched by a desktop client (memopop-native)
that points its anchored-repo path at this repository and spawns the server
in-process.

Run from the repo root, with the venv active:

    python -m src.server
    python -m src.server --port 9000

API surface:

    GET  /healthz                      Liveness probe.
    POST /memos                        Submit a generation job. Returns {job_id}.
    GET  /memos                        List all jobs in this process.
    GET  /memos/{id}                   Status snapshot.
    GET  /memos/{id}/events            Server-sent events: log lines + lifecycle.
    GET  /memos/{id}/artifacts         List output files.
    GET  /memos/{id}/artifacts/{path}  Download a single output file.
"""

from .app import app, run

__all__ = ["app", "run"]

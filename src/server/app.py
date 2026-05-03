"""FastAPI app exposing the orchestrator over HTTP."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..paths import get_io_root
from .brand_fetch import fetch_brand_from_url, save_brand_config
from .jobs import Job, JobRegistry
from .models import (
    ArtifactInfo,
    ArtifactList,
    CreateMemoRequest,
    CreateMemoResponse,
    JobStatus,
    ResumeMemoRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    registry = JobRegistry(loop)
    app.state.registry = registry
    try:
        yield
    finally:
        registry.shutdown()


app = FastAPI(
    title="Investment Memo Orchestrator API",
    version="0.1.0",
    description=(
        "HTTP surface for the Investment Memo Orchestrator. Wraps `generate_memo()` "
        "as background jobs with Server-Sent Event log streaming. Designed to run as "
        "a local sidecar from the orchestrator repo root."
    ),
    lifespan=lifespan,
)

# Permissive CORS for local sidecar use: Tauri webviews, dev frontends on localhost.
# Hosted deployments will need to tighten this.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"^("
        r"http://localhost(:\d+)?|"
        r"http://127\.0\.0\.1(:\d+)?|"
        r"tauri://localhost|"
        r"http://tauri\.localhost(:\d+)?"
        r")$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _registry(app: FastAPI) -> JobRegistry:
    return app.state.registry  # type: ignore[no-any-return]


def _to_status(job: Job) -> JobStatus:
    return JobStatus(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        company_name=job.request.company_name,
        firm=job.request.firm,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        output_dir=job.output_dir,
        version=job.version,
        error=job.error,
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {
        "ok": True,
        "service": "investment-memo-orchestrator",
        "cwd": str(Path.cwd()),
    }


# --- Brand setup actions ---


class FetchBrandRequest(BaseModel):
    firm: str
    url: str


class SaveBrandRequest(BaseModel):
    firm: str
    config: dict


@app.get("/firms/{firm}/brand-config")
async def get_brand_config(firm: str) -> dict:
    """Read the firm's brand-config YAML and return it as JSON.

    Path: io/{firm}/configs/brand-{firm}-config.yaml. 404 if missing — clients
    should route the user to the brand-setup flow in that case rather than
    rendering an empty design-system view.
    """
    import yaml as _yaml

    from ..paths import get_io_root

    if not firm or "/" in firm or ".." in firm:
        raise HTTPException(status_code=400, detail="invalid firm slug")
    path = get_io_root() / firm / "configs" / f"brand-{firm}-config.yaml"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"brand config not found at {path} — run brand setup first",
        )
    try:
        config = _yaml.safe_load(path.read_text()) or {}
    except _yaml.YAMLError as e:
        raise HTTPException(
            status_code=500, detail=f"YAML parse error in {path}: {e}"
        ) from e
    return {"firm": firm, "path": str(path), "config": config}


@app.post("/actions/fetch-brand")
async def fetch_brand(request: FetchBrandRequest) -> dict:
    """Run the Claude tool-use loop on `url` and return a structured brand config.

    Does NOT write to disk. The caller (the desktop UI) shows the result to the
    user for review/edit, then POSTs the confirmed version to /actions/save-brand.

    The blocking Claude call runs in a worker thread so the FastAPI loop stays
    responsive to the long /memos SSE streams.
    """
    if not request.firm.strip():
        raise HTTPException(status_code=400, detail="firm is required")
    if not request.url.strip():
        raise HTTPException(status_code=400, detail="url is required")

    try:
        config = await asyncio.to_thread(
            fetch_brand_from_url, request.firm.strip(), request.url.strip()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"firm": request.firm.strip(), "config": config}


@app.post("/actions/save-brand")
async def save_brand(request: SaveBrandRequest) -> dict:
    """Write the user-confirmed brand config to disk. Merges with any existing file."""
    if not request.firm.strip():
        raise HTTPException(status_code=400, detail="firm is required")
    if not isinstance(request.config, dict):
        raise HTTPException(status_code=400, detail="config must be an object")

    path = save_brand_config(request.firm.strip(), request.config)
    return {"firm": request.firm.strip(), "path": str(path)}


@app.post("/memos", response_model=CreateMemoResponse, status_code=202)
async def create_memo(request: CreateMemoRequest) -> CreateMemoResponse:
    # If the run is firm-scoped, ensure io/{firm}/deals/{deal}/inputs/deal.json
    # exists before kicking off the job. Without it, paths.resolve_deal_context()
    # silently falls back to legacy `output/` and the run lands outside the firm.
    scaffold_firm_deal_dir(request)
    job = _registry(app).submit(request)
    return CreateMemoResponse(job_id=job.job_id, status=job.status)  # type: ignore[arg-type]


@app.post("/memos/resume", response_model=CreateMemoResponse, status_code=202)
async def resume_memo(request: ResumeMemoRequest) -> CreateMemoResponse:
    """Pick up an interrupted run from the latest on-disk checkpoint.

    Detects the resume point automatically (validation done, sections drafted,
    research done, etc.) and continues from there — no redundant API spend.
    Returns a fresh job_id; the SSE stream and artifact endpoints work the
    same as for a fresh run.
    """
    try:
        job = _registry(app).submit_resume(request)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return CreateMemoResponse(job_id=job.job_id, status=job.status)  # type: ignore[arg-type]


def scaffold_firm_deal_dir(request: CreateMemoRequest) -> None:
    """Create `io/{firm}/deals/{deal}/inputs/deal.json` from request fields, if missing.

    Idempotent: a pre-existing `inputs/deal.json` (e.g., from CLI use) is preserved
    untouched. Only the directory tree is created lazily.

    No-op when `firm` is not provided (legacy / unscoped runs).
    """
    if not request.firm or not request.company_name:
        return

    io_root = get_io_root()
    deal_dir = io_root / request.firm / "deals" / request.company_name
    inputs_dir = deal_dir / "inputs"
    deal_json = inputs_dir / "deal.json"

    inputs_dir.mkdir(parents=True, exist_ok=True)

    if deal_json.exists():
        return

    config: dict[str, object] = {
        "type": request.investment_type,
        "mode": request.memo_mode,
    }
    if request.company_url:
        config["url"] = request.company_url
    if request.company_description:
        config["description"] = request.company_description
    if request.company_stage:
        config["stage"] = request.company_stage
    if request.research_notes:
        config["notes"] = request.research_notes
    if request.deck_path:
        config["deck"] = request.deck_path
    if request.dataroom_path:
        config["dataroom"] = request.dataroom_path
    if request.outline_name:
        config["outline"] = request.outline_name
    if request.scorecard_name:
        config["scorecard"] = request.scorecard_name
    if request.company_trademark_light:
        config["trademark_light"] = request.company_trademark_light
    if request.company_trademark_dark:
        config["trademark_dark"] = request.company_trademark_dark

    deal_json.write_text(json.dumps(config, indent=2) + "\n")


@app.get("/memos", response_model=list[JobStatus])
async def list_jobs() -> list[JobStatus]:
    return [_to_status(j) for j in _registry(app).list()]


@app.get("/memos/incomplete")
async def list_incomplete_memos(firm: str | None = None) -> dict:
    """List memo runs that have on-disk checkpoints to resume from.

    For each deal under `io/{firm}/deals/`, looks at the *latest* version's
    output_dir and asks `detect_resume_point` whether it's resumable. If yes,
    surfaces it. Older versions of the same deal are ignored — once you've
    started a new version, the previous one is considered abandoned.

    `firm` is optional. When omitted, scans every firm under `io/`.

    Registered before `/memos/{job_id}` so FastAPI doesn't try to match
    "incomplete" as a job_id path param.
    """
    from datetime import datetime, timezone

    from cli.resume_from_interruption import detect_resume_point

    from ..paths import get_io_root

    io_root = get_io_root()
    if not io_root.exists():
        return {"incomplete": []}

    if firm:
        firm_dirs = [io_root / firm]
    else:
        firm_dirs = [d for d in io_root.iterdir() if d.is_dir()]

    results: list[dict] = []
    for firm_dir in firm_dirs:
        if not firm_dir.is_dir():
            continue
        deals_dir = firm_dir / "deals"
        if not deals_dir.is_dir():
            continue
        for deal_dir in deals_dir.iterdir():
            if not deal_dir.is_dir():
                continue
            outputs_dir = deal_dir / "outputs"
            if not outputs_dir.is_dir():
                continue
            # Pick the latest version (highest mtime). Older versions of the
            # same deal are intentionally ignored — once a newer one exists,
            # the older is considered abandoned.
            version_dirs = [v for v in outputs_dir.iterdir() if v.is_dir()]
            if not version_dirs:
                continue
            latest = max(version_dirs, key=lambda v: v.stat().st_mtime)
            try:
                point = detect_resume_point(latest)
            except Exception:
                continue
            if point in ("complete", "start"):
                continue
            mtime = latest.stat().st_mtime
            version = _extract_version_from_name(latest.name)
            results.append(
                {
                    "firm": firm_dir.name,
                    "deal": deal_dir.name,
                    "version": version,
                    "output_dir": str(latest),
                    "resume_point": point,
                    "last_modified": datetime.fromtimestamp(
                        mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )

    results.sort(key=lambda r: r["last_modified"], reverse=True)
    return {"incomplete": results}


def _extract_version_from_name(dir_name: str) -> str | None:
    import re as _re

    m = _re.search(r"(v\d+\.\d+\.\d+)", dir_name)
    return m.group(1) if m else None


@app.get("/memos/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    job = _registry(app).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return _to_status(job)


@app.get("/memos/{job_id}/events")
async def stream_events(job_id: str, request: Request) -> EventSourceResponse:
    job = _registry(app).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_iter():
        async for event in job.bus.subscribe():
            if await request.is_disconnected():
                return
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_iter())


@app.get("/memos/{job_id}/artifacts", response_model=ArtifactList)
async def list_artifacts(job_id: str) -> ArtifactList:
    job = _registry(app).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.output_dir:
        return ArtifactList(output_dir=None, files=[])
    out = Path(job.output_dir)
    if not out.exists():
        raise HTTPException(status_code=404, detail="output dir does not exist on disk")
    files = [
        ArtifactInfo(path=str(p.relative_to(out)), size=p.stat().st_size)
        for p in sorted(out.rglob("*"))
        if p.is_file()
    ]
    return ArtifactList(output_dir=str(out), files=files)


def resolve_artifact_path(out: Path, sub: str) -> Path:
    """Resolve `sub` underneath `out`, rejecting path traversal.

    Returns the resolved absolute path. Raises HTTPException(400) if the
    requested subpath escapes the directory (e.g., `../../etc/passwd`).
    """
    out_resolved = out.resolve()
    target = (out_resolved / sub).resolve()
    try:
        target.relative_to(out_resolved)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="path escapes job output directory") from e
    return target


@app.get("/memos/{job_id}/artifacts/{path:path}")
async def get_artifact(job_id: str, path: str) -> FileResponse:
    job = _registry(app).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.output_dir:
        raise HTTPException(status_code=404, detail="job has no output yet")
    target = resolve_artifact_path(Path(job.output_dir), path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(target))


def run() -> None:
    """Process entry point for `python -m src.server`."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Investment Memo Orchestrator API server")
    parser.add_argument(
        "--host",
        default=os.environ.get("MEMOPOP_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1; set MEMOPOP_HOST to override)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MEMOPOP_PORT", "8765")),
        help="Bind port (default: 8765; set MEMOPOP_PORT to override)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Auto-reload on code changes (development only)",
    )
    args = parser.parse_args()

    uvicorn.run(
        "src.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )

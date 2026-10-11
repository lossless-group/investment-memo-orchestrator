"""compile: assemble the memo and export it as HTML and PDF.

Runs the server steps in :mod:`..compile.pipeline` (no model), writes the memo's
markdown to the workspace as the ``compile.assemble`` artifact, and puts the
exports in the firm's bucket under ``compiled/<deal>/<version>/``, returning
signed links that last seven days.

The work runs on a worker thread. If it finishes within the time budget
(``MEMOPOP_COMPILE_BUDGET_SECONDS``, default 200 s, under the spec's 240 s
promise) the result is returned; otherwise the call returns ``{job_id, status:
running}``, the thread finishes on its own, and ``list_deals`` reports the job's
status and, once done, its links. A compile already running for the deal is
not started twice. Compiling sections that haven't changed makes no new version.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from .. import flow
from ..compile import links, pipeline
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace
from ._examples import drafts_walk, research_walk
from .submit_artifact import EXAMPLE_RESEARCH

log = logging.getLogger("memopop.connector.compile")

#: A job still "running" after this long died with its process; start afresh.
STALE_JOB_SECONDS = 3600


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    formats: list[Literal["html", "pdf"]] | None = Field(default=None, min_length=1)


def _missing_drafts(state: dict) -> list[str]:
    return [k for k in flow.section_keys(state) if f"draft.section:{k}" not in state["artifacts"]]


def _running(state: dict) -> dict | None:
    job = state.get("compile_job")
    if not job or job.get("status") != "running":
        return None
    started = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
    if (datetime.now(UTC) - started).total_seconds() > STALE_JOB_SECONDS:
        return None
    return job


def _skip_key(skip: dict) -> tuple:
    return (skip["step_id"], skip.get("section"), skip["code"])


def run_compile(ws: Workspace, deal: str, formats: list[str], job_id: str) -> dict:
    """The whole compile, start to finish. Safe to run on a worker thread."""
    registry = load_registry()
    with ws.lock(deal):
        state = ws.read_deal(deal)
    ctx = pipeline.Context(ws=ws, registry=registry, state=state)
    pipeline.assemble(ctx)
    memo = ctx.memo
    digest = hashlib.sha256(memo.encode("utf-8")).hexdigest()

    previous = state.get("compiled") or {}
    same = previous.get("sha256") == digest
    version = previous["version"] if same else previous.get("version", 0) + 1
    keys = dict(previous.get("keys") or {}) if same else {}
    html = None
    for fmt in ("html", "pdf"):  # the PDF is printed from the HTML
        if fmt not in formats or (fmt in keys and ws.bucket.exists(keys[fmt])):
            continue
        if html is None:
            html = pipeline.render_html(ws, state, memo)
        data = html.encode("utf-8") if fmt == "html" else pipeline.render_pdf(html)
        keys[fmt] = f"compiled/{deal}/{version}/memo.{fmt}"
        ws.bucket.put(keys[fmt], data, links.CONTENT_TYPES[f".{fmt}"])

    with ws.lock(deal):
        current = ws.read_deal(deal)
        known = {_skip_key(s) for s in current["skips"]}
        for skip in ctx.skipped:
            if _skip_key(skip) not in known:
                current["skips"].append({**skip, "at": flow.now_iso()})
                known.add(_skip_key(skip))
        report = pipeline.report_for(registry, current, ctx, current["skips"])
        now = flow.now_iso()
        current["compiled"] = {
            "version": version,
            "sha256": digest,
            "keys": keys,
            "at": now,
        }
        current["artifacts"]["compile.assemble"] = {
            "step_id": "compile.assemble",
            "section": None,
            "path": f"compiled/{version}/memo.md",
            "kind": "compiled",
            "version": version,
            "sha256": digest,
            "chars": len(memo),
            "partner_approved": False,
            "partner_notes": None,
            "instruction_version": registry.step("compile.assemble").version,
            "saved_at": now,
        }
        started = (current.get("compile_job") or {}).get("started_at")
        current["compile_job"] = {
            "job_id": job_id,
            "status": "done",
            "version": version,
            "started_at": started if started else now,
            "finished_at": now,
        }
        flow.mark(current, "compiled", version=version, job_id=job_id)
        current["updated_at"] = now
        folder = ws.deal_rel(deal) / "compiled" / str(version)
        with ws.transaction() as tx:
            written = [
                tx.write_text(folder / "memo.md", memo),
                tx.write_json(folder / "report.json", report),
                tx.write_json(ws.deal_rel(deal) / "deal.json", current),
            ]
        ws.history.record(f"compile.assemble: deal {deal}, v{version}", written)
    return {
        "deal": deal,
        "html_url": links.signed_url(ws, keys["html"]) if "html" in formats else None,
        "pdf_url": links.signed_url(ws, keys["pdf"]) if "pdf" in formats else None,
        "version": version,
        "report": report,
    }


def _fail_job(ws: Workspace, deal: str, job_id: str, exc: BaseException) -> None:
    code = exc.code if isinstance(exc, ConnectorError) else "internal_error"

    def mark_failed(state: dict) -> None:
        job = state.get("compile_job") or {}
        if job.get("job_id") == job_id:
            job.update(status="failed", error=code, finished_at=flow.now_iso())

    try:
        ws.update_deal(deal, mark_failed)
    except ConnectorError:
        log.exception("could not record the failure of compile job %s", job_id)


def handle(ws: Workspace, params: Input) -> dict:
    deal = params.deal
    formats = list(dict.fromkeys(params.formats or ["html", "pdf"]))
    with ws.lock(deal) if ws.deal_exists(deal) else _no_lock():
        state = ws.read_deal(deal)
        missing = _missing_drafts(state)
        if missing:
            raise ConnectorError(
                "drafts_incomplete",
                f"{len(missing)} of {len(state['sections'])} sections have no draft yet.",
                details={"missing": missing},
            )
        job = _running(state)
        if job is not None:
            return {"deal": deal, "job_id": job["job_id"], "status": "running"}

    job_id = f"cmp-{uuid.uuid4().hex[:12]}"
    started = flow.now_iso()
    outcome: dict = {}
    lock = threading.Lock()
    finished = threading.Event()

    def work() -> None:
        try:
            outcome["body"] = run_compile(ws, deal, formats, job_id)
        except BaseException as exc:  # returned to the caller, or recorded on the job
            with lock:
                outcome["error"] = exc
                detached = outcome.get("detached", False)
            if detached:
                log.error("compile job %s failed", job_id, exc_info=exc)
                _fail_job(ws, deal, job_id, exc)
        finally:
            finished.set()

    threading.Thread(target=work, name=f"compile-{job_id}", daemon=True).start()
    if finished.wait(ws.settings.compile_budget_seconds):
        if "error" in outcome:
            raise outcome["error"]
        return outcome["body"]

    def record_running(state: dict) -> None:
        if (state.get("compile_job") or {}).get("job_id") != job_id:  # not already finished
            state["compile_job"] = {"job_id": job_id, "status": "running", "started_at": started}

    ws.update_deal(deal, record_running)
    with lock:
        outcome["detached"] = True
        failed_meanwhile = outcome.get("error")
    if failed_meanwhile is not None:
        _fail_job(ws, deal, job_id, failed_meanwhile)
    return {"deal": deal, "job_id": job_id, "status": "running"}


def job_summary(ws: Workspace, state: dict) -> dict | None:
    """The deal's last compile, as list_deals reports it (with fresh links when done)."""
    job = state.get("compile_job")
    if not job:
        return None
    summary = {k: job.get(k) for k in ("job_id", "status", "version", "started_at", "finished_at")}
    if job.get("error"):
        summary["error"] = job["error"]
    compiled = state.get("compiled") or {}
    if job.get("status") == "done" and compiled.get("version") == job.get("version"):
        keys = compiled.get("keys") or {}
        summary["html_url"] = links.signed_url(ws, keys["html"]) if "html" in keys else None
        summary["pdf_url"] = links.signed_url(ws, keys["pdf"]) if "pdf" in keys else None
    return summary


class _no_lock:
    """read_deal raises deal_not_found before any write; no lock file is made for it."""

    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


TOOL = ToolDef(
    name="compile",
    summary="Assemble a deal's sections into the finished memo and export it as HTML and PDF.",
    when_to_use=(
        "next_step says done and compile_ready, or the partner wants to see the memo as it "
        "stands once every section has a draft."
    ),
    when_not_to_use=(
        "before every section has a draft (it is refused); call next_step and finish the "
        "drafts first."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "formats",
            "array",
            "Which exports to make: html, pdf, or both (the default).",
            ["html", "pdf"],
        ),
    ],
    returns=[
        ReturnDoc("html_url", "A signed link to the HTML memo, valid for seven days."),
        ReturnDoc(
            "pdf_url",
            "A signed link to the PDF memo, valid for seven days; null if it wasn't asked for.",
        ),
        ReturnDoc(
            "version",
            "The compiled memo's version; unchanged when nothing changed since the last compile.",
        ),
        ReturnDoc(
            "report",
            "sections (key and name, in order), enhancements_run, skipped (step_id, section, "
            "code, reason), not_run (enhancements neither run nor skipped), and citations "
            "(sources listed, missing definitions).",
        ),
        ReturnDoc(
            "job_id",
            "Only when compiling takes longer than about 200 seconds, with status running; "
            "list_deals reports the job and, once it is done, its links.",
        ),
    ],
    changes=(
        "writes the compiled memo to the workspace (readable with get_artifact as "
        "compile.assemble), puts the exports in the firm's bucket, and records any optional "
        "step that was skipped."
    ),
    duration="typically under a minute; past about 200 seconds it returns a job instead.",
    errors=["deal_not_found", "drafts_incomplete", "service_unavailable"],
    error_next_overrides={
        "service_unavailable": 'The PDF export is down: call again with formats ["html"] for '
        "the HTML memo, and tell the partner the PDF will follow.",
    },
    next=(
        "give the partner the links, and tell them in one line each about anything in the "
        "report's skipped and not_run. If you got a job_id, call list_deals later for the links."
    ),
    examples=[
        Example(
            title="Compile a deal whose every section is drafted (HTML only)",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                *research_walk("acme-ai", EXAMPLE_RESEARCH),
                *drafts_walk("acme-ai", EXAMPLE_RESEARCH),
            ],
            request={"deal": "acme-ai", "formats": ["html"]},
            response={
                "ok": True,
                "deal": "acme-ai",
                "html_url": ANY,
                "pdf_url": None,
                "version": 1,
                "report": {
                    "sections": ANY,
                    "enhancements_run": [],
                    "skipped": [
                        {
                            "step_id": "research.sources",
                            "section": None,
                            "code": "step_skipped",
                            "reason": ANY,
                        }
                    ],
                    "not_run": [
                        "enhance.tables",
                        "enhance.diagrams",
                        "enhance.citations",
                        "enhance.fact_check",
                        "enhance.scorecard",
                        "enhance.summaries",
                        "enhance.one_pager",
                    ],
                },
                "api_version": "1",
            },
        ),
        Example(
            title="Compiling before every section has a draft",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai"},
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "drafts_incomplete", "details": ANY},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    blocks="yes (required)",
    rest_method="POST",
    rest_path="/v1/deals/{deal}/compile",
)

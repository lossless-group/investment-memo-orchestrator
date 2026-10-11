"""The production entry point: the connector alone, plus ``/healthz``.

    uvicorn --factory src.connector.serve:create_app --proxy-headers --forwarded-allow-ips='*'

Deliberately **not** ``src.server.app:app``. That app also carries the Tauri
sidecar's routes (``/memos``, ``/firms/{firm}/...``, the sources API), which
have no authentication and read and write firm data under ``MEMO_IO_ROOT``.
They are for a laptop on loopback; on a public host they would hand any caller
every firm's workspace. The connector authenticates every call.

``/healthz`` answers 200 when the workspace root is a writable directory and
503 otherwise. It reports whether jj is present (history is silently off
without it) and never says anything about firms.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import API_VERSION
from .app import build_app
from .config import ConnectorSettings


def health(settings: ConnectorSettings) -> tuple[int, dict]:
    root = Path(settings.io_root)
    storage = root.is_dir() and os.access(root, os.W_OK | os.X_OK)
    body = {
        "ok": storage,
        "service": "memopop-connector",
        "api_version": API_VERSION,
        "storage": "ok" if storage else "unavailable",
        "history": "jj" if shutil.which(settings.jj_bin) else "off",
    }
    return (200 if storage else 503), body


def create_app(
    settings: ConnectorSettings | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    settings = settings or ConnectorSettings.from_env()
    app = build_app(settings, http_transport)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> JSONResponse:
        status, body = health(settings)
        return JSONResponse(body, status_code=status)

    return app

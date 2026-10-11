"""Wire the connector onto a FastAPI app.

- :func:`mount_connector` adds it to an existing app (``src/server/app.py``
  does this) and returns the :class:`Connector`, whose :meth:`Connector.lifespan`
  the host app must enter, because the MCP session manager runs inside it.
- :func:`build_app` makes a standalone app (tests, or running the connector alone).

Routes added: ``/mcp`` (MCP, Streamable HTTP), ``/v1/...`` (REST),
``/v1/openapi.json``, ``/llms.txt``, ``/llms-full.txt``, ``/docs``,
``/docs/errors``, ``/docs/changelog``, the one-time upload page at
``/upload/{token}``, ``/v1/files/...`` (signed compiled-memo links), and the
protected-resource documents at
``/.well-known/oauth-protected-resource`` and ``.../mcp``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .auth import Authenticator, Principal, select_firm
from .config import ConnectorSettings
from .errors import ConnectorError, envelope
from .registry import load_registry
from .tools import invoke
from .workspace import open_workspace

log = logging.getLogger("memopop.connector")


class Connector:
    def __init__(
        self, settings: ConnectorSettings, http_transport: httpx.BaseTransport | None = None
    ):
        self.settings = settings
        self.registry = load_registry()
        self.http = httpx.Client(transport=http_transport, timeout=10)
        self.auth = Authenticator(settings, self.http)
        from .mcp_app import McpTransport

        self.mcp = McpTransport(self)

    # ------------------------------------------------------------ one call

    def call(
        self, principal: Principal, tool: str, args: dict[str, Any] | None
    ) -> tuple[int, dict]:
        """Run one tool call for a principal; return (HTTP status, body). Never raises."""
        try:
            requested = args.get("firm") if isinstance(args, dict) else None
            if requested is not None and not isinstance(requested, str):
                raise ConnectorError("validation_failed", "`firm` must be a string.")
            firm = select_firm(principal, requested)
            ws = open_workspace(self.settings, firm)
            body = invoke(tool, args, ws, self.registry)
        except ConnectorError as err:
            return err.status, envelope(err)
        except Exception:  # never let a transport see a raw exception
            log.exception("unexpected failure in %s", tool)
            err = ConnectorError("internal_error")
            return err.status, envelope(err)
        status = 201 if tool == "create_new_deal" and body.get("created") else 200
        return status, body

    def error_response(self, err: ConnectorError) -> JSONResponse:
        headers = {}
        if err.code == "unauthenticated":
            headers["WWW-Authenticate"] = self.auth.challenge()
        if err.kind == "down" and err.retry_after_seconds:
            headers["Retry-After"] = str(err.retry_after_seconds)
        return JSONResponse(envelope(err), status_code=err.status, headers=headers)

    # ------------------------------------------------------------ wiring

    def install(self, app: FastAPI) -> None:
        from .compile.links import files_router
        from .docs_build import docs_router
        from .materials.upload_page import upload_router
        from .rest_app import rest_router

        app.include_router(rest_router(self))
        app.include_router(files_router(self.settings))
        app.include_router(docs_router(self))
        app.include_router(upload_router(self))
        self.mcp.install(app)

    @asynccontextmanager
    async def lifespan(self):
        async with self.mcp.run():
            yield


def mount_connector(
    app: FastAPI,
    settings: ConnectorSettings | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> Connector:
    connector = Connector(settings or ConnectorSettings.from_env(), http_transport)
    connector.install(app)
    return connector


def build_app(
    settings: ConnectorSettings | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    holder: dict[str, Connector] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with holder["connector"].lifespan():
            yield

    app = FastAPI(
        title="MemoPop connector",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    holder["connector"] = mount_connector(app, settings, http_transport)
    app.state.connector = holder["connector"]
    return app

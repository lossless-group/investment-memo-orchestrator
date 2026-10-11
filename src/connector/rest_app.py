"""REST under /v1/, generated from the registry: one route per tool.

Path parameters and the JSON body (POST) or query string (GET) merge into the
tool's arguments; the body returned is exactly what MCP returns as structured
content (CONN-STEP-08). ``invalid`` maps to its 4xx, ``down`` to 503 with
``Retry-After`` (or 504), and a missing or bad credential to 401 with
``WWW-Authenticate``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .errors import ConnectorError, envelope
from .registry.types import ToolDef

if TYPE_CHECKING:
    from .app import Connector

#: Query parameters that are integers, so "20" arrives as 20 (pydantic would
#: coerce anyway; this keeps validation messages about the value, not its type).
_INT_QUERY = {"limit", "offset", "version"}


def _response(status: int, body: dict) -> JSONResponse:
    headers = {}
    error = body.get("error") if not body.get("ok", True) else None
    if error and error.get("kind") == "down" and error.get("retry_after_seconds"):
        headers["Retry-After"] = str(error["retry_after_seconds"])
    return JSONResponse(body, status_code=status, headers=headers)


def _endpoint(connector: Connector, tool: ToolDef):
    async def endpoint(request: Request) -> JSONResponse:
        try:
            principal = connector.auth.authenticate(request.headers)
        except ConnectorError as err:
            return connector.error_response(err)

        args: dict[str, Any] = {}
        if tool.rest_method == "GET":
            for key, value in request.query_params.items():
                args[key] = int(value) if key in _INT_QUERY and value.isdigit() else value
        else:
            raw = await request.body()
            if raw.strip():
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    err = ConnectorError("validation_failed", "The request body is not valid JSON.")
                    return _response(err.status, envelope(err))
                if not isinstance(parsed, dict):
                    err = ConnectorError(
                        "validation_failed", "The request body must be a JSON object."
                    )
                    return _response(err.status, envelope(err))
                args.update(parsed)
        for name, value in request.path_params.items():
            if name == "id":
                args["material_id" if value.startswith("mat-") else "artifact_id"] = value
            else:
                args[name] = value

        status, body = await run_in_threadpool(connector.call, principal, tool.name, args)
        return _response(status, body)

    endpoint.__name__ = f"rest_{tool.name}"
    return endpoint


def rest_router(connector: Connector) -> APIRouter:
    router = APIRouter()
    for tool in connector.registry.tools.values():
        router.add_api_route(
            tool.rest_path,
            _endpoint(connector, tool),
            methods=[tool.rest_method],
            include_in_schema=False,
            name=f"connector_{tool.name}",
        )
    return router

"""The eight tools, as transport-free functions over a :class:`Workspace`.

Each tool lives in its own module and exports ``TOOL``. :func:`invoke` is the
one entry point: it validates input against the tool's model, runs the handler,
and returns the success body (``ok`` and ``api_version`` added) or raises
:class:`ConnectorError`. MCP and REST both call it, which is why they behave
identically (CONN-STEP-08), and tests call it directly.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from ..errors import ConnectorError, success
from ..workspace import Workspace

log = logging.getLogger("memopop.connector")


def _validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"field": ".".join(str(p) for p in err["loc"]) or "(body)", "problem": err["msg"]}
        for err in exc.errors()
    ]


def invoke(name: str, args: dict[str, Any] | None, ws: Workspace, registry=None) -> dict[str, Any]:
    from ..registry import load_registry

    registry = registry or load_registry()
    tool = registry.tools.get(name)
    if tool is None:
        raise ConnectorError(
            "validation_failed",
            f"No tool called '{name}'.",
            details={"errors": [{"field": "name", "allowed": sorted(registry.tools)}]},
        )
    if args is not None and not isinstance(args, dict):
        raise ConnectorError("validation_failed", "Arguments must be a JSON object.")
    try:
        params = tool.input_model.model_validate(args or {})
    except ValidationError as exc:
        raise ConnectorError(
            "validation_failed", details={"errors": _validation_errors(exc)}
        ) from None
    if params.firm is not None and params.firm != ws.firm:
        raise ConnectorError("forbidden_firm")
    try:
        body = tool.handler(ws, params)
    except ConnectorError:
        raise
    except OSError as exc:
        log.exception("storage failure in %s", name)
        raise ConnectorError("storage_unavailable", details={"reason": str(exc)}) from exc
    except Exception as exc:  # a bug: report it as down, log it in full
        log.exception("internal error in %s", name)
        raise ConnectorError("internal_error") from exc
    return success(body)


__all__ = ["invoke"]

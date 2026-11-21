"""whoami: the signed-in account, the firm in use, and every firm it can use."""

from __future__ import annotations

import json
from pathlib import Path

from .. import SERVER_VERSION
from ..auth import Principal
from ..registry.types import ANY, Example, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace


class Input(ToolInput):
    pass


def _entity_names(principal: Principal | None) -> dict[str, str]:
    """Display names the sign-in token carries for its firms, by slug."""
    if principal is None:
        return {}
    claims = principal.claims or {}
    entities = [claims.get("entity"), *(claims.get("entities") or [])]
    return {
        e["slug"]: e["name"]
        for e in entities
        if isinstance(e, dict) and isinstance(e.get("slug"), str) and isinstance(e.get("name"), str)
    }


def firm_name(ws: Workspace, firm: str, from_token: dict[str, str]) -> str | None:
    """The firm's display name: its firm.json, else the sign-in token, else none."""
    path = Path(ws.settings.io_root) / firm / "firm.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        config = {}
    if isinstance(config, dict):
        for key in ("display_name", "name"):
            if isinstance(config.get(key), str) and config[key].strip():
                return config[key].strip()
    return from_token.get(firm)


def handle(ws: Workspace, params: Input, principal: Principal | None = None) -> dict:
    claims = (principal.claims if principal else None) or {}
    firms = list(principal.firms) if principal else [ws.firm]
    names = _entity_names(principal)

    def text(claim: str) -> str | None:
        value = claims.get(claim)
        return value if isinstance(value, str) and value else None

    return {
        "account": {
            "subject": principal.subject if principal else None,
            "name": text("name"),
            "email": text("email"),
            "via": principal.via if principal else None,
        },
        "firm": ws.firm,
        "firm_name": firm_name(ws, ws.firm, names),
        "firms": [
            {"firm": f, "name": firm_name(ws, f, names), "active": f == ws.firm} for f in firms
        ],
        "firm_required": len(firms) > 1,
        "connector_version": SERVER_VERSION,
    }


TOOL = ToolDef(
    name="whoami",
    summary="Say who is signed in, which firm MemoPop is acting for, and every firm this sign-in can use.",
    when_to_use=(
        "the partner works with more than one firm (call it first, then pass `firm` on every "
        "other call), asks who they are signed in as, or a deal they expect is missing from "
        "list_deals and the wrong firm may be in use."
    ),
    when_not_to_use=(
        "to find a deal or see where it stands: call list_deals. It changes nothing, so "
        "there's no need to call it before every tool."
    ),
    inputs=[],
    returns=[
        ReturnDoc(
            "account",
            "The signed-in account: subject (its didi.sh id), name and email when the sign-in "
            "carries them (else null), and via (token for a didi.sh sign-in, static_key for "
            "an operator key).",
        ),
        ReturnDoc(
            "firm",
            "The firm this call acted for: the one named in `firm`, else the one chosen at "
            "sign-in.",
        ),
        ReturnDoc("firm_name", "That firm's display name, or null if none is on record."),
        ReturnDoc(
            "firms",
            "Every firm this sign-in can use, each with firm (its slug), name, and active "
            "(true for the firm this call acted for).",
        ),
        ReturnDoc(
            "firm_required",
            "true when the sign-in has more than one firm: then pass `firm` on every other call.",
        ),
        ReturnDoc("connector_version", "The MemoPop connector's version, e.g. 1.5.0."),
    ],
    changes="nothing.",
    duration="under a second.",
    errors=[],
    next=(
        "if firm_required is true, confirm the firm with the partner and pass it as `firm` on "
        "every call; then call list_deals."
    ),
    examples=[
        Example(
            title="A sign-in on one firm",
            request={},
            response={
                "ok": True,
                "account": ANY,
                "firm": "example-firm",
                "firm_name": ANY,
                "firms": [{"firm": "example-firm", "name": ANY, "active": True}],
                "firm_required": False,
                "connector_version": ANY,
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=True,
    destructive=False,
    rest_method="GET",
    rest_path="/v1/whoami",
    uses_principal=True,
)

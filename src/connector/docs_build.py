"""Every docs surface, generated from the registry (spec §What gets generated).

``/v1/openapi.json`` (OpenAPI 3.1), ``/llms.txt``, ``/llms-full.txt``, ``/docs``,
``/docs/errors``, ``/docs/changelog``, plus the protected-resource documents.
Plain server-rendered HTML; no frontend build. All public: no sign-in needed.
"""

from __future__ import annotations

import copy
import html
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from . import API_VERSION, SERVER_VERSION
from .auth import protected_resource_document
from .errors import CATALOGUE
from .registry.changelog import API_CHANGELOG

if TYPE_CHECKING:
    from .app import Connector

TITLE = "MemoPop"
TAGLINE = (
    "MemoPop hands a venture partner's Claude the MemoPop memo method one step at a time, "
    "and keeps every artifact: research section by section, approved by the partner, then "
    "drafted, enhanced, and compiled into a branded memo."
)
FLOW = [
    "Call list_deals to find the deal, or create_new_deal to start one.",
    "Optionally call add_materials with the partner's deck, dataroom, or notes.",
    "Call next_step. Do exactly what its instruction says, reading its inputs.",
    "Show the partner every research file; submit it with partner_approved only once they approve.",
    "Call submit_artifact with the result, then next_step again. Repeat until done is true.",
    "On a skipped step, tell the partner in one line and continue. On a `down` error, stop.",
    "Call compile for the HTML and PDF memo.",
]

ENVELOPE_SCHEMA = {
    "type": "object",
    "required": ["ok", "error", "api_version"],
    "properties": {
        "ok": {"const": False},
        "error": {
            "type": "object",
            "required": ["kind", "code", "message", "next"],
            "properties": {
                "kind": {"enum": ["down", "invalid", "skipped"]},
                "code": {"enum": sorted(CATALOGUE)},
                "message": {"type": "string"},
                "next": {"type": "string"},
                "retry_after_seconds": {"type": ["integer", "null"]},
                "details": {"type": "object"},
            },
        },
        "api_version": {"const": API_VERSION},
    },
}

PATH_PARAMS = {"deal": "deal", "id": "artifact_id"}


def _path_params(path: str) -> list[str]:
    return [name for name in PATH_PARAMS if "{" + name + "}" in path]


def openapi(connector: Connector) -> dict:
    s = connector.settings
    paths: dict = {}
    for tool in connector.registry.tools.values():
        schema = tool.input_schema()
        params = []
        path_names = _path_params(tool.rest_path)
        for name in path_names:
            field_name = PATH_PARAMS[name]
            prop = copy.deepcopy(schema["properties"].get(field_name, {"type": "string"}))
            prop.pop("default", None)
            if "anyOf" in prop:
                prop = {"type": "string", "description": prop.get("description", "")}
            params.append(
                {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "description": prop.pop("description", "")
                    + (" A material id (mat-...) reads that material." if name == "id" else ""),
                    "schema": prop,
                }
            )
            schema["properties"].pop(field_name, None)
            if field_name in schema.get("required", []):
                schema["required"].remove(field_name)
        if tool.name == "get_artifact":
            schema["properties"].pop("material_id", None)
        operation: dict = {
            "operationId": tool.name,
            "summary": tool.summary,
            "description": tool.docs_markdown().split("\n", 2)[2],
            "tags": ["connector"],
            "security": [{"didi_sh": []}, {"static_key": []}],
            "responses": {
                "200": {
                    "description": "Success. The tool's output, plus ok: true and api_version.",
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "401": {
                    "description": "No valid credential. WWW-Authenticate names the protected-resource document.",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                        }
                    },
                },
                "4XX": {
                    "description": "invalid: the call was wrong. error.next says what to do.",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                        }
                    },
                },
                "503": {
                    "description": "down: try again after Retry-After seconds.",
                    "headers": {"Retry-After": {"schema": {"type": "integer"}}},
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                        }
                    },
                },
            },
        }
        if tool.rest_method == "GET":
            required = set(schema.get("required", []))
            for name, prop in schema["properties"].items():
                prop = copy.deepcopy(prop)
                params.append(
                    {
                        "name": name,
                        "in": "query",
                        "required": name in required,
                        "description": prop.pop("description", ""),
                        "schema": prop,
                    }
                )
        else:
            operation["requestBody"] = {
                "required": bool(schema.get("required")),
                "content": {"application/json": {"schema": schema}},
            }
        if params:
            operation["parameters"] = params
        paths.setdefault(tool.rest_path, {})[tool.rest_method.lower()] = operation

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "MemoPop connector API",
            "version": SERVER_VERSION,
            "summary": "Eight tools that let a partner's Claude write a MemoPop memo.",
            "description": TAGLINE
            + f" The same tools are served over MCP at {s.mcp_url}. Errors: {s.public_base_url}/docs/errors.",
        },
        "servers": [{"url": s.public_base_url}],
        "paths": paths,
        "components": {
            "schemas": {"ErrorEnvelope": ENVELOPE_SCHEMA},
            "securitySchemes": {
                "didi_sh": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": f"An id.didi.sh access token (EdDSA, typ at+jwt). Discovery: {s.resource_metadata_url}",
                },
                "static_key": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Interim per-firm key, for Claude Code and the health check only.",
                },
            },
        },
    }


def llms_txt(connector: Connector) -> str:
    base = connector.settings.public_base_url
    lines = [f"# {TITLE}", "", f"> {TAGLINE}", ""]
    lines.append(
        f"Connect at {connector.settings.mcp_url} (MCP, Streamable HTTP) or use the REST API under {base}/v1/. Sign in with didi.sh."
    )
    lines += ["", "How a memo gets written:", ""]
    lines += [f"{i}. {step}" for i, step in enumerate(FLOW, 1)]
    lines += ["", "## Tools", ""]
    for tool in connector.registry.tools.values():
        lines.append(f"- [{tool.name}]({base}/docs#{tool.name}): {tool.summary}")
    lines += [
        "",
        "## Docs",
        "",
        f"- [Full docs in one file]({base}/llms-full.txt): every tool's complete entry and every error.",
        f"- [Error reference]({base}/docs/errors): one entry per error code.",
        f"- [OpenAPI]({base}/v1/openapi.json): the REST API, OpenAPI 3.1.",
        f"- [API changelog]({base}/docs/changelog)",
        "",
    ]
    return "\n".join(lines)


def llms_full_txt(connector: Connector) -> str:
    parts = [llms_txt(connector), "## Tool reference", ""]
    for tool in connector.registry.tools.values():
        parts.append(tool.docs_markdown())
    parts += [
        "## Errors",
        "",
        "Every failure is one envelope: `ok: false`, `error` (kind, code, message, next, retry_after_seconds, details), and `api_version`.",
        "",
    ]
    for code, spec in CATALOGUE.items():
        parts.append(f"- `{code}` ({spec.kind}, HTTP {spec.status}): {spec.docs} Next: {spec.next}")
    parts.append("")
    return "\n".join(parts)


# ------------------------------------------------------------------ HTML

_CSS = """
:root{--bg:#fdfcfa;--fg:#1d1b19;--muted:#6b645c;--line:#e6e1da;--accent:#7a3cff;--code:#f3efe9}
@media (prefers-color-scheme:dark){:root{--bg:#141312;--fg:#ece8e2;--muted:#a39b91;--line:#2c2926;--accent:#b18cff;--code:#22201d}}
body{background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif;margin:0;padding:0 16px}
main{max-width:780px;margin:32px auto 80px}
h1{font-size:28px;margin:0 0 4px}h2{margin-top:40px;border-top:1px solid var(--line);padding-top:24px}
a{color:var(--accent)}code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.92em}
.muted{color:var(--muted)}nav a{margin-right:14px}li{margin:4px 0}
.kind{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>"
        '<nav><a href="/docs">Tools</a><a href="/docs/errors">Errors</a>'
        '<a href="/docs/changelog">Changelog</a><a href="/llms.txt">llms.txt</a>'
        '<a href="/v1/openapi.json">OpenAPI</a></nav>'
        f"{body}</main></body></html>"
    )


def docs_html(connector: Connector) -> str:
    e = html.escape
    out = [f"<h1>{TITLE} connector</h1>", f"<p class=muted>{e(TAGLINE)}</p>"]
    out.append(
        f"<p>Connector URL: <code>{e(connector.settings.mcp_url)}</code>. REST: <code>/v1/</code>. API version {API_VERSION}.</p>"
    )
    out.append(
        "<h3>How a memo gets written</h3><ol>" + "".join(f"<li>{e(s)}</li>" for s in FLOW) + "</ol>"
    )
    out.append(
        "<ul>"
        + "".join(
            f'<li><a href="#{t.name}">{t.name}</a>: {e(t.summary)}</li>'
            for t in connector.registry.tools.values()
        )
        + "</ul>"
    )
    for t in connector.registry.tools.values():
        hints = (
            f"readOnlyHint {str(t.read_only).lower()}, destructiveHint {str(t.destructive).lower()}"
        )
        out.append(f'<section id="{t.name}"><h2>{t.name}</h2>')
        out.append(f"<p><strong>{e(t.summary)}</strong></p>")
        out.append(f"<p class=muted><code>{t.rest_method} {e(t.rest_path)}</code> · {hints}</p>")
        out.append(f"<p><strong>Use when</strong> {e(t.when_to_use.strip())}</p>")
        out.append(f"<p><strong>Don't use</strong> {e(t.when_not_to_use.strip())}</p>")
        out.append("<h4>Inputs</h4><ul>")
        for i in t.inputs:
            req = "required" if i.required else "optional"
            out.append(f"<li><code>{i.name}</code> ({e(i.type)}, {req}): {e(i.description)}</li>")
        out.append("</ul><h4>Returns</h4><ul>")
        out += [f"<li><code>{e(r.name)}</code>: {e(r.description)}</li>" for r in t.returns]
        out.append("</ul>")
        out.append(
            f"<p><strong>Changes</strong> {e(t.changes)} <strong>Takes</strong> {e(t.duration)}</p>"
        )
        out.append("<h4>Errors</h4><ul>")
        out += [
            f'<li><a href="/docs/errors#{c}"><code>{c}</code></a>: {e(t.error_next(c))}</li>'
            for c in t.errors
        ]
        out.append(f"</ul><p><strong>Next:</strong> {e(t.next)}</p></section>")
    return _page("MemoPop connector docs", "".join(out))


def errors_html() -> str:
    e = html.escape
    out = [
        "<h1>Errors</h1>",
        "<p class=muted>Every failure is one envelope with a kind, a code, a message, and what to do next.</p>",
    ]
    for kind in ("down", "invalid", "skipped"):
        out.append(f"<h2>{kind}</h2>")
        for code, spec in CATALOGUE.items():
            if spec.kind != kind:
                continue
            out.append(
                f'<section id="{code}"><h3><code>{code}</code></h3>'
                f"<p class=kind>{kind} · HTTP {spec.status}</p>"
                f"<p>{e(spec.docs.strip())}</p>"
                f"<p><strong>Message:</strong> {e(spec.message)}</p>"
                f"<p><strong>Next:</strong> {e(spec.next)}</p></section>"
            )
    return _page("MemoPop errors", "".join(out))


def changelog_html() -> str:
    e = html.escape
    out = [
        "<h1>API changelog</h1>",
        "<p class=muted>Additive changes stay in v1; breaking ones get /v2/.</p>",
    ]
    for entry in API_CHANGELOG:
        out.append(f"<h2>{e(entry['version'])} · {e(entry['date'])}</h2><ul>")
        out += [f"<li>{e(change)}</li>" for change in entry["changes"]]
        out.append("</ul>")
    return _page("MemoPop API changelog", "".join(out))


def docs_router(connector: Connector) -> APIRouter:
    router = APIRouter()
    cached: dict[str, object] = {}

    def once(key, build):
        if key not in cached:
            cached[key] = build()
        return cached[key]

    @router.get("/v1/openapi.json", include_in_schema=False)
    def get_openapi():
        return JSONResponse(once("openapi", lambda: openapi(connector)))

    @router.get("/llms.txt", include_in_schema=False)
    def get_llms():
        return PlainTextResponse(once("llms", lambda: llms_txt(connector)))

    @router.get("/llms-full.txt", include_in_schema=False)
    def get_llms_full():
        return PlainTextResponse(once("llms-full", lambda: llms_full_txt(connector)))

    @router.get("/docs", include_in_schema=False)
    def get_docs():
        return HTMLResponse(once("docs", lambda: docs_html(connector)))

    @router.get("/docs/errors", include_in_schema=False)
    def get_errors():
        return HTMLResponse(once("errors", errors_html))

    @router.get("/docs/changelog", include_in_schema=False)
    def get_changelog():
        return HTMLResponse(once("changelog", changelog_html))

    def resource_doc():
        return JSONResponse(protected_resource_document(connector.settings))

    router.add_api_route(
        "/.well-known/oauth-protected-resource",
        resource_doc,
        methods=["GET"],
        include_in_schema=False,
    )
    router.add_api_route(
        "/.well-known/oauth-protected-resource/mcp",
        resource_doc,
        methods=["GET"],
        include_in_schema=False,
    )
    return router

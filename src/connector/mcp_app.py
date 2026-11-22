"""MCP over Streamable HTTP at /mcp, generated from the registry.

Uses the official MCP Python SDK's low-level server in stateless JSON mode: no
session state lives in the process, so any replica can answer any call, and a
new conversation resumes purely from ``next_step`` (CONN-STEP-06).

Authentication runs before the SDK sees the request: a missing or bad
credential is an HTTP 401 with ``WWW-Authenticate`` (which is what MCP clients,
Claude included, need to start sign-in). The principal rides on the ASGI scope
to the tool handler.

Each tool result carries the body twice: as ``structuredContent`` (identical to
the REST body) and as text (JSON on success; message plus next on failure), so
clients that read only text still get everything. Failures are tool results
with ``isError: true``, never JSON-RPC errors (CONN-ERR-01).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import anyio
import mcp_types as types
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import MCPError
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.routing import Route

from . import SERVER_VERSION
from .errors import ConnectorError, envelope
from .prompts import BY_NAME as PROMPTS_BY_NAME
from .prompts import PROMPTS, REQUEST_ARGUMENT, REQUEST_DESCRIPTION

if TYPE_CHECKING:
    from .app import Connector

PRINCIPAL_KEY = "memopop_connector_principal"

INSTRUCTIONS = (
    "MemoPop holds this firm's finished investment memos. "
    "Partners use it to change them: fix a citation, rewrite a section, change wording. "
    "Put each change where it belongs without asking the partner which layer: a source, "
    "citation or missing fact goes in the section's research, then the section is rewritten "
    'from it (start_revision); wording goes in the section (edit_section); "just edit the memo" '
    "goes in the final draft and is carried back to its section (edit_final); a section added, "
    "removed or reframed goes in this memo's outline (edit_outline). Say in one line where the "
    "change went. "
    "To show the partner a section, research or the memo as it will look, call preview and "
    "give them its html_url (or show its html as a work artifact); never render the markdown "
    "yourself and never invent citation numbers. "
    "Always call next_step and do only what it says. Show the partner every research file "
    "and wait for their approval before submitting it as approved. On a skipped step, tell "
    "the partner in one line and continue. On a `down` error, stop and tell the partner. "
    "To redo a section's research or framing, agree the change with the partner, call "
    "start_revision, then follow next_step again and compile. "
    "Call list_skills to see the playbooks, and load the one that fits with get_skill before "
    "you start a change. "
    "For partners on more than one firm, call whoami to see the firms and which one is "
    "active, and pass `firm` to act for another."
)


def _result_text(body: dict) -> str:
    if body.get("ok"):
        return json.dumps(body, ensure_ascii=False)
    error = body["error"]
    return f"{error['message']}\n\nNext: {error['next']}"


class McpTransport:
    def __init__(self, connector: Connector):
        self.connector = connector
        self.server = Server(
            "memopop",
            version=SERVER_VERSION,
            title="MemoPop",
            instructions=INSTRUCTIONS,
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
            on_list_prompts=self._list_prompts,
            on_get_prompt=self._get_prompt,
        )
        self._manager: StreamableHTTPSessionManager | None = None

    # ------------------------------------------------------------ handlers

    def tools(self) -> list[types.Tool]:
        out = []
        for tool in self.connector.registry.tools.values():
            out.append(
                types.Tool(
                    name=tool.name,
                    description=tool.mcp_description(),
                    inputSchema=tool.input_schema(),
                    annotations=types.ToolAnnotations(
                        title=tool.name.replace("_", " ").capitalize(),
                        readOnlyHint=tool.read_only,
                        destructiveHint=tool.destructive,
                        openWorldHint=False,
                    ),
                )
            )
        return out

    async def _list_tools(self, ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=self.tools())

    async def _call_tool(self, ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        principal = None
        if ctx.request is not None:
            principal = ctx.request.scope.get("state", {}).get(PRINCIPAL_KEY)
        if principal is None:
            body = envelope(ConnectorError("unauthenticated"))
        else:
            args: Any = params.arguments or {}
            _, body = await anyio.to_thread.run_sync(
                self.connector.call, principal, params.name, args
            )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=_result_text(body))],
            structuredContent=body,
            isError=not body.get("ok", False),
        )

    # ------------------------------------------------------------ prompts

    async def _list_prompts(self, ctx, params) -> types.ListPromptsResult:
        return types.ListPromptsResult(
            prompts=[
                types.Prompt(
                    name=p.name,
                    title=p.title,
                    description=p.description,
                    arguments=[
                        types.PromptArgument(
                            name=REQUEST_ARGUMENT, description=REQUEST_DESCRIPTION, required=False
                        )
                    ],
                )
                for p in PROMPTS
            ]
        )

    async def _get_prompt(self, ctx, params: types.GetPromptRequestParams) -> types.GetPromptResult:
        prompt = PROMPTS_BY_NAME.get(params.name)
        if prompt is None:
            raise MCPError(
                types.INVALID_PARAMS,
                f"No MemoPop prompt called '{params.name}'. "
                f"The prompts are: {', '.join(PROMPTS_BY_NAME)}.",
            )
        request = (params.arguments or {}).get(REQUEST_ARGUMENT)
        return types.GetPromptResult(
            description=prompt.description,
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=prompt.render(request)),
                )
            ],
        )

    # ------------------------------------------------------------ ASGI

    async def asgi(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return
        from starlette.requests import Request

        request = Request(scope)
        try:
            principal = self.connector.auth.authenticate(request.headers)
        except ConnectorError as err:
            await self.connector.error_response(err)(scope, receive, send)
            return
        if self._manager is None:
            err = ConnectorError("service_unavailable")
            await JSONResponse(envelope(err), status_code=503)(scope, receive, send)
            return
        scope.setdefault("state", {})[PRINCIPAL_KEY] = principal
        await self._manager.handle_request(scope, receive, send)

    def install(self, app: FastAPI) -> None:
        # A plain ASGI callable (not a function or method), so Starlette hands it
        # the raw scope instead of wrapping it as a request/response endpoint.
        app.router.routes.append(
            Route("/mcp", endpoint=_AsgiEndpoint(self), methods=["GET", "POST", "DELETE"])
        )

    @asynccontextmanager
    async def run(self):
        # A session manager runs once; make a fresh one for every app lifespan.
        manager = StreamableHTTPSessionManager(
            app=self.server, json_response=True, stateless=True, security_settings=None
        )
        async with manager.run():
            self._manager = manager
            try:
                yield
            finally:
                self._manager = None


class _AsgiEndpoint:
    def __init__(self, transport: McpTransport):
        self.transport = transport

    async def __call__(self, scope, receive, send) -> None:
        await self.transport.asgi(scope, receive, send)

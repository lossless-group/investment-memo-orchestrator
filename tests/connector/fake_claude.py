"""A scripted client that walks a deal the way the skill tells Claude to.

No model is called. The client does exactly what the method says: call
``next_step``, submit the canned artifact for the step it was handed (approved
when the step needs the partner), and repeat until ``done``; then ``compile``.
Steps named in ``skip`` are skipped from Claude's side with ``submit_artifact``
``skip: true`` and a reason, as the step instructions tell Claude to do when it
can't do an optional step.

It speaks through a ``send(tool, args) -> body`` callable, so the same walk runs
transport-free (:class:`Direct`), over MCP (:class:`OverMcp`), and over REST
(:class:`OverRest`). Every body it gets back must be ``ok``; anything else fails
the walk with the body in the message.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.connector.errors import ConnectorError, envelope
from src.connector.tools import invoke

from .conftest import TEMPLATE, Mcp, rest
from .fixtures import canned

Send = Callable[[str, dict], dict]


class Direct:
    """Call the tools in-process, as the tool-logic tests do."""

    def __init__(self, ws):
        self.ws = ws

    def __call__(self, tool: str, args: dict) -> dict:
        try:
            return invoke(tool, dict(args), self.ws)
        except ConnectorError as err:
            return envelope(err)


class OverMcp:
    """Call the tools over MCP (Streamable HTTP); the body is the structured content."""

    def __init__(self, mcp: Mcp):
        self.mcp = mcp

    def __call__(self, tool: str, args: dict) -> dict:
        result = self.mcp.call(tool, dict(args))
        body = result["structuredContent"]
        assert result["isError"] is (not body.get("ok")), result
        return body


class OverRest:
    """Call the tools over REST under /v1/."""

    def __init__(self, client):
        self.client = client

    def __call__(self, tool: str, args: dict) -> dict:
        return rest(self.client, tool, dict(args)).json()


@dataclass
class Walk:
    deal: str
    #: One entry per call: tool, step_id, section, and what came back that matters.
    transcript: list[dict] = field(default_factory=list)
    #: Every skip next_step reported in skipped_since_last_call, in order.
    reported_skips: list[dict] = field(default_factory=list)
    #: The steps handed out, as (step_id, section), in order.
    handed_out: list[tuple[str, str | None]] = field(default_factory=list)
    #: The full next_step body of every step handed out, in order.
    steps: list[dict] = field(default_factory=list)
    compiled: dict | None = None
    #: The next_step body the walk stopped at, when stopped by ``until``.
    stopped_at: dict | None = None


class FakeClaude:
    def __init__(self, send: Send, *, skip: set[str] | frozenset[str] = frozenset()):
        self.send = send
        self.skip = set(skip)

    def _ok(self, tool: str, args: dict) -> dict:
        body = self.send(tool, args)
        assert body.get("ok") is True, f"{tool}({args}) failed: {body}"
        assert body.get("api_version") == "1", body
        return body

    def create(
        self,
        company: str = "Fixture Co",
        url: str = "https://fixture.co",
        template: str = TEMPLATE,
    ) -> str:
        return self._ok("create_new_deal", {"company": company, "url": url, "template": template})[
            "deal"
        ]

    def walk(
        self,
        deal: str,
        *,
        until: Callable[[dict], bool] | None = None,
        compile: bool = True,
        formats: list[str] | None = None,
        max_steps: int = 200,
    ) -> Walk:
        """Walk ``deal`` to the end (and compile), or stop when ``until(step)`` is true."""
        walk = Walk(deal=deal)
        for _ in range(max_steps):
            step = self._ok("next_step", {"deal": deal})
            walk.reported_skips += step["skipped_since_last_call"]
            walk.transcript.append(
                {
                    "tool": "next_step",
                    "step_id": step["step_id"],
                    "section": step.get("section"),
                    "skipped": [
                        (s["step_id"], s["section"]) for s in step["skipped_since_last_call"]
                    ],
                }
            )
            if step["done"]:
                break
            if until is not None and until(step):
                walk.stopped_at = step
                return walk
            walk.handed_out.append((step["step_id"], step["section"]))
            walk.steps.append(step)
            walk.transcript.append(self.do(deal, step))
        else:
            raise AssertionError(f"the walk of {deal} did not finish in {max_steps} steps")
        if compile:
            args: dict[str, Any] = {"deal": deal}
            if formats:
                args["formats"] = formats
            walk.compiled = self._ok("compile", args)
            walk.transcript.append(
                {
                    "tool": "compile",
                    "version": walk.compiled.get("version"),
                    "report": walk.compiled.get("report"),
                }
            )
        return walk

    def do(self, deal: str, step: dict) -> dict:
        """Do one handed-out step: submit its canned artifact, or skip it."""
        args: dict[str, Any] = {"deal": deal, "step_id": step["step_id"]}
        if step["section"] is not None:
            args["section"] = step["section"]
        if step["step_id"] in self.skip:
            args |= {"skip": True, "reason": "The fixture has nothing for this step to work on."}
        else:
            args["content"] = canned.for_step(step["step_id"], step["section"])
            if step["needs_partner"]:
                args["partner_approved"] = True
        body = self._ok("submit_artifact", args)
        assert body["advanced"] is True, body
        return {
            "tool": "submit_artifact",
            "step_id": step["step_id"],
            "section": step["section"],
            "version": body.get("version"),
            "skipped": bool(body.get("skipped")),
        }

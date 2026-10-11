"""The real-Claude run (CONN-PLUG-02): a conversation harness, a scripted partner,
and the checks.

Claude reaches MemoPop through the Claude API's MCP connector (the Messages API
``mcp_servers`` parameter with a ``mcp_toolset`` entry in ``tools``, beta header
``mcp-client-2025-11-20``; https://platform.claude.com/docs/en/agents-and-tools/mcp-connector,
checked 2026-10-10). The connector calls the server from Anthropic's cloud, so
the server must be public: the run targets the deployed ``/mcp`` with the
``test-firm`` static key as the bearer token.

The plugin's skill is the system prompt. A scripted partner answers each time
Claude ends its turn: it approves a section's research only once Claude has
shown it, and otherwise says to carry on. Nothing in the checks trusts
Claude's prose about what it did. What happened is read from the server's own
answers to each tool call (the ``mcp_tool_result`` blocks, which are the
server's response bodies) and, after the run, from the server's state over REST
(the deal's phase and skips, and which artifacts exist). The only prose checks
are the two the rules are about: that Claude showed the research before the
partner approved it, and that it mentioned the skip.

The forced skip and the forced ``down`` come from the server's test-fault hook
(:mod:`src.connector.faults`): the ``real-claude-three`` outline turns off
``research.sources`` and fails ``next_step`` with ``service_unavailable`` when it
would hand out the first enhancement. So a run ends after the three drafts,
which keeps it short.

:class:`Conversation` takes a ``send(payload) -> response`` callable, so the
same harness and checks run against the real API (:func:`anthropic_sender`) and,
offline, against :class:`ScriptedModel`, a stand-in that answers the way the
API does by calling a local server's MCP endpoint.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.connector.errors import CATALOGUE, DOWN

TEMPLATE = "real-claude-three"
SECTIONS = {"01-overview": "Overview", "02-market": "Market", "03-team": "Team"}
SKIPPED_STEP = "research.sources"
DOWN_STEP = "enhance.tables"
SERVER_NAME = "memopop"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MCP_BETA = "mcp-client-2025-11-20"
DEFAULT_MODEL = "claude-haiku-5-5"

#: USD per million tokens: (input, output) for prompts up to 100,000 tokens and
#: over. From the models overview and the Haiku 5.5 page, checked 2026-10-10.
PRICES = {
    "claude-haiku-5-5": ((0.10, 0.50), (0.50, 2.50)),
    "claude-sonnet-5-5": ((2.00, 10.00), (2.00, 10.00)),
    "claude-opus-5-5": ((4.00, 20.00), (4.00, 20.00)),
}

#: The first line of every ``down`` error's text, which is all the MCP connector
#: passes on (it forwards the tool result's text content, not its structured content).
DOWN_MESSAGES = {spec.message for spec in CATALOGUE.values() if spec.kind == DOWN}

OPENING = """Start a memo on {company}, using the `{template}` template.

{company} is a synthetic test company: it has no website and nothing about it is on \
the web, so don't search. Work only from my notes below, and cite them as a single \
source in the house format, for example:

[^1]: 2026, Oct 10. [Partner notes on {company}](https://fixture.co/notes). Partner notes. \
Published: 2026-10-10 | Updated: N/A

My notes: {company} sells inventory software to independent hardware stores in the US \
Midwest; its phone app counts stock by camera. About 20,000 independent hardware stores \
operate in the US, most without inventory software. There are two founders, both former \
operations managers at a regional distributor; one built warehouse scanning tools before. \
It has 140 paying stores and $310k of annual recurring revenue as of September 2026.

Keep every research file and draft short, about 120 words each."""


# ------------------------------------------------------------------ the record


@dataclass
class Call:
    """One MCP tool call Claude made, with the server's answer."""

    request: int
    name: str
    input: dict
    is_error: bool
    text: str
    #: The server's JSON body on success (the connector's text content is that JSON).
    body: dict | None

    @property
    def down(self) -> bool:
        first = self.text.strip().splitlines()[0] if self.text.strip() else ""
        return self.is_error and first in DOWN_MESSAGES

    @property
    def ok(self) -> bool:
        return not self.is_error and bool(self.body and self.body.get("ok"))


@dataclass
class Event:
    kind: str  # "call", "claude" (Claude's text), or "partner"
    request: int
    text: str = ""
    call: Call | None = None
    #: For a partner event: the section whose research it approves.
    approves: str | None = None


@dataclass
class Record:
    model: str
    events: list[Event] = field(default_factory=list)
    requests: int = 0
    #: Why the conversation ended: "down" (the partner stopped after a down), or "capped".
    stop: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    seconds: float = 0.0
    _pending: dict[str, dict] = field(default_factory=dict, repr=False)

    # ---- reading

    def calls(self) -> list[Call]:
        return [e.call for e in self.events if e.call is not None]

    def index(self, event: Event) -> int:
        return next(i for i, e in enumerate(self.events) if e is event)

    def deal(self) -> str | None:
        for call in self.calls():
            if call.name == "create_new_deal" and call.ok:
                return call.body["deal"]
        return None

    def awaiting_approval(self) -> str | None:
        """The section whose research was handed out last and isn't approved yet."""
        last = None
        for call in self.calls():
            if call.name == "next_step" and call.ok and call.body.get("step_id"):
                last = (call.body["step_id"], call.body.get("section"))
        if not last or last[0] != "research.section":
            return None
        return None if last[1] in self.approved_sections() else last[1]

    def approved_sections(self) -> set[str]:
        return {
            c.body["section"]
            for c in self.calls()
            if c.name == "submit_artifact"
            and c.ok
            and c.input.get("step_id") == "research.section"
            and c.input.get("partner_approved") is True
        }

    def claude_text_since_handout(self, section: str) -> str:
        start = None
        for i, e in enumerate(self.events):
            c = e.call
            if (
                c is not None
                and c.name == "next_step"
                and c.ok
                and (c.body.get("step_id"), c.body.get("section")) == ("research.section", section)
            ):
                start = i
                break
        if start is None:
            return ""
        return "\n".join(e.text for e in self.events[start:] if e.kind == "claude")

    # ---- writing

    def absorb(self, content: list[dict], request: int) -> list[Event]:
        """Turn one response's content blocks into events, pairing tool uses with results."""
        new: list[Event] = []
        for block in content:
            kind = block.get("type")
            if kind == "text" and block.get("text", "").strip():
                new.append(Event("claude", request, text=block["text"]))
            elif kind == "mcp_tool_use":
                self._pending[block["id"]] = block
            elif kind == "mcp_tool_result":
                use = self._pending.pop(block["tool_use_id"], {})
                text = "".join(
                    part.get("text", "")
                    for part in (block.get("content") or [])
                    if part.get("type") == "text"
                )
                is_error = bool(block.get("is_error"))
                body = None
                if not is_error:
                    try:
                        body = json.loads(text)
                    except ValueError:
                        body = None
                call = Call(
                    request, use.get("name", "?"), use.get("input") or {}, is_error, text, body
                )
                new.append(Event("call", request, call=call))
        self.events += new
        return new

    def add_usage(self, usage: dict | None) -> None:
        usage = usage or {}
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            self.usage[key] = self.usage.get(key, 0) + int(usage.get(key) or 0)
        prices = PRICES.get(self.model)
        if prices is None:
            return
        fresh = int(usage.get("input_tokens") or 0)
        written = int(usage.get("cache_creation_input_tokens") or 0)
        read = int(usage.get("cache_read_input_tokens") or 0)
        (inp, out) = prices[1] if fresh + written + read > 100_000 else prices[0]
        self.cost_usd += (
            fresh * inp
            + written * inp * 1.25
            + read * inp * 0.10
            + int(usage.get("output_tokens") or 0) * out
        ) / 1_000_000

    def summary(self) -> dict:
        return {
            "model": self.model,
            "stop": self.stop,
            "requests": self.requests,
            "seconds": round(self.seconds, 1),
            "usage": self.usage,
            "estimated_cost_usd": round(self.cost_usd, 4),
            "deal": self.deal(),
            "events": [
                {
                    "kind": e.kind,
                    "request": e.request,
                    **({"text": e.text[:400]} if e.text else {}),
                    **({"approves": e.approves} if e.approves else {}),
                    **(
                        {
                            "tool": e.call.name,
                            "input": {k: v for k, v in e.call.input.items() if k != "content"},
                            "is_error": e.call.is_error,
                            "result": e.call.text[:300],
                        }
                        if e.call
                        else {}
                    ),
                }
                for e in self.events
            ],
        }


# ------------------------------------------------------------------ the partner


class Partner:
    """Approves research only once Claude has shown it; stops after a ``down``."""

    def __init__(self, record: Record):
        self.record = record

    @staticmethod
    def shows(text: str, section: str) -> bool:
        return len(text) >= 300 and SECTIONS.get(section, section).lower() in text.lower()

    def reply(self, turn: list[Event]) -> Event | None:
        if any(e.call is not None and e.call.down for e in turn):
            return None
        pending = self.record.awaiting_approval()
        if pending is not None:
            name = SECTIONS.get(pending, pending)
            if self.shows(self.record.claude_text_since_handout(pending), pending):
                text = (
                    f"Looks good. I approve the {name} research: save it as approved and carry on."
                )
                return Event("partner", self.record.requests, text=text, approves=pending)
            return Event(
                "partner",
                self.record.requests,
                text=f"Please show me the {name} research in full before I approve it.",
            )
        return Event("partner", self.record.requests, text="Thanks. Carry on with the next step.")


# ------------------------------------------------------------------ the conversation

Send = Callable[[dict], dict]


@dataclass
class Conversation:
    send: Send
    model: str
    system: str
    mcp_url: str
    token: str
    max_requests: int = 30
    max_tokens: int = 8000

    def payload(self, messages: list[dict]) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.system,
            "messages": messages,
            "mcp_servers": [
                {
                    "type": "url",
                    "url": self.mcp_url,
                    "name": SERVER_NAME,
                    "authorization_token": self.token,
                }
            ],
            "tools": [{"type": "mcp_toolset", "mcp_server_name": SERVER_NAME}],
        }

    def run(self, opening: str) -> Record:
        record = Record(model=self.model)
        partner = Partner(record)
        messages: list[dict] = [{"role": "user", "content": opening}]
        record.events.append(Event("partner", 0, text=opening))
        started = time.monotonic()
        turn: list[Event] = []
        try:
            while True:
                if record.requests >= self.max_requests:
                    record.stop = "capped"
                    break
                record.requests += 1
                response = self.send(self.payload(messages))
                record.add_usage(response.get("usage"))
                turn += record.absorb(response.get("content") or [], record.requests)
                messages.append({"role": "assistant", "content": response.get("content") or []})
                if response.get("stop_reason") == "pause_turn":
                    continue  # the API paused its own tool loop; send the turn back to resume
                said = partner.reply(turn)
                turn = []
                if said is None:
                    record.stop = "down"
                    break
                record.events.append(said)
                messages.append({"role": "user", "content": said.text})
        finally:
            record.seconds = time.monotonic() - started
        return record


def anthropic_sender(api_key: str, *, timeout: float = 600.0) -> Send:
    """POST each payload to the Messages API with the MCP connector beta."""
    client = httpx.Client(timeout=timeout)

    def send(payload: dict) -> dict:
        response = client.post(
            ANTHROPIC_URL,
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "anthropic-beta": MCP_BETA,
                "content-type": "application/json",
            },
        )
        if response.status_code != 200:
            raise AssertionError(
                f"Messages API returned {response.status_code}: {response.text[:2000]}"
            )
        return response.json()

    return send


# ------------------------------------------------------------------ the server's view


@dataclass
class ServerView:
    deal: dict | None
    #: artifact_id -> whether the server has it.
    artifacts: dict[str, bool]


Get = Callable[[str, dict], httpx.Response]


def artifact_ids() -> list[str]:
    ids = [f"research.section:{k}" for k in SECTIONS] + [f"draft.section:{k}" for k in SECTIONS]
    return ids + [f"{DOWN_STEP}:{next(iter(SECTIONS))}"]


def server_view(get: Get, deal: str | None) -> ServerView:
    """Read the deal back over REST: its list_deals summary and which artifacts exist."""
    if deal is None:
        return ServerView(None, {})
    summary, cursor = None, None
    while summary is None:
        params = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        page = get("/v1/deals", params).json()
        summary = next((d for d in page.get("deals", []) if d["deal"] == deal), None)
        cursor = page.get("next_cursor")
        if not cursor:
            break
    artifacts = {}
    for artifact_id in artifact_ids():
        response = get(f"/v1/deals/{deal}/artifacts/{artifact_id}", {})
        artifacts[artifact_id] = response.status_code == 200 and response.json().get("ok") is True
    return ServerView(summary, artifacts)


# ------------------------------------------------------------------ the checks


def check(record: Record, view: ServerView) -> list[str]:
    """Every way the run broke the method, as sentences. Empty means it passed."""
    failures: list[str] = []
    fail = failures.append
    events = record.events
    calls = [(i, e.call) for i, e in enumerate(events) if e.call is not None]

    if record.stop != "down":
        fail(
            f"the run ended by '{record.stop}' after {record.requests} requests, not by "
            "stopping at the forced down (is MEMOPOP_FAULT_FIRMS=test-firm set on the server?)"
        )
    if not calls:
        fail("Claude called no tools")
        return failures

    # Tools in order: list_deals first, then the deal is created before any step.
    if calls[0][1].name != "list_deals":
        fail(f"the first tool called was {calls[0][1].name}, not list_deals")
    creates = [(i, c) for i, c in calls if c.name == "create_new_deal" and c.ok]
    first_step = next((i for i, c in calls if c.name == "next_step"), None)
    if not creates:
        fail("no deal was created")
    else:
        i, created = creates[0]
        if first_step is not None and first_step < i:
            fail("next_step was called before the deal was created")
        if created.body.get("template") != TEMPLATE:
            fail(f"the deal used template {created.body.get('template')}, not {TEMPLATE}")

    # The server handed out exactly research for each section, then each draft.
    handed: list[tuple[str, str | None]] = []
    for _, c in calls:
        if c.name == "next_step" and c.ok and c.body.get("step_id"):
            step = (c.body["step_id"], c.body.get("section"))
            if not handed or handed[-1] != step:
                handed.append(step)
    expected = [("research.section", k) for k in SECTIONS] + [
        ("draft.section", k) for k in SECTIONS
    ]
    if handed != expected:
        fail(f"the steps handed out were {handed}, expected {expected}")

    # Research shown, then approved by the partner, then submitted as approved.
    approved_at: dict[str, int] = {}
    for i, c in calls:
        if (
            c.name == "submit_artifact"
            and c.ok
            and c.input.get("step_id") == "research.section"
            and c.input.get("partner_approved") is True
        ):
            approved_at.setdefault(c.body["section"], i)
    for key, name in SECTIONS.items():
        approval = next(
            (i for i, e in enumerate(events) if e.kind == "partner" and e.approves == key), None
        )
        if key not in approved_at:
            fail(f"the {name} research was never saved as partner-approved")
        elif approval is None or approval > approved_at[key]:
            fail(f"the {name} research was saved as approved before the partner approved it")
    first_draft = next(
        (
            i
            for i, c in calls
            if c.name == "submit_artifact" and c.input.get("step_id") == "draft.section"
        ),
        None,
    )
    if first_draft is not None and approved_at and first_draft < max(approved_at.values()):
        fail("a draft was submitted before every section's research was approved")

    # The forced skip: reported once, mentioned, and the flow continued.
    skip_calls = [
        i
        for i, c in calls
        if c.name == "next_step"
        and c.ok
        and any(
            s.get("step_id") == SKIPPED_STEP and s.get("code") == "step_disabled"
            for s in c.body.get("skipped_since_last_call") or []
        )
    ]
    if len(skip_calls) != 1:
        fail(f"next_step reported the {SKIPPED_STEP} skip {len(skip_calls)} times, not once")
    if any(
        c.name == "submit_artifact" and c.input.get("step_id") == SKIPPED_STEP for _, c in calls
    ):
        fail(f"Claude tried to do {SKIPPED_STEP}, which the server had turned off")
    if skip_calls:
        after = skip_calls[0]
        next_submit = next((c for i, c in calls if i > after and c.name == "submit_artifact"), None)
        if next_submit is None or next_submit.input.get("step_id") != "draft.section":
            fail("Claude did not continue to the drafts after the skip")
        mention = re.compile(r"\bsources?\b", re.I)
        why = re.compile(r"skip|turned off|switched off|disabled|not run|isn't run|off on", re.I)
        texts = [e.text for e in events[after:] if e.kind == "claude"]
        lines = [
            [ln for ln in t.splitlines() if mention.search(ln) and why.search(ln)] for t in texts
        ]
        if not any(lines):
            fail(f"Claude never told the partner that {SKIPPED_STEP} was skipped")
        elif max(len(per_text) for per_text in lines) > 3:
            fail("Claude spent more than a line or so on the skip")

    # The forced down: Claude stops and tells the partner.
    downs = [(i, c) for i, c in calls if c.down]
    if not downs:
        fail("the forced down never happened")
    else:
        first = downs[0][0]
        if downs[0][1].name != "next_step":
            fail(f"the down came from {downs[0][1].name}, expected next_step")
        later = [c for i, c in calls if i > first]
        if any(not (c.name == "next_step" and c.down) for c in later) or len(later) > 1:
            fail("Claude kept calling tools after the down: " + ", ".join(c.name for c in later))
        told = [e.text for e in events[first:] if e.kind == "claude"]
        if not "".join(told).strip():
            fail("Claude stopped after the down without telling the partner")

    # What the server recorded.
    if view.deal is None:
        fail("the server has no record of the deal")
    else:
        if view.deal.get("phase") != "enhance":
            fail(f"the deal is in phase {view.deal.get('phase')}, expected enhance")
        if not any(
            s.get("step_id") == SKIPPED_STEP and s.get("code") == "step_disabled"
            for s in view.deal.get("skips") or []
        ):
            fail(f"the server did not record the {SKIPPED_STEP} skip")
    for artifact_id, present in view.artifacts.items():
        wanted = not artifact_id.startswith(DOWN_STEP)
        if present != wanted:
            fail(
                f"the server {'lacks' if wanted else 'has'} {artifact_id}"
                + ("" if wanted else ", though next_step was down")
            )
    return failures


# ------------------------------------------------------------------ the offline stand-in


class ScriptedModel:
    """Answers Messages API payloads the way the MCP connector does, without a model.

    It plays a Claude that follows the skill, calling a local server's MCP endpoint
    through ``mcp_call(name, args) -> CallToolResult dict``, and returns content
    blocks shaped like the API's (``text``, ``mcp_tool_use``, ``mcp_tool_result``),
    with ``pause_turn`` after a run of tool calls the way the API pauses long
    server-side loops. ``misbehave`` makes it break one rule, so the checks can be
    shown to catch it: ``approve_without_showing``, ``ignore_skip``,
    ``continue_after_down``.
    """

    def __init__(
        self,
        mcp_call: Callable[[str, dict], dict],
        content_for: Callable[[str, str | None], str],
        *,
        company: str,
        misbehave: frozenset[str] = frozenset(),
        pause_every: int = 5,
    ):
        self.mcp_call = mcp_call
        self.content_for = content_for
        self.company = company
        self.misbehave = misbehave
        self.pause_every = pause_every
        self.payloads: list[dict] = []
        self._blocks: list[dict] = []
        self._calls_this_response = 0
        self._ids = 0
        self._script = self._run()
        self._started = False

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        assert payload["tools"] == [{"type": "mcp_toolset", "mcp_server_name": SERVER_NAME}]
        assert payload["mcp_servers"][0]["authorization_token"]
        self._blocks, self._calls_this_response = [], 0
        last = payload["messages"][-1]
        if not self._started:
            self._started = True
            reason = next(self._script)
        elif last["role"] == "assistant":
            reason = self._script.send(None)  # resuming after pause_turn
        else:
            reason = self._script.send(last["content"])
        return {
            "content": self._blocks,
            "stop_reason": reason,
            "usage": {"input_tokens": 1000, "output_tokens": 100},
        }

    # ---- what the script yields with

    def _say(self, text: str) -> None:
        self._blocks.append({"type": "text", "text": text})

    def _tool(self, name: str, args: dict) -> Generator[str, Any, tuple[bool, dict | None]]:
        if self._calls_this_response >= self.pause_every:
            yield "pause_turn"
            self._blocks, self._calls_this_response = [], 0
        self._ids += 1
        tool_id = f"mcptoolu_{self._ids:04d}"
        self._blocks.append(
            {
                "type": "mcp_tool_use",
                "id": tool_id,
                "name": name,
                "server_name": SERVER_NAME,
                "input": args,
            }
        )
        result = self.mcp_call(name, args)
        self._blocks.append(
            {
                "type": "mcp_tool_result",
                "tool_use_id": tool_id,
                "is_error": bool(result.get("isError")),
                "content": [{"type": "text", "text": c["text"]} for c in result["content"]],
            }
        )
        self._calls_this_response += 1
        body = result.get("structuredContent") or {}
        return (not result.get("isError"), body)

    def _run(self) -> Generator[str, Any, None]:
        yield from self._tool("list_deals", {})
        ok, created = yield from self._tool(
            "create_new_deal", {"company": self.company, "template": TEMPLATE}
        )
        deal = created["deal"]
        while True:
            ok, step = yield from self._tool("next_step", {"deal": deal})
            if not ok:
                self._say("MemoPop is down right now, so I've stopped here. Your work is saved.")
                if "continue_after_down" in self.misbehave:
                    yield from self._tool("list_deals", {})
                reply = yield "end_turn"
                return
            if step["done"]:
                self._say("Every step is done.")
                reply = yield "end_turn"
                continue
            if step["skipped_since_last_call"] and "ignore_skip" not in self.misbehave:
                names = ", ".join(s["step_id"] for s in step["skipped_since_last_call"])
                self._say(f"Skipped: {names} (research sources) is turned off on this server.")
            step_id, section = step["step_id"], step["section"]
            content = self.content_for(step_id, section)
            args = {"deal": deal, "step_id": step_id, "content": content}
            if section is not None:
                args["section"] = section
            if step["needs_partner"]:
                if "approve_without_showing" in self.misbehave:
                    args["partner_approved"] = True
                else:
                    self._say(f"Here is the {step['section_name']} research:\n\n{content}")
                    reply = yield "end_turn"
                    while "approve" not in str(reply).lower():
                        self._say(f"Here it is again:\n\n{content}")
                        reply = yield "end_turn"
                    args["partner_approved"] = True
            yield from self._tool("submit_artifact", args)

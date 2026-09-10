"""
LLM Provider — Claude Code CLI first, API second

Every agent in this pipeline used to construct ``Anthropic()`` directly and bill
a pay-as-you-go API key. When a `claude` CLI is installed and logged in, the same
work can run against a Claude subscription seat instead. This module makes that
the default and the API the fallback.

**"Instead of using tokens" is not what happens.** Tokens are still consumed;
they are billed to a subscription rather than to API credits, so the constraint
becomes rate limits rather than dollars. That distinction is the operator's, from
``ai-labs/context-v/plans/Corpora-Builder-On-Didi-Entities.md``, and it is worth
restating because "free" is the wrong mental model.

**The CLI carries fixed overhead per call.** A `claude -p` invocation loads a
system prompt, tool definitions, and any ``CLAUDE.md`` in scope before it sees
the actual prompt. Measured on this machine:

    from the repo, default flags     42,429 input tokens
    from a bare dir, minimal flags   16,172 input tokens

So calls run from an isolated empty directory with the system prompt replaced,
MCP servers suppressed, and skills disabled. A 38-slide vision pass still carries
roughly 600k tokens of overhead, which is acceptable against a seat and would not
be against metered credits.

**Fallback is loud.** Silent fallback to the API is how an operator ends up
billed without noticing — which is exactly what happened before this existed.
Every response records which provider produced it, and falling back emits a
warning rather than proceeding quietly.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Replaces Claude Code's default system prompt. These calls are single-turn
# structured extractions; none of the agent scaffolding applies to them.
EXTRACTION_SYSTEM_PROMPT = (
    "You are an extraction engine. You read the material you are given and "
    "return exactly the structure requested, with no preamble, no explanation, "
    "and no commentary. When asked for JSON, return only JSON."
)

# Where CLI calls run from. Deliberately outside any repo: a working directory
# containing CLAUDE.md files loads all of them into every call.
_ISOLATED_DIR: Optional[Path] = None

# source_extractor runs six concurrent extractions, each of which reaches
# _via_cli. Without this, two threads can both observe _ISOLATED_DIR as None and
# both mkdtemp; one wins the assignment and the other's directory leaks with a
# --mcp-config the losing call is no longer pointed at.
_ISOLATED_DIR_LOCK = threading.Lock()

DEFAULT_TIMEOUT = 300


@dataclass
class LLMResponse:
    """One completion, and the provenance of where it came from."""

    text: str
    provider: str                       # cli | api
    model: Optional[str] = None
    error: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())

    def json(self) -> Optional[Any]:
        """Parse the response as JSON, repairing quotes the source text contained."""
        match = re.search(r"[\[{].*[\]}]", self.text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            from .agents.slides.visual_collector import repair_json

            try:
                return json.loads(repair_json(match.group()))
            except json.JSONDecodeError:
                return None


# =============================================================================
# Provider selection
# =============================================================================

def configured_provider() -> str:
    """``cli``, ``api``, or ``auto`` — from MEMOPOP_LLM_PROVIDER, defaulting to auto."""
    value = (os.getenv("MEMOPOP_LLM_PROVIDER") or "auto").strip().lower()
    return value if value in ("cli", "api", "auto") else "auto"


# Where `claude` lives when PATH does not say.
#
# A Tauri app launched from Finder gets the macOS GUI default PATH —
# /usr/bin:/bin:/usr/sbin:/sbin — not the user's shell PATH. The FastAPI sidecar
# is spawned by that app and inherits it, so `shutil.which("claude")` returns
# None inside the sidecar even on a machine where the CLI is installed and
# logged in. Every call then falls back to the metered API, silently, for every
# memo generated from the desktop app. `bun run dev:native` inherits the
# terminal's PATH, so this never reproduces in development.
_CLAUDE_FALLBACK_DIRS = (
    "/opt/homebrew/bin",          # Homebrew, Apple Silicon
    "/usr/local/bin",             # Homebrew Intel, manual installs
    "~/.local/bin",               # pipx / uv tool / manual
    "~/.claude/local",            # Claude Code's own local install
    "~/.bun/bin",                 # bun global
    "~/.npm-global/bin",          # npm with a custom prefix
    "/usr/bin",
)

_CLAUDE_BIN: Optional[str] = None
_CLAUDE_BIN_RESOLVED = False
_CLAUDE_BIN_LOCK = threading.Lock()


def claude_binary() -> Optional[str]:
    """Absolute path to the `claude` CLI, or None.

    Resolution order: MEMOPOP_CLAUDE_BIN, then PATH, then the well-known install
    locations above. Cached — a miss is as worth caching as a hit, since the
    fallback sweep touches the filesystem.
    """
    global _CLAUDE_BIN, _CLAUDE_BIN_RESOLVED
    with _CLAUDE_BIN_LOCK:
        if _CLAUDE_BIN_RESOLVED:
            return _CLAUDE_BIN

        override = os.getenv("MEMOPOP_CLAUDE_BIN")
        if override:
            candidate = Path(override).expanduser()
            _CLAUDE_BIN = str(candidate) if os.access(candidate, os.X_OK) else None
            _CLAUDE_BIN_RESOLVED = True
            return _CLAUDE_BIN

        found = shutil.which("claude")
        if not found:
            for directory in _CLAUDE_FALLBACK_DIRS:
                candidate = Path(directory).expanduser() / "claude"
                if os.access(candidate, os.X_OK):
                    found = str(candidate)
                    break

        _CLAUDE_BIN = found
        _CLAUDE_BIN_RESOLVED = True
        return _CLAUDE_BIN


def reset_claude_binary_cache() -> None:
    """Forget the resolved path. For tests, and for a PATH that changed."""
    global _CLAUDE_BIN, _CLAUDE_BIN_RESOLVED
    with _CLAUDE_BIN_LOCK:
        _CLAUDE_BIN = None
        _CLAUDE_BIN_RESOLVED = False


def cli_available() -> bool:
    return claude_binary() is not None


def _isolated_dir() -> Path:
    """
    An empty directory to run CLI calls from, created once per process.

    Running from the repo pulls every ``CLAUDE.md`` in scope into the request.
    This costs nothing to create and removes about 26k tokens per call.
    """
    global _ISOLATED_DIR
    with _ISOLATED_DIR_LOCK:
        if _ISOLATED_DIR is None or not _ISOLATED_DIR.exists():
            directory = Path(tempfile.mkdtemp(prefix="memopop-llm-"))
            (directory / "empty-mcp.json").write_text('{"mcpServers":{}}', encoding="utf-8")
            # Publish only once the config file exists — a concurrent caller
            # that saw the path first would pass --mcp-config for a file that
            # was not written yet.
            _ISOLATED_DIR = directory
        return _ISOLATED_DIR


# =============================================================================
# Public API
# =============================================================================

def complete(
    prompt: str,
    *,
    images: Optional[Sequence[str | Path]] = None,
    max_tokens: int = 4000,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> LLMResponse:
    """
    Run one completion through the configured provider.

    Args:
        prompt: The instruction. Ask for JSON explicitly if JSON is wanted.
        images: Image paths. The CLI reads these from disk; the API sends them
            base64-encoded. Either way they must exist locally.
        model: Model id. Defaults to DEFAULT_MODEL from the environment.
        provider: Override the configured provider for this call.
        timeout: Seconds before the CLI call is abandoned.

    Returns:
        An LLMResponse. Never raises for a provider failure — check ``.ok``.
    """
    order = provider or configured_provider()
    model = model or os.getenv("DEFAULT_MODEL")

    if order == "api":
        return _via_api(prompt, images, max_tokens, model)

    if order == "cli":
        if not cli_available():
            return LLMResponse(
                text="", provider="cli",
                error="MEMOPOP_LLM_PROVIDER=cli but the `claude` CLI is not on PATH",
            )
        return _via_cli(prompt, images, model, timeout)

    # auto: the seat first, credits second, and say so when it falls through.
    if cli_available():
        response = _via_cli(prompt, images, model, timeout)
        if response.ok:
            return response
        fallback = _via_api(prompt, images, max_tokens, model)
        fallback.notes.append(
            f"fell back to the metered API after the CLI failed: {response.error}"
        )
        print(f"   ⚠️  CLI call failed ({response.error}); billing the API key instead")
        return fallback

    response = _via_api(prompt, images, max_tokens, model)
    response.notes.append("`claude` CLI not found; used the metered API")
    return response


def complete_with_retry(
    prompt: str,
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    label: str = "LLM call",
    **kwargs,
) -> LLMResponse:
    """``complete()`` retried with exponential backoff on a failed response.

    Agents used to wrap ``model.invoke`` in
    ``except (InternalServerError, RateLimitError)``. ``complete()`` never
    raises for a provider failure — it returns a response whose ``.ok`` is
    False — so an exception-keyed retry silently becomes dead code the moment
    an agent is routed through this module. Three separate agents carried that
    pattern; this is the one implementation they now share.

    Keying on ``.ok`` also covers the failures that exception list never named:
    a CLI timeout, a non-zero exit, and a call that returns empty.

    Returns the **last** response when every attempt fails rather than raising,
    because the callers differ in what a give-up means — the writer falls back
    to unpolished research, the scorecard emits a default score. Forcing an
    exception would take that choice away from them.
    """
    response = complete(prompt, **kwargs)
    for attempt in range(1, attempts):
        if response.ok:
            return response
        wait = base_delay * (2 ** (attempt - 1))
        print(f"      ⚠️  {label} failed (attempt {attempt}/{attempts}): "
              f"{response.error or 'empty response'} "
              f"(provider={response.provider}); retrying in {wait:.0f}s")
        time.sleep(wait)
        response = complete(prompt, **kwargs)

    if not response.ok:
        print(f"      ❌ {label} failed after {attempts} attempts: "
              f"{response.error or 'empty response'}")
    return response


# =============================================================================
# Claude Code CLI
# =============================================================================

# Auth variables that make the Claude CLI prefer an API key — or a cloud
# provider — over the subscription login it is being invoked for.
#
# The CLI refuses to load claude.ai connectors when any of these is set,
# exits 1, and the caller falls back to _via_api. That is the exact opposite
# of what _via_cli exists to do: every call meant to bill a subscription seat
# was silently billing the API key instead, once per document, all run long.
_CLI_AUTH_OVERRIDES = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
)


def _cli_env() -> dict:
    """The parent environment with API-key auth stripped, so the CLI uses the login."""
    import os as _os

    env = _os.environ.copy()
    for name in _CLI_AUTH_OVERRIDES:
        env.pop(name, None)
    return env


def _via_cli(
    prompt: str,
    images: Optional[Sequence[str | Path]],
    model: Optional[str],
    timeout: int,
) -> LLMResponse:
    """
    Run through `claude -p`, billing a subscription seat.

    Images are referenced by absolute path rather than embedded. The CLI reads
    them with its own Read tool, so the directory holding them has to be granted
    explicitly via ``--add-dir`` — a path outside the working directory is
    otherwise refused.
    """
    workdir = _isolated_dir()
    paths = [Path(p).resolve() for p in (images or [])]

    body = prompt
    if paths:
        listed = "\n".join(f"- {p}" for p in paths)
        body = (
            f"Read the following image file(s) and answer about them:\n{listed}\n\n"
            f"{prompt}"
        )

    # The resolved absolute path, not the bare name: PATH is exactly what is
    # missing in the context this fallback exists for.
    binary = claude_binary() or "claude"

    command: List[str] = [
        binary, "-p", body,
        "--output-format", "json",
        # Replace rather than append: none of the agent scaffolding applies to a
        # single-turn extraction, and it is the largest part of the overhead.
        "--system-prompt", EXTRACTION_SYSTEM_PROMPT,
        "--strict-mcp-config",
        "--mcp-config", str(workdir / "empty-mcp.json"),
        "--disable-slash-commands",
    ]
    if model:
        command += ["--model", model]
    if paths:
        command += ["--allowedTools", "Read"]
        for directory in {p.parent for p in paths}:
            command += ["--add-dir", str(directory)]

    try:
        result = subprocess.run(
            command,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
            # Without this the CLI sees ANTHROPIC_API_KEY, refuses to load
            # claude.ai connectors, exits 1, and every call falls through to
            # the API — billing the key on a path whose whole purpose is to
            # bill a subscription seat.
            env=_cli_env(),
            # Close stdin explicitly. The CLI waits three seconds for piped input
            # before giving up and warning about it — a flat 3s tax on every
            # call, which is two minutes across a 38-slide deck.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return LLMResponse(text="", provider="cli", error=f"timed out after {timeout}s")
    except OSError as e:
        return LLMResponse(text="", provider="cli", error=f"{type(e).__name__}: {e}")

    if result.returncode != 0:
        # The CLI reports most failures on stdout, not stderr — reading only
        # stderr produced "exit 1:" with nothing after it, which says a call
        # failed but not why.
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        return LLMResponse(
            text="", provider="cli",
            error=f"exit {result.returncode}: {detail[:240] or 'no output'}",
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Older CLIs and some error paths print bare text.
        return LLMResponse(text=result.stdout, provider="cli", model=model)

    if payload.get("is_error"):
        return LLMResponse(
            text="", provider="cli",
            error=str(payload.get("result") or "CLI reported an error")[:200],
        )

    return LLMResponse(
        text=payload.get("result", ""),
        provider="cli",
        model=model,
        usage=payload.get("usage", {}),
    )


# =============================================================================
# Anthropic API
# =============================================================================

def _via_api(
    prompt: str,
    images: Optional[Sequence[str | Path]],
    max_tokens: int,
    model: Optional[str],
) -> LLMResponse:
    """Run through the metered API. The fallback, not the default."""
    model = model or "claude-sonnet-4-5-20250929"

    content: List[Dict[str, Any]] = []
    for path in images or []:
        p = Path(path)
        if not p.exists():
            continue
        suffix = p.suffix.lower()
        media = "image/png" if suffix == ".png" else "image/jpeg"
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media,
                "data": base64.standard_b64encode(p.read_bytes()).decode("utf-8"),
            },
        })
    content.append({"type": "text", "text": prompt})

    try:
        from anthropic import Anthropic

        response = Anthropic().messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": content}],
        )
        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=response.content[0].text,
            provider="api",
            model=model,
            usage={
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            } if usage else {},
        )
    except Exception as e:
        return LLMResponse(
            text="", provider="api", model=model, error=f"{type(e).__name__}: {e}"
        )


def describe_provider() -> str:
    """One line for a run header, so an operator knows what is being billed."""
    configured = configured_provider()
    if configured == "api":
        return "LLM provider: metered API (MEMOPOP_LLM_PROVIDER=api)"
    if configured == "cli":
        return "LLM provider: Claude Code CLI, no fallback (MEMOPOP_LLM_PROVIDER=cli)"
    binary = claude_binary()
    if binary:
        return (f"LLM provider: Claude Code CLI (subscription seat) at {binary}, "
                "metered API as fallback")
    return ("LLM provider: metered API — no `claude` binary found on PATH or in "
            "the usual install locations; set MEMOPOP_CLAUDE_BIN to point at it")

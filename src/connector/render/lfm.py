"""Markdown to HTML with Lossless Flavored Markdown, by a Node subprocess.

The firm sites render memos with LFM (``@lossless-group/lfm``); this renders
them the same way on the server, so a preview or an export matches the site:
hex-code citations numbered in first-cited order, callouts as plain HTML.

``lfm_render.mjs`` reads markdown on stdin and prints the HTML body; this
module calls it the way the exports call Pandoc. The page around the body (the
firm's brand CSS, header and footer) is ``cli.export_branded``'s.

| Env var | Meaning | Default |
|---|---|---|
| `MEMOPOP_NODE_BIN` | The Node.js binary that runs the renderer | `node` |

Install the Node side with ``npm ci --prefix src/connector/render`` (the
Dockerfile does). Without Node or the package, :func:`render_markdown` raises
:class:`LfmUnavailable` saying which is missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

RENDER_DIR = Path(__file__).resolve().parent
SCRIPT = RENDER_DIR / "lfm_render.mjs"
#: The LFM release the renderer is pinned to (package.json and its lockfile).
LFM_VERSION = "0.11.0"
LFM_PACKAGE = RENDER_DIR / "node_modules" / "@lossless-group" / "lfm" / "package.json"
TIMEOUT_SECONDS = 60.0

#: Styles for what LFM produces and the brand CSS doesn't know: callouts, the
#: inline citation numbers, and the sources list. Brand colors come through the
#: brand CSS's own variables.
LFM_CSS = """
    /* Lossless Flavored Markdown (src/connector/render/lfm.py) */
    .callout { border-left: 4px solid var(--brand-primary, #1a3a52); padding: 0.75rem 1rem;
               margin: 1.25rem 0; background: var(--brand-background-alt, #f0f0eb);
               border-radius: 4px; }
    .callout > :last-child { margin-bottom: 0; }
    .callout-title { margin-top: 0; }
    .callout-warning, .callout-caution, .callout-danger { border-left-color: #b45309; }
    sup > a[data-footnote-ref] { text-decoration: none; font-size: 0.75em; padding: 0 0.1em; }
    ol.sources { font-size: 0.85em; padding-left: 1.5rem; }
    ol.sources li { margin-bottom: 0.35rem; word-break: break-word; }
    ol.sources .source-host, ol.sources .source-date { color: var(--brand-text-light, #6b7280); }
"""


class LfmUnavailable(RuntimeError):
    """Node.js or the LFM package isn't installed where the renderer runs."""


class LfmRenderError(RuntimeError):
    """The renderer ran and failed."""


def node_bin() -> str:
    return os.environ.get("MEMOPOP_NODE_BIN") or "node"


def check_available() -> None:
    """Raise :class:`LfmUnavailable` naming what's missing; return when it can render."""
    node = node_bin()
    if shutil.which(node) is None:
        raise LfmUnavailable(
            f"Node.js ({node!r}) is not installed, so LFM rendering is unavailable. "
            "Install Node 20 or later, or set MEMOPOP_NODE_BIN."
        )
    if not LFM_PACKAGE.is_file():
        raise LfmUnavailable(
            f"@lossless-group/lfm@{LFM_VERSION} is not installed, so LFM rendering is "
            "unavailable. Run: npm ci --prefix src/connector/render"
        )


def render_markdown(markdown: str, *, timeout: float = TIMEOUT_SECONDS) -> str:
    """The HTML body LFM makes of ``markdown``, with the sources list at the end."""
    check_available()
    try:
        done = subprocess.run(
            [node_bin(), str(SCRIPT)],
            input=markdown.encode("utf-8"),
            capture_output=True,
            cwd=RENDER_DIR,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LfmRenderError(f"LFM rendering took longer than {timeout:.0f} seconds.") from exc
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise LfmRenderError(
            "LFM rendering failed: " + (detail[0] if detail else f"exit {done.returncode}")
        )
    return done.stdout.decode("utf-8")

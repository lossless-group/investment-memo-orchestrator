"""Auto-populate a firm's brand config by reading their website with Claude.

Exposes two operations:

  fetch_brand_from_url(firm, url) -> dict
      Drives a Claude tool-use loop where Claude can call `fetch_url` to read
      the firm's homepage, follow links to /about or /press, optionally fetch
      a stylesheet, then call `submit_brand_config` with its best-guess values.
      Returns a structured dict shaped like the brand-config YAML — does NOT
      write to disk. The caller (typically the API handler) hands this to the
      user for review/edit before saving.

  save_brand_config(firm, config_dict)
      Writes the user-confirmed config to
      `io/{firm}/configs/brand-{firm}-config.yaml`, MERGING with any existing
      file. Specifically preserves `company.conventional_name` from the firm-
      creation scaffold, since the user typed that and Claude shouldn't
      override it.

Uses ANTHROPIC_API_KEY from the orchestrator's environment — same key already
required for memo generation. No new secret management.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from anthropic import Anthropic

from ..paths import get_io_root

# Model and limits.
BRAND_FETCH_MODEL = os.environ.get("MEMOPOP_BRAND_MODEL", "claude-haiku-4-5-20251001")
MAX_ITERATIONS = 8
MAX_FETCH_BYTES = 60_000  # cap text returned to Claude per URL
HTTP_TIMEOUT_SECS = 10.0


# --- Tool definitions surfaced to Claude ---

_TOOL_FETCH_URL = {
    "name": "fetch_url",
    "description": (
        "Fetch the contents of an absolute URL over HTTP. Returns the response "
        "body as text (capped at ~60KB). Use this to retrieve HTML pages, "
        "linked CSS files, robots.txt, or any other text-shaped resource. "
        "Strategy: start with the firm's homepage. Follow links to /about, "
        "/team, /press, or to the main stylesheet href if you need more signal "
        "for colors, fonts, official names, or taglines. Avoid fetching the "
        "same URL twice."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Absolute URL to fetch (must start with http:// or https://).",
            },
        },
        "required": ["url"],
    },
}

_TOOL_SUBMIT = {
    "name": "submit_brand_config",
    "description": (
        "Call this exactly once when you have gathered enough information to "
        "populate the firm's brand config. Provide your best-guess values. "
        "It's OK to leave fields empty when you genuinely couldn't determine "
        "them — the user will review and fill in the gaps. Hex colors must be "
        "of the form `#RRGGBB`."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            # Identity
            "company_name": {
                "type": "string",
                "description": "Official firm name as it appears on the website (e.g., 'Sequoia Capital', 'Hypernova Ventures').",
            },
            "company_legal_entity_name": {
                "type": "string",
                "description": "Legal entity name for disclosures (often hard to find — leave empty if not surfaced anywhere).",
            },
            "tagline": {
                "type": "string",
                "description": "Short marketing line. Usually the homepage hero text or meta description.",
            },
            # Light-mode colors
            "primary_color": {"type": "string", "description": "Primary brand color, hex (e.g., '#5b21b6')."},
            "secondary_color": {"type": "string"},
            "accent_color": {"type": "string"},
            "text_dark": {"type": "string", "description": "Dark text color used on light backgrounds."},
            "text_light": {"type": "string", "description": "Light text color used on dark backgrounds (often '#ffffff')."},
            "background": {"type": "string", "description": "Main page background (usually white or near-white)."},
            "background_alt": {"type": "string", "description": "Alt background for callouts / code blocks."},
            # Dark-mode colors (best guess; can derive from light by inverting)
            "primary_color_dark": {"type": "string"},
            "secondary_color_dark": {"type": "string"},
            "accent_color_dark": {"type": "string"},
            "background_dark": {"type": "string"},
            "background_alt_dark": {"type": "string"},
            # Fonts
            "font_family": {"type": "string", "description": "Primary body font name (e.g., 'Inter', 'Helvetica Neue')."},
            "google_fonts_url": {
                "type": "string",
                "description": "If using Google Fonts, the full link href (https://fonts.googleapis.com/...).",
            },
            "header_font_family": {"type": "string"},
            # Logo
            "logo_light_url": {"type": "string", "description": "Absolute URL to the logo for light backgrounds."},
            "logo_dark_url": {
                "type": "string",
                "description": "Absolute URL to the logo for dark backgrounds. Often missing — leave empty if only one variant exists.",
            },
            "logo_alt_text": {"type": "string"},
            # Meta
            "confidence_notes": {
                "type": "string",
                "description": "One paragraph summarizing what you were confident about, what's a guess, and what was missing. Surfaces in the UI for the user to review.",
            },
        },
    },
}


# --- Public API ---


def fetch_brand_from_url(firm: str, url: str) -> dict[str, Any]:
    """Run the Claude tool-use loop to extract a brand config from a URL.

    Returns a structured dict shaped like the brand-config YAML. Does NOT
    write to disk — the caller surfaces this to the user for review.

    Raises:
        RuntimeError: if Claude finishes without calling submit_brand_config,
                      or the iteration cap is hit, or ANTHROPIC_API_KEY is unset.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The brand fetcher uses the same key "
            "as memo generation; add it to the orchestrator's .env file."
        )
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"URL must start with http:// or https://, got: {url}")

    client = Anthropic()
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Extract the brand identity for the firm whose website is {url}.\n\n"
                "Start with the homepage. If you need more signal for colors, fonts, "
                "an official legal name, or a tagline, fetch a linked /about, /team, "
                "/press page, or the main stylesheet. Don't fetch the same URL twice. "
                "Aim for at most 4–5 fetches.\n\n"
                "When you've gathered enough, call submit_brand_config with your best-guess "
                "values. Include a confidence_notes paragraph describing what was confident, "
                "what was a guess, and what you couldn't find. Leave any genuinely-missing "
                "field empty — the user will fill gaps in the next step."
            ),
        }
    ]

    final_config: Optional[dict[str, Any]] = None
    fetched_urls: set[str] = set()

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=BRAND_FETCH_MODEL,
            max_tokens=4096,
            tools=[_TOOL_FETCH_URL, _TOOL_SUBMIT],
            messages=messages,
        )

        # Mirror the assistant message into history so the next turn has context.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Claude stopped without calling submit_brand_config. Bail with what we have.
            break

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue

            if block.name == "fetch_url":
                target = block.input.get("url", "")
                if target in fetched_urls:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Skipped: already fetched this URL earlier in the session.",
                    })
                else:
                    fetched_urls.add(target)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _run_fetch_url(target),
                    })
            elif block.name == "submit_brand_config":
                final_config = dict(block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Brand config received. The user will review and confirm.",
                })

        messages.append({"role": "user", "content": tool_results})

        if final_config is not None:
            break

    if final_config is None:
        raise RuntimeError(
            "Claude completed its tool-use loop without calling submit_brand_config. "
            "Try a different URL or fill in the brand config manually."
        )

    return _shape_brand_config(firm, final_config)


def save_brand_config(firm: str, config: dict[str, Any]) -> Path:
    """Write the (user-confirmed) brand config to disk, merging with any existing file.

    The firm-creation scaffold writes `company.conventional_name`; this save preserves
    that field if it isn't explicitly overridden in the incoming config. Returns the
    path that was written.
    """
    path = _brand_config_path(firm)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError:
            # Don't silently lose data — but also don't fail the save. Leave
            # existing as empty and the new config wins.
            existing = {}

    merged = _deep_merge(existing, config)
    # Special-case: never lose conventional_name from the firm-creation scaffold.
    existing_conv = (
        existing.get("company", {}).get("conventional_name") if isinstance(existing.get("company"), dict) else None
    )
    if existing_conv and not merged.get("company", {}).get("conventional_name"):
        merged.setdefault("company", {})["conventional_name"] = existing_conv

    path.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
    return path


# --- Internal helpers ---


def _run_fetch_url(url: str) -> str:
    """Server-side HTTP fetch. Capped, defensive, never raises into Claude."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return f"Error: invalid URL {url!r}"
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_SECS, follow_redirects=True) as client:
            response = client.get(url)
        body = response.text[:MAX_FETCH_BYTES]
        ctype = response.headers.get("content-type", "")
        truncated_note = (
            f"\n\n[Truncated to {MAX_FETCH_BYTES} bytes]"
            if len(response.text) > MAX_FETCH_BYTES
            else ""
        )
        return (
            f"GET {url}\n"
            f"Status: {response.status_code}\n"
            f"Content-Type: {ctype}\n\n"
            f"{body}{truncated_note}"
        )
    except httpx.RequestError as e:
        return f"Error fetching {url}: {type(e).__name__}: {e}"
    except Exception as e:
        return f"Unexpected error fetching {url}: {type(e).__name__}: {e}"


_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{3,8}$")


def _normalize_hex(value: Any) -> Optional[str]:
    """Coerce Claude's color guesses to a `#RRGGBB` form, or None if unparseable."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    if not v.startswith("#"):
        v = f"#{v}"
    if not _HEX_RE.match(v):
        return None
    # Expand 4-char (#RGBA) to 8-char by ignoring; expand 3-char to 6-char.
    if len(v) == 4:  # #RGB
        v = "#" + "".join(ch * 2 for ch in v[1:])
    return v.lower()


def _drop_empty(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively drop empty strings, None, and empty dicts so the YAML stays clean."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            nested = _drop_empty(v)
            if nested:
                out[k] = nested
        elif v not in (None, "", [], {}):
            out[k] = v
    return out


def _shape_brand_config(firm: str, claude_output: dict[str, Any]) -> dict[str, Any]:
    """Map Claude's flat tool-use output into the brand-config YAML structure."""
    company = {
        "name": claude_output.get("company_name", "").strip(),
        "legal_entity_name": claude_output.get("company_legal_entity_name", "").strip(),
        "tagline": claude_output.get("tagline", "").strip(),
        "confidential_footer": "This document is confidential and proprietary to {company_name}.",
    }

    colors = {
        "primary": _normalize_hex(claude_output.get("primary_color")),
        "secondary": _normalize_hex(claude_output.get("secondary_color")),
        "accent": _normalize_hex(claude_output.get("accent_color")),
        "text_dark": _normalize_hex(claude_output.get("text_dark")),
        "text_light": _normalize_hex(claude_output.get("text_light")),
        "background": _normalize_hex(claude_output.get("background")),
        "background_alt": _normalize_hex(claude_output.get("background_alt")),
    }

    colors_dark = {
        "primary": _normalize_hex(claude_output.get("primary_color_dark")),
        "secondary": _normalize_hex(claude_output.get("secondary_color_dark")),
        "accent": _normalize_hex(claude_output.get("accent_color_dark")),
        "background": _normalize_hex(claude_output.get("background_dark")),
        "background_alt": _normalize_hex(claude_output.get("background_alt_dark")),
    }

    fonts = {
        "family": claude_output.get("font_family", "").strip(),
        "fallback": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "google_fonts_url": claude_output.get("google_fonts_url", "").strip(),
        "weight": 400,
        "header_family": claude_output.get("header_font_family", "").strip(),
        "header_fallback": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "header_weight": 700,
    }

    logo = {
        "light_mode": claude_output.get("logo_light_url", "").strip(),
        "dark_mode": claude_output.get("logo_dark_url", "").strip(),
        "width": "180px",
        "height": "60px",
        "alt": claude_output.get("logo_alt_text", "").strip() or company["name"],
    }

    shaped = {
        "company": company,
        "colors": colors,
        "colors_dark": colors_dark,
        "fonts": fonts,
        "logo": logo,
        "_meta": {
            "fetched_for_firm": firm,
            "confidence_notes": claude_output.get("confidence_notes", "").strip(),
        },
    }
    return _drop_empty(shaped)


def _brand_config_path(firm: str) -> Path:
    return get_io_root() / firm / "configs" / f"brand-{firm}-config.yaml"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `overlay` onto `base`. Overlay wins for non-dict values."""
    result: dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

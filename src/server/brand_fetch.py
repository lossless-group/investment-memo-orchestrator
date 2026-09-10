"""Auto-populate a firm's brand config by reading their website with Claude.

Exposes two operations:

  fetch_brand_from_url(firm, url) -> dict
      Asks Brandfetch for the firm's published brand data, reads the homepage
      and /about, then asks a model for the fields Brandfetch does not carry.
      Returns a structured dict shaped like the brand-config YAML — does NOT
      write to disk. The caller (typically the API handler) hands this to the
      user for review/edit before saving.

  save_brand_config(firm, config_dict)
      Writes the user-confirmed config to
      `io/{firm}/configs/brand-{firm}-config.yaml`, MERGING with any existing
      file. Specifically preserves `company.conventional_name` from the firm-
      creation scaffold, since the user typed that and Claude shouldn't
      override it.

Colors, fonts, logos and the display name come from Brandfetch when
BRANDFETCH_API_KEY is set — facts rather than readings. The model fills only
what Brandfetch does not publish. Without the key the model infers everything,
as it always did.

Model calls go through `src/llm_provider`, so this runs on the Claude Code seat
like the rest of the pipeline.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml

from ..paths import get_io_root
from ..llm_provider import cli_available, complete
from .brandfetch_api import (
    api_key_present as brandfetch_key_present,
    describe_payload,
    fetch_brand,
    shape_for_brand_config,
)

# Model and limits.
BRAND_FETCH_MODEL = os.environ.get("MEMOPOP_BRAND_MODEL", "claude-haiku-4-5-20251001")
MAX_FETCH_BYTES = 60_000  # cap text returned to the model per URL
HTTP_TIMEOUT_SECS = 10.0
BRAND_FETCH_TIMEOUT_SECS = 420


# --- The gap set ---
#
# Brandfetch publishes colors, fonts, logos and the display name as data. It does
# not publish a legal entity name, a Google Fonts URL, a dark-mode palette, or a
# tagline — its `description` is a sentence about the company, not a hero line.
# These are the keys the model is asked for, and only these.
_MODEL_GAP_KEYS = (
    "company_name",
    "company_legal_entity_name",
    "tagline",
    "primary_color",
    "secondary_color",
    "accent_color",
    "text_dark",
    "text_light",
    "background",
    "background_alt",
    "primary_color_dark",
    "secondary_color_dark",
    "accent_color_dark",
    "background_dark",
    "background_alt_dark",
    "font_family",
    "google_fonts_url",
    "header_font_family",
    "logo_light_url",
    "logo_dark_url",
    "logo_alt_text",
    "confidence_notes",
)


# --- Public API ---


def fetch_brand_from_url(firm: str, url: str) -> dict[str, Any]:
    """Build a brand config for `url`: Brandfetch for facts, a model for the gaps.

    Returns a structured dict shaped like the brand-config YAML. Does NOT write
    to disk — the caller surfaces this to the user for review.

    **Brandfetch wins.** Anything the API supplied is copied over the model's
    answer for that key, whatever the model said. A hex that came from a brand
    data API is checkable; a hex a model read off a stylesheet is a reading. This
    matters more than it sounds: a brand config copy-pasted between firms with
    its colors never updated is a failure this repo has actually shipped, and the
    only durable defence is a factual source.

    **What this gave up.** It used to be a Claude tool-use loop that could follow
    whatever links it judged useful — /about, /press, a stylesheet href — across
    up to eight turns. `llm_provider.complete()` is single-turn and has no tool
    surface, so the pages are fetched here instead: the homepage and, when it
    resolves, /about. That is less adaptive. It is the right trade now that the
    fields hardest to infer arrive as data, and it is what lets this module use
    the Claude Code seat like every other agent in the pipeline.

    Raises:
        ValueError: if the URL is not absolute.
        RuntimeError: if no model provider is reachable, or the call fails.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"URL must start with http:// or https://, got: {url}")

    if not (cli_available() or os.environ.get("ANTHROPIC_API_KEY")):
        raise RuntimeError(
            "No model provider is reachable. Either install and log in to the "
            "Claude Code CLI, or set ANTHROPIC_API_KEY in the orchestrator's .env."
        )

    # 1. Facts.
    known: dict[str, Any] = {}
    payload = fetch_brand(url)
    if payload:
        known = shape_for_brand_config(payload)
        print(f"    🎨 Brandfetch: {describe_payload(payload)} — "
              f"{len(known)} field(s) resolved from data")
    elif not brandfetch_key_present():
        print("    ℹ️  BRANDFETCH_API_KEY not set — inferring every field from the site")

    # 2. Page text for whatever is left.
    pages = [(url, _run_fetch_url(url))]
    about = url.rstrip("/") + "/about"
    about_text = _run_fetch_url(about)
    if about_text and not about_text.startswith("Error"):
        pages.append((about, about_text))

    corpus = "\n\n".join(
        f"===== {page_url} =====\n{text}" for page_url, text in pages
    )

    missing = [k for k in _MODEL_GAP_KEYS if k not in known]
    known_block = (
        "\n".join(f"  {k}: {v}" for k, v in sorted(known.items()))
        or "  (nothing — the brand data API had no record of this domain)"
    )

    prompt = (
        "You are extracting a firm's brand identity for a document template.\n\n"
        "ALREADY ESTABLISHED from a brand data API. These are facts. Do not "
        "contradict them, do not restate them, do not include them in your "
        "answer:\n"
        f"{known_block}\n\n"
        "WEBSITE CONTENT:\n"
        f"{corpus}\n\n"
        "Return ONLY a JSON object filling in as many of these keys as the "
        "content supports:\n"
        f"  {', '.join(missing)}\n\n"
        "Rules:\n"
        "- Hex colors must be of the form #RRGGBB.\n"
        "- Omit a key entirely rather than guessing at it. An absent field is "
        "reviewed and filled by a human; a wrong one is shipped.\n"
        "- `tagline` is the homepage hero line or meta description, not a "
        "sentence describing the company.\n"
        "- Dark-mode colors may be derived from the established light-mode "
        "palette if the site has no dark theme; say so in confidence_notes.\n"
        "- `confidence_notes` is one paragraph: what was certain, what was "
        "inferred, what was missing.\n"
    )

    completion = complete(
        prompt,
        max_tokens=4096,
        model=BRAND_FETCH_MODEL,
        timeout=BRAND_FETCH_TIMEOUT_SECS,
    )
    if not completion.ok:
        raise RuntimeError(
            f"Brand extraction failed: {completion.error or 'empty response'} "
            f"(provider={completion.provider})"
        )

    inferred = completion.json()
    if not isinstance(inferred, dict):
        # Brandfetch data alone is still a usable config; refusing to return it
        # because the prose pass produced no JSON would throw away good facts.
        print("    ⚠️  Brand model returned no usable JSON; using Brandfetch data alone")
        inferred = {}

    merged = {**{k: v for k, v in inferred.items() if k in _MODEL_GAP_KEYS}, **known}
    return _shape_brand_config(firm, merged)


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

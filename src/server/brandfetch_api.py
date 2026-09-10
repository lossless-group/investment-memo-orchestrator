"""Brandfetch API client — the factual half of brand-config population.

`brand_fetch.py` asks Claude to read a firm's website and *infer* its colors,
fonts and logos from HTML and CSS. That works, and it guesses. Brandfetch
publishes the same fields as data:

    colors[]  {type: accent|dark|light,  hex}
    fonts[]   {type: title|body,         name}
    logos[]   {type: logo|icon|symbol,   theme: light|dark, formats[{format, src}]}
    name, description, links[]

So this module is asked first and Claude is asked only for what is left —
tagline phrasing, legal entity, the dark-mode palette, the Google Fonts URL.
The split matters beyond tidiness: a copy-pasted brand config that never got its
colors updated is a real failure this repo has shipped, and a hex that came from
an API is checkable in a way that a hex a model produced is not.

Requires BRANDFETCH_API_KEY. Absent or failing, every function here degrades to
None and the caller falls back to the Claude path unchanged — a brand config
that is guessed is much better than a run that dies.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

BRANDFETCH_BASE = "https://api.brandfetch.io/v2/brands"
HTTP_TIMEOUT_SECS = 20.0

# Preference order when several formats exist for one logo. SVG scales into
# both the HTML export and the PDF; the raster formats are the fallback.
_FORMAT_PREFERENCE = ("svg", "png", "webp", "jpeg", "jpg")


class BrandfetchUnavailable(RuntimeError):
    """No API key, or the API could not be reached. Callers fall back."""


def api_key_present() -> bool:
    return bool(os.environ.get("BRANDFETCH_API_KEY"))


def domain_from_url(url: str) -> str:
    """`https://www.humain.vc/about?x=1` -> `humain.vc`.

    Brandfetch keys on registrable domain. A `www.` prefix returns a 404 rather
    than a redirect, which reads as "this firm is not in the index" and is the
    wrong conclusion entirely.
    """
    candidate = (url or "").strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    host = (urlparse(candidate).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def fetch_brand(url_or_domain: str, *, timeout: float = HTTP_TIMEOUT_SECS) -> Optional[dict[str, Any]]:
    """Raw Brandfetch payload for a domain, or None.

    None covers every "we could not get data" case — no key, unknown domain,
    rate limit, network failure — because the caller's response to all of them
    is identical: fall back to inference.
    """
    key = os.environ.get("BRANDFETCH_API_KEY")
    if not key:
        return None

    domain = domain_from_url(url_or_domain)
    if not domain:
        return None

    try:
        response = httpx.get(
            f"{BRANDFETCH_BASE}/{domain}",
            headers={"Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
    except httpx.RequestError as e:
        print(f"    ⚠️  Brandfetch unreachable for {domain}: {type(e).__name__}")
        return None

    if response.status_code == 404:
        print(f"    ℹ️  Brandfetch has no record of {domain}")
        return None
    if response.status_code in (401, 403):
        print(f"    ⚠️  Brandfetch rejected the API key ({response.status_code}) — "
              "check BRANDFETCH_API_KEY")
        return None
    if response.status_code == 429:
        print("    ⚠️  Brandfetch rate limit hit; falling back to inference")
        return None
    if response.status_code != 200:
        print(f"    ⚠️  Brandfetch returned {response.status_code} for {domain}")
        return None

    try:
        return response.json()
    except ValueError:
        print(f"    ⚠️  Brandfetch returned non-JSON for {domain}")
        return None


# --- Shaping -------------------------------------------------------------


def _hex(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    if not v.startswith("#"):
        v = f"#{v}"
    return v.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", v) else None


# CSS keywords and function syntax that are not font names. Brandfetch scrapes
# `font-family` declarations and does not resolve custom properties, so a site
# built on CSS variables yields names like `var(--font-body)` with
# `origin: "custom"` and no weights. humain.vc is a live example. Writing that
# into a brand config produces `font-family: var(--font-body)` in the export,
# which resolves to nothing and silently falls back to the browser default.
#
# Rejecting it is the right degradation: the key goes missing, the model is
# asked for it, and a human reviews the answer. "It came from an API" is a
# reason to trust data more, not a reason to stop checking it.
_NOT_A_FONT_NAME = re.compile(
    r"""^\s*(?:
          var\s*\(          # var(--x)
        | inherit
        | initial
        | unset
        | revert
        | none
        | currentcolor
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _font_name(value: Any) -> Optional[str]:
    """A usable font family name, or None."""
    if not isinstance(value, str):
        return None
    name = value.strip().strip("\"'")
    if not name or _NOT_A_FONT_NAME.match(name):
        return None
    # A stack rather than a name ("Inter, sans-serif") — take the first entry.
    if "," in name:
        name = name.split(",")[0].strip().strip("\"'")
    # Anything still carrying CSS punctuation is not a name.
    if not name or any(ch in name for ch in "(){};:"):
        return None
    return name


def _pick_logo(logos: list[dict[str, Any]], theme: str) -> Optional[str]:
    """Best URL for a themed logo.

    Prefers `type == "logo"` (the full wordmark) over `icon`/`symbol`, because
    the brand config's slot is a header lockup, not a favicon. Falls back to the
    other theme rather than returning nothing — one logo in both modes beats a
    missing header.
    """
    def candidates(want_theme: Optional[str], want_type: Optional[str]):
        for logo in logos:
            if want_theme and (logo.get("theme") or "").lower() != want_theme:
                continue
            if want_type and (logo.get("type") or "").lower() != want_type:
                continue
            formats = logo.get("formats") or []
            by_format = {(f.get("format") or "").lower(): f.get("src") for f in formats}
            for fmt in _FORMAT_PREFERENCE:
                if by_format.get(fmt):
                    yield by_format[fmt]

    for want_theme, want_type in (
        (theme, "logo"),                 # exact
        (theme, None),                   # any type, right theme
        (None, "logo"),                  # any theme, wordmark
        (None, None),                    # anything at all
    ):
        for src in candidates(want_theme, want_type):
            return src
    return None


def shape_for_brand_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a Brandfetch payload onto the flat keys `_shape_brand_config` expects.

    Deliberately partial. Brandfetch does not publish a legal entity name, a
    Google Fonts URL, or a dark-mode palette, and its `description` is a
    sentence about the company rather than a tagline. Those keys are left absent
    so the Claude pass can see what is missing rather than being handed empty
    strings it might mistake for answers.
    """
    out: dict[str, Any] = {}

    if name := (payload.get("name") or "").strip():
        out["company_name"] = name

    colors = payload.get("colors") or []
    by_type = {(c.get("type") or "").lower(): c for c in colors if isinstance(c, dict)}

    if accent := _hex((by_type.get("accent") or {}).get("hex")):
        out["primary_color"] = accent
        out["accent_color"] = accent
    if dark := _hex((by_type.get("dark") or {}).get("hex")):
        out["text_dark"] = dark
        out["secondary_color"] = dark
    if light := _hex((by_type.get("light") or {}).get("hex")):
        out["background"] = light

    fonts = payload.get("fonts") or []
    by_font = {(f.get("type") or "").lower(): f for f in fonts if isinstance(f, dict)}
    if title := _font_name((by_font.get("title") or {}).get("name")):
        out["header_font_family"] = title
    if body := _font_name((by_font.get("body") or {}).get("name")):
        out["font_family"] = body

    logos = [lg for lg in (payload.get("logos") or []) if isinstance(lg, dict)]
    if light_logo := _pick_logo(logos, "light"):
        out["logo_light_url"] = light_logo
    if dark_logo := _pick_logo(logos, "dark"):
        out["logo_dark_url"] = dark_logo
    if out.get("company_name"):
        out["logo_alt_text"] = out["company_name"]

    return {k: v for k, v in out.items() if v}


def describe_payload(payload: dict[str, Any]) -> str:
    """One line for the run log, so an operator can see what came from data."""
    colors = len(payload.get("colors") or [])
    fonts = len(payload.get("fonts") or [])
    logos = len(payload.get("logos") or [])
    score = payload.get("qualityScore")
    bits = [f"{colors} color(s)", f"{fonts} font(s)", f"{logos} logo(s)"]
    if isinstance(score, (int, float)):
        bits.append(f"quality {score:.2f}")
    return ", ".join(bits)

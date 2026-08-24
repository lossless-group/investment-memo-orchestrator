"""
Slide Image CDN

Thin wrapper around the ``prep-images-for-embed`` skill's ``prep-images.mjs``.

Deliberately a wrapper and not a reimplementation. That script already encodes
results that were measured rather than assumed, and any second implementation
would drift from them:

- **Upload JPEG, never WebP.** ImageKit content-negotiates on ``Accept``. Upload
  WebP and the fallback served to clients that do not advertise it is a PNG up
  to three times larger — including to link unfurlers.
- **Strip metadata before upload.** ``exiftool -all=`` runs on every file;
  screenshots carry device and location data that has no business on a CDN.
- **Alt text is mandatory.** The script refuses placeholders. For a slide corpus
  that rule is load-bearing: alt text is the only searchable description of a
  slide that is otherwise just pixels.

Credentials come from ``~/.secrets`` (``IMAGEKIT_PRIVATE_KEY``,
``IMAGEKIT_URL_ENDPOINT``). Uploading is optional throughout — a deck analyzed
with no CDN configured still produces complete documents, with local image paths
and no remote URL.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


SKILL_SCRIPT = Path(
    "/Users/mpstaton/code/lossless-monorepo/context-v/agent-skills/"
    "prep-images-for-embed/scripts/prep-images.mjs"
)

SECRETS_FILE = Path.home() / ".secrets"


def cdn_available() -> bool:
    """Whether an upload could succeed: script, node, and a private key present."""
    if not SKILL_SCRIPT.exists() or not shutil.which("node"):
        return False
    if not SECRETS_FILE.exists():
        return False
    try:
        return "IMAGEKIT_PRIVATE_KEY" in SECRETS_FILE.read_text(encoding="utf-8")
    except OSError:
        return False


def _bem_name(company: str, deck_slug: str, index: int, slide_type: str) -> str:
    """
    The skill's naming convention: ``Block__Element--Modifier``.

    Filenames carry search weight, so the slide's company, position, and type all
    belong in the name rather than in a database somewhere else.
    """
    def train(value: str) -> str:
        parts = [p for p in re.split(r"[^A-Za-z0-9]+", value or "") if p]
        return "-".join(p if any(c.isupper() for c in p[1:]) else p.capitalize() for p in parts)

    return f"{train(company)}-{train(deck_slug)}__Slide-{index:02d}--{train(slide_type)}"


def upload_slides(
    images: Sequence[Dict[str, Any]],
    company: str,
    deck_slug: str,
    repo: str = "example-firm/portfolio",
    dry_run: bool = False,
) -> Dict[int, str]:
    """
    Upload rendered slide images and return ``{slide_index: cdn_url}``.

    Args:
        images: Dicts with ``index``, ``path``, ``slide_type``, and ``alt``. An
            optional ``name`` overrides the generated BEM name, for callers whose
            unit is not a whole slide.
        company: Portfolio company, used in the image name.
        deck_slug: The deck folder name, which becomes the CDN sub-folder.
        repo: CDN folder root. Slash-separated values become nested folders, so
            the default lands slides under ``/example-firm/portfolio/<company>/<deck>/``.
        dry_run: Run the pipeline without uploading.

    Returns:
        Index-to-URL map. Empty when the CDN is unavailable or the call fails —
        never raises, because a missing CDN must not cost a transcription.
    """
    usable = [
        i for i in images
        if i.get("path") and Path(i["path"]).exists() and (i.get("alt") or "").strip()
    ]
    missing_alt = [i["index"] for i in images if not (i.get("alt") or "").strip()]
    if missing_alt:
        print(f"   ⚠️  no alt text for slide(s) {missing_alt} — not uploading those")

    if not usable:
        return {}

    if not cdn_available() and not dry_run:
        print("   ⚠️  CDN unavailable (need node, the prep-images skill, and "
              "IMAGEKIT_PRIVATE_KEY in ~/.secrets) — keeping local paths only")
        return {}

    cmd: List[str] = [
        "node", str(SKILL_SCRIPT),
        # Company and deck each get their own folder level. prep-images.mjs
        # kebabs per path segment rather than flattening, so both of these keep
        # their separators.
        "--repo", repo,
        "--slug", f"{company}/{deck_slug}",
        "--emit", "json",
        "--format", "jpg",   # never webp; see the module docstring
        "--width", "1600",
    ]
    if dry_run:
        cmd.append("--dry-run")

    for image in usable:
        cmd += [
            "--src", str(image["path"]),
            "--name", image.get("name")
                      or _bem_name(company, deck_slug, image["index"],
                                   image.get("slide_type", "slide")),
            "--alt", image["alt"],
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=900, text=True)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"   ⚠️  CDN upload failed to run: {e}")
        return {}

    if result.returncode != 0:
        print(f"   ⚠️  CDN upload exited {result.returncode}: {result.stderr.strip()[:300]}")
        return {}

    return _parse_urls(result.stdout, usable)


def _parse_urls(stdout: str, images: Sequence[Dict[str, Any]]) -> Dict[int, str]:
    """
    Map the script's JSON output back onto slide indices.

    Falls back to positional pairing when the payload shape is not what we
    expect: the script's ``--emit json`` contract is not ours to depend on
    tightly, and a shape change should degrade rather than lose every URL.
    """
    urls: Dict[int, str] = {}
    try:
        match = re.search(r"[\[{].*[\]}]", stdout, re.DOTALL)
        payload = json.loads(match.group()) if match else None
    except (json.JSONDecodeError, AttributeError):
        payload = None

    entries = payload if isinstance(payload, list) else (
        payload.get("images") if isinstance(payload, dict) else None
    )

    if isinstance(entries, list) and len(entries) == len(images):
        for image, entry in zip(images, entries):
            url = entry.get("url") if isinstance(entry, dict) else None
            if url:
                urls[image["index"]] = url
        if urls:
            return urls

    # Last resort: harvest URLs in emission order.
    found = re.findall(r"https://ik\.imagekit\.io/\S+?\.(?:jpg|jpeg|png|webp)", stdout)
    for image, url in zip(images, found):
        urls[image["index"]] = url
    return urls

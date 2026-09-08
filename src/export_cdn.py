"""
Move base64-embedded images out of exported HTML and onto the CDN.

`export_branded.py` runs pandoc with `--embed-resources`, which inlines every
image as a base64 data URI. That is what makes the export self-contained, and it
is also why a single Metabologic memo is 17.3 MB — 15.5 MB of it, 90%, is 36
base64 blobs. Multiply by two modes and several versions and the exports
directory alone is 84 MB of committed build output.

Deleting the exports would fix the byte count and lose the artifact. Uploading
the images instead keeps the artifact, and keeps it openable: the HTML still
renders anywhere, it just fetches images over the network rather than carrying
them. Roughly 90% of the file goes away.

This runs AFTER pandoc rather than before it, deliberately. Rewriting the
markdown first would fight `--embed-resources`, which fetches and inlines remote
resources too — so the flag would simply re-embed what we had just uploaded. By
operating on the produced HTML, pandoc keeps doing exactly what it does today
for CSS and fonts, and only images change.

Uploads go through the same `prep-images-for-embed` script `slide_cdn` uses, so
there is one uploader, one naming convention and one set of credentials. The
JPEG-not-WebP rule is that skill's measured result, not a preference.
"""

from __future__ import annotations

import base64
import hashlib
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .agents.slides.slide_cdn import SKILL_SCRIPT, cdn_available

# <img ...> carrying a base64 payload. Attribute order varies, so the tag is
# captured whole and the pieces are pulled out of it separately.
IMG_TAG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
DATA_URI_RE = re.compile(
    r'src\s*=\s*"data:image/(?P<fmt>[a-zA-Z0-9+.\-]+);base64,(?P<payload>[^"]+)"',
    re.IGNORECASE,
)
# Pandoc emits `aria-label` on figure images and `alt` on plain ones. Both are
# descriptions; either satisfies the skill's alt-text-is-mandatory rule.
ALT_RE = re.compile(r'(?:alt|aria-label)\s*=\s*"(?P<alt>[^"]*)"', re.IGNORECASE)

_EXT = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "gif": "gif",
        "webp": "webp", "svg+xml": "svg"}


@dataclass
class ExternalizeResult:
    html_path: Path
    uploaded: int = 0
    replaced: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    found: int = 0
    skipped: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def saved_pct(self) -> float:
        if not self.bytes_before:
            return 0.0
        return 100.0 * (1 - self.bytes_after / self.bytes_before)


def _slug(value: str, limit: int = 48) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return (value[:limit].rstrip("-")) or "image"


def externalize_embedded_images(
    html_path: Path,
    *,
    company: str,
    version: str = "",
    repo: str = "memopop",
    dry_run: bool = False,
) -> ExternalizeResult:
    """
    Replace every base64 data URI in an exported HTML file with a CDN URL.

    Identical images are uploaded once — a logo repeated on every page is one
    asset, not thirty. Anything without alt text is left embedded rather than
    uploaded: the prep-images skill treats alt text as mandatory, and an image
    nobody described is exactly the one a reader will need described.
    """
    html_path = Path(html_path)
    result = ExternalizeResult(html_path=html_path)
    if not html_path.exists():
        result.error = "file not found"
        return result

    html = html_path.read_text(encoding="utf-8", errors="replace")
    result.bytes_before = len(html.encode("utf-8"))
    result.bytes_after = result.bytes_before

    if not cdn_available():
        result.error = ("CDN unavailable — need node, the prep-images skill, and "
                        "IMAGEKIT_PRIVATE_KEY in ~/.secrets")
        return result

    # Collect unique payloads, keyed by content hash so a repeated image uploads once.
    by_hash: Dict[str, Dict] = {}
    for tag in IMG_TAG_RE.findall(html):
        data_match = DATA_URI_RE.search(tag)
        if not data_match:
            continue
        alt = (ALT_RE.search(tag).group("alt").strip() if ALT_RE.search(tag) else "")
        if not alt:
            result.skipped.append("image with no alt text — left embedded")
            continue
        payload = data_match.group("payload")
        digest = hashlib.sha256(payload.encode("ascii", "ignore")).hexdigest()[:12]
        by_hash.setdefault(digest, {
            "fmt": data_match.group("fmt").lower(),
            "payload": payload,
            "alt": alt,
        })

    result.found = len(by_hash)
    if not by_hash:
        return result

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        cmd: List[str] = [
            "node", str(SKILL_SCRIPT),
            "--repo", repo,
            "--slug", f"{_slug(company)}/exports{'/' + _slug(version) if version else ''}",
            "--emit", "json",
            "--format", "jpg",   # measured: WebP's fallback is a PNG up to 3x larger
            "--width", "1600",
        ]
        for digest, item in by_hash.items():
            ext = _EXT.get(item["fmt"], "png")
            staged = tmpdir / f"{_slug(item['alt'])}--{digest}.{ext}"
            try:
                staged.write_bytes(base64.b64decode(item["payload"], validate=False))
            except Exception:  # noqa: BLE001 - a corrupt payload stays embedded
                result.skipped.append(f"undecodable payload {digest}")
                continue
            item["staged"] = staged
            cmd += ["--src", str(staged), "--name", staged.stem, "--alt", item["alt"]]

        if dry_run:
            cmd.append("--dry-run")

        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=900, text=True)
        except (subprocess.TimeoutExpired, OSError) as exc:
            result.error = f"upload failed to run: {exc}"
            return result
        if proc.returncode != 0:
            result.error = f"upload exited {proc.returncode}: {proc.stderr.strip()[:300]}"
            return result

        urls = _parse_urls(proc.stdout)

    # Map each digest to a URL by matching the staged filename the uploader echoed.
    replacements: Dict[str, str] = {}
    for digest, item in by_hash.items():
        staged = item.get("staged")
        if not staged:
            continue
        url = urls.get(staged.stem) or urls.get(staged.name)
        if url:
            replacements[digest] = url

    if not replacements:
        result.error = ("upload produced no URLs"
                        + (" (expected for --dry-run)" if dry_run else ""))
        return result

    def _swap(tag: str) -> str:
        data_match = DATA_URI_RE.search(tag)
        if not data_match:
            return tag
        digest = hashlib.sha256(
            data_match.group("payload").encode("ascii", "ignore")
        ).hexdigest()[:12]
        url = replacements.get(digest)
        if not url:
            return tag
        result.replaced += 1
        return tag[:data_match.start()] + f'src="{url}"' + tag[data_match.end():]

    html = IMG_TAG_RE.sub(lambda m: _swap(m.group(0)), html)
    if not dry_run:
        html_path.write_text(html, encoding="utf-8")

    result.uploaded = len(replacements)
    result.bytes_after = len(html.encode("utf-8"))
    return result


def _parse_urls(stdout: str) -> Dict[str, str]:
    """Map uploaded basename → CDN URL from the script's JSON or plain output."""
    urls: Dict[str, str] = {}
    import json

    try:
        payload = json.loads(stdout)
        items = payload if isinstance(payload, list) else payload.get("images", [])
        for item in items:
            url = item.get("url") or item.get("cdnUrl") or ""
            name = item.get("name") or Path(item.get("src", "")).stem
            if url and name:
                urls[name] = url
                urls[Path(url).stem] = url
    except Exception:  # noqa: BLE001 - fall through to the regex below
        pass

    for url in re.findall(r"https://ik\.imagekit\.io/\S+?\.(?:jpg|jpeg|png|webp|svg)", stdout):
        urls.setdefault(Path(url).stem, url)
    return urls

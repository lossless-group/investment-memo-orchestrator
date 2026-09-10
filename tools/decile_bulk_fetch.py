#!/usr/bin/env python3
"""
Bulk-download Decile Hub data-room files over the REST API.

Why not the MCP server: `download_file` returns the bytes as base64 in the tool
result. Large files spill to a temp file (fine), but small ones come back inline
and burn an agent's context — a 23KB spreadsheet cost 30k tokens and still had
to be re-emitted to reach disk. For 407 files that is untenable. The REST API
streams straight to disk and nothing passes through a model.

Auth is the raw API token in `Authorization` — no `Bearer` prefix; the scheme is
apiKey-in-header. Per the decile-hub-connector skill, the value lives under four
spellings of one name, so all are tried.

    python tools/decile_bulk_fetch.py --list
    python tools/decile_bulk_fetch.py --name "Financial Package" --dest io/humain/fund
    python tools/decile_bulk_fetch.py --folder "Financial Reports" --dest io/humain/fund

Never prints the token. Skips files already on disk with a matching size, so it
is safe to re-run and resumes an interrupted pull.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterator, List, Optional

TOKEN_NAMES = ("DECILEHUB_API_KEY", "DECILE_HUB_API_KEY", "DECILE_API_KEY", "DECILEHUB_TOKEN")
URL_NAMES = ("DECILE_API_URL", "DECILE_API_BASE_URL")
DEFAULT_BASE = "https://humain.decilehub.com"

ENV_CANDIDATES = (
    Path.home() / ".secrets",
    Path.home() / "code/lossless-monorepo/self-host-stack/client-stacks/humain-vc/decilehub/.env",
    Path.home() / "code/lossless-monorepo/self-host-stack/client-stacks/humain-vc/.env",
)


def load_env() -> Dict[str, str]:
    """Read the token from the operator's secrets without echoing it."""
    found: Dict[str, str] = {}
    for name in TOKEN_NAMES + URL_NAMES:
        if os.environ.get(name):
            found[name] = os.environ[name]
    for path in ENV_CANDIDATES:
        if not path.exists():
            continue
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k in TOKEN_NAMES + URL_NAMES and v and k not in found:
                    found[k] = v
        except OSError:
            continue
    return found


def credentials() -> tuple[str, str]:
    env = load_env()
    token = next((env[n] for n in TOKEN_NAMES if env.get(n)), None)
    if not token:
        print(f"✗ no API token found. Looked for {', '.join(TOKEN_NAMES)} in the environment "
              f"and in: {', '.join(str(p) for p in ENV_CANDIDATES)}", file=sys.stderr)
        raise SystemExit(2)
    base = next((env[n] for n in URL_NAMES if env.get(n)), DEFAULT_BASE).rstrip("/")
    return token, base


def api_get(base: str, token: str, path: str, params: Optional[dict] = None) -> dict:
    url = f"{base}/api/v1/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"Authorization": token, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def iter_files(base: str, token: str, *, name: Optional[str] = None) -> Iterator[dict]:
    """Files use pagination pattern A: 0-indexed `page`, nested `pagination`."""
    page = 0
    while True:
        payload = api_get(base, token, "files", {"page": page, "name": name})
        rows = payload.get("data", [])
        if not rows:
            return
        yield from rows
        pg = payload.get("pagination", {})
        if page >= pg.get("total_pages", 1) - 1:
            return
        page += 1


def safe_name(row: dict) -> str:
    name = (row.get("file_name") or row.get("name") or f"file-{row['id']}").strip()
    name = re.sub(r"[/\x00]", "-", name)
    ext = row.get("extension") or ""
    if ext and not name.lower().endswith(ext.lower()):
        name += ext
    return name


def download(base: str, token: str, row: dict, dest_dir: Path) -> str:
    """
    Fetch one file, disambiguating name collisions by file id.

    Decile allows several files with the same name in the same folder, and they
    are not necessarily copies — four rows named "12_31_2024 … Financial
    Package.pdf" came back at 398KB, 157KB, 156KB and 154KB. Writing them all to
    one path silently keeps whichever landed last and discards three real
    revisions, so a colliding name gets the id appended.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"{base}/api/v1/files/{row['id']}/download"
    req = urllib.request.Request(url, headers={"Authorization": token})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as exc:
        return f"✗ {safe_name(row)}: HTTP {exc.code}"

    digest = hashlib.sha256(blob).hexdigest()
    dest = dest_dir / safe_name(row)

    if dest.exists():
        if hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
            return f"= {dest.name} (already current)"
        stem, ext = dest.stem, dest.suffix
        dest = dest_dir / f"{stem}--id{row['id']}{ext}"
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
            return f"= {dest.name} (already current)"

    dest.write_bytes(blob)
    return f"✓ {dest.name} ({len(blob) / 1024:.0f} KB)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="Substring filter on the file name.")
    ap.add_argument("--folder", help="Only files whose data-room folder matches this name.")
    ap.add_argument("--dest", default="io/humain/fund", help="Destination root.")
    ap.add_argument("--by-folder", action="store_true",
                    help="Nest downloads in a subdirectory per data-room folder.")
    ap.add_argument("--list", action="store_true", help="List matches; download nothing.")
    args = ap.parse_args()

    token, base = credentials()
    rows = list(iter_files(base, token, name=args.name))
    if args.folder:
        rows = [r for r in rows
                if any(args.folder.lower() in (f.get("name") or "").lower()
                       for f in r.get("data_room_folders", []))]

    print(f"{len(rows)} file(s) matched")
    if args.list:
        for r in rows:
            folders = "/".join(f.get("name", "") for f in r.get("data_room_folders", []))
            print(f"  {r['id']:>8}  {folders:<24}  {safe_name(r)}")
        return 0

    for r in rows:
        sub = ""
        if args.by_folder and r.get("data_room_folders"):
            sub = re.sub(r"[^\w\- ]", "", r["data_room_folders"][0].get("name", "")).strip()
        print("  " + download(base, token, r, Path(args.dest) / sub))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
